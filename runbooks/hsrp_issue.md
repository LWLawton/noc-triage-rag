# Runbook: HSRP Issue

## Alert Type
HSRP State Change / HSRP Failover / HSRP Active Change

## Overview
An HSRP group has changed state. The virtual IP gateway may have failed over to the standby router.

---

## Common Causes

1. **Active router interface down** — Physical failure on active router triggers standby takeover
2. **HSRP hello timer expiry** — Active router stopped sending hellos (CPU overload, link congestion)
3. **Priority change** — Manual or tracked-object priority decrement caused failover
4. **IP SLA tracking failure** — Tracked object (uplink, IP reachability) failed, triggering preempt
5. **Preemption** — Higher-priority router came online and preempted active role
6. **Split-brain** — Both routers believe they are active (HSRP hello packets not reaching each other)

---

## Initial Health Checks (Read-Only)

```
show standby brief
show ip interface brief
show logging last 100
```

---

## Key Things to Look For

### In `show standby brief`
- **State**: Active / Standby / Init / Listen / Speak
- Are both routers showing expected states?
- Has the Active router changed compared to the expected primary?

### In `show logging last 100`
- Look for: `%HSRP-5-STATECHANGE`, `%TRACK-6-STATE`

---

## Escalation Criteria
- Both routers showing Active (split-brain) — escalate to Network Engineering immediately
- Repeated failovers — escalate for root cause investigation

---

## Notes
All checks are **read-only**. No changes were made.
