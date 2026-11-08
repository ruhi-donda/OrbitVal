"""
Tests for the two-sided setting: its two thresholds, its alarm counts,
and that it reproduces the one-sided detector and stays on dev data.
"""

import json

import numpy as np
import pytest

pytest.importorskip("torch")

from orbitval import logging as ov_logging  # noqa: E402
from orbitval.config.hardware_3u_schema import load_hardware_config  # noqa: E402
from orbitval.ml import run_two_sided  # noqa: E402
from orbitval.ml.data.telemanom import load_spacecraft, split_channels  # noqa: E402
from orbitval.ml.evaluate import EVENT_GRACE, evaluate  # noqa: E402
from orbitval.ml.metrics import count_channel, runs  # noqa: E402
from orbitval.ml.models.baseline import PersistenceBaseline  # noqa: E402
from orbitval.ml.scoring import ScoreConfig, ewma, score_from_forecast  # noqa: E402
from orbitval.ml.sim.missions import (  # noqa: E402
    SPLIT_SEED_BASE, detectability_map, make_mission, mission_scores, mission_seed,
)
from orbitval.ml.two_sided import (  # noqa: E402
    SETTINGS, Tally, calibrate_sides, channel_z, clean_rates, detected, evaluate_orbitval,
    evaluate_telemanom, false_alarm_runs, locate_low_alarm, margin, mission_sides, setting_scores,
    z_floor,
)
from tests.conftest import SATELLITE_YAML  # noqa: E402
from tests.ml.test_telemanom_pipeline import dataset  # noqa: E402, F401  (fixture)


@pytest.fixture(scope="module")
def hw():
    ov_logging.set_log_level("WARNING")
    return load_hardware_config(SATELLITE_YAML)


def _noise(seed=0, n=20_000):
    return np.random.default_rng(seed).normal(size=n)


def test_each_side_has_its_own_budget():
    z = _noise()
    cal = calibrate_sides([z], [-z])
    assert cal.one_sided.budget_per_10k == 2.0
    assert cal.high.budget_per_10k == cal.low.budget_per_10k == 1.0
    assert len(runs(z > cal.high.threshold)) <= 2           # 1 per 10k over 20k steps
    assert len(runs(-z > cal.low.threshold)) <= 2
    assert cal.high.threshold >= cal.one_sided.threshold    # a smaller budget is stricter


def test_a_compressed_low_tail_gets_a_lower_threshold():
    # Like z from an error bounded at zero: long high tail, short low tail
    z = np.random.default_rng(0).exponential(size=20_000) - 1.0
    cal = calibrate_sides([z], [-z])
    assert cal.low.threshold < 1.0 < cal.high.threshold


def test_mission_sides_matches_the_shared_mission_score(hw):
    m = make_mission(hw, mission_seed("dev", 0), "stuck_sensor", 1.0)
    detector = PersistenceBaseline()
    z = channel_z(detector, m.data)
    high, low = mission_sides(z)
    np.testing.assert_array_equal(high, mission_scores(detector, m.data))
    scored = np.isfinite(low)
    np.testing.assert_array_equal(low[scored], -z[scored].min(axis=1))


def test_mission_sides_takes_each_sides_own_max_over_channels():
    z = np.array([[np.nan, np.nan], [1.0, -3.0], [-2.0, 0.5], [np.nan, -1.0]])
    high, low = mission_sides(z)
    np.testing.assert_array_equal(high, [np.nan, 1.0, 0.5, -1.0])
    np.testing.assert_array_equal(low, [np.nan, 3.0, 2.0, 1.0])


def test_margin_alarms_exactly_when_either_side_does():
    high, low = _noise(1, 5000), _noise(2, 5000)
    cal = calibrate_sides([high], [low])
    alarm = margin(high, low, cal) > 0
    expected = (high > cal.high.threshold) | (low > cal.low.threshold)
    np.testing.assert_array_equal(alarm, expected)


def test_margin_is_nan_during_warmup():
    high = np.array([np.nan, 1.0])
    cal = calibrate_sides([np.array([0.0, 1.0])], [np.array([0.0, 1.0])])
    assert np.isnan(margin(high, -high, cal)[0])


def test_false_alarm_runs_match_the_shared_count():
    z = _noise(3, 5000)
    events = [(1000, 1029), (3000, 3029)]
    for threshold in (1.0, 2.0, 3.0):
        got = false_alarm_runs(z, threshold, events)
        assert len(got) == count_channel(z, threshold, events, EVENT_GRACE).n_false_alarms


def test_low_error_alarms_only_on_the_low_side():
    # Steady noisy error, then the error collapses to zero (a frozen sensor)
    n = 700
    x = np.random.default_rng(0).normal(0, 0.1, n)
    x[500:530] = x[499]
    z = score_from_forecast(x, np.r_[np.nan, x[:-1]], ScoreConfig())
    high, low = z, -z
    event = (500, 529)
    assert np.nanmax(low[500:530]) > 1.5                     # z drops well below normal
    assert detected(low, 1.5, event) and not detected(high, 3.0, event)


def test_z_floor_is_the_z_of_a_zero_error_and_bounds_every_z():
    rng = np.random.default_rng(0)
    x = rng.normal(0, 0.1, 800)
    pred = np.r_[np.nan, x[:-1]]
    config = ScoreConfig()
    z, floor = score_from_forecast(x, pred, config), z_floor(x, pred, config)
    scored = np.isfinite(z)
    np.testing.assert_array_equal(np.isfinite(floor), scored)
    assert np.all(z[scored] >= floor[scored])
    # By hand at one step: -mean/std of the window just before it
    smoothed = ewma(np.abs(x - pred), config.smooth_span)
    window = smoothed[500 - config.z_window:500]
    assert floor[500] == pytest.approx(-window.mean() / window.std())


def test_detected_only_looks_inside_the_event():
    score = np.array([9.0, 0.0, 0.0, 9.0])
    assert not detected(score, 1.0, (1, 2))
    assert detected(score, 1.0, (0, 1))
    assert not detected(np.array([np.nan, np.nan]), 1.0, (0, 1))


def test_clean_rates_count_runs_per_side():
    high = np.array([np.nan, 5.0, 5.0, 0.0, 5.0, 0.0])
    low = np.array([np.nan, 0.0, 0.0, 2.0, 0.0, 0.0])
    cal = calibrate_sides([np.array([0.0, 4.0])], [np.array([0.0, 1.0])])
    rates = clean_rates([high], [low], cal)
    assert rates["normal_steps"] == 5
    assert rates["high_only"]["false_alarms"] == 2
    assert rates["low_only"]["false_alarms"] == 1
    assert rates["two_sided"]["false_alarms"] == 1      # (1..4) is one run across both sides
    assert rates["low_alarm_step_fraction"] == pytest.approx(1 / 5)
    assert rates["lowest_z"] == -2.0


def test_locate_low_alarm_reports_lighting_timing_and_channel():
    illum = np.array([1.0, 1.0, 0.5, 0.0, 0.0, 0.0])
    z = np.zeros((6, 6))
    z[5, 2] = -4.0
    a = locate_low_alarm(5, 5, z, illum)
    assert a["lighting"] == "umbra" and a["steps_since_lighting_change"] == 2
    assert a["channel"] == "temperature_c" and a["length"] == 1
    # Nothing has changed yet at the first step
    assert locate_low_alarm(0, 0, z, illum)["steps_since_lighting_change"] is None


def test_tally_gives_every_setting_and_the_union_counts():
    z = _noise(4, 3000)
    cal = calibrate_sides([z], [-z])
    labels = np.zeros(3000, dtype=bool)
    labels[100:130] = True
    t = Tally()
    t.add(z, -z, labels, [(100, 129)], cal)
    metrics = t.metrics()
    assert set(metrics) == set(SETTINGS)
    score, threshold = setting_scores(z, -z, cal)["two_sided"]
    assert metrics["two_sided"]["n_false_alarms"] == len(false_alarm_runs(score, threshold, [(100, 129)]))


def test_orbitval_one_sided_setting_reproduces_the_existing_detector(hw):
    detector = PersistenceBaseline()
    faults, severities = ("stuck_sensor", "power_brownout"), (1.0,)
    r = evaluate_orbitval(detector, hw, n_reps=2, n_val=3, faults=faults, severities=severities)
    cal, cells = detectability_map(detector, hw, split="dev", n_reps=2, n_val=3,
                                   budget_per_10k=2.0, faults=faults, severities=severities)
    assert r["calibration"]["one_sided"]["threshold"] == cal.threshold
    for mine, theirs in zip(r["cells"], cells):
        m = mine["metrics"]["one_sided"]
        assert m["n_detected"] == theirs.metrics.n_detected
        assert m["n_false_alarms"] == theirs.metrics.n_false_alarms
        assert m["pr_auc"] == pytest.approx(theirs.metrics.pr_auc)


def test_orbitval_rows_agree_with_the_metrics_and_use_only_dev_missions(hw, monkeypatch):
    import orbitval.ml.two_sided as module
    seeds = []
    real = module.make_mission
    monkeypatch.setattr(module, "make_mission", lambda hardware, seed, *a, **k: (
        seeds.append(seed), real(hardware, seed, *a, **k))[1])
    r = evaluate_orbitval(PersistenceBaseline(), hw, n_reps=2, n_val=2,
                          faults=("stuck_sensor",), severities=(1.0,))
    assert seeds and all(SPLIT_SEED_BASE["dev"] <= s < SPLIT_SEED_BASE["test"] for s in seeds)

    m = r["cells"][0]["metrics"]
    rows = r["rows"]
    assert sum(x["one_sided"] for x in rows) == m["one_sided"]["n_detected"]
    assert sum(x["low"] for x in rows) == m["low_only"]["n_detected"]
    assert sum(x["high"] or x["low"] for x in rows) == m["two_sided"]["n_detected"]
    for x in rows:
        assert not x["low_attributable"] or x["low_on_affected"]


def test_telemanom_one_sided_setting_reproduces_evaluate_and_skips_held_out(dataset):  # noqa: F811
    channels = load_spacecraft(dataset, "SMAP")
    dev, held_out = split_channels(channels, dev_frac=0.5)
    detector = PersistenceBaseline()
    r = evaluate_telemanom(detector, channels, dev)
    old = evaluate(detector, channels, dev, budget_per_10k=2.0)
    assert r["calibration"]["one_sided"]["threshold"] == old.calibration.threshold
    assert r["metrics"]["one_sided"]["n_detected"] == old.metrics.n_detected
    assert r["metrics"]["one_sided"]["n_false_alarms"] == old.metrics.n_false_alarms
    scored = {x["channel"] for x in r["rows"]}
    assert scored <= {c.chan_id for c in dev}
    assert not scored & {c.chan_id for c in held_out}


def test_run_and_summarize_end_to_end(tmp_path, capsys, monkeypatch):
    # One cell is enough here; the full map is covered by the run itself
    import orbitval.ml.two_sided as module
    monkeypatch.setattr(run_two_sided, "evaluate_orbitval", lambda d, hw, reps, val: module.evaluate_orbitval(
        d, hw, reps, val, faults=("stuck_sensor", "sensor_drift"), severities=(1.0,)))
    run_two_sided.main(["run", "--dataset", "orbitval", "--model", "persistence",
                        "--reps", "1", "--val", "2", "--outdir", str(tmp_path),
                        "--config", SATELLITE_YAML])
    saved = json.loads((tmp_path / "two_sided" / "orbitval_persistence_seed0.json").read_text())
    assert saved["reps"] == 1 and len(saved["rows"]) == 2

    capsys.readouterr()
    run_two_sided.main(["summarize", "--outdir", str(tmp_path)])
    out = capsys.readouterr().out
    assert "stuck_sensor" in out and "where low-side false alarms" in out


def test_cli_requires_dataset_and_model(tmp_path):
    with pytest.raises(SystemExit):
        run_two_sided.main(["run", "--outdir", str(tmp_path)])
