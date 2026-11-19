# Presentation guide (CS462, Nov 20, 2026)

A study guide for the 3-slide talk (`results/slides/14_Ruhi_Donda.pptx`).
Every fact here comes from `docs/ml-project-log.md`, the README section
"Detector validation results (CS462)", the held-out result files in
`results/heldout/heldout/`, or the deck. Numbers from development data
are marked **dev**. All other numbers are from the held-out run.

---

## 1. Project overview

### The problem

A satellite sends down **telemetry**: a stream of sensor readings, such
as solar power, battery charge and temperature. A **fault** is when
something goes wrong, for example a power drop or a broken sensor.
Operators want an **alarm** as soon as a fault starts.

Two things make this hard:

- Faults are rare, so there are few examples to learn from.
- Every **false alarm** (an alarm when nothing is wrong) teaches
  operators to ignore the system.

So a useful detector must catch faults early *and* stay quiet on
normal data. My question: **which faults can a deep learning detector
actually catch, and which does it miss?**

### What I built

A detector-validation feature for **OrbitVal**, my open-source (MIT)
CubeSat stress-testing tool. It measures detectors: which faults they
catch, how fast, and how many false alarms they raise.

I compared three **forecasters**. A forecaster looks at recent readings
and predicts the next one.

- **Persistence**: predicts "next value = current value". No learning.
  This is the **baseline**, the simple method to beat.
- **LSTM** (Long Short-Term Memory): a small **recurrent neural
  network**. A recurrent network reads a sequence one step at a time
  and keeps a memory of what it has seen. 4,513 **parameters** (the
  numbers the network learns).
- **GRU** (Gated Recurrent Unit): a simpler recurrent network with
  fewer parameters, 3,393.

Each model was trained 3 times with different **seeds**. A seed fixes
the random starting weights, so 3 seeds show how much luck matters.

### How the pieces fit

```
 telemetry          windowing           forecaster
 x[0..T-1]  --->  last 64 readings --->  persistence,  ---> forecast of
 (one channel)     (64 steps)            LSTM or GRU        next reading
                                                                 |
                                                                 v
 ALARM  <---  threshold  <---  rolling z-score  <---  error = |reading - forecast|
 (if score     (set on          (how unusual is        smoothed (EWMA)
  > line)       clean data)      this error lately?)
```

Step by step:

1. **Windowing.** Cut the series into windows of 64 past readings. Each
   window's target is the reading right after it.
2. **Forecaster.** Predicts the next reading from the window.
3. **Error.** The absolute difference between the real reading and the
   forecast.
4. **Smoothing.** An **EWMA** (exponentially weighted moving average,
   span 10) smooths the error. It is an average that weighs recent
   steps more.
5. **Rolling z-score.** Compares the smoothed error to the last 250
   steps: how many **standard deviations** (a measure of typical
   spread) above the recent average is it? The deck calls this the
   **surprise score**.
6. **Threshold.** The **alarm line**. If the score goes above it, the
   detector raises an alarm.

Steps 3–6 are the same for every detector. Only the forecaster changes.
So any difference in results comes from the forecaster.

The threshold is set on **clean** data (no faults): the lowest line
that allows at most **2 false alarms per 10,000 steps**.

### The data

- **NASA SMAP and MSL.** Real telemetry from two NASA spacecraft, with
  anomalies labeled by experts. The channels were split once: 30% **dev**
  (development, looked at while building) and 70% **held out** (scored
  once at the end). Held out: SMAP 37 channels with 49 anomaly events,
  MSL 19 channels with 25 events.
- **OrbitVal simulated missions.** A real orbit calculation decides
  when the satellite is in sunlight or in Earth's shadow (an
  **eclipse**). That drives solar power, battery and temperature. A
  mission is 24 hours at one reading per minute. I inject 5 fault types:
  brownout (power drop), sensor noise, eclipse power stress, slow sensor
  drift, and stuck sensor (frozen reading). Four have a **severity**
  knob from 0 to 1. Stuck sensor has none.
- **Held-out orbits.** Training and dev missions fly 6 orbits. Test
  missions fly 2 other orbits that no model trained on or was tuned on.

### The 4 main findings

1. **Trained models catch much smaller sudden faults.** Brownout at
   severity 0.1, held-out orbits: persistence 0/20 missions, LSTM 59/60,
   GRU 60/60.
2. **On real NASA data the gain is small.** SMAP: within the spread
   between seeds. MSL: every model run beats persistence, but only by
   2–3 of 25 events.
3. **A frozen sensor in steady sun fools every detector.** The frozen
   reading is easy to predict, so the error drops and nothing fires.
   Catches happen only when the freeze crosses an eclipse. Slow drift is
   mostly missed too. Also alarming on *low* error didn't fix it. The
   blind spot is in the scoring, not the model.
4. **Alarm lines don't transfer cleanly to new orbits.** On clean
   held-out missions, false alarms went up for persistence and LSTM and
   down for GRU.

---

## 2. The 3-minute script

About 120 words per slide. Say it at a relaxed pace. `[pause]` means
one breath.

### Slide 1 (about 1 minute)

> Satellites need early fault alarms. But faults are rare, and every
> false alarm teaches operators to ignore the system. [pause]
>
> So my question is: which faults can a deep learning detector actually
> catch? [point to the three stat cards] I test on real data from two
> NASA missions, and on simulated missions with five fault types, flown
> on two orbits the models never saw.
>
> [point to solar plot] This is simulated solar power. It drops to zero
> every time the satellite goes through Earth's shadow.
>
> [point to the flow boxes] Every detector forecasts the next reading.
> If the error is unusually big, the surprise score crosses a line and
> raises an alarm. Only the forecaster changes: persistence, which just
> repeats the last value, versus a small LSTM and GRU, three seeds each.
> [pause]

### Slide 2 (about 1 minute)

> Here's the main result, on the two new orbits. [pause]
>
> This is a small brownout, severity 0.1. [point to 0/20] Persistence
> catches none of 20 missions. [point to 59/60] The LSTM catches 59 of
> 60, over three seeds. [point to 60/60] The GRU catches all 60.
> Persistence needs severity 0.2 before it catches most of them, 17 of
> 20. So for sudden faults like this one, learning a forecast really
> pays off. [pause]
>
> [point to the bottom row of the heatmap] This bottom row is a frozen
> sensor. Every detector does badly there. That's the next slide.
>
> [point to the NASA line] On real NASA data the gain is much smaller.
> On SMAP it's within the noise between seeds. On MSL every model beats
> persistence, but only by two or three of 25 events.

### Slide 3 (about 1 minute)

> [point to the title] In steady sun, no detector catches a frozen
> sensor. [point to 0/20 · 6/60 · 20/60] These catches only happen when
> the freeze crosses an eclipse. [pause]
>
> Why? A frozen reading is easy to predict, so the error drops and
> nothing fires. To this score, a frozen sensor looks like an eclipse.
>
> [point to the three cards] Slow drift is mostly missed too. Alarming on
> low error caught nothing I could attribute to it. And the alarm line
> didn't transfer to new orbits: persistence and the LSTM got noisier
> there, the GRU quieter. [pause]
>
> [point to the bold line] So the blind spot is in the scoring, not the
> model. Better training can't fix it. [point to OrbitVal box] That's
> why this matters for OrbitVal: before a satellite's fault detection
> flies, the team sees which faults it misses. Thanks.

---

## 3. The 30-second version

> I test whether deep learning can catch spacecraft faults early. Each
> detector forecasts the next sensor reading and raises an alarm when
> the error is unusually big. I compared a no-learning baseline with a
> small LSTM and GRU, on real NASA data and on simulated missions from
> OrbitVal, my CubeSat testing tool. The trained models catch much
> smaller sudden faults, like a 0.1 brownout: 59 and 60 of 60 against 0
> of 20. But on real data the gain is small. And a frozen sensor fools
> every detector, because a frozen reading is easy to predict.

---

## 4. Numbers cheat sheet

"Of 20" = 20 missions. "Of 60" = the same 20 missions × 3 seeds.
Persistence has no seed, so it is always out of 20.

### Slide 1

| Number | What it means | Out of |
|---|---|---|
| 2 real NASA missions | SMAP and MSL, real spacecraft telemetry with expert-labeled anomalies. | — |
| 5 simulated fault types | Brownout, sensor noise, eclipse power stress, sensor drift, stuck sensor. | — |
| 2 orbits never seen in training | Test missions fly 2 orbits; training and dev fly 6 others. | 8 orbits total |
| 0 W | Simulated solar power drops to zero in Earth's shadow. Normal, not a fault. | — |
| 2 false alarms per 10,000 steps | The alarm line is the lowest line that keeps clean validation data at or under this. | per 10,000 normal steps |
| 3 seeds | Each model was trained 3 times from different random starts. | — |

### Slide 2

| Number | What it means | Out of |
|---|---|---|
| Severity 0.1 | A small brownout: solar reading × 0.91, battery reading × 0.95. | scale 0–1 |
| 0/20 | Persistence caught the 0.1 brownout in none of the missions. | 20 missions |
| 59/60* | The LSTM caught it in 59 mission runs. | 60 (20 × 3 seeds) |
| 60/60 | The GRU caught it in every mission run. | 60 |
| * 1 | One of the LSTM's 59 catches also fires on the fault-free twin, so it may be chance. | 59 catches |
| +2–3 events on MSL | Every model run caught 6 or 7 events; persistence caught 4. | 25 MSL events |
| "within seed noise on SMAP" | Models caught 28–35 events; persistence caught 30. | 49 SMAP events |

Heatmap on slide 2 (missions caught, severities 0.05, 0.1, 0.2, 0.35,
0.5, 0.75, 1.0):

| Row | Persistence (of 20) | LSTM (of 60) | GRU (of 60) |
|---|---|---|---|
| Brownout | 0, 0, 17, 20, 20, 20, 20 | 26, 59, 60, 60, 60, 60, 60 | 37, 60, 60, 60, 60, 60, 60 |
| Stuck sensor | 0 in every column | 6 in every column | 20 in every column |

The stuck row is the same in every column on purpose: severity does
nothing to a frozen sensor.

### Slide 3

| Number | What it means | Out of |
|---|---|---|
| 0/20 | Persistence never caught a frozen solar sensor. | 20 missions |
| 6/60* | The LSTM caught 6; 1 of them also fires on the twin. | 60 |
| 20/60 | The GRU caught 20. | 60 |
| Severity 1.0 drift | The strongest drift: temperature rises 8 °C over the 30-step fault. | scale 0–1 |
| Drift 0/20, 12/60, 4/60 | Persistence, LSTM, GRU catches at full drift. | 20, 60, 60 |
| SMAP loses 1–9 events per run | Two-sided alarms caught 1–9 fewer SMAP events than one-sided, depending on the run. | 49 events |
| * 1 | Same footnote as slide 2, for the stuck row. | 6 catches |

Numbers in the slide 3 notes (alarm lines on new orbits), false alarms
per 10,000 steps on clean missions, dev orbits → held-out orbits:
persistence 2.23 → 4.46, LSTM 2.83 → 4.76, GRU 3.57 → 2.83. Budget 2.
(The dev-orbit values are **dev**.)

---

## 5. Q&A prep

**1. What are the tensor shapes through the LSTM?**
Each channel is cut into windows: shape (N, 64, 1), where N = T − 64,
and the target is (N, 1). A batch is (256, 64, 1). The LSTM output is
(256, 64, 32): a 32-number hidden state after each of the 64 steps. I
keep only the last step, (256, 32), and a linear layer turns it into
(256, 1), one forecast per window.

**2. LSTM vs GRU: what's the difference?**
Both are recurrent networks with **gates**: small learned switches
that decide what to keep and what to forget. The LSTM keeps two states,
a hidden state and a cell state, with three gates: forget, input,
output. The GRU keeps one state with two gates, reset and update, so it
is smaller: 3,393 parameters against 4,513.

**3. Why gradient clipping?**
The network is trained with **backpropagation through time**: the
error signal flows back through all 64 steps of the window. Over many
steps the **gradient** (the direction to change the weights) can grow
very large, or "explode". I cap its overall size at 1.0, so one bad
batch can't throw the weights far off.

**4. Why train on normal data only?**
Faults are rare and I want the model to learn what normal telemetry
looks like. Then a fault is just whatever it predicts badly. It also
means fault labels never touch training, so they can't leak into the
model.

**5. How is the threshold set?**
On clean validation data only, no faults. I pick the lowest line that
keeps false alarms at or under 2 per 10,000 steps, and that stays under
budget for every higher line too. A run of consecutive alarm steps
counts as one false alarm, like one page to an operator. I didn't
choose the line by maximising F1, because that would tune on the labels
I'm measuring.

**6. Why does a frozen sensor lower the error?**
A forecaster predicts the next value from recent values. Once the input
window has gone flat, it predicts flat, and the frozen reading matches
it. On dev, in sunlight, persistence's error fell from 0.538 to 0.022 W.
The score only alarms on *high* error, so a drop can never fire.
The error only goes up when the freeze crosses an eclipse, because the
model expects the solar power to change and it doesn't.

**7. Why no transformer?**
Honestly, time. I dropped it to finish the core work and the evaluation.
My reasoning, which I haven't tested, is that it wouldn't fix the
frozen-sensor blind spot. It would use the same one-step forecast and
the same high-error-only score, and that's where the blind spot is.

**8. Did the models beat persistence on real data?**
Only a little. On SMAP the models caught 28 to 35 of 49 events against
30 for persistence, which is inside the spread between seeds. On MSL
every run beat persistence, but by just 2–3 of 25 events, and 2 of the
7 MSL runs went over the false-alarm budget. The models forecast better,
but that didn't reliably turn into catching more real faults.

**9. Isn't synthetic data too easy?**
Partly, yes. It's simplified on purpose: a one-node thermal model, a
constant power load, a simple magnetic field model. Large faults are
easy for everyone: from severity 0.5 up, all detectors catch nearly all
brownout, sensor-noise and eclipse-stress faults. But it's hard where it matters: drift and stuck sensors are
mostly missed. And the real-data gains are much smaller, so I don't read
the simulated results as real-world performance.

**10. How do you know you didn't tune on the test set?**
The split was fixed before building: 30% of NASA channels for dev, 70%
held out, and 2 orbits held out. While building I only looked at dev.
The held-out run was done once, on Nov 8, and frozen at commit
`3bb2e90`. A file records the SHA-256 hash of every model, and the
script refuses to run if code or weights changed. Nothing was retuned
after it.

**11. What's the clean-twin check?**
Every simulated fault mission is also flown without the fault, with
exactly the same noise. If an alarm also fires in the same steps of the
clean twin, the catch may be chance, not the fault. I report it next to
the counts. On held-out orbits, persistence and GRU have none, and the
LSTM has about one mission per fault row.

**12. How much of the code did AI write, and what did you verify?**
Claude Code wrote most of the code and drafted the slides, under a
staged plan I approved stage by stage. I reviewed each stage before the
next started and made the design decisions; they're all recorded in the
project log. For example, I corrected the two-sided alarm design, set
the freeze rule, and chose the 74-step grace period and the 80-epoch
cap. [Add one or two things you checked yourself, in your own words,
and only say them if they're true.]

---

## 6. "If I get stuck" lines

- "I don't know that one off the top of my head. I'd rather not guess.
  I can check the project log and get back to you."
- "I didn't test that, so I can't say. My guess would be [X], but it's
  untested."
- "That's outside what I measured. I only looked at [these detectors /
  this data], so I can't claim anything beyond it."

---

## Glossary (quick lookup)

- **Anomaly / fault:** something going wrong. NASA calls them anomalies;
  OrbitVal injects faults.
- **Baseline:** a simple method to compare against. Here, persistence.
- **Channel:** one sensor stream, like solar power.
- **Dev / held out:** dev data is looked at while building. Held-out
  data is scored once at the end.
- **Early stopping:** stop training when validation error hasn't
  improved for 5 epochs, and keep the best weights.
- **Epoch:** one full pass over the training data.
- **Event recall:** the share of faults caught at least once.
- **Adam:** the optimizer, the rule that updates the weights. Learning
  rate 0.001.
- **MSE (mean squared error):** the training loss: the average of
  squared forecast errors.
- **Two-sided alarm:** also alarming on unusually *low* error, with the
  false-alarm budget split between high and low.
- **Umbra / penumbra:** full shadow / partial shadow of the Earth.
