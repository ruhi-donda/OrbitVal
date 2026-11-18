# Slide outline: CS462 project deck

All numbers are from the frozen held-out run unless marked "dev". Sources: docs/ml-project-log.md, the README "Detector validation results (CS462)" section, and the held-out result files in results/heldout/heldout/*.json. Figures are in results/slides/. "Say:" lines go in speaker notes, not on the slides.

One message to land: on simulated faults, trained models catch much smaller sudden faults than "nothing changes". On real NASA data the advantage mostly disappears. All detectors share a blind spot that better training and two-sided alarms don't fix, and alarm lines set on familiar orbits don't transfer predictably to new ones.

## 1. Title
- On slide: "Can a detector catch this fault? Validating spacecraft fault detection with OrbitVal." Ruhi Donda, CS462, Nov 20 2026.
- Say: "I built a way to measure which spacecraft faults a deep learning detector catches, how fast, and which ones it can't see at all."

## 2. The problem
- On slide: clean_solar_power.png (solar power over a few orbits of one clean simulated mission; data only, not a result) and three lines: faults are rare, mostly unlabeled, and operators need early alarms without constant false ones.
- Say: "A satellite streams sensor readings all day. When something breaks, you want to know fast, but every false alarm teaches operators to ignore the system."

## 3. Approach: forecast, then flag
- On slide: a left-to-right flow: past window -> forecaster -> error -> smoothing + rolling z-score -> alarm line -> alarm.
- Say: "Each model predicts the next reading. If the error is unusually large compared with the recent past, that's an alarm. All detectors share the same scoring, so the only difference between them is the forecast."

## 4. Models and deep learning techniques
- On slide: three columns: persistence ("next = current", no learning), LSTM, GRU.
- Shapes: each channel is windowed separately and stacked along the batch axis: input (batch, L, 1) -> hidden (batch, H) -> prediction (batch, 1).
- Techniques, named on the slide: recurrent networks (LSTM, GRU), gating, backpropagation through time, gradient clipping, Adam, MSE loss (= Gaussian likelihood), early stopping, 3 random seeds, trained on normal data only.
- Say: "Persistence is the baseline that matters. If a trained model can't beat 'nothing changes', it hasn't learned anything."

## 5. Data: real and synthetic
- NASA SMAP/MSL: real spacecraft telemetry with expert-labeled anomalies. Results were viewed only on 30% of channels (dev) while building; final numbers come from the other 70% (held out). Alarm lines were set from normal data only.
- OrbitVal: simulated missions where real orbit propagation drives sun and shadow, which drive solar power, battery and temperature; the magnetometer follows the ground track. 5 fault types; 4 have a 0-1 severity knob, stuck sensor has no severity. Test missions fly 2 orbits never seen in training.
- Say: "Real data proves it works on real spacecraft. Synthetic data gives exact fault start times and controlled severity, which real labels can't."

## 6. Evaluation rules
- Alarm line set on clean data, allowing at most 2 false alarms per 10,000 steps
- Metrics: event recall, false alarms per 10k, median detection delay, plus point F1 and PR-AUC
- No point-adjusted F1: it can make even random scores look strong (Kim et al., AAAI 2022)
- Held-out results come from one locked run, recorded with the commit and the hash of every checkpoint; the runner refuses to overwrite it. Dev results rebuild exactly with scripts/reproduce.sh

## 7. Live demo
- On slide: a screenshot of the demo (brownout preset, light theme) and the four scenes: brownout in sun, stuck in sun, stuck at eclipse edge, sensor drift.
- Say: walk through the presets in that order.

## 8. Result 1: trained models catch much smaller sudden faults
- On slide: heldout_detectability.png (three heatmaps side by side).
- Brownout at severity 0.1: persistence 0/20, LSTM 59/60, GRU 60/60. Sensor noise at 0.1: 0/20, 54/60, 60/60.
- At severity 0.05, GRU still catches 37/60 brownouts, steadier across seeds (11, 15, 11) than LSTM (26/60: 13, 10, 3).
- Eclipse stress at 0.1: the models' edge is small (LSTM 13/60, GRU 12/60, persistence 0/20). At 0.2 the models catch 60/60, persistence 0/20.
- Say: "On orbits the models never trained on, they catch brownouts and sensor noise at severity 0.1, where 'nothing changes' catches none. Persistence needs severity 0.2 for most brownouts (17/20) and 0.5 for most sensor noise (19/20)."

## 9. Result 2: on real NASA data, the gain is small
- On slide: heldout_recall.png.
- SMAP (49 held-out events): persistence 30; LSTM 31, 34, 28; GRU 30, 32, 35 (per seed). Within seed-to-seed spread.
- MSL (25 held-out events): persistence 4; LSTM 7, 6, 6; GRU 7, 6, 6. Every model run beats persistence, by 2-3 events; false alarms over budget in 2 of 7 runs.
- Say: "The trained models forecast better but don't reliably detect more on SMAP. On MSL the gain is consistent but small."

## 10. Result 3: the shared blind spot
- Frozen sensor: caught only at eclipse crossings (persistence 0/20, LSTM 6/60, GRU 20/60). In steady sun the error drops, so nothing fires.
- Slow drift at severity 1.0: persistence 0/20, LSTM 12/60, GRU 4/60.
- Two-sided alarms (also alarm on unusually low error): 0 catches attributable to the low side; cost SMAP 1-9 events per run.
- Say: "To this score, a frozen solar sensor looks like an eclipse. This is a scoring problem, not a model problem: better training can't fix it."

## 11. Result 4: alarm lines don't transfer predictably to new orbits
- On slide: false_alarms_dev_vs_heldout.png.
- False alarms per 10k on clean missions, dev orbits -> held-out orbits: persistence 2.23 -> 4.46, LSTM 2.83 -> 4.76, GRU 3.57 -> 2.83.
- Say: "The same alarm line behaves differently on orbits it wasn't set on. Persistence and LSTM got noisier; GRU got quieter. A budget set on one set of orbits isn't guaranteed on another."

## 12. Limitations
- OrbitVal data is synthetic; models may partly learn the simulator
- SMAP/MSL uses one shared model on the telemetry value only, simplified from the original paper (telemanom) for compute, so not directly comparable
- Small event counts: 49 SMAP and 25 MSL held-out events
- Alarm lines set on clean data don't fully transfer: false alarms exceed the budget on new orbits and faulted missions
- Demo scenes are chosen by written rules on seed 0, not randomly

## 13. What I learned
1. Better forecasting isn't better detection (dev). Longer training (30 -> 80 epochs) cut forecast error on MSL and one SMAP run, but recall moved no more than seed noise. On OrbitVal it changed nothing.
2. Evaluation choices can matter more than the model. Point-adjusted scoring can make even random scores look strong (Kim et al., AAAI 2022; not measured here).
3. Some blind spots are in the scoring, not the network.
- Next: multi-step forecasting for drift; a flatline check for frozen sensors; a multichannel model.

## 14. Why this matters: OrbitVal
- On slide: "Before a satellite's fault detection flies, OrbitVal tells the team which faults it misses and how late it catches the rest." Under it: the detectability map, the blind spot it exposed, and alarm lines that don't transfer to new orbits. Planned next: an evaluate-detector command and hashed detector reports.
- Say: "This project is the first version of a validation feature for OrbitVal, my open-source CubeSat stress-testing tool."

## 15. AI-use disclosure
- Claude Code wrote most of the code under a staged plan I approved stage by stage, and drafted this deck
- I reviewed each stage before the next started and made the design decisions, recorded in docs/ml-project-log.md
- What I did myself: [FILL IN, e.g. traced the windowing and LSTM tensor shapes by hand]
- Numbers in this deck were checked against the raw result files before presenting.

## Backup (after a "Backup" divider slide)
- B1. Tensor shapes: each channel of each series, (T,), is windowed on its own -> windows (N, L, 1), targets (N, 1), N = T - L. Windows from every channel and series are concatenated along the batch axis -> batch (B, L, 1) -> LSTM -> last hidden (B, H) -> linear -> (B, 1). L = 64, H = 32. No window spans two channels or two missions.
- B2. LSTM vs GRU gates in words; why tanh inside recurrence; why gradient clipping
- B3. Threshold calibration: the lowest alarm line keeping clean-data false alarms at or under 2 per 10k
- B4. (dev) False alarms at grace period 10 vs 74 steps, per detector
- B5. (dev) 30 vs 80 epochs: lower forecast error on MSL and one SMAP run, recall unchanged within seed noise; on OrbitVal nothing changed (every run stopped before the old cap mattered)
- B6. Dataset quirks: original link 403s, Kaggle mirror used, P-2 duplicate label skipped, unlabeled T-10 ignored, 320-step warm-up, 0 unscoreable events
- B7. Why no transformer: dropped for time. My analysis suggests it wouldn't fix either failure, since it would share the one-step forecast and the high-error-only score (untested).
- B8. Clean-twin check: each fault mission is also flown without the fault on identical noise. A separate check, reported next to the headline counts (not a filter on them): it shows which catches also fire on the twin and so may be chance. Held out: persistence and GRU have none; LSTM about one mission per fault row.
- B9. Locked test run: before scoring, the held-out run recorded the commit and the hash of every checkpoint. It refuses uncommitted code, code or weights changed since then, and a folder that already holds a held-out run, so the result can't be overwritten.
