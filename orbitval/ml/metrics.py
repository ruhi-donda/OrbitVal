"""
orbitval/ml/metrics.py

Detection metrics. Two views of the same alarms:

EVENT view (what an operator cares about) — the headline numbers:
- event recall: fraction of labeled anomaly events with at least one
  alarm inside [start, end]
- false alarms per 10k steps: alarm *runs* (consecutive alarm steps
  count once) that touch no labeled event (or its short grace period,
  see count_channel), per 10,000 normal steps
- detection delay: steps from event start to its first alarm, over the
  detected events; we report the median

POINT view (each time step is a sample) — reported for comparison:
- precision / recall / F1 over time steps, with NO point-adjustment.
  Point-adjusted F1 marks a whole event as detected if any one step is
  flagged, which inflates scores so much that random scores can look
  good (Kim et al., AAAI 2022). We deliberately don't use it.
- PR-AUC (average precision): threshold-free ranking quality of the
  raw scores.

Steps whose score is NaN (detector warm-up) are excluded everywhere.
An event with no scored step at all is "unscoreable" and left out of
recall rather than counted as a miss for every detector alike.
"""

from dataclasses import dataclass, field

import numpy as np


def runs(mask: np.ndarray) -> list[tuple[int, int]]:
    """Inclusive (start, end) of every run of consecutive True values."""
    m = np.asarray(mask, dtype=bool).astype(np.int8)
    # Pad with False on both sides, then +1 marks a run starting and
    # -1 marks the step after a run ends.
    d = np.diff(np.concatenate([[0], m, [0]]))
    starts = np.flatnonzero(d == 1)
    ends = np.flatnonzero(d == -1) - 1
    return list(zip(starts.tolist(), ends.tolist()))


def events_to_labels(events: list[tuple[int, int]], length: int) -> np.ndarray:
    """Point-wise labels: True at every step inside an inclusive event."""
    labels = np.zeros(length, dtype=bool)
    for start, end in events:
        labels[start:end + 1] = True
    return labels


@dataclass
class ChannelCounts:
    """Raw counts for one series; summed across channels by summarize()."""
    n_events: int = 0              # scoreable events
    n_unscoreable: int = 0         # events entirely inside the warm-up
    n_detected: int = 0
    delays: list[int] = field(default_factory=list)
    n_false_alarms: int = 0        # alarm runs touching no event
    n_normal_steps: int = 0        # scored steps outside every event
    tp: int = 0                    # point-wise counts over scored steps
    fp: int = 0
    fn: int = 0


def count_channel(
    scores: np.ndarray,
    threshold: float,
    events: list[tuple[int, int]],
    grace: int = 0,
) -> ChannelCounts:
    """
    Apply `score > threshold` to one series and count everything.

    grace: steps after each event's end in which a new alarm run is
    blamed on the event, not counted as a false alarm. When a fault
    ends, the signal snaps back and a forecaster sees one more big
    error; that alarm is caused by the fault. It is also NOT a
    detection, which must happen inside [start, end]. Grace steps are
    left out of the normal-step count too. Point-wise metrics use the
    plain labels.
    """
    scores = np.asarray(scores, dtype=np.float64)
    valid = np.isfinite(scores)
    alarms = valid & (np.where(valid, scores, -np.inf) > threshold)
    labels = events_to_labels(events, len(scores))
    blamed = events_to_labels(                     # event + grace steps
        [(start, min(end + grace, len(scores) - 1)) for start, end in events],
        len(scores),
    )

    c = ChannelCounts()
    for start, end in events:
        if not valid[start:end + 1].any():
            c.n_unscoreable += 1
            continue
        c.n_events += 1
        hits = np.flatnonzero(alarms[start:end + 1])
        if hits.size:
            c.n_detected += 1
            c.delays.append(int(hits[0]))      # steps after event start

    c.n_false_alarms = sum(
        1 for a, b in runs(alarms) if not blamed[a:b + 1].any()
    )
    c.n_normal_steps = int((valid & ~blamed).sum())
    c.tp = int((alarms & labels).sum())
    c.fp = int((alarms & ~labels).sum())
    c.fn = int((valid & labels & ~alarms).sum())
    return c


def average_precision(scores: np.ndarray, labels: np.ndarray) -> float:
    """
    Area under the precision-recall curve, as a step sum:
        AP = sum_k (R_k - R_{k-1}) * P_k
    over thresholds k from highest score to lowest. Tied scores move
    together (one threshold), matching sklearn's average_precision_score.
    NaN if there are no positive labels.
    """
    scores = np.asarray(scores, dtype=np.float64)
    labels = np.asarray(labels, dtype=bool)
    if scores.shape != labels.shape:
        raise ValueError("scores and labels must have the same shape")
    n_pos = int(labels.sum())
    if n_pos == 0:
        return float("nan")

    order = np.argsort(-scores, kind="mergesort")   # highest score first
    s = scores[order]
    y = labels[order]
    tp = np.cumsum(y)
    fp = np.cumsum(~y)
    # Only the last position of each run of tied scores is a real threshold
    last_of_tie = np.r_[np.flatnonzero(np.diff(s)), len(s) - 1]
    tp, fp = tp[last_of_tie], fp[last_of_tie]

    precision = tp / (tp + fp)
    recall = tp / n_pos
    recall_prev = np.r_[0.0, recall[:-1]]
    return float(np.sum((recall - recall_prev) * precision))


@dataclass
class DetectionMetrics:
    """Aggregate metrics over a set of channels (counts are pooled)."""
    n_channels: int
    n_events: int
    n_unscoreable: int
    n_detected: int
    event_recall: float
    n_false_alarms: int
    n_normal_steps: int
    false_alarms_per_10k: float
    median_delay: float            # steps; NaN if nothing was detected
    point_precision: float
    point_recall: float
    point_f1: float
    pr_auc: float
    # The same false-alarm count under a shorter grace period, for comparison
    n_false_alarms_short_grace: int | None = None
    n_normal_steps_short_grace: int | None = None
    false_alarms_per_10k_short_grace: float = float("nan")


def _safe_div(a: float, b: float) -> float:
    return a / b if b else float("nan")


def summarize(
    counts: list[ChannelCounts],
    pooled_scores: np.ndarray,
    pooled_labels: np.ndarray,
    counts_short_grace: list[ChannelCounts] | None = None,
) -> DetectionMetrics:
    """
    Pool per-channel counts into one set of metrics. Pooling (summing
    counts) rather than averaging per-channel rates weights every event
    and every step equally, whatever channel it came from.

    pooled_scores / pooled_labels: all scored steps of all channels,
    concatenated (NaN steps already removed), for PR-AUC.
    counts_short_grace: optional counts for the same alarms under a shorter
    grace period. Grace only affects false alarms, so that's all it adds.
    """
    n_events = sum(c.n_events for c in counts)
    n_detected = sum(c.n_detected for c in counts)
    n_fa = sum(c.n_false_alarms for c in counts)
    n_normal = sum(c.n_normal_steps for c in counts)
    tp = sum(c.tp for c in counts)
    fp = sum(c.fp for c in counts)
    fn = sum(c.fn for c in counts)
    delays = [d for c in counts for d in c.delays]

    precision = _safe_div(tp, tp + fp)
    recall = _safe_div(tp, tp + fn)
    f1 = _safe_div(2 * tp, 2 * tp + fp + fn)

    short_fa, short_normal, short_rate = None, None, float("nan")
    if counts_short_grace is not None:
        short_fa = sum(c.n_false_alarms for c in counts_short_grace)
        short_normal = sum(c.n_normal_steps for c in counts_short_grace)
        short_rate = _safe_div(short_fa * 10_000, short_normal)

    return DetectionMetrics(
        n_channels=len(counts),
        n_events=n_events,
        n_unscoreable=sum(c.n_unscoreable for c in counts),
        n_detected=n_detected,
        event_recall=_safe_div(n_detected, n_events),
        n_false_alarms=n_fa,
        n_normal_steps=n_normal,
        false_alarms_per_10k=_safe_div(n_fa * 10_000, n_normal),
        median_delay=float(np.median(delays)) if delays else float("nan"),
        point_precision=precision,
        point_recall=recall,
        point_f1=f1,
        pr_auc=average_precision(pooled_scores, pooled_labels),
        n_false_alarms_short_grace=short_fa,
        n_normal_steps_short_grace=short_normal,
        false_alarms_per_10k_short_grace=short_rate,
    )
