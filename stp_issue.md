# Runbook: STP Issue

## Alert Type
Spanning Tree Issue / STP Topology Change / STP Loop / TCN

## Overview
A Spanning Tree Protocol topology change or instability event has been detected.

---

## Common Causes

1. **BPDU Guard trigger** — Non-switch device connected to PortFast port sent a BPDU
2. **Topology change notification (TCN) flood** — Frequent TCNs flushing MAC tables, causing performance issues
3. **Root bridge change** — Unintended device won root bridge election
4. **Port role change** — Designated/root port roles shifting (indicates instability)
5. **Physical loop** — Physical cable loop with no STP protection (BPDU filter misconfigured)
6. **Unidirectional link** — STP blocking based on incorrect topology view

---

## Initial Health Checks (Read-Only)

```
show spanning-tree vlan <vlan>
show interfaces status
show logging last 100
```

---

## Key Things to Look For

### In `show spanning-tree vlan <vlan>`
- **Root bridge**: Is it the expected switch?
- **Port states**: Any unexpected BLK (blocking) or LIS (listening)?
- **Topology changes**: High TC count indicates instability

### In `show logging last 100`
- Look for: `%SPANTREE-2-BLOCK_BPDUGUARD`, `%SPANTREE-5-TOPOTRAP`, `%SPANTREE-2-LOOPGUARD_BLOCK`

---

## Escalation Criteria
- Root bridge is an access switch (should never be root) — escalate to Network Engineering
- Topology changes occurring every few seconds — active loop or instability, escalate immediately

---

## Notes
All checks are **read-only**. No changes were made.
