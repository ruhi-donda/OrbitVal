"""
tests/test_time_axis.py

Regression tests for the propagation time axis (Q1).

Mission elapsed time is derived by index everywhere downstream:
telemetry frames use t = index * step_seconds, eclipse periods use
start_t = index * step_seconds, and comms windows use the same at their
own (finer) step. That only holds if the propagator's samples are
spaced exactly step_seconds apart.

They were not. np.linspace(start, end, n) includes the endpoint, so a
1-hour run at 60s produced 60 samples 61.02s apart — the ISO timestamps
drifted away from the index-derived t by nearly a full step by the end
of the window, and comms windows (10s step) drifted against telemetry
frames (60s step) at a different rate.
"""

import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from orbitval.orbits.propagation import propagate_from_tle, propagate_from_params

TLE1 = "1 25544U 98067A   24001.50000000  .00001000  00000+0  10000-4 0  9991"
TLE2 = "2 25544  51.6400 100.0000 0001000  90.0000 270.0000 15.50000000000010"


def _iso_seconds(points) -> list[float]:
    """Seconds since the first sample, from the ISO timestamps."""
    times = [
        datetime.fromisoformat(p.time.replace("Z", "+00:00"))
        for p in points
    ]
    return [(t - times[0]).total_seconds() for t in times]


class TestGroundTrackSpacing:
    def test_spacing_matches_step_seconds(self):
        r = propagate_from_tle(TLE1, TLE2, duration_hours=1.0, step_seconds=60.0)
        secs = _iso_seconds(r.ground_track)
        deltas = [b - a for a, b in zip(secs, secs[1:])]
        for d in deltas:
            assert abs(d - 60.0) < 0.5, f"sample spacing {d}s, expected 60s"

    def test_spacing_matches_non_default_step(self):
        r = propagate_from_tle(TLE1, TLE2, duration_hours=1.0, step_seconds=120.0)
        secs = _iso_seconds(r.ground_track)
        deltas = [b - a for a, b in zip(secs, secs[1:])]
        for d in deltas:
            assert abs(d - 120.0) < 0.5

    def test_iso_time_agrees_with_index_derived_t(self):
        """The invariant the whole system assumes: the Nth sample's real
        elapsed time equals N * step_seconds."""
        step = 60.0
        r = propagate_from_tle(TLE1, TLE2, duration_hours=1.0, step_seconds=step)
        secs = _iso_seconds(r.ground_track)
        for i, actual in enumerate(secs):
            assert abs(actual - i * step) < 0.5, (
                f"frame {i}: ISO time is {actual}s in, but every consumer "
                f"treats it as t={i * step}s"
            )

    def test_last_sample_is_one_step_short_of_the_window(self):
        step = 60.0
        r = propagate_from_tle(TLE1, TLE2, duration_hours=1.0, step_seconds=step)
        secs = _iso_seconds(r.ground_track)
        assert abs(secs[-1] - (3600.0 - step)) < 0.5

    def test_sample_count_unchanged(self):
        """The endpoint fix must not change how many samples we produce."""
        r = propagate_from_tle(TLE1, TLE2, duration_hours=1.0, step_seconds=60.0)
        assert len(r.ground_track) == 60


class TestPrelaunchSpacing:
    def test_prelaunch_spacing_matches_step(self):
        r = propagate_from_params(
            alt_km=550, inc_deg=53.0, duration_hours=1.0, step_seconds=60.0,
            epoch="2026-09-08T00:00:00",
        )
        secs = _iso_seconds(r.ground_track)
        deltas = [b - a for a, b in zip(secs, secs[1:])]
        for d in deltas:
            assert abs(d - 60.0) < 0.5


class TestEclipsePeriodAlignment:
    def test_eclipse_bounds_land_on_step_multiples(self):
        step = 60.0
        r = propagate_from_tle(TLE1, TLE2, duration_hours=3.0, step_seconds=step)
        assert r.eclipse_periods, "expected at least one eclipse in 3 hours"
        for p in r.eclipse_periods:
            assert p["start_t"] % step == 0
            assert p["end_t"] % step == 0
            assert p["duration_s"] == p["end_t"] - p["start_t"]

    def test_eclipse_start_time_matches_start_t(self):
        """The ISO start_time and the mission-elapsed start_t must describe
        the same instant — they are read by different consumers."""
        step = 60.0
        r = propagate_from_tle(TLE1, TLE2, duration_hours=3.0, step_seconds=step)
        epoch = datetime.fromisoformat(r.epoch.replace("Z", "+00:00"))
        for p in r.eclipse_periods:
            iso_start = datetime.fromisoformat(
                p["start_time"].replace("Z", "+00:00")
            )
            elapsed = (iso_start - epoch).total_seconds()
            assert abs(elapsed - p["start_t"]) < 1.0, (
                f"eclipse ISO start is {elapsed}s in but start_t says "
                f"{p['start_t']}s"
            )
