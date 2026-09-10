# OrbitVal — Technical Guide

**Version covered:** 1.1.1 (2026-09-10) · **License:** MIT · **Python:** ≥ 3.9
**Sources:** this guide is compiled entirely from the OrbitVal codebase, `README.md`, `CHANGELOG.md`, and `docs-template/ARCHITECTURE.md` as of v1.1.0. Test/coverage numbers were measured by running the suite directly.

---

## Table of contents

1. [What OrbitVal is and why](#1-what-orbitval-is-and-why)
2. [Architecture overview](#2-architecture-overview)
3. [Fault scenarios](#3-fault-scenarios)
4. [The ORF report format](#4-the-orf-report-format)
5. [The hash registry](#5-the-hash-registry)
6. [CLI reference](#6-cli-reference)
7. [Known limitations](#7-known-limitations)
8. [Test coverage and what's verified](#8-test-coverage-and-whats-verified)
9. [Roadmap](#9-roadmap)

---

## 1. What OrbitVal is and why

OrbitVal is a **local testing framework that runs standardized fault injection scenarios against a CubeSat's onboard autonomy software** — before launch, not after. You define your hardware in a `satellite.yaml`, plug in your flight logic as a Python class, and OrbitVal tells you exactly where it breaks, producing a cryptographically verifiable report you can hand to a mission readiness review, launch provider, or insurer.

### The problem

Most CubeSat teams validate autonomy through hardware-in-the-loop testing, manual scripts, and empirical launches. Failure modes get discovered in orbit — where you can't fix them. OrbitVal gives teams a reproducible, automated way to find those failures on the ground:

- **GPS dropout** — does your autonomy switch to dead reckoning?
- **Power brownout** — does it enter safe mode before the battery dies?
- **Sensor noise** — does it detect degraded sensor quality and reduce operations?

### How it works, end to end

The `TestRunner` harness (`orbitval/engine/runner.py`):

1. Loads and validates `satellite.yaml` against the 3U hardware schema
2. Obtains an orbit — live TLE fetch, manual TLE strings, or a synthesized pre-launch orbit
3. Propagates the orbit (SGP4 via skyfield), computing ground track and eclipse periods
4. Builds a telemetry stream (`TelemetryFrame` per time step)
5. For each scenario: injects faults into the telemetry, runs the user's autonomy code against the injected frames, records every response, and evaluates pass/fail
6. Generates an ORF-compliant JSON report, a human-readable PDF, and a full `.log` audit trail — and appends the report's integrity hash to a local append-only registry

**Pass/fail evaluation** (`_evaluate_scenario` in `runner.py`): a scenario **PASSes** if the autonomy code returned at least one *safe response* while the fault was active; it **FAILs** if it only returned `"nominal"` (i.e., never detected or responded to the fault); it is marked **SKIP** if the fault window never overlapped the simulation. The default safe-response set is:

```
safe_mode, failover, failover_to_dead_reckoning, emergency_shutdown, reduced_ops
```

Users integrate by implementing a two-method interface — no monkey-patching, no changes to flight code beyond the wrapper:

```python
class Autonomy:
    def process(self, telemetry) -> str:
        """Receive a telemetry frame, return a response string."""
        ...
    def reset(self):
        """Called between scenarios to reset internal state."""
        ...
```

If autonomy code raises an exception on a frame, the harness records `"exception: ..."` as that frame's response and continues.

### The long-term thesis (from ARCHITECTURE.md)

OrbitVal's strategic position is as a **standardization company**. The goal is for the OrbitVal Report Format (ORF) to become the de facto artifact that mission readiness reviews, launch providers, and satellite insurers expect to see — making OrbitVal usage a compliance checkbox, not a purchasing decision. Three layers:

1. **The tool** — earns trust through local-first execution and clear boundaries around proprietary code
2. **The format (ORF)** — published as an open standard, community-governed, modeled on OpenAPI and FHIR, usable independently of the OrbitVal implementation
3. **The certification** — an OrbitVal-certified badge recognized by insurers and launch providers

Growth phases: university adoption → format establishment → first institutional endorsement (insurer or launch provider) → certification revenue → consortium governance. Priority institutional targets, in order: satellite insurers, launch providers, space agencies/regulators, large constellation operators and bus manufacturers.

---

## 2. Architecture overview

### 2.1 Local-first by design (ADR-001)

OrbitVal is delivered as an installable Python package. **All execution — simulation, fault injection, and the autonomy code under test — runs locally on the user's machine. Proprietary flight code never leaves the user's infrastructure.** This was a deliberate choice over a cloud-first SaaS: it gives a strong security posture and easier adoption for constrained teams, at the cost of requiring a clear, explicit harness contract for integrating user code.

A future cloud dashboard, if added, will accept **only scenario configs and test outputs/reports — never proprietary autonomy code**. Cloud value is additive (visualization/sharing), not required for core function.

The local-first guarantee shapes implementation details too: eclipse detection uses an analytic solar-position model (Astronomical Almanac low-precision formula, accurate to ~0.01°) instead of skyfield's `is_sunlit()`, specifically because the latter requires downloading a JPL ephemeris file (`de421.bsp`), which would break the offline/air-gapped guarantee.

### 2.2 Core design principles (from ARCHITECTURE.md)

- **Simulation correctness over UX cleverness** — if propagation or units are wrong, everything downstream is wrong
- **Explicit, versioned interfaces at boundaries** — user autonomy code ↔ harness, and config ↔ engine
- **Units and time always explicit** — astropy units/time, no unitless floats in orbital math
- **Determinism when possible** — seeded randomness (`--seed`, default 42) makes stress tests reproducible
- **Hardware scope stays tractable** — v1 targets the 3U CubeSat standard configuration only
- **Observability is part of the product** — runs produce structured results (inputs, seed, scenarios, anomalies, artifacts)

### 2.3 Module structure

The package is built on five conceptual modules (per README), implemented as:

| Module | Files | Role |
|---|---|---|
| orbital_engine | `orbitval/orbits/propagation.py`, `tle.py`, `comms_windows.py` | SGP4 propagation via skyfield + astropy; TLE fetch/cache; ground track, eclipse periods, ground-station visibility windows |
| hardware_model | `orbitval/config/hardware_3u_schema.py` | `satellite.yaml` loader and validator (schema v1.0, 3U only) |
| fault_library | `orbitval/faults/base.py`, `catalog.py`, `scenarios/*.py` | Named, versioned fault scenario classes behind a common `FaultScenario` protocol |
| injection_engine | `orbitval/engine/injection.py`, `runner.py` | Applies faults to telemetry frames, records the full injection trace, runs autonomy code, evaluates pass/fail |
| report_generator | `orbitval/reporting/json_report.py`, `pdf_report.py`; `orbitval/registry.py`; `orbitval/logging.py` | ORF-compliant JSON + PDF output, run log capture, hash registry |

Dependencies (`pyproject.toml`): `skyfield`, `astropy`, `numpy`, `pyyaml`, `reportlab`. skyfield + astropy were chosen over poliastro (unmaintained since 2023, Python 3.12+ compatibility issues) and over OreKit/GMAT (wrong runtime/language for Python-centric aerospace teams) — ADR-002 and ADR-005.

Console entry point: `orbitval = orbitval.cli:main`. Python API entry point: `from orbitval import TestRunner`.

### 2.4 Key mechanics

**Immutable telemetry.** `TelemetryFrame` is a dataclass; fault scenarios must return a *new* frame via `dataclasses.replace()`, never mutate the input. Frame fields: mission time `t`, GPS (lat/lon/alt/available), magnetometer x/y/z (µT), star tracker availability, attitude quaternion (scalar-first, `attitude_qw/qx/qy/qz`) plus `attitude_valid`, battery charge (Wh), solar power (W), reaction wheel speed (rpm), `ground_contact`, bus `temperature_c`, and an internal `flags` dict.

**Flag stripping (ADR-007).** OrbitVal records fault metadata in `TelemetryFrame.flags` for internal tracking. If autonomy code could read these flags, teams could "detect" faults by reading OrbitVal metadata rather than raw sensor anomalies — producing passing reports for code that would fail in orbit. So the harness strips all flags (`replace(frame, flags={})`) before every `autonomy.process()` call. Autonomy code sees only raw sensor values, exactly as onboard software would in orbit. Flags remain available internally for the injection trace and report generator. A consequence: the `sensor_noise` scenario correctly FAILs autonomy code that doesn't implement real noise detection.

**Three orbit input modes** (`TestRunner.__init__` / `orbitval run` flags):

- **Mode 1 — Live TLE (default):** fetches from Celestrak (`celestrak.org/NORAD/elements/gp.php`) by satellite name, with a local cache under `~/.orbitval/tle_cache/`. Cache entries are considered fresh for **6 hours** (`CACHE_EXPIRY_HOURS = 6` in `orbitval/orbits/tle.py`; the README said 24 hours until 1.1.1, when the docs were corrected to match the code). If the network is unreachable, a **stale cache is used as fallback**; if there's no cache either, a `ConnectionError` is raised with a tip to use pre-launch mode.
- **Mode 2 — Manual TLE strings:** `--tle-line1`/`--tle-line2` for offline/air-gapped environments. No network access; not cached. The two flags must be used together (the CLI rejects one without the other).
- **Mode 3 — Pre-launch:** `--orbit-alt`/`--orbit-inc` synthesize a circular orbit for satellites that haven't launched. Since 1.1.1, `--epoch` pins the start time; without it the orbit starts at the current clock and the run is not reproducible (`simulation.epoch_source` records which applied). Implementation: `propagate_from_params()` computes mean motion for a circular orbit and builds a properly column-aligned **synthetic TLE** (catalog number 99999, valid checksums) which is then propagated through the same SGP4 path as real TLEs.

For Modes 1 and 2, the CLI backfills the ORF `mission_profile` altitude/inclination from the TLE itself (inclination parsed from TLE line 2, altitude averaged from the propagated ground track) when the user didn't pass explicit orbit flags.

**Eclipse detection** (new in 1.1.0): the propagator classifies every time step as sunlit / penumbra / umbra using the standard conical shadow model (comparing apparent angular radii of Earth and Sun as seen from the satellite), then extracts contiguous shadow intervals as `eclipse_periods`. These are embedded in the ORF report and fed to eclipse-aware fault scenarios so the fault fires during *actual* shadow passages.

**Comms windows:** with `--ground-station`, visibility windows (satellite above the station's minimum elevation, default 10°) are computed by sampling elevation at 10-second resolution. Frames outside all windows are flagged `comms_blackout: True` internally. Comms windows require a real TLE — in pre-launch mode (synthetic orbit) they are unavailable and a warning is logged.

**Run log:** a custom logging layer (`orbitval/logging.py`) mirrors every INFO/WARNING/ERROR (and DEBUG when enabled) event into a run-event buffer embedded in the ORF report as `run_log`, and into a `.log` file next to the reports. Since 1.1.0 the buffer is cleared and the log file opened *before* scenarios execute (previously scenario events were missed), and a second `run()` in the same process no longer appends to the previous run's `.log` file.

### 2.5 Open-core model (ADR-004)

The core framework is free and open source (MIT); advanced fault scenario packs and reporting tools are paid. **University CubeSat teams get everything free (`.edu` email); commercial operators pay.**

The free/paid boundary rule: **if a fault requires knowledge of a specific hardware vendor's behavior or specifications, it belongs in the paid tier; if it can be modeled generically without vendor secrets, it's free.**

| Tier | Examples |
|---|---|
| **Free (generic)** | RF interference, power brownout, generic sensor noise, GPS dropout, communication blackout during eclipse |
| **Paid (hardware-specific)** | Reaction wheel bearing degradation (vendor torque curves), star tracker lost-in-space recovery failure, specific solar panel degradation models, battery cell failure under specific thermal conditions |

All six currently shipped scenarios are FREE tier. Paid packs implement the same `FaultScenario` protocol as free scenarios.

### 2.6 Dual-entity structure (ADR-006)

A standard owned by a for-profit company faces institutional resistance — insurers and launch providers won't tie their workflows to a single startup's proprietary format. The planned structure separates the standard from the business:

**OrbitVal Inc (commercial entity):**
- Builds and maintains the tooling; sells advanced scenario packs
- Operates the cloud dashboard; issues certification badges (early stage)
- For-profit, founder-owned

**ORF Foundation (future non-profit/consortium):**
- Owns and governs the ORF spec
- Operates the hash registry (append-only, publicly queryable)
- Issues certifications long-term
- Board includes insurers, launch providers, universities, and OrbitVal Inc as founding member
- Modeled on the OpenAPI Initiative, Linux Foundation, and HL7 (FHIR)

Sequencing: the foundation cannot be created before OrbitVal has institutional credibility. Planned order: (1) build tool, get university adoption → (2) get one institutional reference → (3) spin out foundation with institutional co-founders → (4) transfer spec governance and registry to the foundation → (5) OrbitVal Inc becomes the premier commercial tooling provider for the standard it founded.

---

## 3. Fault scenarios

Six scenarios ship in v1.1.0, all FREE tier, all versioned `1.0.0`, registered in `orbitval/faults/catalog.py` (`FAULT_REGISTRY`). Each implements the `FaultScenario` protocol: `name`, `description`, `version`, `inject(telemetry) -> TelemetryFrame` (returns a new frame, never mutates), and `is_active(t) -> bool` (time-windowed activation). Most share a `WindowedFault` base providing the `t_start`/`duration_s` window. Scenarios that accept a `seed` receive the run's seed automatically for reproducibility.

### 3.1 `gps_dropout`

**Simulates:** complete GPS signal loss for a configurable duration — one of the most common CubeSat failure modes (orbital insertion, eclipse entry, antenna obstruction).
**Injection:** sets `gps_available=False` and zeroes `gps_lat`/`gps_lon`/`gps_alt_km` during the window.
**Tests:** whether autonomy maintains safe operation using dead reckoning or alternative navigation.
**Defaults:** `t_start=60.0`, `duration_s=120.0`.

### 3.2 `power_brownout`

**Simulates:** a sudden reduction in battery charge and solar input — battery drain or panel degradation entering eclipse.
**Injection:** multiplies `battery_charge_wh` by `battery_drain_factor` and `solar_power_w` by `solar_drain_factor` during the window.
**Tests:** autonomous power management — shedding non-critical loads and safe mode triggering.
**Defaults:** `t_start=120.0`, `duration_s=180.0`, `battery_drain_factor=0.3`, `solar_drain_factor=0.1`.

### 3.3 `sensor_noise`

**Simulates:** amplified Gaussian noise on magnetometer and GPS readings — electromagnetic interference, radiation effects, or gradual sensor degradation.
**Injection:** adds seeded Gaussian noise to `magnetometer_x/y/z` (σ=0.1×scale) and `gps_lat`/`gps_lon` (σ=0.001×scale) during the window.
**Tests:** robustness against degraded sensor quality. Because fault flags are stripped (ADR-007), this scenario FAILs autonomy code that doesn't implement genuine noise detection (e.g., watching magnetometer variance).
**Defaults:** `t_start=0.0`, `duration_s=300.0`, `noise_scale=5.0`, `seed=42`.

### 3.4 `eclipse_power_stress` (added in 1.1.0)

**Simulates:** power and thermal stress during eclipse passage — solar input collapses, battery degrades, and bus temperature drops until re-entering sunlight.
**Injection:** multiplies `solar_power_w` by `solar_factor` (default 0.0 — total collapse), `battery_charge_wh` by `battery_factor`, and subtracts `temperature_drop_c` from `temperature_c` while in shadow.
**Eclipse-aware:** when the propagated orbit produced real `eclipse_periods`, the runner passes those umbra/penumbra intervals in as `eclipse_windows` and the fault activates during *actual* shadow passages instead of the fixed fallback window.
**Tests:** load shedding and power management across eclipse entry and exit.
**Defaults:** fallback `t_start=120.0`, `duration_s=600.0`; `solar_factor=0.0`, `battery_factor=0.8`, `temperature_drop_c=35.0`.
**Caveat:** the thermal model is a flat bus-temperature drop, not a component-level thermal simulation (see Known limitations).

### 3.5 `comms_blackout` (added in 1.1.0)

**Simulates:** total loss of ground contact for a configurable duration — antenna failure, ground segment outage, or an extended pass gap. During the blackout no commands can be received and no telemetry reaches the ground.
**Injection:** sets `ground_contact=False` during the window.
**Tests:** fully autonomous operation during the blackout (conserving resources, buffering data) and recovery detection when contact is reacquired.
**Defaults:** `t_start=300.0`, `duration_s=900.0`.

### 3.6 `star_tracker_failure` (added in 1.1.0)

**Simulates:** attitude determination failure — the star tracker feeds bad or null quaternion data. The dangerous failure mode is not the loss itself but *silent trust*: downstream subsystems (pointing, momentum management, comms scheduling) acting on garbage attitude data as if it were valid.
**Two modes:**
- `"failed"` — star tracker offline: `star_tracker_available=False`, null quaternion (0,0,0,0 — zero norm, mathematically invalid), `attitude_valid=False`
- `"degraded"` — the tracker still reports available, but the quaternion is corrupted with seeded Gaussian noise and no longer normalized; only `attitude_valid=False` reveals the solution can't be trusted

**Tests:** that autonomy flags degraded attitude confidence rather than silently trusting invalid attitude solutions.
**Defaults:** `t_start=180.0`, `duration_s=300.0`, `mode="failed"`, `noise_sigma=0.3`, `seed=42`. An invalid `mode` raises `ValueError` at construction.

### Scenario configuration file (`scenario.yaml`)

Since 1.1.0, `orbitval/config/scenario_schema.py` defines a validated `scenario.yaml` (schema version `"1.0"`) for declaring scenarios and parameters instead of CLI flags:

```yaml
schema_version: "1.0"
scenarios:
  - name: gps_dropout
    params:
      t_start: 60.0
      duration_s: 120.0
  - name: eclipse_power_stress
  - name: star_tracker_failure
    params:
      mode: degraded
```

Valid names and parameters are derived automatically from `FAULT_REGISTRY` and each scenario's constructor signature — the schema never needs updating when a new fault is registered. **Note:** the schema and validation exist and are tested, but the CLI flag to use it (`--scenario-config`) is **not wired up yet** (roadmap item). Today the file can only be consumed via the Python API.

---

## 4. The ORF report format

The **OrbitVal Report Format (ORF)** is the canonical output schema for every run (spec version 1.0, defined in ARCHITECTURE.md under "ORF Spec — Report Format Fields" and implemented in `orbitval/reporting/json_report.py`). It is designed to be **self-describing**: an insurer or launch provider must be able to understand the mission and test results without reading separate documentation.

Every run writes three files to the output directory (default `reports/`), named `<satellite>_<timestamp>`:

```
reports/
├── my_cubesat_2026-07-01_03-20-30.json   ← machine-readable ORF report
├── my_cubesat_2026-07-01_03-20-30.pdf    ← human-readable mission readiness report
└── my_cubesat_2026-07-01_03-20-30.log    ← full internal audit trail (plain text)
```

### 4.1 Required top-level fields (enforced by schema validation)

`validate_orf_schema()` checks presence and type of these fields; `verify-report` rejects any document failing them:

| Field | Type | Content |
|---|---|---|
| `orbitval_version` | str | Generating tool version (`"1.1.0"`) |
| `orf_spec_version` | str | ORF spec version (`"1.0"`) |
| `schema_version` | str | `"1.0"` |
| `report_id` | str | UUID4, unique per report |
| `generated_at` | str | ISO 8601 UTC timestamp |
| `test_integrity_hash` | str | SHA-256 of all inputs and outputs (see below) |
| `mission_profile` | dict | `orbit_type` (e.g. LEO), `altitude_band_km`, `inclination_deg`, `operational_lifetime_years` |
| `regulatory_jurisdiction` | str | e.g. FCC/ITU/ESA; default `"none declared"` |
| `applicable_standard` | str | default `"none declared"` |
| `hardware_generation` | str | e.g. `"COTS"` |
| `form_factor` | str | `"3U"` |
| `scenarios_run` | list | Per-scenario results (see below) |
| `overall_result` | str | `PASS` \| `FAIL` (FAIL if any scenario failed) |
| `certification_eligible` | bool | True only when no scenario failed |

The *mission context* fields exist because "3U" tells an insurer the size, not the capability or risk profile — the report must describe the mission independently of OrbitVal.

### 4.2 Additional embedded sections

- **`satellite`** — the hardware under test: name, mass, every sensor (`type`, `noise_sigma`), every actuator (`type`, `max_torque_nm`), and power (`battery_capacity_wh`, `solar_panel_area_m2`)
- **`simulation`** — `orbit_epoch` (ISO 8601), `duration_s`, `seed`
- **`scenarios_run[]`** — per scenario: `name`, `version`, `result` (PASS/FAIL/SKIP), `duration_s`, `seed`, `autonomy_response` (the most common response during the active fault), `fault_trace` (every injection event for that scenario), and `failure_reason` when applicable
- **`comms_windows[]`** — ground-station visibility intervals: station, start/end (ISO 8601 and mission-elapsed seconds), duration, max elevation. Empty when no ground stations were given or in pre-launch mode
- **`eclipse_periods[]`** — umbra/penumbra intervals from shadow geometry: `type`, start/end times, mission-elapsed `start_t`/`end_t`, `duration_s`. Empty if the orbit never crosses Earth's shadow in the window
- **`injection_trace[]`** — the flat, full audit trail across all scenarios: every fault event with timestamp `t`, `fault_name`, and `fields_modified`
- **`run_log[]`** — every internal log event of the run (timestamp, level, module, message), making the report self-documenting

### 4.3 The integrity hash

`test_integrity_hash` is the SHA-256 of the canonical JSON serialization (sorted keys) of the *entire report payload* — everything above, inputs and outputs — computed before the hash field itself is added. It transforms the report from a structured document into a **verifiable attestation**: any modification after generation invalidates the hash. This is the field designed to let insurers and launch providers trust a report without auditing the test themselves. `orbitval verify-report` recomputes and compares it.

### 4.4 The PDF report

The PDF (`pdf_report.py`, generated with reportlab, A4) is the human-readable companion: result banner (PASS/FAIL + certification eligibility), report metadata (ID, timestamps, versions, truncated hash), satellite-under-test table, simulation parameters, per-scenario results, comms-window summary (count, total contact time, % of simulation; first 15 windows), injection trace summary (first 20 events), and a footer with the full integrity hash. It deliberately does **not** contain the full run log — that lives in the JSON and `.log` file only.

---

## 5. The hash registry

### 5.1 What it is

`orbitval/registry.py` implements a **local, append-only registry of report hashes**, modeled on Certificate Transparency (deliberately *not* blockchain — a simple append-only log achieves the same trust properties with less overhead).

- **Storage:** a JSONL file. Path resolution, first match wins: explicit `--registry` argument → `ORBITVAL_REGISTRY` environment variable → `.orbitval/registry.jsonl` in the current working directory.
- **Entries:** `{report_hash, timestamp, satellite_id, prev_entry_hash}`, serialized canonically (sorted keys, compact separators), one per line.
- **Chaining:** each entry's `prev_entry_hash` is the SHA-256 of the previous entry's line exactly as stored; the first entry chains to a genesis hash of 64 zeros. The file is only ever opened in append mode — existing lines are never rewritten.
- **Automatic:** every `orbitval run` appends the new report's `test_integrity_hash` to the registry as part of report generation. No opt-in needed.

### 5.2 What it protects against

Because each entry is hashed into the next, **altering, reordering, or deleting any past entry breaks the chain for every entry after it**. Concretely:

- A **tampered report** is caught by the internal hash check (`verify-report` recomputes SHA-256 over the payload).
- A **back-dated or fabricated report** whose hash was never registered shows `registry provenance: not found`.
- **Editing a past registry entry** (e.g., to launder a fabricated hash into history) shows `chain broken`, and `orbitval registry verify` pinpoints the first bad entry: *"Entries at or after the break cannot be trusted."*
- A registry tampered *anywhere* cannot vouch for *anything*: `check_provenance()` verifies the full chain before answering any lookup, so even a hash that is genuinely present returns `chain broken` if the chain fails elsewhere.

Two independent verification paths:

- `orbitval verify-report <report.json>` — checks **both** the internal hash (valid/invalid) and registry provenance (confirmed/not found/chain broken). Exits 0 only when both pass.
- `orbitval registry verify` — walks the full chain independently of any single report.

### 5.3 What it does NOT protect against — the local-only limitation

Be precise about scope: **the local registry proves provenance against local history only.** Its known, documented gaps:

1. **Wholesale deletion or replacement of the registry file.** Nothing prevents an attacker with filesystem access from deleting `.orbitval/registry.jsonl` and rebuilding a self-consistent chain from scratch that includes whatever hashes they like.
2. **Rewriting the most recent entry.** The chain protects entries that something *later* chains to. The final entry has nothing chaining to it yet, so it can be rewritten (with a recomputed line) without breaking anything.
3. **Cross-machine verification.** Provenance is checked against the *local* registry — a legitimate report verified on a machine that didn't generate it will show `not found`, and conversely, an attacker controls the registry on their own machine.

Closing these gaps requires the **hosted/public registry** operated by the ORF Foundation — a remote append-only log with a **witnessed chain head** that third parties (insurers, launch providers) query directly ("is this hash registered and does it match a valid OrbitVal run?"). The hosted registry never sees proprietary autonomy code — only the hash of the outputs. This is **planned, deliberately not half-built** (the CHANGELOG's phrasing): the local registry is the on-ramp, not the trust anchor.

**Status: implemented (local), not yet hosted.**

---

## 6. CLI reference

Program: `orbitval` (entry point `orbitval.cli:main`). Global flag: `--version` (prints `OrbitVal 1.1.0`). A subcommand is required.

### `orbitval list-faults`

List all available fault scenarios with tier, version, and description. No flags.

### `orbitval validate`

Validate a `satellite.yaml` hardware config; prints the parsed satellite summary on success, actionable errors on failure. Exits 1 on missing or invalid config.

| Flag | Default | Description |
|---|---|---|
| `--config <path>` | `satellite.yaml` | Path to satellite.yaml |

Config schema (v1.0, 3U only): `schema_version: "1.0"`, `name`, `form_factor: "3U"`, positive `mass_kg`, at least one sensor (`type` ∈ GPS, star_tracker, magnetometer, sun_sensor, gyroscope; non-negative `noise_sigma`), at least one actuator (`type` ∈ reaction_wheel, magnetorquer, thruster; positive `max_torque_nm`), and `power` with positive `battery_capacity_wh` and `solar_panel_area_m2`.

### `orbitval run`

Run a fault injection stress test. Exits 1 on config/TLE/run errors **and when the overall result is FAIL** (CI-friendly).

| Flag | Default | Description |
|---|---|---|
| `--config <path>` | `satellite.yaml` | satellite.yaml path |
| `--scenarios <names...>` | `gps_dropout power_brownout sensor_noise` | Fault scenarios to run (space-separated) |
| `--autonomy <path>` | built-in stub | Path to a `.py` file defining an `Autonomy` class. If omitted, a default stub runs (fails over on GPS loss, safe-modes below 5 Wh, reduces ops on low solar/no ground contact, fails over on star tracker/attitude loss, detects magnetometer variance) |
| `--tle-name <name>` | `ISS (ZARYA)` | Satellite name for Celestrak fetch (Mode 1) |
| `--tle-line1 <string>` | — | TLE line 1 (Mode 2; must be paired with `--tle-line2`) |
| `--tle-line2 <string>` | — | TLE line 2 (Mode 2; must be paired with `--tle-line1`) |
| `--orbit-alt <km>` | — | Orbital altitude for pre-launch mode (Mode 3) |
| `--orbit-inc <deg>` | — | Orbital inclination for pre-launch mode (Mode 3) |
| `--orbit-type <str>` | `LEO` | Orbit type recorded in the report's mission profile |
| `--duration <hours>` | `1.0` | Simulation duration |
| `--step <seconds>` | `60.0` | Telemetry time step |
| `--seed <int>` | `42` | Random seed for reproducibility |
| `--ground-station <spec...>` | — | One or more stations as `name,lat,lon[,alt,min_el]` (alt in km, min elevation default 10°) |
| `--output <dir>` | `reports/` | Report output directory |
| `--verbose` | off | Debug logs |
| `--quiet` | off | Warnings and errors only |

Mode selection: `--orbit-alt` + `--orbit-inc` → pre-launch; else `--tle-line1` + `--tle-line2` → manual TLE; else live Celestrak fetch of `--tle-name`.

### `orbitval verify-report`

```
orbitval verify-report <report.json> [--registry <path>]
```

Verify an ORF JSON report. Order of checks: file exists → valid JSON → is a JSON object → **passes ORF schema validation** (a self-consistent hash on a non-ORF document is rejected, not "verified") → then two independent results are printed:

- **Internal hash** — `valid` / `invalid` (report modified after generation)
- **Registry provenance** — `confirmed` (with registration timestamp) / `not found` / `chain broken`

Exits 0 **only if the hash matches AND the report is registered in an intact local registry**.

| Flag | Default | Description |
|---|---|---|
| `--registry <path>` | `$ORBITVAL_REGISTRY` or `.orbitval/registry.jsonl` | Registry file to check provenance against |

### `orbitval registry verify`

```
orbitval registry verify [--registry <path>]
```

Verify full chain integrity of the local append-only registry, independent of any single report. Prints entry count on success; on failure, reports the 0-based index of the first broken entry and warns that entries at or after the break cannot be trusted. Exits 1 if the registry is missing or the chain is broken. Same `--registry` flag as above. (`verify` is currently the only `registry` subcommand.)

---

## 7. Known limitations

Current, honest, as documented in README/ARCHITECTURE and confirmed in code:

**Documented in README (v1.1.0):**

- **Thermal model is simplified** — `eclipse_power_stress` models a flat bus-temperature drop in shadow, not a full thermal simulation with component-level gradients.
- **PDF audit trail** — the PDF is a human-readable summary; the full internal run log (every injected fault event, timestamped) is in the JSON report and `.log` file only.
- **Hash registry is local-only** — detects tampering with individual entries and reports, but cannot detect deletion or wholesale replacement of the registry file itself (see §5.3). The hosted registry that closes this gap is planned, not built.

**From ARCHITECTURE.md (v1 limitations):**

- **SGP4 propagation** — well-suited for LEO analysis, not for high-fidelity maneuver planning or long-duration GEO/HEO campaigns.
- **Simplified power budget** — no detailed thermal modeling or fine-grained EPS dynamics.
- **Sensor independence assumed** — correlated failures and cascading cross-subsystem effects are not modeled.
- **3U-tuned models** — applying orbit/hardware models to other form factors may produce misleading results (and the config validator rejects anything but `3U`).

**Explicit v1 non-goals (by design, not gaps):** atmospheric drag / higher-order perturbations (J2+), multi-satellite constellations, non-3U form factors, network-dependent autonomy code, real-time simulation (batch-only for determinism), GUI usage (CLI + Python API only), hardware-in-the-loop testing.

**Additional current-state facts worth knowing:**

- `scenario.yaml` schema and validation exist but are **not wired to the CLI** yet — no `--scenario-config` flag (roadmap item).
- Since 1.1.1 the propagation time axis is spaced exactly `step_seconds`; before that `np.linspace` included the endpoint, stretching a 60-second step to 61.02 seconds.
- Comms windows require a real TLE; they are unavailable in pre-launch mode.
- The README states a 24-hour TLE cache; the code sets **6 hours** (`CACHE_EXPIRY_HOURS = 6`).
- ~~Per-scenario `duration_s` assumes a 60-second step~~ — fixed in 1.1.1; it now uses the run's actual `--step`.
- Autonomy pass criteria are coarse: any safe response at any point during the active fault passes. No time-to-detect bound, and no check that the autonomy recovered once the fault cleared.
- The registry is not safe against concurrent writers; parallel runs need separate `--registry` paths.

---

## 8. Test coverage and what's verified

Measured directly (`pytest --cov=orbitval`, Python 3.13): **318 tests, all passing, 95% line coverage** (1,266 statements, 60 missed), zero warnings. This supersedes the 1.1.0 figure of 252 tests at 92%.

### Coverage by module

| Module | Coverage |
|---|---|
| `registry.py`, `json_report.py`, `injection.py`, `hardware_3u_schema.py`, `propagation.py`, `comms_windows.py`, `base.py`, `comms_blackout.py`, `eclipse_power_stress.py`, `star_tracker_failure.py` | 100% |
| `pdf_report.py` | 98% |
| `logging.py` | 96% |
| `runner.py` | 95% |
| `sensor_noise.py` / `power_brownout.py` / `gps_dropout.py` | 93–95% |
| `scenario_schema.py`, `tle.py`, `catalog.py` | 92% |
| `cli.py` | 92% (was 75%; `main()`'s argparse wiring is now driven through `sys.argv`) |

### What the suite verifies

- **Hash registry (33 tests)** — chain construction, genesis hash, append semantics, chain verification, tamper/reorder/delete detection, path resolution (arg/env/default)
- **Hardware config (28 tests)** — schema boundary cases: bad form factors, missing/invalid sensors, actuators, power, mass, schema version
- **CLI integration (22 tests)** — end-to-end subcommand behavior including bad-input paths
- **Fault scenarios (42 tests)** — `star_tracker_failure` (17: both modes, invalid mode, quaternion behavior), `eclipse_power_stress` (13: real-window vs fallback activation), `comms_blackout` (12: blackout and reacquisition)
- **verify-report (15 tests)** — dual-check output, ORF schema rejection of non-ORF documents, exit codes
- **Orbit engine (48 tests)** — propagation edge cases (14), eclipse detection geometry (14), TLE fetch/cache/offline logic (12), TLE flag validation (8)
- **Scenario schema (12 tests)** — `scenario.yaml` validation, unknown names/params derived from the registry
- **Run log (8 tests)** — event buffer scoping and `.log` file lifecycle
- **Regression tests (41 tests across `test_bug1`–`test_bug7`)** — pinned fixes for: pre-launch propagation, injection trace, comms windows, scenario lookup, config errors in `run`, TLE connection errors, mission-profile backfill from TLE, and `__init__` exports

(Note: a root-level `test_orbit.py` exists but contains no test functions.)

---

## 9. Roadmap

From the README roadmap, ARCHITECTURE.md, and the CHANGELOG:

**Shipped (1.1.0):**
- ✅ Eclipse period detection (umbra/penumbra shadow geometry)
- ✅ Three new fault scenarios: `eclipse_power_stress`, `comms_blackout`, `star_tracker_failure`
- ✅ Local append-only hash registry + `registry verify` + dual-check `verify-report` with ORF schema validation
- ✅ `scenario.yaml` schema and validation

**Next (planned, not built):**
- ☐ **`scenario.yaml` CLI wiring** — the `--scenario-config` flag (schema + validation already exist)
- ☐ **Hosted/remote hash registry** — remote append-only log with a witnessed chain head, operated by the ORF Foundation and queried directly by insurers/launch providers; closes the local-only trust gap (§5.3)
- ☐ **Constellation simulation** (multi-satellite)
- ☐ **Optional cloud dashboard for report sharing** — planned stack (ADR-005): React frontend on Vercel + FastAPI report API on Render; strictly ingests test outputs and scenario configs, never autonomy code

**Longer-term (strategic, from ARCHITECTURE.md):**
- Publish the ORF spec as an open, community-governed standard
- Paid hardware-specific fault packs for commercial operators (reaction wheel degradation, vendor-specific star tracker recovery, panel/battery degradation models)
- OrbitVal certification badge recognized by insurers and launch providers
- Spin out the ORF Foundation and transfer spec governance and the public registry to it

---

*Generated 2026-07-04 from the OrbitVal repository at v1.1.0; updated 2026-09-10 for v1.1.1.*
