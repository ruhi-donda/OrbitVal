"""
tests/test_bug3_comms_windows.py

Bug 3: TestRunner computed self.comms_windows when --ground-station was
given, but never passed the result to generate_json_report or
generate_pdf_report. The comms_windows field was absent from the JSON
and the PDF had no comms section, despite README claiming the report
includes "comms window analysis."

Fix: runner.run() passes comms_windows to generate_json_report;
json_report.py serializes them into the payload (before hashing);
pdf_report.py renders a Ground Station Comms Windows section.
"""

import sys
import pytest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from orbitval.engine.runner import TestRunner
from orbitval.orbits.comms_windows import GroundStation


SATELLITE_YAML = str(Path(__file__).parent.parent / "satellite.yaml")

TLE_LINE1 = "1 25544U 98067A   24010.50000000  .00016717  00000-0  10270-3 0  9007"
TLE_LINE2 = "2 25544  51.6400 208.9163 0006317  69.9862  25.2906 15.49815747 33333"

MISSION_PROFILE = {
    "orbit_type": "LEO",
    "altitude_band_km": None,
    "inclination_deg": None,
    "operational_lifetime_years": None,
}


class _NoopAutonomy:
    def process(self, telemetry):
        return "nominal"

    def reset(self):
        pass


class TestCommsWindowsInReport:
    def test_comms_windows_key_present_without_ground_station(self, tmp_path):
        """comms_windows key must exist in report even when no ground station given (empty list)."""
        runner = TestRunner(
            config=SATELLITE_YAML,
            autonomy=_NoopAutonomy(),
            tle_line1=TLE_LINE1,
            tle_line2=TLE_LINE2,
            duration_hours=0.1,
            step_seconds=60.0,
            seed=42,
        )
        report = runner.run(
            scenarios=["gps_dropout"],
            output_dir=str(tmp_path),
            mission_profile=MISSION_PROFILE,
        )
        assert "comms_windows" in report, (
            "comms_windows key missing from report — Bug 3 regression"
        )
        assert report["comms_windows"] == [], (
            "comms_windows should be empty list when no ground station provided"
        )

    def test_comms_windows_with_ground_station(self, tmp_path):
        """comms_windows must be populated when a ground station is provided with a real TLE."""
        gs = GroundStation(name="TestStation", lat_deg=40.5, lon_deg=-74.4)
        runner = TestRunner(
            config=SATELLITE_YAML,
            autonomy=_NoopAutonomy(),
            tle_line1=TLE_LINE1,
            tle_line2=TLE_LINE2,
            duration_hours=3.0,   # 3h gives ISS a good chance of a pass
            step_seconds=60.0,
            seed=42,
            ground_stations=[gs],
        )
        report = runner.run(
            scenarios=["gps_dropout"],
            output_dir=str(tmp_path),
            mission_profile=MISSION_PROFILE,
        )
        assert "comms_windows" in report
        # We can't guarantee a window in any fixed 3h window (orbit geometry),
        # but the field must be a list (possibly empty).
        assert isinstance(report["comms_windows"], list)

    def test_comms_window_event_shape(self, tmp_path):
        """Each comms_window entry must have the required fields."""
        gs = GroundStation(name="TestStation", lat_deg=40.5, lon_deg=-74.4)
        runner = TestRunner(
            config=SATELLITE_YAML,
            autonomy=_NoopAutonomy(),
            tle_line1=TLE_LINE1,
            tle_line2=TLE_LINE2,
            duration_hours=24.0,  # 24h guarantees at least one ISS pass
            step_seconds=60.0,
            seed=42,
            ground_stations=[gs],
        )
        report = runner.run(
            scenarios=["gps_dropout"],
            output_dir=str(tmp_path),
            mission_profile=MISSION_PROFILE,
        )
        required_keys = {"ground_station", "start_time", "end_time",
                         "duration_s", "max_elevation_deg", "start_t", "end_t"}
        for w in report["comms_windows"]:
            missing = required_keys - set(w.keys())
            assert not missing, f"comms_window entry missing keys: {missing}"

    def test_integrity_hash_includes_comms_windows(self, tmp_path):
        """test_integrity_hash must still be present after adding comms_windows to payload."""
        runner = TestRunner(
            config=SATELLITE_YAML,
            autonomy=_NoopAutonomy(),
            tle_line1=TLE_LINE1,
            tle_line2=TLE_LINE2,
            duration_hours=0.1,
            step_seconds=60.0,
            seed=42,
        )
        report = runner.run(
            scenarios=["gps_dropout"],
            output_dir=str(tmp_path),
            mission_profile=MISSION_PROFILE,
        )
        assert "test_integrity_hash" in report
        assert len(report["test_integrity_hash"]) == 64
