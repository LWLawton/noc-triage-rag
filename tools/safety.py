"""
safety.py
All validation logic for the NOC Pre-Triage Agent.
The command broker calls this module before executing any command.

Responsibilities:
  - Allow-list enforcement
  - Deny-list / forbidden pattern enforcement
  - Interface name validation
  - IP address validation
  - VLAN ID validation
  - Device scope validation
  - Output sanitization (remove credentials from command output)

This module has NO network access and NO side effects.
It only validates and returns results.
"""

import ipaddress
import re
from pathlib import Path
from typing import Optional

import yaml
from pydantic import BaseModel


# ── Models ──────────────────────────────────────────────────────────────────

class ValidationResult(BaseModel):
    passed: bool
    reason: str


# ── SafetyValidator ──────────────────────────────────────────────────────────

class SafetyValidator:
    """
    Loads allow-list, deny-list, and device scope from config files.
    Provides validation methods used by the command broker.
    """

    def __init__(
        self,
        allowed_commands_path: str = "config/allowed_commands.yaml",
        device_scope_path: str = "config/device_scope.yaml",
        safety_policy_path: str = "config/safety_policy.yaml",
    ):
        self.allowed_commands = self._load_yaml(allowed_commands_path)
        self.device_scope = self._load_yaml(device_scope_path)
        self.safety_policy = self._load_yaml(safety_policy_path)

        self._allowed_templates: list[str] = self.allowed_commands.get("commands", [])
        self._forbidden_patterns: list[str] = (
            self.safety_policy.get("command_validation", {}).get("forbidden_patterns", [])
        )
        self._interface_patterns: list[str] = (
            self.safety_policy.get("interface_validation", {}).get("allowed_patterns", [])
        )
        self._redact_patterns: list[dict] = (
            self.safety_policy.get("credential_safety", {}).get("redact_patterns", [])
        )
        self._forbidden_strings: list[str] = (
            self.safety_policy.get("credential_safety", {}).get("forbidden_strings", [])
        )

        # Build a flat set of all allowed device hostnames
        self._allowed_devices: dict[str, dict] = self._build_device_map()

    # ── Loaders ──────────────────────────────────────────────────────────────

    @staticmethod
    def _load_yaml(path: str) -> dict:
        p = Path(path)
        if not p.exists():
            raise FileNotFoundError(f"Config file not found: {path}")
        with open(p, encoding="utf-8") as f:
            return yaml.safe_load(f) or {}

    def _build_device_map(self) -> dict[str, dict]:
        """Flatten device_scope.yaml into {hostname: {tier, allowed_in_triage, ...}}"""
        device_map: dict[str, dict] = {}
        groups = self.device_scope.get("device_groups", {})
        for group_name, group in groups.items():
            group_allowed = group.get("allowed_in_triage", False)
            tier = group.get("tier", "unknown")
            for device in group.get("devices", []):
                # Per-device override takes precedence over group setting
                allowed = device.get("allowed_in_triage", group_allowed)
                device_map[device["hostname"]] = {
                    "tier": tier,
                    "allowed_in_triage": allowed,
                    "platform": device.get("platform", "ios"),
                    "site": device.get("site", "unknown"),
                    "group": group_name,
                }
        # Also add mock devices
        for device in self.device_scope.get("mock_devices", []):
            hn = device["hostname"]
            if hn not in device_map:
                device_map[hn] = {
                    "tier": "access",
                    "allowed_in_triage": True,
                    "platform": device.get("platform", "ios"),
                    "site": device.get("site", "mock"),
                    "group": "mock",
                }
        return device_map

    # ── Device Scope ─────────────────────────────────────────────────────────

    def validate_device(self, hostname: str) -> ValidationResult:
        """Check if a device is in scope and allowed for triage."""
        block_unknown = self.safety_policy.get("general", {}).get("block_unknown_devices", True)

        if hostname not in self._allowed_devices:
            if block_unknown:
                return ValidationResult(
                    passed=False,
                    reason=f"Device '{hostname}' not found in device_scope.yaml — blocked by policy."
                )
            return ValidationResult(passed=True, reason="Device not in scope but block_unknown_devices=false")

        info = self._allowed_devices[hostname]
        if not info["allowed_in_triage"]:
            return ValidationResult(
                passed=False,
                reason=(
                    f"Device '{hostname}' is tier={info['tier']} and "
                    f"allowed_in_triage=false in device_scope.yaml."
                )
            )
        return ValidationResult(passed=True, reason=f"Device '{hostname}' is approved (tier={info['tier']})")

    def get_device_info(self, hostname: str) -> Optional[dict]:
        return self._allowed_devices.get(hostname)

    # ── Command Validation ────────────────────────────────────────────────────

    def validate_command(self, command: str) -> ValidationResult:
        """
        Full command validation pipeline:
        1. Strip and normalize
        2. Check for forbidden patterns (deny-list)
        3. Check against allow-list templates
        """
        if not command or not command.strip():
            return ValidationResult(passed=False, reason="Empty command rejected.")

        cmd = command.strip()

        # Step 1: Deny-list check — fastest rejection
        deny_result = self._check_forbidden_patterns(cmd)
        if not deny_result.passed:
            return deny_result

        # Step 2: Allow-list check
        return self._check_allow_list(cmd)

    def _check_forbidden_patterns(self, command: str) -> ValidationResult:
        """Reject immediately if any forbidden pattern is found."""
        cmd_lower = command.lower()
        for pattern in self._forbidden_patterns:
            if pattern.lower() in cmd_lower:
                return ValidationResult(
                    passed=False,
                    reason=f"Command contains forbidden pattern: '{pattern}'"
                )
        return ValidationResult(passed=True, reason="No forbidden patterns found.")

    def _check_allow_list(self, command: str) -> ValidationResult:
        """
        Check command against allow-list templates.
        Templates use {interface}, {ip}, {vlan} as placeholders.
        """
        cmd_lower = command.lower().strip()

        for template in self._allowed_templates:
            t_lower = template.lower().strip()

            # Exact match
            if cmd_lower == t_lower:
                return ValidationResult(passed=True, reason=f"Exact match: '{template}'")

            # Parameterized match
            if "{" in t_lower:
                regex = self._template_to_regex(t_lower)
                if re.match(regex, cmd_lower):
                    # Validate the extracted parameter
                    param_result = self._validate_template_params(command, template)
                    if param_result.passed:
                        return ValidationResult(passed=True, reason=f"Template match: '{template}'")
                    else:
                        return param_result

        return ValidationResult(
            passed=False,
            reason=f"Command '{command}' does not match any allowed command template."
        )

    def _template_to_regex(self, template: str) -> str:
        """
        Convert a template like 'show interface {interface}' to a regex.
        Uses non-greedy capture so trailing keywords (status, counters, etc.)
        are NOT swallowed into the parameter match.
        """
        parts = re.split(r"(\{[^}]+\})", template)
        regex_parts = []
        for i, part in enumerate(parts):
            if part.startswith("{") and part.endswith("}"):
                # Non-greedy: capture up to the next space/end-of-string
                # This prevents "Gi1/0/14 status" being captured as the interface name
                regex_parts.append(r"(\S+)")
            else:
                regex_parts.append(re.escape(part))
        return "^" + "".join(regex_parts) + "$"

    def _validate_template_params(self, command: str, template: str) -> ValidationResult:
        """Extract and validate parameters from a matched command template."""
        # Find parameter names
        param_names = re.findall(r"\{(\w+)\}", template)

        # Extract parameter values via regex
        regex = self._template_to_regex(template.lower())
        match = re.match(regex, command.lower())
        if not match:
            return ValidationResult(passed=False, reason="Parameter extraction failed.")

        values = match.groups()
        for name, value in zip(param_names, values):
            if name == "interface":
                result = self.validate_interface(value)
            elif name == "ip":
                result = self.validate_ip(value)
            elif name == "vlan":
                result = self.validate_vlan(value)
            else:
                # Unknown param — allow but note
                result = ValidationResult(passed=True, reason=f"Unknown param '{name}' — allowed by default")
            if not result.passed:
                return result

        return ValidationResult(passed=True, reason="All parameters valid.")

    # ── Parameter Validators ──────────────────────────────────────────────────

    def validate_interface(self, interface: str) -> ValidationResult:
        """Validate a Cisco interface name against allowed patterns."""
        for pattern in self._interface_patterns:
            if re.match(pattern, interface, re.IGNORECASE):
                return ValidationResult(passed=True, reason=f"Interface '{interface}' matches pattern.")
        return ValidationResult(
            passed=False,
            reason=f"Interface name '{interface}' does not match any allowed interface pattern."
        )

    def validate_ip(self, ip_str: str) -> ValidationResult:
        """Validate an IPv4 address."""
        try:
            ip = ipaddress.IPv4Address(ip_str)
        except ValueError:
            return ValidationResult(passed=False, reason=f"'{ip_str}' is not a valid IPv4 address.")

        policy = self.safety_policy.get("ip_validation", {})

        if not policy.get("allow_multicast", False) and ip.is_multicast:
            return ValidationResult(passed=False, reason=f"Multicast IP '{ip_str}' not allowed.")
        if not policy.get("allow_loopback", False) and ip.is_loopback:
            return ValidationResult(passed=False, reason=f"Loopback IP '{ip_str}' not allowed.")
        if ip == ipaddress.IPv4Address("255.255.255.255"):
            return ValidationResult(passed=False, reason="Broadcast IP not allowed.")

        return ValidationResult(passed=True, reason=f"IP '{ip_str}' is valid.")

    def validate_vlan(self, vlan_str: str) -> ValidationResult:
        """Validate a VLAN ID."""
        try:
            vlan = int(vlan_str)
        except ValueError:
            return ValidationResult(passed=False, reason=f"'{vlan_str}' is not a valid VLAN ID (not an integer).")

        policy = self.safety_policy.get("vlan_validation", {})
        min_vlan = policy.get("min_vlan", 1)
        max_vlan = policy.get("max_vlan", 4094)

        if not (min_vlan <= vlan <= max_vlan):
            return ValidationResult(
                passed=False,
                reason=f"VLAN {vlan} is out of valid range ({min_vlan}–{max_vlan})."
            )
        return ValidationResult(passed=True, reason=f"VLAN {vlan} is valid.")

    # ── Output Sanitization ───────────────────────────────────────────────────

    def sanitize_output(self, output: str) -> str:
        """
        Apply redaction patterns to command output before passing to LLM.
        Removes or masks credential-like strings.
        """
        if not output:
            return output

        sanitized = output

        # Apply configured redact patterns
        for rule in self._redact_patterns:
            pattern = rule.get("pattern", "")
            replacement = rule.get("replacement", "[REDACTED]")
            if pattern:
                try:
                    sanitized = re.sub(pattern, replacement, sanitized, flags=re.IGNORECASE)
                except re.error:
                    pass  # Bad pattern in config — skip silently

        # Additional hard check: block if forbidden strings still present
        lower = sanitized.lower()
        for fs in self._forbidden_strings:
            if fs.lower() in lower:
                sanitized = sanitized.replace(fs, "[REDACTED]")

        return sanitized
