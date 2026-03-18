# OrbitVal — INTERNALS.md

> The internal map of this codebase: files, what each owns,
> dependencies, and known gaps.
> Read this to understand how OrbitVal works from the inside.
> Entry point: [MAP.md](MAP.md)
> Last updated: 2026-03-17 — v0.1 complete

---

## What OrbitVal is (one paragraph for AI context)

OrbitVal is a local-first Python package that stress-tests CubeSat autonomy
software before launch. Teams install it via pip, define their satellite in
a satellite.yaml file, and run named fault injection scenarios against their
onboard autonomy code — entirely on their own machine. No proprietary code
ever leaves their infrastructure. The output is an ORF-compliant JSON + PDF
+ log report suitable for mission readiness reviews, launch provider
documentation, and insurance underwriting. The long-term goal is for the
OrbitVal Report Format (ORF) to become the de facto industry standard for
CubeSat autonomy validation — making OrbitVal usage a compliance checkbox,
not a purchasing decision.

---

## Business context (for AI reasoning about decisions)

- **Model:** Open core. Core framework is free and open source.
- **Free tier:** generic fault scenarios (GPS dropout, power brownout,
  sensor noise). No vendor-specific knowledge required.
- **Paid tier:** hardware-specific fault scenario packs (reaction wheel
  bearing degradation, star tracker lost-in-space recovery, etc.).
- **Boundary rule:** if a fault requires vendor-specific behavior or specs
  it is paid. If it can be modeled generically it is free.
- **University exemption:** perpetually free, verified by .edu email.
- **Long-term:** ORF Foundation (non-profit) governs the open standard.
  OrbitVal Inc (commercial) builds the best certified tooling around it.
  Modeled on OpenAPI Initiative + Linux Foundation + HL7/FHIR.
- **Trust moat:** local-first execution. "Your code never moves. Ever.
  Only your reports do, and only if you choose."
- **Core thesis:** OrbitVal is a standardization company. The fault
  scenario library + ORF spec are the moat, not the framework code.

---

## Codebase map
```
orbitval/                        Python package root
├── __init__.py                  version + public export surface
├── cli.py                       ✓ BUILT — full CLI (run, validate, list-faults)
├── logging.py                   ✓ BUILT — structured logging (terminal + file + report)
│
├── config/
│   ├── __init__.py
│   ├── scenario_schema.py       NOT YET BUILT — scenario config model + validation
│   └── hardware_3u_schema.py    ✓ BUILT — 3U CubeSat hardware config loader/validator
│
├── orbits/
│   ├── __init__.py
│   ├── tle.py                   ✓ BUILT — Celestrak TLE fetcher + cache + offline mode
│   ├── propagation.py           ✓ BUILT — orbit propagation via skyfield (TLE + params)
│   └── comms_windows.py         ✓ BUILT — ground station visibility windows + blackout annotation
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
│   └── runner.py                ✓ BUILT — autonomy harness, pass/fail eval, report gen
│
└── reporting/
    ├── __init__.py
    ├── json_report.py           ✓ BUILT — ORF-compliant JSON + integrity hash + run_log
    └── pdf_report.py            ✓ BUILT — human-readable PDF for mission readiness reviews

docs-template/                   project documentation
├── MAP.md                       entry point, codebase at a glance, phases
├── ARCHITECTURE.md              ADRs, philosophy, ORF spec, entity structure, strategic thesis
├── MANIFEST.md                  file map, data flow, ASCII component diagram
├── manifest.yaml                parseable connections for tools + AI
├── TEMPLATES.md                 contracts, satellite.yaml schema, FaultScenario interface
├── INTERNALS.md                 this file
├── ROADMAP.md                   7-phase company + product roadmap
├── TODO.md                      ordered task list
├── AUDIT.md                     phase readiness audit template
└── UPDATE.md                    when and how to update each doc

reports/                         generated output (gitignored)
├── *.json                       ORF-compliant machine-readable report
├── *.pdf                        human-readable mission readiness report
└── *.log                        full internal audit trail for each run

satellite.yaml                   example 3U CubeSat hardware config (user-defined)
test_orbit.py                    end-to-end integration test (dev only)
pyproject.toml                   package metadata + dependencies
README.md                        public-facing documentation
```

---

## Module ownership table

| Module | File | Owns | Depends on |
|--------|------|------|------------|
| logging | `orbitval/logging.py` | get_logger(), set_log_level(), init_run_log(), get_run_events(), OrbitValLogger, run event buffer | logging, pathlib |
| hardware_3u_schema | `orbitval/config/hardware_3u_schema.py` | load_hardware_config(), HardwareConfig, SensorConfig, ActuatorConfig, PowerConfig, HardwareConfigError | pyyaml |
| tle | `orbitval/orbits/tle.py` | fetch_tle(), tle_from_strings(), TLERecord, TLE cache (~/.orbitval/tle_cache), offline fallback | urllib, json, pathlib, logging |
| propagation | `orbitval/orbits/propagation.py` | propagate_from_tle(), propagate_from_params(), GroundTrackPoint, PropagationResult | skyfield, astropy, logging |
| comms_windows | `orbitval/orbits/comms_windows.py` | compute_comms_windows(), annotate_blackouts(), GroundStation, CommsWindow | skyfield, logging |
| base | `orbitval/faults/base.py` | TelemetryFrame dataclass, FaultScenario Protocol | dataclasses |
| catalog | `orbitval/faults/catalog.py` | FAULT_REGISTRY dict, list_faults(), get_fault() | all scenario modules |
| gps_dropout | `orbitval/faults/scenarios/gps_dropout.py` | GpsDropout fault class | base.TelemetryFrame |
| power_brownout | `orbitval/faults/scenarios/power_brownout.py` | PowerBrownout fault class | base.TelemetryFrame |
| sensor_noise | `orbitval/faults/scenarios/sensor_noise.py` | SensorNoise fault class | base.TelemetryFrame |
| injection | `orbitval/engine/injection.py` | run_injection(), InjectionEvent, fault trace | base, catalog, logging |
| runner | `orbitval/engine/runner.py` | TestRunner, AutonomyInterface, ScenarioResult, _evaluate_scenario(), three orbit input modes | all modules, logging |
| json_report | `orbitval/reporting/json_report.py` | generate_json_report(), ORF JSON, test_integrity_hash, run_log embed | hashlib, uuid, json, logging |
| pdf_report | `orbitval/reporting/pdf_report.py` | generate_pdf_report(), mission readiness PDF | reportlab, logging |
| cli | `orbitval/cli.py` | main(), cmd_run(), cmd_validate(), cmd_list_faults(), --verbose/--quiet flags | runner, logging |

---

## Data flow (end to end)
```
satellite.yaml
      │
      ▼
hardware_3u_schema.py
  └─ HardwareConfig
      │
      │         THREE ORBIT INPUT MODES
      │         ┌──────────────────────────────────────┐
      │         │ Mode 1: fetch live TLE from Celestrak │
      │         │ Mode 2: manual TLE strings provided   │
      │         │ Mode 3: pre-launch (alt + inc only)   │
      │         └──────────────────────────────────────┘
      │                           │
      │                           ▼
      │                    propagation.py
      │                  └─ PropagationResult
      │                    (ground_track points)
      │                           │
      │                    comms_windows.py (optional)
      │                  └─ CommsWindow list
      │                  └─ blackout annotation
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
                    runner.py strips flags
                    (autonomy code sees clean
                     sensor data only — no
                     OrbitVal internal metadata)
                           │
                           ▼
                    autonomy.process(frame)
                    └─ response string per frame
                           │
                           ▼
                    _evaluate_scenario()
                    └─ ScenarioResult (PASS/FAIL/SKIP)
                           │
                           ▼
              json_report.py + pdf_report.py
              └─ satellite_2026-03-17_05-09-59.json
              └─ satellite_2026-03-17_05-09-59.pdf
              └─ satellite_2026-03-17_05-09-59.log
                 (with test_integrity_hash + run_log)
```

---

## Logging system

OrbitVal uses a structured logging system with three output destinations:

| Destination | Format | When |
|-------------|--------|------|
| Terminal | colored, timestamped | always |
| `.log` file | plain text, timestamped | every run, alongside reports |
| `run_log` in JSON | structured events | embedded in ORF report |

**Log levels:**

| Level | Audience | Example |
|-------|----------|---------|
| DEBUG | Developer (you) | `Fault active at t=60s — modified: gps_lat` |
| INFO | User (CubeSat team) | `Running scenario: gps_dropout` |
| WARNING | User | `57/60 frames in comms blackout` |
| ERROR | User | `FAIL — sensor_noise: no response detected` |

**CLI verbosity flags:**
```bash
orbitval run ...            # INFO — normal output
orbitval run ... --verbose  # DEBUG — full internal state
orbitval run ... --quiet    # WARNING+ — errors only
```

**Usage in any module:**
```python
from orbitval.logging import get_logger
log = get_logger("module_name")

log.info("Normal progress message")
log.warning("Something recoverable happened")
log.error("Something failed")
log.debug("Internal state detail — hidden by default")
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
    flags: dict                     # internal only — stripped before autonomy sees it
```

### FaultScenario interface
```python
class FaultScenario(Protocol):
    name: str
    description: str
    version: str

    def inject(self, telemetry: TelemetryFrame) -> TelemetryFrame:
        # Must return a NEW TelemetryFrame — never mutate input
        # Use dataclasses.replace()
        ...

    def is_active(self, t: float) -> bool:
        # Return True if fault applies at mission time t
        ...
```

### AutonomyInterface
```python
class AutonomyInterface(Protocol):
    def process(self, telemetry: TelemetryFrame) -> str:
        # Receives CLEAN telemetry — flags are stripped
        # Must detect faults from raw sensor data only
        # Return: "nominal", "safe_mode", "failover",
        #         "failover_to_dead_reckoning",
        #         "emergency_shutdown", "reduced_ops"
        ...

    def reset(self) -> None:
        # Called between scenarios to reset internal state
        ...
```

### Adding a new fault scenario
```python
# 1. Create orbitval/faults/scenarios/your_fault.py
# 2. Implement name, description, version, inject(), is_active()
# 3. Register in orbitval/faults/catalog.py:
#    from orbitval.faults.scenarios.your_fault import YourFault
#    FAULT_REGISTRY["your_fault"] = YourFault
# 4. Add log calls using get_logger("your_fault_name")
# 5. Update MANIFEST.md and manifest.yaml
# 6. Update INTERNALS.md module ownership table
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
      "fault_trace": [ ... ],
      "failure_reason": "string | null"
    }
  ],
  "overall_result": "PASS | FAIL",
  "certification_eligible": boolean,
  "injection_trace": [ ... ],
  "run_log": [
    {
      "timestamp": "ISO 8601",
      "level": "INFO | WARNING | ERROR | DEBUG",
      "module": "string",
      "msg": "string"
    }
  ]
}
```

---

## CLI reference
```
orbitval list-faults
  List all available fault scenarios with descriptions

orbitval validate --config <path>
  Validate a satellite.yaml config file

orbitval run
  --config <path>           satellite.yaml path (default: satellite.yaml)
  --scenarios <names>       fault scenarios to run
  --autonomy <path>         user autonomy module .py file
  --tle-name <name>         satellite name for Celestrak fetch
  --orbit-alt <km>          orbital altitude — pre-launch mode (no TLE)
  --orbit-inc <deg>         orbital inclination — pre-launch mode (no TLE)
  --duration <hours>        simulation duration (default: 1.0)
  --step <seconds>          telemetry time step (default: 60.0)
  --seed <int>              random seed for reproducibility (default: 42)
  --output <dir>            report output directory (default: reports/)
  --ground-station <spec>   name,lat,lon[,alt,min_el]
  --orbit-type <string>     orbit type for report (default: LEO)
  --verbose                 show DEBUG logs
  --quiet                   show WARNING+ only
```

---

## Dependencies

| Package | Version | Purpose |
|---------|---------|---------|
| skyfield | latest | TLE loading, orbit propagation, ground track, comms windows |
| astropy | latest | time handling, coordinate frames |
| numpy | latest | numerical arrays |
| pyyaml | latest | satellite.yaml loading |
| reportlab | latest | PDF report generation |

---

## What is NOT built yet (known gaps)

| Gap | File | Priority | Notes |
|-----|------|----------|-------|
| Scenario config schema | `orbitval/config/scenario_schema.py` | High | Lets users define scenarios in YAML instead of CLI flags |
| Eclipse period detection | `orbitval/orbits/propagation.py` | Medium | Stub exists, needs implementation |
| Comms windows in PDF | `orbitval/reporting/pdf_report.py` | Medium | Currently JSON only |
| Run log in PDF | `orbitval/reporting/pdf_report.py` | Medium | Currently JSON only |
| Summary warning block | `orbitval/engine/runner.py` | Medium | Surface warnings at end of run |
| Additional fault scenarios | `orbitval/faults/scenarios/` | Medium | Comms blackout, star tracker failure |
| Regression runner | `orbitval/regression/` | Phase 2 | Batch runs, result diffing |
| Cloud dashboard | `cloud-dashboard/` | Phase 3 | React + FastAPI, outputs only |
| ORF spec as standalone doc | `orbitval.com` | High | Publish ORF v1.0 as open standard |

---

## Architecture constraints (never violate these)

1. **No proprietary code leaves the machine.** The cloud layer, if added,
   accepts only test outputs and scenario configs. Never autonomy code.

2. **TelemetryFrame is immutable at injection.** FaultScenario.inject()
   must return a new TelemetryFrame using dataclasses.replace().
   Never mutate the input frame.

3. **Flags are stripped before autonomy code sees telemetry.**
   runner.py calls replace(frame, flags={}) before autonomy.process().
   Autonomy code must detect faults from raw sensor data only.
   This is ADR-007 — never revert this.

4. **All fault scenarios that use randomness must accept a seed.**
   Reproducibility is non-negotiable for the ORF report.

5. **test_integrity_hash is always the last field computed.**
   It hashes everything else in the report payload.
   Never include it in the pre-hash payload.

6. **3U only in v1.** The hardware model is constrained to 3U CubeSat.
   Any expansion requires a new ADR in ARCHITECTURE.md.

7. **skyfield + astropy for all orbital math.** Never roll custom
   propagation. See ADR-002.

8. **schema_version in every satellite.yaml.** Required for backwards
   compatibility as the spec evolves.

9. **Use get_logger() for all output.** Never use print() in any module.
   print() is only acceptable in cli.py for the final summary block.

---

## How to continue building in a new AI conversation

Paste this file plus ARCHITECTURE.md into the conversation.
That gives the AI full context on:
- What exists and what doesn't
- The interfaces it must respect
- The constraints it must never violate
- Where the next work starts (known gaps table above)

**Current version:** v0.1.0 — MVP complete
**GitHub:** https://github.com/ruhi-donda/OrbitVal

**Recommended next build priorities:**
1. `orbitval/config/scenario_schema.py` — scenario config validation
2. Eclipse period detection in `propagation.py`
3. Comms windows + run log in PDF report
4. Additional fault scenarios (comms blackout, star tracker failure)
5. Summary warning block in runner.py