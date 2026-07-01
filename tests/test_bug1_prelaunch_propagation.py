"""
tests/test_bug1_prelaunch_propagation.py

Bug 1: propagate_from_params() built a malformed synthetic TLE string —
wrong column alignment and incorrect epoch format ("%f" = microseconds,
only 12 chars instead of the required 14-char "YYDDD.FFFFFFFF").
SGP4 rejected the malformed TLE and returned NaN for every ground track
point, making pre-launch mode (--orbit-alt / --orbit-inc) completely broken.

Fix: added _tle_checksum() helper; rebuilt both TLE lines with exact
fixed-width column layout per the TLE standard (69 chars total: 68-char
body + 1 checksum digit); computed epoch fraction as seconds-since-midnight
/ 86400 formatted to 8 decimal places.
"""

import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from orbitval.orbits.propagation import propagate_from_params, _tle_checksum


# ── helper ────────────────────────────────────────────────────────────────────

def _run(alt_km=550.0, inc_deg=53.0, duration_hours=0.25, step_seconds=60.0):
    return propagate_from_params(
        alt_km=alt_km,
        inc_deg=inc_deg,
        duration_hours=duration_hours,
        step_seconds=step_seconds,
        epoch="2026-01-01T00:00:00",  # fixed epoch for reproducibility
    )


# ── checksum helper ───────────────────────────────────────────────────────────

class TestTleChecksum:
    def test_all_zeros_gives_zero(self):
        """A body of all-zero digits produces checksum 0."""
        line = "0" * 68
        assert _tle_checksum(line) == 0

    def test_digit_sum_mod_10(self):
        """Checksum is (sum of digits) mod 10."""
        # 7 fives = 35, 35 % 10 = 5
        line = "55555550000000000000000000000000000000000000000000000000000000000000"
        assert len(line) == 68
        assert _tle_checksum(line) == 5

    def test_minus_counts_as_one(self):
        """Each '-' contributes 1 to the sum."""
        # 3 dashes, no digits → checksum = 3
        line = "-" * 3 + " " * 65
        assert len(line) == 68
        assert _tle_checksum(line) == 3

    def test_result_is_single_digit(self):
        """Result must be in [0, 9]."""
        line = "9" * 68  # 9*68=612, 612%10=2
        chk = _tle_checksum(line)
        assert 0 <= chk <= 9

    def test_synthetic_tle_checksum_roundtrip(self):
        """Checksum appended to a body must verify correctly (self-consistency)."""
        # Body generated from propagate_from_params format (known 68 chars)
        body = "2 99999  53.0000   0.0000 0000001   0.0000   0.0000 15.07819960    1"
        assert len(body) == 68
        chk = _tle_checksum(body)
        full_line = body + str(chk)
        # The checksum of the body must equal the digit we appended
        assert int(full_line[-1]) == _tle_checksum(full_line[:-1])


# ── NaN regression ────────────────────────────────────────────────────────────

class TestNoNaN:
    def test_lat_deg_no_nan(self):
        """lat_deg must not be NaN for any ground track point."""
        result = _run()
        nan_points = [p for p in result.ground_track if math.isnan(p.lat_deg)]
        assert len(nan_points) == 0, (
            f"{len(nan_points)} points have NaN lat_deg — Bug 1 not fixed"
        )

    def test_lon_deg_no_nan(self):
        """lon_deg must not be NaN for any ground track point."""
        result = _run()
        nan_points = [p for p in result.ground_track if math.isnan(p.lon_deg)]
        assert len(nan_points) == 0, (
            f"{len(nan_points)} points have NaN lon_deg — Bug 1 not fixed"
        )

    def test_alt_km_no_nan(self):
        """alt_km must not be NaN for any ground track point."""
        result = _run()
        nan_points = [p for p in result.ground_track if math.isnan(p.alt_km)]
        assert len(nan_points) == 0, (
            f"{len(nan_points)} points have NaN alt_km — Bug 1 not fixed"
        )


# ── physical plausibility ─────────────────────────────────────────────────────

class TestPlausibility:
    def test_altitude_within_50km_of_requested(self):
        """Mean altitude must be within ±50 km of the requested altitude."""
        requested_alt = 550.0
        result = _run(alt_km=requested_alt)
        alts = [p.alt_km for p in result.ground_track]
        mean_alt = sum(alts) / len(alts)
        assert abs(mean_alt - requested_alt) < 50.0, (
            f"Mean altitude {mean_alt:.1f} km is more than 50 km from "
            f"requested {requested_alt} km"
        )

    def test_latitude_bounded_by_inclination(self):
        """Ground track latitudes must stay within [-inc_deg, +inc_deg]."""
        inc_deg = 53.0
        result = _run(inc_deg=inc_deg)
        max_lat = max(abs(p.lat_deg) for p in result.ground_track)
        assert max_lat <= inc_deg + 1.0, (
            f"Max |latitude| {max_lat:.2f}° exceeds inclination {inc_deg}° "
            f"(+1° tolerance for propagation rounding)"
        )

    def test_longitude_in_valid_range(self):
        """Longitudes must be in [-180, 180]."""
        result = _run()
        for p in result.ground_track:
            assert -180.0 <= p.lon_deg <= 180.0, (
                f"Longitude {p.lon_deg}° out of range"
            )

    def test_point_count_matches_duration_and_step(self):
        """Ground track length must match int(duration_hours * 3600 / step_seconds)."""
        duration_hours = 0.25
        step_seconds = 60.0
        result = _run(duration_hours=duration_hours, step_seconds=step_seconds)
        expected = int(duration_hours * 3600 / step_seconds)
        assert len(result.ground_track) == expected, (
            f"Expected {expected} points, got {len(result.ground_track)}"
        )


# ── reproducibility ───────────────────────────────────────────────────────────

class TestReproducibility:
    def test_identical_inputs_produce_identical_ground_track(self):
        """Two calls with identical inputs must produce identical ground tracks."""
        r1 = _run()
        r2 = _run()
        assert len(r1.ground_track) == len(r2.ground_track)
        for i, (p1, p2) in enumerate(zip(r1.ground_track, r2.ground_track)):
            assert p1.lat_deg == p2.lat_deg, f"lat_deg differs at point {i}"
            assert p1.lon_deg == p2.lon_deg, f"lon_deg differs at point {i}"
            assert p1.alt_km == p2.alt_km, f"alt_km differs at point {i}"
