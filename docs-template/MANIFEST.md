# OrbitVal — Manifest

> The WHAT and WHERE of this codebase.
> Every file that matters is linked here.
> Update this file whenever a new file is added or a connection changes.
> Entry point: [MAP.md](MAP.md).
>
> **Connections in parseable form:** The same wiring is kept in [manifest.yaml](manifest.yaml). Keep MANIFEST.md and manifest.yaml in sync when connections change.

---

## Entry point

| File | Role |
|------|------|
| `orbitval/__init__.py` | Package entry; version/export surface |
| `orbitval/cli.py` | CLI entrypoint for running scenarios, fault packs, and generating reports |

---

## Package modules

### Config and schemas
| File | Owns |
|------|------|
| `orbitval/config/scenario_schema.py` | Scenario config model + validation (orbit source/params, ground station, duration, sampling rate) |
| `orbitval/config/hardware_3u_schema.py` | 3U CubeSat hardware config model (sensors, actuators, power budget) |

### Orbital mechanics
| File | Owns |
|------|------|
| `orbitval/orbits/tle.py` | Celestrak TLE fetch + parse + caching; offline mode support |
| `orbitval/orbits/propagation.py` | Propagate orbit from TLE/params using poliastro + astropy; produce ephemeris + ground track |
| `orbitval/orbits/comms_windows.py` | Compute ground station visibility windows from propagated states |

### Fault injection and execution
| File | Owns |
|------|------|
| `orbitval/faults/catalog.py` | Registry of named fault scenarios; pack discovery/versioning |
| `orbitval/faults/scenarios/` | Core fault scenarios (documented) |
| `orbitval/engine/injection.py` | Applies named faults (noise, dropouts, degradations) to telemetry streams |
| `orbitval/engine/runner.py` | Harness to execute user autonomy code under test and capture outputs |

### Reporting
| File | Owns |
|------|------|
| `orbitval/reporting/json_report.py` | Structured machine-readable pass/fail output + artifacts manifest |
| `orbitval/reporting/pdf_report.py` | Human-friendly PDF report suitable for mission readiness reviews |

---

## Phase 1 (MVP) scope

### 1) Orbital simulation engine

| Artifact | Role | Reads | Writes | Emits |
|----------|------|-------|--------|-------|
| `orbitval/orbits/propagation.py` | Propagate orbit from TLE or orbital parameters | scenario config | ephemeris arrays | ground track points |
| `orbitval/orbits/comms_windows.py` | Compute comms windows vs ground station | propagated states + station config | comms windows | time intervals |

### 2) Hardware config model (3U CubeSat only)

| Artifact | Role | Reads | Writes | Emits |
|----------|------|-------|--------|-------|
| `orbitval/config/hardware_3u_schema.py` | Validate and normalize 3U hardware model | hardware config | normalized model | validation errors/warnings |

### 3) Fault injection engine

| Artifact | Role | Reads | Writes | Emits |
|----------|------|-------|--------|-------|
| `orbitval/faults/catalog.py` | Fault scenario registry + documentation hooks | installed packs | available scenarios | scenario metadata |
| `orbitval/engine/injection.py` | Inject faults into telemetry | base telemetry + scenario + seed | injected telemetry | trace of applied faults |

### 4) Test report output (JSON + PDF)

| Artifact | Role | Reads | Writes | Emits |
|----------|------|-------|--------|-------|
| `orbitval/reporting/json_report.py` | Produce reproducible, structured pass/fail report | run inputs + outputs + traces | JSON report file | artifact manifest |
| `orbitval/reporting/pdf_report.py` | Produce human-readable readiness report | JSON report (or run model) | PDF report file | summary tables/plots |

---

## Data flow

### Local run flow (scenario + hardware + faults → report)
```
User installs OrbitVal (pip) and writes scenario + 3U hardware config files
  → user runs `orbitval` CLI (or imports Python API) with a fault scenario list and seed
  → OrbitVal loads and validates configs (scenario + hardware)
  → OrbitVal resolves orbit input (TLE from Celestrak cache/fetch or direct parameters)
  → OrbitVal propagates orbit and computes ground track + comms windows
  → OrbitVal generates or ingests base telemetry timeline
  → injection engine applies named fault scenarios deterministically (seeded)
  → runner executes the user autonomy code under test against injected telemetry
  → OrbitVal evaluates pass/fail and assembles artifacts
  → OrbitVal writes JSON report + PDF report to the output directory
```

### Component dependency diagram

```
scenario.yaml        satellite.yaml (3U hardware cfg)
      |                     |
      v                     v
  +------------------------------+
  |        test_runner           |
  | - orchestrates sim loop      |
  | - calls autonomy harness     |
  +-----+------------------------+
        | uses
        v
  +-----+------------------------+      +-------------------------+
  |        orbital_engine        |      |      fault_library      |
  | - SGP4 propagation           |      | - FaultScenario classes |
  | - ground track, eclipses     |      | - versioned fault packs |
  | - comms windows              |      +-----------+-------------+
  +-----+------------------------+                  |
        | telemetry                                  | injects
        v                                           v
  +-----+------------------------+      +-------------------------+
  |        hardware_model        |      |     injection_engine    |
  | - sensor behavior            |      | - applies faults        |
  | - actuator behavior          |      |   via inject()          |
  | - power budget               |      | - checks is_active(t)   |
  +-----+------------------------+      +-----------+-------------+
        | telemetry                           |
        +-----------------+-------------------+
                          v
                +---------+----------+
                |  autonomy harness  |
                |  (user code)       |
                +---------+----------+
                          |
                          v
                +---------+----------+
                |   report_generator |
                | - JSON + PDF       |
                +--------------------+
```

### Offline / air-gapped mode
```
User provides TLE directly (or pre-populates the cache)
  → OrbitVal skips network fetch and uses local TLE source
  → everything else remains identical; reports record that offline mode was used
```

---

## Planned connections *(optional)*

- Phase 2: add regression runner (campaigns) and scenario library tooling (local).
- Phase 3: add optional cloud dashboard (React + FastAPI hosted on Vercel/Render) that ingests only scenario configs and test outputs for visualization and sharing.

---

## Related documents

- [MAP.md](MAP.md) — entry point
- [manifest.yaml](manifest.yaml) — same connections in parseable YAML
- [ARCHITECTURE.md](ARCHITECTURE.md) — decisions and reasoning
- [TEMPLATES.md](TEMPLATES.md) — how to add new things
- [UPDATE.md](UPDATE.md) — when to update each doc
