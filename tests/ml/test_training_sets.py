"""
Tests for orbitval/ml/data/training_sets.py. Numpy only, so these run in
the core CI job too.
"""

import numpy as np
import pytest

from orbitval import logging as ov_logging
from orbitval.config.hardware_3u_schema import load_hardware_config
from orbitval.ml.data.telemanom import ChannelSeries
from orbitval.ml.data.training_sets import orbitval_training_set, telemanom_training_set
from orbitval.ml.sim.missions import clean_missions
from orbitval.ml.sim.telemetry import CHANNELS
from tests.conftest import SATELLITE_YAML


def _channel(chan_id, offset, n_train=40, n_val=10):
    series = offset + np.arange(n_train + n_val, dtype=np.float64)
    return ChannelSeries(chan_id, "SMAP", series[:n_train], series[n_train:],
                         np.zeros(5), [])


def test_telemanom_shapes_and_identity_scaling():
    ts = telemanom_training_set([_channel("A", 0.0), _channel("B", 1000.0)], window=8)
    assert ts.X_train.shape == (2 * (40 - 8), 8, 1)
    assert ts.y_train.shape == (2 * (40 - 8), 1)
    assert ts.X_val.shape == (2 * 10, 8, 1)            # one target per val step
    assert (ts.mean, ts.std) == ([0.0], [1.0])
    assert ts.X_train.dtype == np.float32


def test_telemanom_no_window_spans_two_channels():
    ts = telemanom_training_set([_channel("A", 0.0), _channel("B", 1000.0)], window=8)
    spread = ts.X_train.max(axis=1) - ts.X_train.min(axis=1)
    assert spread.max() == 7                           # A's and B's values never mix


def test_telemanom_val_targets_are_exactly_the_val_series():
    c = _channel("A", 0.0)
    ts = telemanom_training_set([c], window=8)
    np.testing.assert_array_equal(ts.y_val[:, 0], c.val)
    np.testing.assert_array_equal(ts.X_val[0, :, 0], c.train[-8:])     # inputs are the past


def test_telemanom_skips_channels_shorter_than_the_window():
    ts = telemanom_training_set([_channel("A", 0.0), _channel("B", 5.0, n_train=4)], window=8)
    assert ts.X_train.shape[0] == 40 - 8


def test_orbitval_scaler_from_train_only_and_shapes():
    ov_logging.set_log_level("WARNING")
    hw = load_hardware_config(SATELLITE_YAML)
    ts = orbitval_training_set(hw, window=16, n_train=2, n_val=1)
    train = clean_missions(hw, "train", 2)
    all_train = np.concatenate([m.data for m in train])
    np.testing.assert_allclose(ts.mean, all_train.mean(axis=0))
    np.testing.assert_allclose(ts.std, all_train.std(axis=0))
    per_series = 1440 - 16
    assert ts.X_train.shape == (2 * len(CHANNELS) * per_series, 16, 1)
    assert ts.X_val.shape == (1 * len(CHANNELS) * per_series, 16, 1)
    # standardized training data pooled over channels: mean ~0, std ~1
    assert abs(ts.y_train.mean()) < 0.01 and ts.y_train.std() == pytest.approx(1.0, abs=0.01)
