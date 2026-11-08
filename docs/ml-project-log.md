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
| 3 | Small LSTM + GRU, 3 seeds, no ablations; rerun with 80-epoch cap and grace 74 | Nov 7 | done (Nov 4) | `3a0ba54`, `8873af3`, `849a06b` |
| 5 | Streamlit demo (runs before Stage 4) | Nov 9 | done (Nov 4) | see change history |
| 4a | `scripts/reproduce.sh`, dev results (D33) | Nov 8 | done (Nov 5) | `0e3900a` |
| — | Two-sided score variant, dev only (D32) | Nov 8 | done (Nov 5), approved Nov 7 | see change history |
| — | One held-out run: all detectors, both held-out sets (D34) | Nov 8 | next | — |
| 4b | README results section | after the held-out run | pending | — |
| 6 | Transformer | — | skipped by decision | — |

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

**D11. Recovery grace period: 74 steps (originally 10).**
*Changed 2026-11-04, user decision, after Stage 3.* 74 steps for every
detector and dataset: a model's 64-step input window still holds faulty
data after a fault ends, and the EWMA (span 10) lags after that. False
alarms are reported at both 74 and 10. Grace only affects false alarms,
never recall. The rest of this entry describes the original 10-step
version.
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

**D22. Torch code has its own CI job (added in Stage 3).**
The core job stays free of torch: `recurrent.py`, `neural_detector.py`,
`train.py` and `run_neural.py` are omitted from its coverage, and their
tests skip without torch (checked by blocking the import: 400 passed,
1 skipped, 95.6% coverage against the 90% gate). The new `test-ml` job
installs `.[ml,dev]` with CPU torch and runs `tests/ml`. First run on
GitHub: `test-ml` and Python 3.11–3.13 passed; 3.10 failed because an
existing test imported `tomllib`, fixed with `importorskip` (`94a44a5`).
The demo (`orbitval/ml/app/`) is omitted from core coverage too.

**D23. Environment.** Tests run with `.venv/bin/python -m pytest`; dev
dependencies were installed into `.venv` on 2026-11-03.

### Models and training (Stage 3)

**D24. Small one-layer LSTM and GRU, fixed settings, no tuning.**
Window L = 64, hidden size 32. LSTM 4,513 parameters, GRU 3,393. Adam,
learning rate 1e-3, MSE, batch 256, gradient norm clipped to 1.0, at
most 80 epochs, early stopping with patience 5, seeds 0/1/2. These were
set before the first run, with one exception: the cap was 30 until
2026-11-04, then raised to 80 by user decision because several runs
peaked at epoch 24–29. Effect measured below (30 vs 80 epochs).
`orbitval/ml/models/recurrent.py`, `orbitval/ml/train.py`

**D25. One shared univariate model per dataset (3 datasets).**
Separate models for SMAP, MSL and OrbitVal, each trained on all of that
dataset's channels pooled. OrbitVal's 6 channels share one model, so it
can't use links between channels (e.g. solar drives battery). SMAP/MSL
models also train on the *normal* train series of held-out channels,
never on their test series (same reasoning as D3).

**D26. Shared scoring is unchanged. Forecasts return to original units.**
`scoring.py` was not touched. For OrbitVal, models work on standardized
data (per-channel mean and std from training missions only), and the
forecast is converted back before scoring, so the scoring sees the same
raw values as persistence. To support this, `detector.score()` gained a
`channel` argument, which persistence ignores; the test
`test_wrapper_reproduces_persistence_with_a_last_value_model` confirms
a copy-the-last-input network reproduces persistence exactly.

**D27. Early stopping uses 10 clean val missions; the threshold uses 30.**
Both are validation data. Early stopping uses fewer only for speed.

### Demo (Stage 5)

**D28. The demo reuses the real evaluation code and flies dev missions
only.** `make_mission`, `mission_scores` and the thresholds calibrated
on clean validation missions. It never adjusts a threshold and never
flies test orbits. Logic in `orbitval/ml/app/core.py`, page in
`orbitval/ml/app/demo.py`. Weights and thresholds are copied to the
tracked `orbitval/ml/app/weights/` by `scripts/export_demo_weights.py`,
which also writes `maps.json`, the heatmap counts, because `results/` is
not tracked.

**D29. Presets are found by written rules, not by eye.**
`scripts/pick_demo_presets.py` takes the first dev mission and onset
meeting each rule, using model seed 0 only, so a scene can't come from
shopping for a lucky seed. Every other detector must miss the scene, and
no detector may raise a false alarm. A test re-checks each scene's
claim. **A preset is one chosen mission, so the page quotes the overall
rate next to it.** This matters: the "stuck at eclipse edge" scene shows
the LSTM catching it, but overall that happens 7/33 times, all from seed
0.

| Preset | Fault, severity | Mission, onset | Shown | Caught by | Overall, all dev windows |
|---|---|---|---|---|---|
| Brownout in sun | brownout, 0.1 | 0, 768 | LSTM | LSTM, GRU | persistence 0/20, LSTM 54/60, GRU 60/60 |
| Stuck in sun | stuck | 0, 768 | GRU | none | persistence 0/8, LSTM 0/24, GRU 0/24 |
| Stuck at eclipse edge | stuck | 0, 829 | GRU | LSTM, GRU | persistence 0/11, LSTM 7/33, GRU 24/33 |
| Sensor drift | drift, 1.0 | 0, 767 | LSTM | none | persistence 0/20, LSTM 8/60, GRU 3/60 |

The sunlit rule keeps 8 steps of full sun either side of the fault;
sunlit stretches last only about 55 steps. In the stuck and drift scenes
alarms do fire after the fault, when the signal snaps back. Those are
recovery alarms, not detections. The app opens on "Brownout in sun", and
the buttons sit at the top of the sidebar, visible on every tab.

**D30. Plots say "surprise score (higher = more unusual)"** instead of
"z-score". The axis is capped at 3x the threshold so a large spike can't
flatten the alarm line. Alarms above the cap are drawn on the top edge.

**D31. The page can't go blank on a rerun.** Streamlit reruns the script
on every control change and can interrupt it. Each run first re-shows
the last good table and chart, then replaces them. Charts are embedded
in the page as data, not served as temporary media files. A failed run
keeps the previous view and shows a warning. Tested with 60 preset and
Play clicks 70–160 ms apart, and 7 fault-dropdown changes as fast as the
browser tool could send them (slower than the clicks): 1,386 samples
every 25 ms, with no missing chart or table and no exception.

### Next

**D32. Two-sided score variant, before the held-out run.** *New order,
user decision 2026-11-05, because the test set is touched once.* Also
alarm on unusually LOW error, as an extra detector setting evaluated on
dev only. Measure its false-alarm cost and its effect on the
`stuck_sensor` and `sensor_drift` rows. The default shared score stays
one-sided.

*Design corrected by the user, 2026-11-05.* My proposal was one threshold
on `|z|`. Error is bounded at zero, so z can't go much below −mean/std,
and a compressed low tail could never reach a high-side threshold.
Instead the high side keeps its score, the low side checks `−z` against
its own threshold from clean validation data, and the budget is split:
1 per 10k per side, 2 in total. On a mission each side takes its own max
over channels. Trained weights are reused. Code: `orbitval/ml/two_sided.py`,
`orbitval/ml/run_two_sided.py`. Results below.

**D35. Clean-twin check on alarms.** *My addition.* Each dev mission is
also flown without its fault, on identical noise. An alarm that also
fires during the same steps of the clean twin may be chance. A low-side
catch counts as attributable only if it is on a channel the fault changed
and that channel of the twin doesn't alarm in the same steps. Reported
next to the plain counts, which keep the shared definition. SMAP/MSL have
no twin, so this applies to OrbitVal only.

**D33. `scripts/reproduce.sh` rebuilds all dev results and checks them.**
Checks the setup, runs the tests, trains and evaluates every detector,
writes the tables to `<outdir>/report.txt` and the code version to
`environment.txt`, and compares results with the demo's tracked numbers
and an optional reference directory (`scripts/compare_results.py`). Only
training time may differ. It refuses to write into an existing results
directory, and `--quick` checks the pipeline in about 3 minutes. It uses
persistence results from the same run, so Stages 1 and 2 need no scripts
of their own.

Verified 2026-11-05 from clean commit `0e3900a`: 464 tests passed, 32
minutes with 4 jobs, **0 differences across all 21 result files**
against `results/stage3`, 18/18 checkpoints with identical tensors, and
identical tables apart from training times. The check also fails when it
should: against the 30-epoch run it reports 1,434 differences.

Limits: this shows repeatability on one machine (Apple Silicon, Python
3.13.2, torch 2.15.0, numpy 2.4.3). Another CPU or library version may
give different floating-point results. A fresh clone can check only
OrbitVal without a reference directory, since `results/` isn't tracked.

*Verified again 2026-11-08, with the two-sided step*, from commit
`23bde54` in a separate checkout, with torch limited to 2 threads per job
(`--threads 2`, `OMP_NUM_THREADS=2`): 483 tests passed, **0 differences
across all result files including the 21 two-sided ones**, 0 against the
demo's numbers, 18/18 checkpoints with identical tensors. Wall time was
about 6 hours at 48% CPU, so the machine probably slept; CPU time was
about 2.8 hours.

**D34. One held-out run, after D32 is settled.** Persistence, LSTM, GRU,
each one-sided and two-sided, on the held-out SMAP/MSL channels and the
held-out-orbit OrbitVal missions, with clean-twin attribution on
OrbitVal. Thresholds come from the same clean validation data as on dev.
`scripts/run_heldout.sh OUTDIR WEIGHTS` (`orbitval/ml/run_heldout.py`)
first writes `frozen.json` with the commit and the SHA-256 of every
checkpoint. It refuses uncommitted code, a folder that already has a
held-out run, a result file that already exists, and code or weights
that changed since the freeze. `reproduce.sh --held-out` repeats it after
the dev checks pass, and refuses `--quick`. Its tests never score real
held-out data: OrbitVal test missions are redirected to dev missions,
and SMAP/MSL use a fake dataset.

**Freeze rule (user, 2026-11-07).** After the held-out run nothing is
retuned on its results: no threshold, budget, grace period, window,
model or setting changes. Its numbers are reported as they are.

**D36. Future work, not built: a zero-variance check for frozen sensors.**
*User decision, 2026-11-07.* D32 shows the shared score can't separate a
frozen solar sensor from an eclipse, since both give near-zero error. A
direct rule, such as "this channel's value hasn't changed for N steps
while it normally does", would target that fault. It is a different
detector, it would need its own threshold on clean data, and it would
need care with channels that are legitimately flat (solar in umbra,
battery at full charge). Left for after the presentation.

**Known weaknesses of this setup, not fixed:**
- *Longer training changed little (see 30 vs 80 epochs).* Early stopping
  with patience 5 ended most runs well before the cap, some very early.
- *MSL thresholds are unstable.* From 13.49 to 33.45 across seeds, with
  false alarms of 1–10 runs on test. Results on MSL rest on few events.
- *OrbitVal LSTM varies a lot by seed.* Best epochs 18, 11 and 4, val
  MSE 0.0087 to 0.0134. Seed 2 stopped early and did noticeably worse.
- *Threshold context is in-sample for models.* SMAP/MSL validation is
  scored with the train series as context (D3), and models fit that
  series, so the rolling statistics start slightly low at the start of
  validation. Persistence has no such effect.
- *Dataset property:* per the telemanom README, values are scaled by the
  min/max of the test set, so test ranges influence inputs for all
  detectors. This comes from the dataset and can't be undone here.

## Results to date

All of these are on **dev** data. Held-out channels and the test
mission split have not been scored.

### Stage 1: persistence baseline, SMAP/MSL dev channels

*Stage 1 and 2 numbers below use the original grace of 10 (D11).
Persistence at both grace values is in the Stage 3 tables.*

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
stuck sensor: a frozen reading is perfectly predicted by "no change", so
its error falls (measured: 20/20 missions, 0.794 → 0.013 W).

**Correction (2026-11-04):** the Stage 2 report suggested that an LSTM
would fail to predict a flat signal, so its error would grow. Stage 3
measurements show that is false outside eclipse transitions. See below.

### Stage 3: LSTM and GRU, dev data, 3 seeds

Produced by `scripts/run_stage3.sh`; tables by
`python -m orbitval.ml.run_neural summarize`; files in `results/stage3/`.
Max 80 epochs; false alarms at both grace values. Training time summed
over the 18 runs: about 90 minutes on CPU, 4 at a time. Seed-to-seed spread is shown as ±1 standard deviation.

**Forecast error on validation (MSE, lower is better):**

| | "no change" | LSTM (3 seeds) | GRU (3 seeds) |
|---|---|---|---|
| SMAP | 0.0306 | 0.0205–0.0210 | 0.0188–0.0196 |
| MSL | 0.0552 | 0.0415–0.0423 | 0.0408–0.0416 |
| OrbitVal (standardized) | 0.0200 | 0.0087–0.0134 | 0.0080–0.0096 |

**SMAP/MSL dev channels:**

| | Event recall by seed | Rate | FA/10k, grace 74 | FA/10k, grace 10 | False-alarm runs (grace 74) | Median delay | Point F1 | PR-AUC |
|---|---|---|---|---|---|---|---|---|
| SMAP persistence | 12/18 | 0.67 | 0.46 | 0.46 | 5 | 62.5 | 0.01 | 0.13 |
| SMAP LSTM | 13/18, 15/18, 10/18 | 0.70±0.11 | 0.43±0.04 | 0.43±0.04 | 5, 5, 4 | 47.8±12.9 | 0.01 | 0.13 |
| SMAP GRU | 13/18, 14/18, 13/18 | 0.74±0.03 | 0.56±0.08 | 0.55±0.07 | 5, 7, 6 | 45.3±3.8 | 0.01 | 0.13 |
| MSL persistence | 3/11 | 0.27 | 1.58 | 1.50 | 2 | 7.0 | 0.00 | 0.26 |
| MSL LSTM | 5/11, 3/11, 4/11 | 0.36±0.07 | 4.22±2.69 | 4.01±2.56 | 10, 2, 4 | 8.0±0.8 | 0.00 | 0.29 |
| MSL GRU | 4/11, 3/11, 3/11 | 0.30±0.04 | 1.85±0.99 | 1.76±0.94 | 4, 1, 2 | 7.3±0.5 | 0.00 | 0.30 |

Unscoreable events: 0 for every run. On real data the gains are small
and rest on few events: MSL's difference from persistence is at most a
couple of events, and the LSTM's SMAP range (10–15 of 18) spans
persistence's 12. MSL LSTM also exceeds the false-alarm budget on test,
on small counts (seed 0: 10 runs, 7.91/10k).

**OrbitVal dev map, event recall, mean over 3 seeds (20 missions per cell):**

LSTM (thresholds 5.66, 5.57, 5.48):

| fault | 0.05 | 0.1 | 0.2 | 0.35 | 0.5 | 0.75 | 1.0 |
|---|---|---|---|---|---|---|---|
| power_brownout | 0.35 | 0.90 | 1 | 1 | 1 | 1 | 1 |
| sensor_noise | 0.48 | 0.95 | 1 | 1 | 1 | 1 | 1 |
| eclipse_power_stress | 0 | 0.30 | 1 | 1 | 1 | 1 | 1 |
| sensor_drift | 0 | 0 | 0 | 0 | 0 | 0.03 | 0.13 |
| stuck_sensor | 0.12 | 0.12 | 0.12 | 0.12 | 0.12 | 0.12 | 0.12 |

GRU (thresholds 5.92, 5.93, 6.00):

| fault | 0.05 | 0.1 | 0.2 | 0.35 | 0.5 | 0.75 | 1.0 |
|---|---|---|---|---|---|---|---|
| power_brownout | 0.45 | 1 | 1 | 1 | 1 | 1 | 1 |
| sensor_noise | 0.50 | 1 | 1 | 1 | 1 | 1 | 1 |
| eclipse_power_stress | 0 | 0.25 | 1 | 1 | 1 | 1 | 1 |
| sensor_drift | 0.02 | 0.02 | 0.02 | 0.02 | 0.02 | 0.02 | 0.05 |
| stuck_sensor | 0.40 | 0.40 | 0.40 | 0.40 | 0.40 | 0.40 | 0.40 |

- Step faults and noise: models detect far lower severities than
  persistence (persistence is 0 at severity 0.05 and 0.1).
- **Drift is mostly missed.** At full severity: LSTM 8/60, 6 of them
  from one seed; GRU 3/60. GRU's flat 0.02 is 1/60 at every severity,
  which looks like a background alarm rather than a response to drift.
- **Stuck sensor is caught only in part,** and unevenly: LSTM 7/60, all
  from seed 0; GRU 24/60.

**Does forecast error go down when the sensor freezes?** Solar channel,
paired against the same mission with no fault, mean |error| in W inside
the fault window, per seed:

| Lighting of the fault window | Persistence | LSTM | GRU |
|---|---|---|---|
| Sunlit (n=8): error went down | 8/8 | 8/8, 8/8, 8/8 | 8/8, 8/8, 8/8 |
| Sunlit: clean → frozen | 0.538 → 0.022 | ~0.28 → ~0.12 | ~0.25 → ~0.13 |
| Sunlit: detected | 0/8 | 0, 0, 0 | 0, 0, 0 |
| In eclipse (n=1): error went down | 1/1 | 1/1 ×3 | 1/1 ×3 |
| Crossing a transition (n=11): error went down | 11/11 | 0, 0, 0 of 11 | 1, 0, 0 of 11 |
| Crossing: clean → frozen | 1.044 → 0.008 | ~1.04 → 1.5–4.0 | ~0.94 → 5.6–6.1 |
| Crossing: detected | 0/11 | 7, 0, 0 | 7, 10, 7 |

So **yes, error goes down whenever the freeze doesn't span an eclipse
transition,** for every detector and seed. The models then behave like
persistence: once the input window has gone flat, they predict flat.
Error goes up only when the frozen sensor fails to follow an eclipse
transition the model expects. Every stuck-sensor detection comes from
those crossing windows. The score alarms only on *high* error
(`score > threshold`), so a falling error can never raise an alarm.
Changing that would mean changing shared scoring, which needs the
user's approval. The eclipse row has just one mission.

**Drift at severity 1.0:** error does rise in most missions (e.g. GRU
seed 0: 0.231 → 0.321 °C, down in only 1/20), but by too little to cross
the threshold. A one-step forecaster anchors on its latest inputs, so it
follows a slow ramp, and the rolling z-score also adapts to it.

**False alarms on faulted missions (budget 2/10k):**

| | Grace 74: mean, max | Grace 10: mean, max |
|---|---|---|
| Persistence | 2.49, 2.95 | 2.34, 2.78 |
| LSTM | 2.99, 4.43 | 3.00, 6.02 |
| GRU | 3.61, 4.43 | 4.13, 9.72 |

The longer grace period removes the post-fault cluster that inflated the
models' maximum (15–59 steps after the fault ended, GRU seed 0). It
lowers the GRU mean by 13% and leaves the LSTM's about the same. All
three detectors still sit above the 2/10k validation budget on faulted
missions. Persistence goes *up* with the longer grace: it has no extra
alarms to reclassify, and the same count over fewer normal steps (1016
vs 1080 per mission) gives a rate about 6% higher.

**30 vs 80 epochs: did longer training change anything?**

- **OrbitVal: nothing.** Every run stopped before the old cap could
  matter. Best epochs 18, 11, 4 (LSTM) and 20, 24, 18 (GRU). Model
  tensors, thresholds and the whole map are identical, so the demo's
  models are the same as the 30-epoch ones. Only `train_seconds` in the
  saved file differs.
- **SMAP: 1 of 6 runs changed.** GRU seed 2, best epoch 27 → 49, val MSE
  0.01958 → 0.01880. Its recall went *down*, 15/18 → 13/18, with median
  delay 26 → 48 steps.
- **MSL: 5 of 6 runs changed.** All had val MSE improve by 3–6%. Recall:
  LSTM 4,4,4 → 5,3,4 of 11; GRU 4,4,3 → 4,3,3 of 11. False-alarm runs
  (grace 10): LSTM 6,4,2 → 10,2,4; GRU 4,3,1 → 4,1,2. Thresholds moved
  a lot, e.g. GRU seed 1 from 18.35 to 33.45.
- Persistence is identical, as it should be. GRU MSL seed 0 reproduced
  its best epoch and val MSE exactly, confirming runs are deterministic.

Reading: **better forecasts did not give better detection.** Across the
six changed runs, recall rose once, fell three times and held twice,
which is no more than seed-to-seed noise. A 30-epoch cap was a real
limit on the forecasters but not on the detectors. Patience 5 is now the
binding limit for most runs (OrbitVal LSTM seed 2 stops at epoch 4 and
stays about 50% worse than seed 0). Not changed: it would be tuning.

### Two-sided setting: dev data, saved 80-epoch weights (D32)

Reproduce: `python -m orbitval.ml.run_two_sided summarize`, after `run`
for each detector, or `scripts/reproduce.sh`. Held-out data was not
scored. The setting's one-sided column matches the saved Stage 3 results:
259 metric sets, 0 differences. Rerunning all 21 from the same weights
gave 0 differences. `reproduce.sh` with this step has been run only with
`--quick` (483 tests passed), not as a full rerun.

**Result: the low side caught no fault that can be attributed to it on
OrbitVal, and splitting the budget cost SMAP about a third of its events.**

**`stuck_sensor` and `sensor_drift`, missions detected at severity 1.0**
(persistence out of 20, models out of 60 over 3 seeds):

| Row | Detector | One-sided at 2 | High at 1 | Low at 1 | Low, attributable | Two-sided |
|---|---|---|---|---|---|---|
| stuck | persistence | 0 | 0 | 0 | 0 | 0 |
| stuck | LSTM | 7 | 7 | 0 | 0 | 7 |
| stuck | GRU | 24 | 23 | 1 | 0 | 23 |
| drift | persistence | 0 | 0 | 0 | 0 | 0 |
| drift | LSTM | 8 | 7 | 0 | 0 | 7 |
| drift | GRU | 3 | 2 | 1 | 0 | 3 |

The stuck row is flat across severities by design. Drift at lower
severities: LSTM 2/60 at 0.75 (2 at high side, 0 low) and 0/60 below;
GRU 1/60 one-sided and 1/60 two-sided at 0.05–0.75, and both are alarms
that also fire on the clean twin.

**Why the low side can't catch a stuck solar sensor.** On that channel
the floor of z, −mean/std of the trailing window, is about −0.9, because
eclipse crossings put large errors in the window. A frozen sensor reaches
that floor (persistence: lowest z −0.98, floor −0.96) while the low
thresholds are 2.70–2.97. A separate threshold for solar wouldn't help
either: clean solar reaches about the same depth (−0.74 to −0.99), since
normal eclipses also have near-zero error. To this score, a stuck solar
sensor looks like an eclipse.

**Why it doesn't catch drift.** Drift raises the error on average (mean
error at severity 1.0, seed 0: persistence 0.47 to 0.61, LSTM 0.25 to
0.37, GRU 0.23 to 0.32). The lowest z on temperature is −0.9 to −1.9,
against a floor of −2.6 to −3.8, so the floor isn't what limits it here.

**Previously caught events lost, OrbitVal, all faults and severities, all
seeds.** "Not in twin" leaves out catches where the one-sided alarm also
fired on the clean twin.

| Detector | One-sided catches not in twin | Lost, not in twin | Kept only by low side |
|---|---|---|---|
| persistence | 254 | 1 (`sensor_noise`) | 0 |
| LSTM | 1,138 | 6 (`sensor_noise` 2, `eclipse_power_stress` 3, drift 1) | 0 |
| GRU | 1,241 | 17 (brownout 4, `sensor_noise` 4, `eclipse_power_stress` 2, stuck 7) | 0 |

GRU's 7 stuck losses are one mission (seed 0, rep 14) repeated across 7
severities, which don't affect that fault. GRU drift looks unchanged (9
one-sided, 9 two-sided, out of 420), but that hides a swap. Seed 1 loses 7
one-sided catches on rep 6, and seed 0 gains 7 low-side catches on the same
rep. All 14 alarms also fire on the clean twin. Its catches not in the
twin are 2 either way.

**Correction to earlier numbers.** The clean-twin check shows GRU's Stage 3
counts include alarms that also fire with no fault: at severity 1.0, drift
3/60 and stuck 24/60 each have 1 (seed 1, rep 6). The tracked demo maps
keep the shared definition and are not changed.

**False alarms per 10k steps, OrbitVal, mean over seeds.** Validation is
on budget by construction: 3 runs per side in 33,600 steps. Clean dev
missions are the fair out-of-sample number (22,400 steps).

| Detector | Set | One-sided at 2 | High at 1 | Low at 1 | Two-sided |
|---|---|---|---|---|---|
| persistence | clean dev | 2.23 | 2.23 | 1.34 | 3.57 |
| LSTM | clean dev | 2.83 | 2.08 | 1.04 | 3.12 |
| GRU | clean dev | 3.57 | 2.38 | 2.08 | 4.46 |
| persistence | faulted dev, grace 74 | 2.49 | 2.49 | 1.50 | 3.99 |
| LSTM | faulted dev, grace 74 | 2.98 | 2.14 | 1.15 | 3.29 |
| GRU | faulted dev, grace 74 | 3.61 | 2.56 | 2.12 | 4.68 |

Grace 10, two-sided: persistence 3.76, LSTM 3.28, GRU 5.08. The cost is
real but small, and seeds differ a lot: LSTM's two-sided rate on faulted
missions runs from 1.48 to 4.44, and one seed's low side raised no false
alarm at all. Low-side runs are short (median 1–5 steps, longest 9), and
at most 0.08% of clean dev steps are in low alarm, so a long run can't
overlap a fault window by chance very often.

**Where low-side false alarms happen, OrbitVal, val and clean dev pooled:**

| Detector | Runs | In umbra | Channel | Note |
|---|---|---|---|---|
| persistence | 6 | 0 | all battery | near full charge, about 20 Wh, where steps are about 0.05 Wh against 0.13 on average |
| LSTM | 16 | 7 (44%) | magnetometer x, y | |
| GRU | 23 | 10 (43%) | magnetometer x, y | |

Umbra is about 36% of scored time, so eclipses are **not** a clear
hotspot, on few counts. None of these alarms is on the solar channel,
where the eclipse effect would be largest, because solar can't reach the
threshold. The threshold is set by the channels with the deepest tails.

**SMAP/MSL dev channels, events detected per run** (persistence, then LSTM
seeds 0–2, then GRU seeds 0–2). There's no clean twin, so these gains and
losses can't be attributed.

| Dataset | Setting | Detected | False-alarm runs |
|---|---|---|---|
| SMAP (18) | one-sided at 2 | 12; 13, 15, 10; 13, 14, 13 | 5; 5, 5, 4; 5, 7, 6 |
| SMAP (18) | high at 1 | 7; 7, 8, 8; 8, 7, 7 | 0 in all |
| SMAP (18) | low at 1 | 1; 1, 1, 0; 1, 1, 0 | 22; 21, 22, 14; 19, 13, 9 |
| SMAP (18) | two-sided | 8; 8, 8, 8; 8, 7, 7 | 22; 21, 22, 14; 19, 13, 9 |
| MSL (11) | one-sided at 2 | 3; 5, 3, 4; 4, 3, 3 | 2; 10, 2, 4; 4, 1, 2 |
| MSL (11) | high at 1 | 3; 4, 3, 3; 4, 3, 3 | 1; 4, 1, 2; 2, 1, 1 |
| MSL (11) | low at 1 | 1; 1, 1, 0; 0, 0, 0 | 27; 12, 5, 2; 2, 2, 1 |
| MSL (11) | two-sided | 4; 5, 4, 3; 4, 3, 3 | 28; 16, 6, 4; 4, 3, 2 |

- *SMAP loses 2–7 of 18 events*, nearly all from the stricter high side.
  Its high threshold jumps from 6.0–7.7 to 20.2–33.4. Budget 1 allows only
  2 runs in about 27,000 validation steps (MSL: 1 in about 11,700), so the
  threshold lands on one of the few largest validation peaks.
- *Low-side false alarms run well over budget on real data*: SMAP
  0.83–2.04 per 10k against 1, MSL 0.79–21.37. They cluster on a few
  channels, mostly with long flat stretches: SMAP A-4 (in all 7 runs),
  D-11, E-3, E-9; MSL D-16, T-9. G-1 and P-15 are not flat.
- *Low-side catches are rare*: SMAP G-1 and MSL D-16 are gains, on channels
  that also produce low-side false alarms, so they could be chance.

**Reading.** On this data, low error is not a usable fault signal for this
score. The setting should be reported as a measured negative result, and
the one-sided detector stays the default. The result is about this score:
a window of 250 steps that spans eclipses, and one low threshold across
channels. It doesn't show that a frozen sensor is undetectable. A direct
check for zero variance would likely catch it, but that would be a
different detector and is not built.

*User decision, 2026-11-07:* keep the two-sided setting in the held-out
run as a measured negative result. One-sided stays the headline. The
zero-variance detector is not built (D36).

Limits: thresholds rest on 3 runs per side (OrbitVal), 2 (SMAP) or 1
(MSL). The missions in a rep share a base across cells, so counts over
severities aren't independent: 7 lost events can be one mission.

## Change history

| Date | Change |
|---|---|
| 2026-10-22 | Plan approved: shared univariate SMAP/MSL model, demo before transformer, 2 FA/10k budget |
| 2026-10-22 | Stage 0+1 code; D3 dev/held-out split introduced |
| 2026-11-03 | Scope reduced (D19–D21); data copied from the Kaggle archive; P-2 skipped (D4) |
| 2026-11-03 | Stage 2 done; recovery grace period added (D11) |
| 2026-11-03 | This log created |
| 2026-11-04 | D18 resolved: 2 orbits held out for test missions; Stage 2 map rerun |
| 2026-11-04 | Bug fixed: the `data/` line in `.gitignore` also matched `orbitval/ml/data/`, so the loader, windowing and training sets were missing from every earlier commit. Rule anchored to the repo root; checked with a clean clone. Commits before this one do not run from a fresh checkout |
| 2026-11-04 | Stage 3 done (D24–D27). Stage 2 claim about stuck sensors corrected from measurements. Open questions: one-sided score, grace period length |
| 2026-11-04 | Decisions: grace period 74 with both values reported (D11); max epochs 80 (D24); shared scoring unchanged; transformer skipped; two-sided score as optional ablation (D32) |
| 2026-11-04 | CI first ran on GitHub (D22); `tomllib` test fixed for Python 3.10 |
| 2026-11-04 | Stage 3 rerun at 80 epochs; comparison above. Stage 5 demo done (D28–D31), using these weights |
| 2026-11-05 | New order: reproduce.sh, two-sided variant on dev (D32), one held-out run (D34), README. Demo: presets moved to the sidebar |
| 2026-11-05 | `scripts/reproduce.sh` added and verified: full dev rerun matches exactly (D33) |
| 2026-11-05 | Two-sided setting on dev (D32, design corrected by the user), clean-twin check (D35). `reproduce.sh` and `compare_results.py` extended to cover it. Held-out data not touched |
