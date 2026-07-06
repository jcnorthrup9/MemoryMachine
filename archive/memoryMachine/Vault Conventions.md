**Tags:** #meta #vault-structure

This vault (`archive/memoryMachine/`) is the single home for Memory Machine project context that isn't live code or live data — handoffs, precedent research, session logs, and reference material. Going forward, new notes should follow whichever pattern below fits the content, so the vault doesn't drift back into the scattered-at-repo-root state it was just cleaned up from (2026-06-29 consolidation, see below).

## Naming patterns

| Content type | Pattern | Example |
|---|---|---|
| Session/work logs | `session_log_YYYY-MM-DD.md` | `session_log_2026-06-27.md` |
| Dated handoffs to another agent/session | `HANDOFF_MMDDYYYY[_TOPIC].md` | `HANDOFF_04072026_B.md`, `HANDOFF_06292026_SYNCTHING.md` |
| Precedent / spatial-analysis notes | `Title Case Subject — Note Type.md` (em dash) | `Parc de la Villette — Spatial Analysis.md` |
| Data/schema reference docs | `Topic - actual_filename.ext.md` | `Prototype Data Schema - site_data.json.md` |
| Standing plans (not yet executed) | `Refactoring Plan - Subject.md` | `Refactoring Plan - PershingMetabolizer Prototype.md` |
| Raw research dumps / source lists | `Topic — Source Links.md` | — |

If none of these fit, default to Title Case with spaces — avoid introducing a new ALLCAPS_SNAKE_CASE or all-lowercase pattern.

## Cross-linking

Use Obsidian `[[wikilinks]]` when a note references another concept that has (or should eventually have) its own note — see `MemoryMachineForensicPalimpse.md` for the pattern (`[[Nakagin Capsule Tower]]`, `[[1988 Trailer]]`, etc.). It's fine to link to a note that doesn't exist yet; that's a marker for future content, not an error.

## What belongs here vs. elsewhere

- **Belongs in this vault:** handoff docs, precedent/case-study research, session logs, data-schema explainers, sourced reference material, standing plans.
- **Stays in the repo root / code dirs:** anything actively read by code or actively maintained as the current spec (`README.md`, `CHANGELOG.md`, `GEMINI_CONTEXT.md`, `PROTOTYPE_REFACTOR_PLAN.md`, `urban_design_guidelines.md`) — these are live documents, not archive.
- **`_OLD` / superseded files:** move here rather than deleting, so the prior version stays available as context.

## 2026-06-29 consolidation

Moved 28 files here from the repo root, `data/`, `logic/`, and `plans/` — prior-semester handoffs (`HANDOFF_*`, `handoff*.md`), concept docs (`MEMORY_MACHINE_CONCEPTS.md`, `CROSS_POLLINATION_ENGINE.md`, `Claude_Code_Brief*.md`), daily/status logs, and precedent research (`MemoryMachineForensicPalimpse.md`, `nakagin_parsed_data.md`, `rhino_precedent_pass.md`, `rhino_forensic_plan.md`, `DIAGRAM_RULES.md`). The superseded `urban_design_guidelinesOLD.md` came along too. Left at root: `villette_analysis.md` — a shorter draft superseded by the fuller `Parc de la Villette — Spatial Analysis.md` already in this vault; not moved since it's redundant, not additive context.
