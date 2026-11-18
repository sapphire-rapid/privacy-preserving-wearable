# Border Router

> **Superseded.** The current border-router firmware is [`firmware/mesh/mesh_br`](../firmware/mesh/mesh_br) and the current Pi 4 sink is [`firmware/mesh/server/mesh_server.py`](../firmware/mesh/server/mesh_server.py). This folder keeps the original server for reference.

- Dongle: Nordic PCA10059 running RIOT's `gnrc_border_router` example (`UPLINK=cdc-ecm`, `PREFIX_CONF=static`, `gnrc_rpl` enabled in the Makefile).
- Host: Raspberry Pi 4, downstream logging only. It does not run RPL/6LoWPAN logic.
- `hr_reply_server.py`: the original UDP server. It receives node packets, replies with a bare `ACK`, tracks per-session packet loss (reset on RPL rejoin), and logs distance-tagged CSV rows for walk tests. `mesh_server.py` replaces it: it replies `ACK`+seq, as the current firmware expects, and keeps statistics per node.
