"""
tests/test_ticket_schema.py
Unit tests for Ticket Pydantic schema validation and TicketClient.
"""

import sys
import json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from pydantic import ValidationError
from tools.ticket_client import Ticket, TicketClient
from tools.audit_logger import AuditLogger


# ── Fixtures ──────────────────────────────────────────────────────────────────

VALID_TICKET = {
    "ticket_id": "INC12345",
    "source": "SolarWinds",
    "severity": "Medium",
    "alert": "Interface Down",
    "device": "access-sw-22",
    "interface": "Gi1/0/14",
    "description": "Interface Gi1/0/14 is down on access-sw-22",
    "created_at": "2026-04-24T10:15:00",
}


@pytest.fixture
def ticket_client(tmp_path):
    audit = AuditLogger(log_path=str(tmp_path / "audit.jsonl"), ticket_id="SCHEMATEST")
    return TicketClient(outputs_dir=str(tmp_path / "outputs"), audit_logger=audit)


# ── Valid Ticket Tests ─────────────────────────────────────────────────────────

class TestValidTicket:
    def test_valid_ticket_loads(self):
        t = Ticket(**VALID_TICKET)
        assert t.ticket_id == "INC12345"
        assert t.device == "access-sw-22"
        assert t.interface == "Gi1/0/14"

    def test_device_name_lowercased(self):
        data = {**VALID_TICKET, "device": "ACCESS-SW-22"}
        t = Ticket(**data)
        assert t.device == "access-sw-22"

    def test_optional_fields_default_to_none(self):
        minimal = {
            "ticket_id": "INC00001",
            "alert": "High CPU",
            "device": "access-sw-01",
        }
        t = Ticket(**minimal)
        assert t.interface is None
        assert t.ip is None
        assert t.vlan is None

    def test_severity_defaults_to_medium_if_invalid(self):
        data = {**VALID_TICKET, "severity": "UltraCritical"}
        t = Ticket(**data)
        assert t.severity == "Medium"

    @pytest.mark.parametrize("severity", ["Critical", "High", "Medium", "Low", "Informational"])
    def test_all_valid_severities(self, severity):
        data = {**VALID_TICKET, "severity": severity}
        t = Ticket(**data)
        assert t.severity == severity

    def test_load_from_real_sample_file(self, ticket_client):
        t = ticket_client.load_ticket("tickets/sample_ticket_interface_down.json")
        assert t.ticket_id == "INC12345"
        assert t.device == "access-sw-22"
        assert t.alert == "Interface Down"


# ── Invalid Ticket Tests ───────────────────────────────────────────────────────

class TestInvalidTickets:
    def test_missing_alert_raises(self):
        data = {k: v for k, v in VALID_TICKET.items() if k != "alert"}
        with pytest.raises(ValidationError):
            Ticket(**data)

    def test_missing_device_raises(self):
        data = {k: v for k, v in VALID_TICKET.items() if k != "device"}
        with pytest.raises(ValidationError):
            Ticket(**data)

    def test_missing_ticket_id_raises(self):
        data = {k: v for k, v in VALID_TICKET.items() if k != "ticket_id"}
        with pytest.raises(ValidationError):
            Ticket(**data)

    def test_ticket_id_with_path_traversal_raises(self):
        data = {**VALID_TICKET, "ticket_id": "../../etc/passwd"}
        with pytest.raises(ValidationError):
            Ticket(**data)

    def test_ticket_id_with_spaces_raises(self):
        data = {**VALID_TICKET, "ticket_id": "INC 12345"}
        with pytest.raises(ValidationError):
            Ticket(**data)

    def test_device_with_special_chars_raises(self):
        data = {**VALID_TICKET, "device": "switch$(reboot)"}
        with pytest.raises(ValidationError):
            Ticket(**data)

    def test_empty_ticket_id_raises(self):
        data = {**VALID_TICKET, "ticket_id": ""}
        with pytest.raises(ValidationError):
            Ticket(**data)


# ── TicketClient Tests ────────────────────────────────────────────────────────

class TestTicketClient:
    def test_load_ticket_file_not_found(self, ticket_client):
        with pytest.raises(FileNotFoundError):
            ticket_client.load_ticket("tickets/does_not_exist.json")

    def test_save_triage_note_creates_file(self, ticket_client, tmp_path):
        path = ticket_client.save_triage_note("INC12345", "Test triage note content.")
        assert Path(path).exists()
        content = Path(path).read_text()
        assert "INC12345" in content
        assert "Test triage note content." in content

    def test_save_triage_note_has_header_and_footer(self, ticket_client):
        path = ticket_client.save_triage_note("INC99999", "Sample note.")
        content = Path(path).read_text()
        assert "NOC AI PRE-TRIAGE NOTE" in content
        assert "No changes were made to any device" in content

    def test_format_ticket_summary_includes_all_fields(self):
        t = Ticket(**VALID_TICKET)
        client = TicketClient()
        summary = client.format_ticket_summary(t)
        assert "INC12345" in summary
        assert "access-sw-22" in summary
        assert "Gi1/0/14" in summary
        assert "Interface Down" in summary
        assert "Medium" in summary

    def test_format_ticket_summary_omits_none_fields(self):
        minimal = Ticket(ticket_id="INC00001", alert="High CPU", device="access-sw-01")
        client = TicketClient()
        summary = client.format_ticket_summary(minimal)
        assert "Interface:" not in summary
        assert "IP:" not in summary

    def test_load_invalid_json_raises(self, ticket_client, tmp_path):
        bad_json = tmp_path / "bad_ticket.json"
        bad_json.write_text("{ this is not valid json }")
        with pytest.raises(Exception):
            ticket_client.load_ticket(str(bad_json))

    def test_load_ticket_missing_required_field_raises(self, ticket_client, tmp_path):
        bad_ticket = tmp_path / "missing_field.json"
        # Missing 'alert' field
        bad_ticket.write_text(json.dumps({
            "ticket_id": "INC99999",
            "device": "access-sw-01",
        }))
        with pytest.raises(ValidationError):
            ticket_client.load_ticket(str(bad_ticket))
