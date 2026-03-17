# OrbitVal — Documentation

OrbitVal is an installed local testing framework for CubeSat autonomy software. Teams install it as a Python package, define a mission scenario and 3U CubeSat hardware configuration, and run standardized fault injection stress tests against their onboard autonomy code — entirely on their own machine. No code ever leaves their infrastructure. Output is a structured, reproducible test report suitable for mission readiness reviews.

---

## Business model

- **Open core**: core framework is free and open source.
- **Free tier**: generic, hardware-agnostic fault scenarios (e.g. RF interference, power brownouts, sensor noise).
- **Paid tier**: hardware-specific fault scenario packs and advanced reporting tools.
- **Dividing principle**: generic faults are free; hardware-specific faults are paid.
- **University exemption**: self-serve, verified via `.edu` email; perpetually free.
- **Commercial operators**: per-seat licensing.

---

## Future: optional cloud dashboard

OrbitVal may add a cloud dashboard layer (SaaS) later for visualizing test results, sharing reports across teams, and storing scenario libraries. The cloud layer never touches proprietary satellite code — only test outputs and scenario configs. It is planned to run as a React frontend on Vercel and a FastAPI backend on Render so the dashboard and report API can scale independently, while avoiding single-provider lock-in.

---

## Stack

- **Core**: Python package (installable via pip) — matches the language most aerospace autonomy teams already use.
- **Orbital mechanics**: poliastro + astropy — chosen over OreKit (Java ecosystem) and GMAT (GUI-oriented, no Python API) because it is Python-native, actively maintained, and sufficient for LEO propagation at v1 fidelity.
- **TLE data**: Celestrak — primary public TLE source; planned fallback to Space-Track.org (requires free account), with manual TLE string input always supported.
- **Fault injection engine**: Python — integrates naturally with user autonomy code.
- **Reporting**: structured JSON (machine-readable) + PDF (human-readable) output.
- **Future cloud dashboard**: React frontend + FastAPI backend, hosted on Vercel (frontend) and Render (backend), ingesting only configs + test outputs.

---

## Phase 1 scope (MVP)

1. **Orbital simulation engine** — input TLE or orbital parameters, propagate orbit using poliastro, compute ground track and comms windows
2. **Hardware config model** — define a 3U CubeSat’s sensors, actuators, and power budget in a config file
3. **Fault injection engine** — library of named, documented fault scenarios (e.g. GPS dropout, reaction wheel degradation, corrupted star tracker data during eclipse) injected against the user’s autonomy code
4. **Test report output** — structured pass/fail report with reproducible test cases in JSON and PDF format

---

## Non-goals (v1)

- No atmospheric drag or higher-order perturbation modeling (J2 and beyond out of scope).
- No multi-satellite constellation simulation.
- No hardware form factors other than the 3U CubeSat standard configuration.
- No network-dependent autonomy code support (assume local, offline-capable autonomy).
- No real-time simulation — batch-only runs for deterministic, replayable tests.
- No GUI — CLI and Python API only for v1.
- No hardware-in-the-loop faults — scenarios assume simulated sensors/actuators only.

---

## Known limitations (v1)

- Orbital propagation uses SGP4: sufficient for LEO but not for high-fidelity maneuver planning.
- Power budget model is simplified (no thermal modeling or detailed EPS dynamics).
- Fault scenarios assume sensor independence; correlated failures are not modeled in v1.

## Documentation index

Start with [MAP.md](MAP.md), then use:

- [MANIFEST.md](MANIFEST.md) for the file map and data flows
- [manifest.yaml](manifest.yaml) for parseable wiring and phase planning
- [ARCHITECTURE.md](ARCHITECTURE.md) for ADRs, philosophy, and glossary
- [TEMPLATES.md](TEMPLATES.md) for contracts and templates
- [ROADMAP.md](ROADMAP.md) for the phase-by-phase product + business roadmap
- [TODO.md](TODO.md) for build order and backlog
- [AUDIT.md](AUDIT.md) before Phase 2/3 work or major refactors
- [UPDATE.md](UPDATE.md) for doc maintenance checklists

---

## Docs files

| File | Purpose |
|------|---------|
| MAP.md | Entry point; project summary; doc index; codebase tree; phases |
| MANIFEST.md | File map, data flow, connections, planned features |
| manifest.yaml | Parseable wiring: modules, services, phases |
| ARCHITECTURE.md | Philosophy, ADRs, glossary |
| TEMPLATES.md | Contracts + module/fault/report templates |
| ROADMAP.md | Long-range roadmap (phases, metrics, timelines) |
| UPDATE.md | When to update each doc; new file/connection/ADR checklists |
| TODO.md | Phase build order + misc backlog |
| AUDIT.md | Phase-readiness audit template |
