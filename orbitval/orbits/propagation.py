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

    return PropagationResult(
        epoch=epoch.utc_iso(),
        duration_s=duration_hours * 3600,
        ground_track=ground_track,
        eclipse_periods=[],   # Phase 1.1
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