Great instinct — debug logs are the difference between a tool that's easy to maintain and one that's impossible to debug in production. Let me plan it out properly before we write any code.

---

## The problem with current logging

Right now OrbitVal uses raw `print()` statements scattered everywhere. That works for a demo but breaks down because:

- You can't turn them off in production
- You can't filter by severity
- You can't write them to a file
- You can't tell the difference between info, warnings, and errors
- They're inconsistent — some say `[orbitval]`, some don't

---

## The logging plan

**Three destinations:**
- **Terminal** — human readable, colored, concise
- **Log file** — every run gets its own log file in `reports/` alongside the JSON and PDF
- **Report** — key log events get embedded in the ORF JSON report for auditability

**Four levels, used consistently:**

| Level | When to use | Example |
|-------|-------------|---------|
| `DEBUG` | Internal state, values, decisions | `Cache hit for ISS (ZARYA), age 2.3h` |
| `INFO` | Normal progress milestones | `Propagating orbit...` |
| `WARNING` | Recoverable issues | `Using stale cache — Celestrak unreachable` |
| `ERROR` | Something failed but run continues | `Scenario gps_dropout failed to inject at t=120` |

**What gets logged where:**

```
Module              What gets logged
─────────────────────────────────────────────────────
tle.py              cache hit/miss, fetch success/fail,
                    stale cache fallback, TLE age

propagation.py      epoch, duration, step count,
                    any SGP4 warnings

comms_windows.py    stations checked, windows found,
                    blackout percentage

hardware_3u_schema  config path, validation errors,
                    schema version mismatch

injection.py        each fault activated, fields modified,
                    injection count per scenario

runner.py           scenario start/end, pass/fail,
                    failure reason, report paths

json_report.py      report id, integrity hash,
                    output path

pdf_report.py       output path, page count
```

**Log file naming:**
```
reports/
├── my_cubesat_2026-03-17_05-17-42.json
├── my_cubesat_2026-03-17_05-17-42.pdf
└── my_cubesat_2026-03-17_05-17-42.log   ← same stem, .log
```

Every run produces three files. The log is the raw audit trail of exactly what happened internally.

**Log format:**
```
2026-03-17 05:17:42 UTC | INFO    | tle          | Cache hit for 'ISS (ZARYA)', age 0.2h
2026-03-17 05:17:42 UTC | INFO    | propagation  | Propagating 60 steps over 1.0h from epoch 2026-03-16T20:53:41Z
2026-03-17 05:17:43 UTC | INFO    | comms        | Found 1 window over Rutgers NJ (max el: 11.66°)
2026-03-17 05:17:43 UTC | WARNING | comms        | 57/60 frames (95%) in comms blackout
2026-03-17 05:17:43 UTC | INFO    | runner       | Running scenario: gps_dropout
2026-03-17 05:17:43 UTC | DEBUG   | injection    | Fault gps_dropout active at t=120s, modified: gps_lat, gps_lon, gps_alt_km, gps_available
2026-03-17 05:17:43 UTC | INFO    | runner       | PASS — gps_dropout (primary: failover_to_dead_reckoning)
2026-03-17 05:17:44 UTC | INFO    | report       | JSON written: reports/my_cubesat_2026-03-17_05-17-42.json
2026-03-17 05:17:44 UTC | INFO    | report       | Integrity hash: 465f403a...
```

**What gets embedded in the ORF JSON report:**
```json
"run_log": [
    {"level": "INFO", "module": "tle", "msg": "Cache hit for 'ISS (ZARYA)', age 0.2h"},
    {"level": "WARNING", "module": "comms", "msg": "57/60 frames in comms blackout"},
    {"level": "INFO", "module": "runner", "msg": "PASS — gps_dropout"},
    {"level": "INFO", "module": "runner", "msg": "FAIL — sensor_noise: no response to noise"}
]
```

This means the ORF report is self-documenting — an insurer or launch provider can see not just the result but exactly what the tool did to produce it.

---

## Implementation plan

One new file: `orbitval/logging.py`

```
orbitval/logging.py    — central logger setup
                         get_logger(module_name) → logger
                         init_run_log(output_path) → sets up file handler
                         get_run_events() → returns embedded log for ORF report
```

Every module calls:
```python
from orbitval.logging import get_logger
log = get_logger("tle")

log.info("Cache hit for '%s', age %.1fh", satellite_name, age)
log.warning("Stale cache fallback — Celestrak unreachable")
log.debug("TLE epoch: %s", tle.epoch)
```

The CLI controls verbosity:
```bash
orbitval run ...              # INFO level — normal output
orbitval run ... --verbose    # DEBUG level — full internal state
orbitval run ... --quiet      # WARNING+ only — errors and warnings
```

---

## What NOT to log

- TLE line content (could contain sensitive mission data)
- Autonomy code internals (proprietary)
- File paths outside the project directory
- Any user data beyond what's already in the report

---

Ready to build `orbitval/logging.py` and wire it into every module?