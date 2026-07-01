# OrbitVal

**Autonomy stress testing for CubeSats — before launch, not after.**

OrbitVal is a local testing framework that runs standardized fault injection scenarios against your satellite's onboard autonomy software. You define your hardware, plug in your flight logic, and OrbitVal tells you exactly where it breaks — with a cryptographically verifiable report you can hand to your mission readiness review, launch provider, or insurer.

*No code leaves your machine. Ever.*

---

## Why OrbitVal

Most CubeSat teams validate autonomy through hardware-in-the-loop testing, manual scripts, and empirical launches. That means failure modes get discovered in orbit — where you can't fix them.

OrbitVal gives you a reproducible, automated way to find those failures on the ground:

- **GPS dropout** — does your autonomy switch to dead reckoning?
- **Power brownout** — does it enter safe mode before the battery dies?
- **Sensor noise** — does it detect degraded sensor quality and reduce operations?

Every run produces a structured JSON + PDF report with a SHA-256 integrity hash. The same report format — ORF (OrbitVal Report Format) — is designed to eventually become the standard artifact for satellite autonomy validation.

---

## Install

```bash
pip install orbitval
```

Or clone and install locally:

```bash
git clone https://github.com/ruhi-donda/OrbitVal.git
cd OrbitVal
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

---

## Quick start

```bash
# See available fault scenarios
orbitval list-faults

# Validate your satellite config
orbitval validate --config satellite.yaml

# Run a stress test — pre-launch mode (no TLE needed)
orbitval run --orbit-alt 550 --orbit-inc 53.0 \
  --scenarios gps_dropout power_brownout sensor_noise

# Run a stress test — live TLE fetch from Celestrak
orbitval run --tle-name "ISS (ZARYA)" \
  --scenarios gps_dropout power_brownout sensor_noise

# Run a stress test — manual TLE strings (offline/air-gapped)
orbitval run \
  --tle-line1 "1 25544U 98067A   24001.00000000 ..." \
  --tle-line2 "2 25544  51.6400 ..." \
  --scenarios gps_dropout power_brownout sensor_noise
```

**`orbitval list-faults` output:**

```
Available fault scenarios:

  [FREE] gps_dropout v1.0.0
         Complete GPS signal loss for a configurable duration. Tests whether
         autonomy code can maintain safe operation using dead reckoning or
         alternative navigation.

  [FREE] power_brownout v1.0.0
         Sudden reduction in battery charge and solar power input. Tests
         autonomous power management and safe mode triggering.

  [FREE] sensor_noise v1.0.0
         Amplified gaussian noise injected into magnetometer and GPS readings.
         Tests autonomy code robustness against degraded sensor quality.
```

---

## Define your satellite

Create a `satellite.yaml` file describing your 3U CubeSat hardware:

```yaml
schema_version: "1.0"
name: "My CubeSat"
form_factor: "3U"
mass_kg: 4.0

sensors:
  - type: GPS
    noise_sigma: 0.01
  - type: star_tracker
    noise_sigma: 0.005
  - type: magnetometer
    noise_sigma: 0.02

actuators:
  - type: reaction_wheel
    max_torque_nm: 0.001
  - type: magnetorquer
    max_torque_nm: 0.0005

power:
  battery_capacity_wh: 20.0
  solar_panel_area_m2: 0.06
```

Supported sensors: `GPS`, `star_tracker`, `magnetometer`, `sun_sensor`, `gyroscope`
Supported actuators: `reaction_wheel`, `magnetorquer`, `thruster`

Validate it before running:

```
$ orbitval validate --config satellite.yaml

✓ Config valid: satellite.yaml
  Satellite:   My CubeSat
  Form factor: 3U
  Mass:        4.0 kg
  Sensors:     ['GPS', 'star_tracker', 'magnetometer']
  Actuators:   ['reaction_wheel', 'magnetorquer']
  Battery:     20.0 Wh
```

---

## Plug in your autonomy code

Create a Python file with a class called `Autonomy` that implements two methods:

```python
# my_autonomy.py

class Autonomy:
    def process(self, telemetry) -> str:
        """
        Receive a telemetry frame and return a response string.
        OrbitVal evaluates your response to determine pass/fail.

        Safe responses: "safe_mode", "failover",
                        "failover_to_dead_reckoning",
                        "emergency_shutdown", "reduced_ops"
        Nominal response: "nominal"
        """
        if not telemetry.gps_available:
            return "failover_to_dead_reckoning"

        if telemetry.battery_charge_wh < 5.0:
            return "safe_mode"

        return "nominal"

    def reset(self):
        """Called between scenarios to reset internal state."""
        pass
```

Run OrbitVal with your autonomy code:

```bash
orbitval run --config satellite.yaml \
  --autonomy my_autonomy.py \
  --scenarios gps_dropout power_brownout sensor_noise
```

**Important:** Your autonomy code receives raw sensor data only. OrbitVal strips internal fault metadata before passing telemetry to your code — exactly as your software would run in orbit. You must detect faults from sensor values, not from OrbitVal flags.

---

## Orbit input modes

OrbitVal supports three ways to provide orbital context:

**Mode 1 — Live TLE** (default): fetches from [Celestrak](https://celestrak.org) and caches locally for 24 hours.

```bash
orbitval run --tle-name "LEMUR-2-JOSHUATREE"
```

**Mode 2 — Manual TLE strings**: for offline or air-gapped environments. Pass your TLE lines directly — no network access required.

```bash
orbitval run \
  --tle-line1 "1 25544U 98067A   24001.00000000  .00001000  00000+0  10000-4 0  999X" \
  --tle-line2 "2 25544  51.6400 100.0000 0001000  90.0000 270.0000 15.50000000    0X"
```

**Mode 3 — Pre-launch** (no TLE yet): OrbitVal synthesizes a circular orbit from your planned mission parameters.

```bash
orbitval run --orbit-alt 550 --orbit-inc 53.0
```

---

## Available fault scenarios

| Scenario | Tier | Description |
|----------|------|-------------|
| `gps_dropout` | FREE | Complete GPS signal loss for a configurable duration |
| `power_brownout` | FREE | Sudden reduction in battery charge and solar input |
| `sensor_noise` | FREE | Amplified gaussian noise injected into magnetometer and GPS |

Hardware-specific fault scenario packs (reaction wheel degradation, star tracker failures, etc.) are available for commercial operators. University CubeSat teams get everything free — use your `.edu` email.

---

## What a run looks like

```
$ orbitval run --orbit-alt 550 --orbit-inc 53.0 \
    --scenarios gps_dropout power_brownout sensor_noise

2026-07-01 03:20:30 UTC | INFO | Pre-launch mode — synthesizing orbit (alt=550km, inc=53.0°)
2026-07-01 03:20:30 UTC | INFO | Propagating 60 steps over 1.0h from epoch 2026-07-01T03:20:31Z
2026-07-01 03:20:30 UTC | INFO | Running scenario: gps_dropout
2026-07-01 03:20:30 UTC | INFO | Injection complete — 3 events recorded across 1 scenario(s)
2026-07-01 03:20:30 UTC | INFO | PASS — gps_dropout (primary: failover_to_dead_reckoning)
2026-07-01 03:20:30 UTC | INFO | Running scenario: power_brownout
2026-07-01 03:20:30 UTC | INFO | Injection complete — 4 events recorded across 1 scenario(s)
2026-07-01 03:20:30 UTC | INFO | PASS — power_brownout (primary: reduced_ops)
2026-07-01 03:20:30 UTC | INFO | Running scenario: sensor_noise
2026-07-01 03:20:30 UTC | INFO | Injection complete — 6 events recorded across 1 scenario(s)
2026-07-01 03:20:30 UTC | INFO | PASS — sensor_noise (primary: nominal)
2026-07-01 03:20:30 UTC | INFO | Generating reports...

==================================================
✓ Overall result:         PASS
  Certification eligible: True
  Integrity hash:         26fd754e75db0b2c2df1911b25c3b08d...
  Reports written to:     reports/
==================================================
```

Three files are written:

```
reports/
├── my_cubesat_2026-07-01_03-20-30.json   ← machine-readable ORF report
├── my_cubesat_2026-07-01_03-20-30.pdf    ← human-readable mission readiness report
└── my_cubesat_2026-07-01_03-20-30.log    ← full internal audit trail
```

The JSON report includes:

- Pass/fail result per scenario with autonomy response
- Full injection trace — every fault event with timestamp and modified fields
- Mission context — orbit type, altitude, inclination, hardware specs
- Comms window analysis — how much of the simulation had no ground contact
- `test_integrity_hash` — SHA-256 hash of all inputs and outputs

The integrity hash makes every ORF report a **verifiable attestation**. Any modification after generation invalidates the hash.

---

## CLI reference

```
orbitval list-faults
  List all available fault scenarios

orbitval validate --config <path>
  Validate a satellite.yaml config file

orbitval run
  --config <path>           satellite.yaml path (default: satellite.yaml)
  --scenarios <names>       fault scenarios to run
  --autonomy <path>         autonomy module .py file
  --tle-name <name>         satellite name for Celestrak fetch (Mode 1)
  --tle-line1 <string>      TLE line 1 for offline mode (Mode 2, use with --tle-line2)
  --tle-line2 <string>      TLE line 2 for offline mode (Mode 2, use with --tle-line1)
  --orbit-alt <km>          orbital altitude for pre-launch mode (Mode 3)
  --orbit-inc <deg>         orbital inclination for pre-launch mode (Mode 3)
  --duration <hours>        simulation duration (default: 1.0)
  --step <seconds>          telemetry time step (default: 60.0)
  --seed <int>              random seed for reproducibility (default: 42)
  --ground-station <spec>   name,lat,lon[,alt,min_el]
  --output <dir>            report output directory (default: reports/)
  --verbose                 show debug logs
  --quiet                   show warnings and errors only
```

---

## Architecture

OrbitVal is built on five modules:

```
orbital_engine    — SGP4 propagation via skyfield + astropy
hardware_model    — satellite.yaml config loader and validator
fault_library     — named, versioned fault scenario classes
injection_engine  — applies faults to telemetry, records trace
report_generator  — ORF-compliant JSON + PDF output
```

All orbital mechanics use [skyfield](https://rhodesmill.org/skyfield/) and [astropy](https://www.astropy.org/).
TLE data from [Celestrak](https://celestrak.org) with local caching and offline fallback.

---

## Roadmap

- [ ] Eclipse period detection
- [ ] Scenario config file (`scenario.yaml`)
- [ ] More fault scenarios (communication blackout, star tracker failure)
- [ ] Constellation simulation (multi-satellite)
- [ ] Optional cloud dashboard for report sharing

---

## Known limitations

- **Eclipse period detection** — the `eclipse_periods` field exists in every ORF report but is always empty. Detection is not yet implemented; if your autonomy code handles eclipse entry as a distinct fault mode, test it separately.
- **PDF audit trail** — the PDF report is a human-readable mission readiness summary. The full internal run log (every injected fault event, timestamped) is in the JSON report only.

---

## License

MIT

---

## About

OrbitVal is built on the belief that satellite autonomy validation should be standardized, reproducible, and accessible — not just for teams with large budgets and internal simulation infrastructure, but for every CubeSat team building the next generation of small satellites.

The OrbitVal Report Format (ORF) is designed to become the de facto standard for CubeSat autonomy validation — the artifact that mission readiness reviews, launch providers, and insurers expect to see.

Built by [Ruhi Donda](https://github.com/ruhi-donda).
