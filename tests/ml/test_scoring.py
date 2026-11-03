"""
Tests for orbitval/ml/scoring.py and the persistence baseline.
"""

import numpy as np
import pytest

from orbitval.ml.models.baseline import PersistenceBaseline
from orbitval.ml.scoring import ScoreConfig, ewma, rolling_zscore, score_from_forecast


def test_ewma_matches_recurrence():
    v = np.array([np.nan, 1.0, 0.0, 0.0])
    out = ewma(v, span=3)                       # a = 0.5
    assert np.isnan(out[0])
    np.testing.assert_allclose(out[1:], [1.0, 0.5, 0.25])


def test_ewma_all_nan_and_bad_span():
    assert np.all(np.isnan(ewma(np.full(4, np.nan), 3)))
    with pytest.raises(ValueError):
        ewma(np.zeros(3), 0)


def test_rolling_zscore_uses_only_past_window():
    v = np.array([1.0, 2.0, 3.0, 10.0])
    z = rolling_zscore(v, window=3, min_std=1e-9)
    assert np.all(np.isnan(z[:3]))
    mean, std = 2.0, np.std([1.0, 2.0, 3.0])
    assert z[3] == pytest.approx((10.0 - mean) / std)


def test_rolling_zscore_is_causal():
    rng = np.random.default_rng(1)
    v = rng.normal(size=200)
    z = rolling_zscore(v, window=20, min_std=1e-3)
    v2 = v.copy()
    v2[150:] += 100.0                            # change the future only
    z2 = rolling_zscore(v2, window=20, min_std=1e-3)
    np.testing.assert_array_equal(z[:150], z2[:150])


def test_rolling_zscore_std_floor_on_flat_signal():
    v = np.concatenate([np.zeros(10), [0.01]])
    z = rolling_zscore(v, window=5, min_std=1e-2)
    assert z[-1] == pytest.approx(1.0)           # 0.01 / floor 0.01


def test_rolling_zscore_rejects_nan_after_warmup():
    with pytest.raises(ValueError, match="leading"):
        rolling_zscore(np.array([1.0, np.nan, 2.0, 3.0]), 2, 1e-3)
    assert np.all(np.isnan(rolling_zscore(np.full(5, np.nan), 2, 1e-3)))
    with pytest.raises(ValueError):
        rolling_zscore(np.zeros(5), 1, 1e-3)


def test_score_from_forecast_rejects_shape_mismatch():
    with pytest.raises(ValueError):
        score_from_forecast(np.zeros(5), np.zeros(4))


def test_persistence_forecast_is_previous_value():
    det = PersistenceBaseline()
    pred = det.forecast(np.array([1.0, 2.0, 4.0]))
    assert np.isnan(pred[0])
    np.testing.assert_array_equal(pred[1:], [1.0, 2.0])
    pred = det.forecast(np.array([1.0, 2.0]), context=np.array([7.0]))
    np.testing.assert_array_equal(pred, [7.0, 1.0])


def test_persistence_warmup_length():
    cfg = ScoreConfig(smooth_span=5, z_window=20)
    s = PersistenceBaseline(cfg).score(np.random.default_rng(0).normal(size=100))
    # pred NaN at t=0 -> first smoothed error at t=1 -> first z at 1 + 20
    assert np.all(np.isnan(s[:21])) and np.all(np.isfinite(s[21:]))


def test_persistence_context_warms_up_and_flags_a_spike():
    rng = np.random.default_rng(0)
    cfg = ScoreConfig(smooth_span=3, z_window=50)
    context = rng.normal(0, 0.01, 200)
    x = rng.normal(0, 0.01, 100)
    x[60] += 1.0
    s = PersistenceBaseline(cfg).score(x, context=context)
    assert s.shape == x.shape and np.all(np.isfinite(s))
    assert np.argmax(s) in (60, 61)              # spike enters error at t and t+1
