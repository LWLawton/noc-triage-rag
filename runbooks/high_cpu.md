# Runbook: High CPU

## Alert Type
High CPU / CPU Threshold Exceeded / CPU Utilization High

## Overview
Device CPU utilization has exceeded the monitoring threshold. This runbook covers read-only investigation for Cisco IOS/NX-OS high CPU events.

---

## Common Causes

1. **Routing protocol storm** — OSPF/BGP reconvergence, STP topology change flooding
2. **Broadcast/multicast storm** — Layer 2 loop or misconfigured device flooding traffic
3. **ARP storm** — Gratuitous ARP flood or proxy ARP overload
4. **IP Input process** — Traffic being punted to CPU (TTL=1 packets, ICMP unreachable, etc.)
5. **Interface flapping** — Rapid link state changes consuming CPU
6. **CEF / FIB rebuild** — Large routing table change causing FIB refresh
7. **Debug commands left enabled** — Any active `debug` command causes significant CPU load
8. **Crypto/VPN processing** — High-throughput IPSec on software crypto
9. **SNMP polling** — Aggressive SNMP polling overwhelming the management plane
10. **Software bug or memory leak** — Process consuming abnormal CPU over time

---

## Initial Health Checks (Read-Only)

```
show processes cpu sorted
show processes memory sorted
show logging last 100
show environment all
show version
```

---

## Key Things to Look For

### In `show processes cpu sorted`
- **Top processes**: What process is consuming the most CPU?
- **IP Input high**: Traffic being process-switched (not CEF) — look for ACL hits, NAT, or punted traffic
- **Interrupt %**: Hardware interrupt load, indicates high packet rate
- **5sec/1min/5min**: Compare — is CPU sustained high or was it a spike?

### In `show logging last 100`
- Look for: `%SYS-3-CPUHOG`, `%PLATFORM_ENV-1-FRU_PS_ACCESS`, topology change messages, interface flap messages
- Note: Timing of CPU spike vs other events

---

## Escalation Criteria
- CPU sustained above 90% for more than 5 minutes — escalate to Network Engineering immediately
- Control plane protocols affected (OSPF/BGP drops) — escalate
- Debug commands left active — escalate to clear (requires config access)

---

## Notes
All checks are **read-only**. No changes were made.
