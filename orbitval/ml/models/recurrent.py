"""
orbitval/ml/models/recurrent.py

Detectors (b) and (c): small one-layer LSTM and GRU forecasters.

Both do the same job: read the last L values and predict the next one.
They are univariate (C = 1), and one model is shared by every channel of
a dataset. Shape names used in the comments:

    B  batch size           number of windows in this batch
    L  window length        64 past steps (WINDOW)
    H  hidden size          32 numbers of memory (HIDDEN_SIZE)

An RNN runs one step at a time. At each step it combines the new input
with its memory from the previous step, and produces new memory.

The only difference between the two is that memory:
- LSTM keeps two states, a hidden state h and a cell state c, controlled
  by three gates (forget, input, output).
- GRU keeps one state h, controlled by two gates (reset, update), so it
  has fewer parameters: 3 sets of gate weights against the LSTM's 4.

These are not trained here; see orbitval/ml/train.py.
"""

import torch
from torch import nn

WINDOW = 64        # matches the warm-up budget in orbitval/ml/evaluate.py
HIDDEN_SIZE = 32


class LSTMForecaster(nn.Module):
    """x[t-L : t] -> forecast of x[t], using an LSTM."""

    name = "lstm"

    def __init__(self, hidden_size: int = HIDDEN_SIZE):
        super().__init__()
        self.rnn = nn.LSTM(input_size=1, hidden_size=hidden_size,
                           num_layers=1, batch_first=True)
        self.head = nn.Linear(hidden_size, 1)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        # x:       (B, L, 1)    B windows, L steps, 1 value per step

        # `out` holds the hidden state after every step. h_n and c_n are
        # the final hidden and cell states; the leading 1 is num_layers.
        out, (h_n, c_n) = self.rnn(x)
        # out:     (B, L, H)
        # h_n:     (1, B, H)
        # c_n:     (1, B, H)

        # Only the state after the last step is used: it has read the
        # whole window. For a one-layer LSTM this equals h_n[0].
        last = out[:, -1, :]
        # last:    (B, H)

        pred = self.head(last)
        # pred:    (B, 1)       one forecast per window
        return pred


class GRUForecaster(nn.Module):
    """x[t-L : t] -> forecast of x[t], using a GRU."""

    name = "gru"

    def __init__(self, hidden_size: int = HIDDEN_SIZE):
        super().__init__()
        self.rnn = nn.GRU(input_size=1, hidden_size=hidden_size,
                          num_layers=1, batch_first=True)
        self.head = nn.Linear(hidden_size, 1)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        # x:       (B, L, 1)

        # Same as the LSTM, but there is no separate cell state.
        out, h_n = self.rnn(x)
        # out:     (B, L, H)
        # h_n:     (1, B, H)

        last = out[:, -1, :]
        # last:    (B, H)

        pred = self.head(last)
        # pred:    (B, 1)
        return pred


MODELS = {LSTMForecaster.name: LSTMForecaster, GRUForecaster.name: GRUForecaster}
