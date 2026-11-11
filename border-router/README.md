# Border Router

- Dongle: Nordic PCA10059, running RIOT's gnrc_border_router example (UPLINK=cdc-ecm, PREFIX_CONF=static, gnrc_rpl enabled in the Makefile).
- Host: Raspberry Pi 4 — downstream logging only, does not run RPL/6LoWPAN logic.
- hr_reply_server.py: Python UDP server — receives node packets, sends ACKs, tracks per-session packet loss (reset on RPL rejoin), and logs to CSV for range/walk tests.

> Populate this folder with hr_reply_server.py from the Pi 4.
