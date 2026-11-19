#!/usr/bin/env python3
"""
cal_capture.py - record ONE resting orientation for calibrate.py.

  cal_capture.py [--subject S01] [--trial 1] [--seconds 11]

Records with record.py, finds which IMU axis points up from the data (dominant axis and
sign of the mean over the middle 8 s) and stores the CSV as
data/own/<subject>_cal-<xp|xn|yp|yn|zp|zn>_<trial>.csv, so the person placing the board
does not need to know the IMU axis directions.  Refuses (exit 2) when the board was not at
rest (axis std > 10 mg), when the dominant axis is not clearly ~1 g, or when that
orientation already has a file (the old file is kept; the new recording is stored with a
'-dupN' suffix).  Exit codes: 0 stored, 2 refused, other = record.py failure.
"""
import argparse
import os
import statistics as st
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(os.path.dirname(HERE), "data", "own")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--subject", default="S01")
    ap.add_argument("--trial", default="1")
    ap.add_argument("--seconds", type=float, default=11.0)
    ap.add_argument("--port")
    a = ap.parse_args()

    tmp = "calcap"
    cmd = [sys.executable, os.path.join(HERE, "record.py"), a.subject, tmp, a.trial,
           "--duration", str(a.seconds), "--quiet"]
    if a.port:
        cmd += ["--port", a.port]
    r = subprocess.run(cmd, capture_output=True, text=True)
    print(r.stdout.strip())
    if r.returncode != 0:
        print(r.stderr.strip())
        print(f"record.py failed (rc={r.returncode})")
        return r.returncode
    tmp_path = os.path.join(DATA, f"{a.subject}_{tmp}_{a.trial}.csv")

    rows = []
    with open(tmp_path) as f:
        next(f)
        for line in f:
            rows.append([int(v) for v in line.split(",")])
    t0 = rows[0][0]
    mid = [x for x in rows if 1.0 <= (x[0] - t0) / 1e6 < 9.0]
    mean = [st.fmean(x[1 + i] for x in mid) for i in range(3)]
    std = [st.pstdev([x[1 + i] for x in mid]) for i in range(3)]
    dom = max(range(3), key=lambda i: abs(mean[i]))
    label = "xyz"[dom] + ("p" if mean[dom] > 0 else "n")
    print(f"middle-8s mean (mg): x {mean[0]:.1f}  y {mean[1]:.1f}  z {mean[2]:.1f}   "
          f"std max {max(std):.2f} mg   n={len(mid)}")
    print(f"detected: {'+' if mean[dom] > 0 else '-'}{'XYZ'[dom]} axis up  -> {label}")

    problems = []
    if max(std) > 10.0:
        problems.append(f"not at rest (axis std {max(std):.1f} mg > 10)")
    if not 800 < abs(mean[dom]) < 1300:
        problems.append(f"dominant axis {mean[dom]:.0f} mg is not ~1 g")
    others = [abs(mean[i]) for i in range(3) if i != dom]
    if max(others) > 400:
        problems.append(f"board is tilted: off-axis component {max(others):.0f} mg (> 400)")
    if len(mid) < 8 * 40:
        problems.append("too few samples")

    final = os.path.join(DATA, f"{a.subject}_cal-{label}_{a.trial}.csv")
    if os.path.exists(final):
        problems.append(f"orientation {label} already recorded")
        k = 1
        while os.path.exists(os.path.join(DATA, f"{a.subject}_cal-{label}-dup{k}_{a.trial}.csv")):
            k += 1
        final = os.path.join(DATA, f"{a.subject}_cal-{label}-dup{k}_{a.trial}.csv")
    os.replace(tmp_path, final)
    print("stored " + os.path.relpath(final, os.path.dirname(HERE)))
    if problems:
        print("REFUSED: " + "; ".join(problems))
        return 2
    have = sorted(n for n in os.listdir(DATA)
                  if n.startswith(f"{a.subject}_cal-") and "dup" not in n
                  and n.endswith(f"_{a.trial}.csv"))
    print("have: " + " ".join(n.split("_")[1][4:] for n in have) + f"   ({len(have)}/6)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
