# Installation / Dev Environment Setup

## Prerequisites

- Linux dev machine (this project is developed on Fedora) with the ARM embedded GCC toolchain.
- `nrfutil` — the Rust-based v8.x release (the legacy pip v5 release does not work for this dongle).
- Python 3 on the Raspberry Pi 4.

## 1. RIOT OS + custom apps

```
git clone https://github.com/RIOT-OS/RIOT.git ~/riotproject
# Custom apps live OUTSIDE the RIOT tree, pointing RIOTBASE back at it:
#   ~/riotproject-apps/<appname>/Makefile  ->  RIOTBASE ?= $(HOME)/riotproject
```

## 2. Flashing a XIAO node

Important: UF2_SOFTDEV=DROP must be passed on every flash. Without it the SoftDevice blocks the RIOT image, and once dropped, Arduino IDE / Nordic serial DFU will no longer work on that board — RIOT's UF2 drag-and-drop path is the only way to flash it from then on.

```
cd ~/riotproject-apps/<appname>
make BOARD=seeedstudio-xiao-nrf52840-sense UF2_SOFTDEV=DROP flash
```

If the board doesn't show up as a USB drive, double-tap reset to force the UF2 bootloader.

## 3. Border router

```
cd ~/riotproject/examples/networking/gnrc/gnrc_border_router
make BOARD=nrf52840dongle UPLINK=cdc-ecm PREFIX_CONF=static flash
```

gnrc_rpl must be enabled manually in the app's Makefile. Plug the flashed dongle into the Pi 4.

## 4. Raspberry Pi 4 side

PREFIX_CONF=static means the BR does not send router advertisements on its uplink, so the Pi's usb0 needs a persistent static config (survives dongle reconnects via systemd-networkd):

```
sudo tee /etc/systemd/network/10-usb0.network << 'NET'
[Match]
Name=usb0

[Network]
Address=2001:db8:1::2/64

[Route]
Destination=2001:db8::/64
Gateway=2001:db8:1::1
NET
sudo systemctl restart systemd-networkd
networkctl status usb0   # should show "routable (configured)"
```

Run the UDP server (see border-router/):

```
python3 ~/privacy-preserving-wearable/border-router/hr_reply_server.py
```

## 5. Verifying the mesh

On the border router shell (pyterm/serial over ttyACM0):

```
nib route     # confirm the node's route is present
nib neigh     # confirm a resolved neighbor entry
```

On the Pi 4, confirm traffic with `tcpdump -i usb0 -n port 8888` while a node is sending.
