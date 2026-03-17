# OrbitVal — Architecture

> The WHY behind every decision.
> For WHAT exists and WHERE, see [MANIFEST.md](MANIFEST.md).
> For HOW to add something new, see [TEMPLATES.md](TEMPLATES.md).
> Entry point: [MAP.md](MAP.md).

---

## Philosophy

- **Local-first by design.** OrbitVal runs on the user’s machine; proprietary autonomy code never leaves their infrastructure.
- **Simulation correctness over UX cleverness.** If propagation or units are wrong, everything downstream (faults, reports, decisions) is wrong.
- **Explicit interfaces at boundaries.** The boundary is “user autonomy code ↔ OrbitVal harness” and “config ↔ engine”; both must be explicit and versioned.
- **Units and time are always explicit.** Use astropy units/time and a clear epoch; avoid unitless floats in orbital math code paths.
- **Determinism when possible.** Stress tests support seeded randomness for reproducible failures.
- **Hardware scope stays tractable.** v1 targets a 3U CubeSat standard configuration only; expand later with ADRs and versioned schemas.
- **Observability is part of the product.** Runs produce structured results (inputs, seed, fault scenario, anomalies, artifacts) for debugging and regression.

---

## Internal connections map (manifest)

We keep two complementary views of **what connects to what**:

| Artifact | Role | Consumed by |
|----------|------|-------------|
| [MANIFEST.md](MANIFEST.md) | Rich, link-heavy map: files, data flows, planned connections | Humans and AI reading the repo |
| [manifest.yaml](manifest.yaml) | Same wiring in parseable YAML: views, hooks/contexts, services, planned | Tools and AI that need to parse structure |

**Rules:** When a view, hook/context, service, or connection is added/removed/changed, update both MANIFEST.md and manifest.yaml so they stay in sync.

---

## Architecture Decision Records
### ADR-001: Local-first installed testing framework (no proprietary code leaves)

**Status:** Accepted

**Problem:**  
CubeSat teams need a standardized way to stress-test autonomy software without shipping proprietary code or telemetry pipelines to a third-party service. They also need artifacts suitable for mission readiness reviews.

**Options considered:**  
- Option A: Cloud-first SaaS that runs autonomy code in hosted infrastructure
- Option B: Local installed framework that runs entirely on the user’s machine

**Decision:**  
OrbitVal is delivered as an installable Python package. All execution (simulation, injection, and autonomy code under test) runs locally. A future cloud dashboard, if added, will accept only scenario configs and test outputs/reports — never proprietary autonomy code.

**Consequences:**  
- Strong security posture and easier adoption for constrained teams.
- Requires a clear harness contract for integrating user autonomy code locally.
- Cloud value is additive (visualization/sharing), not required for core function.

---

### ADR-002: Use skyfield + astropy for orbital mechanics

**Status:** Accepted (supersedes poliastro decision)

**Problem:**
We need orbit propagation and frame/unit-safe computations for TLE-driven 
scenarios and orbital-parameter scenarios, plus ground track and comms 
window calculations.

**Options considered:**
- Option A: poliastro + astropy — unmaintained since 2023, known 
  compatibility issues with Python 3.12+, not future-proof
- Option B: skyfield + astropy — actively maintained, Python 3.13 
  compatible, production-proven, clean TLE propagation API
- Option C: Hand-roll propagation math — high risk of unit/time bugs

**Decision:**
Use skyfield for TLE loading, propagation, and ground track computation.
Use astropy for unit handling where needed. Skyfield is actively maintained,
compatible with Python 3.13, and sufficient for all v1 LEO requirements.

**Consequences:**
- No poliastro dependency — eliminates a major maintenance risk
- Slightly less built-in orbital maneuver planning, but that is out 
  of scope for v1 anyway
- Cleaner, more readable propagation code
---

### ADR-003: Use Celestrak as a supported TLE source

**Status:** Accepted

**Problem:**  
We need a stable, widely used source for up-to-date TLEs, while still supporting fully offline/air-gapped usage.

**Options considered:**  
- Option A: Require users to paste/provide TLEs only (fully offline)
- Option B: Support fetching from a canonical public feed (Celestrak) with caching; allow offline override

**Decision:**  
Support Celestrak TLE fetching with caching, and allow direct TLE input for offline use.

**Consequences:**  
- Better UX for connected environments.
- Requires sensible caching and explicit “offline mode” behavior.

---

### ADR-004: Open-core business model (paid fault packs + reporting tools)

**Status:** Accepted

**Problem:**  
We want a widely adopted core framework, while funding sustained development and high-quality, documented fault scenarios and reporting.

**Options considered:**  
- Option A: Fully open source with donations only
- Option B: Fully closed source licensing
- Option C: Open core with paid add-ons

**Decision:**  
Use an open-core model: core framework is free and open source; advanced fault scenario packs and reporting tools are paid. Free licensing is available for university CubeSat teams, with paid licensing for commercial operators.

**Consequences:**  
- Keeps core accessible while funding advanced content and tooling.
- Requires clear boundaries between core and paid packs (pack format, compatibility).

---

#### Free vs paid boundary (fault scenarios)

| Tier | Examples | Description |
|------|----------|-------------|
| **Free (generic faults)** | RF interference; power brownout; generic sensor noise; GPS signal dropout; communication blackout during eclipse | Hardware-agnostic faults that can be expressed without knowledge of a specific vendor’s behavior or proprietary specs. |
| **Paid (hardware-specific faults)** | Reaction wheel bearing degradation (vendor-specific torque curves); star tracker lost-in-space recovery failure; specific solar panel degradation models; battery cell failure under specific thermal conditions | Faults that depend on detailed, vendor-specific behavior, calibration data, or specifications. |

**Boundary rule:** if a fault requires knowledge of a specific hardware vendor’s behavior or specifications, it belongs in the **paid** tier. If it can be modeled generically without vendor secrets, it belongs in the **free** tier.

---

### ADR-005: Tooling choices (poliastro vs OreKit/GMAT; cloud stack)

**Status:** Accepted

**Problem:**  
We need orbital and cloud tooling that matches the Python-centric ecosystem of aerospace autonomy teams and keeps lock-in manageable.

**Options considered (orbital):**  
- skyfield + astropy (Python-native)
- OreKit (Java; wrong runtime/language for our users)
- GMAT (GUI-first; no clean Python API)

**Decision (orbital):**  
Use skyfield + astropy; ...

**Options considered (cloud):**  
- Single-provider PaaS (e.g. all-in-one Heroku-like)
- React + FastAPI split hosted on Vercel (frontend) and Render (backend)

**Decision (cloud):**  
Plan for a React dashboard on Vercel and a FastAPI report API on Render, both using free/low-cost tiers initially. This allows independent scaling of UI and API and avoids single-provider lock-in. The cloud layer only ingests test outputs and scenario configs, never autonomy code.

**Consequences:**  
- Aligns with Python-heavy teams (no Java/GUI runtime dependency).
- Keeps future dashboard flexible and cost-efficient.
- Enforces a strict “outputs/configs only” boundary for any hosted components.

---

## Glossary

| Term | Definition |
|------|-------------|
| **TLE** | Two-Line Element set used to describe an Earth-orbiting object’s orbit; used as input to initialize a propagated orbit. |
| **Ground track** | The projection of the satellite’s subpoint (lat/long) on Earth over time, derived from orbit propagation. |
| **Scenario** | A mission definition: orbit source/type, ground stations, duration, sampling rate, and run parameters. |
| **Telemetry** | Time-series sensor and state data produced by simulation (position, velocity, attitude, sensor readings). |
| **Injection** | A controlled perturbation applied to telemetry (noise, bias, dropout) or system behavior (simulated faults). |
| **Anomaly** | A flagged response or behavior from onboard autonomy logic that violates expected constraints or rules. |
| **Seed** | Random seed used to make stress tests reproducible. |
| **Fault scenario pack** | A named, documented collection of injectable faults and expected behaviors; may be core (free) or advanced (paid). |
| **3U CubeSat** | A CubeSat form factor (approximately 10×10×30 cm) used as the initial supported hardware configuration model in v1. |
| **Comms window** | Time interval when a satellite is visible to a ground station given orbit propagation and constraints (e.g., elevation mask). |

---

## Non-goals (v1)

- Atmospheric drag modeling and higher-order perturbations (J2 and beyond) are intentionally out of scope.
- Multi-satellite constellation simulation is out of scope.
- Hardware form factors other than the 3U CubeSat standard configuration are out of scope for v1.
- Network-dependent autonomy code (e.g., cloud-coupled decision loops) is not supported.
- Real-time simulation is not a goal; batch-only runs are prioritized for determinism.
- GUI-based usage is out of scope; CLI and Python APIs are the primary interfaces.
- Hardware-in-the-loop testing is out of scope; OrbitVal assumes simulated hardware models.

---

## Known limitations (v1)

- Orbital propagation uses SGP4, which is well-suited for LEO analysis but not for high-fidelity maneuver planning or long-duration GEO/HEO campaigns.
- The power budget model is simplified and does not include detailed thermal modeling or fine-grained EPS dynamics.
- Fault scenarios assume sensor independence; correlated failures and cascading cross-subsystem effects are not modeled in v1.
- Orbit and hardware models are tuned for 3U CubeSat configurations; applying them to other form factors may produce misleading results.

---

## Long-term strategic thesis

OrbitVal’s strongest long-term position is as a **standardization company**. The goal is for the **OrbitVal Report Format (ORF)** to become the de facto standard that mission readiness reviews, launch providers, and satellite insurers expect to see — making OrbitVal usage a compliance checkbox, not a purchasing decision.

### The three layers

- **Layer 1: The tool** — earns trust through local-first execution, strong engineering, and clear boundaries around proprietary code.
- **Layer 2: The format (ORF)** — the ORF spec is published as an open standard, community governed, modeled on OpenAPI and FHIR, and usable independently of the OrbitVal implementation.
- **Layer 3: The certification** — an OrbitVal-certified badge recognized by insurers and launch providers, creating recurring revenue that is independent of free-tier usage.

### Growth phases

- **Phase 1: University adoption** — become the standard teaching tool for CubeSat autonomy and mission readiness.
- **Phase 2: Format establishment** — publish the ORF spec openly and encourage third-party tools to consume and produce it.
- **Phase 3: First institutional endorsement** — secure at least one satellite insurer or launch provider that recognizes ORF as an acceptable or preferred artifact.
- **Phase 4: Certification revenue** — the OrbitVal certification badge becomes expected for payload approval or insurance underwriting.
- **Phase 5: Consortium governance** — transfer ORF format governance to an independent body and launch the cloud dashboard as a first-party, ORF-native viewer.

### Institutional targets (priority order)

1. Satellite insurers (e.g., Lloyd’s, Marsh McLennan, Starr Companies)
2. Launch providers (e.g., SpaceX, Rocket Lab, Arianespace)
3. Space agencies and regulatory bodies (e.g., NASA, ESA, national regulators)
4. Large commercial constellation operators and bus manufacturers

These targets inform how conservative OrbitVal must be about stability, transparency, and auditability of the ORF spec and the underlying tooling.

---

## Related documents

- [MAP.md](MAP.md) — entry point
- [MANIFEST.md](MANIFEST.md) — file map and connections
- [manifest.yaml](manifest.yaml) — same connections in parseable YAML
- [TEMPLATES.md](TEMPLATES.md) — how to add new things
- [UPDATE.md](UPDATE.md) — when to update each doc

## ORF Spec — Report Format Fields

The OrbitVal Report Format (ORF) is the canonical output schema for every
OrbitVal test run. It is designed to be self-describing — an insurer or
launch provider must be able to understand the mission and test results
without reading any separate documentation.

### Why test_integrity_hash matters
This field is a SHA-256 hash of all test inputs and outputs. It transforms
an ORF report from a structured document into a verifiable attestation —
a report that cannot be manually edited after the fact. This is the field
that makes insurers and launch providers trust the report without needing
to audit the test themselves.

### Why mission context fields matter
An insurer or launch provider must understand the mission independently
of OrbitVal. The report must be self-describing. "3U" tells you the size,
not the capability or risk profile. Mission context fields provide the
full picture.

### Required fields
```json
{
  "orbitval_version": "string",
  "orf_spec_version": "string",
  "schema_version": "1.0",
  "report_id": "UUID",
  "generated_at": "ISO 8601 timestamp",
  "test_integrity_hash": "SHA-256 of all inputs + outputs",

  "mission_profile": {
    "orbit_type": "string (LEO, SSO, etc.)",
    "altitude_band_km": "float",
    "inclination_deg": "float",
    "operational_lifetime_years": "float"
  },
  "regulatory_jurisdiction": "string (e.g. FCC, ITU, ESA)",
  "applicable_standard": "string (e.g. none declared)",
  "hardware_generation": "string (e.g. COTS-2023)",
  "form_factor": "3U",

  "scenarios_run": [
    {
      "name": "string",
      "version": "string",
      "result": "PASS | FAIL | SKIP",
      "duration_s": "float",
      "seed": "integer",
      "autonomy_response": "string",
      "fault_trace": ["array of applied fault events"]
    }
  ],
  "overall_result": "PASS | FAIL",
  "certification_eligible": "boolean"
}
```

---

## Long-term Entity Structure

### OrbitVal Inc (commercial entity)
- Builds and maintains the tooling
- Sells advanced scenario packs
- Operates the cloud dashboard
- Issues certification badges (early stage)
- For-profit, founder-owned

### ORF Foundation (future non-profit/consortium)
- Owns and governs the ORF spec
- Operates the hash registry (append-only, publicly queryable)
- Issues certifications (long-term)
- Governed by a board including insurers, launch providers,
  universities, and OrbitVal Inc as founding member
- Modeled on: OpenAPI Initiative, Linux Foundation, HL7 (FHIR)

### Hash registry design
- Append-only public ledger of report hashes
- Once a hash is registered it cannot be changed or deleted
- Modeled on Certificate Transparency (SSL certificate auditing)
- Does NOT require blockchain — a simpler append-only log achieves
  the same trust properties with less overhead
- Insurers query: "is this hash registered and does it match a
  valid OrbitVal run?"
- OrbitVal never sees proprietary autonomy code — only the hash
  of the outputs

### Sequencing
The foundation cannot be created before OrbitVal has earned
institutional credibility. The realistic sequence is:

1. Build tool, get university adoption
2. Get one institutional reference (insurer or launch provider)
3. Spin out foundation with institutional co-founders on the board
4. Transfer spec governance and registry to the foundation
5. OrbitVal Inc becomes the premier commercial tooling provider
   for the standard it founded

---

### ADR-006: Separate open standard governance from commercial entity

**Status:** Accepted

**Problem:**
A standard owned by a for-profit company will face institutional
resistance. Insurers, launch providers, and agencies will not want
their workflows dependent on a single startup's proprietary format.

**Options considered:**
- Option A: Keep spec governance inside OrbitVal Inc
- Option B: Spin out ORF governance to an independent foundation
  with institutional co-founders on the board

**Decision:**
Option B. The ORF Foundation governs the spec and operates the
registry. OrbitVal Inc is the founding member and premier commercial
tooling provider. The standard is neutral. The tooling is commercial.

**Consequences:**
Requires eventually transferring spec governance — complex to manage
but necessary for institutional credibility at scale. Modeled on how
Linux, OpenAPI, and FHIR achieved universal adoption while commercial
entities built sustainable businesses around them.
