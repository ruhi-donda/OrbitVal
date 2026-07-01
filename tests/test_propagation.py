"""
tests/test_propagation.py

Edge-case and boundary tests for orbitval/orbits/propagation.py.
Covers propagate_from_tle and propagate_from_params with unusual inputs.
"""

import sys
import math
import pytest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from orbitval.orbits.propagation import (
    propagate_from_tle,
    propagate_from_params,
    PropagationResult,
)

TLE1 = "1 25544U 98067A   24001.50000000  .00001000  00000+0  10000-4 0  9991"
TLE2 = "2 25544  51.6400 100.0000 0001000  90.0000 270.0000 15.50000000000010"


class TestPropagateFromTle:
    def test_returns_propagation_result(self):
        r = propagate_from_tle(TLE1, TLE2, duration_hours=0.1, step_seconds=60)
        assert isinstance(r, PropagationResult)

    def test_ground_track_not_empty(self):
        r = propagate_from_tle(TLE1, TLE2, duration_hours=0.1, step_seconds=60)
        assert len(r.ground_track) > 0

    def test_point_count_matches_formula(self):
        duration_hours = 0.5
        step_seconds = 60.0
        expected = int(duration_hours * 3600 / step_seconds)
        r = propagate_from_tle(TLE1, TLE2, duration_hours=duration_hours,
                                step_seconds=step_seconds)
        assert len(r.ground_track) == expected

    def test_single_step(self):
        # step == duration → exactly 1 point
        r = propagate_from_tle(TLE1, TLE2, duration_hours=1/3600, step_seconds=1.0)
        assert len(r.ground_track) == 1

    def test_lat_within_bounds(self):
        r = propagate_from_tle(TLE1, TLE2, duration_hours=1.0, step_seconds=120)
        for pt in r.ground_track:
            assert -90.0 <= pt.lat_deg <= 90.0

    def test_lon_within_bounds(self):
        r = propagate_from_tle(TLE1, TLE2, duration_hours=1.0, step_seconds=120)
        for pt in r.ground_track:
            assert -180.0 <= pt.lon_deg <= 180.0

    def test_altitude_positive(self):
        r = propagate_from_tle(TLE1, TLE2, duration_hours=1.0, step_seconds=120)
        for pt in r.ground_track:
            assert pt.alt_km > 0

    def test_epoch_is_set(self):
        r = propagate_from_tle(TLE1, TLE2, duration_hours=0.1, step_seconds=60)
        assert r.epoch  # non-empty string


class TestPropagateFromParams:
    def test_returns_propagation_result(self):
        r = propagate_from_params(alt_km=500, inc_deg=51.6,
                                  duration_hours=0.5, step_seconds=120)
        assert isinstance(r, PropagationResult)

    def test_point_count_matches_formula(self):
        duration_hours = 0.5
        step_seconds = 60.0
        expected = int(duration_hours * 3600 / step_seconds)
        r = propagate_from_params(alt_km=500, inc_deg=51.6,
                                  duration_hours=duration_hours,
                                  step_seconds=step_seconds)
        assert len(r.ground_track) == expected

    def test_equatorial_orbit_lats_near_zero(self):
        """0° inclination → all latitudes should be close to 0°."""
        r = propagate_from_params(alt_km=500, inc_deg=0.0,
                                  duration_hours=1.0, step_seconds=120)
        for pt in r.ground_track:
            assert abs(pt.lat_deg) < 5.0, f"lat {pt.lat_deg} too far from equator"

    def test_polar_orbit_spans_full_latitude_range(self):
        """90° inclination → ground track should reach high latitudes."""
        r = propagate_from_params(alt_km=500, inc_deg=90.0,
                                  duration_hours=2.0, step_seconds=60)
        max_lat = max(abs(pt.lat_deg) for pt in r.ground_track)
        assert max_lat > 60.0, f"polar orbit max lat {max_lat} too low"

    def test_altitude_within_tolerance_of_requested(self):
        """Mean altitude of ground track should be close to requested alt_km."""
        requested = 550.0
        r = propagate_from_params(alt_km=requested, inc_deg=51.6,
                                  duration_hours=1.0, step_seconds=120)
        mean_alt = sum(pt.alt_km for pt in r.ground_track) / len(r.ground_track)
        assert abs(mean_alt - requested) < 50.0

    def test_custom_epoch_accepted(self):
        r = propagate_from_params(alt_km=400, inc_deg=45.0,
                                  duration_hours=0.5, step_seconds=120,
                                  epoch="2025-01-01T00:00:00")
        assert len(r.ground_track) > 0
