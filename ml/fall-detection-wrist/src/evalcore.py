"""Evaluation core (mirrors eval_confirm_nested.py with the Step-4 modifications).

Trial logic
  * window probabilities p_w for every sliding window of a trial (stride 0.5 s, 2 s window)
  * TRIGGER-ONLY: trial detected iff any window has p_w >= thr
  * CONFIRMED  : window w is confirmed iff p_w >= thr AND the 3 s of |a| right after the window is still
                 (population std < std_thr and |mean-1| < 0.2) -- the confirm segment must lie inside the recording
                 ("evaluable"); trial detected / ADL false alarm iff any window is confirmed.
  * a fall is *eligible* for 'with confirm' iff some window containing the impact peak is evaluable
    (this implies >= 3 s of data after the peak; reported next to the plain >=3 s count)
  * tuning (inner CV, outer-train subjects only): over THR_GRID x STD_GRID, keep combos with recall >= 0.95 on eligible
    falls, pick the lowest ADL false-alarm rate (ties -> larger threshold, as in the reference).
  * ADL file with several segments: alarmed iff any segment is.
"""
import numpy as np
import pandas as pd
import features as F

THR_GRID = np.round(np.arange(0.0, 1.0 + 1e-9, 0.001), 3)
TARGET_RECALL = 0.95


# ---------------------------------------------------------------- window / trial scoring
def still_flags(ds, std_thr):
    return ds["ev"] & (ds["sd"] < std_thr) & (np.abs(ds["mu"] - 1.0) < F.MEAN_TOL)


def trial_scores(ds, p, trial_ids, std_thr):
    """per trial -> (score_trigger, score_confirmed, score_confirmed_conservative); score = max p over qualifying windows, -1 if none."""
    still = still_flags(ds, std_thr)
    cons = still | ~ds["ev"]
    out = {}
    for t in trial_ids:
        tr = ds["trials"][t]
        sl = slice(tr["off"], tr["off"] + tr["cnt"])
        pp = p[sl]
        s1 = float(pp.max())
        s2 = float(pp[still[sl]].max()) if still[sl].any() else -1.0
        s3 = float(pp[cons[sl]].max()) if cons[sl].any() else -1.0
        out[t] = (s1, s2, s3)
    return out


def _group_key(tr):
    return tr["trial_id"]


def choose_params_trigger(ds, p, trial_ids, std_default=0.08, target=TARGET_RECALL):
    """Trigger-only tuning (no confirm stage): >=95 % recall over ALL falls at the lowest trigger-only ADL false-alarm rate."""
    falls = [t for t in trial_ids if ds["trials"][t]["is_fall"]]
    adl_groups = {}
    for t in trial_ids:
        tr = ds["trials"][t]
        if not tr["is_fall"]:
            adl_groups.setdefault(tr["trial_id"], []).append(t)
    sc = trial_scores(ds, p, falls + [t for g in adl_groups.values() for t in g], std_default)
    fs_ = np.array([sc[t][0] for t in falls]); as_ = np.array([max(sc[t][0] for t in g) for g in adl_groups.values()])
    fr = (fs_[None, :] >= THR_GRID[:, None]).mean(1); af = (as_[None, :] >= THR_GRID[:, None]).mean(1)
    ok = np.where(fr >= target)[0]
    k = ok[np.lexsort((-THR_GRID[ok], af[ok]))[0]] if len(ok) else np.lexsort((af, -fr))[0]
    return dict(thr=float(THR_GRID[k]), std=float(std_default), recall=float(fr[k]), far=float(af[k]), feasible=bool(len(ok)),
                n_falls=len(falls), n_adl_trials=len(adl_groups))


def choose_params(ds, p, trial_ids, std_grid=None):
    """Return dict(thr, std, recall, far, feasible). p = window probs aligned with ds['Xw'] (only trial_ids need be valid)."""
    best = None
    falls = [t for t in trial_ids if ds["trials"][t]["is_fall"] and ds["trials"][t]["elig"]]
    adl_groups = {}
    for t in trial_ids:
        tr = ds["trials"][t]
        if not tr["is_fall"]:
            adl_groups.setdefault(tr["trial_id"], []).append(t)
    fb = None
    for std in (std_grid or F.STD_GRID):
        sc = trial_scores(ds, p, falls + [t for g in adl_groups.values() for t in g], std)
        fs_ = np.array([sc[t][1] for t in falls])
        as_ = np.array([max(sc[t][1] for t in g) for g in adl_groups.values()])
        # vectorised sweep over THR_GRID
        fr = (fs_[None, :] >= THR_GRID[:, None]).mean(1)
        af = (as_[None, :] >= THR_GRID[:, None]).mean(1)
        ok = np.where(fr >= TARGET_RECALL)[0]
        if len(ok):
            # min FAR, ties -> larger thr
            k = ok[np.lexsort((-THR_GRID[ok], af[ok]))[0]]
            key = (af[k], -THR_GRID[k])
            if best is None or key < best[0]:
                best = (key, dict(thr=float(THR_GRID[k]), std=float(std), recall=float(fr[k]), far=float(af[k]), feasible=True))
        # fallback candidate: max recall then min FAR
        k2 = np.lexsort((af, -fr))[0]
        key2 = (-fr[k2], af[k2])
        if fb is None or key2 < fb[0]:
            fb = (key2, dict(thr=float(THR_GRID[k2]), std=float(std), recall=float(fr[k2]), far=float(af[k2]), feasible=False))
    res = best[1] if best else fb[1]
    res["n_falls"] = len(falls); res["n_adl_trials"] = len(adl_groups)
    return res


def outcomes(ds, p, trial_ids, thr, std, meta=None):
    """Per-segment outcomes DataFrame for the given trials."""
    still = still_flags(ds, std)
    cons = still | ~ds["ev"]
    rows = []
    for t in trial_ids:
        tr = ds["trials"][t]
        sl = slice(tr["off"], tr["off"] + tr["cnt"])
        pp = p[sl]
        trig_w = pp >= thr
        conf_w = trig_w & still[sl]
        cons_w = trig_w & cons[sl]

        def n_events(flag):
            idx = np.where(flag)[0]
            if len(idx) == 0:
                return 0
            gap = 10    # windows (5 s refractory)
            return 1 + int((np.diff(idx) > gap).sum())
        rows.append(dict(tid=t, trial_id=tr["trial_id"], subject=tr["subject"], dataset=tr["dataset"], group=tr["group"],
                         is_fall=tr["is_fall"], ftype=tr["ftype"], elig=tr["elig"], post3=tr["post3"], dur_s=tr["dur_s"],
                         trig=bool(trig_w.any()), conf=bool(conf_w.any()), cons=bool(cons_w.any()),
                         ev_trig=n_events(trig_w), ev_conf=n_events(conf_w), max_p=float(pp.max()),
                         thr=thr, std=std, **(meta or {})))
    return pd.DataFrame(rows)


def aggregate_trials(df):
    """Segments -> trials: an ADL file is alarmed iff any segment is; durations / event counts add up."""
    f = df[df.is_fall]
    a = df[~df.is_fall]
    if len(a):
        g = a.groupby("trial_id", sort=False)
        a = g.agg(subject=("subject", "first"), dataset=("dataset", "first"), group=("group", "first"), is_fall=("is_fall", "first"),
                  ftype=("ftype", "first"), elig=("elig", "first"), post3=("post3", "first"), dur_s=("dur_s", "sum"),
                  trig=("trig", "max"), conf=("conf", "max"), cons=("cons", "max"), ev_trig=("ev_trig", "sum"), ev_conf=("ev_conf", "sum"),
                  max_p=("max_p", "max")).reset_index()
    return pd.concat([f, a], ignore_index=True)


# ---------------------------------------------------------------- metrics + subject bootstrap
def metric_defs(df):
    """name -> (numerator mask/values, denominator mask/values) over the rows of df (trial level)."""
    fall = df.is_fall.values; adl = ~fall
    elig = df.elig.values
    h = df.dur_s.values / 3600.0
    d = {}
    d["fall_recall_trigger"] = (fall & df.trig.values, fall)
    d["fall_recall_confirm"] = (fall & elig & df.conf.values, fall & elig)
    d["adl_far_trigger"] = (adl & df.trig.values, adl)
    d["adl_far_confirm"] = (adl & df.conf.values, adl)
    d["adl_far_confirm_cons"] = (adl & df.cons.values, adl)
    d["fa_per_hour_trials"] = ((adl & df.conf.values).astype(float), np.where(adl, h, 0.0))
    d["fa_per_hour_events"] = (np.where(adl, df.ev_conf.values, 0).astype(float), np.where(adl, h, 0.0))
    d["fa_per_hour_trigger_events"] = (np.where(adl, df.ev_trig.values, 0).astype(float), np.where(adl, h, 0.0))
    d["fa_per_hour_trigger_trials"] = ((adl & df.trig.values).astype(float), np.where(adl, h, 0.0))
    for g in ("young", "old"):
        m = adl & (df.group.values == g)
        d[f"adl_far_confirm_{g}"] = (m & df.conf.values, m)
        d[f"adl_far_trigger_{g}"] = (m & df.trig.values, m)
    for ds_ in sorted(df.dataset.unique()):
        mf = fall & (df.dataset.values == ds_)
        ma = adl & (df.dataset.values == ds_)
        d[f"fall_recall_trigger[{ds_}]"] = (mf & df.trig.values, mf)
        d[f"fall_recall_confirm[{ds_}]"] = (mf & elig & df.conf.values, mf & elig)
        d[f"adl_far_confirm[{ds_}]"] = (ma & df.conf.values, ma)
        d[f"adl_far_trigger[{ds_}]"] = (ma & df.trig.values, ma)
        d[f"fa_per_hour_trigger_trials[{ds_}]"] = ((ma & df.trig.values).astype(float), np.where(ma, h, 0.0))
        d[f"fa_per_hour_trigger_events[{ds_}]"] = (np.where(ma, df.ev_trig.values, 0).astype(float), np.where(ma, h, 0.0))
    for ft in sorted(df[df.is_fall].ftype.unique()):
        mf = fall & (df.ftype.values == ft)
        d[f"fall_recall_trigger[{ft}]"] = (mf & df.trig.values, mf)
        d[f"fall_recall_confirm[{ft}]"] = (mf & elig & df.conf.values, mf & elig)
    return d


def summarize(df, B=2000, seed=0):
    """-> DataFrame(metric, value, lo, hi, n_num, n_den). 95 % percentile bootstrap over subjects."""
    d = metric_defs(df)
    subj = df.subject.values
    us, inv = np.unique(subj, return_inverse=True)
    S = len(us)
    rng = np.random.default_rng(seed)
    Wt = rng.multinomial(S, np.ones(S) / S, size=B).astype(float)      # (B, S) subject resampling counts
    rows = []
    for k, (num, den) in d.items():
        nv = np.bincount(inv, weights=np.asarray(num, dtype=float), minlength=S)
        dv = np.bincount(inv, weights=np.asarray(den, dtype=float), minlength=S)
        tn, td = nv.sum(), dv.sum()
        val = tn / td if td > 0 else np.nan
        bn, bd = Wt @ nv, Wt @ dv
        with np.errstate(invalid="ignore", divide="ignore"):
            bs = bn / bd
        bs = bs[np.isfinite(bs)]
        lo, hi = (np.percentile(bs, [2.5, 97.5]) if len(bs) > 20 else (np.nan, np.nan))
        rows.append(dict(metric=k, value=val, lo=lo, hi=hi, n_num=float(tn), n_den=float(td)))
    return pd.DataFrame(rows)


def paired_diff(dfa, dfb, metrics, B=2000, seed=0):
    """Paired subject bootstrap of metric(A) - metric(B) on the same trial set (rows may be in different order).
    -> DataFrame(metric, diff, lo, hi)."""
    da, db = metric_defs(dfa), metric_defs(dfb)
    subs = np.unique(np.concatenate([dfa.subject.values, dfb.subject.values]))
    idx = {s_: i for i, s_ in enumerate(subs)}
    S = len(subs)
    rng = np.random.default_rng(seed)
    Wt = rng.multinomial(S, np.ones(S) / S, size=B).astype(float)

    def per_subject(d, df, k):
        num, den = d[k]
        inv = np.array([idx[s_] for s_ in df.subject.values])
        return (np.bincount(inv, weights=np.asarray(num, dtype=float), minlength=S), np.bincount(inv, weights=np.asarray(den, dtype=float), minlength=S))
    rows = []
    for k in metrics:
        na, dna = per_subject(da, dfa, k); nb, dnb = per_subject(db, dfb, k)
        val = na.sum() / dna.sum() - nb.sum() / dnb.sum()
        with np.errstate(invalid="ignore", divide="ignore"):
            bs = (Wt @ na) / (Wt @ dna) - (Wt @ nb) / (Wt @ dnb)
        bs = bs[np.isfinite(bs)]
        rows.append(dict(metric=k, diff=float(val), lo=float(np.percentile(bs, 2.5)), hi=float(np.percentile(bs, 97.5))))
    return pd.DataFrame(rows)


def adl_breakdown(df, names, top=5):
    """ADL false-alarm (trigger-only) breakdown per dataset: top activities by number of alarmed trials."""
    a = df[~df.is_fall]
    out = []
    for ds_, g in a.groupby("dataset"):
        tot = int(g.trig.sum())
        t = g.groupby("ftype").agg(trials=("trig", "size"), alarmed=("trig", "sum"), hours=("dur_s", lambda x: x.sum() / 3600.0)).reset_index()
        t["far"] = t.alarmed / t.trials
        t["share_of_dataset_FAs"] = t.alarmed / max(tot, 1)
        t["alarmed_per_hour"] = t.alarmed / t.hours
        t = t.sort_values(["alarmed", "far"], ascending=False).head(top)
        t.insert(0, "dataset", ds_)
        t["activity"] = [names.get(k, k) for k in t.ftype]
        out.append(t)
    return pd.concat(out, ignore_index=True)
