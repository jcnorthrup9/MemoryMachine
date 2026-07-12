# ARCHIVE / DIAGNOSTICS Tabs — Code Overview

2026-07-12. Written to track what this feature touches, same purpose as
`ProgramPlacement_CodeOverview.md` — a snapshot for reorienting later, not a
permanent spec.

## Why this exists

`Header.jsx` had two dead nav tabs, RECONSTRUCT (the only real one — the 3D
viewport) alongside ARCHIVE and DIAGNOSTICS, both `href="#"` links with no
content behind them. Investigated first: no documented intent exists for
either. The only trace is `DESIGN.md`, which mentions the whole UI was
extracted from four AI-generated (Google Stitch) mockup screens —
"Reconstruction Workspace," "Parameters & Configuration," "System
Diagnostics," "Archive Index" — of which only the first two ever got built
(Reconstruction Workspace → RECONSTRUCT; Parameters & Configuration → the
existing `ParamPanel` sidebar). The actual Stitch mockup content for the
other two isn't preserved anywhere in the repo — no spec, TODO, or handoff
describes what was meant to go on them. Given no intent to recover, both
tabs were built out from scratch around what already existed elsewhere in
the app but had no real home.

## What ARCHIVE does

A real gallery for build iterations, server-persisted this time — distinct
from the "Save Build"/"Load Build" buttons already in the RECONSTRUCT
toolbar (client-side only: downloads/reads a JSON file, no list view, no
persistence across machines). Both share the exact same
`memory-machine-build-v1` snapshot schema, so a build saved to the server
archive can be loaded exactly the same way a locally-downloaded file is.

- **Backend** (`logic/pershing_api.py`): `ARCHIVE_DIR =
  outputs/pershing_archive/`. `save_build_to_archive()` writes a snapshot
  with a sortable `<epoch_ms>_<slugified-label>.json` filename (slug
  restricted to ASCII alnum/dash — the label is free user text and must not
  become a path/traversal vector, same reasoning as the existing
  `_safe_archive_path()`'s `os.path.basename()` guard on read/delete).
  `list_archived_builds()` returns a lightweight summary per file (label,
  saved_at, material_mode, slab tonnage, instance count, program zone
  count) — deliberately does **not** parse out and return the full
  geometry payload for a listing, only `get_archived_build()` does that, on
  an actual load. Routes: `POST/GET /api/pershing/archive`,
  `GET/DELETE /api/pershing/archive/{filename}`.
- **Frontend** (`ArchivePanel.jsx`): label input + "Save Current Build"
  button, list of archived entries each with Load/Delete. Takes
  `getSnapshot`/`onRestoreSnapshot` callback props rather than owning
  App-level state itself — `App.jsx` extracted its existing
  `handleSaveBuild`/`handleLoadBuild` logic into two shared helpers,
  `buildSnapshot()` and `restoreSnapshot(snapshot)`, so the RECONSTRUCT
  toolbar's file-based save/load and the ARCHIVE tab's server-based
  save/load are two thin wrappers around the same two functions, not
  duplicated logic.

## What DIAGNOSTICS does

A read-only status dashboard for data that was already being computed
server-side (via `rebuild()`, `grow_network()`, `get_program_zones()`,
`get_config()`) but was previously only ever consumed as grounding context
for the juror chat (`App.jsx`'s `handleJurorChat`) or not surfaced at all.
No new backend calls — `DiagnosticsPanel.jsx` just reads `config`/`data`/
`networkData`/`programZones`, state `App.jsx` already holds, and renders
four sections: Site Configuration (grid dims, bay count, which real-data
CSVs are loaded), Last Rebuild (instance/voxel counts, slab tonnage, max
canyon depth, real-data-used flags), Circulation Network (node/attractor
counts — shows a placeholder if the network hasn't been grown yet), and
Program Placement (per-program achieved-vs-target sf, `(partial)` flagged
when a program didn't hit its target — see
`ProgramPlacement_CodeOverview.md`).

## Other changes bundled into this pass

- `Header.jsx` converted from three static links to a real tab switcher
  (`activeTab`/`onSelectTab` props); `App.jsx` gained `activeTab` state and
  now conditionally renders the RECONSTRUCT layout vs. `ArchivePanel` vs.
  `DiagnosticsPanel` in the same content region.
- Earlier in this same session: the old `Sidebar.jsx` (a second, unused
  copy of the RECONSTRUCT/ARCHIVE/DIAGNOSTICS nav, `PERSHING_SQ` /
  `CANYON_ENGINE` title) was deleted outright, and its title text moved
  into `Header.jsx` with `CANYON_ENGINE` replaced by `PERSHING_METABOLIZER`
  — done to give the viewport more horizontal room since the sidebar's nav
  was completely dead.

## Verification status

- Header tab-switching, RECONSTRUCT view, and the ARCHIVE tab's empty
  state were confirmed visually correct via a live isolated browser check
  (Puppeteer + real Chrome against an isolated backend/frontend pair on
  spare ports, screenshotted).
- The full archive backend round trip (save with a label → list shows it
  with correct summary stats → get returns the full snapshot → delete
  removes it, confirmed via a follow-up list) was verified directly against
  a live running FastAPI instance via `curl` — all four operations
  returned correct results.
- A later round of the same live-browser check (meant to also screenshot
  the populated ARCHIVE list and the DIAGNOSTICS tab, and prove the "Load"
  button restores state in the browser itself, not just via curl) hit
  repeated Puppeteer/Chrome launch flakiness (`page.goto` timing out even
  on `about:blank`, and a separate run showing the configured Chrome path
  losing its backslashes when round-tripped through a bash heredoc) — an
  environment/tooling issue in this session, not an application bug (the
  backend log for that same run shows every request the page made
  succeeded normally). Not re-chased further due to session limits.
  **Worth a real from-scratch browser check next session**, particularly
  the "Load" button's actual state-restore behavior in the live UI (already
  proven correct for the RECONSTRUCT toolbar's equivalent file-based
  load — see `restoreSnapshot()` above, shared code path — but not
  re-confirmed for the ARCHIVE tab's server-based load specifically).
