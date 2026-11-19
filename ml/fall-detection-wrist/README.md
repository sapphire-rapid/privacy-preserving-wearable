# Wrist fall detection (branch `wrist-retrain`)

Same 9 features and logistic-regression pipeline as `../fall-detection`, retrained on wrist data at 26 Hz
(WEDA-FALL + SmartFallMM Meta_wrist; BITS held out). Start with `results/REPORT.md`; the data card is `results/DATA_CARD.md`.

| path | contents |
|---|---|
| `src/` | loaders, preprocessing, features, nested evaluation, baseline, final model, exporter, C parity, report generator (commands at the end of `results/REPORT.md`) |
| `include/` | drop-in `fall_model.h` / `test_windows.h` (provisional operating point; `firmware/fall_imu/include/` is untouched) |
| `results/` | report, data card, per-trial outcome and summary CSVs, parity result |
| `cache/`, `.venv/` | derived data and the virtualenv — git-ignored (SmartFallMM-derived data must not be redistributed) |

Raw data live outside the repo (`~/datasets/wrist`, read-only).
SmartFallMM: © SmartFall Group, Texas State University, all rights reserved, credit required —
"SmartFallMM: A multimodal dataset for fall detection using commodity devices" (IEEE),
https://github.com/txst-cs-smartfall/SmartFallMM-Dataset.
