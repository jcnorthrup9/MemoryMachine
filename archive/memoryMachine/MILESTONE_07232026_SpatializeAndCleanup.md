Memory Machine — SPATIALIZE Tab, 2D↔3D Bridge, HUD Accuracy Fixes, App Cleanup
===============================================================================
*2026-07-23. Snapshot after a long session spanning the tail of `HANDOFF_07222026_ZonalConstraintsFix.md` (the last 2D HUD bug) through building native 2D authoring into the 3D app and a first cleanup pass. Committed at `f9aec14` on `feature/blender-mcp-pipeline`, pushed to origin.*

## Context

Session picked up from `HANDOFF_07222026_ZonalConstraintsFix.md`'s Fix #1/#2 (repointing the 2D
app's stale SVG source) and kept finding the same HUD still read wrong even after that landed. Two
more real bugs turned up and got fixed. From there the user asked a bigger question — the app has
two frontends (a vanilla-JS 2D diagram generator on port 8000, a React 3D "Pershing Metabolizer" on
5173) and wanted them combined so the 2D layout could actually influence 3D program placement. That
turned into: discovering the backend was already shared (one FastAPI process, not two), building a
real bridge in both directions, porting 2D authoring natively into the 3D app as a new tab, and a
specific, deliberately-designed answer to "what happens when 2D layers overlap." Session closed with
a first app-cleanup pass (removing now-redundant UI, quarantining stray sync artifacts).

## What's actually different now

### 1. Two more 2D HUD bugs, on top of the SVG-source fix

The Zonal Constraints HUD (`static/js/state.js`'s `getProgramStats()`) was still wrong after
`HANDOFF_07222026`'s SVG repoint, for two independent reasons:

- **No fill check.** `_extractVertices()`/`_getLayerGeometry()` treated *any* path/polyline/polygon
  inside a matched layer group as fillable area, regardless of whether it actually had a `fill`
  attribute. `PEDESTRIAN_PATH` alone has 583 stroke-only dash segments in the real site SVG — every
  one with ≥3 points was getting force-closed and filled by the stats canvas, inflating Hardscape.
  Fixed with a `_hasRealFill()` check mirroring `ingest_diagram_svg.py`'s existing server-side
  `_has_real_fill()`.
- **Wrong denominator.** Percentages divided by the full `STATS_CANVAS_W × STATS_CANVAS_H` stats
  canvas, but Pershing Square's real boundary is rotated — its actual polygon area is only **~48%**
  of its own axis-aligned bounding box. Every percentage was silently deflated by roughly 2x. Fixed
  by rasterizing the real boundary polygon as a mask first and using its true pixel count as the
  denominator, falling back to the old full-canvas count only if no boundary group is found.

Both fixes visually confirmed by the user after a hard reload.

### 2. The 2D↔3D bridge — built in both directions

Discovered the two apps were never actually separate backends: root `app.py` (port 8000) already
mounts every `logic/pershing_api.py` route under `/api/pershing/*`. Only the frontends are split —
the vanilla 2D app (`static/`) and the React 3D app (`frontend/`, Vite dev server on 5173, proxying
`/api/*` back to 8000, no production build currently served).

- **3D → 2D**: `apply_deficit_weighting()` (`logic/ai_synthesizer.py`) now runs on every
  `/api/generate` call — pulls the live bay grid's real amenity-deficit signal
  (`_deficit_weighted_location_weights()`, already existed for the 3D remix path) and biases where
  the AI-picked PROG/amenity layer lands, not just the empty-prompt random path.
  `GET /api/pershing/deficit-weights` exposes this signal directly now too (previously internal-only).
- **2D → 3D**: every `/api/generate` call auto-saves a `memory_machine_generation_<epoch_ms>.json`
  record (prompt, narrative, resolved `spatial_seed`) to `archive/diagrams/generated/`. New
  `GET /api/pershing/2d-generations` / `POST /api/pershing/2d-generations/preview`
  (`logic/pershing_api.py`'s `list_2d_generations()`/`preview_2d_generation()`) let the 3D app list
  and preview-then-bake one of these — reusing `remix_precedent()`'s old rasterization tail (now
  `_compose_layers_to_3d()`), no SVG re-parsing needed since the data's already structured. Surfaced
  as a third tab ("2D Generations") inside the 3D app's PAINT dialog (`PaintOverlay.jsx`), alongside
  the existing Sketch/Diagram tabs — same list→preview→`bakePaint()` pattern as the others.

### 3. SPATIALIZE — native 2D authoring inside the 3D app

New top-level tab in the React app (`frontend/src/components/SpatializerPanel.jsx`, sized like
RECONSTRUCT, not a modal), replacing the old cross-app workflow (generate in 2D app → save → switch
apps → import → bake) with one native flow:

- `frontend/src/spatializerEngine.js` — the 2D rendering + HUD math ported from
  `static/js/engine2D.js` + `static/js/state.js` as a plain, framework-agnostic module (including
  both HUD fixes above), called imperatively from a `useEffect`+ref — same pattern `PaintOverlay.jsx`
  already used for its freehand sketch canvas.
- A live red deficit-hotspot overlay renders under the canvas while composing
  (`GET /api/pershing/deficit-weights`) — the 3D side's amenity-deficit data is visible *during*
  authoring, not just as an invisible bias discovered after the fact.
- One **BAKE** button: `POST /api/pershing/spatialize-preview` (new, takes the live in-memory stack
  directly, no file round-trip) → `bakePaint()` (existing, unchanged).

### 4. Overlap effects — a real design decision, not just a bug fix

User asked what happens when 2D layers overlap. Traced the actual answer through
`terracing_engine.py`: nothing crashes, but resolution is *inconsistent by category* — hardscape
implicitly vetoes excavation before typology classification runs (`_z_for_voxel()`'s
`elif v.is_hardscape: return 0.0`, unconditional, before the canyon/sketch-weight blend a few lines
later is ever reached); water/greenscape/amenity_resting resolve via an explicit fixed
`GROTTO > SANCTUARY > CIRCULATION` priority; trees and the greenscape ground-texture flag bypass the
whole system and can double-place.

First approach was generic occlusion (topmost 2D layer wins overlapping cells) — built, verified,
then **reverted** once the user pushed on what should actually *happen* architecturally. Occlusion
picks a winner and discards the signal that two categories both wanted a cell; the user's direction
needed the opposite — detect the overlap and give it a deliberate physical response, different per
category pair, not a generic winner-take-all.

Landed on the first, clearest case: **Hardscape ∩ Water → canyon rupture**. Water breaking through
pavement, reusing the existing (previously always-zero for any 2D-diagram-sourced grid) `canyon`
excavation-depth weight and the existing `GROTTO` typology — no new 3D typology needed.
`ingest_diagram_svg.apply_hardscape_water_overlap()`, wired into `spatialize_preview()` only (not
`remix_precedent()`'s — since removed, see below — or `preview_2d_generation()`'s paths). Clears
`hardscape` on overlap cells (or the veto silences any canyon weight), keeps `water` (so `GROTTO`
picks it up once excavated), sets `canyon` to a fixed weight. Verified end-to-end through a real
bake+rebuild: 45 overlap cells all became real `GROTTO` voxels at `z_ft < 0`; 402 other
hardscape-classified voxels elsewhere stayed untouched at `z_ft == 0`.

**Explicitly deferred, not built**: other category pairs (Hardscape∩Greenscape as a blended-material
ground texture, Amenity∩Hardscape as a sunken plaza) and same-category overlap ("hills" — confirmed
the terracing engine is excavation-only today, every `_z_for_voxel()` return is `0.0` or negative;
positive elevation would be genuinely new engine capability, not a reuse of existing GROTTO/canyon
machinery, and would need real decisions about how structural framing/slab-harvesting — which
assumes cutting down — would handle terrain going up).

### 5. Cleanup pass

- Removed the "Precedent Remixer" panel end-to-end (`PrecedentRemixerPanel.jsx`, its `ParamPanel.jsx`
  button, `App.jsx` wiring, `api.js`'s `remixPrecedent()`, `pershing_api.py`'s `remix_precedent()` +
  `RemixPrecedentRequest`, the `/api/pershing/remix-precedent` route) — confirmed redundant:
  SPATIALIZE covers everything it did via the same underlying `generate_spatial_seed()`/
  `remix_layers()` pipeline, plus a live canvas, the HUD, the deficit overlay, auto-archiving, and
  the overlap-rupture effect Precedent Remixer's own bake path never got.
- Found and quarantined 60 Syncthing `*.sync-conflict-*` files (same device, same ~14-minute window
  on 2026-07-22 — another machine's stale copies colliding with active edits here). 40 were
  byte-identical to canonical, the rest sampled and confirmed to be strictly older/incomplete
  snapshots (no unique work found in any sampled file). Moved to
  `archive/_sync_conflicts_20260722/` (not deleted — not git-tracked, so no undo-via-git if a
  non-sampled file turns out to matter) rather than hard-deleted. Added `*.sync-conflict-*` to
  `.gitignore` so this doesn't silently recur.

## Current state of the app

- **Backend**: one FastAPI process (`app.py`, port 8000) serves both frontends' APIs. `logic/`
  contains the actual domain logic (`pershing_api.py` is the biggest single file — 3D
  rebuild/bake/program-placement/canopy/circulation orchestration; `terracing_engine.py`,
  `program_placement.py`, `canopy_engine.py`, `circulation_network.py` at repo root do the real
  geometry/scoring work `pershing_api.py` wraps).
- **2D app** (`static/` + root `index.html`, served at `/`): vanilla JS, AI-prompt-driven precedent
  layer picker + manual placement, exports to `archive/diagrams/generated/` (images + now JSON
  generation records). Still the only place to *author* a totally fresh 2D layout from scratch with
  the full manual editing UI (drag/scale/rotate individual layers) — SPATIALIZE only has the
  AI-generate flow currently, no manual placement UI yet.
- **3D app** (`frontend/`, React + react-three-fiber, Vite dev server on 5173 only — no production
  build currently served by `app.py`): RECONSTRUCT (main viewport + param sliders), **SPATIALIZE**
  (new, this session — native 2D authoring, listed first in the tab order per user request), PAINT
  dialog (Sketch / Diagram-import / 2D-Generations-import — three ways to feed the same live paint
  masks), ARCHIVE (server-side build snapshots), DIAGNOSTICS.
- **diagram_tool** (port 8006, standalone): explicitly deprioritized by the user this session ("it
  doesn't seem to be working") — not touched, not part of any bridge work above.
- Two known dead-ish threads noticed in passing, not investigated: `logic/diagram_remix_chat.py`
  (untracked, imports the same `generate_spatial_seed`/`remix_layers` primitives directly — appears
  to be in-progress work for `diagram_tool`'s own chat-based remix, unclear how finished) and
  `diagram_tool/static/js/remixChat.js` (also untracked).

## Not yet verified / open as of this snapshot

- **No visual browser verification** of SPATIALIZE, the deficit overlay, or the Hardscape∩Water
  rupture happened this session — every check was via direct API calls (curl/PowerShell), not a live
  browser. One earlier attempt this session connected to a Chrome instance on a *different physical
  device* than the one being worked on (caught via an on-page marker check before trusting a
  screenshot) — any future visual check should confirm the connected tab is actually visible on the
  user's screen first, not assume.
- Whether `remix_precedent()`/`preview_2d_generation()` should *also* get a version of the
  Hardscape∩Water overlap effect (or others) is an open question — deliberately scoped to
  `spatialize_preview()` only for now.
- The `archive/_sync_conflicts_20260722/` quarantine folder is uncommitted and undecided — user said
  quarantine-not-delete for now; permanent deletion is a separate later call.
- ~190 other pre-existing dirty/untracked files in the repo (Rhino/Blender assets, old handoff docs,
  ~150 workflow screenshots, render test PNGs) were deliberately left out of this session's commit —
  predate this session, no context on them, not swept into `f9aec14`.
- A couple of docstring/comment mentions of `remix_precedent()` linger in `logic/ai_synthesizer.py`,
  `ingest_diagram_svg.py`, and `logic/diagram_remix_chat.py` — descriptive context only, not
  functional references, left alone rather than doing a full comment-sweep.
- Hills/same-category overlap and the other deferred overlap pairs (Hardscape∩Greenscape,
  Amenity∩Hardscape, Trees∩Water light-well verification) remain genuinely unscoped — next real
  design conversation, not a small follow-up.
