"""
orbitval/ml/threshold.py

Choose the alarm threshold from NORMAL validation data alone, so that
the detector raises at most `budget` false alarms per 10,000 steps.

Why a false-alarm budget instead of "the threshold that maximizes F1"?
Maximizing F1 needs anomaly labels, so it tunes on the very thing being
measured. A budget needs only normal data, and it matches how operators
think: "I can tolerate about N false pages per day".

A false alarm is an alarm *run* (consecutive steps above threshold
count once), the same definition used in metrics.py. Every step of the
validation data is normal, so every run there is a false alarm.

How the run count is computed for many thresholds at once:
a run starts at step t exactly when the score crosses upward through
the threshold th there:

    prev[t] <= th < s[t]        (prev[t] = s[t-1], or -inf at t = 0)

So each upward step "owns" the interval [prev[t], s[t]) of thresholds,
and count(th) = number of intervals containing th
              = #(lo <= th) - #(hi <= th)
which two sorted arrays and np.searchsorted answer for every
candidate threshold in one shot.
"""

from dataclasses import dataclass

import numpy as np


def run_starts_per_threshold(scores: np.ndarray, thresholds: np.ndarray) -> np.ndarray:
    """
    For one series, how many alarm runs `scores > th` produces, for each
    th in `thresholds`. NaN scores never alarm (they act like -inf).
    """
    s = np.asarray(scores, dtype=np.float64)
    s = np.where(np.isfinite(s), s, -np.inf)
    prev = np.concatenate([[-np.inf], s[:-1]])
    up = s > prev                                   # steps that rise
    lo = np.sort(prev[up])                          # interval [lo, hi)
    hi = np.sort(s[up])
    th = np.asarray(thresholds, dtype=np.float64)
    return (np.searchsorted(lo, th, side="right")
            - np.searchsorted(hi, th, side="right"))


@dataclass
class Calibration:
    threshold: float
    false_alarms: int            # runs on the validation data at threshold
    normal_steps: int            # scored validation steps
    false_alarms_per_10k: float
    budget_per_10k: float


def calibrate_threshold(
    val_scores: list[np.ndarray],
    budget_per_10k: float = 2.0,
) -> Calibration:
    """
    Lowest threshold whose false-alarm rate on the validation series is
    <= budget — and stays <= budget for every higher threshold too.

    The second condition matters because the run count is not strictly
    monotone: raising the threshold can split one long run into two.
    Taking the lowest *safe* threshold above the last violation avoids
    landing in such a dip.

    Args:
        val_scores: one score array per validation series (channel)
        budget_per_10k: allowed false alarms per 10,000 normal steps
    """
    if budget_per_10k < 0:
        raise ValueError("budget must be >= 0")
    finite = [s[np.isfinite(s)] for s in val_scores]
    normal_steps = int(sum(f.size for f in finite))
    if normal_steps == 0:
        raise ValueError("no finite validation scores to calibrate on")

    # Only thresholds equal to an observed score can change the count
    candidates = np.unique(np.concatenate(finite))
    counts = sum(run_starts_per_threshold(s, candidates) for s in val_scores)
    rates = counts * 10_000 / normal_steps

    # At the largest candidate nothing exceeds it, so rate 0 <= budget
    # and `violations[-1]` (if any) always has a safe candidate above it.
    violations = np.flatnonzero(rates > budget_per_10k)
    idx = 0 if violations.size == 0 else violations[-1] + 1
    return Calibration(
        threshold=float(candidates[idx]),
        false_alarms=int(counts[idx]),
        normal_steps=normal_steps,
        false_alarms_per_10k=float(rates[idx]),
        budget_per_10k=budget_per_10k,
    )
