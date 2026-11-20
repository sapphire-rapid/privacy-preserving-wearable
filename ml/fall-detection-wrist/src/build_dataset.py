"""Step 3: featurise every trial of the train pool (WEDA + SmartFallMM) at 26 and 52 Hz -> cache/ds_<fs>.pkl

ds = dict(
  trials : list of dict(tid, trial_id, subject, dataset, group, is_fall, ftype, n, dur_s, off, cnt, peak, elig, post3, ...)
  Xw     : (Nw, 9) features of every sliding window of every trial (evaluation grid)
  ev/sd/mu : confirm-segment stats per eval window (evaluable flag, std, mean of the CONFIRM samples after the window)
  w_trial, w_start : which trial / start sample each eval window belongs to
  Xtr, ytr, tr_trial, tr_factor : TRAINING windows (ADL: all sliding windows, fall: impact window) for each stretch factor
)
BITS gets the same structure without training windows (cache/ds_bits_<fs>.pkl), built only when the held-out run is allowed.
"""
import os
import sys
import pickle
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import features as F

ROOT = os.path.dirname(HERE)
CACHE = os.path.join(ROOT, "cache")


def build(trials_in, fs, train=True, gyro_key=None):
    c = F.cfg_for(fs)
    trials, Xw, EV, SD, MU, WT, WS = [], [], [], [], [], [], []
    Xtr, ytr, ttr, ftr = [], [], [], []
    off = 0
    for r in trials_in:
        x = r["x%d" % fs].astype(np.float64)
        n = len(x)
        if n < c.win:
            continue
        xg = None
        if gyro_key is not None:
            if not r.get("gyro_ok"):
                continue
            xg = r[gyro_key].astype(np.float64)
        tid = len(trials)
        m = F.mag(x)
        st = F.sliding_starts(n, c)
        xw = F.window_features(x, st, c)
        if xg is not None:
            xw = np.hstack([xw, F.gyro_window_features(x, xg, st, c)])
        ev, sd, mu = F.stillness_stats(m, st, c)
        peak = int(np.argmax(m))
        t = dict(tid=tid, trial_id=r["trial_id"], seg=r["seg"], subject=r["subject"], dataset=r["dataset"], group=r["group"],
                 is_fall=r["is_fall"], ftype=r["ftype"], n=n, dur_s=n / fs, off=off, cnt=len(st), peak=peak,
                 post_s=(n - 1 - peak) / fs)
        # falls: windows that contain the impact peak; eligible for "with confirm" if one of them has its confirm segment inside the data
        if r["is_fall"]:
            contains = (st <= peak) & (peak < st + c.win)
            t["elig"] = bool((contains & ev).any())
            t["post3"] = bool(t["post_s"] >= 3.0)
        else:
            t["elig"] = True
            t["post3"] = True
        for k in ("rest_g", "rule4_pass", "rule5_pass", "ts_span_s", "n_expected_s"):
            if k in r:
                t[k] = r[k]
        trials.append(t)
        Xw.append(xw); EV.append(ev); SD.append(sd); MU.append(mu)
        WT.append(np.full(len(st), tid)); WS.append(st)
        off += len(st)
        if train:
            for f in F.STRETCH:
                xs = F.stretch(x, f)
                xt, yt = F.trial_windows(xs, r["is_fall"], c, None if xg is None else F.stretch(xg, f))
                if len(xt):
                    Xtr.append(xt); ytr.append(yt); ttr.append(np.full(len(yt), tid)); ftr.append(np.full(len(yt), f))
    ds = dict(fs=fs, trials=trials, Xw=np.vstack(Xw), ev=np.concatenate(EV), sd=np.concatenate(SD), mu=np.concatenate(MU),
              w_trial=np.concatenate(WT), w_start=np.concatenate(WS))
    if train:
        ds.update(Xtr=np.vstack(Xtr), ytr=np.concatenate(ytr), tr_trial=np.concatenate(ttr), tr_factor=np.concatenate(ftr))
    return ds


def main_v3():
    """v3 populations: W = WEDA only, native gyro range; P = WEDA (clipped to +-125 dps/axis) + SmartFallMM (synced gyro, natively +-125 dps)."""
    weda = pickle.load(open(os.path.join(CACHE, "weda.pkl"), "rb"))
    sfmm = pickle.load(open(os.path.join(CACHE, "sfmm.pkl"), "rb"))
    for name, trials, key in (("v3W", weda, "g26"), ("v3P", None, "g26c")):
        if trials is None:
            trials = []
            for r in weda + sfmm:
                trials.append(r)
        ds = build(trials, 26, train=True, gyro_key=key)
        with open(os.path.join(CACHE, "ds_%s_26.pkl" % name), "wb") as f:
            pickle.dump(ds, f, protocol=4)
        tr = ds["trials"]; falls = [t for t in tr if t["is_fall"]]
        print(f"{name}: trials {len(tr)} (falls {len(falls)}, ADL segments {len(tr)-len(falls)}), subjects {len({t['subject'] for t in tr})}, "
              f"eval windows {len(ds['Xw'])} x {ds['Xw'].shape[1]}, train windows {len(ds['ytr'])} (pos {int(ds['ytr'].sum())}), confirm-eligible falls {sum(t['elig'] for t in falls)}", flush=True)


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "v3":
        return main_v3()
    pool = []
    for name in ("weda", "sfmm"):
        pool += pickle.load(open(os.path.join(CACHE, name + ".pkl"), "rb"))
    for fs in (26, 52):
        ds = build(pool, fs, train=True)
        with open(os.path.join(CACHE, "ds_%d.pkl" % fs), "wb") as f:
            pickle.dump(ds, f, protocol=4)
        tr = ds["trials"]
        falls = [t for t in tr if t["is_fall"]]
        print(f"fs={fs}: trials {len(tr)} (falls {len(falls)}, ADL segments {len(tr)-len(falls)}), eval windows {len(ds['Xw'])}, "
              f"train windows {len(ds['ytr'])} (pos {int(ds['ytr'].sum())}), "
              f"falls post>=3s {sum(t['post3'] for t in falls)}, confirm-eligible {sum(t['elig'] for t in falls)}", flush=True)


if __name__ == "__main__":
    main()
