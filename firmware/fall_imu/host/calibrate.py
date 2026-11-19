#!/usr/bin/env python3
"""
calibrate.py - six-position accelerometer calibration from `w` recordings.

Input: six CSVs (t_us,ax_mg,ay_mg,az_mg) written by record.py, one per orientation,
named  <subject>_cal-<o>_<trial>.csv  with o in
    xp xn yp yn zp zn     (the named axis points UP: +X up = reads about +1 g on X)
Each segment is ~10 s; only the MIDDLE 8 s (1 s .. 9 s after the first sample, by the
device t_us clock) is used, so hand/placement transients at either end are ignored.

Model (diagonal): calibrated_mg = (raw_mg - offset_mg) / scale   (per axis)
    offset = (raw(+1g) + raw(-1g)) / 2
    scale  = (raw(+1g) - raw(-1g)) / 2000          (dimensionless, 1.0 = ideal)
This assumes gravity = 1000 mg and that each axis was vertical (+-) in its two
orientations.  Cross-axis (misalignment) is not modelled; the residual on the four
orthogonal orientations after calibration is printed as a check of that assumption
and of how vertical the board actually was.

Checks (the run is rejected, exit 2, if any fails): each segment has >= 8 s of data, the
dominant axis and its sign match the label, and per-axis std within the 8 s < 10 mg
(board was at rest).

  calibrate.py [--subject S01] [--trial 1] [--dir data/own]
               [--markdown] [--write-header include/imu_cal.h]
"""
import argparse
import datetime as dt
import math
import os
import statistics as st
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
APP_DIR = os.path.dirname(HERE)
ORIENT = [("xp", 0, +1), ("xn", 0, -1), ("yp", 1, +1), ("yn", 1, -1),
          ("zp", 2, +1), ("zn", 2, -1)]
AXIS = "XYZ"
MID_FROM_S, MID_TO_S = 1.0, 9.0      # the middle 8 s of a 10 s segment
STD_MAX_MG = 10.0


def load(path):
    rows = []
    with open(path) as f:
        next(f)
        for line in f:
            t, x, y, z = (int(v) for v in line.split(","))
            rows.append((t, x, y, z))
    return rows


def segment_stats(rows):
    """mean/std per axis (mg) over the middle 8 s; also n and the span used."""
    t0 = rows[0][0]
    mid = [r for r in rows if MID_FROM_S <= (r[0] - t0) / 1e6 < MID_TO_S]
    if len(mid) < 8 * 40 or (rows[-1][0] - t0) / 1e6 < MID_TO_S:
        raise ValueError(f"segment too short: {len(rows)} rows, "
                         f"{(rows[-1][0] - t0) / 1e6:.1f} s")
    mean = [st.fmean(r[1 + a] for r in mid) for a in range(3)]
    std = [st.pstdev([r[1 + a] for r in mid]) for a in range(3)]
    return {"n": len(mid), "mean": mean, "std": std}


def norm(v):
    return math.sqrt(sum(c * c for c in v))


def calibrate(stats):
    off, scale = [0.0] * 3, [1.0] * 3
    for a in range(3):
        p = stats[f"{AXIS[a].lower()}p"]["mean"][a]
        n = stats[f"{AXIS[a].lower()}n"]["mean"][a]
        off[a] = (p + n) / 2.0
        scale[a] = (p - n) / 2000.0
    return off, scale


def apply(v, off, scale):
    return [(v[a] - off[a]) / scale[a] for a in range(3)]


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--subject", default="S01")
    ap.add_argument("--trial", default="1")
    ap.add_argument("--dir", default=os.path.join(APP_DIR, "data", "own"))
    ap.add_argument("--markdown", action="store_true", help="print REPORT.md tables")
    ap.add_argument("--write-header", metavar="PATH", help="generate imu_cal.h")
    a = ap.parse_args()

    stats, bad = {}, []
    for name, axis, sign in ORIENT:
        path = os.path.join(a.dir, f"{a.subject}_cal-{name}_{a.trial}.csv")
        try:
            s = segment_stats(load(path))
        except (OSError, ValueError) as e:
            bad.append(f"{name}: {e}")
            continue
        s["file"] = os.path.basename(path)
        dom = max(range(3), key=lambda i: abs(s["mean"][i]))
        if dom != axis or (s["mean"][dom] > 0) != (sign > 0):
            bad.append(f"{name}: dominant axis is {'+' if s['mean'][dom] > 0 else '-'}"
                       f"{AXIS[dom]} (mean {s['mean'][dom]:.0f} mg), expected "
                       f"{'+' if sign > 0 else '-'}{AXIS[axis]}")
        if max(s["std"]) > STD_MAX_MG:
            bad.append(f"{name}: not at rest, axis std {max(s['std']):.1f} mg > {STD_MAX_MG}")
        stats[name] = s
    if bad:
        print("REJECTED:")
        for b in bad:
            print("  " + b)
        return 2

    off, scale = calibrate(stats)

    print(f"{'orient':6} {'file':28} {'n':>5} {'mean_x':>9} {'mean_y':>9} {'mean_z':>9} "
          f"{'std max':>8} {'|a| before':>11} {'|a| after':>10}   (mg, g)")
    rows_out = []
    for name, axis, sign in ORIENT:
        s = stats[name]
        cal = apply(s["mean"], off, scale)
        before, after = norm(s["mean"]) / 1000.0, norm(cal) / 1000.0
        rows_out.append((name, s, cal, before, after))
        print(f"{name:6} {s['file']:28} {s['n']:5d} {s['mean'][0]:9.1f} {s['mean'][1]:9.1f} "
              f"{s['mean'][2]:9.1f} {max(s['std']):8.2f} {before:11.4f} {after:10.4f}")
    print()
    for i in range(3):
        print(f"axis {AXIS[i]}: offset {off[i]:+8.2f} mg   scale {scale[i]:.5f} "
              f"({(scale[i] - 1) * 100:+.2f} %)")
    print()
    print("calibrated mean vectors (mg) - the 4 off-axis components are the residual:")
    worst = 0.0
    for name, axis, sign in ORIENT:
        cal = [r for r in rows_out if r[0] == name][0][2]
        res = [cal[i] for i in range(3) if i != axis]
        worst = max(worst, max(abs(v) for v in res))
        print(f"  {name}: x {cal[0]:+8.1f}  y {cal[1]:+8.1f}  z {cal[2]:+8.1f}")
    print(f"worst off-axis residual after calibration: {worst:.1f} mg "
          f"(= {math.degrees(math.asin(min(1.0, worst / 1000.0))):.2f} deg tilt / misalignment)")
    ab = [r[3] for r in rows_out]
    aa = [r[4] for r in rows_out]
    print(f"|a| over the 6 orientations: before {min(ab):.4f}..{max(ab):.4f} g "
          f"(mean {st.fmean(ab):.4f}), after {min(aa):.4f}..{max(aa):.4f} g (mean {st.fmean(aa):.4f})")

    if a.markdown:
        print("\n--- markdown ---")
        print("| orientation | file | n | mean x / y / z (mg) | σ max (mg) | \\|a\\| before (g) | \\|a\\| after (g) |")
        print("|---|---|---|---|---|---|---|")
        for name, s, cal, b, af in rows_out:
            print(f"| {name} | `{s['file']}` | {s['n']} | {s['mean'][0]:.1f} / {s['mean'][1]:.1f} / "
                  f"{s['mean'][2]:.1f} | {max(s['std']):.2f} | {b:.4f} | {af:.4f} |")
        print("\n| axis | offset (mg) | scale | scale error |")
        print("|---|---|---|---|")
        for i in range(3):
            print(f"| {AXIS[i]} | {off[i]:+.2f} | {scale[i]:.5f} | {(scale[i] - 1) * 100:+.2f} % |")

    if a.write_header:
        src = ", ".join(stats[n]["file"] for n, _, _ in ORIENT)
        with open(a.write_header, "w") as f:
            f.write(f"""/*
 * imu_cal.h - six-position calibration of the on-board LSM6DS3TR-C accelerometer.
 * GENERATED by host/calibrate.py ({dt.datetime.now():%Y-%m-%d %H:%M}); NOT used by the
 * firmware yet.  Do not edit by hand.
 *
 * Source recordings (middle 8 s of each 10 s segment): {src}
 *
 * Per axis (X, Y, Z), raw values in mg as printed by the 'w' mode (+-16 g range):
 *     calibrated_mg = (raw_mg - IMU_CAL_OFFSET_MG[axis]) / IMU_CAL_SCALE[axis]
 *     calibrated_g  = calibrated_mg / 1000
 * Diagonal model only (no cross-axis term).  Worst off-axis residual after
 * calibration on the calibration data: {worst:.1f} mg.
 * Valid for this one board; offset/scale drift with temperature.
 */
#ifndef IMU_CAL_H
#define IMU_CAL_H

static const float IMU_CAL_OFFSET_MG[3] = {{ {off[0]:.3f}f, {off[1]:.3f}f, {off[2]:.3f}f }};
static const float IMU_CAL_SCALE[3]     = {{ {scale[0]:.6f}f, {scale[1]:.6f}f, {scale[2]:.6f}f }};

#endif /* IMU_CAL_H */
""")
        print(f"\nWROTE {a.write_header}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
