#!/usr/bin/env python3
import socket
import struct
import threading
import csv
import time
from collections import deque

LISTEN_PORT = 8888
WINDOW_SIZE = 20
CSV_PATH = "walktest_log.csv"

sock = socket.socket(socket.AF_INET6, socket.SOCK_DGRAM)
sock.bind(("::", LISTEN_PORT))
print(f"Listening for HR packets on UDP port {LISTEN_PORT}...")
print("Type a number + Enter anytime to tag subsequent packets with that distance (m).")

state_lock = threading.Lock()
current_distance = None
seq_window = deque(maxlen=WINDOW_SIZE)
last_seq = None
session_id = 0
session_first_seq = None
session_seen = set()

csv_file = open(CSV_PATH, "a", newline="")
csv_writer = csv.writer(csv_file)
if csv_file.tell() == 0:
    csv_writer.writerow(["timestamp", "session_id", "distance_m", "seq", "bpm",
                          "rank", "window_loss_pct", "session_loss_pct", "src_addr"])
csv_file.flush()

def distance_input_thread():
    global current_distance
    while True:
        try:
            line = input()
        except EOFError:
            return
        line = line.strip()
        if not line:
            continue
        try:
            d = float(line)
        except ValueError:
            print(f"  (ignored '{line}', not a number)")
            continue
        with state_lock:
            current_distance = d
        print(f"  >> distance set to {d} m")

threading.Thread(target=distance_input_thread, daemon=True).start()

def clamp(x):
    return max(0.0, min(100.0, x))

while True:
    data, addr = sock.recvfrom(1024)
    if len(data) != 8:
        print(f"[RX] {len(data)} bytes from {addr[0]} (unexpected size)")
        continue

    seq, bpm, rank = struct.unpack("<IHH", data)

    with state_lock:
        # detect a session reset: seq dropped back to 0 after a nonzero last_seq
        if last_seq is not None and seq == 0 and last_seq > 0:
            session_id += 1
            seq_window.clear()
            session_seen.clear()
            session_first_seq = None
            print(f"  -- new session detected (rejoin), session_id={session_id} --")

        last_seq = seq
        seq_window.append(seq)
        session_seen.add(seq)
        if session_first_seq is None:
            session_first_seq = seq

        # windowed loss (recent), deduped
        unique_window = set(seq_window)
        if len(unique_window) >= 2:
            span = max(unique_window) - min(unique_window) + 1
            window_loss = clamp((span - len(unique_window)) / span * 100)
        else:
            window_loss = 0.0

        # cumulative session loss since this session's first packet, deduped
        span_session = seq - session_first_seq + 1
        if span_session > 0:
            session_loss = clamp((span_session - len(session_seen)) / span_session * 100)
        else:
            session_loss = 0.0

        dist = current_distance

    dist_str = f"{dist}m" if dist is not None else "?"
    print(f"[RX] seq={seq} bpm={bpm} rank={rank} dist={dist_str} "
          f"win_loss={window_loss:.1f}% sess_loss={session_loss:.1f}% from {addr[0]}")

    csv_writer.writerow([time.time(), session_id, dist, seq, bpm, rank,
                          f"{window_loss:.1f}", f"{session_loss:.1f}", addr[0]])
    csv_file.flush()

    sock.sendto(b"ACK", addr)
