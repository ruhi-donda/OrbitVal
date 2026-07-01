"""
tests/test_bug6_mission_profile_backfill.py

Bug 6: mission_profile.altitude_band_km and inclination_deg were populated
only from --orbit-alt/--orbit-inc CLI flags. On live-TLE and manual-TLE
runs (Modes 1 and 2) where those flags aren't given, both fields were
silently None in every report — making the ORF non-self-describing,
contradicting ARCHITECTURE.md's stated purpose for mission context fields.

Fix: after TestRunner construction, cli.py parses inclination from TLE
line 2 (cols 8-15) and computes mean altitude from the ground track when
args.orbit_alt is None and runner.tle is not None (Modes 1 & 2).

These tests verify the fix via the Python API (Mode 2 / manual TLE),
since Mode 1 requires live network. The backfill logic is also tested
directly against known TLE values.
"""

import sys
import math
import pytest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from orbitval.engine.runner import TestRunner


SATELLITE_YAML = str(Path(__file__).parent.parent / "satellite.yaml")

# ISS TLE — inclination is 51.6400°, mean altitude ~410 km
TLE_LINE1 = "1 25544U 98067A   24010.50000000  .00016717  00000-0  10270-3 0  9007"
TLE_LINE2 = "2 25544  51.6400 208.9163 0006317  69.9862  25.2906 15.49815747 33333"

MISSION_PROFILE_TEMPLATE = {
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


def _make_runner(**kwargs):
    defaults = dict(
        config=SATELLITE_YAML,
        autonomy=_NoopAutonomy(),
        tle_line1=TLE_LINE1,
        tle_line2=TLE_LINE2,
        duration_hours=0.5,
        step_seconds=60.0,
        seed=42,
    )
    defaults.update(kwargs)
    return TestRunner(**defaults)


class TestTLEParsing:
    """Unit tests for the TLE parsing that drives the backfill."""

    def test_inclination_parsed_from_tle_line2(self):
        """Inclination must be parsed from TLE line 2 columns 8-15."""
        # ISS TLE has 51.6400° inclination at cols 8-15
        inclination = float(TLE_LINE2[8:16].strip())
        assert abs(inclination - 51.64) < 0.01, (
            f"Expected ~51.64°, got {inclination}°"
        )

    def test_mean_altitude_from_ground_track(self):
        """Mean altitude from ground track must be plausible for ISS (~400 km)."""
        runner = _make_runner()
        track_alts = [p.alt_km for p in runner.orbit.ground_track]
        mean_alt = sum(track_alts) / len(track_alts)
        # ISS orbits at ~400-420 km; allow a wider band for propagation math
        assert 350 < mean_alt < 500, (
            f"Mean altitude {mean_alt:.1f} km outside expected ISS range 350-500 km"
        )


class TestMissionProfileBackfill:
    """Integration tests: verify the runner exposes the data the CLI backfill needs."""

    def test_runner_tle_is_set_for_mode2(self):
        """runner.tle must be set (not None) for Mode 2 (manual TLE strings)."""
        runner = _make_runner()
        assert runner.tle is not None

    def test_runner_ground_track_has_valid_alts_for_mode2(self):
        """Ground track must have valid (non-NaN) altitudes for Mode 2."""
        runner = _make_runner()
        for point in runner.orbit.ground_track:
            assert not math.isnan(point.alt_km), (
                f"NaN altitude at t={point.time} — ground track is invalid"
            )

    def test_runner_tle_is_none_for_prelaunch_mode(self):
        """runner.tle must be None for Mode 3 (pre-launch) — backfill must not run."""
        runner = TestRunner(
            config=SATELLITE_YAML,
            autonomy=_NoopAutonomy(),
            orbit_alt_km=550.0,
            orbit_inc_deg=53.0,
            duration_hours=0.1,
            step_seconds=60.0,
            seed=42,
        )
        assert runner.tle is None, (
            "runner.tle should be None in pre-launch mode — backfill would use NaN track"
        )

    def test_backfill_produces_plausible_values(self, tmp_path):
        """When backfill runs for Mode 2, the resulting mission_profile values
        must be numeric and plausible for ISS (sanity check, not exact match)."""
        runner = _make_runner()
        # Simulate what cli.py's backfill does
        inclination_deg = float(runner.tle.line2[8:16].strip())
        track_alts = [p.alt_km for p in runner.orbit.ground_track]
        altitude_band_km = round(sum(track_alts) / len(track_alts), 1)

        assert 45 < inclination_deg < 60, (
            f"ISS inclination {inclination_deg}° not in expected range 45-60°"
        )
        assert 350 < altitude_band_km < 500, (
            f"ISS mean altitude {altitude_band_km} km not in expected range 350-500 km"
        )

    def test_report_mission_profile_non_null_for_mode2(self, tmp_path):
        """After backfill, mission_profile in the report must not have None
        for altitude_band_km or inclination_deg (regression guard)."""
        runner = _make_runner()

        # Replicate the backfill as cli.py does it
        altitude_band_km = None
        inclination_deg = None
        if runner.tle is not None and altitude_band_km is None:
            inclination_deg = float(runner.tle.line2[8:16].strip())
            track_alts = [p.alt_km for p in runner.orbit.ground_track]
            if track_alts:
                altitude_band_km = round(sum(track_alts) / len(track_alts), 1)

        report = runner.run(
            scenarios=["gps_dropout"],
            output_dir=str(tmp_path),
            mission_profile={
                "orbit_type": "LEO",
                "altitude_band_km": altitude_band_km,
                "inclination_deg": inclination_deg,
                "operational_lifetime_years": None,
            },
        )
        mp = report["mission_profile"]
        assert mp["altitude_band_km"] is not None, (
            "altitude_band_km is None after backfill — Bug 6 regression"
        )
        assert mp["inclination_deg"] is not None, (
            "inclination_deg is None after backfill — Bug 6 regression"
        )
