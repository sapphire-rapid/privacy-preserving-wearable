# Post-impact stillness (finding; not a detection criterion)

Fall trials with peak p = argmax|a|; 'reaches stillness within T s' = some start in [p, p+T] is followed by L s of |a| with std < thr and |mean − 1| < 0.2. Only trials with ≥ T + L s of data after the peak are counted (others cannot be judged).

## Placeholder long-lie setting: L = 3 s, std < 0.08, |mean−1| < 0.2

| dataset | horizon | falls with enough post-peak data (≥ T+L s) / all falls | reached stillness within T | median time to stillness (s) |
|---|---|---|---|---|
| WEDA | 3 s | 231/350 | 91.8% (212/231) | 0.88 |
| WEDA | 5 s | 90/350 | 98.9% (89/90) | 0.88 |
| WEDA | 10 s | 2/350 | 100.0% (2/2) | 2.40 |
| SFMM | 3 s | 182/691 | 22.5% (41/182) | 0.58 |
| SFMM | 5 s | 62/691 | 30.6% (19/62) | 0.50 |
| SFMM | 10 s | 11/691 | 45.5% (5/11) | 5.23 |
| pooled | 3 s | 413/1041 | 61.3% (253/413) | 0.85 |
| pooled | 5 s | 152/1041 | 71.1% (108/152) | 0.88 |
| pooled | 10 s | 13/1041 | 53.8% (7/13) | 4.65 |

## Sensitivity: L = 3 s, std < 0.05

| dataset | horizon | falls with enough post-peak data (≥ T+L s) / all falls | reached stillness within T | median time to stillness (s) |
|---|---|---|---|---|
| WEDA | 3 s | 231/350 | 82.7% (191/231) | 1.00 |
| WEDA | 5 s | 90/350 | 92.2% (83/90) | 1.04 |
| WEDA | 10 s | 2/350 | 100.0% (2/2) | 5.08 |
| SFMM | 3 s | 182/691 | 12.1% (22/182) | 0.77 |
| SFMM | 5 s | 62/691 | 21.0% (13/62) | 0.77 |
| SFMM | 10 s | 11/691 | 18.2% (2/11) | 3.48 |
| pooled | 3 s | 413/1041 | 51.6% (213/413) | 1.00 |
| pooled | 5 s | 152/1041 | 63.2% (96/152) | 1.04 |
| pooled | 10 s | 13/1041 | 30.8% (4/13) | 3.48 |

## Sensitivity: L = 3 s, std < 0.12

| dataset | horizon | falls with enough post-peak data (≥ T+L s) / all falls | reached stillness within T | median time to stillness (s) |
|---|---|---|---|---|
| WEDA | 3 s | 231/350 | 95.7% (221/231) | 0.73 |
| WEDA | 5 s | 90/350 | 100.0% (90/90) | 0.73 |
| WEDA | 10 s | 2/350 | 100.0% (2/2) | 2.19 |
| SFMM | 3 s | 182/691 | 37.4% (68/182) | 0.38 |
| SFMM | 5 s | 62/691 | 46.8% (29/62) | 0.31 |
| SFMM | 10 s | 11/691 | 81.8% (9/11) | 4.54 |
| pooled | 3 s | 413/1041 | 70.0% (289/413) | 0.65 |
| pooled | 5 s | 152/1041 | 78.3% (119/152) | 0.65 |
| pooled | 10 s | 13/1041 | 84.6% (11/13) | 4.31 |

## Sensitivity: L = 1 s, std < 0.08

| dataset | horizon | falls with enough post-peak data (≥ T+L s) / all falls | reached stillness within T | median time to stillness (s) |
|---|---|---|---|---|
| WEDA | 3 s | 336/350 | 98.5% (331/336) | 1.00 |
| WEDA | 5 s | 231/350 | 100.0% (231/231) | 1.00 |
| WEDA | 10 s | 11/350 | 100.0% (11/11) | 1.12 |
| SFMM | 3 s | 298/691 | 86.2% (257/298) | 0.92 |
| SFMM | 5 s | 182/691 | 94.0% (171/182) | 0.81 |
| SFMM | 10 s | 17/691 | 100.0% (17/17) | 0.58 |
| pooled | 3 s | 634/1041 | 92.7% (588/634) | 0.96 |
| pooled | 5 s | 413/1041 | 97.3% (402/413) | 0.96 |
| pooled | 10 s | 28/1041 | 100.0% (28/28) | 0.92 |
