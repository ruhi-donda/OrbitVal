"""
tests/test_bug2_injection_trace.py

Bug 2: runner.run() hardcoded injection_trace=[] when calling
generate_json_report, even though real fault events existed in each
scenario's fault_trace. The ORF JSON always had an empty injection_trace
and the PDF always showed "0 injection events recorded."

Fix: runner.run() now builds injection_trace by flattening all per-scenario
fault_trace lists and passes the real events to generate_json_report.
"""

import sys
import pytest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from orbitval.engine.runner import TestRunner


SATELLITE_YAML = str(Path(__file__).parent.parent / "satellite.yaml")

TLE_LINE1 = "1 25544U 98067A   24010.50000000  .00016717  00000-0  10270-3 0  9007"
TLE_LINE2 = "2 25544  51.6400 208.9163 0006317  69.9862  25.2906 15.49815747 33333"


class _NoopAutonomy:
    def process(self, telemetry):
        return "nominal"

    def reset(self):
        pass


def _make_runner():
    return TestRunner(
        config=SATELLITE_YAML,
        autonomy=_NoopAutonomy(),
        tle_line1=TLE_LINE1,
        tle_line2=TLE_LINE2,
        duration_hours=0.1,
        step_seconds=60.0,
        seed=42,
    )


MISSION_PROFILE = {
    "orbit_type": "LEO",
    "altitude_band_km": None,
    "inclination_deg": None,
    "operational_lifetime_years": None,
}


class TestInjectionTrace:
    def test_injection_trace_not_empty_after_run(self, tmp_path):
        """injection_trace in the JSON report must contain events when faults fired."""
        runner = _make_runner()
        report = runner.run(
            scenarios=["gps_dropout"],
            output_dir=str(tmp_path),
            mission_profile=MISSION_PROFILE,
        )
        assert len(report["injection_trace"]) > 0, (
            "injection_trace was empty — Bug 2 regression: "
            "fault events fired but weren't wired into the report"
        )

    def test_injection_trace_event_shape(self, tmp_path):
        """Each injection_trace event must have t, fault_name, fields_modified."""
        runner = _make_runner()
        report = runner.run(
            scenarios=["gps_dropout"],
            output_dir=str(tmp_path),
            mission_profile=MISSION_PROFILE,
        )
        for event in report["injection_trace"]:
            assert "t" in event, f"missing 't' in event: {event}"
            assert "fault_name" in event, f"missing 'fault_name' in event: {event}"
            assert "fields_modified" in event, f"missing 'fields_modified' in event: {event}"

    def test_injection_trace_aggregates_all_scenarios(self, tmp_path):
        """injection_trace must be the union of all per-scenario fault_trace lists."""
        runner = _make_runner()
        report = runner.run(
            scenarios=["gps_dropout", "power_brownout", "sensor_noise"],
            output_dir=str(tmp_path),
            mission_profile=MISSION_PROFILE,
        )
        expected_total = sum(
            len(sc["fault_trace"]) for sc in report["scenarios_run"]
        )
        assert len(report["injection_trace"]) == expected_total, (
            f"injection_trace has {len(report['injection_trace'])} events "
            f"but scenarios_run fault_traces total {expected_total}"
        )

    def test_injection_trace_fault_names_match_scenarios(self, tmp_path):
        """Each event's fault_name must correspond to a scenario that was run."""
        runner = _make_runner()
        report = runner.run(
            scenarios=["gps_dropout", "power_brownout"],
            output_dir=str(tmp_path),
            mission_profile=MISSION_PROFILE,
        )
        run_names = {sc["name"] for sc in report["scenarios_run"]}
        for event in report["injection_trace"]:
            assert event["fault_name"] in run_names, (
                f"injection_trace event has fault_name '{event['fault_name']}' "
                f"which is not in scenarios_run: {run_names}"
            )

    def test_integrity_hash_still_valid_after_fix(self, tmp_path):
        """test_integrity_hash must still be present and non-empty after the fix."""
        runner = _make_runner()
        report = runner.run(
            scenarios=["gps_dropout"],
            output_dir=str(tmp_path),
            mission_profile=MISSION_PROFILE,
        )
        assert "test_integrity_hash" in report
        assert len(report["test_integrity_hash"]) == 64  # SHA-256 hex = 64 chars
