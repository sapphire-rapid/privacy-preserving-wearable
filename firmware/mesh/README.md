# mesh — clean rewrite of the wearable RPL mesh

```
mesh/
├── rpl_tuning.mk        shared Trickle/lifetime/TX-power flags (every build includes it)
├── mesh_node/           ONE firmware for all XIAOs: make ROLE=hr | ROLE=relay
├── mesh_br/             nRF52840 dongle: border router + RPL root, auto-configured
└── server/mesh_server.py  Pi4 sink: per-node stats, replies "ACK"+seq
```

Built and checked against RIOT master (2026-11-12) with arm-none-eabi-gcc 13.2, `-Werror`:
mesh_node hr 72 KB, relay 70 KB, mesh_br 98 KB.

## Install (Fedora)

```bash
cd <your repo clone> && git pull          # brings in firmware/mesh/
cd firmware/mesh
```
`RIOTBASE` defaults to `~/riotproject` in both Makefiles, so the apps build from anywhere.
Build output goes to `bin/` (gitignored).

## Flash

```bash
# HR node (prototype 1, battery + MAX30102)  — double-tap reset for the UF2 drive
cd firmware/mesh/mesh_node
make ROLE=hr UF2_SOFTDEV=DROP flash

# the two relay XIAOs
make ROLE=relay UF2_SOFTDEV=DROP flash

# border router dongle: flash exactly the way you flashed gnrc_border_router before
cd ../mesh_br
make                     # -> bin/nrf52840dongle/mesh_br.hex for nrfutil
```
`UF2_SOFTDEV=DROP` is still mandatory on every XIAO flash.

Pi4: copy `server/mesh_server.py` over and run `python3 mesh_server.py`. It **replaces** `hr_reply_server.py`:
the repo version of that script replies with a bare 3-byte `ACK`, while the firmware only accepts
`ACK`+seq (7 bytes), and it mixed all nodes into one loss counter.
The Pi4 `usb0` systemd-networkd config stays as it is.

## What changed vs. the old apps

| Problem | Root cause (RIOT source) | Fix |
|---|---|---|
| `nib prefix add 6 2001:db8:1::/64` after every BR boot | `gnrc_ipv6_static_addr` adds the uplink address as a /128, so the /64 is never on-link | `mesh_br` adds the prefix in `main()` |
| ACKs dead after a BR reboot until `rpl trickle reset` | Root always boots with the same version and DTSN=1, so nodes never resend DAOs and the BR has no downward routes | Random DTSN at boot → every node resends its DAO; trickle reset at boot |
| Nodes need a power-cycle to find a parent | RIOT sends **one** DIS at init, then waits for DIOs; with Imax ≈ 2.3 h the wait can be hours | DIS keeper thread: multicast DIS every 5 s while the node has no parent |
| Slow reaction to moved/dead parents | Imax 2.3 h, route lifetime 5 min | Imax ≈ 33 s (Thread-like), 90 s routes, silent parent probed after 75 s |
| MAX30102 FIFO overflow | 500 ms blocking `sock_udp_recv` vs. a 320 ms FIFO | ACKs handled in their own thread; FIFO polled every 100 ms; `FIFO_OVF!` flag if it ever happens |

The power cost of the faster Trickle is negligible: the nRF52840 radio listens continuously anyway,
and the HR node already transmits every 3 s, against one DIO every ~33 s.

## What you should see

HR node terminal:
```
mesh_node role=HR period=3000ms sink=[2001:db8:1::2]:8888
[HR] MAX30102 OK (SpO2 mode, 100 Hz)
[RPL] no parent -> multicast DIS
[RPL] JOINED DODAG
[ADDR] 2001:db8::xxxx
[RPL] parent=fe80::... parent_rank=512 my_rank=768
[TX] seq=0 bpm=76 rank=768 hops=2 | loss=0% (0/0 ok) sent=1 acked=0 late=0
[ACK] seq=0 rtt=38ms
```
Relays print the same `[RPL]` lines plus a heartbeat `[TX]`/`[ACK]` every 10 s.
BR on boot:
```
[BR] uplink if 6: on-link prefix 2001:db8:1::/64 added
[BR] RPL root instance 0 dodag 2001:db8::... dtsn=137, trickle reset (Imin=1024ms, doublings=5)
```
Pi4: one `[RX <node> HR|relay/hb]` line per packet; type `t` + Enter for a per-node table,
a number + Enter to tag the distance for walk tests (CSV: `mesh_log.csv`).

## Acceptance test — no shell commands allowed

Pass = the HR terminal shows `[ACK]` again within ~10 s (worst case ~40 s) of the last step, every time.

1. BR + Pi4 up first, then power relay A, relay B, HR node.
2. HR node first, then relays, BR last.
3. Everything running → unplug/replug the BR dongle.
4. HR node out of BR range so it hops through a relay → switch that relay off → it should re-parent
   through the other relay or the BR within ~2 min (silent-parent probe).
5. Switch the relay back on → it rejoins on its own.

If a step fails, send me the HR, relay and BR terminal output from that step.
`rpl` and `nib route` are still available on the BR shell for diagnosis.
