# OrbitVal — Map of Content

> The entry point for this repository.
> Read this first. Everything links from here.
> Last updated: 2026-03-16
>
> **Documentation lives in this folder.** From repo root, paths are `MAP.md`, `MANIFEST.md`, etc.

---

## What is this project?

OrbitVal is an installed local testing framework for CubeSat autonomy software. Teams install it as a Python package, define a satellite mission scenario and 3U CubeSat hardware configuration, and run standardized fault injection stress tests against their onboard autonomy code — entirely on their own machine. No code ever leaves their infrastructure. Output is a structured, reproducible test report suitable for mission readiness reviews.

---

## Documentation

All of these files live alongside this file. Keep the table below in sync whenever a doc is added, removed, or moved (see [UPDATE.md](UPDATE.md)).

| File | Purpose | Read when... |
|------|---------|--------------|
| [MAP.md](MAP.md) | This file — entry point | Always first |
| [ARCHITECTURE.md](ARCHITECTURE.md) | Why decisions were made | You want to understand the reasoning |
| [MANIFEST.md](MANIFEST.md) | What exists and where | You need to find something |
| [TEMPLATES.md](TEMPLATES.md) | How to add something new | You're building a new view/hook/service/model |
| [ROADMAP.md](ROADMAP.md) | Long-range product + business roadmap | You want the full phase-by-phase plan and success metrics |
| [UPDATE.md](UPDATE.md) | When and how to update each doc | Adding/moving files or changing architecture |
| [manifest.yaml](manifest.yaml) | Internal connections map (parseable YAML) | Wiring overview; what connects to what; AI/tooling parse |
| [TODO.md](TODO.md) | Running task list (ordered + misc) | Day-to-day tasks; what to do next |
| [AUDIT.md](AUDIT.md) | Phase/readiness audit template | Before a major feature, refactor, or Phase 2 |

---

## Docs at a glance

```
./
├── MAP.md                  this file — entry point
├── ARCHITECTURE.md         ADRs, philosophy, glossary
├── MANIFEST.md             file map, data flow, connections (rich, linked)
├── manifest.yaml           internal connections map (parseable schema)
├── TEMPLATES.md            contracts, view/hook/service/model templates
├── ROADMAP.md              long-range roadmap (phases, metrics, timelines)
├── UPDATE.md               checklists for when to update each doc
├── TODO.md                 ordered refactors + misc / backlog
└── AUDIT.md                phase/readiness audit template
```

---

## Codebase at a glance

Proposed repo layout (installable Python package; optional future cloud dashboard):

```
orbitval/
├── __init__.py
├── cli.py                         local runner (scenarios, faults, reports)
├── config/
│   ├── scenario_schema.py         scenario config model + validation
│   └── hardware_3u_schema.py      3U CubeSat hardware config model + validation
├── orbits/
│   ├── tle.py                     Celestrak fetch + TLE parsing/caching
│   ├── propagation.py             poliastro propagation + ground track
│   └── comms_windows.py           ground station visibility windows
├── faults/
│   ├── catalog.py                 registry of named fault scenarios
│   └── scenarios/                 documented scenario pack(s)
├── engine/
│   ├── runner.py                  executes user autonomy code under test
│   └── injection.py               applies faults to telemetry/time-series
├── reporting/
│   ├── json_report.py             structured machine-readable report
│   └── pdf_report.py              mission readiness PDF output
└── types.py                       shared domain types

tests/
docs/ (optional)
scripts/

cloud-dashboard/ (future; optional)
├── frontend/                      React dashboard (results + report sharing)
└── backend/                       FastAPI API for storing configs/results only
```

---

## Architecture in one paragraph

OrbitVal is a local-first Python package that runs orbital simulation and standardized fault-injection stress tests against user-provided autonomy code on the user’s machine. Scenarios and 3U CubeSat hardware configurations are defined via config files (validated against schemas), orbits are propagated with poliastro + astropy using TLEs from Celestrak (or user-provided parameters), and the engine executes named fault scenarios to produce deterministic, reproducible outcomes. Results are emitted as structured JSON plus a PDF report for mission readiness reviews; a future optional cloud dashboard will visualize and share **only** scenario configs and test outputs, never proprietary flight code.

---

## Current build phase

```
Phase 1    ■   MVP (local sim engine, 3U hardware config, fault injection, JSON+PDF reporting)
Phase 2    □   Expanded fault packs + regression runs + scenario libraries (local)
Phase 3    □   Optional cloud dashboard (SaaS) for results/configs only
```

---

## Active branch

```
Branch:   main
Focus:    Phase 1 (MVP)
Next:     Implement TLE/orbital params → propagation → comms windows → report
```

---

## ADR summary

Decisions are captured in [ARCHITECTURE.md](ARCHITECTURE.md).

| ADR | Decision | Why |
|-----|----------|-----|
| ADR-001 | Local-first installed test framework | Keep proprietary autonomy code on user infrastructure; reduce integration friction |
| ADR-002 | Use poliastro + astropy for orbit propagation | Trusted libraries; clear units/time handling and established orbital primitives |
| ADR-003 | Source TLEs from Celestrak | Standard public distribution; easy to fetch/update and validate |
| ADR-004 | Open-core + paid fault packs/reporting | Sustain development while keeping core accessible (free for universities) |

---

## Planned features

- [ ] Additional documented fault scenario packs (paid add-ons; free for university teams)
- [ ] Regression runner (repeatable campaigns; compare reports across versions)
- [ ] Scenario library management (local)
- [ ] Optional cloud dashboard for visualizing/sharing reports and scenario configs (no proprietary code)

---

## Company vision

OrbitVal aims to become a **standardization company** for autonomy stress testing. The long-term goal is for the **OrbitVal Report Format (ORF)** to become the expected artifact for mission readiness reviews, launch providers, and satellite insurers — turning OrbitVal usage into a compliance checkbox rather than a purchasing decision.

At a high level:

- The **tool** earns trust through local-first execution and strong engineering.
- The **format (ORF)** becomes an open, community-governed standard modeled on OpenAPI/FHIR.
- The **certification layer** creates recurring revenue via OrbitVal-certified badges recognized by insurers and launch providers.

See [ARCHITECTURE.md](ARCHITECTURE.md) for the full long-term strategic thesis and growth phases.

---

## Non-goals (v1)

High-level non-goals for OrbitVal v1 (see [ARCHITECTURE.md](ARCHITECTURE.md) for details):

- Constellation-level simulation and higher-fidelity perturbation modeling.
- Support for non-3U hardware form factors.
- Real-time or GUI-based operation (CLI and Python APIs only).

---

## Known limitations (v1)

Summary of key limitations (see [ARCHITECTURE.md](ARCHITECTURE.md) for full list):

- SGP4-based propagation is tuned for LEO and not suitable for precise maneuver planning.
- The power and thermal model is simplified.
- Faults assume independent sensors and do not yet model correlated failures.

---

## For AI assistants

> If you are an AI reading this:
> 1. Read MAP.md first — you are here
> 2. Read [MANIFEST.md](MANIFEST.md) to locate specific files
> 3. Read [TEMPLATES.md](TEMPLATES.md) before writing any new code
> 4. Read [ARCHITECTURE.md](ARCHITECTURE.md) only to understand a specific decision
> 5. Do NOT scan the entire codebase — use MANIFEST.md links to jump directly
> 6. All new code must satisfy the contracts in TEMPLATES.md
> 7. When you create or move files, update MAP.md and MANIFEST.md per [UPDATE.md](UPDATE.md) ("When you create or move files")
> 8. Keep `MANIFEST.md` and `manifest.yaml` synchronized when wiring changes.
