"""
tests/test_eclipse_detection.py

Eclipse period computation in propagation.py — shadow geometry
correctness, period structure, determinism, and presence in the
ORF report.
"""

import numpy as np
import pytest

from orbitval.orbits.propagation import (
    propagate_from_tle,
    propagate_from_params,
    _sun_vector_eci,
    _shadow_state,
    R_EARTH_KM,
)
from tests.conftest import TLE1, TLE2


class TestSunVector:
    def test_unit_vector(self):
        sun_hat, _ = _sun_vector_eci(2451545.0)
        assert abs(np.linalg.norm(sun_hat) - 1.0) < 1e-9

    def test_january_declination_near_minus_23(self):
        """Sun declination on Jan 1 (J2000) is ~ -23°."""
        sun_hat, _ = _sun_vector_eci(2451545.0)
        dec = np.degrees(np.arcsin(sun_hat[2]))
        assert -23.5 < dec < -22.5

    def test_july_declination_near_plus_23(self):
        """Sun declination near July solstice is ~ +23°."""
        # J2000 + 172 days ≈ June 21
        sun_hat, _ = _sun_vector_eci(2451545.0 + 172)
        dec = np.degrees(np.arcsin(sun_hat[2]))
        assert 23.0 < dec < 23.6

    def test_distance_near_one_au(self):
        _, dist = _sun_vector_eci(2451545.0)
        assert 1.45e8 < dist < 1.53e8  # km, within perihelion/aphelion


class TestShadowState:
    def test_satellite_between_sun_and_earth_is_sunlit(self):
        """Satellite on the day side, directly toward the sun."""
        sun_hat, _ = _sun_vector_eci(2451545.0)
        r_sat = sun_hat * (R_EARTH_KM + 550.0)
        assert _shadow_state(r_sat, 2451545.0) == "sunlit"

    def test_satellite_behind_earth_is_umbra(self):
        """Satellite on the anti-sun side, deep in shadow."""
        sun_hat, _ = _sun_vector_eci(2451545.0)
        r_sat = -sun_hat * (R_EARTH_KM + 550.0)
        assert _shadow_state(r_sat, 2451545.0) == "umbra"

    def test_satellite_perpendicular_is_sunlit(self):
        """Satellite 90° from the sun line is outside the shadow."""
        sun_hat, _ = _sun_vector_eci(2451545.0)
        # Any vector perpendicular to sun_hat
        perp = np.cross(sun_hat, [0.0, 0.0, 1.0])
        perp = perp / np.linalg.norm(perp)
        r_sat = perp * (R_EARTH_KM + 550.0)
        assert _shadow_state(r_sat, 2451545.0) == "sunlit"


class TestEclipsePeriods:
    def test_iss_orbit_has_eclipse_periods(self):
        """An ISS-like LEO orbit crosses the shadow every ~92 min."""
        r = propagate_from_tle(TLE1, TLE2, duration_hours=3.0, step_seconds=60)
        assert len(r.eclipse_periods) > 0

    def test_shadow_fraction_plausible_for_leo(self):
        """LEO shadow fraction is roughly 30-40% of the orbit."""
        r = propagate_from_tle(TLE1, TLE2, duration_hours=3.0, step_seconds=60)
        total_shadow = sum(p["duration_s"] for p in r.eclipse_periods)
        fraction = total_shadow / (3.0 * 3600)
        assert 0.2 < fraction < 0.5, f"shadow fraction {fraction:.2f} implausible"

    def test_period_structure(self):
        r = propagate_from_tle(TLE1, TLE2, duration_hours=3.0, step_seconds=60)
        for p in r.eclipse_periods:
            assert p["type"] in ("umbra", "penumbra")
            assert p["end_t"] > p["start_t"]
            assert p["duration_s"] == p["end_t"] - p["start_t"]
            assert p["start_time"]  # ISO string
            assert p["end_time"]

    def test_deterministic(self):
        r1 = propagate_from_tle(TLE1, TLE2, duration_hours=2.0, step_seconds=60)
        r2 = propagate_from_tle(TLE1, TLE2, duration_hours=2.0, step_seconds=60)
        assert r1.eclipse_periods == r2.eclipse_periods

    def test_prelaunch_mode_also_computes_eclipse(self):
        """propagate_from_params routes through the same eclipse scan."""
        r = propagate_from_params(alt_km=550, inc_deg=53.0,
                                  duration_hours=3.0, step_seconds=60)
        # Result must be a list (may legitimately be empty for some
        # epoch/orbit geometry, but the field must be populated)
        assert isinstance(r.eclipse_periods, list)


class TestEclipseInReport:
    def test_eclipse_periods_in_orf_report(self, prelaunch_runner, tmp_path):
        report = prelaunch_runner.run(
            scenarios=["gps_dropout"],
            output_dir=str(tmp_path),
        )
        assert "eclipse_periods" in report
        assert report["eclipse_periods"] == prelaunch_runner.orbit.eclipse_periods

    def test_eclipse_periods_included_in_integrity_hash(self, prelaunch_runner, tmp_path):
        """Tampering with eclipse_periods must break verification."""
        import json
        report = prelaunch_runner.run(
            scenarios=["gps_dropout"],
            output_dir=str(tmp_path),
        )
        report_file = next(tmp_path.glob("*.json"))
        data = json.loads(report_file.read_text())
        data["eclipse_periods"] = [{"type": "umbra", "forged": True}]  # tamper
        report_file.write_text(json.dumps(data))

        import argparse
        from orbitval.cli import cmd_verify_report
        with pytest.raises(SystemExit) as exc:
            cmd_verify_report(argparse.Namespace(report=str(report_file)))
        assert exc.value.code == 1
