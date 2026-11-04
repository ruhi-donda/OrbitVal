"""
orbitval/ml/models/neural_detector.py

Wraps a trained forecaster so it plugs into the same evaluation code as
the persistence baseline: forecast(), then the shared score pipeline.

The model works in standardized units, because a neural net trains badly
on inputs of very different sizes (solar in tens of watts, magnetometer
near zero). Forecasts are converted back to original units before
scoring, so the shared pipeline sees exactly what it sees for the
baseline: raw values and raw forecasts.
"""

import numpy as np
import torch

from orbitval.ml.data.windowing import make_windows
from orbitval.ml.scoring import ScoreConfig, score_from_forecast


class NeuralDetector:
    def __init__(
        self,
        model: torch.nn.Module,
        mean: list[float],
        std: list[float],
        window: int,
        score_config: ScoreConfig = ScoreConfig(),
        batch_size: int = 4096,
    ):
        """
        Args:
            model: (B, L, 1) -> (B, 1) forecaster
            mean, std: standardization per channel, from training data
            window: L, the input window the model was trained with
        """
        self.model = model
        self.mean = mean
        self.std = std
        self.window = window
        self.score_config = score_config
        self.batch_size = batch_size
        self.name = model.name

    def forecast(self, x: np.ndarray, channel: int = 0) -> np.ndarray:
        """
        (T,) series in original units -> (T,) forecasts in original units.
        pred[t] uses only x[t-L : t]; the first L steps have no forecast.
        """
        x = np.asarray(x, dtype=np.float64)
        pred = np.full_like(x, np.nan)
        if len(x) <= self.window:
            return pred

        scaled = (x - self.mean[channel]) / self.std[channel]
        X, _ = make_windows(scaled, self.window)            # X: (N, L, 1), N = T - L
        X = torch.from_numpy(X.astype(np.float32))

        self.model.eval()
        batches = []
        with torch.no_grad():
            for start in range(0, len(X), self.batch_size):
                batches.append(self.model(X[start:start + self.batch_size]))
        scaled_pred = torch.cat(batches).numpy()[:, 0]      # (N,)

        # Window i predicts step i + L
        pred[self.window:] = scaled_pred * self.std[channel] + self.mean[channel]
        return pred

    def score(self, x: np.ndarray, context: np.ndarray | None = None, channel: int = 0) -> np.ndarray:
        """
        (T,) series -> (T,) anomaly scores (NaN during warm-up).

        With context, forecasts and rolling statistics run over
        context + x, and only the scores for x are returned. Context
        holds only past values, so nothing leaks.
        """
        x = np.asarray(x, dtype=np.float64)
        n_context = 0 if context is None else len(context)
        full = x if n_context == 0 else np.concatenate([np.asarray(context, dtype=np.float64), x])
        return score_from_forecast(full, self.forecast(full, channel), self.score_config)[n_context:]
