"""
orbitval/faults/scenarios/gps_dropout.py

Free fault scenario: GPS signal dropout.
Simulates complete loss of GPS signal for a configurable duration.

Tier: FREE (generic fault — no vendor-specific behavior required)
"""

from dataclasses import replace
from orbitval.faults.base import TelemetryFrame


class GpsDropout:
    """
    Simulates a complete GPS signal dropout starting at t_start
    and lasting for duration_s seconds.

    This is one of the most common CubeSat failure modes —
    GPS loss during orbital insertion, eclipse entry, or
    antenna obstruction.
    """

    name = "gps_dropout"
    description = (
        "Complete GPS signal loss for a configurable duration. "
        "Tests whether autonomy code can maintain safe operation "
        "using dead reckoning or alternative navigation."
    )
    version = "1.0.0"

    def __init__(self, t_start: float = 60.0, duration_s: float = 120.0):
        """
        Args:
            t_start: mission time (seconds) when dropout begins
            duration_s: how long the dropout lasts
        """
        self.t_start = t_start
        self.duration_s = duration_s

    def is_active(self, t: float) -> bool:
        return self.t_start <= t <= self.t_start + self.duration_s

    def inject(self, telemetry: TelemetryFrame) -> TelemetryFrame:
        if not self.is_active(telemetry.t):
            return telemetry
        return replace(
            telemetry,
            gps_available=False,
            gps_lat=0.0,
            gps_lon=0.0,
            gps_alt_km=0.0,
            flags={**telemetry.flags, "gps_dropout": True},
        )