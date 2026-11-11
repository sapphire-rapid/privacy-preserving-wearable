# Architecture

## Hardware

| Component | Role |
|---|---|
| Seeed XIAO nRF52840 Sense ×N | Wearable node: onboard LSM6DS3TR-C IMU + external MAX30102 PPG sensor, RIOT OS, custom RPL OF |
| Nordic PCA10059 nRF52840 dongle | Border router radio — runs RIOT `gnrc_border_router`, owns the RPL/6LoWPAN stack |
| Raspberry Pi 4 | Downstream host only — UDP server, logging, supervisor view. Does **not** run BR logic (RIOT has no slip-radio "dumb radio" path) |

## Network

- IEEE 802.15.4 (O-QPSK, 250 kbps) at the PHY/MAC layer, 6LoWPAN for IPv6 header compression, RPL for mesh routing.
- Wireless mesh prefix: `2001:db8::/64`. BR uplink (to the Pi): `2001:db8:1::/64`, static-configured (`PREFIX_CONF=static`), so the Pi side needs manual IPv6 address/route configuration — see `docs/INSTALLATION.md`.
- Routing decisions (planned: custom OF) will weight a node's DODAG parent choice by its current health-urgency flag, residual battery, and IMU-derived mobility — a node mid-alert should get preferential routing over idle neighbors, not continuous ML-driven re-routing.

## On-device inference pipeline

1. **Stage 1 — Fall detection (IMU, ML):** 1–2 s accelerometer windows, 9 magnitude/tilt features, logistic regression classifier, running directly on the XIAO.
2. **Stage 2 — Severity check (PPG, rule-based):** on a Stage-1 trigger, a 10–30 s heart-rate read determines whether the alert is "fall-only" or "critical."
3. The combined alert level is what feeds the RPL routing priority above — this is deliberately not a continuous classifier driving routing on every packet.

## Software stack

- RIOT OS, custom apps built outside the RIOT tree (`RIOTBASE` pointing back at a pristine checkout — never edited in place).
- MAX30102 driver written from scratch against RIOT's `periph/i2c.h` (no native driver exists in-tree).
- Border router: stock RIOT `gnrc_border_router` example, `UPLINK=cdc-ecm`.
- Pi 4: a plain Python UDP server (RIOT native board mode doesn't build on aarch64 — hardcoded x86 flags in RIOT's native board makefiles).
