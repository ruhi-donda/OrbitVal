"""Tests for scripts/compare_results.py, which judges whether a rerun reproduced."""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[2] / "scripts"))
from compare_results import compare_dirs, compare_with_demo, differences  # noqa: E402


def _cell(detected=3):
    return {"fault": "stuck_sensor", "severity": 1.0, "metrics": {"n_detected": detected, "n_events": 20}}


def _result(threshold=5.5, detected=3, seconds=10.0):
    return {"model": "lstm", "seed": 0, "reps": 20, "train_seconds": seconds,
            "calibration": {"threshold": threshold}, "cells": [_cell(detected)],
            "error_analysis": {"stuck_sensor": {"by_lighting": {"all": {"n_detected": detected, "n": 20}}}}}


def _write(tmp_path, name, result):
    d = tmp_path / name / "results"
    d.mkdir(parents=True)
    (d / "orbitval_lstm_seed0.json").write_text(json.dumps(result))
    return tmp_path / name


def test_equal_values_have_no_differences():
    assert differences(_result(), _result()) == []


def test_training_time_may_differ():
    assert differences(_result(seconds=1.0), _result(seconds=99.0)) == []


def test_changed_number_is_reported_with_its_path():
    found = differences(_result(detected=3), _result(detected=4))
    assert any("n_detected" in line and "3 vs 4" in line for line in found)


def test_nan_equals_nan_but_not_a_number():
    assert differences({"a": float("nan")}, {"a": float("nan")}) == []
    assert differences({"a": float("nan")}, {"a": 1.0}) != []


def test_missing_key_and_list_length_are_reported():
    assert differences({"a": 1}, {}) == ["/a: only in new"]
    assert differences([1, 2], [1]) == [": length 2 vs 1"]


def test_string_change_is_reported():
    assert differences({"a": "x"}, {"a": "y"}) == ["/a: x vs y"]


def test_compare_dirs_reports_missing_files_and_changes(tmp_path):
    new = _write(tmp_path, "new", _result(threshold=5.5))
    ref = _write(tmp_path, "ref", _result(threshold=5.6))
    (ref / "results" / "extra.json").write_text("{}")
    found = compare_dirs(new, ref)
    assert "results/extra.json: only in reference" in found
    assert any("threshold" in line for line in found)


def test_compare_dirs_also_checks_two_sided_results(tmp_path):
    new = _write(tmp_path, "new", _result())
    ref = _write(tmp_path, "ref", _result())
    assert compare_dirs(new, ref) == []
    (new / "two_sided").mkdir()
    (ref / "two_sided").mkdir()
    (new / "two_sided" / "a.json").write_text('{"threshold": 1.0}')
    (ref / "two_sided" / "a.json").write_text('{"threshold": 2.0}')
    assert compare_dirs(new, ref) == ["two_sided/a.json/threshold: 1.0 vs 2.0"]


@pytest.mark.parametrize("threshold,same", [(5.5, True), (5.6, False)])
def test_compare_with_demo_checks_thresholds(tmp_path, threshold, same):
    new = _write(tmp_path, "new", _result(threshold=threshold))
    demo = tmp_path / "demo"
    demo.mkdir()
    (demo / "manifest.json").write_text(json.dumps(
        {"lstm": {"0": {"file": "orbitval_lstm_seed0.pt", "threshold": 5.5}}}))
    (demo / "maps.json").write_text(json.dumps(
        {"lstm": {"seeds": 1, "reps": 20,
                  "cells": [{"fault": "stuck_sensor", "severity": 1.0, "recall": 0.15,
                             "detected": 3, "total": 20}],
                  "stuck_by_lighting": {"all": {"n_detected": 3, "n": 20}}}}))
    assert (compare_with_demo(new, demo) == []) is same


def test_tracked_demo_numbers_load():
    from compare_results import DEST
    assert (DEST / "manifest.json").exists() and (DEST / "maps.json").exists()
