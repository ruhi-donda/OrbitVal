"""
Tests for orbitval/ml/sim — telemetry generator, severity-scaled
faults, and fault-onset labels on generated missions.
"""

import math

import numpy as np
import pytest

from orbitval.config.hardware_3u_schema import load_hardware_config
from orbitval.faults.base import FaultScenario
from orbitval.ml.evaluate import EVAL_WARMUP
from orbitval.ml.metrics import count_channel
from orbitval.ml.models.baseline import PersistenceBaseline
from orbitval.ml.sim.faults import FAULTS, SensorDrift, StuckSensor, build_fault
from orbitval.ml.sim.missions import (
    FAULT_STEPS, ORBIT_POOL, SPLIT_SEED_BASE, TEST_ORBITS, detectability_map,
    make_mission, mission_scores, mission_seed,
)
from orbitval.ml.sim.telemetry import (
    CHANNELS, generate_telemetry, frames_to_array, illumination_from_periods,
)
from orbitval import logging as ov_logging
from tests.conftest import SATELLITE_YAML, make_frame


@pytest.fixture(scope="module")
def hw():
    ov_logging.set_log_level("WARNING")
    return load_hardware_config(SATELLITE_YAML)


@pytest.fixture(scope="module")
def sim(hw):
    return generate_telemetry(hw, 550.0, 53.0, "2026-03-01T00:00:00Z", seed=7)


# ── generator ────────────────────────────────────────────────

def test_illumination_from_periods():
    periods = [{"type": "umbra", "start_t": 120.0, "end_t": 300.0},
               {"type": "penumbra", "start_t": 300.0, "end_t": 360.0}]
    np.testing.assert_array_equal(
        illumination_from_periods(periods, 8, 60.0),
        [1, 1, 0, 0, 0, 0.5, 1, 1])


def test_generator_shape_and_determinism(hw, sim):
    X = frames_to_array(sim.frames)
    assert X.shape == (1440, len(CHANNELS))
    again = generate_telemetry(hw, 550.0, 53.0, "2026-03-01T00:00:00Z", seed=7)
    np.testing.assert_array_equal(X, frames_to_array(again.frames))
    other = generate_telemetry(hw, 550.0, 53.0, "2026-03-01T00:00:00Z", seed=8)
    assert not np.array_equal(X, frames_to_array(other.frames))


def test_eclipse_drives_solar_battery_temperature(hw, sim):
    X = frames_to_array(sim.frames)
    solar, battery, temp = X[:, 0], X[:, 1], X[:, 2]
    dark = sim.illumination == 0
    assert 0.2 < dark.mean() < 0.5                     # LEO: ~35% in shadow
    assert solar[dark].max() < 1.0                     # noise only in umbra
    assert solar[~dark].mean() > 15.0
    # battery charges in sunlight and drains in shadow, within capacity
    d_batt = np.diff(battery)
    assert d_batt[dark[:-1]].mean() < 0 < d_batt[~dark[:-1]].mean()
    assert battery.max() < hw.power.battery_capacity_wh + 0.2
    # spacecraft cools in shadow
    assert np.diff(temp)[dark[:-1]].mean() < 0


# ── faults ───────────────────────────────────────────────────

def test_catalogue_faults_follow_core_interface():
    for name in FAULTS:
        f = build_fault(name, 0.5, t_start=600.0, duration_s=600.0)
        assert isinstance(f, FaultScenario)
        assert f.is_active(600.0) and f.is_active(1200.0) and not f.is_active(1260.0)


def test_build_fault_validation():
    with pytest.raises(ValueError, match="unknown"):
        build_fault("gps_dropout", 0.5, 0.0, 60.0)
    with pytest.raises(ValueError, match="severity"):
        build_fault("sensor_drift", 1.5, 0.0, 60.0)


@pytest.mark.parametrize("name", ["power_brownout", "sensor_noise",
                                  "eclipse_power_stress", "sensor_drift"])
def test_zero_severity_changes_nothing(name):
    f = build_fault(name, 0.0, t_start=0.0, duration_s=600.0)
    frame = make_frame(t=60.0, temperature_c=20.0)
    out = f.inject(frame)
    for ch in CHANNELS:
        assert getattr(out, ch) == pytest.approx(getattr(frame, ch))


def test_sensor_drift_is_linear():
    f = SensorDrift(t_start=0.0, duration_s=100.0, channel="temperature_c", total_drift=10.0)
    assert f.inject(make_frame(t=0.0, temperature_c=20.0)).temperature_c == 20.0
    assert f.inject(make_frame(t=50.0, temperature_c=20.0)).temperature_c == 25.0
    assert f.inject(make_frame(t=100.0, temperature_c=20.0)).temperature_c == 30.0
    assert f.inject(make_frame(t=150.0, temperature_c=20.0)).temperature_c == 20.0
    zero = SensorDrift(t_start=0.0, duration_s=0.0, total_drift=3.0)
    assert zero.inject(make_frame(t=0.0, temperature_c=0.0)).temperature_c == 3.0


def test_stuck_sensor_holds_first_faulty_value():
    f = StuckSensor(t_start=60.0, duration_s=120.0, channel="solar_power_w")
    assert f.inject(make_frame(t=0.0, solar_power_w=1.0)).solar_power_w == 1.0
    assert f.inject(make_frame(t=60.0, solar_power_w=7.0)).solar_power_w == 7.0
    assert f.inject(make_frame(t=120.0, solar_power_w=9.0)).solar_power_w == 7.0
    assert f.inject(make_frame(t=240.0, solar_power_w=9.0)).solar_power_w == 9.0


# ── missions and onset labels ────────────────────────────────

def test_clean_mission_has_no_labels(hw):
    m = make_mission(hw, seed=3)
    assert m.data.shape == (1440, len(CHANNELS))
    assert not m.labels.any() and m.events == []


@pytest.mark.parametrize("fault", list(FAULTS))
def test_onset_labels_match_injected_steps(hw, fault):
    seed = SPLIT_SEED_BASE["dev"] + 4
    clean = make_mission(hw, seed)
    m = make_mission(hw, seed, fault=fault, severity=1.0)
    # exactly one event of FAULT_STEPS steps, after warm-up + margin
    assert len(m.events) == 1
    start, end = m.events[0]
    assert end - start + 1 == FAULT_STEPS == m.labels.sum()
    assert start >= EVAL_WARMUP + 60
    # the faulted data differs from the clean mission ONLY inside the
    # labeled window
    changed = np.any(m.data != clean.data, axis=1)
    assert not changed[~m.labels].any()
    # stuck holds the (unchanged) first value; drift starts at offset 0
    if fault not in ("stuck_sensor", "sensor_drift"):
        assert changed[start]            # the label starts where the data changes
    else:
        assert changed[start + 1]
    assert changed[m.labels].mean() > 0.9


def test_eclipse_power_stress_is_placed_in_sunlight(hw):
    for i in range(5):
        m = make_mission(hw, SPLIT_SEED_BASE["dev"] + i, "eclipse_power_stress", 0.5)
        assert np.all(m.illumination[m.labels] == 1.0)


def test_paired_design_shares_onset_across_faults(hw):
    seed = SPLIT_SEED_BASE["dev"] + 2
    a = make_mission(hw, seed, "sensor_drift", 0.2)
    b = make_mission(hw, seed, "power_brownout", 0.9)
    assert a.events == b.events


def test_split_seed_ranges_disjoint():
    bases = sorted(SPLIT_SEED_BASE.values())
    assert all(b - a >= 100_000 for a, b in zip(bases, bases[1:]))


def test_test_orbits_are_held_out():
    assert len(ORBIT_POOL) == 6 and len(TEST_ORBITS) == 2
    assert not set(ORBIT_POOL) & set(TEST_ORBITS)


@pytest.mark.parametrize("split", ["train", "val", "dev", "test"])
def test_each_split_flies_only_its_own_orbits(hw, split):
    allowed = TEST_ORBITS if split == "test" else ORBIT_POOL
    seen = {make_mission(hw, mission_seed(split, i)).orbit for i in range(25)}
    assert seen <= set(allowed)
    assert len(seen) > 1                       # really samples the pool


# ── scoring and the detectability map ────────────────────────

def test_mission_scores_shape_and_warmup(hw):
    m = make_mission(hw, seed=5)
    s = mission_scores(PersistenceBaseline(), m.data)
    assert s.shape == (1440,)
    assert np.all(np.isnan(s[:EVAL_WARMUP])) and np.all(np.isfinite(s[EVAL_WARMUP:]))


def test_grace_period_blames_recovery_alarm_on_event():
    s = np.zeros(30)
    s[[10, 21]] = 1.0                          # alarm in event, then at recovery
    no_grace = count_channel(s, 0.5, [(8, 15)], grace=0)
    graced = count_channel(s, 0.5, [(8, 15)], grace=10)
    assert no_grace.n_false_alarms == 1 and graced.n_false_alarms == 0
    assert graced.n_detected == 1 and graced.n_normal_steps == 30 - 8 - 10


def test_detectability_map_small_grid(hw):
    cal, cells = detectability_map(
        PersistenceBaseline(), hw, n_reps=3, n_val=3,
        faults=("power_brownout", "stuck_sensor"), severities=(0.05, 1.0))
    assert cal.false_alarms_per_10k <= 2.0
    assert [(c.fault, c.severity) for c in cells] == [
        ("power_brownout", 0.05), ("power_brownout", 1.0),
        ("stuck_sensor", 0.05), ("stuck_sensor", 1.0)]
    recall = {(c.fault, c.severity): c.metrics.event_recall for c in cells}
    assert recall[("power_brownout", 1.0)] == 1.0      # big step: always caught
    assert all(c.metrics.n_events == 3 for c in cells)
    with pytest.raises(ValueError):
        detectability_map(PersistenceBaseline(), hw, split="train")


def test_run_detectability_cli(tmp_path, capsys):
    from orbitval.ml import run_detectability
    out = tmp_path / "map.json"
    result = run_detectability.main(["--config", SATELLITE_YAML, "--reps", "1",
                                     "--val", "2", "--out", str(out)])
    assert len(result["cells"]) == len(FAULTS) * 7
    assert out.exists() and "event recall" in capsys.readouterr().out
    assert not math.isnan(result["calibration"]["threshold"])


def test_plot_detectability(tmp_path):
    pytest.importorskip("matplotlib")
    from orbitval.ml.plots import plot_detectability
    cells = [{"fault": f, "severity": s, "metrics": {"event_recall": s}}
             for f in ("a", "b") for s in (0.1, 1.0)]
    path = tmp_path / "map.png"
    plot_detectability({"detector": "x", "split": "dev", "reps": 1, "cells": cells}, path)
    assert path.stat().st_size > 1000
