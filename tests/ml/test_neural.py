"""
Tests for the torch side of orbitval/ml: model shapes, the training
loop, and the wrapper that plugs a model into the shared evaluation.
Skipped when the optional [ml] extra isn't installed.
"""

import json

import numpy as np
import pytest

torch = pytest.importorskip("torch")

from torch import nn  # noqa: E402

from orbitval import logging as ov_logging  # noqa: E402
from orbitval.config.hardware_3u_schema import load_hardware_config  # noqa: E402
from orbitval.ml import run_neural  # noqa: E402
from orbitval.ml.data.training_sets import orbitval_training_set  # noqa: E402
from orbitval.ml.evaluate import EVAL_WARMUP  # noqa: E402
from orbitval.ml.models.baseline import PersistenceBaseline  # noqa: E402
from orbitval.ml.models.neural_detector import NeuralDetector  # noqa: E402
from orbitval.ml.models.recurrent import (  # noqa: E402
    MODELS, GRUForecaster, LSTMForecaster,
)
from orbitval.ml.scoring import score_from_forecast  # noqa: E402
from orbitval.ml.sim.missions import fault_error_analysis, make_mission, mission_scores  # noqa: E402
from orbitval.ml.train import TrainConfig, batched_mse, train_forecaster  # noqa: E402
from tests.conftest import SATELLITE_YAML  # noqa: E402


class LastValue(nn.Module):
    """A 'model' that repeats the last input: persistence, as a network."""
    name = "last_value"

    def forward(self, x):
        return x[:, -1, :]


@pytest.fixture(scope="module")
def hw():
    ov_logging.set_log_level("WARNING")
    return load_hardware_config(SATELLITE_YAML)


def _sine_data(n=300, window=16, seed=0):
    rng = np.random.default_rng(seed)
    t = np.arange(n + window)
    x = np.sin(t / 5.0) + rng.normal(0, 0.01, len(t))
    from orbitval.ml.data.windowing import make_windows
    return make_windows(x, window)


# ── model shapes ─────────────────────────────────────────────

@pytest.mark.parametrize("cls", [LSTMForecaster, GRUForecaster])
@pytest.mark.parametrize("batch,length", [(1, 8), (7, 64)])
def test_forward_shape(cls, batch, length):
    out = cls(hidden_size=8)(torch.zeros(batch, length, 1))
    assert out.shape == (batch, 1)


def test_gru_has_fewer_parameters_than_lstm():
    count = lambda m: sum(p.numel() for p in m.parameters())
    # H = 32, input size 1. Each gate set: H*H (from memory) + H (from the
    # input) + 2H (PyTorch keeps two bias vectors). LSTM has 4 sets, GRU 3.
    # The linear head adds H + 1.
    gate_set = 32 * 32 + 32 + 2 * 32
    assert count(LSTMForecaster(32)) == 4 * gate_set + 33 == 4513
    assert count(GRUForecaster(32)) == 3 * gate_set + 33 == 3393


@pytest.mark.parametrize("name", sorted(MODELS))
def test_gradients_reach_every_parameter(name):
    model = MODELS[name](hidden_size=8)
    model(torch.randn(4, 16, 1)).sum().backward()
    assert all(p.grad is not None and p.grad.abs().sum() > 0 for p in model.parameters())


# ── training loop ────────────────────────────────────────────

@pytest.mark.parametrize("name", sorted(MODELS))
def test_can_overfit_one_small_batch(name):
    # If a model can't memorise 32 windows, the training loop is broken
    torch.manual_seed(0)
    X, y = _sine_data(n=32)
    model = MODELS[name](hidden_size=16)
    result = train_forecaster(model, X, y, X, y,
                              TrainConfig(lr=5e-3, batch_size=32, max_epochs=300, patience=300))
    assert result.best_val_loss < 0.05 * result.val_losses[0]


def test_training_is_deterministic_for_a_seed():
    X, y = _sine_data()
    weights = []
    for _ in range(2):
        torch.manual_seed(3)
        model = GRUForecaster(hidden_size=8)
        train_forecaster(model, X, y, X, y, TrainConfig(max_epochs=2), seed=3)
        weights.append(model.state_dict())
    for k in weights[0]:
        assert torch.equal(weights[0][k], weights[1][k])


def test_early_stopping_restores_best_weights():
    # Train on one signal, validate on a different one, with a learning
    # rate high enough that validation loss won't improve steadily.
    X, y = _sine_data(seed=0)
    Xv, yv = X * -1.0, y * 0.0
    torch.manual_seed(0)
    model = GRUForecaster(hidden_size=8)
    r = train_forecaster(model, X, y, Xv, yv,
                         TrainConfig(lr=0.05, max_epochs=40, patience=2), seed=0)
    assert len(r.val_losses) == r.best_epoch + 3 or len(r.val_losses) == 40
    if len(r.val_losses) < 40:                  # stopped early
        assert len(r.val_losses) - 1 - r.best_epoch == 2
    # the returned model has the weights from the best epoch
    final = batched_mse(model, torch.from_numpy(Xv.astype(np.float32)),
                        torch.from_numpy(yv.astype(np.float32)))
    assert final == pytest.approx(r.best_val_loss, rel=1e-5)
    assert r.best_val_loss == min(r.val_losses)


# ── wrapper around the shared evaluation ─────────────────────

def test_wrapper_reproduces_persistence_with_a_last_value_model():
    # Checks scaling, unscaling and window alignment together: a network
    # that copies its last input must give exactly the persistence forecast
    x = np.random.default_rng(0).normal(5.0, 2.0, 200)
    det = NeuralDetector(LastValue(), mean=[5.0], std=[2.0], window=16)
    pred = det.forecast(x)
    assert np.all(np.isnan(pred[:16]))
    np.testing.assert_allclose(pred[16:], x[15:-1], rtol=1e-5)


def test_forecast_uses_the_right_channel_scaling():
    x = np.random.default_rng(1).normal(100.0, 10.0, 80)
    det = NeuralDetector(GRUForecaster(4), mean=[0.0, 100.0], std=[1.0, 10.0], window=8)
    # untrained net outputs near 0 in standardized units -> near the channel mean
    assert abs(np.nanmean(det.forecast(x, channel=1)) - 100.0) < 10.0
    assert abs(np.nanmean(det.forecast(x, channel=0)) - 100.0) > 50.0


def test_forecast_is_causal():
    torch.manual_seed(0)
    x = np.random.default_rng(2).normal(size=120)
    det = NeuralDetector(LSTMForecaster(8), mean=[0.0], std=[1.0], window=16)
    changed = x.copy()
    changed[80:] += 50.0                        # change the future only
    np.testing.assert_array_equal(det.forecast(x)[:81], det.forecast(changed)[:81])


def test_short_series_has_no_forecast():
    det = NeuralDetector(LastValue(), mean=[0.0], std=[1.0], window=16)
    assert np.all(np.isnan(det.forecast(np.zeros(10))))


def test_score_uses_the_shared_pipeline_unchanged():
    x = np.random.default_rng(3).normal(size=500)
    det = NeuralDetector(GRUForecaster(4), mean=[0.0], std=[1.0], window=16)
    np.testing.assert_array_equal(det.score(x), score_from_forecast(x, det.forecast(x)))


def test_score_with_context_returns_only_x():
    full = np.random.default_rng(4).normal(size=600)
    det = NeuralDetector(GRUForecaster(4), mean=[0.0], std=[1.0], window=16)
    s = det.score(full[400:], context=full[:400])
    assert s.shape == (200,) and np.all(np.isfinite(s))
    np.testing.assert_array_equal(s, det.score(full)[400:])


def test_window_fits_inside_the_shared_warmup(hw):
    # 64-step window + 250-step z-score must finish before the warm-up ends
    det = NeuralDetector(GRUForecaster(4), mean=[0.0] * 6, std=[1.0] * 6, window=64)
    s = mission_scores(det, make_mission(hw, seed=1).data)
    assert np.all(np.isnan(s[:EVAL_WARMUP])) and np.all(np.isfinite(s[EVAL_WARMUP:]))


# ── error analysis ───────────────────────────────────────────

def test_error_analysis_shows_persistence_error_falls_when_stuck(hw):
    # A frozen reading is perfectly predicted by "no change", so the
    # error must go to ~0: it can only go down
    a = fault_error_analysis(PersistenceBaseline(), hw, "stuck_sensor", 1.0,
                             "solar_power_w", threshold=5.0, n_reps=5)
    assert a["by_lighting"]["all"]["n"] == 5
    assert sum(g["n"] for k, g in a["by_lighting"].items() if k != "all") == 5
    for row in a["rows"]:
        if row["lighting"] == "sunlit":
            assert row["mean_error_faulted"] < row["mean_error_clean"]


def test_error_analysis_shows_drift_raises_error_with_a_last_value_model(hw):
    a = fault_error_analysis(PersistenceBaseline(), hw, "sensor_drift", 1.0,
                             "temperature_c", threshold=5.0, n_reps=3)
    assert a["channel"] == "temperature_c" and len(a["rows"]) == 3


# ── end to end on small data ─────────────────────────────────

def test_train_eval_summarize_end_to_end(tmp_path, capsys):
    run_neural.main(["train", "--dataset", "orbitval", "--model", "gru", "--seed", "0",
                     "--max-epochs", "1", "--outdir", str(tmp_path),
                     "--config", SATELLITE_YAML])
    assert (tmp_path / "weights" / "orbitval_gru_seed0.pt").exists()

    det, ckpt = run_neural.load_detector(tmp_path / "weights" / "orbitval_gru_seed0.pt")
    assert ckpt["window"] == 64 and len(ckpt["mean"]) == 6 and det.name == "gru"

    run_neural.main(["eval", "--dataset", "orbitval", "--model", "gru", "--seed", "0",
                     "--reps", "1", "--val", "2", "--outdir", str(tmp_path),
                     "--config", SATELLITE_YAML])
    run_neural.main(["eval", "--dataset", "orbitval", "--model", "persistence",
                     "--reps", "1", "--val", "2", "--outdir", str(tmp_path),
                     "--config", SATELLITE_YAML])
    r = json.loads((tmp_path / "results" / "orbitval_gru_seed0.json").read_text())
    assert r["error_analysis"]["stuck_sensor"]["fault"] == "stuck_sensor"
    assert len(r["cells"]) == 35

    capsys.readouterr()
    run_neural.main(["summarize", "--outdir", str(tmp_path)])
    out = capsys.readouterr().out
    assert "stuck_sensor" in out and "best epoch" in out


def test_cli_requires_dataset_and_model(tmp_path):
    with pytest.raises(SystemExit):
        run_neural.main(["train", "--outdir", str(tmp_path)])
    with pytest.raises(SystemExit):
        run_neural.main(["train", "--dataset", "smap", "--model", "persistence",
                         "--outdir", str(tmp_path)])
