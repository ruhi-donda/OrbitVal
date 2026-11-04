"""
orbitval/ml/data/training_sets.py

Build training and validation windows for the shared univariate models.
Each channel of each series is windowed separately and then pooled, so
no window ever spans two channels or two missions.

All arrays: X (N, L, 1), y (N, 1). Normal data only.
"""

from dataclasses import dataclass

import numpy as np

from orbitval.config.hardware_3u_schema import HardwareConfig
from orbitval.ml.data.telemanom import ChannelSeries
from orbitval.ml.data.windowing import make_windows
from orbitval.ml.sim.missions import clean_missions


@dataclass
class TrainingSet:
    X_train: np.ndarray
    y_train: np.ndarray
    X_val: np.ndarray
    y_val: np.ndarray
    mean: list[float]    # per channel, in original units
    std: list[float]


def _pool(pairs: list[tuple[np.ndarray, np.ndarray]]) -> tuple[np.ndarray, np.ndarray]:
    return (np.concatenate([p[0] for p in pairs]).astype(np.float32),
            np.concatenate([p[1] for p in pairs]).astype(np.float32))


def telemanom_training_set(channels: list[ChannelSeries], window: int) -> TrainingSet:
    """
    Windows from every channel's train and val series. The dataset is
    already scaled to [-1, 1], so standardization is the identity.

    Each val series is prefixed with the last L train values: val targets
    then start at the first val step, using only past inputs.
    """
    train = [make_windows(c.train, window) for c in channels if len(c.train) > window]
    val = [make_windows(np.concatenate([c.train[-window:], c.val]), window)
           for c in channels if len(c.train) >= window]
    X_train, y_train = _pool(train)
    X_val, y_val = _pool(val)
    return TrainingSet(X_train, y_train, X_val, y_val, mean=[0.0], std=[1.0])


def orbitval_training_set(
    hardware: HardwareConfig,
    window: int,
    n_train: int = 20,
    n_val: int = 10,
) -> TrainingSet:
    """
    Windows from clean missions, every channel pooled into one model.
    Mean and std come from the training missions only, per channel.
    """
    train_missions = clean_missions(hardware, "train", n_train)
    val_missions = clean_missions(hardware, "val", n_val)

    all_train = np.concatenate([m.data for m in train_missions])    # (T_total, C)
    mean = all_train.mean(axis=0)
    std = all_train.std(axis=0)

    def windows(missions):
        pairs = []
        for m in missions:
            scaled = (m.data - mean) / std
            pairs += [make_windows(scaled[:, c], window) for c in range(scaled.shape[1])]
        return _pool(pairs)

    X_train, y_train = windows(train_missions)
    X_val, y_val = windows(val_missions)
    return TrainingSet(X_train, y_train, X_val, y_val,
                       mean=mean.tolist(), std=std.tolist())
