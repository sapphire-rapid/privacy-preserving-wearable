"""Domain-gap baseline: the existing SisFall-waist LR (firmware/fall_imu/include/fall_model.h, 52 Hz constants:
WIN 104 / STRIDE 26 / CONFIRM 156, thr 0.93, std 0.05, tol 0.2) applied UNCHANGED to the wrist pool at 52 Hz.
No tuning, no cross-validation (nothing is fitted to wrist data), evaluated on every pool trial."""
import os
import re
import sys
import pickle
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import evalcore as E

ROOT = os.path.dirname(HERE)
REPO = os.path.dirname(os.path.dirname(ROOT))
HDR = os.path.join(REPO, "firmware", "fall_imu", "include", "fall_model.h")


def parse_header(path):
    s = open(path).read()

    def arr(name):
        m = re.search(r"%s\[\]\s*=\s*\{([^}]*)\}" % name, s)
        return np.array([float(v.strip().rstrip("f")) for v in m.group(1).split(",") if v.strip()])

    def scal(name):
        return float(re.search(r"%s\s*=\s*([-0-9.eE+]+)f" % name, s).group(1))
    return dict(mean=arr("FALL_MEAN"), scale=arr("FALL_SCALE"), coef=arr("FALL_COEF"), b=scal("FALL_INTERCEPT"),
                thr=scal("FALL_PROB_THR"), std=scal("STILL_STD_THR"),
                win=int(re.search(r"#define WIN_SAMPLES\s+(\d+)", s).group(1)), confirm=int(re.search(r"#define CONFIRM_SAMPLES\s+(\d+)", s).group(1)),
                fs=int(re.search(r"#define SAMPLE_RATE_HZ\s+(\d+)", s).group(1)))


def main():
    h = parse_header(HDR)
    assert (h["fs"], h["win"], h["confirm"]) == (52, 104, 156), h
    ds = pickle.load(open(os.path.join(ROOT, "cache", "ds_52.pkl"), "rb"))
    z = (ds["Xw"] - h["mean"]) / h["scale"] @ h["coef"] + h["b"]
    p = 1.0 / (1.0 + np.exp(-z))
    out = E.outcomes(ds, p, [t["tid"] for t in ds["trials"]], h["thr"], h["std"], meta=dict(model="baseline_sisfall_waist_52"))
    out.to_csv(os.path.join(ROOT, "results", "outcomes_segments_baseline_52.csv"), index=False)
    tr = E.aggregate_trials(out)
    tr.to_csv(os.path.join(ROOT, "results", "outcomes_baseline_52.csv"), index=False)
    summ = E.summarize(tr)
    summ.to_csv(os.path.join(ROOT, "results", "summary_baseline_52.csv"), index=False)
    print("baseline thr=%.2f std=%.2f" % (h["thr"], h["std"]))
    print(summ[summ.metric.isin(["fall_recall_trigger", "fall_recall_confirm", "adl_far_trigger", "adl_far_confirm", "fa_per_hour_trials"])].to_string(index=False))


if __name__ == "__main__":
    main()
