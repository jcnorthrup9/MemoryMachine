Memory Machine — Current State of the App
===========================================
*2026-07-12. A snapshot of what the live app actually does today, for fresh orientation — not a permanent spec. Complements the session-specific `HANDOFF_07122026.md` in this same folder.*

## What this app is

"Pershing Metabolizer" — a site-intervention design tool for a real thesis project (a surface intervention on Pershing Square, downtown LA). A FastAPI backend (`app.py` + `logic/pershing_api.py`) wraps a pure-Python voxel terracing engine (`terracing_engine.py`) driven by real Rhino-extracted site geometry (`PershingMetabolizer_Prototype/real_geometry.json`); a React + Three-fiber frontend (`frontend/`) renders the result live and lets a designer paint/import design intent that feeds back into the engine.

**Three parallel front-ends exist in this repo at different maturity levels** — know which one you're looking at:
1. `PershingMetabolizer_Prototype/index.html` — superseded, JSON→BufferGeometry only.
2. `index.html` + `static/main.js` (repo root) — the **legacy AI-prompt-driven precedent remixer** ("the old app"). Served by `app.py`'s `GET /`. Not freehand paint — types a prompt, an LLM (`logic/ai_synthesizer.py`) picks/transforms real polygon layers from a curated precedent-park SVG library (`data/ParkSVG/`), optionally generates AI 3D props via ComfyUI. Exports diagrams to `archive/diagrams/generated/` (SVG/JPG, color/grey). Still useful as a diagram *source*, not itself the design-input mechanism.
3. **`terracing_engine.py` + FastAPI + React (`frontend/`)** — the live, primary target for all current work. Everything below describes this one.

## Live data flow

Slider/paint change → debounced `POST /api/pershing/rebuild` → `TerracingEngine` (voxel depth/typology) → `StructuralFramingEngine` (excavation shoring/salvage on real columns/slabs) → `TypologyAssetEngine` (amenity/tree props) → one JSON response → React `Viewport.jsx` renders everything generically by `kind`.

## Design-input mechanisms (two, independent, both feed the same masks)

1. **Paint** (`PaintOverlay.jsx`) — freehand brush strokes on a sketch-photo background, 6 categories: `canyon` (continuous excavation weight), `hardscape`, `water`, `shade`, `greenscape`, `amenity_resting` (all boolean zone masks). Categories live in one shared source, `frontend/src/paintCategories.js`.
2. **Diagram Input** (`DiagramInputPanel.jsx`, new 2026-07-11) — a sibling panel, not routed through painting: picks a recent legacy-tool diagram export, converts it via `ingest_legacy_diagram.py` (color-segments green/blue/gray/tan pixels into greenscape/water/hardscape/shade), previews the result, commits via the same `bake()` endpoint painting uses.

Both write to the same 6 masks (`WATER_MASK`, `SHADE_MASK`, `HARDSCAPE_MASK`, `GREENSCAPE_MASK`, `AMENITY_RESTING_MASK`, `SKETCH_WEIGHTS`/canyon), persisted to `outputs/cockpit/web_paint_state.json` and reloaded on backend restart.

## What painting/importing each category actually does

- `canyon` — additively blends into excavation depth alongside real transit-proximity/deficit data (`sketch_alpha` slider, default 0.75).
- `hardscape` — hard excavation veto (protected, never dug) + circulation-typology source (where foot-traffic influence crosses a threshold).
- `water` — GROTTO typology **only where excavated** (`z_ft < 0 AND is_water`) — un-excavated water paint has no visible effect yet.
- `shade` — drives tree placement (`TypologyAssetEngine.tree_specs()`, thinned to ~1 tree per 3 voxels) and a tan ground cap in the viewport; also the direct source for the circulation network's "shade" motivator attractor bucket.
- `greenscape` — pure grass ground cap only (no trees — that's shade's job as of 2026-07-11).
- `amenity_resting` — SANCTUARY typology when combined with greenscape.

## Circulation network (Space Colonization)

`circulation_network.py`'s `CirculationNetworkEngine` grows a real pedestrian network from the Metro entrance toward weighted motivators (`shade`, `water`, `rest`, `foot_traffic`, `deficit` — sliders in `ParamPanel.jsx`). Explicit action (`POST /api/pershing/grow-network`), not part of the live rebuild loop. Note: "water" motivator still only comes from already-*built* GROTTO/fountain props, not directly from the `water` mask — an asymmetry with "shade" (fixed 2026-07-11 to read its mask directly) that's flagged but not yet resolved.

## Headless-Blender "build" tier

Explicit, occasional action (`POST /api/pershing/blender-build`), separate from the live rebuild loop (Blender subprocess startup cost is real). Two things it can produce, in one subprocess call:
1. **Full-fidelity OBJ** (`?` no special params) — the terrace + every structural-framing kind, concatenated real bmesh geometry, viewable via `BlenderBuild.jsx`.
2. **Line Art SVG** (`?lineart=true`) — Blender's native Grease Pencil Line Art hidden-line removal, viewable via `LineArtOverlay.jsx`. As of 2026-07-11 this can also:
   - Include real columns/slabs as lightweight native primitives (`?include_real_context=true`) — NOT the heavy original Rhino OBJ (confirmed pathological for a different pipeline, see HANDOFF).
   - Use an arbitrary camera direction (`?view_dir=x,y,z`) instead of the one fixed isometric default — driven live from `Viewport.jsx`'s "Export Current View" button, which derives the direction from wherever the user has actually orbited an orthographic camera.
   - Split output into depth-band SVG `<g>` groups (`near`/`mid`/`far`), which Illustrator reads as layers on import.

Only one Blender build can run at a time (backend-side lock); the frontend polls job status (`GET /api/pershing/blender-build/{job_id}`).

## Vector/CAD export (`vector_export.py`, standalone script path)

A separate, older pipeline (`run_vector_export_demo.py`, not wired to any live endpoint) that produces true DXF/SVG/PNG plan cuts, section cuts, and an axonometric hidden-line view via `trimesh`'s pure-Python ray-triangle intersector. As of 2026-07-11 its terrain-mesh builder (`build_terraced_solid`) was rewritten to use real slab plates (boolean-cut with `manifold3d`) plus greedy-merged fallback boxes instead of one box per voxel — a real, dramatic face-count win (618,900 → 33,560 for the full site) that's still useful for this module's non-axonometric functions, even though `axonometric_projection()` itself turned out to have a separate, deeper `trimesh`/`rtree` scaling limitation unrelated to face count (see HANDOFF — this is why live arbitrary-view export now goes through the Blender pipeline above instead).

## Juror chat (live control)

`JurorChatBar.jsx` + `logic/juror_chat.py` — a grounded Q&A chat (local Ollama) for live thesis-defense questions, grounded in real site data (explicitly distinguishes real Rhino data from placeholder amenity/foot-traffic data). As of this session, it can also **take real action**: the model may return `{"action": {...}}` alongside its reply (adjust a motivator weight, set canyon width/depth, grow the network, toggle a real-data source), validated/clamped server-side (`_validate_action`) before the frontend dispatches it through the exact same state setters the matching UI control uses.

## Known gaps / rough edges as of this snapshot

- Port 8000 has had a persistent unkillable phantom TCP listener all session (serves stale pre-restart data, no matching Windows process) — dev work happens on port 8001 instead; `vite.config.js`'s proxy comment documents this and should be reverted once confirmed fixed (likely needs a reboot).
- The "water" motivator's mask-vs-built-props asymmetry (see Circulation network, above).
- `_getLayerColor()`'s gray catchall in `static/main.js` still conflates `PEDESTRIAN_PATH` with several out-of-scope legacy layers (`STREET`/`BOUNDARY`/`PARKING`) for diagram-import purposes — accepted as "hardscape catches everything else" for now.
- The new tan/shade color threshold in `ingest_legacy_diagram.py` is arithmetically derived, not yet empirically re-verified against a real diagram containing genuine SHADE-layer picks (none existed before this session's `_getLayerColor()` fix).
- `vector_export.py`'s standalone DXF/SVG/PNG path is not wired to any live endpoint — still a manual script (`run_vector_export_demo.py`), separate from the now-live Blender vector-export path.
