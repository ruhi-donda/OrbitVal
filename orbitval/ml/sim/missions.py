"""
orbitval/ml/sim/missions.py

Missions for training and evaluating detectors on OrbitVal telemetry.

A mission is 24 h of telemetry at 60 s steps (1440 steps, ~15 orbits)
from one orbit, with its own noise and attitude phase.
A faulted mission has exactly one fault event of FAULT_STEPS steps.
Its onset is random, but always after the evaluation warm-up.

Splits use disjoint seed ranges so no mission appears in two of them:
    train  clean missions the models learn from          (stage 3)
    val    clean missions: early stopping + threshold
    dev    faulted missions for looking at results while building
    test   faulted missions scored once, by scripts/reproduce.sh

Orbits are held out too: train, val and dev missions fly ORBIT_POOL;
test missions fly only TEST_ORBITS, which no model ever trains on or is
tuned on. A model can't pass the test by memorising eclipse timing.

Paired design: inside a split, rep r uses the same base mission (orbit,
noise, onset) for every fault and every severity. A change across the
detectability map then comes from the fault, not from luck of the draw.
"""

from dataclasses import dataclass

import numpy as np

from orbitval.config.hardware_3u_schema import HardwareConfig
from orbitval.engine.injection import run_injection
from orbitval.ml.evaluate import EVAL_WARMUP, EVENT_GRACE, SHORT_GRACE
from orbitval.ml.metrics import DetectionMetrics, count_channel, runs, summarize
from orbitval.ml.sim.faults import FAULTS, build_fault
from orbitval.ml.sim.telemetry import CHANNELS, frames_to_array, generate_telemetry
from orbitval.ml.threshold import Calibration, calibrate_threshold

# (altitude km, inclination deg, epoch). Mid inclinations and different
# seasons, so every orbit has eclipses but of different lengths.
ORBIT_POOL = (
    (500.0, 51.6, "2026-01-15T00:00:00Z"),
    (550.0, 53.0, "2026-03-01T00:00:00Z"),
    (525.0, 45.0, "2026-04-20T06:00:00Z"),
    (450.0, 40.0, "2026-07-15T00:00:00Z"),
    (600.0, 65.0, "2026-09-01T18:00:00Z"),
    (540.0, 70.0, "2026-12-01T00:00:00Z"),
)
# Test missions only. Altitude and inclination both lie inside the range
# of ORBIT_POOL, so this tests a new orbit, not an extrapolation.
TEST_ORBITS = (
    (575.0, 60.0, "2026-06-10T12:00:00Z"),
    (480.0, 51.6, "2026-10-10T00:00:00Z"),
)

SPLIT_SEED_BASE = {"train": 0, "val": 100_000, "dev": 200_000, "test": 300_000}
SEVERITIES = (0.05, 0.1, 0.2, 0.35, 0.5, 0.75, 1.0)
FAULT_STEPS = 30            # every fault lasts 30 steps = 30 min
MISSION_HOURS = 24.0
STEP_S = 60.0


@dataclass
class Mission:
    data: np.ndarray                 # (T, C) channels in telemetry.CHANNELS order
    labels: np.ndarray               # (T,) True while the fault is active
    events: list[tuple[int, int]]    # inclusive (start, end) steps
    illumination: np.ndarray         # (T,)
    seed: int
    orbit: tuple[float, float, str]  # (altitude km, inclination deg, epoch)
    fault: str | None = None
    severity: float = 0.0


def mission_seed(split: str, index: int) -> int:
    return SPLIT_SEED_BASE[split] + index


def orbits_for_seed(seed: int) -> tuple:
    """
    Which orbits a mission may fly. Decided by the seed's range, so a
    test-split seed can't end up on a training orbit or the reverse.
    """
    return TEST_ORBITS if seed >= SPLIT_SEED_BASE["test"] else ORBIT_POOL


def _pick_onset(rng: np.random.Generator, illum: np.ndarray, sunlit_only: bool) -> int:
    """
    Random onset step, so the whole event lies after the warm-up (with
    a 60-step margin) and inside the mission. With sunlit_only, the
    whole event must also be in full sunlight; if no such window exists
    the constraint is dropped.
    """
    n = len(illum)
    candidates = np.arange(EVAL_WARMUP + 60, n - FAULT_STEPS)
    if sunlit_only:
        ok = [o for o in candidates if np.all(illum[o:o + FAULT_STEPS] == 1.0)]
        if ok:
            candidates = np.array(ok)
    return int(rng.choice(candidates))


def make_mission(
    hardware: HardwareConfig,
    seed: int,
    fault: str | None = None,
    severity: float = 0.0,
    onset: int | None = None,
) -> Mission:
    """
    One mission, clean (fault=None) or with one fault event. The onset
    step is drawn from the seed unless given (the demo lets you pick it).
    """
    rng = np.random.default_rng(seed)
    orbits = orbits_for_seed(seed)
    orbit = orbits[rng.integers(len(orbits))]
    alt, inc, epoch = orbit
    sim = generate_telemetry(hardware, alt, inc, epoch, seed=seed,
                             duration_hours=MISSION_HOURS, step_s=STEP_S)
    frames = sim.frames
    labels = np.zeros(len(frames), dtype=bool)

    if fault is not None:
        # The onset is drawn the same way for every fault, so a rep
        # shares its onset across faults. Only eclipse_power_stress needs
        # a sunlit window: an eclipse during an eclipse isn't a fault.
        if onset is None:
            onset_rng = np.random.default_rng([seed, 1])
            sunlit_only = fault == "eclipse_power_stress"
            onset = _pick_onset(onset_rng, sim.illumination, sunlit_only)
        elif not 0 <= onset <= len(frames) - FAULT_STEPS:
            raise ValueError(f"onset must be in [0, {len(frames) - FAULT_STEPS}]")
        f = build_fault(fault, severity,
                        t_start=onset * STEP_S,
                        # is_active is inclusive at both ends, so N steps
                        # span (N - 1) step lengths
                        duration_s=(FAULT_STEPS - 1) * STEP_S,
                        seed=seed)
        frames, _trace = run_injection(frames, [f])
        # Labels come from the fault's own is_active() — the same test
        # the injector used — so they match the injection exactly.
        labels = np.array([f.is_active(fr.t) for fr in frames])

    return Mission(
        data=frames_to_array(frames),
        labels=labels,
        events=runs(labels),
        illumination=sim.illumination,
        seed=seed,
        orbit=orbit,
        fault=fault,
        severity=severity,
    )


def clean_missions(hardware: HardwareConfig, split: str, n: int) -> list[Mission]:
    return [make_mission(hardware, mission_seed(split, i)) for i in range(n)]


def mission_scores(detector, data: np.ndarray, warmup: int = EVAL_WARMUP) -> np.ndarray:
    """
    Score each channel separately with the same univariate detector,
    then take the max over channels: the mission is alarming if any
    channel is. Each channel's score is a rolling z-score, so they are
    on comparable scales.

    (T, C) -> (T,), with the shared warm-up set to NaN.
    """
    per_channel = np.stack(
        [detector.score(data[:, c], channel=c) for c in range(data.shape[1])], axis=1)
    finite = np.isfinite(per_channel)
    scores = np.where(finite, per_channel, -np.inf).max(axis=1)
    scores[~finite.any(axis=1)] = np.nan
    scores[:warmup] = np.nan
    return scores


@dataclass
class CellResult:
    fault: str
    severity: float
    metrics: DetectionMetrics


def calibrate_on_missions(detector, missions: list[Mission], budget_per_10k: float) -> Calibration:
    return calibrate_threshold([mission_scores(detector, m.data) for m in missions], budget_per_10k)


def evaluate_cell(detector, missions: list[Mission], threshold: float) -> DetectionMetrics:
    """Metrics for one (fault, severity) cell of the map."""
    counts, counts_short, pooled_s, pooled_y = [], [], [], []
    for m in missions:
        s = mission_scores(detector, m.data)
        counts.append(count_channel(s, threshold, m.events, EVENT_GRACE))
        counts_short.append(count_channel(s, threshold, m.events, SHORT_GRACE))
        valid = np.isfinite(s)
        pooled_s.append(s[valid])
        pooled_y.append(m.labels[valid])
    return summarize(counts, np.concatenate(pooled_s), np.concatenate(pooled_y), counts_short)


def detectability_map(
    detector,
    hardware: HardwareConfig,
    split: str = "dev",
    n_reps: int = 20,
    n_val: int = 30,
    budget_per_10k: float = 2.0,
    faults: tuple[str, ...] = tuple(FAULTS),
    severities: tuple[float, ...] = SEVERITIES,
) -> tuple[Calibration, list[CellResult]]:
    """
    1. threshold <- clean val missions at the false-alarm budget
    2. for each (fault, severity): n_reps faulted missions -> metrics
    """
    if split not in ("dev", "test"):
        raise ValueError("detectability maps are computed on 'dev' or 'test'")
    calibration = calibrate_on_missions(
        detector, clean_missions(hardware, "val", n_val), budget_per_10k)
    cells = []
    for fault in faults:
        for sev in severities:
            missions = [make_mission(hardware, mission_seed(split, r), fault, sev)
                        for r in range(n_reps)]
            cells.append(CellResult(fault, sev, evaluate_cell(detector, missions, calibration.threshold)))
    return calibration, cells


def fault_error_analysis(
    detector,
    hardware: HardwareConfig,
    fault: str,
    severity: float,
    channel: str,
    threshold: float,
    split: str = "dev",
    n_reps: int = 20,
) -> dict:
    """
    Does the fault make the forecast error on its channel go up or down?

    Paired comparison: each rep is flown twice, with and without the
    fault, on identical noise. Inside the fault window we compare the
    mean |forecast error| of the two runs, in the channel's own units.
    Results are grouped by lighting, since a frozen sensor behaves very
    differently in sunlight, in eclipse, and across a transition.
    """
    c = CHANNELS.index(channel)
    rows = []
    for r in range(n_reps):
        seed = mission_seed(split, r)
        clean = make_mission(hardware, seed)
        faulted = make_mission(hardware, seed, fault, severity)
        start, end = faulted.events[0]
        window = slice(start, end + 1)

        err_clean = np.abs(clean.data[:, c] - detector.forecast(clean.data[:, c], channel=c))[window]
        err_fault = np.abs(faulted.data[:, c] - detector.forecast(faulted.data[:, c], channel=c))[window]
        peak = float(np.max(mission_scores(detector, faulted.data)[window]))

        illum = faulted.illumination[window]
        lighting = "sunlit" if np.all(illum == 1.0) else "eclipse" if np.all(illum == 0.0) else "crossing"
        rows.append({
            "seed": seed,
            "lighting": lighting,
            "mean_error_clean": float(err_clean.mean()),
            "mean_error_faulted": float(err_fault.mean()),
            "peak_score": peak,
            "detected": peak > threshold,
        })

    def group(items: list[dict]) -> dict:
        return {
            "n": len(items),
            "mean_error_clean": float(np.mean([i["mean_error_clean"] for i in items])),
            "mean_error_faulted": float(np.mean([i["mean_error_faulted"] for i in items])),
            "n_error_down": sum(i["mean_error_faulted"] < i["mean_error_clean"] for i in items),
            "n_detected": sum(i["detected"] for i in items),
            "mean_peak_score": float(np.mean([i["peak_score"] for i in items])),
        }

    by_lighting = {"all": group(rows)}
    for lighting in ("sunlit", "eclipse", "crossing"):
        items = [i for i in rows if i["lighting"] == lighting]
        if items:
            by_lighting[lighting] = group(items)
    return {"fault": fault, "severity": severity, "channel": channel,
            "threshold": threshold, "by_lighting": by_lighting, "rows": rows}
