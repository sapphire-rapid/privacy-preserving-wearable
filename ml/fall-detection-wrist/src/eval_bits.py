"""Step 5b: ONE-SHOT held-out evaluation of the final LR@26 on BITS (`acg`, 20 -> 26 Hz).  NOT RUN YET.

  .venv/bin/python -I src/eval_bits.py --op trig --rule5 skip --i-understand-this-is-the-single-run
Options (decided BEFORE looking at any BITS result, see REPORT.md §0):
  --op {spec,ext,trig}  operating point from results/final_model.json (or --thr/--std)
  --rule5 {literal,skip}  literal = drop files with |timestamp span - N/20| > 10 % (leaves ~12 files), skip = do not apply it
A lock file results/bits_run.lock makes a second run impossible (delete it only if the first run crashed before writing results).
--selftest runs the same code path on WEDA-FALL pool data (no lock, nothing written to BITS outputs) to validate the plumbing.
Per-fall-type recall uses the INFERRED file-index -> paper-table mapping (fall1..fall8), see DATA_CARD.md section 6.
"""
import os
import sys
import json
import pickle
import argparse
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import evalcore as E
import features as F
from build_dataset import build

ROOT = os.path.dirname(HERE)
RES = os.path.join(ROOT, "results")
CACHE = os.path.join(ROOT, "cache")
FALL_NAMES = {"fall1": "forward fall landing on knee", "fall2": "right fall", "fall3": "left fall", "fall4": "forward fall",
              "fall5": "seated on bed, falling to ground", "fall6": "forward fall, body weight on hand", "fall7": "backward fall from seated",
              "fall8": "grabbing while falling"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--op", default="trig", choices=["spec", "ext", "trig"])
    ap.add_argument("--thr", type=float); ap.add_argument("--std", type=float)
    ap.add_argument("--rule5", default="skip", choices=["literal", "skip"])
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--i-understand-this-is-the-single-run", dest="go", action="store_true")
    a = ap.parse_args()
    lock = os.path.join(RES, "bits_run.lock")
    if not a.selftest:
        if not a.go:
            sys.exit("refusing: pass --i-understand-this-is-the-single-run (BITS may be evaluated exactly once)")
        if os.path.exists(lock):
            sys.exit("refusing: BITS was already evaluated (results/bits_run.lock exists)")
    fm = json.load(open(os.path.join(RES, "final_model.json")))
    op = fm["operating_points"][a.op]
    thr = a.thr if a.thr is not None else op["thr"]
    std = a.std if a.std is not None else op["std"]
    if a.selftest:
        trials = [r for r in pickle.load(open(os.path.join(CACHE, "weda.pkl"), "rb")) if r["subject"] in ("W01", "W02", "W21", "W22")]
        tag = "selftest"
    else:
        trials = pickle.load(open(os.path.join(CACHE, "bits.pkl"), "rb"))
        n0 = len(trials)
        trials = [r for r in trials if r["rule4_pass"]]
        n4 = len(trials)
        if a.rule5 == "literal":
            trials = [r for r in trials if r["rule5_pass"]]
        tag = "bits"
        print(f"BITS files: {n0} -> rule 4: {n4} -> rule 5 ({a.rule5}): {len(trials)}  (falls {sum(r['is_fall'] for r in trials)})")
        open(lock, "w").write(f"op={a.op} thr={thr} std={std} rule5={a.rule5}\n")
    ds = build(trials, 26, train=False)
    z = ((ds["Xw"] - np.array(fm["mean"])) / np.array(fm["scale"])) @ np.array(fm["coef"]) + fm["intercept"]
    p = 1.0 / (1.0 + np.exp(-z))
    seg = E.outcomes(ds, p, [t["tid"] for t in ds["trials"]], thr, std, meta=dict(model="lr_26_final"))
    tr = E.aggregate_trials(seg)
    summ = E.summarize(tr)
    seg.to_csv(os.path.join(RES, f"{tag}_outcomes_segments.csv"), index=False)
    tr.to_csv(os.path.join(RES, f"{tag}_outcomes.csv"), index=False)
    summ.to_csv(os.path.join(RES, f"{tag}_summary.csv"), index=False)
    key = ["fall_recall_trigger", "fall_recall_confirm", "adl_far_trigger", "adl_far_confirm", "fa_per_hour_trials"]
    print(summ[summ.metric.isin(key)].to_string(index=False))
    print(f"operating point: thr={thr} std={std} (mode {a.op}); falls {int(tr.is_fall.sum())}, ADL trials {int((~tr.is_fall).sum())}")


if __name__ == "__main__":
    main()
