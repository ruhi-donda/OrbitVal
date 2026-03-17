from orbitval.orbits.tle import fetch_tle
from orbitval.orbits.propagation import propagate_from_tle
from orbitval.config.hardware_3u_schema import load_hardware_config
from orbitval.faults.catalog import list_faults, get_fault
from orbitval.faults.base import TelemetryFrame
from orbitval.engine.injection import run_injection
from orbitval.reporting.json_report import generate_json_report
from orbitval.reporting.pdf_report import generate_pdf_report

# ── Orbit ────────────────────────────────────────────────────
print("Fetching live TLE from Celestrak...")
tle = fetch_tle("ISS (ZARYA)")
print(f"Fetched: {tle.name}\n")

result = propagate_from_tle(
    tle_line1=tle.line1,
    tle_line2=tle.line2,
    duration_hours=1.0,
    step_seconds=60.0,
)

# ── Hardware ─────────────────────────────────────────────────
print("Loading hardware config...")
hw = load_hardware_config("satellite.yaml")
print(f"Satellite: {hw.name} | {hw.form_factor} | {hw.mass_kg}kg\n")

# ── Telemetry stream ─────────────────────────────────────────
telemetry_stream = []
for i, point in enumerate(result.ground_track):
    telemetry_stream.append(TelemetryFrame(
        t=float(i * 60),
        gps_lat=point.lat_deg,
        gps_lon=point.lon_deg,
        gps_alt_km=point.alt_km,
        gps_available=True,
        magnetometer_x=25.0,
        magnetometer_y=-10.0,
        magnetometer_z=40.0,
        star_tracker_available=True,
        battery_charge_wh=hw.power.battery_capacity_wh,
        solar_power_w=5.0,
        reaction_wheel_speed_rpm=100.0,
    ))

# ── Fault injection ───────────────────────────────────────────
print("Running fault injection...")
scenarios = [
    get_fault("gps_dropout", t_start=120.0, duration_s=180.0),
    get_fault("power_brownout", t_start=300.0, duration_s=120.0),
    get_fault("sensor_noise", t_start=0.0, duration_s=600.0, seed=42),
]

injected, trace = run_injection(telemetry_stream, scenarios)
print(f"Injection trace: {len(trace)} events\n")

# ── Scenario results (placeholder pass/fail logic) ────────────
scenarios_run = [
    {
        "name": "gps_dropout",
        "version": "1.0.0",
        "result": "FAIL",
        "duration_s": 180.0,
        "seed": 42,
        "autonomy_response": "no_failover_detected",
        "fault_trace": [e.__dict__ for e in trace if e.fault_name == "gps_dropout"],
    },
    {
        "name": "power_brownout",
        "version": "1.0.0",
        "result": "PASS",
        "duration_s": 120.0,
        "seed": 42,
        "autonomy_response": "safe_mode_triggered",
        "fault_trace": [e.__dict__ for e in trace if e.fault_name == "power_brownout"],
    },
    {
        "name": "sensor_noise",
        "version": "1.0.0",
        "result": "PASS",
        "duration_s": 600.0,
        "seed": 42,
        "autonomy_response": "nominal_operation",
        "fault_trace": [e.__dict__ for e in trace if e.fault_name == "sensor_noise"],
    },
]

# ── Reports ───────────────────────────────────────────────────
print("Generating reports...")
report = generate_json_report(
    satellite_name=hw.name,
    hardware=hw,
    scenarios_run=scenarios_run,
    injection_trace=trace,
    orbit_epoch=result.epoch,
    duration_s=result.duration_s,
    seed=42,
    output_path="reports/orbitval_report.json",
    mission_profile={
        "orbit_type": "LEO",
        "altitude_band_km": 426.0,
        "inclination_deg": 51.6,
        "operational_lifetime_years": 2.0,
    },
)

generate_pdf_report(
    report=report,
    output_path="reports/orbitval_report.pdf",
)

print(f"\n{'='*50}")
print(f"Overall result:        {report['overall_result']}")
print(f"Certification eligible: {report['certification_eligible']}")
print(f"Integrity hash:        {report['test_integrity_hash'][:32]}...")
print(f"{'='*50}")
print("\n✓ MVP pipeline complete. Check reports/ folder.")