# Runbook: VLAN Issue

## Alert Type
VLAN Issue / VLAN Not Found / VLAN Mismatch

## Overview
A VLAN-related issue has been detected. This may be a missing VLAN, a trunk mismatch, or a VLAN pruning issue.

---

## Common Causes

1. **VLAN not in database** — VLAN was deleted or never created on this switch
2. **VLAN not allowed on trunk** — Trunk configuration is missing the VLAN
3. **VTP pruning** — VLAN pruned by VTP, removing it from trunk
4. **VTP mode mismatch** — Client/server/transparent inconsistency
5. **Native VLAN mismatch** — Trunk ends have different native VLANs (causes log messages)
6. **VLAN suspended** — VLAN in suspended state in database
7. **Access port VLAN mismatch** — Port assigned to wrong VLAN

---

## Initial Health Checks (Read-Only)

```
show vlan brief
show interface <interface> status
show interfaces status
show logging last 100
```

---

## Key Things to Look For

### In `show vlan brief`
- Is the VLAN present and **active**?
- Which ports are assigned to the VLAN?

### In `show logging last 100`
- Look for: `%SW_VLAN-4-VLAN_CREATE_FAIL`, `%CDP-4-NATIVE_VLAN_MISMATCH`, `%DTP-5-TRUNKPORTON`

---

## Escalation Criteria
- VLAN missing from multiple switches — possible VTP issue, escalate to Network Engineering
- Native VLAN mismatch on uplink — escalate, potential security concern

---

## Notes
All checks are **read-only**. No changes were made.
