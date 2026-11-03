"""
orbitval/ml/sim/faults.py

Fault catalogue for detector validation. Each fault takes one knob,
severity in [0, 1], mapped to that fault's own physical parameters:
0 = no visible effect, 1 = the strongest version.

Three reuse core OrbitVal fault classes unchanged; two are new and live
here (core FAULT_REGISTRY and `orbitval list-faults` are untouched).
Both kinds implement core's FaultScenario interface, so they go
through core's run_injection().

Left out on purpose: gps_dropout, comms_blackout, star_tracker_failure.
They flip availability flags or zero out channels that aren't in
CHANNELS, so a simple rule catches them perfectly. A learned forecaster
is the wrong tool for them.

eclipse_power_stress is given an explicit window and NO eclipse_windows,
and missions.py places that window in sunlight. That makes it an
*unexpected* loss of power and heat. Real eclipses are normal data here.
"""

from dataclasses import replace

from orbitval.faults.base import TelemetryFrame, WindowedFault
from orbitval.faults.scenarios.eclipse_power_stress import EclipsePowerStress
from orbitval.faults.scenarios.power_brownout import PowerBrownout
from orbitval.faults.scenarios.sensor_noise import SensorNoise


class SensorDrift(WindowedFault):
    """A sensor reading drifts linearly away from the truth (e.g. a
    degrading thermistor): offset grows from 0 to `total_drift` over the
    fault window."""

    name = "sensor_drift"
    description = "Linear drift of one sensor reading over the fault window."
    version = "1.0.0"

    def __init__(self, t_start: float, duration_s: float,
                 channel: str = "temperature_c", total_drift: float = 10.0):
        super().__init__(t_start=t_start, duration_s=duration_s)
        self.channel = channel
        self.total_drift = total_drift

    def inject(self, telemetry: TelemetryFrame) -> TelemetryFrame:
        if not self.is_active(telemetry.t):
            return telemetry
        frac = (telemetry.t - self.t_start) / self.duration_s if self.duration_s else 1.0
        return replace(
            telemetry,
            **{self.channel: getattr(telemetry, self.channel) + self.total_drift * frac},
            flags={**telemetry.flags, self.name: True},
        )


class StuckSensor(WindowedFault):
    """A sensor freezes at the value it read when the fault began."""

    name = "stuck_sensor"
    description = "One sensor repeats its last reading for the fault window."
    version = "1.0.0"

    def __init__(self, t_start: float, duration_s: float, channel: str = "solar_power_w"):
        super().__init__(t_start=t_start, duration_s=duration_s)
        self.channel = channel
        self._held: float | None = None

    def inject(self, telemetry: TelemetryFrame) -> TelemetryFrame:
        if not self.is_active(telemetry.t):
            return telemetry
        if self._held is None:                 # first faulty frame: latch it
            self._held = getattr(telemetry, self.channel)
        return replace(
            telemetry,
            **{self.channel: self._held},
            flags={**telemetry.flags, self.name: True},
        )


# Severity -> constructor arguments. These scales were picked so the
# baseline's detection rate moves from "rarely" to "always" across
# 0..1 — a map where everything is 0 or 1 would say nothing.
FAULTS = {
    # battery reading and solar input both sag
    "power_brownout": lambda s, t0, dur, seed: PowerBrownout(
        t_start=t0, duration_s=dur,
        battery_drain_factor=1.0 - 0.5 * s, solar_drain_factor=1.0 - 0.9 * s),
    # extra magnetometer noise: std 0.1 µT * noise_scale (sensor's own is 0.02 µT)
    "sensor_noise": lambda s, t0, dur, seed: SensorNoise(
        t_start=t0, duration_s=dur, noise_scale=10.0 * s, seed=seed),
    # solar collapse + battery dip + temperature drop while in sunlight
    "eclipse_power_stress": lambda s, t0, dur, seed: EclipsePowerStress(
        t_start=t0, duration_s=dur, eclipse_windows=None,
        solar_factor=1.0 - s, battery_factor=1.0 - 0.2 * s, temperature_drop_c=20.0 * s),
    # temperature reading drifts by up to 8 °C over the window
    "sensor_drift": lambda s, t0, dur, seed: SensorDrift(
        t_start=t0, duration_s=dur, channel="temperature_c", total_drift=8.0 * s),
    # solar sensor freezes. Severity has no meaning for a frozen sensor,
    # so it is ignored and this row of the map is flat by design.
    "stuck_sensor": lambda s, t0, dur, seed: StuckSensor(
        t_start=t0, duration_s=dur, channel="solar_power_w"),
}


def build_fault(name: str, severity: float, t_start: float, duration_s: float, seed: int = 0):
    """Instantiate a catalogue fault at a given severity in [0, 1]."""
    if name not in FAULTS:
        raise ValueError(f"unknown fault '{name}'. Available: {sorted(FAULTS)}")
    if not 0.0 <= severity <= 1.0:
        raise ValueError("severity must be in [0, 1]")
    return FAULTS[name](severity, t_start, duration_s, seed)
