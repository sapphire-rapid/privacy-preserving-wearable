"""Gyroscope data card (DATA_CARD.md section 7) + full-scale analysis (results/gyro_fs.json).
BITS gyro is only described here (units / range); it is not used by any model."""
import os
import sys
import json
import collections
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import wrist_io as W

ROOT = os.path.dirname(HERE)
RES = os.path.join(ROOT, "results")
R2D = 180.0 / np.pi
MARK = "\n## 7. Gyroscope (v3 feature set)\n"


def pc(v, ps=(5, 50, 95)):
    return [float(x) for x in np.percentile(np.asarray(v, dtype=float), ps)]


def peaks_dps(g_dps, a_mag=None):
    m = np.linalg.norm(g_dps, axis=1)
    return float(m.max()), float(np.abs(g_dps).max())


def main():
    stat = {}
    # ---------------- WEDA
    rate = collections.defaultdict(list); pk = collections.defaultdict(list); comp = []; clipped = 0
    walk = []; jog = []
    for tr in W.weda_trials("50Hz"):
        t, g = W.load_weda_gyro(tr["path"].replace("_accel.csv", "_gyro.csv"))
        m = np.linalg.norm(g, axis=1) * R2D
        rate["fall" if tr["is_fall"] else "adl"].append((len(t) - 1) / (t[-1] - t[0]))
        if tr["is_fall"]:
            pk["weda_fall"].append(m.max())
        elif tr["code"] in ("D01",):
            walk.append(np.median(m))
        elif tr["code"] == "D02":
            jog.append(np.median(m))
        pk["weda_adl" if not tr["is_fall"] else "weda_fall_all"].append(m.max())
        mx = np.abs(g).max(); comp.append(mx); clipped += int((np.abs(g) == mx).sum() >= 3)
    stat["weda"] = dict(rate_fall=float(np.median(rate["fall"])), rate_adl=float(np.median(rate["adl"])), walk_med_dps=float(np.median(walk)), jog_med_dps=float(np.median(jog)),
                        max_comp_rad=float(max(comp)), max_comp_dps=float(max(comp) * R2D), n_clip=int(clipped), n=len(comp), fall_peak=pk["weda_fall"], adl_peak=pk["weda_adl"])
    # ---------------- SFMM
    S = {"young": dict(n=0, rate=[], clip=0, comp=[], pk_fall=[], pk=[]), "old": dict(n=0, rate=[], clip=0, comp=[], pk_fall=[], pk=[])}
    wrist_vs_hip = [0, 0]
    for tr in W.sfmm_trials():
        gp = W.sfmm_gyro_path(tr)
        if gp is None:
            continue
        t, g = W.load_sfmm_gyro(gp)
        if len(t) < 5:
            continue
        s = S[tr["group"]]
        s["n"] += 1
        s["rate"].append(1.0 / np.median(np.diff(t)) if np.median(np.diff(t)) > 0 else np.nan)
        mx = np.abs(g).max()
        s["comp"].append(mx); s["clip"] += int((np.abs(g) == mx).sum() >= 3 and 120 < mx < 130)
        m = np.linalg.norm(g, axis=1)
        s["pk"].append(m.max())
        if tr["is_fall"]:
            s["pk_fall"].append(m.max())
        if tr["group"] == "old":
            ph = os.path.join(W.SFMM_ROOT, "old", "gyroscope", "meta_hip", os.path.basename(tr["path"]))
            if os.path.exists(ph):
                wrist_vs_hip[0] += 1
                wrist_vs_hip[1] += int(open(gp, "rb").read() == open(ph, "rb").read())
    stat["sfmm"] = {k: dict(n=v["n"], rate_med=float(np.nanmedian(v["rate"])), clip=v["clip"], comp_p50=float(np.median(v["comp"])), comp_max=float(max(v["comp"])),
                            frac_comp_between_124_126=float(np.mean([(123 < c < 127) for c in v["comp"]])), n_pk_fall=len(v["pk_fall"]),
                            frac_fall_at_cap=float(np.mean([p > 210 for p in v["pk_fall"]])) if v["pk_fall"] else None) for k, v in S.items()}
    stat["sfmm_old_wrist_vs_hip"] = dict(pairs=wrist_vs_hip[0], identical=wrist_vs_hip[1])
    # ---------------- BITS (descriptive only)
    bf = []; badl = []; bcomp = []; ratio = []
    for tr in W.bits_trials():
        t, g = W.bits_gyro(tr["path"])
        m = np.linalg.norm(g, axis=1) * R2D
        (bf if tr["is_fall"] else badl).append(m.max()); bcomp.append(np.abs(g).max())
        raw = W.load_bits_raw(tr["path"]); ratio.append(len(raw["gyro"]["t"]) / len(raw["acg"]["t"]))
    stat["bits"] = dict(max_comp_rad=float(max(bcomp)), max_comp_dps=float(max(bcomp) * R2D), fall_peak=bf, ratio_gyro_acg=float(np.median(ratio)))
    gs = json.load(open(os.path.join(RES, "gyro_status.json")))
    wf = np.array(stat["weda"]["fall_peak"]); bfa = np.array(bf)
    fs = {k: {str(th): float((v > th).mean()) for th in (250, 500, 1000, 1500, 2000)} for k, v in (("weda_falls", wf), ("bits_falls_descriptive", bfa))}
    fs["weda_fall_peak_pct"] = dict(zip(("p50", "p75", "p90", "p95", "p99", "max"), [float(x) for x in np.percentile(wf, [50, 75, 90, 95, 99, 100])]))
    fs["bits_fall_peak_pct_descriptive"] = dict(zip(("p50", "p75", "p90", "p95", "p99", "max"), [float(x) for x in np.percentile(bfa, [50, 75, 90, 95, 99, 100])]))
    fs["weda_adl_peak_pct"] = dict(zip(("p50", "p95", "max"), [float(x) for x in np.percentile(stat["weda"]["adl_peak"], [50, 95, 100])]))
    json.dump(dict(stat=stat, fs=fs), open(os.path.join(RES, "gyro_fs.json"), "w"), indent=1)

    cnt = collections.Counter()
    for g in gs:
        key = (g["dataset"], g.get("group", "-"), "fall" if g.get("fall") else "adl")
        cnt[key + (g["ok"],)] += 1
    w = stat["weda"]; sy = stat["sfmm"]["young"]; so = stat["sfmm"]["old"]; b = stat["bits"]
    L = [MARK]; A = L.append
    A("Gyro is merged onto the **accelerometer's uniform grid** (then `resample_poly` to 26 Hz exactly like the accelerometer, so the two series are sample-aligned) and converted to **dps**. A segment is gyro-usable only if the gyro timestamps cover the accel segment to within 0.5 s with no gap > 1 s; otherwise it stays in the accelerometer-only analyses but is excluded from v3. "
      "The gyro series is never extrapolated, and BITS gyro parsing (`wrist_io.bits_gyro`) exists but is **unused**.\n")
    A("| item | WEDA-FALL | SmartFallMM young (Meta_wrist) | SmartFallMM old (Meta_wrist) | BITS wrist IMU+HR (descriptive only) |\n|---|---|---|---|---|")
    A(f"| file | `<code>/U<uid>_R<k>_gyro.csv` (same layout as accel) | `young/gyroscope/meta_wrist/S..A..T...csv` (epoch ms, ISO time, elapsed, x, y, z) | `old/gyroscope/meta_wrist/…csv` — **different format**: `YYYY-MM-DD HH:MM:SS.fff,x,y,z` (no epoch / elapsed); separate `meta_hip` folder exists | `gyro`-tagged block of the same CSV |")
    A(f"| units | **rad/s** (inferred: walking median |ω| = {w['walk_med_dps']:.0f} dps = {w['walk_med_dps']/R2D:.2f} rad/s; the README does not say) → ×57.2958 to dps | **dps** (inferred from the ±125 range below) | dps | rad/s (inferred: max {b['max_comp_rad']:.1f} rad/s = {b['max_comp_dps']:.0f} dps ≈ MPU6500 ±2000 dps) |")
    A(f"| rate | effective {w['rate_adl']:.1f} Hz ADL / {w['rate_fall']:.1f} Hz falls (same burst-stamped, class-dependent artifact as the accelerometer) | median {sy['rate_med']:.0f} Hz | median {so['rate_med']:.0f} Hz | n_gyro / n_acg median {b['ratio_gyro_acg']:.2f} |")
    n = lambda ds, grp, cls: (cnt[(ds, grp, cls, True)], cnt[(ds, grp, cls, True)] + cnt[(ds, grp, cls, False)])
    wf_, wa_ = n("WEDA", "-", "fall"), n("WEDA", "-", "adl")
    wu = sum(v for k, v in cnt.items() if k[0] == "WEDA" and k[3])
    A(f"| sync with accelerometer | first/last timestamps agree to ≤ 0.03 s in 95 % of trials (max 0.48 s); both streams use the per-trial linear time axis → {wu}/969 usable | young: gyro timestamps within 0.5 s of the accel start *and* end in only 71 % of trials; the rule above gives falls {n('SFMM','young','fall')[0]}/{n('SFMM','young','fall')[1]}, ADL {n('SFMM','young','adl')[0]}/{n('SFMM','young','adl')[1]} usable segments | old: **cropped separately from the accel files** — usable ADL segments {n('SFMM','old','adl')[0]}/{n('SFMM','old','adl')[1]}; clocks are assumed common (same device); cross-correlation of |ω| with accel dynamics is too weak (median peak 0.15–0.23) to verify | n/a |")
    A(f"| wrist separated out? | n/a | yes (`meta_wrist` folder) | **yes**: a separate `meta_wrist` folder exists and differs from `meta_hip` in {stat['sfmm_old_wrist_vs_hip']['pairs']-stat['sfmm_old_wrist_vs_hip']['identical']}/{stat['sfmm_old_wrist_vs_hip']['pairs']} paired trials (the README's 'Meta_hip_and_wrist' is two folders here) → old subjects are **kept** in v3 where synced | n/a |")
    A(f"| saturation | max |component| {w['max_comp_rad']:.1f} rad/s = {w['max_comp_dps']:.0f} dps (≈ ±2000 dps range); {w['n_clip']}/{w['n']} trials hold their maximum value on ≥ 3 samples | **±125 dps per axis**: {sy['frac_comp_between_124_126']*100:.0f} % of trials peak at ≈125 dps (|ω| capped near 216 dps); {sy['frac_fall_at_cap']*100:.0f} % of fall trials reach the cap; spurious outliers up to {sy['comp_max']:.0f} dps | same ±125 dps cap ({so['frac_comp_between_124_126']*100:.0f} % of trials), outliers up to {so['comp_max']:.0f} dps | max {b['max_comp_dps']:.0f} dps, no repeated maxima |")
    A("\n**Consequence for v3:** SmartFallMM's wrist gyro is a ±125 dps part and clips in almost every trial, while WEDA reaches ≈2000 dps. Pooled gyro features would therefore encode the dataset. v3 is evaluated on two populations (REPORT §): "
      "**WEDA-only, native range** (the realistic-sensor case) and **pooled, harmonised** (WEDA clipped to ±125 dps/axis before resampling, SmartFallMM natively clipped) as the cross-dataset check.\n")
    A("### 7.1 Gyro full scale needed (firmware feasibility)\n")
    A("Peak |ω| (vector norm, dps) over each trial; WEDA is the only dataset here whose sensor does not clip below the values of interest:\n")
    A("| set | p50 | p75 | p90 | p95 | p99 | max | share > 250 dps | > 500 | > 1000 | > 1500 | > 2000 |\n|---|---|---|---|---|---|---|---|---|---|---|---|")
    for lab, key, pk_ in (("WEDA falls (350)", "weda_falls", fs["weda_fall_peak_pct"]), ("BITS falls (328, descriptive only)", "bits_falls_descriptive", fs["bits_fall_peak_pct_descriptive"])):
        A(f"| {lab} | " + " | ".join(f"{pk_[k]:.0f}" for k in ("p50", "p75", "p90", "p95", "p99", "max")) + " | " + " | ".join(f"{fs[key][str(t)]*100:.0f} %" for t in (250, 500, 1000, 1500, 2000)) + " |")
    a_ = fs["weda_adl_peak_pct"]
    A(f"| WEDA ADL (619) | {a_['p50']:.0f} | – | – | {a_['p95']:.0f} | – | {a_['max']:.0f} | | | | | |")
    A("\nLSM6DS3TR-C gyro full-scale options are ±125 / 250 / 500 / 1000 / 2000 dps (datasheet fetch failed — see REPORT §Firmware feasibility; this list is from the part's published range and is **unverified here**).\n")
    p = os.path.join(RES, "DATA_CARD.md")
    s = open(p).read()
    i = s.find(MARK)
    s = (s[:i] if i >= 0 else s.rstrip("\n") + "\n") + "\n".join(L) + "\n"
    open(p, "w").write(s)
    print("DATA_CARD.md section 7 written")


if __name__ == "__main__":
    main()
