"""
orbitval/ml/train.py

The training loop, written out by hand. No trainer framework and no
DataLoader, so every step can be walked through.

One epoch = one shuffled pass over the training windows. For each batch:
    1. forward pass:  model(x) -> prediction
    2. loss:          mean squared error against the true next value
    3. backward pass: compute the gradient of the loss
    4. clip:          cap the gradient's overall size
    5. step:          Adam updates the weights

After each epoch, measure the loss on validation data, which is never
trained on. Keep the weights from the best epoch, and stop when
validation hasn't improved for `patience` epochs.

Everything here is normal data only: the model learns what normal
telemetry looks like, and anomalies are whatever it then predicts badly.
"""

import copy
from dataclasses import dataclass, field

import numpy as np
import torch
from torch import nn


@dataclass(frozen=True)
class TrainConfig:
    lr: float = 1e-3
    batch_size: int = 256
    max_epochs: int = 80
    patience: int = 5          # epochs without improvement before stopping
    grad_clip: float = 1.0     # maximum gradient norm


@dataclass
class TrainResult:
    best_epoch: int
    best_val_loss: float
    train_losses: list[float] = field(default_factory=list)
    val_losses: list[float] = field(default_factory=list)


def batched_mse(model: nn.Module, X: torch.Tensor, y: torch.Tensor, batch_size: int = 4096) -> float:
    """Mean squared error over a whole dataset, without tracking gradients."""
    model.eval()
    total = 0.0
    with torch.no_grad():
        for start in range(0, len(X), batch_size):
            xb = X[start:start + batch_size]                # (B, L, 1)
            yb = y[start:start + batch_size]                # (B, 1)
            total += ((model(xb) - yb) ** 2).sum().item()
    return total / len(X)


def train_forecaster(
    model: nn.Module,
    X_train: np.ndarray,
    y_train: np.ndarray,
    X_val: np.ndarray,
    y_val: np.ndarray,
    config: TrainConfig = TrainConfig(),
    seed: int = 0,
    log=None,
) -> TrainResult:
    """
    Train in place. On return, `model` holds the best-validation weights.

    Args:
        X_train: (N, L, 1) input windows      y_train: (N, 1) next values
        X_val:   (M, L, 1)                    y_val:   (M, 1)
        seed: seeds the shuffling. Seed torch BEFORE building the model
            to control the initial weights too (see run_neural.py).
    """
    X = torch.from_numpy(X_train.astype(np.float32))
    y = torch.from_numpy(y_train.astype(np.float32))
    Xv = torch.from_numpy(X_val.astype(np.float32))
    yv = torch.from_numpy(y_val.astype(np.float32))

    optimizer = torch.optim.Adam(model.parameters(), lr=config.lr)
    loss_fn = nn.MSELoss()
    shuffle = torch.Generator().manual_seed(seed)

    result = TrainResult(best_epoch=-1, best_val_loss=float("inf"))
    best_weights = copy.deepcopy(model.state_dict())

    for epoch in range(config.max_epochs):
        model.train()
        order = torch.randperm(len(X), generator=shuffle)
        epoch_loss = 0.0

        for start in range(0, len(X), config.batch_size):
            idx = order[start:start + config.batch_size]
            xb, yb = X[idx], y[idx]                         # (B, L, 1), (B, 1)

            pred = model(xb)                                # (B, 1)
            loss = loss_fn(pred, yb)                        # a single number

            optimizer.zero_grad()                           # forget last batch's gradients
            loss.backward()                                 # compute new gradients
            # An RNN's gradient can explode through its many time steps.
            # If its overall size exceeds grad_clip, scale it down.
            nn.utils.clip_grad_norm_(model.parameters(), config.grad_clip)
            optimizer.step()                                # update the weights

            epoch_loss += loss.item() * len(idx)

        train_loss = epoch_loss / len(X)
        val_loss = batched_mse(model, Xv, yv)
        result.train_losses.append(train_loss)
        result.val_losses.append(val_loss)
        if log:
            log(f"epoch {epoch:2d}  train {train_loss:.6f}  val {val_loss:.6f}")

        # Early stopping: keep the best weights seen so far
        if val_loss < result.best_val_loss:
            result.best_val_loss = val_loss
            result.best_epoch = epoch
            best_weights = copy.deepcopy(model.state_dict())
        elif epoch - result.best_epoch >= config.patience:
            break

    model.load_state_dict(best_weights)
    return result
