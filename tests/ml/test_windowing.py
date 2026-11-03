"""
Tests for orbitval/ml/data/windowing.py — window shapes and alignment.
"""

import numpy as np
import pytest

from orbitval.ml.data.windowing import make_windows, target_indices


def test_univariate_shapes():
    X, y = make_windows(np.arange(10.0), window=3)
    assert X.shape == (7, 3, 1)       # N = T - L = 7, C = 1
    assert y.shape == (7, 1)


def test_multivariate_shapes():
    series = np.random.default_rng(0).normal(size=(100, 4))
    X, y = make_windows(series, window=16)
    assert X.shape == (84, 16, 4)
    assert y.shape == (84, 4)


def test_window_is_past_and_target_is_next_step():
    x = np.arange(10.0)
    X, y = make_windows(x, window=3)
    np.testing.assert_array_equal(X[0, :, 0], [0, 1, 2])
    assert y[0, 0] == 3
    np.testing.assert_array_equal(X[-1, :, 0], [6, 7, 8])
    assert y[-1, 0] == 9


def test_target_never_inside_its_own_window():
    x = np.arange(50.0)
    X, y = make_windows(x, window=8)
    # every target is strictly later than every input in its window
    assert np.all(y[:, 0] > X[:, :, 0].max(axis=1))


def test_target_indices_align_with_targets():
    x = np.arange(20.0) * 2
    X, y = make_windows(x, window=5)
    idx = target_indices(len(x), 5)
    np.testing.assert_array_equal(x[idx], y[:, 0])


def test_windows_are_independent_copies():
    x = np.arange(10.0)
    X, _ = make_windows(x, window=3)
    X[0, 0, 0] = 999
    assert x[0] == 0 and X.flags["C_CONTIGUOUS"]


@pytest.mark.parametrize("length,window", [(3, 3), (2, 5)])
def test_too_short_series_rejected(length, window):
    with pytest.raises(ValueError, match="too short"):
        make_windows(np.zeros(length), window)


def test_bad_window_rejected():
    with pytest.raises(ValueError):
        make_windows(np.zeros(10), 0)
    with pytest.raises(ValueError):
        make_windows(np.zeros((2, 2, 2)), 1)
