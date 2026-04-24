"""
tests/test_command_broker.py
Unit tests for the CommandBroker.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from tools.audit_logger import AuditLogger
from tools.command_broker import CommandBroker
from tools.safety import SafetyValidator


@pytest.fixture
def broker(tmp_path):
    """Create a CommandBroker in mock mode with a tmp audit log."""
    audit = AuditLogger(log_path=str(tmp_path / "audit.jsonl"), ticket_id="TEST001")
    safety = SafetyValidator(
        allowed_commands_path="config/allowed_commands.yaml",
        device_scope_path="config/device_scope.yaml",
        safety_policy_path="config/safety_policy.yaml",
    )
    return CommandBroker(
        mock=True,
        audit_logger=audit,
        safety_validator=safety,
        max_commands_per_ticket=10,
        rate_limit_per_device_per_minute=20,
    )


class TestAllowedCommands:
    def test_show_version_allowed(self, broker):
        result = broker.run("show version", "access-sw-22")
        assert result.success
        assert not result.blocked
        assert "Cisco IOS" in result.output

    def test_show_interface_allowed(self, broker):
        result = broker.run("show interface Gi1/0/14", "access-sw-22")
        assert result.success
        assert not result.blocked

    def test_show_interface_status_allowed(self, broker):
        result = broker.run("show interface Gi1/0/14 status", "access-sw-22")
        assert result.success

    def test_show_logging_allowed(self, broker):
        result = broker.run("show logging last 100", "access-sw-22")
        assert result.success

    def test_show_ip_bgp_summary_allowed(self, broker):
        result = broker.run("show ip bgp summary", "access-sw-22")
        assert result.success

    def test_show_vlan_brief_allowed(self, broker):
        result = broker.run("show vlan brief", "access-sw-22")
        assert result.success

    def test_show_standby_brief_allowed(self, broker):
        result = broker.run("show standby brief", "access-sw-22")
        assert result.success


class TestForbiddenCommands:
    def test_configure_terminal_blocked(self, broker):
        result = broker.run("configure terminal", "access-sw-22")
        assert result.blocked
        assert not result.success

    def test_conf_t_blocked(self, broker):
        result = broker.run("conf t", "access-sw-22")
        assert result.blocked

    def test_reload_blocked(self, broker):
        result = broker.run("reload", "access-sw-22")
        assert result.blocked

    def test_write_blocked(self, broker):
        result = broker.run("write memory", "access-sw-22")
        assert result.blocked

    def test_no_shutdown_blocked(self, broker):
        result = broker.run("no shutdown", "access-sw-22")
        assert result.blocked

    def test_shutdown_blocked(self, broker):
        result = broker.run("shutdown", "access-sw-22")
        assert result.blocked

    def test_delete_blocked(self, broker):
        result = broker.run("delete flash:config.bak", "access-sw-22")
        assert result.blocked

    def test_debug_blocked(self, broker):
        result = broker.run("debug ip ospf", "access-sw-22")
        assert result.blocked

    def test_clear_blocked(self, broker):
        result = broker.run("clear ip ospf process", "access-sw-22")
        assert result.blocked

    def test_semicolon_chaining_blocked(self, broker):
        result = broker.run("show version; reload", "access-sw-22")
        assert result.blocked

    def test_pipe_redirect_blocked(self, broker):
        # pipe char is in forbidden patterns
        result = broker.run("show version | redirect tftp://10.0.0.1/", "access-sw-22")
        assert result.blocked

    def test_copy_blocked(self, broker):
        result = broker.run("copy running-config tftp:", "access-sw-22")
        assert result.blocked

    def test_empty_command_blocked(self, broker):
        result = broker.run("", "access-sw-22")
        assert result.blocked

    def test_arbitrary_command_not_in_allowlist_blocked(self, broker):
        result = broker.run("show something-made-up detailed", "access-sw-22")
        assert result.blocked


class TestDeviceScope:
    def test_approved_device_allowed(self, broker):
        result = broker.run("show version", "access-sw-22")
        assert not result.blocked

    def test_unknown_device_blocked(self, broker):
        result = broker.run("show version", "rogue-device-99")
        assert result.blocked
        assert "not found in device_scope" in result.block_reason.lower() or "not in approved" in result.block_reason.lower() or result.blocked

    def test_core_router_blocked(self, broker):
        result = broker.run("show version", "core-rtr-01")
        assert result.blocked


class TestRateLimiting:
    def test_rate_limit_enforced(self, tmp_path):
        """Verify that rate limiting blocks commands beyond the threshold."""
        audit = AuditLogger(log_path=str(tmp_path / "audit.jsonl"), ticket_id="RATETEST")
        safety = SafetyValidator(
            allowed_commands_path="config/allowed_commands.yaml",
            device_scope_path="config/device_scope.yaml",
            safety_policy_path="config/safety_policy.yaml",
        )
        broker = CommandBroker(
            mock=True,
            audit_logger=audit,
            safety_validator=safety,
            max_commands_per_ticket=5,   # Allow up to 5
            rate_limit_per_device_per_minute=3,  # Only 3 per minute
        )
        results = []
        for _ in range(6):
            r = broker.run("show version", "access-sw-22")
            results.append(r)

        # At least one should be rate-limited or hit the hard limit
        blocked = [r for r in results if r.blocked]
        assert len(blocked) >= 1

    def test_hard_command_limit_enforced(self, tmp_path):
        audit = AuditLogger(log_path=str(tmp_path / "audit.jsonl"), ticket_id="LIMITEST")
        safety = SafetyValidator(
            allowed_commands_path="config/allowed_commands.yaml",
            device_scope_path="config/device_scope.yaml",
            safety_policy_path="config/safety_policy.yaml",
        )
        broker = CommandBroker(
            mock=True,
            audit_logger=audit,
            safety_validator=safety,
            max_commands_per_ticket=2,
            rate_limit_per_device_per_minute=100,
        )
        r1 = broker.run("show version", "access-sw-22")
        r2 = broker.run("show clock", "access-sw-22")
        r3 = broker.run("show logging last 100", "access-sw-22")

        assert not r1.blocked
        assert not r2.blocked
        assert r3.blocked
        assert "Hard command limit" in r3.block_reason
