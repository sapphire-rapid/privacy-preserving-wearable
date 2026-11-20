"""Step 5a: final LR@26 Hz on the WHOLE train pool (WEDA + SmartFallMM, augmented), operating points chosen by
5-fold subject-grouped CV on the pool (same tuning code as the nested evaluation).  BITS is not touched here.
Writes results/final_model.json (scaler, coefficients, operating points for the three tuning modes)."""
import os
import sys
import json
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import evalcore as E
import features as F
from eval_nested import Ctx

ROOT = os.path.dirname(HERE)
RES = os.path.join(ROOT, "results")


def main():
    ctx = Ctx(26)
    subj = set(ctx.tsub)
    p_oof = ctx.oof_probs("lr", subj, n_splits=5)
    tids = ctx.trials_of(subj)
    ops = dict(spec=E.choose_params(ctx.ds, p_oof, tids, F.STD_GRID),
               ext=E.choose_params(ctx.ds, p_oof, tids, F.STD_GRID_EXT),
               trig=E.choose_params_trigger(ctx.ds, p_oof, tids))
    for t in (0.80, 0.85, 0.90, 0.95):       # trigger-only operating points for the recall targets (pooled 5-fold CV thresholds)
        ops["trig%d" % round(t * 100)] = E.choose_params_trigger(ctx.ds, p_oof, tids, target=t)
    m = ctx.fit("lr", subj)
    out = dict(fs=26, n_subjects=len(subj), n_train_windows=int(len(ctx.ds["ytr"])), n_pos=int(ctx.ds["ytr"].sum()),
               mean=m.scaler.mean_.tolist(), scale=m.scaler.scale_.tolist(), coef=m.clf.coef_[0].tolist(),
               intercept=float(m.clf.intercept_[0]), mean_tol=F.MEAN_TOL, operating_points=ops)
    json.dump(out, open(os.path.join(RES, "final_model.json"), "w"), indent=1)
    for k, v in ops.items():
        print(k, v)
    print("coef", np.round(out["coef"], 3).tolist())


if __name__ == "__main__":
    main()
