"""
orbitval/faults/scenarios/eclipse_power_stress.py

Free fault scenario: Eclipse-induced power/thermal stress.
Satellite enters Earth's shadow — solar input collapses, battery
degrades, and bus temperature drops until re-entering sunlight.

When the runner has real eclipse periods from the orbit propagation,
the fault activates during those actual umbra/penumbra intervals.
Otherwise it falls back to a fixed t_start/duration window like
every other scenario.

Tier: FREE (generic fault)
"""

from dataclasses import replace
from orbitval.faults.base import TelemetryFrame, WindowedFault


class EclipsePowerStress(WindowedFault):
    """
    Simulates power and thermal stress during eclipse passage.
    Solar input drops to near zero, battery charge degrades, and
    bus temperature falls. Tests whether autonomy code sheds load
    and manages power through the shadow period.

    Note: the thermal model is a simple bus-temperature drop, not
    a full thermal simulation (see Known limitations).
    """

    name = "eclipse_power_stress"
    description = (
        "Solar input collapse and thermal drop while the satellite "
        "passes through Earth's shadow. Tests autonomous power "
        "management across eclipse entry and exit."
    )
    version = "1.0.0"

    def __init__(
        self,
        t_start: float = 120.0,
        duration_s: float = 600.0,
        eclipse_windows: list[tuple[float, float]] | None = None,
        solar_factor: float = 0.0,
        battery_factor: float = 0.8,
        temperature_drop_c: float = 35.0,
    ):
        """
        Args:
            t_start: fallback window start (seconds) when no
                eclipse_windows are provided
            duration_s: fallback window duration
            eclipse_windows: real (start_t, end_t) eclipse intervals
                from orbit propagation — takes precedence over the
                fallback window when provided
            solar_factor: multiply solar power by this in shadow
            battery_factor: multiply battery charge by this in shadow
            temperature_drop_c: bus temperature drop in shadow
        """
        super().__init__(t_start=t_start, duration_s=duration_s)
        self.eclipse_windows = eclipse_windows or []
        self.solar_factor = solar_factor
        self.battery_factor = battery_factor
        self.temperature_drop_c = temperature_drop_c

    def is_active(self, t: float) -> bool:
        if self.eclipse_windows:
            return any(start <= t <= end for start, end in self.eclipse_windows)
        return super().is_active(t)

    def inject(self, telemetry: TelemetryFrame) -> TelemetryFrame:
        if not self.is_active(telemetry.t):
            return telemetry
        return replace(
            telemetry,
            solar_power_w=telemetry.solar_power_w * self.solar_factor,
            battery_charge_wh=telemetry.battery_charge_wh * self.battery_factor,
            temperature_c=telemetry.temperature_c - self.temperature_drop_c,
            flags={**telemetry.flags, "eclipse_power_stress": True},
        )
