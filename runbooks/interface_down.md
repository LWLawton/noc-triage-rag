# Runbook: Interface Down

## Alert Type
Interface Down / Link Down / Port Down / Interface Flap

## Overview
This runbook covers the initial investigation steps for a Cisco IOS/NX-OS access or distribution port that is reported as operationally down by monitoring.

---

## Common Causes

1. **Physical layer issue** — Cable unplugged, damaged, or wrong cable type (SFP mismatch, copper vs fiber)
2. **Remote end shutdown** — The connected device (server, phone, AP, printer) is powered off or its port is administratively shut
3. **Administrative shutdown** — Port was manually shut down on the switch side
4. **Speed/duplex mismatch** — Negotiation failure causes link to not come up
5. **SFP/optic failure** — Transceiver failed or is unsupported
6. **PoE issue** — End device requires PoE but switch cannot supply power (budget exceeded, inline power fault)
7. **BPDU Guard / STP violation** — Port placed in err-disabled state due to spanning-tree BPDU Guard trigger
8. **Port security violation** — Too many MAC addresses or unauthorized MAC detected, port err-disabled
9. **UDLD / Loop Guard action** — Unidirectional link detected, port blocked
10. **Hardware fault** — Bad port, line card failure, or stack member issue

---

## Initial Health Checks (Read-Only)

Run these commands in order. All commands are read-only.

```
show interface <interface>
show interface <interface> status
show interface <interface> counters errors
show running-config interface <interface>
show logging last 100
show cdp neighbors detail
show power inline <interface>
show mac address-table interface <interface>
```

---

## Key Things to Look For

### In `show interface <interface>`
- **Line protocol**: Is it `down` (physical) or `down (notconnect)`?
- **err-disabled**: Indicates a policy violation (BPDU Guard, port security, etc.)
- **Input/output errors**: High error counts suggest physical layer or duplex issues
- **Last input / Last output**: Was traffic flowing before the outage?
- **Hardware type**: Verify SFP type matches expected media

### In `show interface <interface> status`
- **Status column**: `connected`, `notconnect`, `disabled`, `err-disabled`
- **Speed/duplex**: Look for `a-full/a-100` vs forced mismatches

### In `show running-config interface <interface>`
- **shutdown** keyword: Port was administratively shut
- **switchport mode**: Access vs trunk, check VLAN assignment
- **spanning-tree portfast**: Should be enabled on access ports
- **spanning-tree bpduguard enable**: If present, check if BPDU Guard triggered
- **storm-control**: May have triggered and err-disabled port
- **power inline**: PoE configuration

### In `show logging last 100`
- Look for: `%LINK-3-UPDOWN`, `%LINEPROTO-5-UPDOWN`, `%PM-4-ERR_DISABLE`, `%SPANTREE-2-BLOCK_BPDUGUARD`, `%PORT_SECURITY-2-PSECURE_VIOLATION`
- Note: timestamp of last state change

### In `show power inline <interface>`
- Check admin and oper status
- Check if power is being delivered or denied

---

## Err-Disabled Recovery (READ-ONLY — DO NOT CLEAR)

If the port is in `err-disabled` state, note the reason from logs. **Do not issue `shutdown/no shutdown` — escalate to engineer.**

Common err-disable causes:
- `bpduguard` — A downstream device sent a BPDU (possible switch connected to access port)
- `psecure-violation` — MAC address policy violated
- `udld` — Unidirectional link detected
- `storm-control` — Broadcast/multicast storm threshold exceeded
- `loopback` — Physical loop detected on port
- `link-flap` — Port was flapping and auto-disabled

---

## Decision Tree

```
Is the port err-disabled?
  YES → Note the reason from logs → Escalate to engineer
  NO  → Is the port administratively shut?
          YES → Escalate to engineer (intentional? change control?)
          NO  → Is the port "notconnect"?
                  YES → Is it a PoE device?
                          YES → Check power inline, check end device power
                          NO  → Check physical cable, check remote end
                  NO  → Check for physical errors and SFP issues
```

---

## Escalation Criteria

Escalate to **Tier 2 / Network Engineering** if:
- Port is err-disabled and reason is unclear
- High input/output errors with no obvious cause
- SFP/optic failure suspected
- Stack member issue suspected
- The interface connects to a critical server or uplink

Escalate to **Facilities** if:
- PoE budget exceeded and a large number of devices are affected
- Physical cable or patch panel damage is suspected

---

## Notes for Engineer
- Verify change control before making any configuration change
- If port was administratively shut, confirm with requestor before enabling
- Document the resolution in the ticket
- All checks performed by this agent are **read-only**. No changes were made.
