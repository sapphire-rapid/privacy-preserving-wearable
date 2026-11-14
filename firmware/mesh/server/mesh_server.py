#!/usr/bin/env python3
"""
mesh_server.py - Pi4 sink for the wearable RPL mesh.

Receives 8-byte packets {uint32 seq, uint16 bpm, uint16 rank} (little-endian)
on UDP 8888 from every node and replies to the sender's port with
b"ACK" + uint32 seq (7 bytes) - the format mesh_node checks for.

State (loss, sessions) is kept PER SOURCE ADDRESS, so the HR node and the relay
heartbeats never corrupt each other's numbers.

Type a number + Enter to tag following rows with a distance (metres) for
walk tests. Type 't' + Enter to print the per-node table. Any other text
(e.g. "relay2 off") is logged as an EVENT row with a timestamp, for measuring
recovery times.
"""
import csv
import socket
import struct
import sys
import threading
import time
from collections import deque

LISTEN_PORT = 8888
WINDOW = 20
CSV_PATH = "mesh_log.csv"
RANK_PER_HOP = 256          # CONFIG_GNRC_RPL_DEFAULT_MIN_HOP_RANK_INCREASE


class Node:
    def __init__(self, addr):
        self.addr = addr
        self.short = addr.split(":")[-1] or addr   # last group as a short id
        self.session = 0
        self.last_seq = None
        self.first_seq = None
        self.seen = set()
        self.window = deque(maxlen=WINDOW)
        self.rank = 0
        self.bpm = 0
        self.last_rx = 0.0
        self.rx = 0

    def update(self, seq, bpm, rank):
        new_session = False
        # node rebooted: seq went backwards
        if self.last_seq is not None and seq < self.last_seq:
            self.session += 1
            self.first_seq = None
            self.seen.clear()
            self.window.clear()
            new_session = True
        if self.first_seq is None:
            self.first_seq = seq
        self.last_seq = seq
        self.seen.add(seq)
        self.window.append(seq)
        self.rank, self.bpm = rank, bpm
        self.last_rx = time.time()
        self.rx += 1
        return new_session

    def window_loss(self):
        u = set(self.window)
        if len(u) < 2:
            return 0.0
        span = max(u) - min(u) + 1
        return max(0.0, min(100.0, (span - len(u)) / span * 100))

    def session_loss(self):
        span = self.last_seq - self.first_seq + 1
        return max(0.0, min(100.0, (span - len(self.seen)) / span * 100)) if span > 0 else 0.0

    def hops(self):
        return max(1, self.rank // RANK_PER_HOP - 1) if self.rank else 0

    def role(self):
        return "HR" if self.bpm else "relay/hb"


nodes = {}
lock = threading.Lock()
distance = None
writer = None
csv_file = None


def print_table():
    with lock:
        print(f"\n{'node':>8} {'role':>8} {'rank':>5} {'hops':>4} {'rx':>6} "
              f"{'win%':>6} {'sess%':>6} {'age_s':>6}")
        for n in nodes.values():
            print(f"{n.short:>8} {n.role():>8} {n.rank:>5} {n.hops():>4} {n.rx:>6} "
                  f"{n.window_loss():>6.1f} {n.session_loss():>6.1f} "
                  f"{time.time() - n.last_rx:>6.1f}")
        print()


def stdin_thread():
    global distance
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        if line.lower() == "t":
            print_table()
            continue
        try:
            d = float(line)
        except ValueError:
            with lock:
                writer.writerow([f"{time.time():.3f}", "EVENT", "", distance, "", "", "",
                                 "", "", "", line])
                csv_file.flush()
            print(f"  >> EVENT logged: {line}  ({time.strftime('%H:%M:%S')})")
            continue
        with lock:
            distance = d
        print(f"  >> distance set to {d} m")


def main():
    sock = socket.socket(socket.AF_INET6, socket.SOCK_DGRAM)
    sock.bind(("::", LISTEN_PORT))
    print(f"mesh_server listening on [::]:{LISTEN_PORT}  (number=distance tag, t=table)")

    global writer, csv_file
    f = csv_file = open(CSV_PATH, "a", newline="")
    w = writer = csv.writer(f)
    if f.tell() == 0:
        w.writerow(["timestamp", "src_addr", "session", "distance_m", "seq", "bpm",
                    "rank", "hops", "window_loss_pct", "session_loss_pct", "event"])
        f.flush()

    threading.Thread(target=stdin_thread, daemon=True).start()

    while True:
        data, addr = sock.recvfrom(1024)
        src = addr[0]
        if len(data) != 8:
            print(f"[RX] {len(data)} bytes from {src} (unexpected size, ignored)")
            continue
        seq, bpm, rank = struct.unpack("<IHH", data)

        # reply first: keeps RTT low and independent of logging
        sock.sendto(b"ACK" + struct.pack("<I", seq), addr)

        with lock:
            n = nodes.get(src)
            if n is None:
                n = nodes[src] = Node(src)
                print(f"  ++ new node {src}")
            if n.update(seq, bpm, rank):
                print(f"  -- node {n.short} restarted, session {n.session} --")
            wl, sl, d = n.window_loss(), n.session_loss(), distance
            row = [f"{time.time():.3f}", src, n.session, d, seq, bpm, rank, n.hops(),
                   f"{wl:.1f}", f"{sl:.1f}"]

        dist = f"{d}m" if d is not None else "?"
        print(f"[RX {n.short:>4} {n.role():>8}] seq={seq} bpm={bpm} rank={rank} "
              f"hops={n.hops()} win_loss={wl:.1f}% sess_loss={sl:.1f}% dist={dist}")
        with lock:
            w.writerow(row + [""])
            f.flush()


if __name__ == "__main__":
    main()
