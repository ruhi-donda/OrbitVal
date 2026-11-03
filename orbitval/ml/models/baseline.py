"""
orbitval/ml/models/baseline.py

Detector (a): persistence forecast + rolling z-score.

The forecast is "the next value equals the current value":
    pred[t] = x[t-1]
No training and no parameters. It is the bar every neural model has to
clear: if an LSTM can't beat "nothing changes", it hasn't learned the
signal's dynamics.

The score comes from the shared pipeline in orbitval/ml/scoring.py
(smoothed |error| -> rolling z-score), same as every other detector.
"""

import numpy as np

from orbitval.ml.scoring import ScoreConfig, score_from_forecast


class PersistenceBaseline:
    """Forecast-then-flag detector whose forecast is the last value."""

    name = "persistence"

    def __init__(self, score_config: ScoreConfig = ScoreConfig()):
        self.score_config = score_config

    def forecast(self, x: np.ndarray, context: np.ndarray | None = None) -> np.ndarray:
        """
        Args:
            x: (T,) series to forecast
            context: optional (T_ctx,) values immediately before x. With
                context, x[0] gets a forecast too (the last context value).

        Returns:
            pred: (T,) with pred[t] = x[t-1]; NaN where undefined
        """
        x = np.asarray(x, dtype=np.float64)
        pred = np.full_like(x, np.nan)
        pred[1:] = x[:-1]
        if context is not None and len(context):
            pred[0] = context[-1]
        return pred

    def score(self, x: np.ndarray, context: np.ndarray | None = None) -> np.ndarray:
        """
        (T,) series -> (T,) anomaly scores (NaN during warm-up).

        With context, the scoring pipeline is run over context + x so
        the smoothing and rolling statistics are already warmed up when
        x starts; only the scores for x are returned.
        """
        x = np.asarray(x, dtype=np.float64)
        if context is None or not len(context):
            return score_from_forecast(x, self.forecast(x), self.score_config)
        full = np.concatenate([np.asarray(context, dtype=np.float64), x])
        scores = score_from_forecast(full, self.forecast(full), self.score_config)
        return scores[len(context):]
