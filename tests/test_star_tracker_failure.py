"""
tests/test_star_tracker_failure.py

Star tracker failure fault scenario — failed and degraded modes,
quaternion corruption, and the silent-trust failure detection that
is the whole point of this scenario.
"""

import math
import pytest

from orbitval.faults.scenarios.star_tracker_failure import StarTrackerFailure
from orbitval.faults.catalog import get_fault
from tests.conftest import (
    make_frame, SATELLITE_YAML,
    SilentlyTrustingAutonomy, ResponsiveAutonomy,
)


class TestFailedMode:
    def test_tracker_goes_offline(self):
        fault = StarTrackerFailure(t_start=180, duration_s=300, mode="failed")
        injected = fault.inject(make_frame(t=200))
        assert injected.star_tracker_available is False

    def test_null_quaternion(self):
        """Failed mode feeds the null quaternion — zero norm, invalid."""
        fault = StarTrackerFailure(t_start=180, duration_s=300, mode="failed")
        injected = fault.inject(make_frame(t=200))
        norm = math.sqrt(
            injected.attitude_qw ** 2 + injected.attitude_qx ** 2 +
            injected.attitude_qy ** 2 + injected.attitude_qz ** 2
        )
        assert norm == 0.0

    def test_attitude_flagged_invalid(self):
        fault = StarTrackerFailure(t_start=180, duration_s=300, mode="failed")
        injected = fault.inject(make_frame(t=200))
        assert injected.attitude_valid is False


class TestDegradedMode:
    def test_tracker_still_reports_available(self):
        """The dangerous case: tracker looks up, data is garbage."""
        fault = StarTrackerFailure(t_start=180, duration_s=300, mode="degraded")
        injected = fault.inject(make_frame(t=200))
        assert injected.star_tracker_available is True

    def test_quaternion_corrupted(self):
        fault = StarTrackerFailure(t_start=180, duration_s=300,
                                   mode="degraded", seed=42)
        injected = fault.inject(make_frame(t=200))
        original = (1.0, 0.0, 0.0, 0.0)
        corrupted = (injected.attitude_qw, injected.attitude_qx,
                     injected.attitude_qy, injected.attitude_qz)
        assert corrupted != original

    def test_quaternion_not_normalized(self):
        """Corrupted quaternion should no longer have unit norm."""
        fault = StarTrackerFailure(t_start=180, duration_s=300,
                                   mode="degraded", seed=42)
        injected = fault.inject(make_frame(t=200))
        norm = math.sqrt(
            injected.attitude_qw ** 2 + injected.attitude_qx ** 2 +
            injected.attitude_qy ** 2 + injected.attitude_qz ** 2
        )
        assert abs(norm - 1.0) > 1e-6

    def test_attitude_flagged_invalid(self):
        fault = StarTrackerFailure(t_start=180, duration_s=300, mode="degraded")
        injected = fault.inject(make_frame(t=200))
        assert injected.attitude_valid is False

    def test_seeded_corruption_is_reproducible(self):
        f1 = StarTrackerFailure(mode="degraded", seed=7)
        f2 = StarTrackerFailure(mode="degraded", seed=7)
        i1 = f1.inject(make_frame(t=200))
        i2 = f2.inject(make_frame(t=200))
        assert i1.attitude_qw == i2.attitude_qw
        assert i1.attitude_qx == i2.attitude_qx


class TestEdgeCases:
    def test_invalid_mode_raises(self):
        with pytest.raises(ValueError, match="mode"):
            StarTrackerFailure(mode="exploded")

    def test_inactive_outside_window(self):
        fault = StarTrackerFailure(t_start=180, duration_s=300)
        frame = make_frame(t=50)
        assert fault.inject(frame) is frame

    def test_input_frame_not_mutated(self):
        fault = StarTrackerFailure(t_start=180, duration_s=300, mode="failed")
        frame = make_frame(t=200)
        fault.inject(frame)
        assert frame.star_tracker_available is True
        assert frame.attitude_qw == 1.0

    def test_flag_set(self):
        fault = StarTrackerFailure(t_start=180, duration_s=300)
        injected = fault.inject(make_frame(t=200))
        assert injected.flags.get("star_tracker_failure") is True

    def test_registered_in_catalog(self):
        fault = get_fault("star_tracker_failure")
        assert fault.name == "star_tracker_failure"


class TestSilentTrustDetection:
    """The core purpose: autonomy that silently trusts bad attitude
    data must FAIL; autonomy that flags degraded confidence PASSes."""

    def test_silently_trusting_autonomy_fails(self, tmp_path):
        from orbitval.engine.runner import TestRunner
        runner = TestRunner(
            config=SATELLITE_YAML, autonomy=SilentlyTrustingAutonomy(),
            orbit_alt_km=550.0, orbit_inc_deg=53.0,
        )
        report = runner.run(scenarios=["star_tracker_failure"],
                            output_dir=str(tmp_path))
        result = report["scenarios_run"][0]
        assert result["result"] == "FAIL"
        assert "nominal" in result["failure_reason"]

    def test_confidence_flagging_autonomy_passes(self, prelaunch_runner, tmp_path):
        report = prelaunch_runner.run(scenarios=["star_tracker_failure"],
                                      output_dir=str(tmp_path))
        result = report["scenarios_run"][0]
        assert result["result"] == "PASS"
        assert result["autonomy_response"] == "failover"

    def test_degraded_mode_also_caught(self, tmp_path):
        """Even when the tracker reports available, attitude_valid=False
        must be enough for a confidence-checking autonomy to PASS."""
        from orbitval.engine.runner import TestRunner
        runner = TestRunner(
            config=SATELLITE_YAML, autonomy=ResponsiveAutonomy(),
            orbit_alt_km=550.0, orbit_inc_deg=53.0,
        )
        report = runner.run(
            scenarios=["star_tracker_failure"],
            scenario_kwargs={"star_tracker_failure": {"mode": "degraded"}},
            output_dir=str(tmp_path),
        )
        assert report["scenarios_run"][0]["result"] == "PASS"

    def test_report_round_trips_verify(self, prelaunch_runner, tmp_path):
        import argparse
        from orbitval.cli import cmd_verify_report
        prelaunch_runner.run(scenarios=["star_tracker_failure"],
                             output_dir=str(tmp_path))
        report_file = next(tmp_path.glob("*.json"))
        cmd_verify_report(argparse.Namespace(report=str(report_file)))
