"""
orbitval/ml/evaluate.py

Calibrate a detector's threshold on validation data, then score it on
a set of evaluation channels.

A detector is any object with
    score(x, context=None) -> scores     (T,) -> (T,), NaN = no score
"""

from dataclasses import dataclass

import numpy as np

from orbitval.ml.data.telemanom import ChannelSeries
from orbitval.ml.metrics import DetectionMetrics, count_channel, summarize
from orbitval.ml.threshold import Calibration, calibrate_threshold

# Steps at the start of every test series where no detector is scored.
# Test series start cold (no earlier context), and each detector needs
# some history before its score means anything: the rolling z-score
# needs z_window=250 smoothed errors, and the neural models will need a
# 64-step input window on top. Using one fixed warm-up for every
# detector keeps the comparison fair — all are scored on the same steps.
EVAL_WARMUP = 320

# Steps after an event during which a new alarm is blamed on the event
# (the recovery spike when a fault ends), not counted as false. 10 steps
# covers the EWMA smoothing (span 10). Same value for SMAP/MSL and
# OrbitVal missions.
EVENT_GRACE = 10


@dataclass
class EvaluationResult:
    detector: str
    calibration: Calibration
    metrics: DetectionMetrics


def score_val(detector, channels: list[ChannelSeries]) -> list[np.ndarray]:
    """
    Validation scores, one array per channel. Each val series follows
    its train series in time, so train is passed as context — the
    detector only ever uses past values, so this leaks nothing.
    """
    return [detector.score(c.val, context=c.train) for c in channels]


def score_test(detector, channels: list[ChannelSeries], warmup: int = EVAL_WARMUP) -> list[np.ndarray]:
    """Test scores with the shared warm-up blanked out (set to NaN)."""
    out = []
    for c in channels:
        s = np.array(detector.score(c.test), dtype=np.float64)
        s[:warmup] = np.nan
        if not np.all(np.isfinite(s[warmup:])):
            raise ValueError(
                f"{getattr(detector, 'name', detector)} produced NaN scores "
                f"after the {warmup}-step warm-up on channel {c.chan_id}"
            )
        out.append(s)
    return out


def evaluate(
    detector,
    calib_channels: list[ChannelSeries],
    eval_channels: list[ChannelSeries],
    budget_per_10k: float = 2.0,
    warmup: int = EVAL_WARMUP,
) -> EvaluationResult:
    """
    1. threshold <- calibrate on calib_channels' val series (normal only)
    2. metrics   <- apply that fixed threshold to eval_channels' test series
    """
    calibration = calibrate_threshold(score_val(detector, calib_channels), budget_per_10k)

    test_scores = score_test(detector, eval_channels, warmup)
    counts, pooled_s, pooled_y = [], [], []
    for c, s in zip(eval_channels, test_scores):
        counts.append(count_channel(s, calibration.threshold, c.test_events, EVENT_GRACE))
        valid = np.isfinite(s)
        pooled_s.append(s[valid])
        pooled_y.append(c.test_labels()[valid])

    metrics = summarize(counts, np.concatenate(pooled_s), np.concatenate(pooled_y))
    return EvaluationResult(
        detector=getattr(detector, "name", type(detector).__name__),
        calibration=calibration,
        metrics=metrics,
    )
