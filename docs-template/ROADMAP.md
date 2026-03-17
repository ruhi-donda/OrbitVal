# OrbitVal — Roadmap

> Long-range product + business roadmap.
> This document is expected to change; keep it in sync with `MAP.md`, `TODO.md`, and `manifest.yaml` as the plan evolves.
> Entry point: [MAP.md](MAP.md).

---

## The honest timeline (one view)

```
Now          → Phase 0: Build MVP, 10 university users
Year 1       → Phase 1: Traction, first paying customer, ORF spec published
Year 2-3     → Phase 2: Institutional credibility, seed round, first endorsement
Year 3-5     → Phase 3: Standard status, Foundation spun out, Series A
Year 5-7     → Phase 4: Infrastructure layer, Series B
Year 7+      → Phase 5: Permanence, exit options open
```

---

## Phase 0 — Foundation (Now, while you're at Rutgers)

**Goal:** Build the MVP and prove the tool works.  
**Status:** You are here.

### Product
- Build the 5 core modules: `orbital_engine`, `hardware_model`, `fault_library`, `test_runner`, `report_generator`
- Ship a working pip-installable Python package
- Support 3U CubeSat only
- CLI interface only, no GUI
- Output: JSON report with `test_integrity_hash` and mission context fields baked in from day one
- Publish to GitHub as open source
- Write genuinely good documentation and tutorials

### Business
- Register OrbitVal as an LLC (cheap, fast, protects your IP)
- Open a business bank account
- File a provisional patent on the fault injection methodology (cheap, buys you 12 months)
- Domain: `orbitval.com`

### Users
- Target 10 university CubeSat teams
- Give it away completely free
- Sit with them, watch them use it, understand their pain
- Ask every single one: what would make this a tool you couldn't work without?

### Success metrics
- 10 university programs actively using OrbitVal
- At least 3 teams that say they'd be upset if it went away
- One piece of written feedback you can quote publicly

### Timeline
- 3 months to working MVP
- 6 months to first 10 university users

---

## Phase 1 — Traction (Senior year + first year post-graduation)

**Goal:** Establish OrbitVal as the known tool in the CubeSat community.

### Product
- v1.1: Add more fault scenarios based on Phase 0 user feedback
- v1.2: Add scenario contribution workflow — let community submit fault scenarios
- v1.3: First paid tier — hardware-specific scenario packs
- Publish the ORF spec as a standalone versioned document on `orbitval.com`
- PDF spec document authored by hand, not generated
- Public changelog and 90-day comment period process established

### Business
- Convert first commercial operator to paying customer
- Target: $1–5k ARR — small but real
- Apply to Y Combinator, Pear VC, or similar space-focused accelerators
- Begin conversations with aerospace engineering professors at target universities (MIT, Caltech, TU Delft, Rutgers) about integrating OrbitVal into coursework
- Hire first part-time contributor (likely a grad student)

### Community
- Launch a public Slack or Discord for OrbitVal users
- Open the fault scenario library to community contributions
- Host first virtual office hours for CubeSat teams

### Success metrics
- 50+ university programs using OrbitVal
- First paying commercial customer
- ORF spec publicly published and versioned
- At least one professor teaching with OrbitVal

### Timeline
- 12–18 months after Phase 0

---

## Phase 2 — Institutional credibility (Years 2–3)

**Goal:** Get one institution to formally reference ORF.

This is the hardest phase. Everything before this is building. This is where OrbitVal either becomes a standard or stays a tool.

### Product
- v2.0: Expand beyond 3U — support 6U and 12U CubeSat configurations
- Add constellation simulation (multi-satellite scenarios)
- Launch opt-in cloud dashboard — report visualization, team sharing, scenario library browser
- Hash registry v1 — OrbitVal operates it, append-only, publicly queryable
- ORF validator — any tool can check if a report is spec-compliant

### Business
- Raise a seed round ($500k–$2M) — use traction and institutional interest as leverage
- Hire first full-time engineer
- Begin formal conversations with target insurers — Lloyd's, Marsh McLennan
- Begin formal conversations with launch providers — Rocket Lab first (most CubeSat friendly)
- Submit ORF to ESA's CubeSat support program as recommended reporting format
- Apply to NASA CSLI program as recommended validation tool

### The institutional ask
You're not asking them to mandate it yet. You're asking for something much smaller:
- "Would you be willing to say OrbitVal is a recommended tool for teams preparing for launch with you?"
- "Would you accept an ORF report as part of payload documentation?"

One yes from one institution changes everything.

### Success metrics
- One insurer or launch provider formally references ORF in any official document
- Hash registry live and publicly queryable
- $50–100k ARR
- Seed round closed

### Timeline
- 18–36 months after Phase 0

---

## Phase 3 — Standard status (Years 3–5)

**Goal:** ORF becomes what everyone expects to see.

### Product
- v3.0: Full mission simulation beyond LEO — MEO, GEO support
- Hardware-in-the-loop integration (for teams that want it)
- Enterprise tier: white-label reporting, custom scenario development, SLA support
- API access to hash registry for insurer and launch provider integration

### Business
- Spin out the ORF Foundation as a separate non-profit
- Founding board members: OrbitVal Inc + one insurer + one launch provider + one university + one space agency representative
- Transfer spec governance and registry operation to the Foundation
- OrbitVal Inc becomes the premier commercial tooling provider for the standard it founded
- Raise Series A ($5–15M)
- Hire sales, support, and more engineers
- Certification badge program launches — issued by ORF Foundation, recognized by insurers and launch providers

### Revenue model at this stage
```
OrbitVal Inc:
- Scenario pack sales (growing library)
- Per-seat enterprise licensing
- Cloud dashboard subscriptions
- Custom scenario development (professional services)
- Enterprise support contracts

ORF Foundation:
- Consortium membership fees from insurers/launch providers
- Certification issuance fees
- All reinvested into spec governance and registry
```

### Success metrics
- ORF Foundation legally incorporated with institutional board
- 3+ insurers accepting ORF reports in underwriting workflow
- 2+ launch providers requiring or recommending ORF compliance
- $500k–$1M ARR for OrbitVal Inc
- OrbitVal referenced in at least one ESA or NASA document

### Timeline
- 3–5 years after Phase 0

---

## Phase 4 — Infrastructure layer (Years 5–7)

**Goal:** OrbitVal becomes financial infrastructure for the satellite industry.

### What this looks like
The insurer workflow is now:
```
Team runs OrbitVal → hash registered → insurer queries registry
→ automated risk signal → faster, cheaper underwriting
```

Launch providers use ORF compliance as part of automated payload approval. Insurance premiums are partially calculated based on ORF report scores. New space companies budget for OrbitVal certification the way they budget for launch insurance — it’s part of the cost of doing business.

### Product
- Automated insurer API — real-time risk signal from ORF registry
- Regulatory compliance mapping — ORF reports mapped to FCC, ITU, national licensing requirements
- Predictive fault modeling — ML layer that suggests likely failure modes based on mission profile
- Support for non-CubeSat smallsats — broader market

### Business
- Series B ($20–50M)
- International expansion — ESA, JAXA, ISRO relationships
- Explore acquisition by a major aerospace or insurance company, or stay independent
- OrbitVal Inc is now the Bloomberg Terminal of satellite risk — the data layer everyone depends on

### Success metrics
- ORF is the de facto standard — used without being mandated because it's expected
- Registry contains tens of thousands of verified reports
- Insurers price missions differently based on ORF certification status
- $5–10M ARR

### Timeline
- 5–7 years after Phase 0

---

## Phase 5 — Permanence (Year 7+)

**Goal:** OrbitVal outlasts its founder.

### What this means
The ORF Foundation is self-governing. The standard is stable enough that the industry would maintain it even if OrbitVal Inc disappeared tomorrow. OrbitVal Inc is a profitable, growing company with defensible revenue from the best tooling ecosystem around a standard it founded.

### Options at this stage
- Stay independent and grow
- Raise growth equity and expand aggressively
- Strategic acquisition (e.g., Ansys, L3Harris, a major insurer, or a prime contractor) — at a valuation that reflects owning the standard, not just a software tool
- IPO if the market is right

---

## What you control right now

All of this is downstream of one thing: **does the MVP work and do real CubeSat teams find it useful?**

Everything else — the foundation, the registry, the insurers, the Series A — is earned, not planned. The plan gives you direction. Execution gives you the right to the next phase.

