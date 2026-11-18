# Firmware

RIOT OS applications for the wearable nodes and the border router. All apps live outside the RIOT tree and point `RIOTBASE` at a separate, unmodified RIOT checkout (see [`docs/INSTALLATION.md`](../docs/INSTALLATION.md)).

| App | Status | Purpose |
|---|---|---|
| [`mesh/`](mesh/) | **current** | Single node image (`ROLE=hr` or `ROLE=relay`), auto-configuring border router (`mesh_br`), Pi 4 sink (`server/mesh_server.py`), shared RPL/radio tuning (`rpl_tuning.mk`) |
| [`fall_imu/`](fall_imu/) | in progress | Stage-1 fall detector port: exported LR model and feature code (`include/`), a gcc host harness that matches the Python reference (`host/`), and DRDY-gated LSM6DS3TR-C sampling at 52 Hz / ±16 g on the XIAO (`main.c`, step 1 of the on-board port) |
| `max30102_probe/` | validation | First MAX30102 driver + heart-rate app (single hop, ACK round-trip) |
| `imu_test/` | validation | Raw accelerometer/gyroscope over the RPL mesh |
| `relay_node/` | validation | First RPL relay app (superseded by `mesh_node ROLE=relay`) |

The validation apps are kept because each one proved a single subsystem (I2C sensor, UDP, RPL join, relaying) in isolation before it was combined into `mesh/`.

**Flash rule:** pass `UF2_SOFTDEV=DROP` on every XIAO flash.
