"""
orbitval/ml/sim/telemetry.py

The smallest physically-driven telemetry generator that gives a
detector something to learn. Core OrbitVal's runner fills telemetry
with constants (solar always 5 W, battery always full), which a
forecaster would predict perfectly. Here the orbit drives the signals:

    orbit propagation (core OrbitVal, skyfield)
        -> illumination per step: 1 sunlit, 0.5 penumbra, 0 umbra
        -> solar power   = P_peak * illum * attitude factor + noise
        -> battery       integrates (charge efficiency * solar - load)
        -> temperature   relaxes toward a sunlit / eclipse equilibrium
        -> magnetometer  dipole field along the ground track + noise

Eclipse entry and exit are NORMAL here: solar power drops to zero
every orbit. That is deliberate — a persistence forecaster sees a big
error at every transition, so it can't just flag every large change.

Simplifications (on purpose, see "skip extra realism"):
- one-node thermal model, constant electrical load, no battery aging
- tilted-dipole magnetic field, not IGRF
- faults are applied after the fact to the measured values (as core
  OrbitVal does), so e.g. a solar fault does not feed back into the
  battery integration
"""

from dataclasses import dataclass
from functools import lru_cache

import numpy as np

from orbitval.config.hardware_3u_schema import HardwareConfig
from orbitval.faults.base import TelemetryFrame
from orbitval.orbits.propagation import propagate_from_params

# Channels a detector sees, in array column order
CHANNELS = (
    "solar_power_w",
    "battery_charge_wh",
    "temperature_c",
    "magnetometer_x",
    "magnetometer_y",
    "magnetometer_z",
)

SOLAR_CONSTANT_W_M2 = 1361.0
R_EARTH_KM = 6371.0


@dataclass(frozen=True)
class PowerThermalModel:
    """Every physical constant of the generator in one place."""
    cell_efficiency: float = 0.28        # solar cell efficiency
    attitude_period_s: float = 1020.0    # slow spin: not a multiple of the orbit
    attitude_depth: float = 0.2          # solar varies +-20% with attitude
    load_w: float = 10.0                 # constant bus load
    charge_efficiency: float = 0.9
    initial_soc: float = 0.7             # battery state of charge at t=0
    temp_sunlit_c: float = 25.0          # thermal equilibrium in sunlight
    temp_eclipse_c: float = -10.0        # thermal equilibrium in shadow
    thermal_tau_s: float = 1800.0        # thermal time constant
    initial_temp_c: float = 15.0
    dipole_b0_ut: float = 30.0           # equatorial surface field (µT)
    # Measurement noise (1 sigma) per channel
    solar_noise_w: float = 0.15
    battery_noise_wh: float = 0.02
    temp_noise_c: float = 0.15


@dataclass
class SimTelemetry:
    """One generated mission."""
    t: np.ndarray                  # (T,) mission time, seconds
    illumination: np.ndarray       # (T,) 1 / 0.5 / 0
    frames: list[TelemetryFrame]   # same data as frame objects (for fault injection)
    eclipse_periods: list[dict]


@lru_cache(maxsize=64)
def _propagate(alt_km: float, inc_deg: float, epoch: str, duration_hours: float, step_s: float):
    """Orbit propagation is the slow part; missions on the same orbit share it."""
    return propagate_from_params(
        alt_km=alt_km, inc_deg=inc_deg, duration_hours=duration_hours,
        step_seconds=step_s, epoch=epoch,
    )


def illumination_from_periods(eclipse_periods: list[dict], n_steps: int, step_s: float) -> np.ndarray:
    """
    Per-step illumination from core OrbitVal's eclipse periods. Each
    period covers steps [start_t, end_t) (end is the first step back in
    a different state).
    """
    illum = np.ones(n_steps)
    for p in eclipse_periods:
        a = int(round(p["start_t"] / step_s))
        b = int(round(p["end_t"] / step_s))
        illum[a:b] = 0.0 if p["type"] == "umbra" else 0.5
    return illum


def generate_telemetry(
    hardware: HardwareConfig,
    alt_km: float,
    inc_deg: float,
    epoch: str,
    seed: int,
    duration_hours: float = 24.0,
    step_s: float = 60.0,
    model: PowerThermalModel = PowerThermalModel(),
) -> SimTelemetry:
    """Generate one clean (fault-free) mission. Same arguments -> same data."""
    orbit = _propagate(alt_km, inc_deg, epoch, duration_hours, step_s)
    rng = np.random.default_rng(seed)
    n = len(orbit.ground_track)
    t = np.arange(n) * step_s
    illum = illumination_from_periods(orbit.eclipse_periods, n, step_s)

    # Solar: panel area * flux * efficiency, scaled by sunlight and a
    # slow attitude oscillation with a random phase per mission
    p_peak = SOLAR_CONSTANT_W_M2 * hardware.power.solar_panel_area_m2 * model.cell_efficiency
    phase = rng.uniform(0, 2 * np.pi)
    attitude = 1.0 - model.attitude_depth * (0.5 + 0.5 * np.cos(2 * np.pi * t / model.attitude_period_s + phase))
    solar_true = p_peak * illum * attitude

    # Battery: integrate net power (W * s / 3600 = Wh), clipped by the
    # charge controller to [0, capacity]
    cap = hardware.power.battery_capacity_wh
    battery_true = np.empty(n)
    e = model.initial_soc * cap
    for i in range(n):
        battery_true[i] = e
        net_w = model.charge_efficiency * solar_true[i] - model.load_w
        e = min(max(e + net_w * step_s / 3600.0, 0.0), cap)

    # Temperature: first-order relaxation toward the equilibrium for
    # the current lighting, dT = (T_eq - T) * dt / tau
    temp_true = np.empty(n)
    temp = model.initial_temp_c
    k = step_s / model.thermal_tau_s
    for i in range(n):
        temp_true[i] = temp
        t_eq = model.temp_eclipse_c + (model.temp_sunlit_c - model.temp_eclipse_c) * illum[i]
        temp += (t_eq - temp) * k

    # Magnetometer: dipole field at the satellite's latitude, falling off
    # as (R / r)^3. North and radial components, with a small east
    # component standing in for the dipole tilt.
    lat = np.radians([p.lat_deg for p in orbit.ground_track])
    lon = np.radians([p.lon_deg for p in orbit.ground_track])
    b0 = model.dipole_b0_ut * (R_EARTH_KM / (R_EARTH_KM + alt_km)) ** 3
    mag_true = np.stack([
        b0 * np.cos(lat),                # north
        0.1 * b0 * np.sin(lon),          # east (tilt stand-in)
        -2.0 * b0 * np.sin(lat),         # radial
    ], axis=1)
    mag_sigma = next(
        (s.noise_sigma for s in hardware.sensors if s.type == "magnetometer"), 0.02
    )

    # Measurement = truth + Gaussian noise
    solar = np.maximum(solar_true + rng.normal(0, model.solar_noise_w, n), 0.0)
    battery = battery_true + rng.normal(0, model.battery_noise_wh, n)
    temperature = temp_true + rng.normal(0, model.temp_noise_c, n)
    mag = mag_true + rng.normal(0, mag_sigma, (n, 3))

    frames = [
        TelemetryFrame(
            t=float(t[i]),
            gps_lat=orbit.ground_track[i].lat_deg,
            gps_lon=orbit.ground_track[i].lon_deg,
            gps_alt_km=orbit.ground_track[i].alt_km,
            gps_available=True,
            magnetometer_x=float(mag[i, 0]),
            magnetometer_y=float(mag[i, 1]),
            magnetometer_z=float(mag[i, 2]),
            star_tracker_available=True,
            battery_charge_wh=float(battery[i]),
            solar_power_w=float(solar[i]),
            reaction_wheel_speed_rpm=100.0,
            temperature_c=float(temperature[i]),
        )
        for i in range(n)
    ]
    return SimTelemetry(t=t, illumination=illum, frames=frames,
                        eclipse_periods=orbit.eclipse_periods)


def frames_to_array(frames: list[TelemetryFrame]) -> np.ndarray:
    """list of T frames -> (T, C) array in CHANNELS order."""
    return np.array([[getattr(f, ch) for ch in CHANNELS] for f in frames], dtype=np.float64)
