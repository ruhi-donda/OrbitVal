"""
tests/test_eclipse_power_stress.py

Eclipse power/thermal stress fault scenario — injection behavior,
real-eclipse-window activation, and pass/fail evaluation.
"""

import pytest

from orbitval.faults.scenarios.eclipse_power_stress import EclipsePowerStress
from orbitval.faults.catalog import get_fault
from tests.conftest import (
    make_frame, SATELLITE_YAML,
    SilentlyTrustingAutonomy, ResponsiveAutonomy,
)


class TestInjection:
    def test_solar_power_collapses_in_shadow(self):
        fault = EclipsePowerStress(t_start=100, duration_s=200)
        injected = fault.inject(make_frame(t=150))
        assert injected.solar_power_w == 0.0

    def test_battery_degrades_in_shadow(self):
        fault = EclipsePowerStress(t_start=100, duration_s=200)
        injected = fault.inject(make_frame(t=150))
        assert injected.battery_charge_wh == pytest.approx(20.0 * 0.8)

    def test_temperature_drops_in_shadow(self):
        fault = EclipsePowerStress(t_start=100, duration_s=200)
        injected = fault.inject(make_frame(t=150))
        assert injected.temperature_c == pytest.approx(20.0 - 35.0)

    def test_inactive_outside_window(self):
        fault = EclipsePowerStress(t_start=100, duration_s=200)
        frame = make_frame(t=50)
        assert fault.inject(frame) is frame  # untouched

    def test_input_frame_not_mutated(self):
        fault = EclipsePowerStress(t_start=100, duration_s=200)
        frame = make_frame(t=150)
        fault.inject(frame)
        assert frame.solar_power_w == 5.0  # original unchanged

    def test_flag_set(self):
        fault = EclipsePowerStress(t_start=100, duration_s=200)
        injected = fault.inject(make_frame(t=150))
        assert injected.flags.get("eclipse_power_stress") is True


class TestEclipseWindowActivation:
    def test_real_windows_take_precedence(self):
        """When eclipse_windows are provided, the fallback window is ignored."""
        fault = EclipsePowerStress(
            t_start=0, duration_s=10_000,           # fallback: everything
            eclipse_windows=[(500.0, 700.0)],        # real: narrow
        )
        assert fault.is_active(600)
        assert not fault.is_active(100)
        assert not fault.is_active(9000)

    def test_multiple_windows(self):
        fault = EclipsePowerStress(
            eclipse_windows=[(100.0, 200.0), (5000.0, 5500.0)],
        )
        assert fault.is_active(150)
        assert fault.is_active(5200)
        assert not fault.is_active(1000)

    def test_fallback_window_without_eclipse_data(self):
        fault = EclipsePowerStress(t_start=100, duration_s=200)
        assert fault.is_active(200)
        assert not fault.is_active(500)

    def test_registered_in_catalog(self):
        fault = get_fault("eclipse_power_stress")
        assert fault.name == "eclipse_power_stress"


class TestEvaluation:
    def test_responsive_autonomy_passes(self, tmp_path):
        from orbitval.engine.runner import TestRunner
        runner = TestRunner(
            config=SATELLITE_YAML, autonomy=ResponsiveAutonomy(),
            orbit_alt_km=550.0, orbit_inc_deg=53.0,
        )
        report = runner.run(scenarios=["eclipse_power_stress"],
                            output_dir=str(tmp_path))
        result = report["scenarios_run"][0]["result"]
        assert result in ("PASS", "SKIP")  # SKIP only if orbit never in shadow

    def test_silently_trusting_autonomy_fails(self, tmp_path):
        from orbitval.engine.runner import TestRunner
        runner = TestRunner(
            config=SATELLITE_YAML, autonomy=SilentlyTrustingAutonomy(),
            orbit_alt_km=550.0, orbit_inc_deg=53.0,
        )
        report = runner.run(scenarios=["eclipse_power_stress"],
                            output_dir=str(tmp_path))
        result = report["scenarios_run"][0]["result"]
        assert result in ("FAIL", "SKIP")

    def test_report_round_trips_verify(self, prelaunch_runner, tmp_path):
        import argparse
        from orbitval.cli import cmd_verify_report
        prelaunch_runner.run(scenarios=["eclipse_power_stress"],
                             output_dir=str(tmp_path))
        report_file = next(tmp_path.glob("*.json"))
        cmd_verify_report(argparse.Namespace(report=str(report_file)))
