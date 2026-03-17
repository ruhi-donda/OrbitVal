"""
orbitval/faults/scenarios/sensor_noise.py

Free fault scenario: Amplified sensor noise.
Injects gaussian noise into magnetometer and GPS readings,
simulating electromagnetic interference or sensor degradation.

Tier: FREE (generic fault)
"""

from dataclasses import replace
import random
import math
from orbitval.faults.base import TelemetryFrame


class SensorNoise:
    """
    Injects amplified gaussian noise into sensor readings.
    Simulates electromagnetic interference, radiation effects,
    or gradual sensor degradation.
    """

    name = "sensor_noise"
    description = (
        "Amplified gaussian noise injected into magnetometer "
        "and GPS readings. Tests autonomy code robustness against "
        "degraded sensor quality."
    )
    version = "1.0.0"

    def __init__(
        self,
        t_start: float = 0.0,
        duration_s: float = 300.0,
        noise_scale: float = 5.0,
        seed: int = 42,
    ):
        """
        Args:
            t_start: when noise injection begins
            duration_s: how long it lasts
            noise_scale: multiplier on baseline sensor noise_sigma
            seed: random seed for reproducibility (critical for ORF)
        """
        self.t_start = t_start
        self.duration_s = duration_s
        self.noise_scale = noise_scale
        self.rng = random.Random(seed)

    def is_active(self, t: float) -> bool:
        return self.t_start <= t <= self.t_start + self.duration_s

    def _gauss(self, sigma: float) -> float:
        return self.rng.gauss(0, sigma * self.noise_scale)

    def inject(self, telemetry: TelemetryFrame) -> TelemetryFrame:
        if not self.is_active(telemetry.t):
            return telemetry
        return replace(
            telemetry,
            magnetometer_x=telemetry.magnetometer_x + self._gauss(0.1),
            magnetometer_y=telemetry.magnetometer_y + self._gauss(0.1),
            magnetometer_z=telemetry.magnetometer_z + self._gauss(0.1),
            gps_lat=telemetry.gps_lat + self._gauss(0.001),
            gps_lon=telemetry.gps_lon + self._gauss(0.001),
            flags={**telemetry.flags, "sensor_noise": True},
        )