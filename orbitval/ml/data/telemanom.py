"""
orbitval/ml/data/telemanom.py

Loader for the NASA SMAP/MSL telemetry anomaly dataset
(Hundman et al., KDD 2018 — github.com/khundman/telemanom).

On-disk layout (after scripts/download_telemanom.sh):
    <root>/labeled_anomalies.csv
    <root>/train/<chan_id>.npy    shape (T_train, D)
    <root>/test/<chan_id>.npy     shape (T_test, D)

Column 0 of each .npy is the telemetry value, already scaled to [-1, 1]
by the dataset authors. Columns 1..D-1 are one-hot command flags. We
keep only column 0: the plan uses one shared univariate model per
spacecraft, and D differs between channels.

Labels: anomaly_sequences lists inclusive [start, end] index pairs into
the TEST series. Train series have no labeled anomalies, so they are
treated as normal data. Only channels listed in the CSV are loaded
(the Kaggle copy also ships an unlabeled T-10.npy, which is ignored),
and P-2 is skipped because its two label rows disagree.

Splits (nothing here ever looks at test labels to make a choice):
- train / val: chronological split of each channel's train series.
  val is the last `val_frac` of it — normal data used for early
  stopping and for setting the alarm threshold.
- dev / test channels: the channels themselves are split once with a
  fixed seed. Tuning looks at dev channels' test series only; the
  held-out test channels are scored once, by the final reproduce run.
"""

import csv
import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from orbitval.logging import get_logger

log = get_logger("ml.telemanom")

SPACECRAFT = ("SMAP", "MSL")


@dataclass
class ChannelSeries:
    """One telemetry channel, split and ready for scoring."""
    chan_id: str
    spacecraft: str
    train: np.ndarray                  # (T_train,) normal
    val: np.ndarray                    # (T_val,)   normal, follows train
    test: np.ndarray                   # (T_test,)  contains anomalies
    test_events: list[tuple[int, int]]  # inclusive [start, end], sorted

    def test_labels(self) -> np.ndarray:
        """Point-wise labels for the test series: True inside an event."""
        labels = np.zeros(len(self.test), dtype=bool)
        for start, end in self.test_events:
            labels[start:end + 1] = True
        return labels


def load_label_rows(csv_path: str | Path) -> list[dict]:
    """
    Parse labeled_anomalies.csv into dicts with chan_id, spacecraft,
    events (sorted list of (start, end)), and num_values.

    The `class` column is not valid JSON and is not needed, so it is
    left as the raw string.
    """
    rows = []
    with open(csv_path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            events = sorted(
                (int(start), int(end))
                for start, end in json.loads(row["anomaly_sequences"])
            )
            rows.append({
                "chan_id": row["chan_id"],
                "spacecraft": row["spacecraft"],
                "events": events,
                "num_values": int(row["num_values"]),
            })
    return rows


class AmbiguousLabels(ValueError):
    """A channel has several label rows that disagree."""


def _pick_row(rows: list[dict], test_len: int) -> dict:
    """
    Pick the label row for a channel: the one whose num_values matches
    the actual test array.

    The published CSV lists P-2 twice with the same length but
    different windows ([5300, 6420] vs [5350, 6575]). Nothing in the
    data says which is right, so such a channel raises AmbiguousLabels
    and is left out rather than guessed.
    """
    matching = [r for r in rows if r["num_values"] == test_len]
    if not matching:
        raise ValueError(
            f"channel {rows[0]['chan_id']}: no label row with "
            f"num_values={test_len}"
        )
    if any(r["events"] != matching[0]["events"] for r in matching[1:]):
        raise AmbiguousLabels(
            f"channel {rows[0]['chan_id']}: {len(matching)} label rows "
            f"with num_values={test_len} disagree on the anomaly windows"
        )
    return matching[0]


def load_spacecraft(
    root: str | Path,
    spacecraft: str,
    val_frac: float = 0.2,
) -> list[ChannelSeries]:
    """
    Load every channel of one spacecraft ("SMAP" or "MSL").

    Returns channels sorted by chan_id so downstream order (and hence
    every seeded split) is deterministic.
    """
    if spacecraft not in SPACECRAFT:
        raise ValueError(f"spacecraft must be one of {SPACECRAFT}")
    if not 0.0 < val_frac < 1.0:
        raise ValueError("val_frac must be between 0 and 1")

    root = Path(root)
    by_chan: dict[str, list[dict]] = {}
    for row in load_label_rows(root / "labeled_anomalies.csv"):
        if row["spacecraft"] == spacecraft:
            by_chan.setdefault(row["chan_id"], []).append(row)

    channels = []
    for chan_id in sorted(by_chan):
        # Column 0 only — the telemetry value (see module docstring)
        train_full = np.load(root / "train" / f"{chan_id}.npy")[:, 0]
        test = np.load(root / "test" / f"{chan_id}.npy")[:, 0]
        try:
            row = _pick_row(by_chan[chan_id], len(test))
        except AmbiguousLabels as e:
            log.warning("Skipping %s", e)
            continue

        for start, end in row["events"]:
            if not 0 <= start <= end < len(test):
                raise ValueError(
                    f"channel {chan_id}: event [{start}, {end}] outside "
                    f"test series of length {len(test)}"
                )

        # Chronological split: val is the tail of train, never shuffled
        n_val = int(round(len(train_full) * val_frac))
        channels.append(ChannelSeries(
            chan_id=chan_id,
            spacecraft=spacecraft,
            train=train_full[:-n_val].astype(np.float64),
            val=train_full[-n_val:].astype(np.float64),
            test=test.astype(np.float64),
            test_events=row["events"],
        ))
    return channels


def split_channels(
    channels: list[ChannelSeries],
    dev_frac: float = 0.3,
    seed: int = 0,
) -> tuple[list[ChannelSeries], list[ChannelSeries]]:
    """
    Split channels into (dev, test) groups with a fixed seed.

    dev channels' test series are where hyperparameters are tuned;
    test channels' test series are touched once, at the end.
    """
    rng = np.random.default_rng(seed)
    order = rng.permutation(len(channels))
    n_dev = int(round(len(channels) * dev_frac))
    dev_idx = set(order[:n_dev].tolist())
    dev = [c for i, c in enumerate(channels) if i in dev_idx]
    test = [c for i, c in enumerate(channels) if i not in dev_idx]
    return dev, test
