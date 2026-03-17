# OrbitVal — Templates & Contracts

> The HOW of this codebase.
> Copy the relevant template when adding something new.
> The contracts are non-negotiable — they're what makes everything composable.
> Entry point: [MAP.md](MAP.md).

---

## Contracts (non-negotiable rules)

OrbitVal is a local Python testing framework. These contracts keep the simulation, injection, and reporting layers composable and safe for “no code leaves your infrastructure” usage.

### Public API boundary (core rule)
```
✅ MUST    keep proprietary autonomy code on the user’s machine (local execution only)
✅ MUST    treat “user autonomy code” as an injected dependency (never vendored into OrbitVal)
✅ MUST    record inputs + seed + versions so runs are reproducible
❌ NEVER   require uploading code or telemetry to a hosted service in Phase 1
```

### Config (scenario + hardware)
```
✅ MUST    be validated at load time (schema + helpful errors)
✅ MUST    be versioned (schema_version) to support future evolution
✅ SHOULD  be file-based (YAML/JSON) for easy review and storage in repos
❌ NEVER   hide default assumptions without recording them in the report
```

### Orbital mechanics (poliastro + astropy)
```
✅ MUST    use explicit units/time (astropy) end-to-end
✅ MUST    support TLE input and orbital-parameter input
✅ SHOULD  support offline mode (no network), using local TLE cache or direct TLE
❌ NEVER   use unitless floats internally for physics quantities
```

### Fault scenarios (injection)
```
✅ MUST    be named, documented, and parameterizable
✅ MUST    declare what signals they affect (e.g., GPS, star tracker, reaction wheels)
✅ MUST    support deterministic execution (seeded randomness)
✅ SHOULD  be packaged as “fault packs” with versioning metadata
❌ NEVER   bake mission/team specific secrets into a pack
❌ NEVER   require monkey-patching user code; all injection happens via the OrbitVal harness
```

### Reporting
```
✅ MUST    emit structured JSON suitable for automation and archival
✅ MUST    emit a PDF suitable for mission readiness review
✅ MUST    include inputs, seed, versions, and fault scenario identifiers
❌ NEVER   produce reports that can’t be reproduced from recorded inputs
```

---

## Hardware config file (`satellite.yaml`)

OrbitVal expects a 3U CubeSat hardware configuration file named `satellite.yaml` in YAML format.

Required keys (conceptual schema):

```yaml
schema_version: "1.0"
name: string
form_factor: "3U"
mass_kg: float
sensors:
  - type: string        # e.g. GPS, star_tracker, magnetometer
    noise_sigma: float  # baseline noise standard deviation
actuators:
  - type: string        # e.g. reaction_wheel, thruster
    max_torque_nm: float
power:
  battery_capacity_wh: float
  solar_panel_area_m2: float
```

The concrete schema and validation live in `orbitval/config/hardware_3u_schema.py`. Changes there should be reflected here at a conceptual level.  
The `schema_version` field is **required** so that OrbitVal can support backwards compatibility as the hardware spec evolves over time.

---

## New module template (Python)

```python
# orbitval/<domain>/<module>.py

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ModuleResult:
    ok: bool
    details: dict[str, Any]


def run(*, inputs: dict[str, Any]) -> ModuleResult:
    # Pure orchestration: validate, call dependencies, return structured outputs.
    raise NotImplementedError
```

---

## Fault scenario template (Python)

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class FaultScenario(Protocol):
    """Interface for all fault scenarios."""

    name: str
    description: str

    def inject(self, telemetry: "TelemetryFrame") -> "TelemetryFrame":
        ...

    def is_active(self, t: float) -> bool:
        ...


@dataclass(frozen=True)
class GpsDropout:
    name: str = "gps_dropout"
    description: str = "Simulates complete GPS signal loss for a window of time."
    start_time_s: float = 0.0
    end_time_s: float = 0.0

    def inject(self, telemetry: "TelemetryFrame") -> "TelemetryFrame":
        # Return a new TelemetryFrame with GPS data removed when active.
        raise NotImplementedError

    def is_active(self, t: float) -> bool:
        return self.start_time_s <= t <= self.end_time_s
```

---

## Harness usage template (Python)

User autonomy code is integrated via a harness, without modification or monkey-patching:

```python
from orbitval import TestRunner
from my_autonomy import MyAutonomyClass


runner = TestRunner(
    config="satellite.yaml",
    autonomy=MyAutonomyClass,
)

runner.run(scenarios=["gps_dropout", "reaction_wheel_degradation"])
```

The harness intercepts telemetry between the simulation engine and the autonomy code, applies configured fault scenarios, and records responses for reporting.

---

## Report schema template (JSON shape)

```json
{
  "schema_version": 1,
  "run": {
    "id": "string",
    "timestamp_utc": "string",
    "seed": 123,
    "orbitval_version": "0.1.0"
  },
  "inputs": {
    "scenario_config": {},
    "hardware_config": {},
    "faults": [{ "name": "gps_dropout", "version": "1.0.0", "params": {} }]
  },
  "results": {
    "pass": true,
    "checks": [{ "name": "string", "pass": true, "details": {} }],
    "artifacts": [{ "type": "pdf", "path": "reports/run-123.pdf" }]
  }
}
```

---

## Checklist — adding a new capability

```
□ Add/extend a schema (scenario or 3U hardware) if new inputs are needed
□ Add a new fault scenario (or pack) with METADATA + docs
□ Add/extend injection engine support for the new fault signals
□ Add report fields/checks so outcomes are visible in JSON + PDF
□ Add a CLI surface (command/flag) if a user-facing entry is needed
□ Update MANIFEST.md             add new files, connections, data flow
□ Update manifest.yaml           modules/services/phases/planned
□ Update MAP.md                  scope/phases and codebase tree if needed
□ Add an ADR to ARCHITECTURE.md  if a non-obvious decision was made
```

---

## Existing core modules (Phase 1)

| Module | File | Owns |
|--------|------|------|
| config | `orbitval/config/` | scenario + 3U hardware config schemas |
| orbits | `orbitval/orbits/` | propagation, ground track, comms windows, TLE integration |
| faults | `orbitval/faults/` | fault catalog and scenario packs |
| engine | `orbitval/engine/` | runner harness + injection |
| reporting | `orbitval/reporting/` | JSON + PDF output |

---

## Related documents

- [MAP.md](MAP.md) — entry point
- [ARCHITECTURE.md](ARCHITECTURE.md) — decisions and reasoning
- [MANIFEST.md](MANIFEST.md) — file map and connections
- [UPDATE.md](UPDATE.md) — when to update each doc
