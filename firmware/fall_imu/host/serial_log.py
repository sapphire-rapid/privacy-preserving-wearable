#!/usr/bin/env python3
"""
serial_log.py - drive the fall_imu serial menu and log every line with a host
timestamp.

  serial_log.py MODE [--timeout S] [--stop-after S] [--port DEV]

MODE is one menu command: t s r l w i   (x is sent automatically on --stop-after).

  * Handshake: sends "x\\n" until the firmware answers with its "MENU>" line, then
    sends the mode character.
  * Every received line is written to  logs/<mode>_<YYYYmmdd-HHMMSS>.log  as
        <host ISO time, ms> | <line>
    (logs/ is gitignored).  Lines the host adds itself start with "HOST", the
    EVENT lines you add with --event start with "EVENT".
  * Survives USB re-enumeration: when the port vanishes it logs "HOST port lost",
    keeps retrying to open it, and logs "HOST port reopened".  The mode is NOT
    re-sent (a reset device is back at the menu).  A "### BOOT" line appearing
    mid-run means the board reset -> logged as "HOST DEVICE RESET (brownout?)".
  * Stops on the mode's end marker ("### DONE <m>" / "### STOPPED <m>") or on
    --timeout (exit 2).  --stop-after S sends 'x' after S seconds and then waits
    for the STOPPED marker.
  * Physical-action events, from ANOTHER shell while a run is going:
        serial_log.py --event "start hold_in_hand"
        serial_log.py --event "end hold_in_hand"
    The event is stamped with the host time of that call (not of the poll) and
    appended to the running log as an EVENT line.

Exit codes: 0 marker seen, 2 timeout, 3 no port.
"""
import argparse
import datetime as dt
import glob
import os
import re
import sys
import time

try:
    import serial
except ImportError:
    serial = None

HERE = os.path.dirname(os.path.abspath(__file__))
APP_DIR = os.path.dirname(HERE)
LOG_DIR = os.path.join(APP_DIR, "logs")
CTL_FILE = os.path.join(LOG_DIR, "ctl.txt")

DEFAULT_TIMEOUT = {"t": 90, "s": 60, "r": 130, "i": 15, "l": 600, "w": 600}


def iso(ts):
    return dt.datetime.fromtimestamp(ts).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3]


def find_port():
    ports = sorted(glob.glob("/dev/ttyACM*"))
    return ports[0] if ports else None


class Logger:
    """One run: handshake, command, capture, stop."""

    def __init__(self, mode, port=None, timeout=None, stop_after=None,
                 tag=None, echo=True):
        self.mode = mode
        self.port_arg = port
        self.timeout = timeout if timeout else DEFAULT_TIMEOUT.get(mode, 120)
        self.stop_after = stop_after
        self.echo = echo
        os.makedirs(LOG_DIR, exist_ok=True)
        stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
        self.path = os.path.join(LOG_DIR, f"{tag or mode}_{stamp}.log")
        self.f = open(self.path, "w", buffering=1)
        self.lines = []            # (host_ts, text) of device lines
        self.ser = None
        self.buf = b""
        self.resets = 0
        self.reopens = 0
        self.marker_seen = False
        self._ctl_pos = 0
        # fresh control file for this run
        open(CTL_FILE, "w").close()

    # ---- logging ---------------------------------------------------------
    def _w(self, ts, text):
        self.f.write(f"{iso(ts)} | {text}\n")
        if self.echo:
            print(f"{iso(ts)} | {text}", flush=True)

    def host(self, text):
        self._w(time.time(), "HOST " + text)

    # ---- port handling ---------------------------------------------------
    def _open(self, wait):
        end = time.time() + wait
        while True:
            dev = self.port_arg or find_port()
            if dev:
                try:
                    self.ser = serial.Serial(dev, 115200, timeout=0.05)
                    try:
                        self.ser.dtr = True      # CDC ACM: host must raise DTR
                    except (OSError, serial.SerialException):
                        pass             # e.g. a pty in tests
                    self.buf = b""
                    return dev
                except (serial.SerialException, OSError):
                    self.ser = None
            if time.time() >= end:
                return None
            time.sleep(0.2)

    def _close(self):
        try:
            if self.ser:
                self.ser.close()
        except Exception:
            pass
        self.ser = None

    def _send(self, data):
        try:
            self.ser.write(data)
            self.ser.flush()
            return True
        except (serial.SerialException, OSError):
            return False

    # ---- reading ---------------------------------------------------------
    def _poll_ctl(self):
        try:
            with open(CTL_FILE) as c:
                c.seek(self._ctl_pos)
                for raw in c:
                    if not raw.endswith("\n"):
                        break
                    self._ctl_pos += len(raw)
                    ts, _, text = raw.rstrip("\n").partition("\t")
                    try:
                        self._w(float(ts), "EVENT " + text)
                    except ValueError:
                        pass
        except FileNotFoundError:
            pass

    def _pump(self):
        """Read what's available; return list of completed lines. [] on none.
        Raises IOError when the port vanished."""
        try:
            chunk = self.ser.read(self.ser.in_waiting or 1)
        except (serial.SerialException, OSError, TypeError, AttributeError):
            raise IOError("port lost")
        out = []
        if chunk:
            self.buf += chunk
            while b"\n" in self.buf:
                raw, self.buf = self.buf.split(b"\n", 1)
                text = raw.decode("utf-8", "replace").rstrip("\r")
                out.append((time.time(), text))
        return out

    def _ingest(self, items, end_re):
        for ts, text in items:
            self.lines.append((ts, text))
            self._w(ts, text)
            if text.startswith("### BOOT"):
                self.resets += 1
                self.host("DEVICE RESET (brownout?) boot banner seen")
            if end_re.search(text):
                self.marker_seen = True

    def _drain(self, secs):
        t_end = time.time() + secs
        while time.time() < t_end:
            try:
                self._ingest(self._pump(), re.compile(r"$^"))
            except IOError:
                return

    # ---- run -------------------------------------------------------------
    def run(self):
        if serial is None:
            print("pyserial not installed", file=sys.stderr)
            return 3
        self.host(f"run mode={self.mode} timeout={self.timeout}s stop_after={self.stop_after}")
        dev = self._open(10)
        if not dev:
            self.host("no serial port found")
            return 3
        self.host(f"opened {dev}")

        end_re = re.compile(r"### (DONE|STOPPED) %s\b" % re.escape(self.mode))
        menu_re = re.compile(r"^MENU>")

        # --- handshake: stop whatever is running, wait for the menu ---------
        got_menu = False
        hs_end = time.time() + 15
        last_poke = 0
        while time.time() < hs_end and not got_menu:
            if time.time() - last_poke > 1.0:
                if not self._send(b"x\n"):
                    self._close()
                    self._open(5)
                last_poke = time.time()
            try:
                for ts, text in self._pump():
                    self._w(ts, "(handshake) " + text)
                    if menu_re.match(text):
                        got_menu = True
            except IOError:
                self._close()
                self._open(5)
        if not got_menu:
            self.host("no MENU> after 15 s")
            return 2
        self.host("menu ready")
        self._drain(0.3)

        # --- command ---------------------------------------------------------
        t_cmd = time.time()
        self._send(self.mode.encode())
        self.host(f"sent '{self.mode}'")
        sent_stop = False
        deadline = t_cmd + self.timeout
        lost = False

        while True:
            now = time.time()
            if now > deadline and not (self.stop_after and sent_stop is False):
                self.host("TIMEOUT")
                break
            if self.stop_after and not sent_stop and now - t_cmd >= self.stop_after:
                if self.ser and self._send(b"x"):
                    self.host("sent 'x' (stop-after)")
                    sent_stop = True
                    deadline = max(deadline, now + 20)
            self._poll_ctl()
            if self.ser is None:
                if self._open(0.5):
                    self.reopens += 1
                    self.host("port reopened")
                    lost = False
                continue
            try:
                self._ingest(self._pump(), end_re)
            except IOError:
                if not lost:
                    self.host("port lost (USB re-enumeration?)")
                    lost = True
                self._close()
                time.sleep(0.1)
                continue
            if self.marker_seen:
                break

        self._poll_ctl()
        self.host(f"end marker={'yes' if self.marker_seen else 'NO'} resets={self.resets} reopens={self.reopens}")
        self._close()
        self.f.close()
        return 0 if self.marker_seen else 2


def add_event(text):
    os.makedirs(LOG_DIR, exist_ok=True)
    with open(CTL_FILE, "a") as c:
        c.write(f"{time.time():.3f}\t{text}\n")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("mode", nargs="?", choices=list("tsrlwi"))
    ap.add_argument("--port")
    ap.add_argument("--timeout", type=float)
    ap.add_argument("--stop-after", type=float)
    ap.add_argument("--event", help="append an EVENT line to the running log and exit")
    ap.add_argument("--quiet", action="store_true", help="do not echo lines to stdout")
    a = ap.parse_args()
    if a.event:
        add_event(a.event)
        print(f"{iso(time.time())} EVENT {a.event}")
        return 0
    if not a.mode:
        ap.error("mode required")
    lg = Logger(a.mode, a.port, a.timeout, a.stop_after, echo=not a.quiet)
    rc = lg.run()
    print(f"LOG {lg.path}")
    return rc


if __name__ == "__main__":
    sys.exit(main())
