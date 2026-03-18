"""
orbitval/cli.py

Command-line interface for OrbitVal.
Allows teams to run fault injection stress tests without
writing any Python.

Usage:
    orbitval run --config satellite.yaml --scenarios gps_dropout power_brownout
    orbitval list-faults
    orbitval validate --config satellite.yaml
"""

import argparse
import sys
from pathlib import Path


def cmd_list_faults(args):
    """List all available fault scenarios."""
    from orbitval.faults.catalog import list_faults
    faults = list_faults()
    print("\nAvailable fault scenarios:\n")
    for f in faults:
        tier = "FREE"
        print(f"  [{tier}] {f['name']} v{f['version']}")
        print(f"         {f['description']}")
        print()


def cmd_validate(args):
    """Validate a satellite.yaml config file."""
    from orbitval.config.hardware_3u_schema import (
        load_hardware_config, HardwareConfigError
    )
    try:
        hw = load_hardware_config(args.config)
        print(f"\n✓ Config valid: {args.config}")
        print(f"  Satellite:   {hw.name}")
        print(f"  Form factor: {hw.form_factor}")
        print(f"  Mass:        {hw.mass_kg} kg")
        print(f"  Sensors:     {[s.type for s in hw.sensors]}")
        print(f"  Actuators:   {[a.type for a in hw.actuators]}")
        print(f"  Battery:     {hw.power.battery_capacity_wh} Wh")
        print()
    except FileNotFoundError:
        print(f"\n✗ Config file not found: {args.config}")
        sys.exit(1)
    except HardwareConfigError as e:
        print(f"\n✗ Config invalid:\n{e}")
        sys.exit(1)


def cmd_run(args):
    """Run fault injection stress test."""
    from orbitval.logging import set_log_level
    from orbitval.engine.runner import TestRunner
    from orbitval.faults.base import TelemetryFrame
    from orbitval.orbits.comms_windows import GroundStation
    import math

    # Set log level from flags
    if args.verbose:
        set_log_level("DEBUG")
    elif args.quiet:
        set_log_level("WARNING")
    else:
        set_log_level("INFO")

    # Parse ground stations if provided
    ground_stations = []
    if args.ground_station:
        for gs in args.ground_station:
            parts = gs.split(",")
            if len(parts) < 3:
                print(
                    f"✗ Invalid ground station format: '{gs}'. "
                    f"Use: name,lat,lon or name,lat,lon,alt,min_el"
                )
                sys.exit(1)
            ground_stations.append(GroundStation(
                name=parts[0],
                lat_deg=float(parts[1]),
                lon_deg=float(parts[2]),
                alt_km=float(parts[3]) if len(parts) > 3 else 0.0,
                min_elevation_deg=float(parts[4]) if len(parts) > 4 else 10.0,
            ))

    # Default autonomy stub
    class DefaultAutonomy:
        def __init__(self):
            self._mag_history = []

        def process(self, telemetry: TelemetryFrame) -> str:
            if not telemetry.gps_available:
                return "failover_to_dead_reckoning"
            if telemetry.battery_charge_wh < 5.0:
                return "safe_mode"
            if telemetry.solar_power_w < 1.0:
                return "reduced_ops"
            mag = math.sqrt(
                telemetry.magnetometer_x ** 2 +
                telemetry.magnetometer_y ** 2 +
                telemetry.magnetometer_z ** 2
            )
            self._mag_history.append(mag)
            if len(self._mag_history) >= 3:
                recent = self._mag_history[-3:]
                if max(recent) - min(recent) > 0.5:
                    return "reduced_ops"
            return "nominal"

        def reset(self):
            self._mag_history = []

    # Load autonomy module if provided
    autonomy = DefaultAutonomy()
    if args.autonomy:
        try:
            import importlib.util
            spec = importlib.util.spec_from_file_location(
                "user_autonomy", args.autonomy
            )
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            autonomy = module.Autonomy()
        except Exception as e:
            print(f"✗ Failed to load autonomy module: {e}")
            sys.exit(1)

    # Build runner
    runner = TestRunner(
        config=args.config,
        autonomy=autonomy,
        tle_name=args.tle_name,
        duration_hours=args.duration,
        step_seconds=args.step,
        seed=args.seed,
        ground_stations=ground_stations,
    )

    # Run scenarios
    scenarios = args.scenarios or ["gps_dropout", "power_brownout", "sensor_noise"]

    report = runner.run(
        scenarios=scenarios,
        output_dir=args.output,
        mission_profile={
            "orbit_type": args.orbit_type,
            "altitude_band_km": None,
            "inclination_deg": None,
            "operational_lifetime_years": None,
        },
    )

    # Print summary
    result = report["overall_result"]
    cert = report["certification_eligible"]
    symbol = "✓" if result == "PASS" else "✗"
    print(f"\n{'='*50}")
    print(f"{symbol} Overall result:         {result}")
    print(f"  Certification eligible: {cert}")
    print(f"  Integrity hash:         {report['test_integrity_hash'][:32]}...")
    print(f"  Reports written to:     {args.output}")
    print(f"{'='*50}\n")

    if result == "FAIL":
        sys.exit(1)

def main():
    parser = argparse.ArgumentParser(
        prog="orbitval",
        description="OrbitVal — CubeSat autonomy stress testing framework",
    )
    parser.add_argument(
        "--version", action="version", version="OrbitVal 0.1.0"
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    # ── orbitval list-faults ──────────────────────────────────
    subparsers.add_parser(
        "list-faults",
        help="List all available fault scenarios"
    ).set_defaults(func=cmd_list_faults)

    # ── orbitval validate ─────────────────────────────────────
    validate_parser = subparsers.add_parser(
        "validate",
        help="Validate a satellite.yaml config file"
    )
    validate_parser.add_argument(
        "--config", default="satellite.yaml",
        help="Path to satellite.yaml (default: satellite.yaml)"
    )
    validate_parser.set_defaults(func=cmd_validate)

    # ── orbitval run ──────────────────────────────────────────
    run_parser = subparsers.add_parser(
        "run",
        help="Run fault injection stress test"
    )
    run_parser.add_argument(
        "--verbose", action="store_true",
        help="Show debug logs"
    )
    run_parser.add_argument(
        "--quiet", action="store_true",
        help="Show warnings and errors only"
    )
    run_parser.add_argument(
        "--config", default="satellite.yaml",
        help="Path to satellite.yaml (default: satellite.yaml)"
    )
    run_parser.add_argument(
        "--scenarios", nargs="+",
        help="Fault scenarios to run (default: all free scenarios)"
    )
    run_parser.add_argument(
        "--autonomy",
        help="Path to autonomy module .py file (optional)"
    )
    run_parser.add_argument(
        "--tle-name", default="ISS (ZARYA)",
        dest="tle_name",
        help="Satellite name for TLE fetch (default: ISS (ZARYA))"
    )
    run_parser.add_argument(
        "--duration", type=float, default=1.0,
        help="Simulation duration in hours (default: 1.0)"
    )
    run_parser.add_argument(
        "--step", type=float, default=60.0,
        help="Telemetry time step in seconds (default: 60.0)"
    )
    run_parser.add_argument(
        "--seed", type=int, default=42,
        help="Random seed for reproducibility (default: 42)"
    )
    run_parser.add_argument(
        "--output", default="reports/",
        help="Output directory for reports (default: reports/)"
    )
    run_parser.add_argument(
        "--ground-station", nargs="+", dest="ground_station",
        metavar="name,lat,lon[,alt,min_el]",
        help="Ground station(s) e.g. 'Rutgers,40.5,-74.4'"
    )
    run_parser.add_argument(
        "--orbit-type", default="LEO", dest="orbit_type",
        help="Orbit type for report (default: LEO)"
    )
    run_parser.set_defaults(func=cmd_run)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()