# Runbook: Wireless AP Down

## Alert Type
AP Down / Wireless AP Down / Access Point Offline

## Overview
A wireless access point has gone offline or lost its connection to the wireless controller.

---

## Common Causes

1. **Switch port down** — AP's switch port is down (see Interface Down runbook)
2. **PoE failure** — AP lost power from switch (PoE budget exceeded, inline power fault)
3. **CAPWAP tunnel failure** — Control tunnel to WLC dropped
4. **AP hardware failure** — AP itself has crashed or failed
5. **IP connectivity loss** — AP cannot reach the WLC IP
6. **VLAN/DHCP issue** — AP unable to obtain an IP address
7. **WLC failure** — Wireless controller is down or unreachable
8. **Certificate expiry** — CAPWAP certificate expired

---

## Initial Health Checks (Read-Only)

```
show version
show logging last 100
show ip interface brief
show power inline
```

---

## Key Things to Look For

### In `show power inline`
- Is the AP's switch port delivering power?
- Is PoE budget exhausted?

### In `show logging last 100`
- Look for: `%CAPWAP-5-CHANGED`, `%DOT11-6-ASSOC`, `%LINK-3-UPDOWN` for the AP's switch port

---

## Escalation Criteria
- Multiple APs down simultaneously — suspect WLC or upstream switch issue, escalate
- PoE budget exhausted — escalate to Network Engineering for capacity review
- AP hardware failure confirmed — escalate to Facilities for physical replacement

---

## Notes
All checks are **read-only**. No changes were made.
