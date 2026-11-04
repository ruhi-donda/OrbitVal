# Detector-validation project log (CS462)

Running record of every design decision, every deviation from the
approved plan, and every result, so each number in the presentation can
be traced to a choice and a commit. Updated at the end of every stage.

- Branch: `feature/ml-detector-eval`
- Presentation: 2026-11-13
- Code: `orbitval/ml/` (core OrbitVal does not import it)

## Status

| Stage | Scope | Target | Status | Commit |
|---|---|---|---|---|
| 0+1 | `ml` extra, telemanom loader, windowing, persistence baseline, metrics, threshold | — | done | `83863f4`, `fcc5ba9` |
| 2 | Telemetry generator, severity-scaled faults, onset labels, detectability map | Nov 5 | done (Nov 3) | `a486573` |
| 3 | Small LSTM + GRU, 3 seeds, no ablations | Nov 7 | next | — |
| 5 | Streamlit demo (runs before Stage 4) | Nov 9 | pending | — |
| 4 | `scripts/reproduce.sh` + README results only | after 5 | pending | — |
| 6 | Transformer | only if all else is done | dropped for now | — |

## Decisions

Each entry: what was decided, why, and where it lives.

### Data (SMAP/MSL)

**D1. Univariate, column 0 only.**
Each telemanom `.npy` has the telemetry value in column 0 and one-hot
command flags after it. Only column 0 is kept. One shared model per
spacecraft is far cheaper than telemanom's one-model-per-channel, and
the number of command columns differs (SMAP 25, MSL 55).
*Cost:* the models can't use command information that telemanom uses.
`orbitval/ml/data/telemanom.py`

**D2. Chronological 80/20 train/val split.**
Validation is the last 20% of each channel's train series, never
shuffled. It is all normal data and is used for (a) early stopping in
Stage 3 and (b) setting the alarm threshold.
`load_spacecraft(val_frac=0.2)`

**D3. Channels split into dev and held-out groups (30/70, seed 0).**
*Deviation from the plan,* which said "baseline numbers on validation".
Validation contains no anomalies, so recall can't be measured on it.
Instead the channels are split once with a fixed seed:
- SMAP: 53 channels → 16 dev / 37 held-out
- MSL: 27 channels → 8 dev / 19 held-out

Results looked at while building come only from dev channels' test
series. Held-out channels' test series are scored once, by
`scripts/reproduce.sh` (Stage 4).
Thresholds are calibrated on the validation series of **all** channels,
including held-out ones. That uses only their normal training data,
never their test series or labels.
`split_channels()`, `run_telemanom.py`

**D4. P-2 is skipped.**
`labeled_anomalies.csv` lists P-2 twice with the same length (8209) but
different windows: [5300, 6420] and [5350, 6575]. Nothing in the data
says which is correct. Picking one would move the detection delay by up
to 50 steps, so the channel is left out with a warning.
`_pick_row()` raises `AmbiguousLabels`; commit `fcc5ba9`.

**D5. Unlabeled T-10 is ignored.**
The Kaggle copy ships `T-10.npy`, which has no row in the CSV. Only
channels listed in the CSV are loaded.

**D6. Data source is the Kaggle mirror.**
The original S3 link (`s3-us-west-2.amazonaws.com/telemanom/data.zip`)
returns 403 Forbidden. The telemanom README now points to Kaggle
(`patrickfleith/nasa-anomaly-detection-dataset-smap-msl`), downloaded
manually and copied into `data/telemanom/` (git-ignored).

### Scoring and evaluation (shared by both datasets)

**D7. One shared scoring pipeline: smoothed error, then rolling z-score.**
Every detector produces only a forecast. The score is always
`|x - forecast|` → EWMA (span 10) → causal rolling z-score
(trailing 250 steps, current step excluded, std floor 1e-3).
- Detectors differ only in the forecaster, so a difference in results
  can't come from post-processing.
- The z-score puts every channel on the same scale, which lets one
  threshold serve all channels of a spacecraft.
- This is how "persistence + rolling z-score" from the plan is read:
  persistence is the forecaster, the z-score is the shared normalisation.

*Known side effect:* during a long anomaly the window fills with
anomalous errors and the score fades. Event recall and delay only need
the first alarm, so they aren't affected. Point-wise recall is, which
is one reason point F1 isn't the headline metric.
`orbitval/ml/scoring.py`

**D8. 320-step warm-up, the same for every detector.**
Test series and missions start with no history. The rolling z-score
needs 250 smoothed errors, and the neural models will need a 64-step
input window, so the first 320 steps are never scored, for any
detector. An event lying entirely inside the warm-up is reported as
"unscoreable" instead of counted as a miss. So far there are none.
`EVAL_WARMUP` in `orbitval/ml/evaluate.py`

**D9. Threshold set by a false-alarm budget of 2 per 10,000 steps.**
The threshold is the lowest value that keeps validation false alarms at
or below budget, and that stays at or below budget for every higher
threshold too, because the count isn't strictly monotone. Only normal
data is needed. F1-maximising thresholds were rejected because they
tune on the labels being measured.
`orbitval/ml/threshold.py`

**D10. A false alarm is an alarm run, not a step.**
Consecutive alarm steps count once, matching one page to an operator.
Used the same way in calibration and in evaluation.

**D11. 10-step recovery grace period.**
*Added during Stage 2.* When a fault ends, the signal snaps back and a
forecaster sees one more large error. A new alarm run starting within
10 steps after an event ends is blamed on that event: it counts as
neither a false alarm nor a detection (detections must fall inside
[start, end]). Grace steps are also left out of the normal-step count.
Point-wise metrics use the plain labels.
Before the change, faulted-mission false alarms averaged 5.26/10k
against a 2.75/10k background. After it: 2.91/10k. SMAP/MSL numbers
were essentially unchanged. 10 steps matches the EWMA span. The same
value is used for both datasets.
`EVENT_GRACE`; `count_channel(grace=...)`

**D12. Metrics.**
- **Headline:** event recall, false alarms per 10k normal steps, median
  detection delay.
- **Secondary:** point-wise precision/recall/F1 with no point-adjustment,
  and PR-AUC (average precision, ties grouped like sklearn).
- Counts are pooled across channels or missions, not averaged per
  channel, so every event and every step weighs the same.

`orbitval/ml/metrics.py`

### OrbitVal synthetic telemetry

**D13. A new generator; core `runner._build_telemetry` is untouched.**
Core OrbitVal's telemetry is constant (solar 5 W, battery full,
temperature 20 °C), so any forecaster predicts it perfectly. The new
generator in `orbitval/ml/sim/telemetry.py` derives everything from the
orbit:
- illumination: 1 sunlit, 0.5 penumbra, 0 umbra, from core's eclipse periods
- solar: about 23 W peak, with a ±20% attitude oscillation (17-min period)
- battery: integrates net power; 10 W load; clipped to [0, 20 Wh]
- temperature: first-order relaxation, 25 °C sunlit / −10 °C eclipse,
  τ = 30 min
- magnetometer: a dipole along the ground track
- seeded Gaussian noise on every channel

Eclipse transitions are normal data. Core's runner is left alone
because realistic eclipses would flip the PASS/FAIL results of the
existing default autonomy.
*Simplifications (on purpose):* one-node thermal model, constant load,
dipole field instead of IGRF. Faults are applied after the fact to
measured values, as in core, so they don't feed back into the battery
integration.

**D14. Fault catalogue and severity scales.**

| Fault | Source | Effect at severity *s* |
|---|---|---|
| `power_brownout` | core | battery × (1 − 0.5s), solar × (1 − 0.9s) |
| `sensor_noise` | core | magnetometer noise std 0.1·(10s) µT (sensor's own: 0.02) |
| `eclipse_power_stress` | core | in sunlight only: solar × (1 − s), battery × (1 − 0.2s), temperature − 20s °C |
| `sensor_drift` | new | temperature + 8s °C, rising linearly over the window |
| `stuck_sensor` | new | solar frozen at its value at onset; severity ignored (flat row by design) |

- The scales were set once, before the first map run, and haven't been
  tuned since.
- Left out: `gps_dropout`, `comms_blackout`, `star_tracker_failure`.
  They flip availability flags or zero out channels outside the
  detector's inputs, so a simple rule catches them perfectly.
- New faults live in `orbitval/ml/sim/faults.py`. Core `FAULT_REGISTRY`
  and `orbitval list-faults` are unchanged.

**D15. Missions and labels.**
- A mission is 24 h at 60 s per step: 1440 steps, about 15 orbits.
- A faulty mission has exactly one 30-step fault.
- Onset is random, at least 380 steps in (warm-up + 60).
  `eclipse_power_stress` is placed fully in sunlight.
- Labels come from the fault's own `is_active()`, so they match the
  injected steps exactly. Tests check that the data differs from the
  clean mission only inside the label.
- Seed ranges: train 0+, val 100,000+, dev 200,000+, test 300,000+.

**D16. Paired design.**
Within a split, replicate *r* uses the same base mission (orbit, noise,
onset) for every fault and every severity. Differences across the map
come from the fault, not from luck.

**D17. Channel aggregation: max over channels.**
Each of the 6 channels is scored separately with the same univariate
detector. The mission score is the maximum over channels: alarm if any
channel is unusual.

**D18. Two of the 8 orbits are held out for test missions. RESOLVED.**
Originally all splits shared one 8-orbit pool, so a model could learn
orbit-specific eclipse timing that carried over to test. Now train, val
and dev missions fly the 6 orbits in `ORBIT_POOL`, and test missions fly
only the 2 in `TEST_ORBITS`: 575 km / 60° (June epoch) and 480 km / 51.6°
(October epoch). Both lie inside the training range of altitude and
inclination, so the test is "a new orbit", not an extrapolation.
The pool is chosen from the seed's range (`orbits_for_seed`), so a test
seed can't land on a training orbit, and tests check this per split.
The dev map below does not fly the held-out orbits, by design. Their
results first appear in the one final test run.
`orbitval/ml/sim/missions.py`

### Scope and process

**D19. Deferred until after Nov 13:** the `evaluate-detector` CLI
subcommand, the SHA-256 hashed detector report, `verify-report`
dispatch, and registry entries. Stage 4 is reduced to
`scripts/reproduce.sh` plus README results.

**D20. Transformer dropped** unless everything else is done. No ablations.

**D21. Stage order:** the demo (Stage 5) now comes before
reproduce/README (Stage 4).

**D22. A CI job for torch is deferred to Stage 3.**
Stages 0–2 are numpy-only and covered by the existing CI job (coverage
97%, gate 90%). When torch code lands, it gets a second job installing
`.[ml,dev]`.

**D23. Environment.** Tests run with `.venv/bin/python -m pytest`; dev
dependencies were installed into `.venv` on 2026-11-03.

## Results to date

All of these are on **dev** data. Held-out channels and the test
mission split have not been scored.

### Stage 1: persistence baseline, SMAP/MSL dev channels

Budget: 2 false alarms per 10k steps. Produced by
`python -m orbitval.ml.run_telemanom --data data/telemanom`, saved in
`results/stage1_baseline.json`.

| | SMAP (16 dev channels) | MSL (8 dev channels) |
|---|---|---|
| Threshold (val FA/10k) | 6.47 (1.85: 5 runs / 27,036 steps) | 47.11 (1.71: 2 runs / 11,663 steps) |
| Event recall | 12/18 = 0.667 | 3/11 = 0.273 |
| False alarms /10k (test) | 0.46 (5 / 108,947) | 1.50 (2 / 13,292) |
| Median delay | 62 steps | 7 steps |
| Point P / R / F1 | 0.881 / 0.004 / 0.009 | 0.600 / 0.001 / 0.002 |
| PR-AUC | 0.126 | 0.264 |
| Unscoreable events | 0 | 0 |

Across all 80 labeled channels (positions only, no scoring), no event
lies entirely inside the warm-up; one MSL event starts inside it.

**Notes:**
- Point recall is near zero because the rolling z-score fades during
  long anomalies (D7).
- The MSL threshold (47) is much higher than SMAP's. Flat channels hit
  the 1e-3 std floor, so any small change gives a huge z.
- MSL false-alarm numbers rest on 2 alarms, so they are very noisy.

### Stage 2: persistence detectability map, OrbitVal dev missions

Dev missions on the 6 non-held-out orbits (D18). 20 missions per cell;
threshold from 30 clean val missions (5.58, val FA/10k 1.79: 6 runs /
33,600 steps). Produced by `python -m orbitval.ml.run_detectability`,
saved in `results/stage2_baseline_map.{json,png}`.

Event recall:

| fault | 0.05 | 0.1 | 0.2 | 0.35 | 0.5 | 0.75 | 1.0 |
|---|---|---|---|---|---|---|---|
| power_brownout | 0 | 0 | 0.85 | 1 | 1 | 1 | 1 |
| sensor_noise | 0 | 0 | 0.25 | 0.70 | 0.95 | 1 | 1 |
| eclipse_power_stress | 0 | 0 | 0 | 0.95 | 1 | 1 | 1 |
| sensor_drift | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| stuck_sensor | 0 | 0 | 0 | 0 | 0 | 0 | 0 |

- Median delay where detected: 0 steps for step faults; 1–12 steps for
  noise, getting faster as severity rises.
- False alarms on faulted missions (outside events and grace): mean
  2.34/10k, max 2.78/10k. Slightly above the 2.0 budget, consistent with
  sampling noise at these counts (about 5–6 alarms in ~22,000 steps).

**Effect of holding out orbits (D18), old shared pool → new:**
threshold 5.61 → 5.58; `power_brownout` at 0.2: 0.75 → 0.85;
`sensor_noise` at 0.5: 0.90 → 0.95 (median delay 3.5 → 3); mean false
alarms 2.91 → 2.34/10k. Every other cell's recall is unchanged. Removing
two orbits changed which orbit each mission draws, so these small shifts
are a resampling effect, not an improvement in the detector.

**Reading:** persistence catches sudden jumps. It never catches slow
drift, because each step is close to the last. It never catches a
stuck sensor either: a frozen reading is perfectly predicted by "no
change", so its error falls instead of rising. These two rows are where
the learned models in Stage 3 have to show value.

## Change history

| Date | Change |
|---|---|
| 2026-10-22 | Plan approved: shared univariate SMAP/MSL model, demo before transformer, 2 FA/10k budget |
| 2026-10-22 | Stage 0+1 code; D3 dev/held-out split introduced |
| 2026-11-03 | Scope reduced (D19–D21); data copied from the Kaggle archive; P-2 skipped (D4) |
| 2026-11-03 | Stage 2 done; recovery grace period added (D11) |
| 2026-11-03 | This log created |
| 2026-11-04 | D18 resolved: 2 orbits held out for test missions; Stage 2 map rerun |
