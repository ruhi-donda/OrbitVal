"""
orbitval/faults/base.py

Base interface for all OrbitVal fault scenarios.
Every fault scenario — free or paid — must implement this interface.

From TEMPLATES.md:
  class FaultScenario:
      name: str
      description: str
      def inject(self, telemetry: TelemetryFrame) -> TelemetryFrame
      def is_active(self, t: float) -> bool
"""

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable
import random


@dataclass
class TelemetryFrame:
    """
    A single snapshot of satellite telemetry at time t.
    This is what flows between the simulation and the autonomy code.
    The fault injection engine intercepts and modifies these frames.
    """
    t: float                          # mission elapsed time in seconds
    gps_lat: float                    # degrees
    gps_lon: float                    # degrees
    gps_alt_km: float                 # km
    gps_available: bool               # False if GPS has dropped out
    magnetometer_x: float             # microtesla
    magnetometer_y: float             # microtesla
    magnetometer_z: float             # microtesla
    star_tracker_available: bool      # False if star tracker has failed
    battery_charge_wh: float          # current battery charge
    solar_power_w: float              # current solar input watts
    reaction_wheel_speed_rpm: float   # current wheel speed
    flags: dict = field(default_factory=dict)  # arbitrary metadata


@runtime_checkable
class FaultScenario(Protocol):
    """
    Interface every fault scenario must implement.
    Free scenarios live in orbitval/faults/scenarios/.
    Paid hardware-specific packs follow the same interface.
    """
    name: str
    description: str
    version: str

    def inject(self, telemetry: TelemetryFrame) -> TelemetryFrame:
        """
        Apply this fault to a telemetry frame.
        Must return a modified TelemetryFrame.
        Must not mutate the input — return a new frame.
        """
        ...

    def is_active(self, t: float) -> bool:
        """
        Return True if this fault should be active at mission time t.
        Allows faults to be time-windowed.
        """
        ...