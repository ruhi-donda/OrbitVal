"""
orbitval/ml/two_sided.py

An extra detector setting: also alarm when forecast error is unusually
LOW, as when a frozen sensor becomes easy to predict. The default shared
score in scoring.py is unchanged, and this file only reads its output.

Error can't go below zero, so z can't go much below -mean/std. Its low
tail is compressed, and a low-side alarm can't share the high side's
threshold. Each side therefore gets its own threshold:

    high[t] = z[t]     alarm when high[t] > high threshold
    low[t]  = -z[t]    alarm when low[t]  > low threshold

The false-alarm budget is split, 1 per 10k steps for each side and 2 in
total, so the setting stays comparable to the one-sided detector at 2.
On a mission, each side takes its own max over channels.

Dev data only: no function here accepts a split, and OrbitVal missions
are always drawn from the dev seeds.
"""

from dataclasses import asdict, dataclass

import numpy as np

from orbitval.config.hardware_3u_schema import HardwareConfig
from orbitval.ml.data.telemanom import ChannelSeries
from orbitval.ml.evaluate import EVAL_WARMUP, EVENT_GRACE, SHORT_GRACE, score_test, score_val
from orbitval.ml.metrics import count_channel, events_to_labels, runs, summarize
from orbitval.ml.scoring import ScoreConfig, ewma
from orbitval.ml.sim.faults import FAULTS
from orbitval.ml.sim.missions import SEVERITIES, clean_missions, make_mission, mission_seed
from orbitval.ml.sim.telemetry import CHANNELS
from orbitval.ml.threshold import Calibration, calibrate_threshold

ONE_SIDED_BUDGET = 2.0       # the existing detector, for comparison
SIDE_BUDGET = 1.0            # each side of the two-sided setting
SETTINGS = ("one_sided", "high_only", "low_only", "two_sided")
LIGHTING = {1.0: "sunlit", 0.5: "penumbra", 0.0: "umbra"}


@dataclass
class TwoSidedCalibration:
    one_sided: Calibration   # high side at 2 per 10k: the existing detector
    high: Calibration        # high side at 1 per 10k
    low: Calibration         # low side at 1 per 10k


def calibrate_sides(highs: list[np.ndarray], lows: list[np.ndarray]) -> TwoSidedCalibration:
    """All three thresholds, from normal validation data only."""
    return TwoSidedCalibration(
        one_sided=calibrate_threshold(highs, ONE_SIDED_BUDGET),
        high=calibrate_threshold(highs, SIDE_BUDGET),
        low=calibrate_threshold(lows, SIDE_BUDGET),
    )


def channel_z(detector, data: np.ndarray, warmup: int = EVAL_WARMUP) -> np.ndarray:
    """(T, C) telemetry -> (T, C) shared scores, warm-up set to NaN."""
    z = np.stack([detector.score(data[:, c], channel=c) for c in range(data.shape[1])], axis=1)
    z[:warmup] = np.nan
    return z


def mission_sides(z: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """
    (T, C) scores -> (T,) high side and (T,) low side, each the max over
    channels. A mission's high side equals missions.mission_scores().
    """
    finite = np.isfinite(z)
    high = np.where(finite, z, -np.inf).max(axis=1)
    low = np.where(finite, -z, -np.inf).max(axis=1)
    high[~finite.any(axis=1)] = np.nan
    low[~finite.any(axis=1)] = np.nan
    return high, low


def margin(high: np.ndarray, low: np.ndarray, cal: TwoSidedCalibration) -> np.ndarray:
    """
    Distance past the nearer threshold. margin > 0 exactly when either
    side alarms, so the shared metric code can count the two-sided
    setting as one score with threshold 0.
    """
    return np.maximum(high - cal.high.threshold, low - cal.low.threshold)


def setting_scores(high: np.ndarray, low: np.ndarray, cal: TwoSidedCalibration) -> dict:
    """Each setting's (score, threshold). A score alarms when > threshold."""
    return {
        "one_sided": (high, cal.one_sided.threshold),
        "high_only": (high, cal.high.threshold),
        "low_only": (low, cal.low.threshold),
        "two_sided": (margin(high, low, cal), 0.0),
    }


def detected(score: np.ndarray, threshold: float, event: tuple[int, int]) -> bool:
    start, end = event
    return bool(np.any(score[start:end + 1] > threshold))


def false_alarm_runs(score: np.ndarray, threshold: float, events: list[tuple[int, int]],
                     grace: int = EVENT_GRACE) -> list[tuple[int, int]]:
    """The alarm runs that metrics.count_channel() counts as false."""
    blamed = events_to_labels(
        [(start, min(end + grace, len(score) - 1)) for start, end in events], len(score))
    return [(a, b) for a, b in runs(score > threshold) if not blamed[a:b + 1].any()]


class Tally:
    """Pools a set of series, then gives each setting's metrics."""

    def __init__(self):
        self.parts = {name: ([], [], [], []) for name in SETTINGS}

    def add(self, high, low, labels, events, cal) -> None:
        valid = np.isfinite(high)
        for name, (score, threshold) in setting_scores(high, low, cal).items():
            counts, short, pooled_s, pooled_y = self.parts[name]
            counts.append(count_channel(score, threshold, events, EVENT_GRACE))
            short.append(count_channel(score, threshold, events, SHORT_GRACE))
            pooled_s.append(score[valid])
            pooled_y.append(labels[valid])

    def metrics(self) -> dict:
        return {name: asdict(summarize(c, np.concatenate(s), np.concatenate(y), short))
                for name, (c, short, s, y) in self.parts.items()}


def clean_rates(highs: list[np.ndarray], lows: list[np.ndarray], cal: TwoSidedCalibration) -> dict:
    """False-alarm runs per setting on normal series, plus time in low alarm."""
    steps = sum(int(np.isfinite(h).sum()) for h in highs)
    out = {"normal_steps": steps}
    for name in SETTINGS:
        n = 0
        for high, low in zip(highs, lows):
            score, threshold = setting_scores(high, low, cal)[name]
            n += len(runs(score > threshold))
        out[name] = {"false_alarms": n, "per_10k": n * 10_000 / steps}
    out["low_alarm_step_fraction"] = sum(
        int((low > cal.low.threshold).sum()) for low in lows) / steps
    out["lowest_z"] = -float(max(np.nanmax(low) for low in lows))
    return out


def locate_low_alarm(start: int, end: int, z: np.ndarray, illumination: np.ndarray) -> dict:
    """Where one low-side alarm run began: lighting, timing and channel."""
    changes = np.flatnonzero(np.diff(illumination[:start + 1]) != 0)
    return {
        "start": start,
        "length": end - start + 1,
        "lighting": LIGHTING[float(illumination[start])],
        # None: no lighting change has happened yet in this mission
        "steps_since_lighting_change": int(start - changes[-1] - 1) if changes.size else None,
        "channel": CHANNELS[int(np.nanargmin(z[start]))],
    }


def mission_low_alarms(seed: int, high, low, z, illumination, events, cal) -> list[dict]:
    return [{"seed": seed, **locate_low_alarm(a, b, z, illumination)}
            for a, b in false_alarm_runs(low, cal.low.threshold, events)]


def lighting_shares(missions: list) -> dict:
    """Share of scored steps in each lighting, to compare the alarms against."""
    illum = np.concatenate([m.illumination[EVAL_WARMUP:] for m in missions])
    return {name: float(np.mean(illum == value)) for value, name in LIGHTING.items()}


def mission_lighting(illumination: np.ndarray) -> str:
    """Same groups as missions.fault_error_analysis()."""
    if np.all(illumination == 1.0):
        return "sunlit"
    return "eclipse" if np.all(illumination == 0.0) else "crossing"


def evaluate_orbitval(detector, hardware: HardwareConfig, n_reps: int = 20, n_val: int = 30,
                      faults: tuple[str, ...] = tuple(FAULTS),
                      severities: tuple[float, ...] = SEVERITIES) -> dict:
    """
    Every setting on OrbitVal dev missions. Each rep is also flown with
    no fault, on identical noise, so a low-side alarm inside the fault
    window can be checked against the same steps of the clean twin.
    """
    val = clean_missions(hardware, "val", n_val)
    val_z = [channel_z(detector, m.data) for m in val]
    val_highs, val_lows = zip(*[mission_sides(z) for z in val_z])
    cal = calibrate_sides(list(val_highs), list(val_lows))

    twins = clean_missions(hardware, "dev", n_reps)
    twin_z = [channel_z(detector, m.data) for m in twins]
    twin_sides = [mission_sides(z) for z in twin_z]
    low_th = cal.low.threshold

    cells, rows, dev_low_alarms = [], [], []
    for fault in faults:
        for severity in severities:
            tally = Tally()
            for r in range(n_reps):
                m = make_mission(hardware, mission_seed("dev", r), fault, severity)
                z = channel_z(detector, m.data)
                high, low = mission_sides(z)
                tally.add(high, low, m.labels, m.events, cal)
                dev_low_alarms += [
                    {"fault": fault, "severity": severity, **alarm}
                    for alarm in mission_low_alarms(m.seed, high, low, z, m.illumination, m.events, cal)]

                event = m.events[0]
                window = slice(event[0], event[1] + 1)
                # Channels the fault really changed, against the clean twin
                affected = np.flatnonzero(np.any(m.data != twins[r].data, axis=0))
                on_affected = (-z[window][:, affected] > low_th).any(axis=0)
                on_twin = (-twin_z[r][window][:, affected] > low_th).any(axis=0)
                rows.append({
                    "fault": fault,
                    "severity": severity,
                    "rep": r,
                    "lighting": mission_lighting(m.illumination[window]),
                    "one_sided": detected(high, cal.one_sided.threshold, event),
                    "high": detected(high, cal.high.threshold, event),
                    "low": detected(low, low_th, event),
                    "low_on_affected": bool(on_affected.any()),
                    # On a channel the fault changed, and not on that
                    # channel of the clean twin during the same steps
                    "low_attributable": bool((on_affected & ~on_twin).any()),
                    "low_in_twin": detected(twin_sides[r][1], low_th, event),
                    # The same check for the high side, at both thresholds
                    "one_sided_in_twin": detected(twin_sides[r][0], cal.one_sided.threshold, event),
                    "high_in_twin": detected(twin_sides[r][0], cal.high.threshold, event),
                })
            cells.append({"fault": fault, "severity": severity, "metrics": tally.metrics()})

    val_low_alarms = [
        alarm for m, z, high, low in zip(val, val_z, val_highs, val_lows)
        for alarm in mission_low_alarms(m.seed, high, low, z, m.illumination, [], cal)]
    twin_low_alarms = [
        alarm for m, z, (high, low) in zip(twins, twin_z, twin_sides)
        for alarm in mission_low_alarms(m.seed, high, low, z, m.illumination, [], cal)]
    return {
        "calibration": asdict(cal),
        "reps": n_reps,
        "val": clean_rates(list(val_highs), list(val_lows), cal),
        "clean_dev": clean_rates([h for h, _ in twin_sides], [lo for _, lo in twin_sides], cal),
        "cells": cells,
        "rows": rows,
        "low_alarms": {"val": val_low_alarms, "clean_dev": twin_low_alarms, "faulted_dev": dev_low_alarms},
        "lighting_shares": {"val": lighting_shares(val), "clean_dev": lighting_shares(twins)},
        "low_tail": low_tail(detector, hardware, val, val_z, cal, n_reps),
    }


def z_floor(x: np.ndarray, pred: np.ndarray, config: ScoreConfig = ScoreConfig()) -> np.ndarray:
    """
    The lowest z each step could reach: the z of a smoothed error of 0,
    which is -mean/std of the trailing window. NaN where z is undefined.
    """
    smoothed = ewma(np.abs(x - pred), config.smooth_span)
    floor = np.full_like(smoothed, np.nan)
    # Windows of W steps; each one is the baseline of the step just after it
    windows = np.lib.stride_tricks.sliding_window_view(smoothed[:-1], config.z_window)
    floor[config.z_window:] = -windows.mean(axis=1) / np.maximum(windows.std(axis=1), config.min_std)
    return floor


def low_tail(detector, hardware: HardwareConfig, val: list, val_z: list[np.ndarray],
             cal: TwoSidedCalibration, n_reps: int) -> dict:
    """
    Can the low side reach its threshold on the channel a fault changed?
    Compares each fault's lowest z, and the floor at that step, with the
    threshold and with how low the same channel goes on clean missions.
    """
    pooled = np.concatenate(val_z)
    out = {"low_threshold": cal.low.threshold,
           "val_lowest_z_by_channel": {name: float(np.nanmin(pooled[:, c]))
                                       for c, name in enumerate(CHANNELS)}}
    for fault, channel in (("stuck_sensor", "solar_power_w"), ("sensor_drift", "temperature_c")):
        c = CHANNELS.index(channel)
        rows = []
        for r in range(n_reps):
            m = make_mission(hardware, mission_seed("dev", r), fault, 1.0)
            x = m.data[:, c]
            start, end = m.events[0]
            z = detector.score(x, channel=c)[start:end + 1]
            floor = z_floor(x, detector.forecast(x, channel=c))[start:end + 1]
            lowest = int(np.argmin(z))
            rows.append({
                "lighting": mission_lighting(m.illumination[start:end + 1]),
                "lowest_z": float(z[lowest]),
                "floor_there": float(floor[lowest]),
            })
        out[fault] = {"channel": channel, "rows": rows}
    return out


def flat_fraction(x: np.ndarray) -> float:
    """Share of steps where the value did not change at all."""
    return float(np.mean(np.diff(x) == 0))


def evaluate_telemanom(detector, channels: list[ChannelSeries], dev: list[ChannelSeries]) -> dict:
    """
    Every setting on SMAP/MSL dev channels. As in evaluate.evaluate(), the
    thresholds come from the val series of all channels, which are normal
    data, and only dev channels' test series are scored.
    """
    val_z = score_val(detector, channels)
    val_lows = [-z for z in val_z]
    cal = calibrate_sides(val_z, val_lows)

    tally, rows, low_by_channel = Tally(), [], []
    for c, z in zip(dev, score_test(detector, dev)):
        low = -z
        tally.add(z, low, c.test_labels(), c.test_events, cal)
        for i, event in enumerate(c.test_events):
            rows.append({
                "channel": c.chan_id,
                "event": i,
                "one_sided": detected(z, cal.one_sided.threshold, event),
                "high": detected(z, cal.high.threshold, event),
                "low": detected(low, cal.low.threshold, event),
            })
        n = len(false_alarm_runs(low, cal.low.threshold, c.test_events))
        if n:
            low_by_channel.append({"channel": c.chan_id, "false_alarms": n,
                                   "flat_fraction": flat_fraction(c.test)})

    val_by_channel = []
    for c, low in zip(channels, val_lows):
        n = len(runs(low > cal.low.threshold))
        if n:
            val_by_channel.append({"channel": c.chan_id, "false_alarms": n,
                                   "flat_fraction": flat_fraction(c.val)})
    return {
        "calibration": asdict(cal),
        "val": clean_rates(val_z, val_lows, cal),
        "metrics": tally.metrics(),
        "rows": rows,
        "low_alarms": {"val": val_by_channel, "dev": low_by_channel},
    }
