"""
orbitval/ml/scoring.py

Shared post-processing from forecast to anomaly score. Every detector
(persistence baseline, LSTM, GRU, transformer) goes through exactly
this pipeline, so the only thing that differs between them is the
forecast.

    pred[t]   forecast of x[t] made from x[:t]        (detector)
    err[t]  = |x[t] - pred[t]|                        absolute error
    sm[t]   = EWMA(err)[t]                            smoothed error
    z[t]    = (sm[t] - mean(sm[t-W:t])) / std(...)    rolling z-score

All three steps only look at the past, so a score at time t could be
computed live at time t — no peeking at the future.

The rolling z-score puts every channel on the same scale ("how unusual
is this error compared with the last W steps?"), which is what lets a
single threshold be shared across all channels of a spacecraft.

Steps without a defined score are NaN; downstream code treats NaN as
"no alarm".
"""

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class ScoreConfig:
    """Post-processing hyperparameters, identical for every detector."""
    smooth_span: int = 10    # EWMA span (steps)
    z_window: int = 250      # trailing window for the rolling z-score
    min_std: float = 1e-3    # std floor: flat channels would divide by ~0


def ewma(values: np.ndarray, span: int) -> np.ndarray:
    """
    Causal exponentially weighted moving average.

        s[t] = a * v[t] + (1 - a) * s[t-1],   a = 2 / (span + 1)

    Leading NaNs (steps with no forecast yet) stay NaN; smoothing
    starts at the first finite value.
    """
    if span < 1:
        raise ValueError("span must be >= 1")
    v = np.asarray(values, dtype=np.float64)
    out = np.full_like(v, np.nan)
    finite = np.flatnonzero(np.isfinite(v))
    if finite.size == 0:
        return out
    a = 2.0 / (span + 1.0)
    start = finite[0]
    s = v[start]
    out[start] = s
    for t in range(start + 1, len(v)):
        s = a * v[t] + (1.0 - a) * s
        out[t] = s
    return out


def rolling_zscore(values: np.ndarray, window: int, min_std: float) -> np.ndarray:
    """
    z[t] = (v[t] - mean(v[t-W:t])) / max(std(v[t-W:t]), min_std)

    The window is strictly before t — the current value is not part of
    its own baseline. z is NaN until W finite values have been seen.
    """
    if window < 2:
        raise ValueError("window must be >= 2")
    v = np.asarray(values, dtype=np.float64)
    out = np.full_like(v, np.nan)
    finite = np.flatnonzero(np.isfinite(v))
    if finite.size == 0:
        return out
    start = finite[0]
    tail = v[start:]
    if not np.all(np.isfinite(tail)):
        raise ValueError("NaNs are only allowed as a leading warm-up")

    # Running sums give every window's mean and variance in O(T):
    # sum(v[a:b]) = c[b] - c[a] with c = [0, cumsum(v)].
    c1 = np.concatenate([[0.0], np.cumsum(tail)])
    c2 = np.concatenate([[0.0], np.cumsum(tail ** 2)])
    t = np.arange(window, len(tail))                     # positions with W past values
    mean = (c1[t] - c1[t - window]) / window
    var = (c2[t] - c2[t - window]) / window - mean ** 2
    std = np.sqrt(np.clip(var, 0.0, None))               # clip float round-off below 0
    out[start + t] = (tail[t] - mean) / np.maximum(std, min_std)
    return out


def score_from_forecast(
    x: np.ndarray,
    pred: np.ndarray,
    config: ScoreConfig = ScoreConfig(),
) -> np.ndarray:
    """
    Full pipeline for a univariate series: (T,) values + (T,) forecasts
    -> (T,) anomaly scores. pred[t] is NaN where no forecast exists.
    """
    x = np.asarray(x, dtype=np.float64)
    pred = np.asarray(pred, dtype=np.float64)
    if x.shape != pred.shape or x.ndim != 1:
        raise ValueError("x and pred must be 1-D arrays of the same length")
    err = np.abs(x - pred)
    smoothed = ewma(err, config.smooth_span)
    return rolling_zscore(smoothed, config.z_window, config.min_std)
