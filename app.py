"""
app.py
NOC Pre-Triage AI Assistant — Main Entry Point

Usage:
    python app.py --ticket tickets/sample_ticket_interface_down.json --mock
    python app.py --ticket tickets/sample_ticket_interface_down.json --mock --rebuild-index
    python app.py --ticket tickets/my_ticket.json  (live mode — requires Netmiko + Vault)

Workflow:
    1.  Load ticket from JSON
    2.  Classify ticket type
    3.  Extract device, interface, IP, VLAN fields
    4.  Validate device against approved scope
    5.  Retrieve matching runbook from local RAG
    6.  Select health checks based on ticket type
    7.  Run approved read-only commands through command broker
    8.  Sanitize outputs
    9.  Pass ticket summary + runbook + sanitized outputs to local LLM
    10. Generate engineer-facing triage note
    11. Save triage note to outputs/
    12. Write full audit log
"""

import argparse
import os
import sys
from pathlib import Path

import yaml


# ── Ensure we can import from tools/ regardless of working directory ──────────
sys.path.insert(0, str(Path(__file__).parent))


def load_config(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def classify_ticket(alert: str, ticket_types: dict) -> str:
    """Map an alert string to an internal ticket type key."""
    alert_lower = alert.lower()
    for type_key, config in ticket_types.get("ticket_types", {}).items():
        for alias in config.get("aliases", []):
            if alias.lower() in alert_lower or alert_lower in alias.lower():
                return type_key
    return "unknown"


def run_health_checks(
    broker,
    health_check_names: list[str],
    device: str,
    interface: str | None,
    ip: str | None,
    vlan: str | None,
) -> tuple[list[dict], str]:
    """
    Resolve health check names to commands, execute through broker,
    and return results list + formatted output string.
    """
    from tools.cisco_health_checks import resolve_commands

    commands = resolve_commands(health_check_names, interface=interface, ip=ip, vlan=vlan)

    results = []
    output_sections = []

    for cmd in commands:
        result = broker.run(cmd, device)
        results.append({
            "command": cmd,
            "success": result.success,
            "blocked": result.blocked,
            "block_reason": result.block_reason,
            "output": result.output if result.success else f"[BLOCKED: {result.block_reason}]",
        })
        if result.success:
            section = (
                f"{'=' * 50}\n"
                f"Command: {cmd}\n"
                f"{'=' * 50}\n"
                f"{result.output}\n"
            )
        elif result.blocked:
            section = f"[Command blocked: {cmd} — {result.block_reason}]\n"
        else:
            section = f"[Command failed: {cmd}]\n"

        output_sections.append(section)

    combined_output = "\n".join(output_sections)
    return results, combined_output


def print_banner() -> None:
    print("\n" + "=" * 60)
    print("  NOC AI Pre-Triage Agent")
    print("  Read-only analysis. No changes made.")
    print("=" * 60 + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="NOC AI Pre-Triage Agent — Read-only Cisco health check and triage note generator"
    )
    parser.add_argument(
        "--ticket", required=True,
        help="Path to ticket JSON file (e.g. tickets/sample_ticket_interface_down.json)"
    )
    parser.add_argument(
        "--mock", action="store_true", default=False,
        help="Use mock Cisco command outputs instead of live device connection"
    )
    parser.add_argument(
        "--rebuild-index", action="store_true", default=False,
        help="Force rebuild of the Chroma RAG index from runbooks/"
    )
    parser.add_argument(
        "--no-llm", action="store_true", default=False,
        help="Skip LLM and use template-based summary only"
    )
    args = parser.parse_args()

    # ── Banner ──────────────────────────────────────────────────────────────
    print_banner()

    # ── Load configs ─────────────────────────────────────────────────────────
    print("[1/9] Loading configuration...")
    ticket_types_config = load_config("config/ticket_types.yaml")
    safety_policy = load_config("config/safety_policy.yaml")
    allowed_commands = load_config("config/allowed_commands.yaml")

    max_commands = allowed_commands.get("max_commands_per_ticket", 15)
    rate_limit = allowed_commands.get("rate_limit_per_device_per_minute", 20)

    # ── Initialize audit logger ───────────────────────────────────────────────
    log_path = safety_policy.get("audit", {}).get("log_path", "logs/audit.jsonl")
    from tools.audit_logger import AuditLogger
    audit = AuditLogger(log_path=log_path, ticket_id="LOADING")

    # ── Load ticket ───────────────────────────────────────────────────────────
    print(f"[2/9] Loading ticket from: {args.ticket}")
    from tools.ticket_client import TicketClient
    ticket_client = TicketClient(audit_logger=audit)
    try:
        ticket = ticket_client.load_ticket(args.ticket)
    except Exception as e:
        print(f"\n[ERROR] Failed to load ticket: {e}")
        sys.exit(1)

    # Update audit logger with real ticket ID
    audit.ticket_id = ticket.ticket_id
    print(f"       Ticket ID: {ticket.ticket_id} | Alert: {ticket.alert} | Device: {ticket.device}")

    # ── Classify ticket ───────────────────────────────────────────────────────
    print("[3/9] Classifying ticket type...")
    ticket_type = classify_ticket(ticket.alert, ticket_types_config)
    type_config = ticket_types_config.get("ticket_types", {}).get(ticket_type, {})
    print(f"       Type: {ticket_type}")
    audit.ticket_classified(ticket_type=ticket_type, confidence="rule-based")

    # ── Validate device scope ─────────────────────────────────────────────────
    print("[4/9] Validating device scope...")
    from tools.safety import SafetyValidator
    safety = SafetyValidator()
    scope_result = safety.validate_device(ticket.device)
    audit.device_scope_check(
        device=ticket.device,
        allowed=scope_result.passed,
        reason=scope_result.reason,
    )
    if not scope_result.passed:
        print(f"\n[BLOCKED] Device '{ticket.device}' is not in approved scope.")
        print(f"          Reason: {scope_result.reason}")
        print("          Generating a limited triage note with no health checks.\n")
        # Continue with no health checks — still generate a note
        health_check_results_str = f"[Device '{ticket.device}' is not in approved triage scope — no health checks were performed.]\n"
        health_check_results_str += f"Reason: {scope_result.reason}"
    else:
        print(f"       {scope_result.reason}")
        health_check_results_str = None  # Will be populated below

    # ── Initialize command broker ─────────────────────────────────────────────
    from tools.command_broker import CommandBroker
    broker = CommandBroker(
        mock=args.mock,
        audit_logger=audit,
        safety_validator=safety,
        max_commands_per_ticket=max_commands,
        rate_limit_per_device_per_minute=rate_limit,
    )

    # ── Run health checks ─────────────────────────────────────────────────────
    if health_check_results_str is None:
        mode_label = "MOCK" if args.mock else "LIVE"
        print(f"[5/9] Running health checks [{mode_label} mode]...")
        health_check_names = type_config.get("health_checks", ["show_version", "show_clock", "show_logging"])

        _, health_check_results_str = run_health_checks(
            broker=broker,
            health_check_names=health_check_names,
            device=ticket.device,
            interface=ticket.interface,
            ip=ticket.ip,
            vlan=ticket.vlan,
        )
        print(f"       Commands executed: {broker.commands_run}")
    else:
        print("[5/9] Skipping health checks (device not in scope).")

    # ── RAG retrieval ─────────────────────────────────────────────────────────
    print("[6/9] Retrieving runbook from local RAG...")
    from tools.rag_search import RAGSearch
    rag = RAGSearch(audit_logger=audit)

    runbook_name = type_config.get("runbook")
    runbook_context = ""

    try:
        rag.initialize()
        if args.rebuild_index:
            print("       Rebuilding RAG index...")
            rag.rebuild_index()

        # First try direct lookup by runbook name
        if runbook_name:
            full_runbook = rag.get_runbook_by_name(runbook_name)
            if full_runbook:
                # Truncate for prompt
                runbook_context = full_runbook[:3000]
                print(f"       Retrieved: {runbook_name}")
            else:
                print(f"       Runbook '{runbook_name}' not found — falling back to semantic search.")

        # Semantic search fallback
        if not runbook_context:
            query = f"{ticket.alert} {ticket.description} {ticket.device}"
            results = rag.search(query, n_results=3)
            runbook_context = rag.format_context(results, max_chars=2000)
            if results:
                print(f"       Semantic match: {results[0]['runbook']} (score={results[0]['score']})")
            else:
                print("       No runbook matches found.")

    except ImportError as e:
        print(f"       [WARNING] RAG dependencies not available: {e}")
        print("       Continuing without runbook context.")
        runbook_context = "RAG dependencies not installed. No runbook context available."
        audit.error("rag_search", f"RAG unavailable: {e}")

    # ── Generate triage note ──────────────────────────────────────────────────
    print("[7/9] Generating triage note...")

    ticket_summary = ticket_client.format_ticket_summary(ticket)

    if args.no_llm:
        print("       [--no-llm] Using template fallback.")
        from tools.llm_client import LLMClient
        llm = LLMClient(audit_logger=audit)
        note, used_fallback = llm._template_fallback(
            ticket_summary=ticket_summary,
            health_check_results=health_check_results_str,
            ticket_type=ticket_type,
            device=ticket.device,
            interface=ticket.interface,
            severity=ticket.severity,
        ), True
    else:
        from tools.llm_client import LLMClient
        llm = LLMClient(audit_logger=audit)
        note, used_fallback = llm.generate_triage_note(
            ticket_summary=ticket_summary,
            runbook_context=runbook_context,
            health_check_results=health_check_results_str,
            ticket_type=ticket_type,
            device=ticket.device,
            interface=ticket.interface,
            severity=ticket.severity,
        )

    if used_fallback:
        print("       [LLM unavailable — template fallback used]")
    else:
        print(f"       [LLM: {llm.model}]")

    # ── Save output ───────────────────────────────────────────────────────────
    print("[8/9] Saving triage note...")
    output_path = ticket_client.save_triage_note(ticket.ticket_id, note)
    print(f"       Saved: {output_path}")

    # ── Print to terminal ─────────────────────────────────────────────────────
    print("[9/9] Complete.\n")
    print("=" * 60)
    print("TRIAGE NOTE")
    print("=" * 60)
    print(note)
    print("=" * 60)
    print(f"\nFull note saved to: {output_path}")
    print(f"Audit log saved to: {log_path}")
    if args.mock:
        print("\n[MOCK MODE] No real device connections were made.")
    print()


if __name__ == "__main__":
    main()
