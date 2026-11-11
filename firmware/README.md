# Firmware

RIOT custom applications for the wearable nodes and relay, kept outside the pristine RIOT tree.

| App | Purpose |
|---|---|
| `max30102_probe` | PPG driver (custom, from scratch) + heart-rate extraction |
| `fall_imu` | Stage 1 fall-detection classifier (IMU, logistic regression, C export) |
| `imu_test` | IMU validation app (raw accel/gyro over RPL mesh) |
| `relay_node` | RPL multi-hop relay app |

Build each with RIOTBASE pointing at a separate RIOT checkout (see docs/INSTALLATION.md). Flash rule: always pass UF2_SOFTDEV=DROP.

> Populate this folder with the current contents of ~/riotproject-apps/ on the dev machine.
