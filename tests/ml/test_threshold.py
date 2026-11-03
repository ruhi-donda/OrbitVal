"""
Tests for orbitval/ml/threshold.py — the vectorized run count is
checked against a brute-force loop.
"""

import numpy as np
import pytest

from orbitval.ml.metrics import runs
from orbitval.ml.threshold import calibrate_threshold, run_starts_per_threshold


def _brute_force(scores, th):
    s = np.where(np.isfinite(scores), scores, -np.inf)
    return len(runs(s > th))


@pytest.mark.parametrize("seed", [0, 1, 2])
def test_run_count_matches_brute_force(seed):
    rng = np.random.default_rng(seed)
    s = np.round(rng.normal(size=300), 1)        # rounding creates ties
    s[:20] = np.nan                              # warm-up
    thresholds = np.unique(s[np.isfinite(s)])
    fast = run_starts_per_threshold(s, thresholds)
    slow = [_brute_force(s, th) for th in thresholds]
    np.testing.assert_array_equal(fast, slow)


def test_run_count_simple_case():
    s = np.array([0.0, 2.0, 0.0, 3.0, 3.0, 0.0])
    # th=1: runs at (1) and (3,4) -> 2; th=2: only (3,4) -> 1; th=3: 0
    np.testing.assert_array_equal(run_starts_per_threshold(s, [1.0, 2.0, 3.0]), [2, 1, 0])


def test_calibration_meets_budget_and_is_lowest_safe():
    rng = np.random.default_rng(0)
    val = [rng.normal(size=5000) for _ in range(4)]          # 20k normal steps
    cal = calibrate_threshold(val, budget_per_10k=2.0)
    total = sum(_brute_force(s, cal.threshold) for s in val)
    assert total == cal.false_alarms
    assert cal.false_alarms_per_10k <= 2.0
    assert cal.normal_steps == 20_000
    # the next lower observed score would exceed the budget
    pooled = np.unique(np.concatenate(val))
    lower = pooled[np.searchsorted(pooled, cal.threshold) - 1]
    assert sum(_brute_force(s, lower) for s in val) * 10_000 / 20_000 > 2.0


def test_zero_budget_means_no_false_alarms():
    val = [np.random.default_rng(3).normal(size=1000)]
    cal = calibrate_threshold(val, budget_per_10k=0.0)
    assert cal.false_alarms == 0 and cal.threshold == val[0].max()


def test_generous_budget_takes_lowest_candidate():
    cal = calibrate_threshold([np.array([0.0, 1.0, 2.0])], budget_per_10k=1e9)
    assert cal.threshold == 0.0


def test_calibration_input_errors():
    with pytest.raises(ValueError):
        calibrate_threshold([np.array([1.0])], budget_per_10k=-1)
    with pytest.raises(ValueError, match="no finite"):
        calibrate_threshold([np.full(3, np.nan)])
