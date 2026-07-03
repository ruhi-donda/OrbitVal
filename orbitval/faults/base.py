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
    ground_contact: bool = True       # False during comms blackout
    attitude_qw: float = 1.0          # attitude quaternion (scalar-first;
    attitude_qx: float = 0.0          #   identity = no rotation)
    attitude_qy: float = 0.0
    attitude_qz: float = 0.0
    attitude_valid: bool = True       # False if attitude solution unreliable
    temperature_c: float = 20.0       # bus temperature
    flags: dict = field(default_factory=dict)  # arbitrary metadata


class WindowedFault:
    """
    Shared base for time-windowed fault scenarios.
    Provides the t_start/duration_s window and is_active() so each
    scenario doesn't reimplement the same logic.
    """

    def __init__(self, t_start: float = 60.0, duration_s: float = 120.0):
        self.t_start = t_start
        self.duration_s = duration_s

    def is_active(self, t: float) -> bool:
        return self.t_start <= t <= self.t_start + self.duration_s


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