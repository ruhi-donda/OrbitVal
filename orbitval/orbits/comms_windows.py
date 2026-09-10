"""
orbitval/orbits/comms_windows.py

Ground station visibility window calculator for OrbitVal.
Computes when a satellite is visible from a ground station
given a propagated orbit.

A comms window is the time interval when the satellite is
above the minimum elevation angle as seen from the ground
station. During these windows the satellite can communicate
with ground control. Outside these windows the satellite
must operate fully autonomously.

This is critical for fault injection context — faults that
occur outside comms windows are the most dangerous because
ground intervention is impossible.
"""

from dataclasses import dataclass
from orbitval.faults.base import TelemetryFrame
from skyfield.api import load, wgs84, EarthSatellite
import numpy as np
from orbitval.logging import get_logger
log = get_logger("comms")


@dataclass
class GroundStation:
    """A ground station location."""
    name: str
    lat_deg: float
    lon_deg: float
    alt_km: float = 0.0
    min_elevation_deg: float = 10.0  # minimum elevation for link


@dataclass
class CommsWindow:
    """
    A single visibility window between satellite and ground station.
    The satellite is above min_elevation_deg for this entire interval.
    """
    ground_station: str      # station name
    start_time: str          # ISO 8601
    end_time: str            # ISO 8601
    duration_s: float
    max_elevation_deg: float
    start_t: float           # mission elapsed seconds
    end_t: float             # mission elapsed seconds


def compute_comms_windows(
    tle_line1: str,
    tle_line2: str,
    tle_name: str,
    ground_stations: list[GroundStation],
    duration_hours: float = 24.0,
    step_seconds: float = 10.0,
) -> list[CommsWindow]:
    """
    Compute all ground station visibility windows for a satellite.

    Args:
        tle_line1: TLE line 1
        tle_line2: TLE line 2
        tle_name: satellite name
        ground_stations: list of GroundStation objects
        duration_hours: how long to search for windows
        step_seconds: time resolution (smaller = more accurate
                      window edges, but slower)

    Returns:
        List of CommsWindow objects sorted by start time
    """
    ts = load.timescale()
    satellite = EarthSatellite(tle_line1, tle_line2, tle_name, ts)
    epoch = satellite.epoch

    # Build time array
    num_steps = int(duration_hours * 3600 / step_seconds)
    # endpoint=False — see propagate_from_tle. Window edges here are
    # reported as start_t/end_t = index * step_seconds and are compared
    # against telemetry frame times, so the spacing must be exact.
    times = ts.tt_jd(
        np.linspace(
            epoch.tt,
            epoch.tt + duration_hours / 24.0,
            num_steps,
            endpoint=False,
        )
    )

    all_windows = []

    for station in ground_stations:
        # Build skyfield ground station location
        gs_location = wgs84.latlon(
            station.lat_deg,
            station.lon_deg,
            elevation_m=station.alt_km * 1000,
        )

        # Compute elevation at each time step
        elevations = []
        for t in times:
            difference = satellite - gs_location
            topocentric = difference.at(t)
            alt, az, distance = topocentric.altaz()
            elevations.append(alt.degrees)

        # Find window start/end by scanning elevation array
        in_window = False
        window_start_idx = None
        max_el = -90.0

        for i, el in enumerate(elevations):
            above = el >= station.min_elevation_deg

            if above and not in_window:
                # Window starts
                in_window = True
                window_start_idx = i
                max_el = el

            elif above and in_window:
                # Window continues
                max_el = max(max_el, el)

            elif not above and in_window:
                # Window ends
                in_window = False
                start_t = window_start_idx * step_seconds
                end_t = i * step_seconds
                duration = end_t - start_t

                # Only record windows longer than 1 step
                if duration > step_seconds:
                    all_windows.append(CommsWindow(
                        ground_station=station.name,
                        start_time=times[window_start_idx].utc_iso(),
                        end_time=times[i].utc_iso(),
                        duration_s=duration,
                        max_elevation_deg=round(max_el, 2),
                        start_t=start_t,
                        end_t=end_t,
                    ))
                max_el = -90.0

        # Handle window still open at end of simulation
        if in_window and window_start_idx is not None:
            start_t = window_start_idx * step_seconds
            end_t = (len(elevations) - 1) * step_seconds
            all_windows.append(CommsWindow(
                ground_station=station.name,
                start_time=times[window_start_idx].utc_iso(),
                end_time=times[-1].utc_iso(),
                duration_s=end_t - start_t,
                max_elevation_deg=round(max_el, 2),
                start_t=start_t,
                end_t=end_t,
            ))

    # Sort all windows by start time
    all_windows.sort(key=lambda w: w.start_t)

    log.debug(
        "Found %d comms window(s) across %d station(s)",
        len(all_windows), len(ground_stations)
    )
    for w in all_windows:
        log.debug(
            "  [%s] %s → %s (%.0fs, max el: %.1f°)",
            w.ground_station, w.start_time, w.end_time,
            w.duration_s, w.max_elevation_deg
        )

    return all_windows


def annotate_blackouts(
    telemetry_stream: list[TelemetryFrame],
    comms_windows: list[CommsWindow],
) -> list[TelemetryFrame]:
    """
    Annotate each telemetry frame with whether it falls inside
    or outside a comms window.

    Frames outside all comms windows are flagged as
    'comms_blackout: True' — these are the most critical frames
    because ground intervention is impossible.

    Args:
        telemetry_stream: list of TelemetryFrames
        comms_windows: list of CommsWindow objects

    Returns:
        Annotated telemetry stream with comms_blackout flags
    """
    from dataclasses import replace

    annotated = []
    for frame in telemetry_stream:
        in_window = any(
            w.start_t <= frame.t <= w.end_t
            for w in comms_windows
        )
        annotated.append(replace(
            frame,
            flags={
                **frame.flags,
                "comms_blackout": not in_window,
            }
        ))

    blackout_count = sum(1 for f in annotated if f.flags.get("comms_blackout"))
    log.warning(
        "%d/%d frames (%.0f%%) in comms blackout — no ground intervention possible",
        blackout_count,
        len(annotated),
        100 * blackout_count / len(annotated) if annotated else 0,
    )

    return annotated