Memory Machine — Surface Interventions Milestone (Buildings / Amenities / Greenscape / Trees)
================================================================================================
*2026-07-08. Snapshot of a planning + implementation session on the terracing_engine.py + FastAPI + React pipeline — not a permanent spec.*

## Context

Session started as a planning conversation ("how do I begin planning surface interventions — buildings, amenities, greenscape, trees — and should I have an assets folder or generate shapes procedurally") while a separate chat session had uncommitted work in flight building out the FastAPI+React web pipeline (logic/pershing_api.py, logic/pershing_blender.py, frontend/, blender/pershing_headless_build.py — all brand new, never committed). Confirmed with the user that session was idle, then built the surface-intervention work on top of it and committed everything together (commit `e600a4c`, branch `feature/blender-mcp-pipeline`).

## Codebase reality check (confirmed via code, not assumption)

There are **three parallel front-ends** in this repo at different maturity levels:
1. `PershingMetabolizer_Prototype/index.html` — explicitly marked "superseded" in `PIPELINE_STATUS_AND_NEXT_STEPS.md`. JSON → BufferGeometry, no model loaders.
2. `index.html` + `static/main.js` (repo root) — real OBJLoader/MTLLoader/GLTFLoader/STLLoader wiring, plus an experimental AI-generation-to-GLB path (ComfyUI/TripoSR endpoints in `app.py`). Confirmed with the user this is legacy exploration being scavenged from, not a live target.
3. **`terracing_engine.py` + FastAPI (`app.py`, `logic/pershing_api.py`, `logic/pershing_blender.py`) + React/Three-fiber (`frontend/`)** — the one the status doc calls "now primary." This is the target for all surface-intervention work going forward.

The live data flow: paint/slider change → debounced `POST /api/pershing/rebuild` → `TerracingEngine` (voxel depth/typology) → `StructuralFramingEngine` (excavation shoring/bracing on real columns) → `TypologyAssetEngine` (amenity props) → one JSON response → React `Viewport.jsx` renders everything generically by `kind`. The load-bearing pattern for adding anything new is a **kind-lookup-table triple** that must stay in sync: `StructuralElement` dataclass (terracing_engine.py), `_PROTOTYPE_DIMS_FT`/cylinder/hex sets (blender/pershing_headless_build.py), `PROTOTYPE_DIMS_FT`/`KIND_COLOR`/cylinder/hex sets (Viewport.jsx).

**Asset strategy decided: hybrid.** Cheap procedural primitives now (boxes, cylinders, hex-prisms) to validate placement/layout; swap for curated or AI-generated models later via the existing ComfyUI text-to-3D endpoints and the GLTFLoader pattern already used by `StaticContext.jsx`/`BlenderBuild.jsx` — without touching the placement engines.

## What shipped this session

1. **Real amenity-survey data reachable from the web app.** Previously `amenity_deficit.py`'s CSV loader was only wired into `blender_cockpit.py` (the separate in-Blender tool) — the web app's `/api/pershing/rebuild` silently ran on the 2-point `DEFAULT_DEFICIT_HOTSPOTS` placeholder with no way to tell from the UI. Added a `use_real_amenity_data` toggle (`RebuildParams`), CSV status display, and an amenity-kind-count readout in `ParamPanel.jsx`, mirroring the Blender panel's existing UX. No CSV exists yet in `data/amenity_survey/` on this machine — toggle is present but inert until one is dropped in.
2. **Greenscape ground plane.** `is_greenscape` (already computed per-voxel, previously not sent to the frontend) now rides along in the `/rebuild` response. New `GreenscapeGround` component in `Viewport.jsx` renders a thin colored cap on top of the terrace surface wherever the greenscape paint mask is true — placeholder solid green, swappable for a real grass texture later.
3. **Procedural trees.** New `TypologyAssetEngine.tree_specs()` places `tree_trunk` (vertical cylinder) + `tree_canopy` (hex-prism stand-in for foliage) pairs on greenscape cells, thinned to roughly one tree per 3 voxels (27ft spacing) via a deterministic grid-modulo check. Fits the existing kind-dispatch paths with zero new geometry code.
4. **Building massing.** New `BuildingMassEngine` — purely user-parameterized (footprint x/y/width/depth/height/setback via a small form in `ParamPanel.jsx`), bay-snapped to the real 27ft structural grid (same convention `StructuralFramingEngine._column_grid()` uses for real columns). Required one small, backward-compatible addition to `StructuralElement`: a `scale_y` field (default `None` = old uniform-scale behavior for every existing kind) so box-shaped elements can have an independent width vs. depth — needed for rectangular buildings, not needed by anything that existed before.

**Explicitly NOT used as a data source:** `data/building_heights.json` — confirmed to be off-site *context* buildings (Biltmore Hotel etc.) in an abstract coordinate frame incompatible with `real_geometry.json`'s real site-feet frame. Would need a real remap effort to be usable; not worth it for v1 procedural massing.

## Verified

- `logic/pershing_api.py` and `terracing_engine.py` both import cleanly; `get_config()` runs.
- Ran `rebuild()` directly with a building param: correct bay-snapped placement (`x_ft=74.0` from an input of `50` → snapped to 54, +width/2). `kind_counts` includes `building_mass: 1`.
- Ran `rebuild()` with a faked-in greenscape mask (36 cells): confirmed 36 `is_greenscape` voxels round-tripped and 8 tree specs (4 tree pairs) were placed at the expected 3-cell spacing.
- `npm run build` in `frontend/` completes clean (631 modules, no errors) — confirms the Viewport.jsx/ParamPanel.jsx/App.jsx changes are syntactically and structurally sound.

## Not verified (known gap)

- **Headless Blender export was not run.** Blender isn't on this machine's PATH in this session's shell, so `blender/pershing_headless_build.py`'s new `tree_trunk`/`tree_canopy`/`building_mass` kind-table entries were reviewed by hand (mirrored exactly against the existing `steel_bolt`/`steel_turnbuckle` dispatch patterns, including the pre-existing generic `_PROTOTYPE_DIMS_FT.get(kind, (1.0,1.0,1.0))` fallback that prevents a KeyError on any unrecognized kind) but not executed. Run `/api/pershing/blender-build` end-to-end next session to confirm the new kinds actually export a valid OBJ.

## Next up (not started)

1. Confirm the headless Blender build path with the new kinds (see gap above).
2. Drop a real amenity-survey CSV into `data/amenity_survey/` and verify `use_real_amenity_data` actually changes the deficit heatmap/amenity counts in the live UI (code path is wired and unit-tested via a direct `rebuild()` call, but never exercised with a real CSV file).
3. Tune tree/building visual parameters once seen in the actual viewport (trunk/canopy dimensions and tree density were reasonable-guess placeholders, not measured against real park precedent).
4. When ready to move off procedural placeholders: reuse the existing ComfyUI `/api/comfy-text-to-3d` endpoint + the `GLTFLoader` pattern already in `StaticContext.jsx`/`BlenderBuild.jsx` to swap in generated/curated tree and building models, keyed off the same `tree_trunk`/`tree_canopy`/`building_mass` kinds — no placement-logic changes needed.
