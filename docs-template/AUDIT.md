# OrbitVal — Architecture Audit (Readiness for next phase)

> Use this doc to audit the existing architecture before a major feature or phase.
> Fill in the sections below (or add your own) so you have a clear list of refactors and compatibility checks.
> Entry point: [MAP.md](MAP.md).

---

## Scope

- **Goal:** Assess readiness for Phase 2 (advanced fault packs + regression runs) and Phase 3 (optional cloud dashboard for outputs/configs only).
- **Areas:** local-first boundary integrity, reproducibility, pack/versioning strategy, config schema evolution, report schema stability, offline mode, and harness interface for autonomy code under test.

---

## 1. Current state summary

| Area | Documented (MANIFEST / TEMPLATES) | Actual code |
|------|-----------------------------------|-------------|
| Local-first guarantee | Proprietary autonomy code runs locally only; no uploads | Verify runner never transmits code/telemetry; audit dependencies for outbound calls |
| Reproducibility | Reports record inputs + seed + versions | Confirm seed is threaded through all faults and recorded; confirm configs are embedded or referenced immutably |
| 3U hardware scope | Only 3U CubeSat model in v1 | Confirm schema enforces 3U-only; document extension strategy for later |
| Fault packs | Named, documented scenarios; packs are versioned | Confirm pack format, discovery, and compatibility rules exist |
| Reporting | JSON + PDF suitable for readiness review | Confirm JSON schema_version; PDF generation determinism; artifacts manifest completeness |

**Conclusion:** Phase 2/3 readiness hinges on strict boundary control (no proprietary code leaves), strong versioning (schemas + packs + report format), and deterministic execution (seeded faults and stable harness). Any drift here should be treated as a release blocker for advanced packs and for the optional cloud layer.

---

## 2. Critical findings

### Finding 1: Harness boundary is underspecified

**Risk:** Without a clear “autonomy code under test” contract, teams will integrate ad-hoc and results won’t be comparable across runs/teams.  
**Recommendation:** Define a stable harness interface and version it; ensure reports record harness version and adapter details.  
→ Reference: [TEMPLATES.md](TEMPLATES.md) (contracts), [MANIFEST.md](MANIFEST.md) (engine/runner)

### Finding 2: Pack/versioning strategy must be locked before selling add-ons

**Risk:** Paid fault packs will fracture if pack metadata, compatibility, and parameter schemas aren’t standardized.  
**Recommendation:** Define a pack manifest format (name, version, required OrbitVal version, parameter schema references) and enforce it in `faults/catalog`.  
→ Reference: [ARCHITECTURE.md](ARCHITECTURE.md) (ADR-004), [manifest.yaml](manifest.yaml)

### Finding 3: Offline mode must be first-class

**Risk:** Some teams operate in air-gapped environments; any hidden network dependency breaks the value proposition.  
**Recommendation:** Add explicit offline mode configuration and verify all code paths behave deterministically with local inputs/cache. Record “offline mode” in reports.  
→ Reference: `orbitval/orbits/tle.py`, `manifest.yaml` env keys

---

## 3. Data / format compatibility

- **Current:** Test outputs are structured JSON + PDF; faults are named scenarios with parameters; configs are file-based and validated.
- **Required for next phase:** Stable versioned JSON report schema and stable pack metadata schema so results can be compared across versions and optionally visualized in a cloud dashboard.
- **Gap:** Ensure the JSON report includes explicit schema_version, OrbitVal version, pack versions, and a normalized representation of scenario/hardware inputs (or immutable references/hashes).

---

## 4. Recommended refactor order

1. **Define and version the harness contract** — make user autonomy integration explicit and testable.
2. **Lock report schema_versioning** — ensure JSON/PDF outputs are stable and reproducible.
3. **Standardize fault pack manifests** — enforce compatibility rules before scaling packs.
4. **Harden offline mode** — explicit behavior + report annotation.

Copy these into [TODO.md](TODO.md) when converting audit findings into build tasks.

---

## 5. Compatibility matrix *(optional)*

| Concern | Mode A | Mode B | Mode C |
|---------|--------|--------|--------|
| Data format | Local run JSON/PDF | Regression campaign JSON/PDF | Cloud dashboard ingest JSON/configs |
| Apply path | Same pack + harness contract | Same pack + harness contract | Read-only visualization (no autonomy code) |

---

## References

- [MANIFEST.md](MANIFEST.md) — file map, data flow, planned connections  
- [manifest.yaml](manifest.yaml) — modules/services/phases/planned  
- [ARCHITECTURE.md](ARCHITECTURE.md) — ADRs and philosophy  
- [TEMPLATES.md](TEMPLATES.md) — contracts  
- [TODO.md](TODO.md) — track refactors here

---

## Related documents

- [MAP.md](MAP.md) — entry point  
- [TODO.md](TODO.md) — build order + backlog  
- [ARCHITECTURE.md](ARCHITECTURE.md) — ADRs  
- [MANIFEST.md](MANIFEST.md) — file map and connections  
- [manifest.yaml](manifest.yaml) — connections in YAML
