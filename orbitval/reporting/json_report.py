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
from orbitval.logging import get_logger, get_run_events
log = get_logger("report")


ORF_SPEC_VERSION = "1.0"
ORBITVAL_VERSION = "0.1.0"


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
    return payload