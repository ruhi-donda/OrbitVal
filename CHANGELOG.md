# Changelog

All notable changes to OrbitVal are documented here.

---

## [1.0.0] — 2026-07-01

First stable release. The core framework is complete and ready for real CubeSat autonomy testing.

### What's in this release

**CLI — three subcommands**
- `orbitval run` — full fault injection stress test with structured output
- `orbitval validate` — satellite.yaml config validation with actionable errors
- `orbitval list-faults` — fault scenario discovery

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
- 128 tests across unit, integration, and end-to-end CLI coverage
- Hardware config boundary cases, TLE cache logic, propagation edge cases, CLI bad-input paths

### Known limitations

- `eclipse_periods` field in ORF output is always empty — detection not yet implemented
- PDF report does not include the internal run log; full audit trail is in the JSON report only

### Upgrading

This is the first stable release. No migration needed.
