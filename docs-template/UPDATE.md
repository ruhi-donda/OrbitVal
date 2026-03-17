# When and how to update each doc

> Concrete checklists so the doc set stays in sync with the codebase.
> Fill in the "Quick reference" section at the bottom when you have pending updates.
> Entry point: [MAP.md](MAP.md).

All OrbitVal documentation in this repo lives alongside `MAP.md` (repo root). Use relative links like `[MAP.md](MAP.md)`.

---

## When you create or move files (update MAP + MANIFEST)

**Do this every time you add, remove, or move a file:**

```
□ New or moved documentation file:
    → Update MAP.md:
      □ Add (or remove) the file in the "Documentation" table
      □ Add (or update) the "Docs at a glance" tree if needed
    → Cross-link from this doc in related sections elsewhere if relevant

□ New or moved code file (in lib/, assets/, etc.):
    → Update MANIFEST.md (new file checklist, connections, data flow, provider tree)
    → Update MAP.md "Codebase at a glance" tree if it's a top-level or notable file
    → Update manifest.yaml if it's a module/service/entrypoint (modules.*, services.*, entrypoints.*, phases.*, planned.*)
```

This keeps MAP.md the single entry point. See MANIFEST.md for detailed file-by-file and connection updates.

---

## When to update each doc

```
MAP.md                  update when:
  □ Current branch or phase changes
  □ A major new feature is planned
  □ The roadmap changes significantly (sync with ROADMAP.md)
  □ A doc file is added, removed, or moved (Documentation table + Docs at a glance)
  □ A notable code file or folder is added or moved (Codebase at a glance)

manifest.yaml           update when:
  □ A module/service/entrypoint is added, removed, or moved
  □ A connection changes (depends_on, module_order, phases/planned)
  □ A planned phase is scoped or a planned item is implemented (move from planned to modules/services)
  □ Keep in sync with MANIFEST.md — same connections, parseable form

MANIFEST.md             update when:
  □ A new file is created
  □ A file is deleted or renamed
  □ A new connection is established (module → service, runner → fault pack, etc.)
  □ A new data flow exists
  □ A planned connection moves from future → current

ARCHITECTURE.md         update when:
  □ A non-obvious decision is made (add an ADR)
  □ An existing decision is reversed (mark ADR as Superseded)
  □ A new phase is completed
  □ A new term needs defining in the glossary

TEMPLATES.md            update when:
  □ A new type of thing is introduced (new pack format, new report schema, new harness integration)
  □ A contract is tightened or relaxed
  □ A new reusable module or fault scenario is added (add to tables)

UPDATE.md               update when:
  □ A new doc is added (add its "when to update" bullets)
  □ A new category of "when you create or move files" rule is adopted

ROADMAP.md              update when:
  □ A phase goal, timeline, or success metric changes
  □ ORF format strategy or certification strategy changes
  □ New major product line is added (e.g., registry, validator, certification)

TODO.md                 update when:
  □ You complete an item (check it off)
  □ You add a new misc task or promote one to ordered refactors
  □ An audit or refactor order changes (sync numbering/descriptions)

AUDIT.md                (if used) update when:
  □ The area being audited changes (pipeline, state ownership, etc.)
  □ A refactor from the recommended order is completed (tick off or adjust)
  □ Scope or compatibility assumptions change
```

---

## MANIFEST.md — new file checklist

Every time you create a new file, answer these and add a row to the right section:

```
□ What folder does it live in?
□ What is its single responsibility? (one sentence)
□ Which feature does it belong to?
□ Which module does it belong to (config/orbits/faults/engine/reporting)?
□ Does it depend on a service (e.g. Celestrak fetch, report writing)? Which one?
□ Does it affect the harness boundary (autonomy code integration)? If yes, record and version it.
□ Does it introduce a new data flow? Document it under Data Flow section
□ Is it a planned future connection? Add to Planned connections section
```

---

## MANIFEST.md — new connection checklist

Every time two files become connected:

```
□ Who calls whom?
□ What is passed (type + name)?
□ Does it cross a feature boundary? (flag this)
□ Add to the relevant Data flow section
□ Update manifest.yaml (modules/services/entrypoints) so the wiring stays parseable
```

---

## ARCHITECTURE.md — new ADR checklist

Every time a non-obvious decision is made:

```
□ What problem were you solving?
□ What options did you consider? (minimum 2)
□ What did you decide?
□ What does this enable?
□ What does this constrain?
□ Does this supersede an existing ADR? If yes: mark old ADR as "Superseded by ADR-XXX"
```

---

## Quick reference — what changed today

Clear this section when done updating docs. Use it as a scratchpad while making changes.

**MAP.md:**  
```
□ Updated project summary, stack, phases, and codebase layout for local-first OrbitVal
```

**MANIFEST.md:**  
```
□ Updated wiring to Python package modules (config/orbits/faults/engine/reporting)
```

**manifest.yaml:**  
```
□ Updated to OrbitVal module/service/entrypoint schema and phases (including future cloud dashboard)
```

**Other:**  
```
□ Updated README.md, TEMPLATES.md, TODO.md, AUDIT.md
```

---

## Related documents

Entry point: [MAP.md](MAP.md). See also [MANIFEST.md](MANIFEST.md), [manifest.yaml](manifest.yaml), [TODO.md](TODO.md), [TEMPLATES.md](TEMPLATES.md), [ARCHITECTURE.md](ARCHITECTURE.md).
