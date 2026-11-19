"""Step 4: nested, subject-grouped evaluation, resumable per outer fold.

  .venv/bin/python -I src/eval_nested.py --model lr --fs 26          # primary
  .venv/bin/python -I src/eval_nested.py --model lr --fs 52
  .venv/bin/python -I src/eval_nested.py --model tree --fs 26
  .venv/bin/python -I src/eval_nested.py --model mlp --fs 26

Outer GroupKFold(5) by subject (WEDA + SmartFallMM pool); inner GroupKFold(3) over the outer-train subjects gives
out-of-fold window probabilities on which (prob threshold, stillness std) are tuned (evalcore.choose_params);
the outer-test subjects are scored once with the parameters chosen without them.  Training windows are augmented
(time-stretch 0.95/1.00/1.05) in training folds only.  Fold results are stored in cache/folds/ and reused on restart.
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
from sklearn.neural_network import MLPClassifier

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import evalcore as E
import features as F

ROOT = os.path.dirname(HERE)
CACHE = os.path.join(ROOT, "cache")
RES = os.path.join(ROOT, "results")
FOLDS = os.path.join(CACHE, "folds")
os.makedirs(FOLDS, exist_ok=True)


class Model:
    """scaler + classifier with predict_proba on raw features."""

    def __init__(self, kind, seed=0):
        self.kind = kind
        self.scaler = StandardScaler() if kind in ("lr", "mlp") else None
        if kind == "lr":
            self.clf = LogisticRegression(class_weight="balanced", max_iter=1000)
        elif kind == "tree":
            self.clf = DecisionTreeClassifier(max_depth=5, class_weight="balanced", random_state=seed)
        elif kind == "mlp":
            self.clf = MLPClassifier(hidden_layer_sizes=(16,), early_stopping=True, n_iter_no_change=5, max_iter=100,
                                     random_state=seed)
        else:
            raise ValueError(kind)

    def fit(self, X, y):
        Xs = self.scaler.fit_transform(X) if self.scaler else X
        if self.kind == "mlp":
            npos = max(int(y.sum()), 1); nneg = len(y) - npos
            sw = np.where(y == 1, len(y) / (2.0 * npos), len(y) / (2.0 * nneg))
            self.clf.fit(Xs, y, sample_weight=sw)
        else:
            self.clf.fit(Xs, y)
        return self

    def proba(self, X):
        Xs = self.scaler.transform(X) if self.scaler else X
        return self.clf.predict_proba(Xs)[:, 1]


def n_params(m):
    if m.kind == "lr":
        return int(m.clf.coef_.size + 1 + 2 * m.scaler.mean_.size)
    if m.kind == "tree":
        t = m.clf.tree_
        return int(t.node_count)      # nodes (each: feature, threshold, children / leaf value)
    return int(sum(w.size for w in m.clf.coefs_) + sum(b.size for b in m.clf.intercepts_) + 2 * m.scaler.mean_.size)


class Ctx:
    def __init__(self, fs):
        self.ds = pickle.load(open(os.path.join(CACHE, "ds_%d.pkl" % fs), "rb"))
        ds = self.ds
        self.tsub = np.array([t["subject"] for t in ds["trials"]])
        self.tr_subj = self.tsub[ds["tr_trial"]]
        self.w_subj = self.tsub[ds["w_trial"]]
        self.base = ds["tr_factor"] == 1.0

    def fit(self, kind, subjects, seed=0):
        m = np.isin(self.tr_subj, list(subjects))
        return Model(kind, seed).fit(self.ds["Xtr"][m], self.ds["ytr"][m])

    def predict(self, model, subjects, p):
        m = np.isin(self.w_subj, list(subjects))
        p[m] = model.proba(self.ds["Xw"][m])
        return p

    def trials_of(self, subjects):
        return [t["tid"] for t in self.ds["trials"] if t["subject"] in set(subjects)]

    def oof_probs(self, kind, subjects, n_splits=3, seed=0):
        """out-of-fold window probabilities for every trial of `subjects` (subject-grouped inner CV)."""
        subjects = np.array(sorted(subjects))
        mb = self.base & np.isin(self.tr_subj, subjects)
        Xb, gb = self.ds["Xtr"][mb], self.tr_subj[mb]
        p = np.full(len(self.ds["Xw"]), np.nan)
        for itr, ite in GroupKFold(n_splits=n_splits).split(Xb, groups=gb):
            held = set(gb[ite]); trn = set(gb[itr])
            self.predict(self.fit(kind, trn, seed), held, p)
        return p


def run_fold(ctx, kind, k, tr_subj, te_subj, std_grid):
    t0 = time.time()
    p_oof = ctx.oof_probs(kind, tr_subj)
    chosen = (E.choose_params(ctx.ds, p_oof, ctx.trials_of(tr_subj), std_grid) if std_grid is not None
              else E.choose_params_trigger(ctx.ds, p_oof, ctx.trials_of(tr_subj)))
    model = ctx.fit(kind, tr_subj)
    p = np.full(len(ctx.ds["Xw"]), np.nan)
    ctx.predict(model, te_subj, p)
    out = E.outcomes(ctx.ds, p, ctx.trials_of(te_subj), chosen["thr"], chosen["std"], meta=dict(fold=k))
    return dict(fold=k, chosen=chosen, outcomes=out, n_params=n_params(model), train_subjects=sorted(tr_subj),
                test_subjects=sorted(te_subj), secs=time.time() - t0)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True, choices=["lr", "tree", "mlp"])
    ap.add_argument("--fs", type=int, default=26, choices=[26, 52])
    ap.add_argument("--folds", type=int, default=5)
    ap.add_argument("--grid", default="spec", choices=["spec", "ext", "trig"], help="spec = std grid {0.05,0.065,0.08}; ext = wider sensitivity grid; trig = tune threshold on trigger-only (no confirm stage)")
    a = ap.parse_args()
    ctx = Ctx(a.fs)
    tag = f"{a.model}_{a.fs}" + ("" if a.grid == "spec" else "_" + a.grid)
    std_grid = {"spec": F.STD_GRID, "ext": F.STD_GRID_EXT, "trig": None}[a.grid]
    subj_all = np.array(sorted(set(ctx.tsub)))
    mb = ctx.base
    Xb, gb = ctx.ds["Xtr"][mb], ctx.tr_subj[mb]
    splits = list(GroupKFold(n_splits=a.folds).split(Xb, groups=gb))
    folds = []
    for k, (itr, ite) in enumerate(splits):
        fp = os.path.join(FOLDS, f"{tag}_fold{k}.pkl")
        if os.path.exists(fp):
            r = pickle.load(open(fp, "rb"))
            print(f"[{tag}] fold {k}: resumed ({r['secs']:.0f}s earlier)  chosen={r['chosen']}", flush=True)
        else:
            r = run_fold(ctx, a.model, k, set(gb[itr]), set(gb[ite]), std_grid)
            pickle.dump(r, open(fp, "wb"))
            print(f"[{tag}] fold {k}: done in {r['secs']:.0f}s  chosen={r['chosen']}", flush=True)
        folds.append(r)
    df = pd.concat([r["outcomes"] for r in folds], ignore_index=True)
    df.to_csv(os.path.join(RES, f"outcomes_segments_{tag}.csv"), index=False)
    tr = E.aggregate_trials(df)
    tr.to_csv(os.path.join(RES, f"outcomes_{tag}.csv"), index=False)
    summ = E.summarize(tr)
    summ.to_csv(os.path.join(RES, f"summary_{tag}.csv"), index=False)
    meta = pd.DataFrame([dict(fold=r["fold"], **r["chosen"], n_params=r["n_params"], secs=r["secs"],
                              n_test_subjects=len(r["test_subjects"])) for r in folds])
    meta.to_csv(os.path.join(RES, f"folds_{tag}.csv"), index=False)
    key = ["fall_recall_trigger", "fall_recall_confirm", "adl_far_confirm", "fa_per_hour_trials"]
    print(summ[summ.metric.isin(key)].to_string(index=False))


if __name__ == "__main__":
    main()
