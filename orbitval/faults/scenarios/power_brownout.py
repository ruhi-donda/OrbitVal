"""
orbitval/faults/scenarios/power_brownout.py

Free fault scenario: Power brownout.
Simulates a sudden drop in available power — battery drain or
solar panel degradation entering eclipse.

Tier: FREE (generic fault)
"""

from dataclasses import replace
from orbitval.faults.base import TelemetryFrame


class PowerBrownout:
    """
    Simulates a power brownout — sudden reduction in battery
    charge and solar input. Tests whether autonomy code correctly
    sheds non-critical loads and enters safe mode.
    """

    name = "power_brownout"
    description = (
        "Sudden reduction in battery charge and solar power input. "
        "Tests autonomous power management and safe mode triggering."
    )
    version = "1.0.0"

    def __init__(
        self,
        t_start: float = 120.0,
        duration_s: float = 180.0,
        battery_drain_factor: float = 0.3,
        solar_drain_factor: float = 0.1,
    ):
        """
        Args:
            t_start: when brownout begins (seconds)
            duration_s: how long it lasts
            battery_drain_factor: multiply battery charge by this
            solar_drain_factor: multiply solar power by this
        """
        self.t_start = t_start
        self.duration_s = duration_s
        self.battery_drain_factor = battery_drain_factor
        self.solar_drain_factor = solar_drain_factor

    def is_active(self, t: float) -> bool:
        return self.t_start <= t <= self.t_start + self.duration_s

    def inject(self, telemetry: TelemetryFrame) -> TelemetryFrame:
        if not self.is_active(telemetry.t):
            return telemetry
        return replace(
            telemetry,
            battery_charge_wh=telemetry.battery_charge_wh * self.battery_drain_factor,
            solar_power_w=telemetry.solar_power_w * self.solar_drain_factor,
            flags={**telemetry.flags, "power_brownout": True},
        )