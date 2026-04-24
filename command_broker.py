"""
command_broker.py
Single execution choke point for all Cisco device commands.

ALL commands pass through this broker. No module may execute device commands
by any other means.

Security guarantees:
  - Every command is validated by safety.py BEFORE execution
  - Device credentials are never passed through this broker
  - Command output is sanitized before being returned
  - Rate limiting is enforced per device
  - Hard command count limit is enforced per ticket run
  - All actions are audit-logged

In mock mode: returns pre-canned responses from cisco_health_checks.py
In live mode: uses Netmiko (future — stubbed out here with a clear interface)
"""

import time
from collections import defaultdict
from datetime import datetime, timezone
from typing import Optional

from tools.audit_logger import AuditLogger
from tools.safety import SafetyValidator, ValidationResult


# ── BrokerResult ──────────────────────────────────────────────────────────────

class BrokerResult:
    def __init__(
        self,
        success: bool,
        output: str,
        command: str,
        device: str,
        blocked: bool = False,
        block_reason: str = "",
        mock: bool = True,
    ):
        self.success = success
        self.output = output
        self.command = command
        self.device = device
        self.blocked = blocked
        self.block_reason = block_reason
        self.mock = mock
        self.timestamp = datetime.now(timezone.utc).isoformat()

    def __repr__(self) -> str:
        status = "BLOCKED" if self.blocked else ("OK" if self.success else "ERROR")
        return f"BrokerResult({status}, device={self.device}, cmd={self.command!r})"


# ── CommandBroker ─────────────────────────────────────────────────────────────

class CommandBroker:
    """
    The single gateway for all Cisco device command execution.

    Usage:
        broker = CommandBroker(mock=True, audit_logger=audit)
        result = broker.run("show interface Gi1/0/14", "access-sw-22")
    """

    def __init__(
        self,
        mock: bool = True,
        audit_logger: Optional[AuditLogger] = None,
        safety_validator: Optional[SafetyValidator] = None,
        max_commands_per_ticket: int = 15,
        rate_limit_per_device_per_minute: int = 20,
    ):
        self.mock = mock
        self.audit = audit_logger or AuditLogger()
        self.safety = safety_validator or SafetyValidator()

        self._max_commands = max_commands_per_ticket
        self._rate_limit = rate_limit_per_device_per_minute

        # Counters
        self._commands_run_this_ticket: int = 0
        self._device_command_times: dict[str, list[float]] = defaultdict(list)

    # ── Public API ─────────────────────────────────────────────────────────────

    def run(self, command: str, device: str) -> BrokerResult:
        """
        Validate and execute a single command against a device.
        Returns a BrokerResult regardless of outcome.
        """

        # 1. Hard limit check
        if self._commands_run_this_ticket >= self._max_commands:
            reason = (
                f"Hard command limit reached ({self._max_commands} commands per ticket). "
                "Blocking further commands."
            )
            self.audit.command_blocked(command, reason)
            return BrokerResult(
                success=False, output="", command=command,
                device=device, blocked=True, block_reason=reason, mock=self.mock
            )

        # 2. Rate limit check
        rate_result = self._check_rate_limit(device)
        if not rate_result.passed:
            self.audit.command_blocked(command, rate_result.reason)
            self.audit.rate_limit_hit(device, self._commands_run_this_ticket, self._rate_limit)
            return BrokerResult(
                success=False, output="", command=command,
                device=device, blocked=True, block_reason=rate_result.reason, mock=self.mock
            )

        # 3. Device scope check
        device_result = self.safety.validate_device(device)
        if not device_result.passed:
            self.audit.command_blocked(command, device_result.reason)
            return BrokerResult(
                success=False, output="", command=command,
                device=device, blocked=True, block_reason=device_result.reason, mock=self.mock
            )

        # 4. Command validation (allow-list + deny-list)
        cmd_result = self.safety.validate_command(command)
        self.audit.command_validated(command, cmd_result.passed, cmd_result.reason)
        if not cmd_result.passed:
            self.audit.command_blocked(command, cmd_result.reason)
            return BrokerResult(
                success=False, output="", command=command,
                device=device, blocked=True, block_reason=cmd_result.reason, mock=self.mock
            )

        # 5. Execute
        self._commands_run_this_ticket += 1
        self._record_device_command_time(device)

        try:
            if self.mock:
                output = self._execute_mock(command, device)
            else:
                output = self._execute_live(command, device)
        except Exception as e:
            self.audit.error("command_broker.run", f"Command execution failed: {e}", e)
            return BrokerResult(
                success=False, output=str(e), command=command,
                device=device, blocked=False, mock=self.mock
            )

        # 6. Sanitize output before returning
        sanitized = self.safety.sanitize_output(output)

        self.audit.command_executed(
            command=command,
            device=device,
            mock=self.mock,
            success=True,
            output_length=len(sanitized),
        )

        return BrokerResult(
            success=True, output=sanitized, command=command,
            device=device, blocked=False, mock=self.mock
        )

    def run_batch(self, commands: list[str], device: str) -> list[BrokerResult]:
        """Run multiple commands against one device, stopping on hard limit."""
        results = []
        for cmd in commands:
            result = self.run(cmd, device)
            results.append(result)
            # If hard limit hit, stop immediately
            if result.blocked and "Hard command limit" in result.block_reason:
                break
        return results

    def reset_ticket_counter(self) -> None:
        """Reset per-ticket command counter (call when starting a new ticket)."""
        self._commands_run_this_ticket = 0

    @property
    def commands_run(self) -> int:
        return self._commands_run_this_ticket

    # ── Rate Limiting ─────────────────────────────────────────────────────────

    def _check_rate_limit(self, device: str) -> ValidationResult:
        """Sliding window rate limit: max N commands per device per 60 seconds."""
        now = time.monotonic()
        window = 60.0
        times = self._device_command_times[device]
        # Remove timestamps outside the window
        self._device_command_times[device] = [t for t in times if now - t < window]
        if len(self._device_command_times[device]) >= self._rate_limit:
            return ValidationResult(
                passed=False,
                reason=(
                    f"Rate limit exceeded for device '{device}': "
                    f"{self._rate_limit} commands per minute max."
                )
            )
        return ValidationResult(passed=True, reason="Rate limit OK.")

    def _record_device_command_time(self, device: str) -> None:
        self._device_command_times[device].append(time.monotonic())

    # ── Mock Execution ────────────────────────────────────────────────────────

    def _execute_mock(self, command: str, device: str) -> str:
        """
        Return canned mock output for a command.
        Imports lazily to avoid circular imports.
        """
        from tools.cisco_health_checks import get_mock_output
        return get_mock_output(command, device)

    # ── Live Execution (Netmiko) — FUTURE ─────────────────────────────────────

    def _execute_live(self, command: str, device: str) -> str:
        """
        Execute a command against a real Cisco device via Netmiko.

        IMPORTANT: Credentials are fetched from the secrets provider here,
        NEVER passed from user input or stored in this class.

        This method is intentionally left as a stub for Phase 2.
        Credentials will come from HashiCorp Vault via SecretsProvider.
        """
        # Future implementation:
        #   from tools.secrets_provider import SecretsProvider
        #   creds = SecretsProvider().get_device_credentials(device)
        #   device_info = self.safety.get_device_info(device)
        #   connection = ConnectHandler(
        #       device_type=_platform_to_netmiko(device_info["platform"]),
        #       host=device,
        #       username=creds.username,
        #       password=creds.password,
        #       secret=creds.enable_secret,
        #   )
        #   output = connection.send_command(command)
        #   connection.disconnect()
        #   return output
        raise NotImplementedError(
            "Live Netmiko mode is not yet implemented. "
            "Run with --mock flag or implement SecretsProvider + Netmiko integration."
        )
