"""
tests/test_reproducibility.py

Determinism and per-run bookkeeping (Q2, Q3, Q5).

Q2 — pre-launch runs were not reproducible. propagate_from_params fell
back to the wall clock when no epoch was given, so the same seed on a
different day produced different solar geometry, different
eclipse_periods, and therefore a different eclipse_power_stress window.
Confirmed before the fix: seed 42 at 550km/53deg gave umbra 1800-3540s
on 2026-03-20 and 3300-3540s on 2026-06-21.

Q3 — per-scenario duration_s multiplied the active-frame count by a
hardcoded 60.0 regardless of --step.

Q5 — caller scenario_kwargs replaced the harness defaults wholesale,
silently dropping the injected seed and the real eclipse windows.
"""

import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from astropy.time import Time

sys.path.insert(0, str(Path(__file__).parent.parent))

from orbitval.engine.runner import TestRunner
from orbitval.orbits.propagation import propagate_from_params
from tests.conftest import SATELLITE_YAML, ResponsiveAutonomy

EPOCH = "2026-09-08T00:00:00"


def _runner(**kwargs):
    defaults = dict(
        config=SATELLITE_YAML,
        autonomy=ResponsiveAutonomy(),
        orbit_alt_km=550.0,
        orbit_inc_deg=53.0,
        epoch=EPOCH,
    )
    defaults.update(kwargs)
    return TestRunner(**defaults)


class TestEpochReproducibility:
    def test_same_epoch_gives_identical_eclipse_periods(self):
        a = propagate_from_params(550, 53.0, 1.0, 60.0, epoch=EPOCH)
        b = propagate_from_params(550, 53.0, 1.0, 60.0, epoch=EPOCH)
        assert a.eclipse_periods == b.eclipse_periods
        assert a.epoch == b.epoch

    def test_different_epoch_gives_different_geometry(self):
        """Sanity check on the other side: the epoch genuinely drives the
        shadow geometry, which is why leaving it to the clock was a bug."""
        a = propagate_from_params(550, 53.0, 1.0, 60.0,
                                  epoch="2026-03-20T12:00:00")
        b = propagate_from_params(550, 53.0, 1.0, 60.0,
                                  epoch="2026-06-21T12:00:00")
        assert a.eclipse_periods != b.eclipse_periods

    def test_wall_clock_drift_is_pinned_by_explicit_epoch(self, tmp_path):
        """With an explicit epoch, faking the clock changes nothing."""
        def run_at(fake_now):
            with patch("orbitval.orbits.propagation.AstropyTime.now",
                       staticmethod(lambda: Time(fake_now))):
                r = _runner()
            return r.run(scenarios=["eclipse_power_stress"],
                         output_dir=tmp_path / fake_now[:10])

        march = run_at("2026-03-20T12:00:00")
        june = run_at("2026-06-21T12:00:00")
        assert march["eclipse_periods"] == june["eclipse_periods"]
        assert march["injection_trace"] == june["injection_trace"]
        assert march["scenarios_run"] == june["scenarios_run"]

    def test_no_epoch_still_works_and_warns(self, tmp_path, caplog):
        """Omitting the epoch stays legal — it just isn't reproducible,
        and the run log has to say so."""
        r = _runner(epoch=None)
        report = r.run(scenarios=["gps_dropout"], output_dir=tmp_path)
        assert report["simulation"]["epoch_source"] == "wall_clock"
        assert any("not" in e["msg"] or "reproducible" in e["msg"]
                   for e in report["run_log"] if e["level"] == "WARNING")

    def test_epoch_source_recorded_for_explicit_epoch(self, tmp_path):
        report = _runner().run(scenarios=["gps_dropout"], output_dir=tmp_path)
        assert report["simulation"]["epoch_source"] == "provided"

    def test_epoch_source_recorded_for_tle_mode(self, tmp_path):
        from tests.conftest import TLE1, TLE2
        with patch("orbitval.engine.runner.fetch_tle"):
            r = TestRunner(config=SATELLITE_YAML, autonomy=ResponsiveAutonomy(),
                           tle_line1=TLE1, tle_line2=TLE2)
        report = r.run(scenarios=["gps_dropout"], output_dir=tmp_path)
        assert report["simulation"]["epoch_source"] == "tle"

    def test_epoch_appears_in_orbit_epoch(self):
        r = _runner()
        assert r.orbit.epoch.startswith("2026-09-08")


class TestScenarioDuration:
    def test_duration_scales_with_step_seconds(self, tmp_path):
        """A fault active over the same wall-clock window must report the
        same duration_s regardless of the telemetry step."""
        coarse = _runner(step_seconds=60.0).run(
            scenarios=["gps_dropout"], output_dir=tmp_path / "coarse")
        fine = _runner(step_seconds=30.0).run(
            scenarios=["gps_dropout"], output_dir=tmp_path / "fine")

        d_coarse = coarse["scenarios_run"][0]["duration_s"]
        d_fine = fine["scenarios_run"][0]["duration_s"]
        # gps_dropout defaults to a 120s window; both runs should agree
        # to within one step of each other.
        assert abs(d_coarse - d_fine) <= 60.0, (
            f"coarse={d_coarse}s fine={d_fine}s — duration_s is not "
            f"honouring step_seconds"
        )

    def test_duration_is_not_hardcoded_to_sixty(self, tmp_path):
        report = _runner(step_seconds=30.0).run(
            scenarios=["gps_dropout"], output_dir=tmp_path)
        result = report["scenarios_run"][0]
        n_active = sum(
            1 for e in report["injection_trace"]
            if e["fault_name"] == "gps_dropout"
        )
        assert result["duration_s"] == pytest.approx(n_active * 30.0, abs=30.0)

    def test_duration_matches_frame_count_times_step(self, tmp_path):
        step = 15.0
        report = _runner(step_seconds=step).run(
            scenarios=["comms_blackout"], output_dir=tmp_path)
        result = report["scenarios_run"][0]
        assert result["duration_s"] % step == 0


class TestScenarioKwargsMerge:
    def test_partial_override_keeps_real_eclipse_windows(self, tmp_path):
        """Overriding one parameter must not discard the harness-supplied
        eclipse windows — that silently moved the fault to the fallback
        window and tested the wrong thing."""
        r = _runner(duration_hours=3.0)
        assert r.orbit.eclipse_periods, "need real eclipses for this test"
        report = r.run(
            scenarios=["eclipse_power_stress"],
            scenario_kwargs={"eclipse_power_stress": {"battery_factor": 0.5}},
            output_dir=tmp_path,
        )
        fired = sorted(
            e["t"] for e in report["injection_trace"]
            if e["fault_name"] == "eclipse_power_stress"
        )
        assert fired, "fault never fired"
        windows = [(p["start_t"], p["end_t"]) for p in r.orbit.eclipse_periods]
        for t in fired:
            assert any(s <= t <= e for s, e in windows), (
                f"injection at t={t} is outside every real eclipse window "
                f"{windows} — the override dropped eclipse_windows"
            )

    def test_partial_override_keeps_injected_seed(self, tmp_path):
        """sensor_noise takes a seed from the harness; overriding only the
        window must not reset it to the class default."""
        r = _runner(seed=1234)
        report = r.run(
            scenarios=["sensor_noise"],
            scenario_kwargs={"sensor_noise": {"duration_s": 600.0}},
            output_dir=tmp_path,
        )
        assert report["scenarios_run"][0]["seed"] == 1234

    def test_explicit_override_still_wins(self, tmp_path):
        r = _runner()
        report = r.run(
            scenarios=["gps_dropout"],
            scenario_kwargs={"gps_dropout": {"t_start": 0.0,
                                             "duration_s": 60.0}},
            output_dir=tmp_path,
        )
        fired = [e["t"] for e in report["injection_trace"]
                 if e["fault_name"] == "gps_dropout"]
        assert fired and max(fired) <= 60.0
