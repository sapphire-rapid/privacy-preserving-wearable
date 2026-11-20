"""Append/refresh '## 5. Exclusion log' in results/DATA_CARD.md from results/exclusions.json + BITS rule flags."""
import os
import json
import pickle
import collections

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
RES = os.path.join(ROOT, "results")
MARK = "\n## 5. Exclusion log (Step 2 preprocessing)\n"

excl = json.load(open(os.path.join(RES, "exclusions.json")))
bits = pickle.load(open(os.path.join(ROOT, "cache", "bits.pkl"), "rb"))
L = [MARK]
A = L.append
A("Rules (all fixed before any model was trained): SmartFallMM — ISO time string as clock; split at |gap| > 1 s; drop samples with non-increasing timestamps; "
  "drop segments < 2 s; fall trials keep only the segment containing the |a| peak; ADL files with median |a| outside 0.5–2 g are not in g and are dropped. "
  "WEDA — nothing excluded; per-trial linear time axis. BITS — `acg`, drop files whose rest |a| is not 1 ± 0.1 g.\n")
kinds = collections.Counter()
for e in excl:
    k = e.get("kind", "file")
    kinds[(e["dataset"], k, "fall" if e.get("fall") else "adl")] += 1
A("| dataset | action | class | count |\n|---|---|---|---|")
for (ds, k, c), n in sorted(kinds.items()):
    A(f"| {ds} | {k if k != 'file' else 'file dropped'} | {c} | {n} |")
nonG = [e for e in excl if e["reason"].startswith("not in g")]
A(f"\n**SmartFallMM non-g files dropped ({len(nonG)}):** " + ", ".join(sorted(e["file"][:-4] for e in nonG)) + ".\n")
short = [e for e in excl if e.get("kind") == "segment"]
A(f"**SmartFallMM segments dropped** ({len(short)}):\n")
for e in short:
    A(f"- {e['file']}: {e['reason']}")
trial = [e for e in excl if e.get("kind") == "trial"]
A(f"\n**SmartFallMM fall trials lost entirely:** {len(trial)}" + (": " + ", ".join(e['file'] for e in trial) if trial else "") + ".\n")
spl = [e for e in excl if e.get("kind") == "split"]
A(f"**SmartFallMM files split at gaps > 1 s ({len(spl)}):** " + "; ".join(f"{e['file'][:-4]} ({e['reason'].split('into ')[1]})" for e in spl) + ".\n")
smp = [e for e in excl if e.get("kind") == "samples"]
A(f"**SmartFallMM segments with non-increasing-timestamp samples removed ({len(smp)}):** " + "; ".join(f"{e['file'][:-4]} ({e['reason'].split(': ')[1]})" for e in smp) + ".\n")

b4 = [r for r in bits if not r["rule4_pass"]]
A("### BITS selection counts (pre-specified rules)\n")
A(f"- Rule 4 (rest |a| of `acg` within 1 ± 0.1 g): **{len(b4)}** of {len(bits)} files fail ({sum(r['is_fall'] for r in b4)} falls, {sum(not r['is_fall'] for r in b4)} ADL); "
  f"{len(bits)-len(b4)} remain ({sum(r['is_fall'] for r in bits if r['rule4_pass'])} falls, {sum(not r['is_fall'] for r in bits if r['rule4_pass'])} ADL). Failing files: " + ", ".join(sorted(r["trial_id"] for r in b4)) + ".")
ok4 = [r for r in bits if r["rule4_pass"]]
b5 = [r for r in ok4 if not r["rule5_pass"]]
A(f"- Rule 5 (|first→last timestamp span − N/20| > 10 % ⇒ drop, timestamps taken as ns): **{len(b5)}** of {len(ok4)} remaining files fail "
  f"({sum(r['is_fall'] for r in b5)} of {sum(r['is_fall'] for r in ok4)} falls). **Skipped by decision**: it would leave {len(ok4)-len(b5)} files, and the check is uninformative because timestamps carry only 3 significant digits "
  "(see §0.5). **Assumption: BITS is 20 Hz by sample order** (nominal rate from the dataset paper; not verifiable from the files). The BITS run is on hold.")
A("\n## 6. Addenda after the BITS paper lookup\n")
A("Read by a sub-agent from https://pmc.ncbi.nlm.nih.gov/articles/PMC10709028/ (Nandi et al., Data in Brief 52 (2024) 109812); not independently re-verified:\n"
  "- 41 volunteers, **ages 20–47 (mean ≈ 27.9)**, 27 male / 14 female — i.e. an adult cohort, **not geriatric** (the on-disk folder is still called `bits_geriatric`); wrist-worn device (Snapdragon 820c, MPU6500, MAX30102).\n"
  "- 16 ADLs and 8 falls, 5 repeats each; motion sensors 20 Hz, HR 1 Hz. The article's tag descriptions say `acc` = accelerometer and `acg` = *linear* accelerometer — **the opposite of what the data show** (`acg` carries gravity, rest ≈ 9.81 m/s²; `acc` rest ≈ 0.14 m/s²). The measurement is used, not the prose.\n"
  "- ADL list: 1 walking slowly, 2 walking quickly, 3 jogging, 4 jumping, 5 climbing up slowly, 6 climbing down slowly, 7 climbing up normally, 8 climbing down normally, 9 slowly sitting on chair, 10 rapidly sitting on chair, 11 nearly sitting and getting up, 12 swinging hands, 13 lying on bed, 14 lying on back and getting up slowly, 15 … normally, 16 sideways → back transition.\n"
  "- Fall list: 1 forward fall landing on knee, 2 right fall, 3 left fall, 4 forward fall, 5 seated on bed falling to ground, 6 forward fall, body weight on hand, 7 backward fall from seated, 8 grabbing while falling.\n"
  "- The article does not state the CSV naming. Each user has exactly 16 `adl` and 8 `fall` files (one per Sr No), and per-index motion energy follows the table (median std of |acg|: adl3 jogging 0.96 g and adl4 jumping 1.17 g highest; adl13 lying on bed 0.02 g lowest; "
  "seated falls 5 and 7 have the smallest peaks, 2.9 and 2.5 g). **Index → activity mapping is therefore inferred, consistent with the data, but undocumented.**\n")
p = os.path.join(RES, "DATA_CARD.md")
s = open(p).read()
i = s.find(MARK)
s = (s[:i] if i >= 0 else s.rstrip("\n") + "\n") + "\n".join(L) + "\n"
open(p, "w").write(s)
print("DATA_CARD.md updated")
