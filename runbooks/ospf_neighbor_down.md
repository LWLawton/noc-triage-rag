# Runbook: OSPF Neighbor Down

## Alert Type
OSPF Neighbor Down / OSPF Adjacency Down

## Overview
An OSPF adjacency has dropped. This runbook covers read-only investigation steps for Cisco IOS/NX-OS OSPF neighbor issues.

---

## Common Causes

1. **Interface down** — Underlying interface failure tears down adjacency
2. **Hello timer mismatch** — Hello/dead intervals must match between neighbors
3. **Area ID mismatch** — Neighbors must be in the same OSPF area
4. **Subnet mask mismatch** — Network type mismatch on the shared segment
5. **Authentication failure** — OSPF MD5 key mismatch
6. **MTU mismatch** — DBD packets being dropped due to MTU differences
7. **Duplicate OSPF Router ID** — Two devices with the same Router ID
8. **Network type mismatch** — Point-to-point vs broadcast mismatch
9. **OSPF process restart** — Caused by memory issues or CPU overload
10. **ACL blocking OSPF multicast** — 224.0.0.5/224.0.0.6 being blocked

---

## Initial Health Checks (Read-Only)

```
show ip ospf neighbor
show ip route
show ip interface brief
show logging last 100
show processes cpu sorted
```

---

## Key Things to Look For

### In `show ip ospf neighbor`
- **State**: Should be `FULL` for point-to-point or `FULL/DR` or `FULL/BDR` for broadcast
- **Dead Time**: If counting down to 0, hellos are not being received
- **Missing neighbor**: Neighbor not appearing at all may mean interface is down or hellos blocked

### In `show logging last 100`
- Look for: `%OSPF-5-ADJCHG`, `%OSPF-4-NONEIGHBOR`, `%OSPF-4-BADLSATYPE`
- Note: Reason for adjacency change (neighbor went down, dead timer expired, etc.)

---

## Escalation Criteria
- Neighbor repeatedly flapping — escalate to Network Engineering
- Multiple OSPF neighbors down simultaneously — potential process or hardware issue
- Core routing affected — escalate immediately

---

## Notes
All checks are **read-only**. No changes were made.
