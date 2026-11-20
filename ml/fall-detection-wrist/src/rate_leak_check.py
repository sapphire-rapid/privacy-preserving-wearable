"""Decision 1 proof: the class-dependent WEDA source rate (falls ~39.8 Hz, ADL ~49.7 Hz) cannot leak at 26 Hz.
For every WEDA ADL trial: direct path  (per-trial linear axis @~49.7 Hz -> 26 Hz)
                           vs  two-step  (-> 39.8 Hz -> 26 Hz).
All sliding windows (2 s / 0.5 s) are featurised on both paths and compared window by window.
rel diff = |a - b| / max(|b|, floor_j); floors: 0.01 g (or g/sample) for magnitude features, 1 sample for count_low, 1 deg for tilt.
"""
import os
import sys
import json
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import wrist_io as W
import preprocess as P
import features as F

RES = os.path.join(os.path.dirname(HERE), "results")
FLOOR = np.array([0.01, 0.01, 0.01, 0.01, 0.01, 0.01, 0.01, 1.0, 1.0])
FS_LOW = 39.8


def main():
    A, B = [], []
    n_tr = 0
    for tr in W.weda_trials("50Hz"):
        if tr["is_fall"]:
            continue
        t, a = W.load_weda(tr["path"])
        g = a / W.G
        fs = (len(t) - 1) / float(t[-1] - t[0])
        direct, _ = P.resample_to(g, fs, 26)
        low, _ = P.resample_to(g, fs, FS_LOW)
        two, _ = P.resample_to(low, FS_LOW, 26)
        n = min(len(direct), len(two))
        st = F.sliding_starts(n, F.CFG26)
        if len(st) == 0:
            continue
        A.append(F.window_features(direct[:n], st, F.CFG26))
        B.append(F.window_features(two[:n], st, F.CFG26))
        n_tr += 1
    A = np.vstack(A); B = np.vstack(B)
    rel = np.abs(A - B) / np.maximum(np.abs(A), FLOOR)
    out = {"adl_trials": n_tr, "windows": int(len(A)), "features": {}}
    lines = ["| feature | median rel diff | 99th pct | max rel diff |", "|---|---|---|---|"]
    for j, nme in enumerate(F.FEATURE_NAMES):
        med, p99, mx = float(np.median(rel[:, j])), float(np.percentile(rel[:, j], 99)), float(rel[:, j].max())
        out["features"][nme] = dict(median=med, p99=p99, max=mx)
        lines.append(f"| {nme} | {med:.2e} | {p99:.2e} | {mx:.2e} |")
    out["table_md"] = "\n".join(lines)
    json.dump(out, open(os.path.join(RES, "rate_leak_check.json"), "w"), indent=1)
    print(f"WEDA ADL trials: {n_tr}, windows: {len(A)}")
    print(out["table_md"])


if __name__ == "__main__":
    main()
