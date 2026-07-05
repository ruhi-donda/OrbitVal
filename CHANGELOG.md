# Changelog

All notable changes to OrbitVal are documented here.

---

## [1.1.0] — 2026-07-03

**Append-only hash registry (local) — report attestation**
- New `orbitval/registry.py` — local append-only JSONL registry of report hashes, Certificate Transparency model. Each entry (`report_hash`, `timestamp`, `satellite_id`, `prev_entry_hash`) is chained to the previous one, so altering, reordering, or deleting any past entry breaks the chain for everything after it.
- Report generation now automatically appends each report's `test_integrity_hash` to the registry (default `.orbitval/registry.jsonl`, overridable via `ORBITVAL_REGISTRY` or `--registry`).
- New `orbitval registry verify` command — checks full chain integrity independent of any single report.
- Known gap (documented, deliberately not half-built): the local registry cannot detect deletion or wholesale replacement of the registry file itself; that requires the hosted registry (future work).

**verify-report — dual-check output and schema validation**
- `orbitval verify-report` now reports two independent results: internal hash (valid/invalid) and registry provenance (confirmed/not found/chain broken). Exits 0 only when both pass.
- Reports are now validated against the ORF schema (required fields, expected types) before verification — a self-consistent hash on a non-ORF document is rejected instead of being reported as verified.

**Eclipse detection**
- Orbit propagation now computes umbra/penumbra intervals from Earth shadow geometry; `eclipse_periods` is embedded in the ORF report and fed to eclipse-aware fault scenarios.

**Three new fault scenarios**
- `eclipse_power_stress` — solar power loss and battery drain during real shadow passages
- `comms_blackout` — ground contact loss; tests reduced-ops behavior
- `star_tracker_failure` — attitude determination loss (full and degraded modes)

**Scenario configuration file**
- New `scenario.yaml` schema (`orbitval/config/scenario_schema.py`) — declare scenarios and parameters in a validated config file instead of CLI flags. Valid names/parameters derive from the fault registry automatically.

**Fixes**
- ORF reports now actually embed the run's audit trail: the `run_log` field and the `.log` file previously missed all scenario events because the event buffer was cleared (and the log file opened) only at report-generation time. Both now start before scenarios execute.
- A second `run()` in the same process no longer appends its log events to the previous run's `.log` file.

---

## [1.0.0] — 2026-07-01

First stable release. The core framework is complete and ready for real CubeSat autonomy testing.

### What's in this release

**CLI — four subcommands**
- `orbitval run` — full fault injection stress test with structured output
- `orbitval validate` — satellite.yaml config validation with actionable errors
- `orbitval list-faults` — fault scenario discovery
- `orbitval verify-report` — recomputes the integrity hash of an ORF JSON report and compares it to the stored hash; detects any modification after generation

**Three orbit input modes**
- Mode 1: live TLE fetch from Celestrak (24-hour local cache)
- Mode 2: manual TLE strings via `--tle-line1`/`--tle-line2` (offline/air-gapped)
- Mode 3: pre-launch synthesis from `--orbit-alt`/`--orbit-inc` (no TLE needed)

**Three free fault scenarios**
- `gps_dropout` — complete GPS signal loss; tests dead reckoning fallback
- `power_brownout` — battery and solar power drop; tests safe mode triggering
- `sensor_noise` — amplified gaussian noise on magnetometer and GPS; tests noise detection

**Fault injection engine**
- Immutable TelemetryFrame — fault scenarios return new frames, never mutate
- Flag stripping — autonomy code sees clean sensor data only, not OrbitVal metadata (ADR-007)
- Seeded randomness — every run is reproducible with `--seed`

**ORF report output**
- JSON report — full ORF v1.0 spec: scenarios, injection trace, comms windows, mission profile, embedded run log
- PDF report — human-readable mission readiness artifact
- `.log` file — full internal audit trail
- `test_integrity_hash` — SHA-256 of all inputs and outputs; makes every report a verifiable attestation

**Ground station comms windows**
- Visibility window computation via `--ground-station name,lat,lon[,alt,min_el]`
- Blackout annotation on telemetry stream

**Hardware config validation**
- `satellite.yaml` schema v1.0 for 3U CubeSat
- Sensors: GPS, star_tracker, magnetometer, sun_sensor, gyroscope
- Actuators: reaction_wheel, magnetorquer, thruster

**Test suite**
- 140 tests across unit, integration, and end-to-end CLI coverage
- Hardware config boundary cases, TLE cache logic, propagation edge cases, CLI bad-input paths

### Known limitations

- Eclipse period detection is not implemented — ORF reports contain no eclipse data
- PDF report does not include the internal run log; full audit trail is in the JSON report only

### Upgrading

This is the first stable release. No migration needed.
