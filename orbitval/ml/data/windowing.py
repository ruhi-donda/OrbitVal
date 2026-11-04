"""
orbitval/ml/data/windowing.py

Turn a time series into (input window, next value) training pairs for
a one-step-ahead forecaster.

    series:  x[0], x[1], ..., x[T-1]          shape (T, C)
    window i:   X[i] = x[i : i+L]             shape (L, C)
    target i:   y[i] = x[i+L]                 shape (C,)

so the model sees L past steps and predicts the very next one. There
are N = T - L such pairs; pair i predicts time step i + L.
"""

import numpy as np
from numpy.lib.stride_tricks import sliding_window_view


def make_windows(series: np.ndarray, window: int) -> tuple[np.ndarray, np.ndarray]:
    """
    Args:
        series: (T,) or (T, C) array. A 1-D series is treated as C=1.
        window: L, number of past steps the forecaster sees.

    Returns:
        X: (N, L, C) input windows, N = T - L
        y: (N, C)    next-step targets; y[i] is series[i + L]
    """
    if window < 1:
        raise ValueError("window must be >= 1")
    x = np.asarray(series, dtype=np.float64)
    if x.ndim == 1:
        x = x[:, None]                                   # (T,) -> (T, 1)
    if x.ndim != 2:
        raise ValueError("series must be 1-D or 2-D")
    T = x.shape[0]
    if T <= window:
        raise ValueError(f"series of length {T} is too short for window {window}")

    # sliding_window_view gives every length-L window along time:
    # (T - L + 1, C, L). Drop the last one — it has no next value to
    # predict — and move the time axis next to the batch axis.
    views = sliding_window_view(x, window, axis=0)       # (T-L+1, C, L)
    X = views[:-1].transpose(0, 2, 1)                    # (N, L, C)
    y = x[window:]                                       # (N, C)
    # Copy: the view shares memory with `x`, and torch wants contiguous data
    return np.ascontiguousarray(X), y.copy()


def target_indices(length: int, window: int) -> np.ndarray:
    """Time index each window's target lands on: [L, L+1, ..., T-1]."""
    return np.arange(window, length)
