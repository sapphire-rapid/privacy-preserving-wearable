# Data

The raw dataset and the derived feature matrices are **not** stored in this repository (they are large and covered by `.gitignore`). This folder only documents where the data comes from and how to rebuild it locally.

## Source dataset: SisFall

The fall-detection model is trained on **SisFall**, a public dataset of simulated falls and activities of daily living (ADL):

> A. Sucerquia, J. D. López, and J. F. Vargas-Bonilla, "SisFall: A Fall and Movement Dataset," *Sensors*, vol. 17, no. 1, p. 198, 2017. doi:10.3390/s17010198

| Property | Value |
|---|---|
| Subjects | 38 (23 young adults, 15 elderly) |
| Recordings | 4505 trials (falls + ADLs) |
| Sensor used here | ADXL345 accelerometer only (the dataset's other sensors are ignored) |
| Original rate | 200 Hz |
| Rate used here | resampled to **52 Hz** to match the LSM6DS3TR-C IMU on the XIAO nRF52840 Sense |
| Window | 2 s |

The dataset's original download page is no longer reliably reachable. Obtain a copy from the authors (contact details are in the paper above) or from a mirror that redistributes it under the original terms, and cite the paper in any derived work.

## Expected local layout

```
ml/fall-detection/data/
├── README.md            (this file, tracked)
├── SisFall_dataset/     raw .txt trials, one folder per subject (SA01…SA23, SE01…SE15)  — not tracked
└── *.csv                derived per-window feature matrices                            — not tracked
```

## Rebuilding the features

From `ml/fall-detection/`:

```bash
python src/features_v2.py            # raw trials -> data/features_v2.csv (9 magnitude/tilt features per 2 s window)
python src/eval_trial_v2.py          # trial-level threshold sweep -> data/features_trials_v2.csv, results/trial_sweep_v2_*.csv
python src/eval_confirm_nested.py    # subject-wise nested CV with stillness confirmation -> results/nested_result.txt
python src/export_final.py           # final LR on all 38 subjects -> include/fall_model.h, include/test_windows.h
```

(`src/train.py` and `src/features.py` are the earlier v1 magnitude-only pipeline, kept for comparison.)

Feature definitions are specified exactly in [`include/FEATURES_SPEC.md`](../include/FEATURES_SPEC.md). The firmware port must follow that spec, not the test vectors.
