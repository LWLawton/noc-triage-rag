"""
llm_client.py
Local LLM client for the NOC Pre-Triage Agent.

Connects to a locally running Ollama instance.
Falls back to a structured template summary if Ollama is unavailable.

Security rules enforced here:
  - Credentials are NEVER passed in prompts
  - Device hostnames are passed only as context labels
  - Raw command output is sanitized BEFORE reaching this module
  - Prompt content is never logged (only prompt length is audit-logged)
"""

import os
from typing import Optional

import requests

from tools.audit_logger import AuditLogger


# ── LLMClient ─────────────────────────────────────────────────────────────────

class LLMClient:
    """
    Sends structured prompts to a local Ollama instance and returns
    the model's response as a string.

    If Ollama is unreachable, falls back to template-based summary generation.
    """

    DEFAULT_MODEL = "llama3.1"
    DEFAULT_BASE_URL = "http://localhost:11434"
    TIMEOUT_SECONDS = 120

    def __init__(
        self,
        model: Optional[str] = None,
        base_url: Optional[str] = None,
        audit_logger: Optional[AuditLogger] = None,
    ):
        self.model = model or os.getenv("OLLAMA_MODEL", self.DEFAULT_MODEL)
        self.base_url = base_url or os.getenv("OLLAMA_BASE_URL", self.DEFAULT_BASE_URL)
        self.audit = audit_logger or AuditLogger()

    # ── Public API ─────────────────────────────────────────────────────────────

    def generate_triage_note(
        self,
        ticket_summary: str,
        runbook_context: str,
        health_check_results: str,
        ticket_type: str,
        device: str,
        interface: Optional[str] = None,
        severity: str = "Medium",
    ) -> tuple[str, bool]:
        """
        Generate an engineer-facing triage note.

        Returns: (note_text, used_fallback)
          - note_text: the generated triage note
          - used_fallback: True if template fallback was used (Ollama unavailable)
        """
        prompt = self._build_prompt(
            ticket_summary=ticket_summary,
            runbook_context=runbook_context,
            health_check_results=health_check_results,
            ticket_type=ticket_type,
            device=device,
            interface=interface,
            severity=severity,
        )

        # Try Ollama first
        if self._is_ollama_available():
            try:
                note = self._call_ollama(prompt)
                self.audit.llm_query(
                    model=self.model,
                    prompt_length=len(prompt),
                    success=True,
                    fallback_used=False,
                )
                return note, False
            except Exception as e:
                self.audit.error("llm_client", f"Ollama call failed: {e}", e)

        # Fall back to template
        self.audit.llm_query(
            model=self.model,
            prompt_length=len(prompt),
            success=False,
            fallback_used=True,
        )
        note = self._template_fallback(
            ticket_summary=ticket_summary,
            health_check_results=health_check_results,
            ticket_type=ticket_type,
            device=device,
            interface=interface,
            severity=severity,
        )
        return note, True

    # ── Prompt Construction ───────────────────────────────────────────────────

    def _build_prompt(
        self,
        ticket_summary: str,
        runbook_context: str,
        health_check_results: str,
        ticket_type: str,
        device: str,
        interface: Optional[str],
        severity: str,
    ) -> str:
        """
        Build the LLM prompt.
        IMPORTANT: Credentials, passwords, and secrets are NEVER included here.
        """
        interface_line = f"Affected Interface: {interface}" if interface else ""

        return f"""You are a network operations center (NOC) AI assistant performing pre-triage analysis.
Your job is to analyze read-only Cisco health check data and produce a structured triage note for an engineer.

IMPORTANT RULES:
- Base your analysis ONLY on the data provided below.
- Do NOT suggest any configuration changes, reloads, or port bounces.
- Do NOT include any credentials, passwords, or sensitive data.
- Always recommend human verification.
- Be factual and specific. Do not speculate beyond the evidence.

--- TICKET SUMMARY ---
{ticket_summary}

--- RUNBOOK GUIDANCE ---
{runbook_context}

--- HEALTH CHECK RESULTS ---
{health_check_results}

--- INSTRUCTIONS ---
Based on the above, produce a structured triage note in exactly this format:

AI Pre-Triage Findings
======================

Ticket ID: [from ticket summary]
Ticket Type: {ticket_type}
Affected Device: {device}
{interface_line}
Severity: {severity}

Health Checks Performed:
[List the commands that were run]

Key Findings:
[2-5 specific findings from the health check data]

Likely Cause:
[Most likely cause based only on the evidence above]

Recommended Next Step:
[One safe, specific next step for the engineer. No config changes.]

Escalation Recommendation:
[Tier 1 / Tier 2 / Network Engineering / Vendor / Facilities — choose one]

Confidence:
[Low / Medium / High — based on quality and completeness of data]

Action Taken:
Read-only checks only. No configuration changes, reloads, restarts, or port bounces were performed. All findings require human verification before any action is taken.
"""

    # ── Ollama Integration ────────────────────────────────────────────────────

    def _is_ollama_available(self) -> bool:
        """Quick health check against Ollama API."""
        try:
            resp = requests.get(f"{self.base_url}/api/tags", timeout=3)
            return resp.status_code == 200
        except Exception:
            return False

    def _call_ollama(self, prompt: str) -> str:
        """Call the Ollama /api/generate endpoint."""
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": 0.2,    # Low temperature for factual NOC output
                "top_p": 0.9,
                "num_ctx": 8192,
            },
        }
        resp = requests.post(
            f"{self.base_url}/api/generate",
            json=payload,
            timeout=self.TIMEOUT_SECONDS,
        )
        resp.raise_for_status()
        data = resp.json()
        return data.get("response", "").strip()

    # ── Template Fallback ─────────────────────────────────────────────────────

    def _template_fallback(
        self,
        ticket_summary: str,
        health_check_results: str,
        ticket_type: str,
        device: str,
        interface: Optional[str],
        severity: str,
    ) -> str:
        """
        Generate a structured triage note without LLM when Ollama is unavailable.
        Extracts key facts from health check results using simple text analysis.
        """
        interface_line = f"Affected Interface: {interface}" if interface else ""

        # Extract key log lines from health check output
        key_logs = _extract_log_lines(health_check_results)
        interface_status = _extract_interface_status(health_check_results, interface)
        err_disabled = "err-disabled" in health_check_results.lower()
        notconnect = "notconnect" in health_check_results.lower()
        admin_shutdown = "administratively down" in health_check_results.lower()

        # Determine likely cause
        if err_disabled:
            likely_cause = (
                "Interface is in err-disabled state. Review syslog for the err-disable reason "
                "(BPDU Guard, port security, storm-control, etc.)."
            )
            escalation = "Tier 2"
            confidence = "High"
        elif admin_shutdown:
            likely_cause = "Interface is administratively shut down. May be intentional."
            escalation = "Tier 1"
            confidence = "High"
        elif notconnect:
            likely_cause = (
                "Interface shows 'notconnect' — no physical signal detected. "
                "Likely causes: cable unplugged, end device powered off, or SFP failure."
            )
            escalation = "Tier 1"
            confidence = "Medium"
        else:
            likely_cause = (
                "Interface is down. Exact cause unclear from available data. "
                "Physical layer or remote end issue suspected."
            )
            escalation = "Tier 2"
            confidence = "Low"

        # Findings
        findings = []
        if interface_status:
            findings.append(f"Interface status: {interface_status}")
        if key_logs:
            findings.append(f"Recent syslog events: {'; '.join(key_logs[:3])}")
        if err_disabled:
            findings.append("Interface is in err-disabled state — requires manual investigation of root cause before recovery.")
        if not findings:
            findings.append("No specific findings extracted — manual review required.")

        # Extract performed commands
        commands_run = _extract_commands_run(health_check_results)

        return f"""AI Pre-Triage Findings (Template Mode — Ollama Unavailable)
=============================================================

Ticket ID: [See ticket]
Ticket Type: {ticket_type}
Affected Device: {device}
{interface_line}
Severity: {severity}

Health Checks Performed:
{chr(10).join(f'- {c}' for c in commands_run) if commands_run else '- See health check output'}

Key Findings:
{chr(10).join(f'- {f}' for f in findings)}

Likely Cause:
{likely_cause}

Recommended Next Step:
Assign to on-call network engineer for physical layer verification. Check end device power status and cable integrity at patch panel. Do not make configuration changes without change control.

Escalation Recommendation:
{escalation}

Confidence:
{confidence}

Note: This summary was generated using the template fallback (Ollama LLM was not available).
A human engineer should review the full health check output in the attached log.

Action Taken:
Read-only checks only. No configuration changes, reloads, restarts, or port bounces were performed. All findings require human verification before any action is taken.
"""


# ── Helpers ───────────────────────────────────────────────────────────────────

def _extract_log_lines(text: str) -> list[str]:
    """Extract syslog-looking lines from health check output."""
    import re
    lines = text.splitlines()
    log_pattern = re.compile(r"%([\w\-]+)-\d-([\w_]+):")
    return [line.strip() for line in lines if log_pattern.search(line)][:5]


def _extract_interface_status(text: str, interface: Optional[str]) -> str:
    """Try to find the interface status line in output."""
    if not interface:
        return ""
    iface_lower = interface.lower()
    for line in text.splitlines():
        if iface_lower in line.lower() and any(
            s in line.lower() for s in ["connected", "notconnect", "disabled", "err-disabled", "down", "up"]
        ):
            return line.strip()
    return ""


def _extract_commands_run(text: str) -> list[str]:
    """Extract command headers from combined health check output."""
    import re
    lines = text.splitlines()
    commands = []
    cmd_pattern = re.compile(r"^={3,}\s*Command: (.+?)\s*={3,}$")
    for line in lines:
        m = cmd_pattern.match(line.strip())
        if m:
            commands.append(m.group(1))
    return commands
