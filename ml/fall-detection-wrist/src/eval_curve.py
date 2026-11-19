"""Trigger-only operating curves, nested subject-grouped CV (outer GroupKFold(5), inner GroupKFold(3)), resumable per fold.

  .venv/bin/python -I src/eval_curve.py --ds pool26 --models acc9_lr                       # item 2: current acc-only LR@26 on the full pool
  .venv/bin/python -I src/eval_curve.py --ds v3W --models acc9_lr gyro15_lr l1sel_lr gyro15_tree
  .venv/bin/python -I src/eval_curve.py --ds v3P --models acc9_lr gyro15_lr l1sel_lr gyro15_tree

Thresholds (0.001 grid) are chosen on out-of-fold probabilities of the outer-train subjects for recall targets 80/85/90/95 %:
the threshold with recall >= target on ALL falls and the lowest trigger-only ADL false-alarm rate (ties -> larger threshold);
the outer-test subjects are scored once.  Stillness plays no role.  `l1sel_lr` = L1-LR feature selection (C chosen in the
inner folds by the mean ADL false-alarm rate over the four targets, selection redone inside every inner fold) followed by a
plain L2 LR on the selected columns.
"""
import os
import sys
import time
import pickle
import argparse
import numpy as np
import pandas as pd
from sklearn.model_selection import GroupKFold
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import LogisticRegression
from sklearn.tree import DecisionTreeClassifier

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import evalcore as E
import features as F
import wrist_io as W

ROOT = os.path.dirname(HERE)
CACHE = os.path.join(ROOT, "cache")
RES = os.path.join(ROOT, "results")
CF = os.path.join(CACHE, "curve")
os.makedirs(CF, exist_ok=True)
TARGETS = (0.80, 0.85, 0.90, 0.95)
C_GRID = (0.003, 0.01, 0.03, 0.1, 1.0)
DSFILE = {"pool26": "ds_26.pkl", "v3W": "ds_v3W_26.pkl", "v3P": "ds_v3P_26.pkl"}
NAMES = {**{"F%02d" % i: n for i, n in enumerate(["fwd fall walking (slip)", "lateral fall walking (slip)", "back fall walking (slip)", "fwd fall walking (trip)",
                                                  "back fall trying to sit", "fwd fall sitting (faint)", "back fall sitting (faint)", "lateral fall sitting (faint)"], 1)},
         "D01": "walking", "D02": "jogging", "D03": "stairs up/down", "D04": "sit-wait-stand", "D05": "sit, try to rise, collapse into chair",
         "D06": "crouch / tie shoes", "D07": "stumble while walking", "D08": "gentle jump", "D09": "hit table with hand", "D10": "clapping", "D11": "open/close door",
         **{"A%02d" % k: v for k, v in W.SFMM_ACTIVITY.items()}}


class Plain:
    """scaler + LR / tree on a column subset."""

    def __init__(self, kind, cols):
        self.kind, self.cols = kind, list(cols)
        self.scaler = StandardScaler() if kind == "lr" else None
        self.clf = LogisticRegression(class_weight="balanced", max_iter=2000) if kind == "lr" else DecisionTreeClassifier(max_depth=5, class_weight="balanced", random_state=0)

    def fit(self, X, y):
        X = X[:, self.cols]
        self.clf.fit(self.scaler.fit_transform(X) if self.scaler else X, y)
        return self

    def proba(self, X):
        X = X[:, self.cols]
        return self.clf.predict_proba(self.scaler.transform(X) if self.scaler else X)[:, 1]


class L1Sel:
    """L1-LR (balanced) selects columns; then a plain L2 LR on them."""

    def __init__(self, C, cols):
        self.C, self.cols = C, list(cols)

    def fit(self, X, y):
        X = X[:, self.cols]
        sc = StandardScaler().fit(X)
        l1 = LogisticRegression(penalty="l1", solver="liblinear", C=self.C, class_weight="balanced", max_iter=300)
        l1.fit(sc.transform(X), y)
        keep = np.where(np.abs(l1.coef_[0]) > 1e-8)[0]
        if len(keep) == 0:
            keep = np.array([int(np.argmax(np.abs(l1.coef_[0])))])
        self.keep = [self.cols[i] for i in keep]
        self.sel_idx = list(keep)
        Xs = X[:, self.sel_idx]
        self.sc2 = StandardScaler().fit(Xs)
        self.lr = LogisticRegression(class_weight="balanced", max_iter=2000).fit(self.sc2.transform(Xs), y)
        return self

    def proba(self, X):
        Xs = X[:, self.cols][:, self.sel_idx]
        return self.lr.predict_proba(self.sc2.transform(Xs))[:, 1]


class Data:
    def __init__(self, name):
        self.ds = pickle.load(open(os.path.join(CACHE, DSFILE[name]), "rb"))
        ds = self.ds
        self.tsub = np.array([t["subject"] for t in ds["trials"]])
        self.tr_subj = self.tsub[ds["tr_trial"]]
        self.w_subj = self.tsub[ds["w_trial"]]
        self.base = ds["tr_factor"] == 1.0
        self.nfeat = ds["Xw"].shape[1]

    def trials_of(self, subjects):
        ss = set(subjects)
        return [t["tid"] for t in self.ds["trials"] if t["subject"] in ss]

    def fit(self, make, subjects):
        m = np.isin(self.tr_subj, list(subjects))
        return make().fit(self.ds["Xtr"][m], self.ds["ytr"][m])

    def predict(self, model, subjects, p):
        m = np.isin(self.w_subj, list(subjects))
        p[m] = model.proba(self.ds["Xw"][m])
        return p

    def oof(self, make, subjects, n_splits=3):
        subjects = np.array(sorted(subjects))
        mb = self.base & np.isin(self.tr_subj, subjects)
        Xb, gb = self.ds["Xtr"][mb], self.tr_subj[mb]
        p = np.full(len(self.ds["Xw"]), np.nan)
        for itr, ite in GroupKFold(n_splits=n_splits).split(Xb, groups=gb):
            self.predict(self.fit(make, set(gb[itr])), set(gb[ite]), p)
        return p


def model_factories(spec, nfeat):
    acc, allc = list(range(9)), list(range(nfeat))
    if spec == "acc9_lr":
        return {None: lambda: Plain("lr", acc)}
    if spec == "gyro15_lr":
        return {None: lambda: Plain("lr", allc)}
    if spec == "gyro15_tree":
        return {None: lambda: Plain("tree", allc)}
    if spec == "acc9_tree":
        return {None: lambda: Plain("tree", acc)}
    if spec == "l1sel_lr":
        return {C: (lambda C=C: L1Sel(C, allc)) for C in C_GRID}
    raise ValueError(spec)


def run_fold(D, spec, k, tr_subj, te_subj):
    t0 = time.time()
    tids = D.trials_of(tr_subj)
    facts = model_factories(spec, D.nfeat)
    best = None
    for key, make in facts.items():
        p_oof = D.oof(make, tr_subj)
        ops = {t: E.choose_params_trigger(D.ds, p_oof, tids, target=t) for t in TARGETS}
        crit = float(np.mean([ops[t]["far"] for t in TARGETS]))
        if best is None or crit < best[0] - 1e-12:
            best = (crit, key, make, ops)
    crit, key, make, ops = best
    model = D.fit(make, tr_subj)
    p = np.full(len(D.ds["Xw"]), np.nan)
    D.predict(model, te_subj, p)
    outs = []
    for t in TARGETS:
        o = E.outcomes(D.ds, p, D.trials_of(te_subj), ops[t]["thr"], 0.08, meta=dict(fold=k, target=t, inner_recall=ops[t]["recall"], inner_far=ops[t]["far"], feasible=ops[t]["feasible"]))
        outs.append(o)
    sel = getattr(model, "keep", None)
    return dict(fold=k, C=key, crit=crit, outcomes=pd.concat(outs, ignore_index=True), selected=sel, secs=time.time() - t0,
                thr={t: ops[t]["thr"] for t in TARGETS})


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ds", required=True, choices=list(DSFILE))
    ap.add_argument("--models", nargs="+", required=True)
    a = ap.parse_args()
    D = Data(a.ds)
    mb = D.base
    Xb, gb = D.ds["Xtr"][mb], D.tr_subj[mb]
    splits = list(GroupKFold(n_splits=5).split(Xb, groups=gb))
    for spec in a.models:
        tag = f"{a.ds}_{spec}"
        folds = []
        for k, (itr, ite) in enumerate(splits):
            fp = os.path.join(CF, f"{tag}_fold{k}.pkl")
            if os.path.exists(fp):
                r = pickle.load(open(fp, "rb")); print(f"[{tag}] fold {k}: resumed", flush=True)
            else:
                r = run_fold(D, spec, k, set(gb[itr]), set(gb[ite]))
                pickle.dump(r, open(fp, "wb"))
                print(f"[{tag}] fold {k}: {r['secs']:.0f}s C={r['C']} thr={ {t: round(v, 3) for t, v in r['thr'].items()} } selected={r['selected']}", flush=True)
            folds.append(r)
        seg = pd.concat([r["outcomes"] for r in folds], ignore_index=True)
        sums, trs = [], []
        for t in TARGETS:
            tr = E.aggregate_trials(seg[seg.target == t].drop(columns=["target"]))
            tr["target"] = t
            trs.append(tr)
            s = E.summarize(tr); s.insert(0, "target", t); sums.append(s)
        pd.concat(trs, ignore_index=True).to_csv(os.path.join(RES, f"curve_{tag}_outcomes.csv"), index=False)
        pd.concat(sums, ignore_index=True).to_csv(os.path.join(RES, f"curve_{tag}_summary.csv"), index=False)
        sel = pd.DataFrame([dict(fold=r["fold"], C=r["C"], selected=" ".join(F.FEATURE_NAMES_V3[i] for i in r["selected"]) if r["selected"] is not None else "",
                                 **{f"thr@{int(t*100)}": r["thr"][t] for t in TARGETS}) for r in folds])
        sel.to_csv(os.path.join(RES, f"curve_{tag}_folds.csv"), index=False)
        g = pd.concat(sums, ignore_index=True)
        print(g[g.metric.isin(["fall_recall_trigger", "adl_far_trigger", "fa_per_hour_trigger_trials"])].pivot(index="target", columns="metric", values="value").round(3).to_string())


if __name__ == "__main__":
    main()
