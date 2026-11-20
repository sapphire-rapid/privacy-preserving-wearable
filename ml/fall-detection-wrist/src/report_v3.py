"""Markdown sections for the operating curve (acc-only), the gyro comparison, the stillness finding and firmware feasibility.
Imported by make_report.py; also writes results/ADL_BREAKDOWN.md and results/SUMMARY_V3.md."""
import os
import sys
import json
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import evalcore as E
import features as F
from eval_curve import TARGETS, NAMES

ROOT = os.path.dirname(HERE)
RES = os.path.join(ROOT, "results")
LABEL = {"acc9_lr": "(i) acc9, LR", "gyro15_lr": "(ii) acc9 + gyro (15), LR", "l1sel_lr": "(iii) L1-selected subset, LR", "gyro15_tree": "(ii) acc9 + gyro (15), tree depth ≤ 5"}


def summ(ds, model):
    return pd.read_csv(os.path.join(RES, f"curve_{ds}_{model}_summary.csv"))


def outc(ds, model):
    return pd.read_csv(os.path.join(RES, f"curve_{ds}_{model}_outcomes.csv"))


def cell(s, t, m, pct=True, count=True, dec=2):
    r = s[(s.target == t) & (s.metric == m)]
    if r.empty or not np.isfinite(r.value.iloc[0]):
        return "n/a"
    r = r.iloc[0]
    if pct:
        out = f"{r.value*100:.1f}% [{r.lo*100:.1f}, {r.hi*100:.1f}]"
        return out + (f" ({int(r.n_num)}/{int(r.n_den)})" if count else "")
    return f"{r.value:.{dec}f} [{r.lo:.{dec}f}, {r.hi:.{dec}f}]"


def curve_table():
    s = summ("pool26", "acc9_lr")
    L = ["| recall target | scope | fall recall (trigger-only) | ADL false alarms per trial | alarmed ADL trials per ADL hour | alarm events per ADL hour (< 5 s merged) |", "|---|---|---|---|---|---|"]
    for t in TARGETS:
        for lab, suf in (("pooled", ""), ("WEDA", "[WEDA]"), ("SmartFallMM", "[SFMM]")):
            L.append(f"| {int(t*100)} % | {lab} | {cell(s,t,'fall_recall_trigger'+suf)} | {cell(s,t,'adl_far_trigger'+suf)} | {cell(s,t,'fa_per_hour_trigger_trials'+suf,False,False)} | {cell(s,t,'fa_per_hour_trigger_events'+suf,False,False)} |")
    return "\n".join(L)


def breakdown_md(ds, model, targets=(0.90, 0.95)):
    o = outc(ds, model)
    out = []
    for t in targets:
        b = E.adl_breakdown(o[o.target == t], NAMES, 5)
        out.append(f"**{LABEL.get(model, model)} — recall target {int(t*100)} %** (ADL trials alarmed / trials, share of that dataset's false alarms)\n")
        out.append("| dataset | activity | alarmed / trials | false-alarm rate per trial | alarmed trials per hour of that activity | share of dataset's false alarms |\n|---|---|---|---|---|---|")
        for _, r in b.iterrows():
            out.append(f"| {r.dataset} | {r.ftype} {r.activity} | {int(r.alarmed)}/{int(r.trials)} | {r.far*100:.0f}% | {r.alarmed_per_hour:.0f} | {r.share_of_dataset_FAs*100:.0f}% |")
        out.append("")
    return "\n".join(out)


def cmp_table(ds):
    models = ["acc9_lr", "gyro15_lr", "l1sel_lr", "gyro15_tree"]
    S_ = {m: summ(ds, m) for m in models}
    L = ["| recall target | model | fall recall | ADL false alarms / trial | alarmed ADL trials / h | alarm events / h |", "|---|---|---|---|---|---|"]
    for t in TARGETS:
        for m in models:
            s = S_[m]
            L.append(f"| {int(t*100)} % | {LABEL[m]} | {cell(s,t,'fall_recall_trigger')} | {cell(s,t,'adl_far_trigger')} | {cell(s,t,'fa_per_hour_trigger_trials',False,False)} | {cell(s,t,'fa_per_hour_trigger_events',False,False)} |")
    return "\n".join(L)


def paired_table(ds):
    base = outc(ds, "acc9_lr")
    L = ["| recall target | comparison | Δ fall recall (pp) | Δ ADL false alarms / trial (pp; negative = fewer) |", "|---|---|---|---|"]
    for t in TARGETS:
        for m in ("gyro15_lr", "l1sel_lr", "gyro15_tree"):
            o = outc(ds, m)
            d = E.paired_diff(o[o.target == t], base[base.target == t], ["fall_recall_trigger", "adl_far_trigger"])
            r = d.set_index("metric")
            L.append(f"| {int(t*100)} % | {LABEL[m]} − {LABEL['acc9_lr']} | {r.loc['fall_recall_trigger','diff']*100:+.1f} [{r.loc['fall_recall_trigger','lo']*100:+.1f}, {r.loc['fall_recall_trigger','hi']*100:+.1f}] | {r.loc['adl_far_trigger','diff']*100:+.1f} [{r.loc['adl_far_trigger','lo']*100:+.1f}, {r.loc['adl_far_trigger','hi']*100:+.1f}] |")
    return "\n".join(L)


def l1_table(ds):
    f = pd.read_csv(os.path.join(RES, f"curve_{ds}_l1sel_lr_folds.csv"))
    cnt = {}
    for sel in f.selected.fillna(""):
        for n in sel.split():
            cnt[n] = cnt.get(n, 0) + 1
    L = ["| outer fold | chosen C | selected features |", "|---|---|---|"]
    for _, r in f.iterrows():
        L.append(f"| {int(r.fold)} | {r.C} | {r.selected} |")
    L.append("")
    L.append("Selection frequency over the 5 outer folds: " + ", ".join(f"{k} {v}/5" for k, v in sorted(cnt.items(), key=lambda kv: -kv[1])))
    return "\n".join(L)


def summary_table():
    """acc-only vs acc+gyro at each recall target (recall, ADL FAR/trial, alarmed ADL trials/h) for both populations."""
    L = ["| recall target | population | acc9 LR: recall / ADL FA per trial / FA per h | acc9+gyro LR | L1 subset LR | acc9+gyro tree |", "|---|---|---|---|---|---|"]
    for t in TARGETS:
        for ds, lab in (("v3W", "WEDA only (native ±2000 dps)"), ("v3P", "pooled, harmonised ±125 dps")):
            cells = []
            for m in ("acc9_lr", "gyro15_lr", "l1sel_lr", "gyro15_tree"):
                s = summ(ds, m)
                g = lambda k: s[(s.target == t) & (s.metric == k)].value.iloc[0]
                cells.append(f"{g('fall_recall_trigger')*100:.1f}% / {g('adl_far_trigger')*100:.1f}% / {g('fa_per_hour_trigger_trials'):.1f}")
            L.append(f"| {int(t*100)} % | {lab} | " + " | ".join(cells) + " |")
    return "\n".join(L)


def gyro_fs_md():
    g = json.load(open(os.path.join(RES, "gyro_fs.json")))["fs"]
    w = g["weda_fall_peak_pct"]
    L = ["- **Gyro full scale.** Peak |ω| of WEDA falls (sensor limit ≈ 2000 dps, so the upper tail is itself clipped): median {p50:.0f}, p90 {p90:.0f}, p95 {p95:.0f}, p99 {p99:.0f}, max {mx:.0f} dps; "
         "{a:.0f}% of falls exceed ±500 dps, {b:.0f}% exceed ±1000, {c:.0f}% exceed ±1500. BITS falls (descriptive only, no clipping): median {bp50:.0f}, p95 {bp95:.0f}, max {bmx:.0f} dps. "
         "**±2000 dps is needed to avoid clipping the upper tail; ±1000 dps would clip ≈{b2:.0f}% of falls near the impact (the features use the maximum and the integrated angle), ±500 dps ≈{b1:.0f}%.** "
         "SmartFallMM's ±125 dps part cannot tell (it saturates in {sat:.0f}% of its falls) — which is also why the pooled gyro result is a lower bound.".format(
             p50=w["p50"], p90=w["p90"], p95=w["p95"], p99=w["p99"], mx=w["max"], a=g["weda_falls"]["500"] * 100, b=g["weda_falls"]["1000"] * 100, c=g["weda_falls"]["1500"] * 100,
             bp50=g["bits_fall_peak_pct_descriptive"]["p50"], bp95=g["bits_fall_peak_pct_descriptive"]["p95"], bmx=g["bits_fall_peak_pct_descriptive"]["max"],
             b2=g["weda_falls"]["1000"] * 100, b1=g["weda_falls"]["500"] * 100,
             sat=json.load(open(os.path.join(RES, "gyro_fs.json")))["stat"]["sfmm"]["young"]["frac_fall_at_cap"] * 100)]
    L.append("- **LSM6DS3TR-C gyro supply current at 26 Hz: UNVERIFIED.** The ST datasheet fetch timed out twice and the Digi-Key/Mouser copies were not reachable by the fetch tool; a web search returned only combined figures "
             "(ST product page: 0.90 mA in high-performance mode; LSM6DS3 datasheet: 0.9 mA combo normal mode, 1.25 mA combo high-performance mode, low-power mode available at ODR 12.5/26/52 Hz via the G_HM_MODE bit in CTRL7_G) "
             "— these are the sibling-part/combined numbers, **not** the gyro-only 26 Hz figure needed here. Sources: [ST product page](https://st.com/en/mems-and-sensors/lsm6ds3tr-c.html), "
             "[LSM6DS3 datasheet (Arduino mirror)](https://docs.arduino.cc/resources/datasheets/LSM6DS3-datasheet.pdf). Read the gyro rows of the 'electrical characteristics' table before committing to a power budget.")
    L.append("- **Firmware impact of adding the gyro (not implemented):** `imu.c` already configures the gyro (`.gyro_odr = LSM6DSXX_DATA_RATE_52HZ`, **`.gyro_fs = LSM6DSXX_GYRO_FS_245DPS`**, no decimation; grep finds no other gyro reference, so it is configured but never read). "
             "The current ±245 dps setting would clip essentially every fall (100% of WEDA falls exceed 250 dps), so v3 needs FS raised to 2000 dps (sensitivity falls from 8.75 to 70 mdps/LSB — datasheet values, unverified here), the gyro ODR set to 26 Hz, "
             "and a read path that delivers sample-aligned |ω| and |a| (whether the two sensors share an ODR clock at equal rates is **not verified here**). The six gyro features are norms and angle sums, hence invariant to sensor orientation (checked in `test_gyro_features.py`) — no axis calibration is needed.")
    return "\n".join(L)


def stillness_md():
    return open(os.path.join(RES, "stillness_finding.md")).read().split("\n", 2)[2].replace("\n## ", "\n### ")


def write_extra():
    """results/ADL_BREAKDOWN.md (all populations, models, targets) and results/SUMMARY_V3.md."""
    L = ["# ADL false-alarm breakdown (top 5 activities per dataset, trigger-only)\n"]
    for ds, ms in (("pool26", ["acc9_lr"]), ("v3W", ["acc9_lr", "gyro15_lr", "l1sel_lr", "gyro15_tree"]), ("v3P", ["acc9_lr", "gyro15_lr", "l1sel_lr", "gyro15_tree"])):
        L.append(f"## Population {ds}\n")
        for m in ms:
            L.append(breakdown_md(ds, m, TARGETS))
    open(os.path.join(RES, "ADL_BREAKDOWN.md"), "w").write("\n".join(L) + "\n")
    open(os.path.join(RES, "SUMMARY_V3.md"), "w").write("# Accelerometer-only vs accelerometer + gyro\n\nCells: fall recall / ADL false alarms per trial / alarmed ADL trials per hour (point estimates; CIs in REPORT.md section 6).\n\n" + summary_table() + "\n")
