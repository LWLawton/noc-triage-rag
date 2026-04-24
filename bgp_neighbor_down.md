# Runbook: BGP Neighbor Down

## Alert Type
BGP Neighbor Down / BGP Session Down / BGP Peer Down

## Overview
A BGP peering session has dropped or failed to establish. This runbook covers initial read-only investigation for Cisco IOS/IOS-XE/NX-OS BGP issues.

---

## Common Causes

1. **Physical/transport link failure** — Underlying interface down breaks TCP session
2. **TCP port 179 blocked** — ACL or firewall blocking BGP port
3. **Authentication mismatch** — MD5 password mismatch between peers
4. **TTL security failure** — GTSM/TTL mismatch
5. **Hold timer expired** — Keepalives not received in time (congestion, CPU overload)
6. **Routing loop or missing return path** — BGP next-hop unreachable
7. **Neighbor IP misconfiguration** — Wrong neighbor IP or update-source
8. **Route policy rejection** — Inbound/outbound policy dropping all prefixes
9. **BGP process restart** — Memory exhaustion, process crash, planned maintenance
10. **AS number mismatch** — Remote AS configured incorrectly

---

## Initial Health Checks (Read-Only)

```
show ip bgp summary
show ip route <neighbor_ip>
show ip interface brief
show logging last 100
show processes cpu sorted
```

---

## Key Things to Look For

### In `show ip bgp summary`
- **State/PfxRcd column**: `Active`, `Idle`, `Connect` indicate session is not established
- **Up/Down**: How long has session been down?
- **PfxRcd**: If 0 prefixes received, session may be up but policy is filtering all routes

### In `show ip route <neighbor_ip>`
- Is there a valid route to the BGP peer IP?
- Is the next-hop reachable?

### In `show logging last 100`
- Look for: `%BGP-5-ADJCHANGE`, `%BGP-3-NOTIFICATION`, `%BGP-4-MSGDUMP`
- Note: BGP notification codes (HOLD TIMER EXPIRED, OPEN MESSAGE ERROR, etc.)

---

## Escalation Criteria
- Session flapping repeatedly — escalate to Network Engineering
- Authentication or policy change suspected — escalate with change control
- Carrier/ISP BGP session — escalate to Vendor/ISP

---

## Notes
All checks are **read-only**. No changes were made.
