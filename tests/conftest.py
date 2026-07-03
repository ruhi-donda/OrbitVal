"""
tests/conftest.py

Shared fixtures and helpers for the OrbitVal test suite.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from orbitval.faults.base import TelemetryFrame

SATELLITE_YAML = str(Path(__file__).parent.parent / "satellite.yaml")

# Real ISS TLE (deterministic, no network required)
TLE1 = "1 25544U 98067A   24001.50000000  .00001000  00000+0  10000-4 0  9991"
TLE2 = "2 25544  51.6400 100.0000 0001000  90.0000 270.0000 15.50000000000010"


def make_frame(t: float = 0.0, **overrides) -> TelemetryFrame:
    """Build a nominal TelemetryFrame, overriding any field."""
    defaults = dict(
        t=t,
        gps_lat=40.0, gps_lon=-74.0, gps_alt_km=550.0, gps_available=True,
        magnetometer_x=25.0, magnetometer_y=-10.0, magnetometer_z=40.0,
        star_tracker_available=True,
        battery_charge_wh=20.0, solar_power_w=5.0,
        reaction_wheel_speed_rpm=100.0,
    )
    defaults.update(overrides)
    return TelemetryFrame(**defaults)


class SilentlyTrustingAutonomy:
    """Autonomy that never reacts to anything — always nominal.
    Every scenario must FAIL against this."""

    def process(self, telemetry) -> str:
        return "nominal"

    def reset(self):
        pass


class ResponsiveAutonomy:
    """Autonomy that correctly detects every free fault from raw
    sensor data. Every scenario should PASS against this."""

    def process(self, telemetry) -> str:
        if not telemetry.gps_available:
            return "failover_to_dead_reckoning"
        if telemetry.battery_charge_wh < 5.0:
            return "safe_mode"
        if telemetry.solar_power_w < 1.0:
            return "reduced_ops"
        if not telemetry.ground_contact:
            return "reduced_ops"
        if not telemetry.star_tracker_available or not telemetry.attitude_valid:
            return "failover"
        return "nominal"

    def reset(self):
        pass


@pytest.fixture
def prelaunch_runner():
    """A TestRunner in pre-launch mode with responsive autonomy —
    no network access needed."""
    from orbitval.engine.runner import TestRunner
    return TestRunner(
        config=SATELLITE_YAML,
        autonomy=ResponsiveAutonomy(),
        orbit_alt_km=550.0,
        orbit_inc_deg=53.0,
    )
