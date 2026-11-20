# Wrist fall detection (branch `wrist-retrain`)

Same 9 features and logistic-regression pipeline as `../fall-detection`, retrained on wrist data at 26 Hz
(WEDA-FALL + SmartFallMM Meta_wrist; BITS wrist IMU+HR held out). Start with `results/REPORT.md`; the data card is `results/DATA_CARD.md`.

| path | contents |
|---|---|
| `src/` | loaders, preprocessing, features, nested evaluation, baseline, final model, exporter, C parity, report generator (commands at the end of `results/REPORT.md`) |
| `include/` | drop-in `fall_model.h` / `test_windows.h` (the same pair is installed in `../../firmware/fall_imu/include/`) |
| `results/` | report, data card, per-trial outcome and summary CSVs, parity result |
| `cache/`, `.venv/` | derived data and the virtualenv — git-ignored (derived signals must not be redistributed) |

## Data sources and attribution

Raw data live outside the repo (`~/datasets/wrist`, read-only) and are **not redistributed**: no raw or resampled signal files are
committed. What is committed is code, trained weights, aggregate and per-trial *outcome* tables (trial ids, probabilities, durations — no
signal samples) and the C test vectors below.

* **WEDA-FALL** — J. Marques and P. Moreno, "Online Fall Detection Using Wrist Devices", *Sensors* 2023, 23(3), 1146,
  <https://www.mdpi.com/1424-8220/23/3/1146>; dataset: <https://github.com/joaojtmarques/WEDA-FALL>.
  `test_windows.h` contains 18 short WEDA-FALL excerpts used as test vectors; credit to the original authors.
* **SmartFallMM** — SmartFall Group, Texas State University, "SmartFallMM: A multimodal dataset for fall detection using commodity devices"
  (IEEE, <https://ieeexplore.ieee.org/abstract/document/11651591>; <https://github.com/txst-cs-smartfall/SmartFallMM-Dataset>).
  **© SmartFall Group, all rights reserved; credit required.** Only the Meta_wrist accelerometer (and, for an ablation, the wrist gyro) was
  read; nothing derived from its signals is committed except trial ids and model outcomes.
* **BITS wrist IMU+HR dataset** (folder named `bits_geriatric`, volunteers aged 20–47) — S. Nandi et al., *Data in Brief* 52 (2024) 109812,
  doi:10.1016/j.dib.2023.109812, licence CC BY 4.0 (verified on Zenodo). Used once, as a held-out test (`src/eval_bits.py`); only per-trial outcomes and aggregate
  statistics are committed.
