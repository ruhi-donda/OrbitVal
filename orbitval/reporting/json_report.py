"""
orbitval/reporting/json_report.py

Produces the OrbitVal Report Format (ORF) JSON output.
This is the machine-readable artifact for tooling integration.

Every field in this report is defined in ARCHITECTURE.md
under "ORF Spec — Report Format Fields".

The test_integrity_hash makes this report a verifiable
attestation — it cannot be modified after generation
without the hash becoming invalid.
"""

import json
import hashlib
import uuid
from datetime import datetime
from pathlib import Path
from orbitval.faults.base import TelemetryFrame
from orbitval.engine.injection import InjectionEvent
from orbitval.config.hardware_3u_schema import HardwareConfig
from orbitval.registry import append_entry
from orbitval.logging import get_logger, get_run_events
log = get_logger("report")


ORF_SPEC_VERSION = "1.0"
ORBITVAL_VERSION = "1.1.0"

# Required top-level fields and expected types, per ARCHITECTURE.md
# "ORF Spec — Report Format Fields / Required fields".
ORF_REQUIRED_FIELDS: dict[str, type] = {
    "orbitval_version": str,
    "orf_spec_version": str,
    "schema_version": str,
    "report_id": str,
    "generated_at": str,
    "test_integrity_hash": str,
    "mission_profile": dict,
    "regulatory_jurisdiction": str,
    "applicable_standard": str,
    "hardware_generation": str,
    "form_factor": str,
    "scenarios_run": list,
    "overall_result": str,
    "certification_eligible": bool,
}


def validate_orf_schema(report: dict) -> list[str]:
    """
    Check a parsed report against the ORF required fields.

    Structure only — content integrity is the hash's job. Returns a
    list of problems; empty means the document is structurally a
    valid ORF report.
    """
    problems = []
    for field, expected_type in ORF_REQUIRED_FIELDS.items():
        if field not in report:
            problems.append(f"missing required field: {field}")
        elif not isinstance(report[field], expected_type):
            problems.append(
                f"field '{field}' should be {expected_type.__name__}, "
                f"got {type(report[field]).__name__}"
            )
    return problems


def _compute_integrity_hash(payload: dict) -> str:
    """
    Compute SHA-256 hash of the report payload.
    This is the test_integrity_hash field in the ORF spec.
    Transforms the report from a document into a
    verifiable attestation.
    """
    canonical = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode()).hexdigest()


def generate_json_report(
    satellite_name: str,
    hardware: HardwareConfig,
    scenarios_run: list[dict],
    injection_trace: list[InjectionEvent],
    orbit_epoch: str,
    duration_s: float,
    seed: int,
    output_path: str | Path,
    mission_profile: dict | None = None,
    comms_windows: list | None = None,
    eclipse_periods: list | None = None,
) -> dict:
    """
    Generate an ORF-compliant JSON report.

    Args:
        satellite_name: name of the satellite under test
        hardware: validated HardwareConfig
        scenarios_run: list of dicts with name, result, duration_s
        injection_trace: list of InjectionEvents from injection engine
        orbit_epoch: ISO 8601 epoch of the propagated orbit
        duration_s: total simulation duration in seconds
        seed: random seed used for reproducibility
        output_path: where to write the JSON file
        mission_profile: optional mission context dict
        comms_windows: list of CommsWindow objects (or dicts) from the
            orbit engine; empty list when no ground stations were provided
            or when running in pre-launch mode without a real TLE

    Returns:
        The report dict (also written to output_path)
    """
    # Determine overall result
    any_fail = any(s.get("result") == "FAIL" for s in scenarios_run)
    overall_result = "FAIL" if any_fail else "PASS"
    certification_eligible = not any_fail

    # Build the core payload (everything that gets hashed)
    payload = {
        "orbitval_version": ORBITVAL_VERSION,
        "orf_spec_version": ORF_SPEC_VERSION,
        "schema_version": "1.0",
        "report_id": str(uuid.uuid4()),
        "generated_at": datetime.utcnow().isoformat() + "Z",

        # Mission context — self-describing for insurers/launch providers
        "mission_profile": mission_profile or {
            "orbit_type": "LEO",
            "altitude_band_km": None,
            "inclination_deg": None,
            "operational_lifetime_years": None,
        },
        "regulatory_jurisdiction": "none declared",
        "applicable_standard": "none declared",
        "hardware_generation": "COTS",
        "form_factor": hardware.form_factor,

        # Satellite under test
        "satellite": {
            "name": satellite_name,
            "mass_kg": hardware.mass_kg,
            "sensors": [
                {"type": s.type, "noise_sigma": s.noise_sigma}
                for s in hardware.sensors
            ],
            "actuators": [
                {"type": a.type, "max_torque_nm": a.max_torque_nm}
                for a in hardware.actuators
            ],
            "power": {
                "battery_capacity_wh": hardware.power.battery_capacity_wh,
                "solar_panel_area_m2": hardware.power.solar_panel_area_m2,
            },
        },

        # Simulation parameters
        "simulation": {
            "orbit_epoch": orbit_epoch,
            "duration_s": duration_s,
            "seed": seed,
        },

        # Test results
        "scenarios_run": scenarios_run,
        "overall_result": overall_result,
        "certification_eligible": certification_eligible,

        # Comms windows — ground station visibility intervals
        # Empty list when no ground stations were provided or in pre-launch mode.
        "comms_windows": [
            w if isinstance(w, dict) else {
                "ground_station": w.ground_station,
                "start_time": w.start_time,
                "end_time": w.end_time,
                "duration_s": w.duration_s,
                "max_elevation_deg": w.max_elevation_deg,
                "start_t": w.start_t,
                "end_t": w.end_t,
            }
            for w in (comms_windows or [])
        ],

        # Eclipse periods — umbra/penumbra intervals from shadow geometry.
        # Empty when the orbit never crosses Earth's shadow in the window.
        "eclipse_periods": eclipse_periods or [],

        # Injection trace — full audit trail
        "injection_trace": [
            event if isinstance(event, dict) else {
                "t": event.t,
                "fault_name": event.fault_name,
                "fields_modified": event.fields_modified,
            }
            for event in injection_trace
        ],

        # Run log — embedded audit trail of every internal decision
        # Makes the report self-documenting for insurers and launch providers
        "run_log": get_run_events(),
    }

    # Compute integrity hash — this is what makes it a verifiable attestation
    integrity_hash = _compute_integrity_hash(payload)
    payload["test_integrity_hash"] = integrity_hash

    # Write to disk
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, default=str))

    log.info("JSON report written: %s", output)
    log.info("Integrity hash: %s...", integrity_hash[:16])

    # Register the hash in the local append-only registry so the
    # report's provenance can be checked later (verify-report).
    entry = append_entry(
        report_hash=integrity_hash,
        satellite_id=satellite_name,
    )
    log.info(
        "Hash registered in append-only registry (prev: %s...)",
        entry["prev_entry_hash"][:16],
    )
    return payload