# Hardware

Physical build of the wearable node, the border router, and the enclosure.

## Bill of materials (per deployment)

| Qty | Part | Role |
|---|---|---|
| 3 | Seeed Studio XIAO nRF52840 Sense | Wearable node MCU + IEEE 802.15.4 radio; on-board LSM6DS3TR-C IMU |
| 3 | MH-ET LIVE MAX30102 breakout | PPG (red + IR) heart-rate sensor |
| 3 | 3.7 V 250 mAh LiPo (502030) | Node battery |
| 3 | SPST slide switch | Inline power switch on the battery lead |
| 1 | Nordic PCA10059 nRF52840 USB dongle | Border router radio / RPL root |
| 1 | Raspberry Pi 4 | Downstream host: UDP sink, logging, supervisor view |
| 3 | 3D-printed wrist enclosure + watch strap | Node housing |

## Wiring (wearable node)

| MAX30102 | XIAO nRF52840 Sense |
|---|---|
| VIN | 3V3 |
| GND | GND |
| SDA / SCL | I2C bus used by RIOT `I2C_DEV(0)` |

- **Solder the 3V3 jumper on the back of the MH-ET LIVE MAX30102.** Its I2C pull-ups default to the 1.8 V rail; with a 3.3 V host the sensor will not ACK (every read returns `-ENXIO`).
- I2C addresses on the node bus: MAX30102 `0x57`, LSM6DS3TR-C `0x6B`.
- Use soldered joints or direct female–female jumpers. Breadboard contacts were unreliable for I2C in testing.

## Power

- The LiPo is soldered directly to the XIAO `BAT+` / `BAT−` pads (no JST connector), with the slide switch inline on the positive lead. The XIAO charges the cell over USB-C.
- Range and walk tests must run on battery. A USB-tethered node browns out and resets when the cable is tugged, which corrupts the measurement.

## Stack order (inside the case, skin side first)

1. MAX30102: bottom, sensor window facing the skin
2. LiPo cell
3. XIAO nRF52840 Sense: top
4. Slide switch: on the side wall

## Enclosure

- **Prototype 1 (HR node)**: 3D-printed box enclosure with hand-cut sensor and switch openings, using the spring-bar lug geometry from enclosure revision V1.3 (that lug gap fit standard watch straps well).
- **Nodes 2 and 3**: redesign in progress, keeping the V1.3 lug/spring-bar geometry and the smaller V2 cavity. STL files will be added to `hardware/enclosure/` as each revision is printed.

## RF notes

- Both the XIAO and the PCA10059 use small on-board chip antennas. External antennas were not used.
- TX power is raised from RIOT's 0 dBm default to the nRF52840 maximum of +8 dBm on both nodes and the border router (`firmware/mesh/rpl_tuning.mk`).
- 2.4 GHz is strongly attenuated by the body and by laptop chassis. For range tests, mount the node away from the body with clear line of sight.
