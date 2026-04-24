"""
tests/test_safety.py
Unit tests for SafetyValidator.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from tools.safety import SafetyValidator


@pytest.fixture
def safety():
    return SafetyValidator(
        allowed_commands_path="config/allowed_commands.yaml",
        device_scope_path="config/device_scope.yaml",
        safety_policy_path="config/safety_policy.yaml",
    )


class TestCommandValidation:
    def test_exact_allowed_command(self, safety):
        result = safety.validate_command("show version")
        assert result.passed

    def test_case_insensitive_match(self, safety):
        result = safety.validate_command("Show Version")
        assert result.passed

    def test_forbidden_configure(self, safety):
        result = safety.validate_command("configure terminal")
        assert not result.passed

    def test_forbidden_reload(self, safety):
        result = safety.validate_command("reload")
        assert not result.passed

    def test_forbidden_write(self, safety):
        result = safety.validate_command("write memory")
        assert not result.passed

    def test_forbidden_debug(self, safety):
        result = safety.validate_command("debug ip ospf")
        assert not result.passed

    def test_parameterized_interface_valid(self, safety):
        result = safety.validate_command("show interface Gi1/0/14")
        assert result.passed

    def test_parameterized_interface_invalid_name(self, safety):
        result = safety.validate_command("show interface ../../etc/passwd")
        assert not result.passed

    def test_parameterized_interface_nx_os(self, safety):
        result = safety.validate_command("show interface Ethernet1/0/1")
        assert result.passed

    def test_parameterized_ip_valid(self, safety):
        result = safety.validate_command("show ip route 10.0.0.1")
        assert result.passed

    def test_parameterized_ip_invalid(self, safety):
        result = safety.validate_command("show ip route not-an-ip")
        assert not result.passed

    def test_parameterized_ip_multicast_blocked(self, safety):
        result = safety.validate_command("ping 224.0.0.1")
        assert not result.passed

    def test_show_spanning_tree_with_vlan(self, safety):
        result = safety.validate_command("show spanning-tree vlan 10")
        assert result.passed

    def test_show_spanning_tree_invalid_vlan(self, safety):
        result = safety.validate_command("show spanning-tree vlan 9999")
        assert not result.passed

    def test_command_not_in_allowlist(self, safety):
        result = safety.validate_command("show something-not-allowed")
        assert not result.passed

    def test_empty_command_rejected(self, safety):
        result = safety.validate_command("")
        assert not result.passed

    def test_semicolon_injection_blocked(self, safety):
        result = safety.validate_command("show version; reload")
        assert not result.passed


class TestInterfaceValidation:
    @pytest.mark.parametrize("interface", [
        "Gi1/0/1", "GigabitEthernet1/0/48", "Te1/0/1", "TenGigabitEthernet1/1/1",
        "Fa0/1", "FastEthernet0/24", "Lo0", "Loopback0", "Vlan10", "Vl100",
        "Po1", "Port-channel1", "Ethernet1/1/1",
    ])
    def test_valid_interfaces(self, safety, interface):
        result = safety.validate_interface(interface)
        assert result.passed, f"Expected {interface} to be valid but got: {result.reason}"

    @pytest.mark.parametrize("interface", [
        "../../etc", "Gi1/0/$(id)", "GigabitEthernet ; reload", "eth0", "Gi1", "",
    ])
    def test_invalid_interfaces(self, safety, interface):
        result = safety.validate_interface(interface)
        assert not result.passed, f"Expected {interface} to be invalid"


class TestIPValidation:
    @pytest.mark.parametrize("ip", ["10.0.0.1", "192.168.1.100", "172.16.0.1"])
    def test_valid_ips(self, safety, ip):
        result = safety.validate_ip(ip)
        assert result.passed

    @pytest.mark.parametrize("ip", [
        "224.0.0.1",   # multicast
        "127.0.0.1",   # loopback
        "255.255.255.255",  # broadcast
        "not-an-ip",
        "999.999.999.999",
        "",
    ])
    def test_invalid_ips(self, safety, ip):
        result = safety.validate_ip(ip)
        assert not result.passed


class TestVLANValidation:
    @pytest.mark.parametrize("vlan", ["1", "10", "100", "4094"])
    def test_valid_vlans(self, safety, vlan):
        result = safety.validate_vlan(vlan)
        assert result.passed

    @pytest.mark.parametrize("vlan", ["0", "4095", "9999", "abc", ""])
    def test_invalid_vlans(self, safety, vlan):
        result = safety.validate_vlan(vlan)
        assert not result.passed


class TestDeviceScope:
    def test_approved_access_switch(self, safety):
        result = safety.validate_device("access-sw-22")
        assert result.passed

    def test_unknown_device_blocked(self, safety):
        result = safety.validate_device("rogue-device-99")
        assert not result.passed

    def test_core_router_blocked(self, safety):
        result = safety.validate_device("core-rtr-01")
        assert not result.passed

    def test_firewall_blocked(self, safety):
        result = safety.validate_device("fw-01")
        assert not result.passed


class TestOutputSanitization:
    def test_password_redacted(self, safety):
        output = "username admin password ClearTextPass123"
        sanitized = safety.sanitize_output(output)
        assert "ClearTextPass123" not in sanitized

    def test_clean_output_unchanged(self, safety):
        output = "GigabitEthernet1/0/14 is down, line protocol is down (notconnect)"
        sanitized = safety.sanitize_output(output)
        assert "notconnect" in sanitized
        assert "GigabitEthernet1/0/14" in sanitized
