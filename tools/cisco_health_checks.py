"""
cisco_health_checks.py
Defines the health check sets for each ticket type and provides
mock Cisco IOS command outputs for --mock mode.

In mock mode: returns realistic pre-canned outputs.
In live mode: the command broker handles actual execution.
"""

from typing import Optional


# ── Health Check Sets ─────────────────────────────────────────────────────────

# Maps health check names (from ticket_types.yaml) to actual CLI commands.
# {interface}, {ip}, {vlan} are substituted with ticket fields before execution.

HEALTH_CHECK_COMMANDS: dict[str, str] = {
    "show_version":                      "show version",
    "show_clock":                        "show clock",
    "show_inventory":                    "show inventory",
    "show_environment":                  "show environment all",
    "show_interface":                    "show interface {interface}",
    "show_interface_status":             "show interface {interface} status",
    "show_interface_counters_errors":    "show interface {interface} counters errors",
    "show_running_config_interface":     "show running-config interface {interface}",
    "show_interfaces_status":            "show interfaces status",
    "show_ip_interface_brief":           "show ip interface brief",
    "show_vlan_brief":                   "show vlan brief",
    "show_spanning_tree":                "show spanning-tree vlan {vlan}",
    "show_spanning_tree_interface":      "show spanning-tree interface {interface} detail",
    "show_etherchannel_summary":         "show etherchannel summary",
    "show_cdp_neighbors":                "show cdp neighbors detail",
    "show_lldp_neighbors":               "show lldp neighbors detail",
    "show_logging":                      "show logging last 100",
    "show_processes_cpu":                "show processes cpu sorted",
    "show_processes_memory":             "show processes memory sorted",
    "show_ip_route":                     "show ip route",
    "show_ip_route_specific":            "show ip route {ip}",
    "show_ip_ospf_neighbor":             "show ip ospf neighbor",
    "show_ip_bgp_summary":               "show ip bgp summary",
    "show_standby_brief":                "show standby brief",
    "show_mac_address_table":            "show mac address-table interface {interface}",
    "show_arp":                          "show arp",
    "show_power_inline":                 "show power inline",
    "show_power_inline_interface":       "show power inline {interface}",
}


def resolve_commands(
    health_check_names: list[str],
    interface: Optional[str] = None,
    ip: Optional[str] = None,
    vlan: Optional[str] = None,
) -> list[str]:
    """
    Convert health check names to actual CLI commands with parameters substituted.
    Skips any health check that requires a parameter not provided.
    """
    commands = []
    for name in health_check_names:
        template = HEALTH_CHECK_COMMANDS.get(name)
        if not template:
            continue

        cmd = template
        if "{interface}" in cmd:
            if not interface:
                continue   # Skip — no interface provided
            cmd = cmd.replace("{interface}", interface)
        if "{ip}" in cmd:
            if not ip:
                continue
            cmd = cmd.replace("{ip}", ip)
        if "{vlan}" in cmd:
            if not vlan:
                continue
            cmd = cmd.replace("{vlan}", vlan)

        commands.append(cmd)

    return commands


# ── Mock Outputs ──────────────────────────────────────────────────────────────

def get_mock_output(command: str, device: str) -> str:
    """
    Return a realistic mock output for a given command and device.
    Normalizes the command to match mock output keys.
    """
    cmd = command.strip().lower()

    # --- show version ---
    if cmd == "show version":
        return f"""Cisco IOS Software, Version 15.2(7)E6, RELEASE SOFTWARE (fc2)
Technical Support: http://www.cisco.com/techsupport
ROM: Bootstrap program is C2960X boot loader
{device} uptime is 47 weeks, 3 days, 14 hours, 22 minutes
System returned to ROM by power-on
System image file is "flash:c2960x-universalk9-mz.152-7.E6.bin"
cisco WS-C2960X-48FPD-L (APM86XXX) processor with 524288K bytes of memory.
Switch Ports Model                     SW Version            SW Image
------ ----- -----                     ----------            ----------
*    1 52    WS-C2960X-48FPD-L         15.2(7)E6             C2960X-UNIVERSALK9-M

Stack Members:
  Switch  Role     Mac Address     Priority Version  State
-----------------------------------------------------------
  *1      Active   f07f.06xx.xxxx  15       V01      Ready
   2      Member   f07f.06xx.xxxy  1        V01      Ready

Configuration register is 0xF
"""

    # --- show clock ---
    if cmd == "show clock":
        return "*10:15:32.104 UTC Thu Apr 24 2026\n"

    # --- show interface Gi1/0/14 ---
    if "show interface" in cmd and "gi1/0/14" in cmd and "status" not in cmd and "counter" not in cmd and "running" not in cmd:
        return """GigabitEthernet1/0/14 is down, line protocol is down (notconnect)
  Hardware is Gigabit Ethernet, address is f07f.0601.0e0e (bia f07f.0601.0e0e)
  MTU 1500 bytes, BW 1000000 Kbit/sec, DLY 10 usec,
     reliability 255/255, txload 1/255, rxload 1/255
  Encapsulation ARPA, loopback not set
  Keepalive set (10 sec)
  Auto-duplex, Auto-speed, media type is 10/100/1000BaseTX
  input flow-control is off, output flow-control is unsupported
  ARP type: ARPA, ARP Timeout 04:00:00
  Last input never, output never, output hang never
  Last clearing of "show interface" counters never
  Input queue: 0/75/0/0 (size/max/drops/flushes); Total output drops: 0
  5 minute input rate 0 bits/sec, 0 packets/sec
  5 minute output rate 0 bits/sec, 0 packets/sec
     0 packets input, 0 bytes, 0 no buffer
     Received 0 broadcasts (0 multicasts)
     0 runts, 0 giants, 0 throttles
     0 input errors, 0 CRC, 0 frame, 0 overrun, 0 ignored
     0 watchdog, 0 multicast, 0 pause input
     0 packets output, 0 bytes, 0 underruns
     0 output errors, 0 collisions, 0 interface resets
     0 unknown protocol drops
     0 babbles, 0 late collision, 0 deferred
     0 lost carrier, 0 no carrier, 0 pause output
     0 output buffer failures, 0 output buffers swapped out
"""

    # --- show interface Gi1/0/14 status ---
    if "show interface" in cmd and "gi1/0/14" in cmd and "status" in cmd:
        return """Port         Name               Status       Vlan       Duplex  Speed Type
Gi1/0/14                        notconnect   10         auto    auto  10/100/1000BaseTX
"""

    # --- show interface Gi1/0/14 counters errors ---
    if "show interface" in cmd and "gi1/0/14" in cmd and "counter" in cmd:
        return """Port        Align-Err     FCS-Err    Xmit-Err     Rcv-Err  UnderSize
Gi1/0/14            0           0           0           0          0
Port      Single-Col  Multi-Col  Late-Col Excess-Col  Carri-Sen     Runts    Giants
Gi1/0/14           0          0         0          0          0         0         0
"""

    # --- show running-config interface Gi1/0/14 ---
    if "show running-config interface" in cmd and "gi1/0/14" in cmd:
        return """Building configuration...

Current configuration : 186 bytes
!
interface GigabitEthernet1/0/14
 description WORKSTATION-14
 switchport access vlan 10
 switchport mode access
 spanning-tree portfast
 spanning-tree bpduguard enable
end
"""

    # --- show interfaces status ---
    if cmd == "show interfaces status":
        return """Port      Name               Status       Vlan       Duplex  Speed Type
Gi1/0/1                         connected    1          a-full a-1000 10/100/1000BaseTX
Gi1/0/2                         connected    1          a-full a-1000 10/100/1000BaseTX
Gi1/0/14                        notconnect   10         auto    auto  10/100/1000BaseTX
Gi1/0/24                        connected    20         a-full a-1000 10/100/1000BaseTX
Gi1/0/48                        connected    trunk      a-full a-1000 10/100/1000BaseTX
"""

    # --- show ip interface brief ---
    if cmd == "show ip interface brief":
        return """Interface              IP-Address      OK? Method Status                Protocol
Vlan1                  10.0.1.1        YES NVRAM  up                    up
Vlan10                 10.10.10.1      YES NVRAM  up                    up
GigabitEthernet0/0     unassigned      YES unset  up                    up
"""

    # --- show vlan brief ---
    if cmd == "show vlan brief":
        return """VLAN Name                             Status    Ports
---- -------------------------------- --------- -------------------------------
1    default                          active    Gi1/0/1, Gi1/0/2
10   DATA_VLAN                        active    Gi1/0/14, Gi1/0/15
20   VOICE_VLAN                       active    Gi1/0/24
1002 fddi-default                     act/unsup
1003 token-ring-default               act/unsup
1004 fddinet-default                  act/unsup
1005 trnet-default                    act/unsup
"""

    # --- show logging last 100 ---
    if "show logging" in cmd:
        return """Syslog logging: enabled (0 messages dropped, 3 messages rate-limited, 0 flushes, 0 overruns, xml disabled, filtering disabled)
No Active Message Discriminator.
No Inactive Message Discriminator.
    Console logging: disabled
    Monitor logging: level debugging, 0 messages logged, xml disabled, filtering disabled
    Buffer logging:  level debugging, 2142 messages logged, xml disabled, filtering disabled
    Logging Exception size (4096 bytes)
    Count and timestamp logging messages: disabled
    Persistent logging: disabled

Log Buffer (4096 bytes):
Apr 24 10:14:55.103: %LINK-3-UPDOWN: Interface GigabitEthernet1/0/14, changed state to down
Apr 24 10:14:56.110: %LINEPROTO-5-UPDOWN: Line protocol on Interface GigabitEthernet1/0/14, changed state to down
Apr 24 10:13:01.225: %LINK-3-UPDOWN: Interface GigabitEthernet1/0/14, changed state to up
Apr 24 10:13:02.231: %LINEPROTO-5-UPDOWN: Line protocol on Interface GigabitEthernet1/0/14, changed state to up
Apr 24 09:55:00.001: %SYS-5-CONFIG_I: Configured from console by admin on vty0 (10.0.1.50)
Apr 23 14:22:10.442: %LINK-3-UPDOWN: Interface GigabitEthernet1/0/14, changed state to down
Apr 23 14:22:11.449: %LINEPROTO-5-UPDOWN: Line protocol on Interface GigabitEthernet1/0/14, changed state to down
"""

    # --- show cdp neighbors detail ---
    if "show cdp neighbors" in cmd:
        return """-------------------------
Device ID: dist-sw-01
Entry address(es):
  IP address: 10.0.0.1
Platform: cisco WS-C3750X-48P,  Capabilities: Switch IGMP
Interface: GigabitEthernet1/0/48,  Port ID (outgoing port): GigabitEthernet1/0/1
Holdtime : 159 sec

Version :
Cisco IOS Software, Version 12.2(55)SE12, RELEASE SOFTWARE (fc2)

advertisement version: 2
VTP Management Domain: 'PROD'
Native VLAN: 1
Duplex: full
Management address(es):
  IP address: 10.0.0.1
"""

    # --- show power inline ---
    if "show power inline" in cmd and "gi1/0/14" not in cmd and cmd != "show power inline":
        return ""
    if "show power inline" in cmd:
        if "gi1/0/14" in cmd:
            return """Available:370.0(w)  Used:52.0(w)  Remaining:318.0(w)

Interface Admin  Oper       Power   Device              Class Max
                                   (Watts)
--------- ------ ---------- ------- ------------------- ----- ----
Gi1/0/14  auto   off        0.0     n/a                 n/a   30.0
"""
        return """Available:370.0(w)  Used:52.0(w)  Remaining:318.0(w)

Interface Admin  Oper       Power   Device              Class Max
                                   (Watts)
--------- ------ ---------- ------- ------------------- ----- ----
Gi1/0/1   auto   on         7.0     IP Phone 8841       2     30.0
Gi1/0/14  auto   off        0.0     n/a                 n/a   30.0
Gi1/0/24  auto   on         15.4    IP Phone 8961       3     30.0
"""

    # --- show mac address-table interface ---
    if "show mac address-table interface" in cmd:
        return """          Mac Address Table
-------------------------------------------
Vlan    Mac Address       Type        Ports
----    -----------       --------    -----
(No MAC entries found for this interface — interface is down)
"""

    # --- show processes cpu sorted ---
    if "show processes cpu" in cmd:
        return """CPU utilization for five seconds: 8%/2%; one minute: 6%; five minutes: 5%
 PID Runtime(ms)     Invoked      uSecs   5Sec   1Min   5Min TTY Process
   1        1672       10042        166  0.00%  0.00%  0.00%   0 Chunk Manager
  63      118722      164338        722  0.31%  0.22%  0.18%   0 IP Input
 122       28332      105491        268  0.15%  0.08%  0.07%   0 OSPF Hello
"""

    # --- show environment all ---
    if "show environment" in cmd:
        return """Switch 1 FAN 1 is OK
Switch 1 FAN 2 is OK
Switch 2 FAN 1 is OK
Switch 2 FAN 2 is OK
SYSTEM TEMPERATURE is OK
SW  PS  PS-Status  Watts  System-watts  RemainingWatts Cutoff-Watts
--  --  ---------  -----  ------------  -------------- ------------
1   1   Good       370    52            318            n/a
2   1   Good       370    48            322            n/a
"""

    # --- show inventory ---
    if "show inventory" in cmd:
        return """NAME: "1", DESCR: "WS-C2960X-48FPD-L"
PID: WS-C2960X-48FPD-L    , VID: V01  , SN: FOC2134ABCD

NAME: "2", DESCR: "WS-C2960X-48FPD-L"
PID: WS-C2960X-48FPD-L    , VID: V01  , SN: FOC2134ABCE
"""

    # --- show ip route ---
    if "show ip route" in cmd:
        return """Codes: L - local, C - connected, S - static, R - RIP, M - mobile, B - BGP
       D - EIGRP, EX - EIGRP external, O - OSPF, IA - OSPF inter area

Gateway of last resort is 10.0.0.1 to network 0.0.0.0

S*    0.0.0.0/0 [1/0] via 10.0.0.1
      10.0.0.0/8 is variably subnetted
C        10.0.1.0/24 is directly connected, Vlan1
O        10.0.2.0/24 [110/2] via 10.0.0.1
"""

    # --- show ip bgp summary ---
    if "show ip bgp summary" in cmd:
        return """BGP router identifier 10.0.0.2, local AS number 65001
BGP table version is 42, main routing table version 42

Neighbor        V           AS MsgRcvd MsgSent   TblVer  InQ OutQ Up/Down  State/PfxRcd
10.0.0.1        4        65000    4821    4789       42    0    0 3d14h          24
"""

    # --- show ip ospf neighbor ---
    if "show ip ospf neighbor" in cmd:
        return """Neighbor ID     Pri   State           Dead Time   Address         Interface
10.0.0.1          1   FULL/DR         00:00:33    10.0.1.1        Vlan1
"""

    # --- show standby brief ---
    if "show standby brief" in cmd:
        return """                     P indicates configured to preempt.
                     |
Interface   Grp  Pri P State   Active          Standby         Virtual IP
Vl10        10   110 P Active  local           10.10.10.2      10.10.10.254
Vl20        20   110 P Active  local           10.20.20.2      10.20.20.254
"""

    # --- show arp ---
    if "show arp" in cmd:
        return """Protocol  Address          Age (min)  Hardware Addr   Type   Interface
Internet  10.0.1.1                -   f07f.0601.0000  ARPA   Vlan1
Internet  10.0.1.50             142   aa:bb:cc:dd:ee:ff  ARPA   Vlan1
"""

    # --- show spanning-tree ---
    if "show spanning-tree" in cmd:
        return """VLAN0010
  Spanning tree enabled protocol ieee
  Root ID    Priority    32778
             Address     f07f.0600.0000
             Cost        4
             Port        52 (GigabitEthernet1/0/48)
             Hello Time   2 sec  Max Age 20 sec  Forward Delay 15 sec

  Bridge ID  Priority    49162  (priority 49152 sys-id-ext 10)
             Address     f07f.0601.0000
             Hello Time   2 sec  Max Age 20 sec  Forward Delay 15 sec
             Aging Time  300 sec

Interface           Role Sts Cost      Prio.Nbr Type
------------------- ---- --- --------- -------- --------------------------------
Gi1/0/1             Desg FWD 4         128.1    P2p
Gi1/0/14            Desg BLK 4         128.14   P2p
Gi1/0/48            Root FWD 4         128.48   P2p
"""

    # --- show etherchannel summary ---
    if "show etherchannel" in cmd:
        return """Flags:  D - down        P - bundled in port-channel
        I - stand-alone s - suspended
        H - Hot-standby (LACP only)
        R - Layer3      S - Layer2
        U - in use      f - failed to allocate aggregator

        M - not in use, minimum links not met
        u - unsuitable for bundling
        w - waiting to be aggregated
        d - default port

Number of channel-groups in use: 0
Number of aggregators:           0

Group  Port-channel  Protocol    Ports
------+-------------+-----------+-----------------------------------------------
"""

    # --- show lldp neighbors ---
    if "show lldp neighbors" in cmd:
        return """Capability codes:
    (R) Router, (B) Bridge, (T) Telephone, (C) DOCSIS Cable Device
    (W) WLAN Access Point, (P) Repeater, (S) Station, (O) Other

Device ID           Local Intf     Hold-time  Capability      Port ID
dist-sw-01          Gi1/0/48       120        B, R            Gi1/0/1

Total entries displayed: 1
"""

    # --- show processes memory ---
    if "show processes memory" in cmd:
        return """Processor Pool Total:  524222464 Used:   87654321 Free:  436568143
 I/O Pool Total:   33554432 Used:    4567890 Free:   28986542

 PID TTY  Allocated      Freed    Holding    Getbufs    Retbufs Process
   0   0    6701784    6668936      97932          0          0 *Init*
   1   0       9376       8000       5376          0          0 Chunk Manager
"""

    # --- terminal commands ---
    if cmd in ("terminal length 0", "terminal width 0"):
        return ""

    # Default fallback
    return f"% Command not found in mock library: {command}\n"
