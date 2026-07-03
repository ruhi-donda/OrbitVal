"""
orbitval/orbits/propagation.py

Orbital mechanics engine for OrbitVal.
Propagates orbits from TLE or orbital parameters using skyfield + astropy.
Produces: ephemeris, ground track, eclipse periods, comms windows.

ADR-002: skyfield + astropy chosen for active maintenance and 
Python 3.13 compatibility.
ADR-003: TLE sourced from Celestrak or provided directly.
"""

from dataclasses import dataclass, field
from typing import Optional
import numpy as np
from skyfield.api import load, EarthSatellite, wgs84
from skyfield.positionlib import Geocentric
from astropy.time import Time as AstropyTime
from orbitval.logging import get_logger
log = get_logger("propagation")


def _tle_checksum(line: str) -> int:
    """Compute TLE line checksum: sum of digits + 1 for each '-', mod 10."""
    total = 0
    for ch in line:
        if ch.isdigit():
            total += int(ch)
        elif ch == "-":
            total += 1
    return total % 10


# ── Eclipse geometry ──────────────────────────────────────────

# Earth/sun constants for shadow computation (km)
R_EARTH_KM = 6371.0
R_SUN_KM = 696000.0
AU_KM = 149597870.7


def _sun_vector_eci(jd_tt: float) -> tuple[np.ndarray, float]:
    """
    Low-precision analytic solar position (Astronomical Almanac).
    Accurate to ~0.01° — far beyond what umbra entry/exit at
    minute-level telemetry resolution requires.

    Deliberately analytic rather than skyfield's is_sunlit(): that
    API requires downloading a JPL ephemeris file (de421.bsp), which
    would break OrbitVal's offline/air-gapped guarantee.

    Args:
        jd_tt: Julian date (TT)

    Returns:
        (unit vector Earth→Sun in ECI, Earth–Sun distance in km)
    """
    n = jd_tt - 2451545.0
    L = np.radians((280.460 + 0.9856474 * n) % 360.0)   # mean longitude
    g = np.radians((357.528 + 0.9856003 * n) % 360.0)   # mean anomaly
    lam = L + np.radians(1.915) * np.sin(g) + np.radians(0.020) * np.sin(2 * g)
    eps = np.radians(23.439 - 0.0000004 * n)             # obliquity

    sun_hat = np.array([
        np.cos(lam),
        np.cos(eps) * np.sin(lam),
        np.sin(eps) * np.sin(lam),
    ])
    dist_km = (1.00014 - 0.01671 * np.cos(g) - 0.00014 * np.cos(2 * g)) * AU_KM
    return sun_hat, dist_km


def _shadow_state(r_sat_km: np.ndarray, jd_tt: float) -> str:
    """
    Classify a satellite position as 'sunlit', 'penumbra', or 'umbra'
    using the standard conical shadow model: compare the apparent
    angular radii of the Earth and Sun as seen from the satellite.
    """
    sun_hat, sun_dist = _sun_vector_eci(jd_tt)
    sun_from_sat = sun_hat * sun_dist - r_sat_km
    earth_from_sat = -r_sat_km

    r_mag = np.linalg.norm(earth_from_sat)
    s_mag = np.linalg.norm(sun_from_sat)

    theta_e = np.arcsin(min(1.0, R_EARTH_KM / r_mag))    # Earth angular radius
    theta_s = np.arcsin(min(1.0, R_SUN_KM / s_mag))      # Sun angular radius
    cos_psi = np.dot(earth_from_sat, sun_from_sat) / (r_mag * s_mag)
    psi = np.arccos(np.clip(cos_psi, -1.0, 1.0))         # Earth–Sun separation

    if psi < theta_e - theta_s:
        return "umbra"
    if psi < theta_e + theta_s:
        return "penumbra"
    return "sunlit"


def _compute_eclipse_periods(
    satellite: EarthSatellite,
    times,
    step_seconds: float,
) -> list[dict]:
    """
    Scan the propagation time array and extract contiguous
    umbra/penumbra intervals as eclipse period dicts.
    """
    time_list = list(times)
    states = []
    for t in time_list:
        r_sat = np.asarray(satellite.at(t).position.km)
        states.append(_shadow_state(r_sat, t.tt))

    periods = []
    current_state = "sunlit"
    start_idx = None

    for i, state in enumerate(states):
        if state != current_state:
            if current_state != "sunlit" and start_idx is not None:
                periods.append({
                    "type": current_state,
                    "start_time": time_list[start_idx].utc_iso(),
                    "end_time": time_list[i].utc_iso(),
                    "start_t": start_idx * step_seconds,
                    "end_t": i * step_seconds,
                    "duration_s": (i - start_idx) * step_seconds,
                })
            start_idx = i if state != "sunlit" else None
            current_state = state

    # Interval still open at end of simulation
    if current_state != "sunlit" and start_idx is not None:
        last = len(states) - 1
        periods.append({
            "type": current_state,
            "start_time": time_list[start_idx].utc_iso(),
            "end_time": time_list[last].utc_iso(),
            "start_t": start_idx * step_seconds,
            "end_t": last * step_seconds,
            "duration_s": (last - start_idx) * step_seconds,
        })

    log.info(
        "Eclipse scan: %d period(s) found (%.0fs total in shadow)",
        len(periods), sum(p["duration_s"] for p in periods)
    )
    return periods


@dataclass
class GroundTrackPoint:
    """A single point on the satellite ground track."""
    time: str        # ISO 8601
    lat_deg: float
    lon_deg: float
    alt_km: float


@dataclass
class CommsWindow:
    """A visibility window between satellite and ground station."""
    start_time: str  # ISO 8601
    end_time: str    # ISO 8601
    duration_s: float
    max_elevation_deg: float


@dataclass
class PropagationResult:
    """Full output of an orbital propagation run."""
    epoch: str                                    # ISO 8601 start time
    duration_s: float
    ground_track: list[GroundTrackPoint]
    eclipse_periods: list[dict] = field(default_factory=list)
    comms_windows: list[CommsWindow] = field(default_factory=list)


def propagate_from_tle(
    tle_line1: str,
    tle_line2: str,
    tle_name: str = "SATELLITE",
    duration_hours: float = 24.0,
    step_seconds: float = 60.0,
    ground_station: Optional[dict] = None,
) -> PropagationResult:
    """
    Propagate an orbit from a TLE and return ground track,
    eclipse periods, and optional comms windows.

    Args:
        tle_line1: TLE line 1 string
        tle_line2: TLE line 2 string
        tle_name: satellite name (optional, for labeling)
        duration_hours: how long to propagate (default 24h)
        step_seconds: time step in seconds (default 60s)
        ground_station: optional dict with keys:
            lat_deg, lon_deg, alt_km, min_elevation_deg

    Returns:
        PropagationResult with ground track
    """
    ts = load.timescale()
    satellite = EarthSatellite(tle_line1, tle_line2, tle_name, ts)

    # Build time array
    epoch = satellite.epoch
    num_steps = int(duration_hours * 3600 / step_seconds)
    times = ts.tt_jd(
        np.linspace(epoch.tt, epoch.tt + duration_hours / 24.0, num_steps)
    )
    log.info(
        "Propagating %d steps over %.1fh from epoch %s",
        len(list(times)), duration_hours, epoch.utc_iso()
    )

    # Propagate and extract ground track
    ground_track = []
    for t in times:
        geocentric = satellite.at(t)
        subpoint = wgs84.subpoint(geocentric)
        ground_track.append(GroundTrackPoint(
            time=t.utc_iso(),
            lat_deg=float(subpoint.latitude.degrees),
            lon_deg=float(subpoint.longitude.degrees),
            alt_km=float(subpoint.elevation.km),
        ))

    # Eclipse periods — umbra/penumbra intervals from shadow geometry
    eclipse_periods = _compute_eclipse_periods(satellite, times, step_seconds)

    return PropagationResult(
        epoch=epoch.utc_iso(),
        duration_s=duration_hours * 3600,
        ground_track=ground_track,
        eclipse_periods=eclipse_periods,
        comms_windows=[],     # populated by comms_windows.py
    )


def propagate_from_params(
    alt_km: float,
    inc_deg: float,
    duration_hours: float = 24.0,
    step_seconds: float = 60.0,
    epoch: Optional[str] = None,
) -> PropagationResult:
    """
    Propagate a circular orbit from basic parameters.
    Useful for early mission design when no TLE exists yet.
    Generates a synthetic TLE for a circular orbit.

    Args:
        alt_km: orbital altitude in km
        inc_deg: inclination in degrees
        duration_hours: propagation duration
        step_seconds: time step
        epoch: ISO 8601 start time (defaults to now)

    Returns:
        PropagationResult with ground track
    """
    import math

    # Earth constants
    R_EARTH_KM = 6371.0
    MU = 398600.4418  # km^3/s^2

    # Compute mean motion (revs/day) for circular orbit
    r = R_EARTH_KM + alt_km
    n_rad_s = math.sqrt(MU / r**3)
    n_rev_day = n_rad_s * 86400 / (2 * math.pi)

    # Use current time if no epoch provided
    t0 = AstropyTime(epoch) if epoch else AstropyTime.now()

    # Build epoch string in TLE format: "YYDDD.FFFFFFFF" (exactly 14 chars)
    # %y = 2-digit year, %j = 3-digit day-of-year; fraction = seconds since midnight / 86400
    year_str = t0.strftime("%y")
    doy_str = t0.strftime("%j")
    midnight = AstropyTime(
        t0.strftime("%Y-%m-%d") + "T00:00:00", format="isot", scale="utc"
    )
    frac_day = (t0 - midnight).to_value("sec") / 86400.0
    epoch_str = year_str + doy_str + f"{frac_day:.8f}"[1:]  # "YYDDD.FFFFFFFF" = 14 chars

    # Build properly column-aligned synthetic TLE (each line = 68-char body + 1 checksum digit)
    # TLE line 1 column layout (0-indexed):
    #   0='1', 1=' ', 2-6=sat_num, 7=classification, 8=' ', 9-16=intl_designator,
    #   17=' ', 18-31=epoch(14), 32=' ', 33-42=dn_dt2(10), 43=' ',
    #   44-51=d2n_dt2(8), 52=' ', 53-60=bstar(8), 61=' ', 62=eph_type,
    #   63=' ', 64-67=elem_set(4), 68=checksum
    line1_body = (
        f"1 99999U 26001A   {epoch_str}"
        f"  .00000000  00000-0  00000-0 0  999"
    )
    line1 = line1_body + str(_tle_checksum(line1_body))

    # TLE line 2 column layout (0-indexed):
    #   0='2', 1=' ', 2-6=sat_num(5), 7=' ', 8-15=inc(8.4f), 16=' ',
    #   17-24=raan(8.4f), 25=' ', 26-32=ecc(7), 33=' ', 34-41=aop(8.4f),
    #   42=' ', 43-50=ma(8.4f), 51=' ', 52-62=n(11.8f), 63-67=revnum(5), 68=checksum
    line2_body = (
        f"2 99999 {inc_deg:8.4f} {0.0:8.4f} 0000001"
        f" {0.0:8.4f} {0.0:8.4f} {n_rev_day:11.8f}{1:5d}"
    )
    line2 = line2_body + str(_tle_checksum(line2_body))

    log.debug("Synthetic TLE line1: %s", line1)
    log.debug("Synthetic TLE line2: %s", line2)

    return propagate_from_tle(
        tle_line1=line1,
        tle_line2=line2,
        tle_name="SYNTHETIC",
        duration_hours=duration_hours,
        step_seconds=step_seconds,
    )