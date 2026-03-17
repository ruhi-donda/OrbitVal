# Cursor context — docs-template and skills

> This file explains how AI assistants (e.g. Cursor agents) should use the
> `docs-template/` set as a **generic, stack-agnostic base** for any project,
> and which skills are natural to derive from it.

---

## Purpose of `docs-template/`

`docs-template/` is a **project-agnostic starting point** for:

- `MAP.md` — entrypoint and documentation index.
- `ARCHITECTURE.md` — philosophy + ADRs.
- `MANIFEST.md` — rich file/connection map for humans.
- `manifest.yaml` — parseable wiring schema for tools.
- `TEMPLATES.md` — screen/controller/service/model patterns.
- `TODO.md` — ordered refactors + backlog.
- `AUDIT.md` — phase/readiness audit.
- `UPDATE.md` — when/how to keep docs in sync.
- `FLUTTER_PRINCIPLES.md` — optional UI/layout rules (can be omitted or renamed for non-Flutter stacks).

Agents should **copy and adapt** these templates into a concrete project’s
`docs/` folder, then keep them synchronized with the real codebase.

---

## Recommended skills to generate (per-project)

When bootstrapping a new project or upgrading an existing one, it’s useful to
create dedicated Cursor skills that wrap common workflows. The following skills
are intentionally project-agnostic and can be specialized per repo.

### 1. `manifest-maintainer`

**Goal:** Keep `manifest.yaml` and `docs/MANIFEST.md` in sync with the code.

- **Inputs:** none (runs from repo root).
- **Behavior:**
  - Scan for new/moved/removed screens, controllers, services.
  - Update:
    - `manifest.yaml` → `screens`, `controllers`, `services`, `phases.planned`.
    - `docs/MANIFEST.md` → tables for screens/controllers/services/models.
  - Preserve comments and ordering where possible.
- **When to use:** After adding a feature folder, controller, or service, or
  when refactoring navigation/data flow.

### 2. `docs-sync`

**Goal:** Keep `MAP.md`, `MANIFEST.md`, `ARCHITECTURE.md`, `TODO.md` and
`UPDATE.md` consistent.

- **Behavior:**
  - Update `MAP.md`:
    - Documentation table.
    - “Docs at a glance” tree.
    - “Codebase at a glance” for new top-level folders.
  - Ensure `MANIFEST.md` and `manifest.yaml` describe the same wiring.
  - Propagate phase/task changes to `docs/TODO.md`.
  - Adjust `UPDATE.md` rules when new docs are added.

### 3. `audit-runner`

**Goal:** Use `docs/AUDIT.md` to assess readiness for a phase before major
changes.

- **Behavior:**
  - Read `ARCHITECTURE.md`, `MANIFEST.md`, `manifest.yaml`, and current code.
  - Fill sections in `AUDIT.md`:
    - Current state summary (doc vs code).
    - Critical findings and recommendations.
    - Data/format compatibility.
    - Recommended refactor order.
  - Optionally push resulting ordered refactors into `docs/TODO.md`.

### 4. `todo-curator`

**Goal:** Maintain a denvboard/forge-friendly TODO structure.

- **Behavior:**
  - Normalize `docs/TODO.md` into:
    - Phase sections (`## Phase N — Name`).
    - A `## Next to build` or similar group.
  - Ensure checkboxes and headings follow the documented conventions.
  - Optionally, cross-link tasks to sections in `ARCHITECTURE.md`, `MANIFEST.md`,
    or `AUDIT.md`.

### 5. `templates-applier`

**Goal:** Apply `TEMPLATES.md` patterns consistently when adding new code.

- **Behavior:**
  - When user asks to add a new controller/screen/service/model:
    - Read `docs/TEMPLATES.md`.
    - Generate skeletons that match the template (imports, naming, contracts).
  - Update relevant docs:
    - `MANIFEST.yaml` / `docs/MANIFEST.md` for new files and connections.
    - `MAP.md` for new feature folders.

---

## How Cursor agents should use this context

- **For new projects:**
  - Copy `docs-template/` into `docs/`.
  - Run skills in this order:
    1. `templates-applier` — create initial `MAP.md`, `ARCHITECTURE.md`,
       `MANIFEST.md`, `manifest.yaml`, `TODO.md`.
    2. `docs-sync` — ensure all docs point to the real folders/files.
    3. `manifest-maintainer` — wire up initial screens/controllers/services.

- **For existing projects:**
  - Use `audit-runner` to understand drift between docs and code.
  - Use `docs-sync` and `manifest-maintainer` to correct it.
  - Use `todo-curator` to keep `docs/TODO.md` usable by humans and tools.

This file is intentionally agnostic; adapt skill names or behaviors per repo,
but keep the **intent** consistent so tools and AI can rely on the same mental
model across projects.

