#!/usr/bin/env python3
"""analyze_live.py - per-phase summary of serial_log.py 'l' logs.

  analyze_live.py LOG [LOG ...] [--json OUT.json]

Phases come from the EVENT lines in each log:  'start NAME' ... 'end NAME'  (host-time stamped).
Single-point events 'cue NAME' open an 8 s window (a gesture cue) used for trigger matching.

Per phase it reports: number of stride windows, EVT TRIGGER count, the p distribution
(min / p25 / median / p75 / p95 / p99 / max), the share of windows whose max |a| exceeds 2 g
(LIVE '... max=<g> ...' is the window's max_mag feature), and max |a| percentiles.
For every TRIGGER it lists the 9 features (EVT TRIGGER_FEAT).
"""
import re
import sys
import json
import argparse
import datetime as dt
import numpy as np

LINE = re.compile(r"^(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d+) \| (.*)$")
KV = re.compile(r"(\w+)=([^\s]+)")


def ts(s):
    return dt.datetime.fromisoformat(s).timestamp()


def parse(path):
    wins, trig, feats, ev, other = [], [], [], [], []
    for raw in open(path):
        m = LINE.match(raw.rstrip("\n"))
        if not m:
            continue
        t, text = ts(m.group(1)), m.group(2)
        if text.startswith("EVENT "):
            ev.append((t, text[6:].strip()))
        elif text.startswith("LIVE up_ms="):
            d = dict(KV.findall(text))
            wins.append(dict(t=t, up_ms=int(d["up_ms"]), wi=int(d["wi"]), p=float(d["p"]), max=float(d["max"]), state=d["state"], pend=int(d["pend"])))
        elif text.startswith("EVT TRIGGER_FEAT"):
            d = dict(KV.findall(text))
            feats.append(dict(t=t, **{k: float(v) for k, v in d.items() if k not in ("up_ms", "wi")}, up_ms=int(d["up_ms"]), wi=int(d["wi"])))
        elif text.startswith("EVT TRIGGER"):
            d = dict(KV.findall(text))
            trig.append(dict(t=t, up_ms=int(d["up_ms"]), wi=int(d["wi"]), p=float(d["p"])))
        elif text.startswith("EVT ") or text.startswith("LIVE samples") or text.startswith("HOST"):
            other.append((t, text))
    return wins, trig, feats, ev, other


def phases(ev):
    out, open_ = [], {}
    for t, text in ev:
        w = text.split(None, 1)
        if len(w) == 2 and w[0] == "start":
            open_[w[1]] = t
        elif len(w) == 2 and w[0] == "end" and w[1] in open_:
            out.append((w[1], open_.pop(w[1]), t))
    return out


def pct(a, ps):
    return [float(x) for x in np.percentile(a, ps)] if len(a) else [float("nan")] * len(ps)


def summarize(path):
    wins, trig, feats, ev, other = parse(path)
    res = {"log": path.split("/")[-1], "phases": []}
    for name, t0, t1 in phases(ev):
        w = [x for x in wins if t0 <= x["t"] <= t1]
        tr = [x for x in trig if t0 <= x["t"] <= t1]
        fe = [x for x in feats if t0 <= x["t"] <= t1]
        p = np.array([x["p"] for x in w]); mx = np.array([x["max"] for x in w])
        res["phases"].append(dict(
            phase=name, dur_s=t1 - t0, windows=len(w), triggers=len(tr),
            p_pct=dict(zip(("min", "p25", "median", "p75", "p95", "p99", "max"), pct(p, [0, 25, 50, 75, 95, 99, 100]))),
            max_pct=dict(zip(("min", "median", "p95", "max"), pct(mx, [0, 50, 95, 100]))),
            n_max_gt_2g=int((mx > 2.0).sum()), frac_max_gt_2g=float((mx > 2.0).mean()) if len(mx) else float("nan"),
            n_p_ge_thr=int((p >= 0.835).sum()), trigger_features=fe, trigger_p=[x["p"] for x in tr]))
    cues = [(t, text.split(None, 1)[1]) for t, text in ev if text.startswith("cue ")]
    res["cues"] = []
    for t, name in cues:
        tr = [x for x in trig if t <= x["t"] <= t + 8.0]
        w = [x for x in wins if t <= x["t"] <= t + 8.0]
        res["cues"].append(dict(cue=name, t=t, triggers_in_8s=len(tr), max_p_in_8s=max([x["p"] for x in w], default=float("nan")),
                                max_g_in_8s=max([x["max"] for x in w], default=float("nan")), trigger_p=[x["p"] for x in tr]))
    res["totals"] = dict(windows=len(wins), triggers=len(trig), events=[text for _, text in ev][:50])
    res["confirm_lines"] = [text for _, text in other if text.startswith("EVT CONFIRMED") or text.startswith("EVT CANCELLED") or text.startswith("EVT ERROR")]
    res["summary_line"] = [text for _, text in other if text.startswith("LIVE samples")]
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("logs", nargs="+")
    ap.add_argument("--json")
    a = ap.parse_args()
    allr = [summarize(p) for p in a.logs]
    for r in allr:
        print("##", r["log"], r["summary_line"])
        for ph in r["phases"]:
            pp, mm = ph["p_pct"], ph["max_pct"]
            print(f"  {ph['phase']:<22} {ph['dur_s']:.0f}s windows={ph['windows']:<4} triggers={ph['triggers']:<3} "
                  f"p[min/med/p95/max]={pp['min']:.4f}/{pp['median']:.4f}/{pp['p95']:.4f}/{pp['max']:.4f}  "
                  f"max|a|>2g: {ph['n_max_gt_2g']}/{ph['windows']} ({ph['frac_max_gt_2g']*100:.1f}%)  max|a| med/p95/max={mm['median']:.2f}/{mm['p95']:.2f}/{mm['max']:.2f} g")
        for c in r["cues"]:
            print(f"  cue {c['cue']:<18} triggers in 8 s={c['triggers_in_8s']} max p={c['max_p_in_8s']:.4f} max|a|={c['max_g_in_8s']:.2f} g")
    if a.json:
        json.dump(allr, open(a.json, "w"), indent=1, default=float)


if __name__ == "__main__":
    main()
