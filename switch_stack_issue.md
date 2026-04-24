# Runbook: Switch Stack Issue

## Alert Type
Stack Member Down / Switch Stack Issue / Stack Partial Ring

## Overview
A Cisco IOS switch stack has lost a member or is reporting a stack ring issue. This runbook covers read-only investigation for Cisco StackWise/StackWise-480 stack events.

---

## Common Causes

1. **Stack cable failure** — StackWise cable damaged, disconnected, or failed
2. **Stack member power failure** — Member switch lost power (PSU failure, power strip trip)
3. **Stack member hardware failure** — Switch crashed or hardware fault
4. **Stack software mismatch** — Incompatible IOS version on a new stack member
5. **Stack ring degraded** — One cable path failed, stack operating in half-ring mode
6. **Member renumbering** — Stack member number changed after reload causing confusion
7. **Overheating** — Environmental issue causing member to shut down

---

## Initial Health Checks (Read-Only)

```
show version
show environment all
show logging last 100
show interfaces status
```

---

## Key Things to Look For

### In `show version`
- **Switch stack members**: Are all members present?
- **Active / Standby**: Which switch is active master?
- **Stack MAC**: Has the stack MAC changed (indicates master election occurred)?

### In `show environment all`
- Fan, power supply, and temperature status per stack member
- Any member showing CRITICAL or FAILED status

### In `show logging last 100`
- Look for: `%STACKMGR-4-STACK_LINK_CHANGE`, `%STACKMGR-6-MASTER_READY`, `%STACKMGR-4-LOST_MEMBER`, `%ENVIRONMENT-1-ALERT`

---

## Escalation Criteria
- Stack member physically absent — escalate to Facilities/hands-on engineer
- Stack ring degraded — escalate to Network Engineering for cable replacement scheduling
- Master re-election occurred — verify impact on connected devices

---

## Notes
All checks are **read-only**. No changes were made.
