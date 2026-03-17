# OrbitVal — INTERNALS.md

> The internal map of this codebase: files, what each owns,
> dependencies, and known gaps.
> Read this to understand how OrbitVal works from the inside.
> Entry point: [MAP.md](MAP.md)

---

## What OrbitVal is (one paragraph for AI context)

OrbitVal is a local-first Python package that stress-tests CubeSat autonomy
software before launch. Teams install it via pip, define their satellite in
a satellite.yaml file, and run named fault injection scenarios against their
onboard autonomy code — entirely on their own machine. No proprietary code
ever leaves their infrastructure. The output is an ORF-compliant JSON + PDF
report suitable for mission readiness reviews, launch provider documentation,
and insurance underwriting. The long-term goal is for the OrbitVal Report
Format (ORF) to become the de facto industry standard for CubeSat autonomy
validation — making OrbitVal usage a compliance checkbox, not a purchasing
decision.

---

## Business context (for AI reasoning about decisions)

- **Model:** Open core. Core framework is free and open source.
- **Free tier:** generic fault scenarios (RF interference, GPS dropout,
  power brownout, sensor noise). No vendor-specific knowledge required.
- **Paid tier:** hardware-specific fault scenario packs (reaction wheel
  bearing degradation, star tracker lost-in-space recovery, etc.).
- **University exemption:** perpetually free, verified by .edu email.
- **Long-term:** ORF Foundation (non-profit) governs the open standard.
  OrbitVal Inc (commercial) builds the best certified tooling around it.
  Modeled on OpenAPI Initiative + Linux Foundation + HL7/FHIR.
- **Trust moat:** local-first execution. "Your code never moves. Ever.
  Only your reports do, and only if you choose."

---

## Codebase map
```
orbitval/                        Python package root
├── __init__.py                  version + public export surface
├── cli.py                       CLI entrypoint (not yet built)
│
├── config/
│   ├── __init__.py
│   ├── scenario_schema.py       scenario config model + validation (not yet built)
│   └── hardware_3u_schema.py    ✓ BUILT — 3U CubeSat hardware config loader/validator
│
├── orbits/
│   ├── __init__.py
│   ├── tle.py                   ✓ BUILT — Celestrak TLE fetcher + cache + offline mode
│   ├── propagation.py           ✓ BUILT — orbit propagation via skyfield, ground track
│   └── comms_windows.py         not yet built — ground station visibility windows
│
├── faults/
│   ├── __init__.py
│   ├── base.py                  ✓ BUILT — TelemetryFrame dataclass + FaultScenario Protocol
│   ├── catalog.py               ✓ BUILT — fault registry, list_faults(), get_fault()
│   └── scenarios/
│       ├── __init__.py
│       ├── gps_dropout.py       ✓ BUILT — free fault: complete GPS signal loss
│       ├── power_brownout.py    ✓ BUILT — free fault: battery + solar power drop
│       └── sensor_noise.py      ✓ BUILT — free fault: amplified gaussian sensor noise
│
├── engine/
│   ├── __init__.py
│   ├── injection.py             ✓ BUILT — applies fault scenarios to telemetry stream
│   └── runner.py                not yet built — autonomy harness (wraps user code)
│
└── reporting/
    ├── __init__.py
    ├── json_report.py           ✓ BUILT — ORF-compliant JSON report + integrity hash
    └── pdf_report.py            ✓ BUILT — human-readable PDF for mission readiness reviews

docs-template/                   project documentation
├── MAP.md                       entry point, codebase at a glance, phases
├── ARCHITECTURE.md              ADRs, philosophy, ORF spec, entity structure
├── MANIFEST.md                  file map, data flow, ASCII component diagram
├── manifest.yaml                parseable connections for tools + AI
├── TEMPLATES.md                 contracts, satellite.yaml schema, FaultScenario interface
├── INTERNALS.md                 this file
├── ROADMAP.md                   7-phase company + product roadmap
├── TODO.md                      ordered task list
├── AUDIT.md                     phase readiness audit template
└── UPDATE.md                    when and how to update each doc

reports/                         generated output (gitignored)
├── orbitval_report.json         ORF-compliant machine-readable report
└── orbitval_report.pdf          human-readable mission readiness report

satellite.yaml                   example 3U CubeSat hardware config (user-defined)
test_orbit.py                    end-to-end integration test (dev only)
pyproject.toml                   package metadata + dependencies
```

---

## Module ownership table

| Module | File | Owns | Depends on |
|--------|------|------|------------|
| hardware_3u_schema | `orbitval/config/hardware_3u_schema.py` | loads + validates satellite.yaml, HardwareConfig dataclass | pyyaml |
| tle | `orbitval/orbits/tle.py` | Celestrak fetch, TLE cache (~/.orbitval/tle_cache), offline fallback, TLERecord dataclass | urllib, json, pathlib |
| propagation | `orbitval/orbits/propagation.py` | orbit propagation from TLE or params, GroundTrackPoint, PropagationResult | skyfield, astropy |
| base | `orbitval/faults/base.py` | TelemetryFrame dataclass, FaultScenario Protocol | dataclasses |
| catalog | `orbitval/faults/catalog.py` | FAULT_REGISTRY dict, list_faults(), get_fault() | all scenario modules |
| gps_dropout | `orbitval/faults/scenarios/gps_dropout.py` | GpsDropout fault class | base.TelemetryFrame |
| power_brownout | `orbitval/faults/scenarios/power_brownout.py` | PowerBrownout fault class | base.TelemetryFrame |
| sensor_noise | `orbitval/faults/scenarios/sensor_noise.py` | SensorNoise fault class | base.TelemetryFrame |
| injection | `orbitval/engine/injection.py` | run_injection(), InjectionEvent, fault trace | base, catalog |
| json_report | `orbitval/reporting/json_report.py` | generate_json_report(), ORF JSON, test_integrity_hash | hashlib, uuid, json |
| pdf_report | `orbitval/reporting/pdf_report.py` | generate_pdf_report(), mission readiness PDF | reportlab |

---

## Data flow (end to end)
```
satellite.yaml
      │
      ▼
hardware_3u_schema.py
  └─ HardwareConfig
      │
      │                    Celestrak (live) or cache
      │                           │
      │                           ▼
      │                        tle.py
      │                     └─ TLERecord
      │                           │
      │                           ▼
      │                    propagation.py
      │                  └─ PropagationResult
      │                    (ground_track points)
      │                           │
      │                           ▼
      │              build TelemetryFrame stream
      │              (one frame per time step)
      │                           │
      ├───────────────────────────┤
      │                           │
      ▼                           ▼
 fault config              telemetry stream
      │                           │
      ▼                           ▼
catalog.py ──► injection.py ──► injected telemetry
                └─ InjectionEvent trace
                           │
                           ▼
              json_report.py + pdf_report.py
              └─ orbitval_report.json
              └─ orbitval_report.pdf
                 (with test_integrity_hash)
```

---

## Key interfaces (copy these when building new modules)

### TelemetryFrame
```python
@dataclass
class TelemetryFrame:
    t: float                        # mission elapsed time in seconds
    gps_lat: float                  # degrees
    gps_lon: float                  # degrees
    gps_alt_km: float               # km
    gps_available: bool
    magnetometer_x: float           # microtesla
    magnetometer_y: float           # microtesla
    magnetometer_z: float           # microtesla
    star_tracker_available: bool
    battery_charge_wh: float
    solar_power_w: float
    reaction_wheel_speed_rpm: float
    flags: dict                     # arbitrary fault metadata
```

### FaultScenario interface
```python
class FaultScenario(Protocol):
    name: str
    description: str
    version: str

    def inject(self, telemetry: TelemetryFrame) -> TelemetryFrame:
        # Must return a NEW TelemetryFrame — never mutate input
        ...

    def is_active(self, t: float) -> bool:
        # Return True if fault applies at mission time t
        ...
```

### Adding a new fault scenario
```python
# 1. Create orbitval/faults/scenarios/your_fault.py
# 2. Implement name, description, version, inject(), is_active()
# 3. Register in orbitval/faults/catalog.py:
#    from orbitval.faults.scenarios.your_fault import YourFault
#    FAULT_REGISTRY["your_fault"] = YourFault
# 4. Update MANIFEST.md and manifest.yaml
```

### satellite.yaml schema (v1.0)
```yaml
schema_version: "1.0"       # required — for backwards compatibility
name: string                 # satellite name
form_factor: "3U"            # only 3U supported in v1
mass_kg: float               # positive
sensors:
  - type: string             # GPS | star_tracker | magnetometer |
                             # sun_sensor | gyroscope
    noise_sigma: float       # baseline noise std deviation, >= 0
actuators:
  - type: string             # reaction_wheel | magnetorquer | thruster
    max_torque_nm: float     # positive
power:
  battery_capacity_wh: float # positive
  solar_panel_area_m2: float # positive
```

### ORF report structure (v1.0)
```json
{
  "orbitval_version": "0.1.0",
  "orf_spec_version": "1.0",
  "schema_version": "1.0",
  "report_id": "UUID",
  "generated_at": "ISO 8601",
  "test_integrity_hash": "SHA-256 of all inputs + outputs",
  "mission_profile": {
    "orbit_type": "LEO",
    "altitude_band_km": float,
    "inclination_deg": float,
    "operational_lifetime_years": float
  },
  "regulatory_jurisdiction": "string",
  "applicable_standard": "string",
  "hardware_generation": "string",
  "form_factor": "3U",
  "satellite": { ... },
  "simulation": {
    "orbit_epoch": "ISO 8601",
    "duration_s": float,
    "seed": int
  },
  "scenarios_run": [
    {
      "name": "string",
      "version": "string",
      "result": "PASS | FAIL | SKIP",
      "duration_s": float,
      "seed": int,
      "autonomy_response": "string",
      "fault_trace": [ ... ]
    }
  ],
  "overall_result": "PASS | FAIL",
  "certification_eligible": boolean
}
```

---

## Dependencies

| Package | Version | Purpose |
|---------|---------|---------|
| skyfield | latest | TLE loading, orbit propagation, ground track |
| astropy | latest | time handling, unit safety |
| numpy | latest | numerical arrays |
| pyyaml | latest | satellite.yaml loading |
| reportlab | latest | PDF report generation |

---

## What is NOT built yet (known gaps)

| Gap | File | Priority |
|-----|------|----------|
| Scenario config schema | `orbitval/config/scenario_schema.py` | High |
| Comms windows calculator | `orbitval/orbits/comms_windows.py` | High |
| Autonomy harness (runner) | `orbitval/engine/runner.py` | High — needed to test real user code |
| CLI entrypoint | `orbitval/cli.py` | Medium |
| Eclipse period detection | `orbitval/orbits/propagation.py` | Medium |
| Additional fault scenarios | `orbitval/faults/scenarios/` | Medium |
| Regression runner | `orbitval/regression/` | Phase 2 |
| Cloud dashboard | `cloud-dashboard/` | Phase 3 |

---

## Architecture constraints (never violate these)

1. **No proprietary code leaves the machine.** The cloud layer, if added,
   accepts only test outputs and scenario configs. Never autonomy code.

2. **TelemetryFrame is immutable at injection.** FaultScenario.inject()
   must return a new TelemetryFrame using dataclasses.replace().
   Never mutate the input frame.

3. **All fault scenarios are seeded.** Reproducibility is non-negotiable
   for the ORF report. Every scenario that uses randomness must accept
   a seed parameter.

4. **test_integrity_hash is always the last field computed.** It hashes
   everything else in the report. Never include it in the pre-hash payload.

5. **3U only in v1.** The hardware model is constrained to 3U CubeSat.
   Any expansion requires a new ADR in ARCHITECTURE.md.

6. **skyfield + astropy for all orbital math.** Never roll custom
   propagation. See ADR-002.

7. **schema_version in every satellite.yaml.** Required for backwards
   compatibility as the spec evolves.

---

## How to continue building in a new AI conversation

Paste this file plus ARCHITECTURE.md into the conversation.
That gives the AI full context on:
- What exists and what doesn't
- The interfaces it must respect
- The constraints it must never violate
- Where the next work starts (known gaps table above)

The next things to build in order are:
1. `orbitval/engine/runner.py` — autonomy harness
2. `orbitval/orbits/comms_windows.py` — ground station visibility
3. `orbitval/config/scenario_schema.py` — scenario config validation
4. `orbitval/cli.py` — CLI entrypoint