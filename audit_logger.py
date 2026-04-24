"""
audit_logger.py
Structured JSON-lines audit logger for the NOC Pre-Triage Agent.
Every significant action is written to logs/audit.jsonl.
"""

import json
import logging
import os
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

# Console logger (for developer visibility only, not for sensitive data)
_console = logging.getLogger("noc_triage.audit")


class AuditLogger:
    """
    Writes structured JSON-line audit events to a file.
    Each line is a self-contained JSON object with timestamp, event type,
    ticket ID, and arbitrary metadata.

    Credentials, device passwords, and raw model prompts are NEVER logged.
    """

    def __init__(self, log_path: str = "logs/audit.jsonl", ticket_id: str = "UNKNOWN"):
        self.log_path = Path(log_path)
        self.ticket_id = ticket_id
        self._ensure_log_dir()

    def _ensure_log_dir(self) -> None:
        self.log_path.parent.mkdir(parents=True, exist_ok=True)

    def _write(self, event_type: str, data: dict[str, Any]) -> None:
        """Write a single audit event as a JSON line."""
        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "ticket_id": self.ticket_id,
            "event_type": event_type,
            **data,
        }
        try:
            with open(self.log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(record) + "\n")
        except OSError as e:
            _console.error(f"[AUDIT] Failed to write audit log: {e}")

    # ── Public event methods ────────────────────────────────────────────────

    def ticket_loaded(self, ticket_id: str, source: str, alert: str, device: str) -> None:
        self._write("ticket_loaded", {
            "ticket_id_value": ticket_id,
            "source": source,
            "alert": alert,
            "device": device,
        })

    def ticket_classified(self, ticket_type: str, confidence: str) -> None:
        self._write("ticket_classified", {
            "ticket_type": ticket_type,
            "confidence": confidence,
        })

    def device_scope_check(self, device: str, allowed: bool, reason: str) -> None:
        self._write("device_scope_check", {
            "device": device,
            "allowed": allowed,
            "reason": reason,
        })

    def command_validated(self, command: str, result: bool, reason: str = "") -> None:
        # Never log the full command if it contains sensitive strings
        safe_command = _mask_sensitive(command)
        self._write("command_validated", {
            "command": safe_command,
            "passed": result,
            "reason": reason,
        })

    def command_blocked(self, command: str, reason: str) -> None:
        safe_command = _mask_sensitive(command)
        self._write("command_blocked", {
            "command": safe_command,
            "reason": reason,
        })

    def command_executed(
        self,
        command: str,
        device: str,
        mock: bool,
        success: bool,
        output_length: int,
    ) -> None:
        safe_command = _mask_sensitive(command)
        self._write("command_executed", {
            "command": safe_command,
            "device": device,
            "mock_mode": mock,
            "success": success,
            "output_length_chars": output_length,
            # NOTE: raw output is never logged — only its length
        })

    def rag_query(self, query: str, results_count: int, runbook: Optional[str]) -> None:
        self._write("rag_query", {
            "query": query,
            "results_count": results_count,
            "runbook_retrieved": runbook,
        })

    def llm_query(self, model: str, prompt_length: int, success: bool, fallback_used: bool) -> None:
        # Prompt content is NEVER logged — only metadata
        self._write("llm_query", {
            "model": model,
            "prompt_length_chars": prompt_length,
            "success": success,
            "fallback_template_used": fallback_used,
        })

    def triage_note_generated(self, output_path: str, note_length: int) -> None:
        self._write("triage_note_generated", {
            "output_path": output_path,
            "note_length_chars": note_length,
        })

    def rate_limit_hit(self, device: str, commands_attempted: int, limit: int) -> None:
        self._write("rate_limit_hit", {
            "device": device,
            "commands_attempted": commands_attempted,
            "limit": limit,
        })

    def error(self, context: str, message: str, exception: Optional[Exception] = None) -> None:
        data: dict[str, Any] = {
            "context": context,
            "message": message,
        }
        if exception:
            data["exception_type"] = type(exception).__name__
            data["exception_message"] = str(exception)
            # Include limited traceback for debugging — no credential data should appear here
            data["traceback_snippet"] = traceback.format_exc()[-500:]
        self._write("error", data)

    def info(self, context: str, message: str, **kwargs: Any) -> None:
        self._write("info", {"context": context, "message": message, **kwargs})


def _mask_sensitive(text: str) -> str:
    """Redact any command that looks like it might contain credentials."""
    sensitive_keywords = ["password", "secret", "key", "token", "enable", "username"]
    lower = text.lower()
    if any(kw in lower for kw in sensitive_keywords):
        return "[COMMAND REDACTED — SENSITIVE KEYWORD DETECTED]"
    return text
