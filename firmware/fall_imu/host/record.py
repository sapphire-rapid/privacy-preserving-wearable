#!/usr/bin/env python3
"""
record.py - record the firmware's raw 52 Hz log ('w' mode) to a labelled CSV.

  record.py SUBJECT ACTIVITY TRIAL --duration SECONDS [--port DEV]

writes  firmware/fall_imu/data/own/<SUBJECT>_<ACTIVITY>_<TRIAL>.csv   (gitignored)
        columns: t_us,ax_mg,ay_mg,az_mg      (t_us = device ztimer_usec, 32-bit,
        unwrapped here so the CSV is monotonic and starts at the first sample's
        device time)
and the full host-timestamped serial log in logs/rawlog_<ts>.log.

Dropped samples are counted from t_us gaps.  The reference period is the MEDIAN
interval of the run itself (the LSM6DS3TR-C "52 Hz" setting really runs at ~54.4 Hz
on this board, so the nominal 19.23 ms would undercount); a gap of dt counts as
round(dt/period)-1 missing samples when dt > 1.5 periods.  A
"### BOOT" banner or a backwards t_us step means the board reset (brownout): the
CSV is NOT written and the exit code is 4 - redo the run.
Exit codes: 0 ok, 1 dropped samples (CSV still written), 2 logger timeout,
3 no port, 4 reset detected.
"""
import argparse
import os
import re
import statistics
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import serial_log  # noqa: E402

NOMINAL_PERIOD_US = 1e6 / 52.0   # only the fallback for runs with < 3 intervals
DATA_DIR = os.path.join(serial_log.APP_DIR, "data", "own")
ROW = re.compile(r"^(\d+),(-?\d+),(-?\d+),(-?\d+)$")


def analyse(rows):
    """rows: list of (t_us32, x, y, z) in arrival order -> dict of stats."""
    out = {"n": len(rows), "dropped": 0, "gaps": [], "reset": False,
           "max_dt_us": 0, "mean_dt_us": 0.0, "median_dt_us": 0.0,
           "rate_hz": 0.0, "span_s": 0.0, "t_unwrapped": [0] * len(rows)}
    if len(rows) < 2:
        return out
    dts = []
    for i in range(1, len(rows)):
        d = rows[i][0] - rows[i - 1][0]
        if d < 0:
            if d > -(1 << 31):          # backwards step, not a 32-bit wrap
                out["reset"] = True
                d = 0
            else:
                d += 1 << 32
        dts.append(d)
    period = statistics.median(dts) if len(dts) >= 3 else NOMINAL_PERIOD_US
    t_unwrapped = [0]
    for i, d in enumerate(dts, start=1):
        t_unwrapped.append(t_unwrapped[-1] + d)
        if d > 1.5 * period:
            miss = int(round(d / period)) - 1
            out["dropped"] += miss
            out["gaps"].append((i, d, miss))
        out["max_dt_us"] = max(out["max_dt_us"], d)
    out["span_s"] = t_unwrapped[-1] / 1e6
    out["mean_dt_us"] = t_unwrapped[-1] / (len(rows) - 1)
    out["median_dt_us"] = period
    out["rate_hz"] = (len(rows) - 1) / out["span_s"] if out["span_s"] else 0.0
    out["t_unwrapped"] = t_unwrapped
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("subject")
    ap.add_argument("activity")
    ap.add_argument("trial")
    ap.add_argument("--duration", type=float, required=True, help="seconds to record")
    ap.add_argument("--port")
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args()
    for part in (a.subject, a.activity, a.trial):
        if not re.fullmatch(r"[A-Za-z0-9\-]+", part):
            ap.error("subject/activity/trial: letters, digits and '-' only")

    lg = serial_log.Logger("w", a.port, timeout=a.duration + 30, stop_after=a.duration,
                           tag="rawlog", echo=not a.quiet)
    rc = lg.run()
    if rc == 3:
        return 3

    rows = []
    summary = None
    for _, text in lg.lines:
        m = ROW.match(text)
        if m:
            rows.append(tuple(int(g) for g in m.groups()))
        elif text.startswith("RAWLOG samples="):
            summary = text
    st = analyse(rows)
    reset = st["reset"] or lg.resets > 0
    print(f"LOG {lg.path}")
    print(f"samples={st['n']} span_s={st['span_s']:.3f} rate_hz={st['rate_hz']:.3f} "
          f"mean_dt_ms={st['mean_dt_us']/1000:.3f} median_dt_ms={st['median_dt_us']/1000:.3f} "
          f"max_dt_ms={st['max_dt_us']/1000:.3f} dropped={st['dropped']} "
          f"gaps={len(st['gaps'])} resets={lg.resets} reopens={lg.reopens}")
    if summary:
        print("firmware: " + summary)
    for i, d, miss in st["gaps"][:10]:
        print(f"  gap at row {i}: {d/1000:.2f} ms (= {miss} missing)")
    if reset:
        print("RESET/BROWNOUT detected - not writing CSV, redo the run")
        return 4
    if rc == 2 or st["n"] == 0:
        print("logger timeout / no data - not writing CSV")
        return 2

    os.makedirs(DATA_DIR, exist_ok=True)
    path = os.path.join(DATA_DIR, f"{a.subject}_{a.activity}_{a.trial}.csv")
    with open(path, "w") as f:
        f.write("t_us,ax_mg,ay_mg,az_mg\n")
        for (t, x, y, z), tu in zip(rows, st["t_unwrapped"]):
            f.write(f"{tu},{x},{y},{z}\n")
    print(f"WROTE {path}")
    return 0 if st["dropped"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
