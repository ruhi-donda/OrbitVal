from orbitval.engine.runner import TestRunner
from orbitval.faults.base import TelemetryFrame
from orbitval.orbits.comms_windows import GroundStation


# ── Define autonomy code (this is what a CubeSat team writes) ──
class MyCubeSatAutonomy:
    """
    Example autonomy code for a 3U CubeSat.
    Detects faults from raw sensor data only —
    no access to OrbitVal internal flags.
    """

    def __init__(self):
        self._mag_history = []

    def process(self, telemetry: TelemetryFrame) -> str:
        # GPS dropout — no flags, detect from gps_available field
        # (this is a real hardware signal, not an OrbitVal flag)
        if not telemetry.gps_available:
            return "failover_to_dead_reckoning"

        # Power brownout — detect from actual battery level
        if telemetry.battery_charge_wh < 5.0:
            return "safe_mode"

        # Low solar — detect from actual solar power reading
        if telemetry.solar_power_w < 1.0:
            return "reduced_ops"

        # Sensor noise — detect from magnetometer variance over time
        mag = (
            telemetry.magnetometer_x ** 2 +
            telemetry.magnetometer_y ** 2 +
            telemetry.magnetometer_z ** 2
        ) ** 0.5
        self._mag_history.append(mag)

        if len(self._mag_history) >= 3:
            recent = self._mag_history[-3:]
            variance = max(recent) - min(recent)
            if variance > 0.5:
                return "reduced_ops"

        

  
        return "nominal"

    def reset(self):
        self._mag_history = []

# ── Run OrbitVal ───────────────────────────────────────────────
runner = TestRunner(
    config="satellite.yaml",
    autonomy=MyCubeSatAutonomy(),
    tle_name="ISS (ZARYA)",
    duration_hours=1.0,
    step_seconds=60.0,
    seed=42,
    ground_stations=[
        GroundStation(
            name="Rutgers NJ",
            lat_deg=40.5008,
            lon_deg=-74.4474,
            alt_km=0.05,
            min_elevation_deg=10.0,
        ),
    ],
)

report = runner.run(
    scenarios=["gps_dropout", "power_brownout", "sensor_noise"],
    scenario_kwargs={
        "gps_dropout": {"t_start": 120.0, "duration_s": 180.0},
        "power_brownout": {
            "t_start": 300.0,
            "duration_s": 120.0,
            "battery_drain_factor": 0.1,
        },
        "sensor_noise": {"t_start": 0.0, "duration_s": 600.0, "seed": 42},
    },
    mission_profile={
        "orbit_type": "LEO",
        "altitude_band_km": 426.0,
        "inclination_deg": 51.6,
        "operational_lifetime_years": 2.0,
    },
    output_dir="reports/",
)

print(f"\n{'='*50}")
print(f"Overall result:         {report['overall_result']}")
print(f"Certification eligible: {report['certification_eligible']}")
print(f"Integrity hash:         {report['test_integrity_hash'][:32]}...")
print(f"{'='*50}")