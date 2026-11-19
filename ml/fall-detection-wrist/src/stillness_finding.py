"""Post-impact stillness as a FINDING (no recall target; stillness is the long-lie / U3 stage, not part of fall detection).

For every fall trial (26 Hz, |a| in g) with peak p = argmax|a|: the trial 'reaches stillness within T s' iff some start s in [p, p + T] has the
following L seconds of |a| still (population std < std_thr and |mean - 1| < 0.2).  A trial is counted for horizon T only if it has
>= T + L seconds of data after the peak (so that every start up to T can be evaluated; a trial without enough data is not counted as 'not still').
L = 3 s is the placeholder confirm length (std 0.08, tol 0.2); L = 1 s and std 0.05 / 0.12 are sensitivity rows.
Writes results/stillness_finding.csv and results/stillness_finding.md.
"""
import os
import sys
import pickle
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import features as F

ROOT = os.path.dirname(HERE)
RES = os.path.join(ROOT, "results")
CACHE = os.path.join(ROOT, "cache")
FS = 26
HORIZONS = (3, 5, 10)


def time_to_still(m, p, T, L, std_thr, tol=F.MEAN_TOL):
    """-> (evaluable, reached, first_start_s) for horizon T (s) and still-segment length L (s)."""
    nL = int(L * FS)
    last_start = p + int(T * FS)
    if last_start + nL > len(m):
        return False, False, np.nan
    starts = np.arange(p, last_start + 1)
    idx = starts[:, None] + np.arange(nL)[None, :]
    seg = m[idx]
    ok = (seg.std(1) < std_thr) & (np.abs(seg.mean(1) - 1.0) < tol)
    if ok.any():
        return True, True, float((starts[np.argmax(ok)] - p) / FS)
    return True, False, np.nan


def main():
    rows = []
    for name in ("weda", "sfmm"):
        for r in pickle.load(open(os.path.join(CACHE, name + ".pkl"), "rb")):
            if not r["is_fall"]:
                continue
            m = F.mag(r["x26"].astype(np.float64))
            p = int(np.argmax(m))
            for L in (3, 1):
                for std in (0.08, 0.05, 0.12):
                    for T in HORIZONS:
                        ev, reached, t0 = time_to_still(m, p, T, L, std)
                        rows.append(dict(dataset=r["dataset"], trial=r["trial_id"], L=L, std=std, T=T, evaluable=ev, reached=reached, t_first=t0, post_s=(len(m) - 1 - p) / FS))
    df = pd.DataFrame(rows)
    out = []
    for (L, std, T, ds), g in df.groupby(["L", "std", "T", "dataset"]):
        e = g[g.evaluable]
        out.append(dict(L_s=L, std=std, T_s=T, dataset=ds, falls=len(g), enough_data=len(e), reached=int(e.reached.sum()),
                        frac=float(e.reached.mean()) if len(e) else np.nan, median_time_to_still_s=float(e[e.reached].t_first.median()) if e.reached.any() else np.nan))
    o = pd.DataFrame(out)
    pooled = []
    for (L, std, T), g in df.groupby(["L", "std", "T"]):
        e = g[g.evaluable]
        pooled.append(dict(L_s=L, std=std, T_s=T, dataset="pooled", falls=len(g), enough_data=len(e), reached=int(e.reached.sum()),
                           frac=float(e.reached.mean()) if len(e) else np.nan, median_time_to_still_s=float(e[e.reached].t_first.median()) if e.reached.any() else np.nan))
    o = pd.concat([o, pd.DataFrame(pooled)], ignore_index=True).sort_values(["L_s", "std", "dataset", "T_s"], ascending=[False, True, True, True])
    o.to_csv(os.path.join(RES, "stillness_finding.csv"), index=False)

    def block(L, std):
        L_ = ["| dataset | horizon | falls with enough post-peak data (≥ T+L s) / all falls | reached stillness within T | median time to stillness (s) |", "|---|---|---|---|---|"]
        for ds in ("WEDA", "SFMM", "pooled"):
            for T in HORIZONS:
                r = o[(o.L_s == L) & (o["std"] == std) & (o.dataset == ds) & (o.T_s == T)].iloc[0]
                frac = f"{r.frac*100:.1f}% ({r.reached}/{r.enough_data})" if r.enough_data else "n/a (no trial has enough data)"
                med = f"{r.median_time_to_still_s:.2f}" if np.isfinite(r.median_time_to_still_s) else "–"
                L_.append(f"| {ds} | {T} s | {r.enough_data}/{r.falls} | {frac} | {med} |")
        return "\n".join(L_)
    md = ["# Post-impact stillness (finding; not a detection criterion)\n",
          "Fall trials with peak p = argmax|a|; 'reaches stillness within T s' = some start in [p, p+T] is followed by L s of |a| with std < thr and |mean − 1| < 0.2. "
          "Only trials with ≥ T + L s of data after the peak are counted (others cannot be judged).\n",
          "## Placeholder long-lie setting: L = 3 s, std < 0.08, |mean−1| < 0.2\n", block(3, 0.08),
          "\n## Sensitivity: L = 3 s, std < 0.05\n", block(3, 0.05), "\n## Sensitivity: L = 3 s, std < 0.12\n", block(3, 0.12),
          "\n## Sensitivity: L = 1 s, std < 0.08\n", block(1, 0.08)]
    open(os.path.join(RES, "stillness_finding.md"), "w").write("\n".join(md) + "\n")
    print(block(3, 0.08))


if __name__ == "__main__":
    main()
