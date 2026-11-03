"""
Tests for orbitval/ml/metrics.py — every expected value is worked out
by hand in the comments.
"""

import math

import numpy as np
import pytest

from orbitval.ml.metrics import (
    average_precision, count_channel, events_to_labels, runs, summarize,
)


def test_runs():
    assert runs(np.array([0, 1, 1, 0, 1, 0, 0, 1], dtype=bool)) == [(1, 2), (4, 4), (7, 7)]
    assert runs(np.zeros(3, dtype=bool)) == []
    assert runs(np.ones(3, dtype=bool)) == [(0, 2)]


def test_events_to_labels_inclusive():
    np.testing.assert_array_equal(
        events_to_labels([(1, 2), (4, 4)], 6),
        [False, True, True, False, True, False],
    )


def _scores(length, high_at):
    s = np.zeros(length)
    s[list(high_at)] = 1.0
    return s


def test_detected_event_delay_and_false_alarm():
    # steps:   0 1 2 3 4 5 6 7 8 9
    # event:             [5 ....  8]
    # alarms:    1 1         x 7 8      -> run (1,2) is a false alarm,
    #                                      run (7,8) detects at delay 2
    s = _scores(10, [1, 2, 7, 8])
    c = count_channel(s, threshold=0.5, events=[(5, 8)])
    assert (c.n_events, c.n_detected, c.delays) == (1, 1, [2])
    assert c.n_false_alarms == 1
    assert c.n_normal_steps == 6                 # 10 steps - 4 event steps
    assert (c.tp, c.fp, c.fn) == (2, 2, 2)       # event steps 5,6 missed


def test_missed_event_counts_no_delay():
    c = count_channel(np.zeros(10), 0.5, events=[(3, 4)])
    assert (c.n_events, c.n_detected, c.delays, c.n_false_alarms) == (1, 0, [], 0)


def test_alarm_run_overlapping_event_is_not_false():
    # run (2,5) starts before the event (4,6) but touches it
    c = count_channel(_scores(8, [2, 3, 4, 5]), 0.5, events=[(4, 6)])
    assert c.n_false_alarms == 0 and c.delays == [0]


def test_nan_warmup_excluded_and_unscoreable_event():
    s = np.r_[np.full(5, np.nan), np.zeros(5)]
    s[7] = 1.0
    # event (1,3) lies fully in warm-up -> unscoreable, not a miss
    c = count_channel(s, 0.5, events=[(1, 3), (6, 8)])
    assert (c.n_unscoreable, c.n_events, c.n_detected, c.delays) == (1, 1, 1, [1])
    assert c.n_normal_steps == 2                 # steps 5 and 9
    assert c.fn == 2                             # steps 6, 8


def test_average_precision_hand_computed():
    # rank: 1 0 1 0 -> (P,R) = (1,.5) (.5,.5) (2/3,1) (.5,1)
    # AP = .5*1 + 0 + .5*(2/3) + 0 = 5/6
    ap = average_precision(np.array([0.9, 0.8, 0.7, 0.6]), np.array([1, 0, 1, 0], bool))
    assert ap == pytest.approx(5 / 6)


def test_average_precision_ties_move_together():
    # 0.9 -> (1, .5); tie at 0.5 -> (2/3, 1). AP = .5 + .5*2/3 = 5/6
    ap = average_precision(np.array([0.9, 0.5, 0.5]), np.array([1, 1, 0], bool))
    assert ap == pytest.approx(5 / 6)


def test_average_precision_perfect_and_no_positives():
    assert average_precision(np.array([2.0, 1.0, 0.0]), np.array([1, 1, 0], bool)) == 1.0
    assert math.isnan(average_precision(np.zeros(3), np.zeros(3, bool)))
    with pytest.raises(ValueError):
        average_precision(np.zeros(3), np.zeros(2, bool))


def test_summarize_pools_counts():
    a = count_channel(_scores(10, [1, 2, 7, 8]), 0.5, [(5, 8)])   # 1 det, 1 FA, delay 2
    b = count_channel(np.zeros(10), 0.5, [(3, 4)])                # 1 miss
    pooled_s = np.r_[_scores(10, [1, 2, 7, 8]), np.zeros(10)]
    pooled_y = np.r_[events_to_labels([(5, 8)], 10), events_to_labels([(3, 4)], 10)]
    m = summarize([a, b], pooled_s, pooled_y)
    assert m.n_events == 2 and m.event_recall == 0.5
    assert m.n_false_alarms == 1 and m.n_normal_steps == 6 + 8
    assert m.false_alarms_per_10k == pytest.approx(10_000 / 14)
    assert m.median_delay == 2
    # tp=2, fp=2, fn=2+2=4 -> P=.5, R=1/3, F1 = 4/(4+2+4) = .4
    assert (m.point_precision, m.point_recall) == (0.5, pytest.approx(1 / 3))
    assert m.point_f1 == pytest.approx(0.4)


def test_summarize_with_nothing_detected():
    c = count_channel(np.zeros(5), 0.5, [(1, 2)])
    m = summarize([c], np.zeros(5), events_to_labels([(1, 2)], 5))
    assert math.isnan(m.median_delay) and math.isnan(m.point_precision)
    assert m.event_recall == 0.0
