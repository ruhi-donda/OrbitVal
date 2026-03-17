# OrbitVal — TODO

> Running task list: ordered refactors (from an audit or plan) plus misc items to keep in mind.
> Check off as you go; add new items under Misc / backlog. Cross-references point to the doc or file that has the detail.
> Entry point: [MAP.md](MAP.md).

---

## Phase 1 (MVP) — build order

- [ ] **1. Define config schemas (scenario + hardware_3u)**  
  Validation, defaults, and schema_versioning for reproducible runs.  
  → Detail: [ARCHITECTURE.md](ARCHITECTURE.md) (contracts + ADRs)  
  → Files: `orbitval/config/`

- [ ] **2. Orbital simulation engine (TLE + orbital params)**  
  Propagation with poliastro + astropy; ground track + comms windows.  
  → Files: `orbitval/orbits/`

- [ ] **3. Fault catalog + core scenario pack**  
  Named, documented faults (GPS dropout, reaction wheel degradation, corrupted star tracker during eclipse).  
  → Files: `orbitval/faults/`, `orbitval/faults/scenarios/`

- [ ] **4. Injection engine + runner harness contract**  
  Deterministic injection (seed) + stable harness interface for user autonomy code.  
  → Files: `orbitval/engine/`

- [ ] **5. Reporting (JSON + PDF)**  
  Structured pass/fail + artifacts manifest; PDF suitable for mission readiness review.  
  → Files: `orbitval/reporting/`

- [ ] **6. CLI surface (pip-installed workflow)**  
  `orbitval validate-config`, `orbitval list-faults`, `orbitval run`, `orbitval report`.  
  → Files: `orbitval/cli.py`

---

## Misc / backlog

Drop one-off tasks and ideas here. Move to “Ordered refactors” or a phase plan when they become part of a sequence.

- [ ] Add “offline mode” ergonomics and documentation (Celestrak cache prefill)  
  → Files: `orbitval/orbits/tle.py`
- [ ] Define a standard “3U default baseline” hardware preset config for quick starts  
  → Files: `orbitval/config/hardware_3u_schema.py`
- [ ] Add regression runner concept (campaigns + diffing) to Phase 2 plan  
  → Docs: [manifest.yaml](manifest.yaml)

---

## When to update this doc

- **Check off** items when done.
- **Add** one-off tasks under Misc / backlog; promote to a phase section or `manifest.yaml` planned phases when scoped.
- **Sync** with [AUDIT.md](AUDIT.md) if the recommended build/refactor order changes.
- See [UPDATE.md](UPDATE.md) for when to update other docs after completing tasks.

---

## Related documents

- [MAP.md](MAP.md) — entry point
- [AUDIT.md](AUDIT.md) — audit/readiness template
- [MANIFEST.md](MANIFEST.md) — file map; update when new files or connections appear
- [manifest.yaml](manifest.yaml) — phases and planned additions
- [TEMPLATES.md](TEMPLATES.md) — contracts when adding modules/faults/reports
- [UPDATE.md](UPDATE.md) — when to update each doc
