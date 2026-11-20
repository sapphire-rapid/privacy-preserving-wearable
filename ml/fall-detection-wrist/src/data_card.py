"""Step 1: measure every property reported in results/DATA_CARD.md straight from the raw files.
Writes results/data_card_stats.json (all per-trial numbers) and results/DATA_CARD.md.
Run: .venv/bin/python -I src/data_card.py
"""
import os
import sys
import json
import collections
import numpy as np
from scipy.ndimage import uniform_filter1d

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import wrist_io as W

RES = os.path.join(os.path.dirname(HERE), "results")
os.makedirs(RES, exist_ok=True)


def rest_mag(m, n):
    """Mean |a| over the n-sample window with the smallest std (a proxy for 'at rest')."""
    if len(m) < n + 1:
        return float("nan")
    s = np.lib.stride_tricks.sliding_window_view(m, n)
    return float(s[int(np.argmin(s.std(axis=1)))].mean())


def lp_norm_median(v, n):
    """Median norm of the 1-s moving-average vector: ~|g| for a gravity-inclusive sensor
    regardless of motion, ~0 for a linear-acceleration (gravity-free) sensor."""
    lp = uniform_filter1d(v, size=n, axis=0, mode="nearest")
    return float(np.median(np.linalg.norm(lp, axis=1)))


def q(a, ps=(5, 50, 95)):
    a = np.asarray(a, dtype=float)
    a = a[np.isfinite(a)]
    return [float(np.percentile(a, p)) for p in ps] if len(a) else [float("nan")] * len(ps)


# ============================================================================ WEDA
def weda():
    ts = W.load_weda_fall_timestamps()
    rows = []
    for tr in W.weda_trials("50Hz"):
        t, a = W.load_weda(tr["path"])
        m = np.linalg.norm(a, axis=1)
        d = np.diff(t)
        med = float(np.median(d))
        peak = int(np.argmax(m))
        r = dict(tr, n=len(t), dur=float(t[-1] - t[0]), med_dt=med,
                 eff_hz=(len(t) - 1) / float(t[-1] - t[0]),
                 frac_dt_lt5ms=float(np.mean(d < 0.005)), frac_dt_gt50ms=float(np.mean(d > 0.05)),
                 frac_dt_off=float(np.mean((d < 0.5 * med) | (d > 1.5 * med))),
                 max_dt=float(d.max()), nonmono=bool(np.any(d <= 0)),
                 rest=rest_mag(m, 50), peak_t=float(t[peak]), post_peak=float(t[-1] - t[peak]),
                 peak_val=float(m[peak]))
        if tr["is_fall"]:
            k = (tr["code"], tr["subject"], tr["trial"])
            if k in ts:
                s, e = ts[k]
                r.update(ann_start=s, ann_end=e, post_ann_end=float(t[-1] - e),
                         peak_in_ann=bool(s - 0.5 <= t[peak] <= e + 0.5))
            else:
                r.update(ann_start=None)
        rows.append(r)
    return rows


# ============================================================================ SFMM
def sfmm():
    rows = []
    for tr in W.sfmm_trials():
        t, el, a = W.load_sfmm(tr["path"])
        if len(t) < 3:
            rows.append(dict(tr, n=len(t), bad=True))
            continue
        m = np.linalg.norm(a, axis=1)
        d = np.diff(t)
        med = float(np.median(d))
        peak = int(np.argmax(m))
        gaps_after = np.where(d[peak:] > 1.0)[0]
        t_end_contig = t[peak + gaps_after[0]] if len(gaps_after) else t[-1]
        rate_cls = {20: 50, 40: 25}.get(round(med * 1000), None)
        rows.append(dict(tr, n=len(t), bad=False, med_dt=med, rate_cls=rate_cls,
                         eff_hz=1.0 / med if med > 0 else float("nan"),
                         frac_dt_off=float(np.mean((d < 0.5 * med) | (d > 1.5 * med))),
                         n_gaps=int((d > 1.0).sum()), n_nonpos=int((d <= 0).sum()),
                         max_dt=float(d.max()), dur=float(t[-1] - t[0]),
                         med_mag=float(np.median(m)), unit_anom=bool(not (0.5 <= np.median(m) <= 2.0)),
                         rest=rest_mag(m, int(round(1.0 / med))), peak_val=float(m[peak]),
                         post_peak=float(t[-1] - t[peak]), post_peak_contig=float(t_end_contig - t[peak])))
    return rows


# ============================================================================ BITS
def bits(nominal_hz=20):
    rows = []
    for tr in W.bits_trials():
        raw = W.load_bits_raw(tr["path"])
        r = dict(tr, tags=sorted(raw))
        for k in ("acc", "acg", "gyro", "mgm", "hrt"):
            r["n_" + k] = int(len(raw[k]["t"])) if k in raw else 0
        for k in ("acc", "acg"):
            m = np.linalg.norm(raw[k]["v"], axis=1)
            r["rest_" + k] = rest_mag(m, nominal_hz)
            r["lp_" + k] = lp_norm_median(raw[k]["v"], nominal_hz)
            r["peak_" + k] = int(np.argmax(m))
            r["peakval_" + k] = float(m.max())
            r["post_peak_n_" + k] = int(len(m) - 1 - np.argmax(m))
        t = raw["acg"]["t"]
        r["uniq_t_frac"] = float(len(np.unique(t)) / len(t))
        r["nonmono_t"] = bool(np.any(np.diff(t) < 0))
        rows.append(r)
    return rows


def main():
    print("WEDA ...", flush=True); Wd = weda()
    print("SFMM ...", flush=True); Sf = sfmm()
    print("BITS ...", flush=True); Bt = bits()
    with open(os.path.join(RES, "data_card_stats.json"), "w") as f:
        json.dump({"weda": Wd, "sfmm": Sf, "bits": Bt}, f)

    L = []; A = L.append
    young = lambda r: r["subject"] <= 14
    F = [r for r in Wd if r["is_fall"]]; D = [r for r in Wd if not r["is_fall"]]
    G_ = [r for r in Sf if not r.get("bad")]
    SF = [r for r in G_ if r["is_fall"]]; SD = [r for r in G_ if not r["is_fall"]]
    BF = [r for r in Bt if r["is_fall"]]; BD = [r for r in Bt if not r["is_fall"]]

    # derived numbers used in several places
    effF = q([r["eff_hz"] for r in F]); effD = q([r["eff_hz"] for r in D])
    c50 = sum(1 for r in G_ if r["rate_cls"] == 50); c25 = sum(1 for r in G_ if r["rate_cls"] == 25)
    cot = len(G_) - c50 - c25
    anom = [r for r in G_ if r["unit_anom"]]
    sf_p3 = sum(1 for r in SF if r["post_peak"] >= 3.0)
    sf_p3c = sum(1 for r in SF if r["post_peak_contig"] >= 3.0)
    w_p3 = sum(1 for r in F if r["post_peak"] >= 3.0)
    b_p3 = sum(1 for r in BF if r["post_peak_n_acg"] >= 3 * 20)
    ratios = [r["n_acg"] / r["n_hrt"] for r in Bt if r["n_hrt"] > 0]
    rq = q(ratios, (5, 25, 50, 75, 95))
    cls = collections.Counter()
    for r in Bt:
        cls[(r["lp_acc"] > 6, r["lp_acg"] > 6)] += 1

    A("# DATA CARD — wrist datasets (Step 1)\n")
    A("Every figure is **measured from the raw files** by `src/data_card.py` (the script also writes a per-trial dump `results/data_card_stats.json`; it is not committed because it contains local file paths — regenerate it by running the script). "
      "Raw data stay outside the repo (`~/datasets/wrist`, read-only). *Rest check* = mean |a| over the 1-s window with the smallest std in each trial; tables give median [5th, 95th percentile] over trials.\n")

    A("## 0. Things that look off — decisions needed before Step 2\n")
    A(f"1. **WEDA-FALL: fall files and ADL files were recorded at different effective sample rates.** The {len(F)} fall trials have a median effective rate of "
      f"**{effF[1]:.1f} Hz** (5–95th pct {effF[0]:.1f}–{effF[2]:.1f}); ADL trials **{effD[1]:.1f} Hz** ({effD[0]:.1f}–{effD[2]:.1f}). "
      f"{sum(1 for r in F if r['eff_hz'] < 45)}/{len(F)} fall trials are below 45 Hz versus {sum(1 for r in D if r['eff_hz'] < 45)}/{len(D)} ADL trials, i.e. rate almost perfectly separates the classes and is an acquisition artifact, not a property of falls, so a naive 'index = time at 50 Hz' or per-trial-clock treatment can leak class through time scale (a ×0.8 time-stretch, far outside the {{0.95, 1.00, 1.05}} augmentation). "
      f"Timestamps are also burst-stamped (≈{np.mean([r['frac_dt_lt5ms'] for r in Wd])*100:.0f} % of intervals < 5 ms, then ~100 ms gaps = Fitbit batch delivery), so 'interpolate on the timestamps' reconstructs a staircase, not the true signal.")
    A(f"2. **SmartFallMM: README says 50 Hz, but it is a mix: {c50} trials at 50 Hz, {c25} at 25 Hz (young subjects S28–S39 only), {cot} other.** The epoch-ms column is Excel-mangled in ~19 % of files, so I used the ISO time string as the clock. "
      f"Also: {sum(1 for r in G_ if r['n_gaps']>0)} trials contain gaps > 1 s (concatenated recordings, up to an hour), {sum(1 for r in G_ if r['n_nonpos']>0)} have non-increasing timestamps, "
      f"and **{len(anom)} ADL files are not in g** (median |a| outside 0.5–2 g, e.g. subject S06 ×27, S30A09 ×5; |a| up to ~200). I propose to drop those {len(anom)} (all ADL, no falls affected) and split trials at gaps.")
    A(f"3. **SmartFallMM falls have little post-impact data:** only **{sf_p3}/{len(SF)}** fall trials have ≥ 3 s after the |a| peak (contiguous, no gap: {sf_p3c}/{len(SF)}); median {np.median([r['post_peak'] for r in SF]):.2f} s. "
      f"'With confirm' on SmartFallMM will cover ~{sf_p3c/len(SF)*100:.0f} % of its falls; WEDA covers {w_p3}/{len(F)}.")
    A("4. **BITS: tag naming is the opposite of intuition.** Of the sensors in each file, `acg` is the gravity-inclusive accelerometer and `acc` is gravity-free *linear* acceleration "
      f"(in {cls[(False, True)]}/{len(Bt)} files `acc` low-passed norm < 6 and `acg` > 6 m/s²; reversed in {cls[(True, False)]}; both gravity-inclusive in {cls[(True, True)]} — likely vigorous motion; neither in {cls[(False, False)]}). "
      "You asked for the accelerometer, not linear acc ⇒ **`acg`** (the 9 features need gravity). Please confirm.")
    A(f"5. **BITS sampling rate and regularity cannot be verified**: timestamps are mangled to 3 significant digits (`1.82E+11`), so only {np.median([r['uniq_t_frac'] for r in Bt])*100:.2f} % of timestamps in a file are unique and {sum(r['nonmono_t'] for r in Bt)}/{len(Bt)} files are non-monotonic. "
      f"The only independent hint: samples-per-HR-row (HR nominally 1 Hz) has median {rq[2]:.1f} (IQR {rq[1]:.1f}–{rq[3]:.1f}, 5–95th {rq[0]:.1f}–{rq[4]:.1f}) — consistent with 20 Hz at the median but far too variable to prove it. I will treat BITS as 20 Hz by sample order, as you specified; the held-out result then carries that caveat.")
    A("6. BITS has no README: no age, no activity legend, no fall-type labels. Per-fall-type recall and young/old ADL split are therefore **not computable on BITS** (ages are only known from the dataset paper: 20–47, see §6).\n")

    # ---------------- WEDA
    r_ = q([r["rest"] for r in Wd]); mdt = q([r["med_dt"] for r in Wd]); mx = q([r["max_dt"] for r in Wd])
    A("## 1. WEDA-FALL (Fitbit Sense, wrist) — `WEDA-FALL/dataset/50Hz`\n")
    A("| item | value |\n|---|---|")
    A("| file format | one CSV per trial per sensor: `<code>/U<uid>_R<trial>_accel.csv`; header `accel_time_list,accel_x_list,accel_y_list,accel_z_list`; floats. (gyro / orientation / vertical_accel files exist, **not used**.) |")
    A(f"| units | **m/s²** (not stated in README; verified: rest |a| median {r_[1]:.2f} m/s² = {r_[1]/W.G:.3f} g, 5–95th [{r_[0]:.2f}, {r_[2]:.2f}]). Time in seconds. Convert ÷ 9.80665. |")
    A(f"| gravity included | **Yes** (|a| = {r_[1]/W.G:.3f} g at rest). |")
    A(f"| sampling rate | nominal 50 Hz. Effective (n−1)/duration per trial: **ADL {effD[1]:.1f} Hz, falls {effF[1]:.1f} Hz** (see §0.1). Median dt {mdt[1]*1000:.1f} ms. |")
    A(f"| regularity | **irregular / burst-stamped**: {np.mean([r['frac_dt_lt5ms'] for r in Wd])*100:.0f} % of intervals < 5 ms, {np.mean([r['frac_dt_gt50ms'] for r in Wd])*100:.0f} % > 50 ms; max gap median {mx[1]*1000:.0f} ms [5–95th {mx[0]*1000:.0f}, {mx[2]*1000:.0f}]; {sum(r['nonmono'] for r in Wd)} trials with duplicate/non-increasing timestamps. |")
    A(f"| subjects | young U01–U14 ({len({r['subject'] for r in Wd if young(r)})}; ages 20–23, U14 is 46) ; elderly U21–U31 ({len({r['subject'] for r in Wd if not young(r)})}; ages 77–95) |")
    A(f"| trials | **{len(Wd)}** accel files: **{len(F)} fall**, **{len(D)} ADL** (README: 350 falls; 462 young + 157 elderly ADL) |")
    A(f"| ADL split | young ADL {sum(1 for r in D if young(r))} trials ({sum(r['dur'] for r in D if young(r))/3600:.2f} h), elderly ADL {sum(1 for r in D if not young(r))} trials ({sum(r['dur'] for r in D if not young(r))/3600:.2f} h); total {sum(r['dur'] for r in D)/3600:.2f} h |")
    fs = sorted({r['subject'] for r in F})
    A(f"| who fell | young only: U{fs[0]:02d}–U{fs[-1]:02d} ({len(fs)} subjects); elderly fall trials: {sum(1 for r in F if not young(r))} |")
    A("| label mapping | folder code: `F01–F08` → fall, `D01–D11` → ADL (all ADL kept, incl. hard negatives D02 jog, D05 collapse into chair, D07 stumble, D08 jump, D09 hit table, D10 clap) |")
    cnt = collections.Counter(r["code"] for r in Wd)
    names = {"F01": "fwd fall walking (slip)", "F02": "lateral fall walking (slip)", "F03": "back fall walking (slip)", "F04": "fwd fall walking (trip)",
             "F05": "back fall trying to sit", "F06": "fwd fall sitting (faint)", "F07": "back fall sitting (faint)", "F08": "lateral fall sitting (faint)",
             "D01": "walking", "D02": "jogging", "D03": "stairs up/down", "D04": "sit–wait–stand", "D05": "sit, try to rise, collapse into chair",
             "D06": "crouch / tie shoes", "D07": "stumble while walking", "D08": "gentle jump", "D09": "hit table with hand", "D10": "clapping", "D11": "open/close door"}
    A("\n| code | activity | trials | subjects | eff. rate Hz (median) |\n|---|---|---|---|---|")
    for c in W.WEDA_FALL_CODES + W.WEDA_ADL_CODES:
        rr = [r for r in Wd if r["code"] == c]
        A(f"| {c} | {names[c]} | {cnt[c]} | {len({r['subject'] for r in rr})} | {np.median([r['eff_hz'] for r in rr]):.1f} |")
    pk = [r["post_peak"] for r in F]
    A(f"\n**Post-fall data after the |a| peak** (argmax |a|): **{w_p3}/{len(F)}** fall trials have ≥ 3 s after the peak (post-peak s: min {min(pk):.2f}, median {np.median(pk):.2f}, max {max(pk):.2f}). "
      f"Using the README's manual annotation (`fall_timestamps.csv`): {sum(1 for r in F if r['post_ann_end']>=3.0)}/{len(F)} have ≥ 3 s after the annotated *end* of the fall; "
      f"the argmax peak lies inside the annotated window (±0.5 s) in {sum(1 for r in F if r['peak_in_ann'])}/{len(F)} trials. (README: annotations 'can have mistakes'.)\n")
    A("| code | trials | ≥3 s post-peak |\n|---|---|---|")
    for c in W.WEDA_FALL_CODES:
        ff = [r for r in F if r["code"] == c]
        A(f"| {c} | {len(ff)} | {sum(1 for r in ff if r['post_peak']>=3.0)} |")

    # ---------------- SFMM
    r2 = q([r["rest"] for r in G_])
    A("\n## 2. SmartFallMM — `Meta_wrist` accelerometer only\n")
    A("*© SmartFall Group, Texas State University — all rights reserved; credit required. Cite: \"SmartFallMM: A multimodal dataset for fall detection using commodity devices\" (IEEE; https://ieeexplore.ieee.org/abstract/document/11651591; code/data: https://github.com/txst-cs-smartfall/SmartFallMM-Dataset). Raw data are not redistributed.*\n")
    A("| item | value |\n|---|---|")
    A("| file format | `{young,old}/accelerometer/meta_wrist/S<sid>A<aid>T<tid>.csv`; **no header**; 6 columns: epoch ms, ISO time, elapsed s, x, y, z |")
    A(f"| units | **g** (not stated in README; verified: rest |a| median {r2[1]:.3f} [5–95th {r2[0]:.3f}, {r2[2]:.3f}]); **{len(anom)} files are NOT in g** (§0.2). |")
    A(f"| gravity included | **Yes** (≈ 1 g at rest). |")
    A(f"| sampling rate | **{c50} trials 50 Hz (dt 20 ms), {c25} trials 25 Hz (dt 40 ms; all young S28–S39), {cot} other (dt ≈ 31 ms)**, from the ISO clock. |")
    A(f"| regularity | within a trial regular (median fraction of intervals outside [0.5,1.5]× median dt = {np.median([r['frac_dt_off'] for r in G_])*100:.1f} %); epoch-ms column corrupted in ~19 % of files; {sum(1 for r in G_ if r['n_gaps']>0)} trials with gaps > 1 s ({sum(1 for r in SF if r['n_gaps']>0)} falls), {sum(1 for r in G_ if r['n_nonpos']>0)} with non-increasing timestamps; {len(Sf)-len(G_)} unreadable files |")
    yS = sorted({r['subject'] for r in G_ if r['group'] == 'young'}); oS = sorted({r['subject'] for r in G_ if r['group'] == 'old'})
    A(f"| subjects | young folder: {len(yS)} subjects (ids {yS[0]}–{yS[-1]}); old folder: {len(oS)} subjects (ids {oS}); overlap: {sorted(set(yS)&set(oS)) or 'none'}. README lists old = 2–26, but the folder also holds S01 and S47 |")
    A(f"| trials | **{len(G_)}**: **{len(SF)} fall**, **{len(SD)} ADL** |")
    A(f"| ADL split | young {sum(1 for r in SD if r['group']=='young')} trials ({sum(r['dur'] for r in SD if r['group']=='young' and r['n_gaps']==0)/3600:.2f} h, gap-free files), old {sum(1 for r in SD if r['group']=='old')} trials ({sum(r['dur'] for r in SD if r['group']=='old' and r['n_gaps']==0)/3600:.2f} h, gap-free files) |")
    fs2 = sorted({r['subject'] for r in SF})
    A(f"| who fell | {len(fs2)} subjects, all young (old-folder falls: {sum(1 for r in SF if r['group']=='old')}) |")
    A("| label mapping | from filename Axx and README: A10 Backfall, A11 Frontfall, A12 Leftfall, A13 Rightfall, A14 Rotatefall → fall; A01–A09 → ADL |")
    A("\n| id | activity | group | trials | subjects |\n|---|---|---|---|---|")
    for aid in range(1, 15):
        for g in ("young", "old"):
            r3 = [r for r in G_ if r["activity"] == aid and r["group"] == g]
            if r3:
                A(f"| A{aid:02d} | {W.SFMM_ACTIVITY[aid]} | {g} | {len(r3)} | {len({r['subject'] for r in r3})} |")
    pk2 = [r["post_peak"] for r in SF]
    A(f"\n**Post-fall data after the |a| peak**: **{sf_p3}/{len(SF)}** fall trials have ≥ 3 s after the peak (≥ 3 s contiguous before any gap: {sf_p3c}); post-peak s: min {min(pk2):.2f}, median {np.median(pk2):.2f}, max {max(pk2):.2f}. "
      f"The dataset authors cropped each trial by hand: fall duration median {np.median([r['dur'] for r in SF]):.1f} s [min {min(r['dur'] for r in SF):.1f}, max {max(r['dur'] for r in SF):.1f}].\n")
    A("| fall type | trials | ≥3 s post-peak | median post-peak s |\n|---|---|---|---|")
    for aid in sorted(W.SFMM_FALL_IDS):
        ff = [r for r in SF if r["activity"] == aid]
        A(f"| A{aid} {W.SFMM_ACTIVITY[aid]} | {len(ff)} | {sum(1 for r in ff if r['post_peak']>=3.0)} | {np.median([r['post_peak'] for r in ff]):.2f} |")
    A("\nNon-g files (median |a| outside 0.5–2 g): " + ", ".join(sorted(f"S{r['subject']:02d}A{r['activity']:02d}T{r['trial']:02d}" for r in anom)) + ".")

    # ---------------- BITS
    ra = q([r["rest_acc"] for r in Bt]); rg = q([r["rest_acg"] for r in Bt])
    tagsets = collections.Counter(tuple(r["tags"]) for r in Bt)
    A("\n## 3. BITS wrist IMU+HR (ages 20–47) — HELD-OUT test set (never used for training/tuning; on-disk folder `bits_geriatric`)\n")
    A("| item | value |\n|---|---|")
    A("| file format | `Dataset/{adl,fall}/user<N>/user<N>_{adl,fall}<k>.csv`; header `t,x,y,z,a,`; several sensors concatenated as contiguous blocks, tagged in the **last column**: `acc`, `acg`, `gyro`, `mgm` (`t,x,y,z,3,<tag>`) and `hrt` (`t,<hr>,<status>,hrt,,`). Tag sets per file: " + str(dict(tagsets)) + ". No README/metadata. |")
    A(f"| units / gravity | native **m/s²** (inferred): `acg` rest |a| median {rg[1]:.3f} m/s² = {rg[1]/W.G:.3f} g ⇒ **gravity included**; `acc` rest median {ra[1]:.3f} m/s² ⇒ **gravity-free linear acceleration** (§0.4). Use `acg`. |")
    A(f"| sampling rate / regularity | **unverifiable** (§0.5). Assumed 20 Hz by sample order. `acc` and `acg` have different sample counts in {sum(r['n_acc']!=r['n_acg'] for r in Bt)}/{len(Bt)} files (separate streams). |")
    A(f"| subjects | {len({r['subject'] for r in Bt})} users (user1–user41); {len({r['subject'] for r in BD})} with ADL, {len({r['subject'] for r in BF})} with falls. Age not stated in the files; the dataset paper (§6) gives 20–47. |")
    A(f"| trials | **{len(Bt)}** files: **{len(BF)} fall** (8 per user), **{len(BD)} ADL** (16 per user); {sum(1 for r in Bt if r['odd_name'])} fall files named `user<N>_.fall<k>.csv` (stray dot, parsed). |")
    A(f"| ADL time | {sum(r['n_acg'] for r in BD)} acg samples = {sum(r['n_acg'] for r in BD)/20/3600:.2f} h **if 20 Hz** |")
    A("| label mapping | `adl/` → ADL, `fall/` → fall; **no activity or fall-type legend** |")
    pp = [r["post_peak_n_acg"] for r in BF]
    A(f"\n**Post-fall data after the `acg` |a| peak**: samples after peak min {min(pp)}, median {int(np.median(pp))}, max {max(pp)}; **{b_p3}/{len(BF)}** fall trials have ≥ 3 s (60 samples) *if 20 Hz*. "
      f"Peak |a| of falls: median {np.median([r['peakval_acg'] for r in BF])/W.G:.1f} g [min {min(r['peakval_acg'] for r in BF)/W.G:.1f}, max {max(r['peakval_acg'] for r in BF)/W.G:.1f}]; ADL median peak {np.median([r['peakval_acg'] for r in BD])/W.G:.1f} g.")
    A("\nHR parsing (`wrist_io.parse_bits_hr`) is written but **not used**.\n")

    # ---------------- cross-dataset
    A("## 4. Cross-dataset summary\n")
    A("| dataset | rate (measured) | units → g | gravity | fall trials | fall trials ≥3 s post-peak | ADL trials | fall subjects | ADL subjects (young/old) |\n|---|---|---|---|---|---|---|---|---|")
    A(f"| WEDA-FALL | ADL {effD[1]:.1f} / fall {effF[1]:.1f} Hz, burst-stamped | ÷9.80665 | yes | {len(F)} | {w_p3} | {len(D)} | {len(fs)} young | {len({r['subject'] for r in D if young(r)})}/{len({r['subject'] for r in D if not young(r)})} |")
    A(f"| SmartFallMM | {c50}×50 Hz, {c25}×25 Hz | none (g); {len(anom)} files bad | yes | {len(SF)} | {sf_p3} | {len(SD)} ({len(anom)} non-g) | {len(fs2)} young | {len({r['subject'] for r in SD if r['group']=='young'})}/{len({r['subject'] for r in SD if r['group']=='old'})} |")
    A(f"| BITS (held-out) | unverified (nominal 20 Hz) | ÷9.80665 (`acg`) | yes (`acg`) | {len(BF)} | {b_p3} @20 Hz | {len(BD)} | {len({r['subject'] for r in BF})} (ages 20–47 per paper) | n/a |")
    A("\nSubject ids will be prefixed per dataset (`W`, `S`, `B`) so GroupKFold never merges different people.\n")
    with open(os.path.join(RES, "DATA_CARD.md"), "w") as f:
        f.write("\n".join(L) + "\n")
    print("wrote DATA_CARD.md")


if __name__ == "__main__":
    main()
