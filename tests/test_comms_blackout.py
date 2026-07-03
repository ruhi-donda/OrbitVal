"""
tests/test_comms_blackout.py

Communication blackout fault scenario — contact loss, autonomous
behavior during the gap, and recovery detection on reacquisition.
"""

import pytest

from orbitval.faults.scenarios.comms_blackout import CommsBlackout
from orbitval.faults.catalog import get_fault
from orbitval.engine.injection import run_injection
from tests.conftest import (
    make_frame, SATELLITE_YAML,
    SilentlyTrustingAutonomy, ResponsiveAutonomy,
)


class TestInjection:
    def test_ground_contact_lost_in_window(self):
        fault = CommsBlackout(t_start=300, duration_s=900)
        injected = fault.inject(make_frame(t=600))
        assert injected.ground_contact is False

    def test_contact_intact_outside_window(self):
        fault = CommsBlackout(t_start=300, duration_s=900)
        frame = make_frame(t=100)
        assert fault.inject(frame) is frame
        assert frame.ground_contact is True

    def test_input_frame_not_mutated(self):
        fault = CommsBlackout(t_start=300, duration_s=900)
        frame = make_frame(t=600)
        fault.inject(frame)
        assert frame.ground_contact is True

    def test_flag_set(self):
        fault = CommsBlackout(t_start=300, duration_s=900)
        injected = fault.inject(make_frame(t=600))
        assert injected.flags.get("comms_blackout_fault") is True

    def test_window_boundaries_inclusive(self):
        fault = CommsBlackout(t_start=300, duration_s=900)
        assert fault.is_active(300)
        assert fault.is_active(1200)
        assert not fault.is_active(299)
        assert not fault.is_active(1201)

    def test_registered_in_catalog(self):
        fault = get_fault("comms_blackout")
        assert fault.name == "comms_blackout"


class TestBlackoutAndRecovery:
    def test_gap_visible_in_injection_trace(self):
        """The report's injection trace must show the contact gap."""
        stream = [make_frame(t=float(i * 60)) for i in range(20)]
        fault = CommsBlackout(t_start=300, duration_s=300)
        injected, trace = run_injection(stream, [fault])
        assert len(trace) > 0
        assert all(e.fault_name == "comms_blackout" for e in trace)
        assert all("ground_contact" in e.fields_modified for e in trace)

    def test_recovery_after_window(self):
        """Contact returns True on frames after the blackout ends."""
        stream = [make_frame(t=float(i * 60)) for i in range(20)]
        fault = CommsBlackout(t_start=300, duration_s=300)
        injected, _ = run_injection(stream, [fault])
        during = [f for f in injected if 300 <= f.t <= 600]
        after = [f for f in injected if f.t > 600]
        assert all(not f.ground_contact for f in during)
        assert all(f.ground_contact for f in after)

    def test_autonomy_sees_recovery(self):
        """A responsive autonomy returns to nominal after reacquisition."""
        autonomy = ResponsiveAutonomy()
        stream = [make_frame(t=float(i * 60)) for i in range(20)]
        fault = CommsBlackout(t_start=300, duration_s=300)
        injected, _ = run_injection(stream, [fault])
        responses = [autonomy.process(f) for f in injected]
        # During blackout: reduced_ops; after: nominal again
        t_index = {f.t: i for i, f in enumerate(injected)}
        assert responses[t_index[420.0]] == "reduced_ops"
        assert responses[t_index[720.0]] == "nominal"


class TestEvaluation:
    def test_responsive_autonomy_passes(self, prelaunch_runner, tmp_path):
        report = prelaunch_runner.run(scenarios=["comms_blackout"],
                                      output_dir=str(tmp_path))
        assert report["scenarios_run"][0]["result"] == "PASS"

    def test_silently_trusting_autonomy_fails(self, tmp_path):
        from orbitval.engine.runner import TestRunner
        runner = TestRunner(
            config=SATELLITE_YAML, autonomy=SilentlyTrustingAutonomy(),
            orbit_alt_km=550.0, orbit_inc_deg=53.0,
        )
        report = runner.run(scenarios=["comms_blackout"],
                            output_dir=str(tmp_path))
        assert report["scenarios_run"][0]["result"] == "FAIL"

    def test_report_round_trips_verify(self, prelaunch_runner, tmp_path):
        import argparse
        from orbitval.cli import cmd_verify_report
        prelaunch_runner.run(scenarios=["comms_blackout"],
                             output_dir=str(tmp_path))
        report_file = next(tmp_path.glob("*.json"))
        cmd_verify_report(argparse.Namespace(report=str(report_file)))
