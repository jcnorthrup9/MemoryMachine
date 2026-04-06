# Memory Machine — Build Log & Roadmap

## What This App Does

**Memory Machine** is an architectural cross-pollination tool for redesigning Pershing Square (DTLA). It lets you pull diagram layers from four reference parks (Pershing Square, Schouwburgplein, Parc de la Villette, Zaryadye Park), stack them together in a 2D remix view, and deploy the composition to a lofi 3D viewer.

---

## Completed Tasks

### Phase 1 — Data & Rhino Pipeline
- [x] **OSM Context Builder** (`logic/rhino_osm_builder.py`) — Scrapes OpenStreetMap data for Pershing Square surroundings and extrudes building footprints into Rhino via RhinoScriptSyntax. Fixed UTF-8 encoding error (`# -*- coding: utf-8 -*-`).
- [x] **Rhino Layer Parser** (`logic/rhino_diagram_parser.py`, `logic/batch_rhino_parser.py`) — Parses Rhino `.3dm` files and exports layer geometry to SVG.
- [x] **Zine Compiler** (`logic/zine_compiler.py`) — Compiles annotated diagram images into a printable zine layout.
- [x] **Autonomous Orchestrator** (`logic/autonomous_diagram_orchestrator.py`) — Chains diagram generation steps end-to-end.
- [x] **Four Park SVGs exported** from Rhino with consistent layer naming convention:
  - `PershingSquare.svg` — layers: BOUNDARY, BUILDINGS, BUILDINGS::hatch, STREET, STREET_FURNITURE, GREEN_SPACE, WATER_FEATURES, UNIQUE_ELEMENTS, PEDESTRIAN_PATH, PARKING, PARKING::entrances, INFRASTRUCTURE_CONNECTIONS
  - `Schouwburgplein.svg` — includes proper SHADE layer (5,379 paths)
  - `ParcdelaVillette.svg`
  - `ZaryadyePark.svg`

### Phase 2 — FastAPI Backend
- [x] **`/api/generate`** — Sends prompt + ChromaDB precedent reviews to Claude/Anthropic API, returns narrative + Three.js geometry JSON.
- [x] **`/api/diagram-data/{site}`** — Serves raw SVG files from `data/ParkSVG/`.
- [x] **`/api/site-context`** — Returns box/cylinder geometry for surrounding buildings.
- [x] **`/api/bake`** — Triggers Rhino bake pipeline.

### Phase 3 — 2D Remix Engine (`templates/index.html`)
- [x] **SVG layer rendering** — Parses `<g id="LAYER_ID">` groups from Rhino-exported SVGs. Uses `pathCoordBBox()` for coordinate-only bounding box (no DOM dependency), `getBoundaryBBox()` to derive the Pershing Square site frame.
- [x] **Multi-layer stack system** — Replace single-precedent slider with a stackable layer system. Each stack item has: `{ id, site, layerId, color, label, visible, transform: {x, y, scale, rot} }`.
- [x] **Per-layer transform controls** — X/Y offset, scale, rotation sliders per stack item. Active editing item highlighted.
- [x] **clipPath masking** — All precedent layers clipped to Pershing Square BOUNDARY bbox rectangle.
- [x] **Site context base map** — BUILDINGS, BUILDINGS::hatch, STREET, PARKING, INFRASTRUCTURE_CONNECTIONS shown as dark underlay. PARKING::entrances sublayer stripped via attribute selector `[id="PARKING::entrances"]`.
- [x] **SHADE layer category** — Added as distinct layer type (separate from PEDESTRIAN_PATH).
- [x] **Visibility toggles** — Per-item eye icon in stack list.
- [x] **`resolveLayerGroup()`** — Handles normal layers, virtual splitFrom layers (by stroke-width), and excludeSW filtering.
- [x] **`SITE_CONTEXT_LAYERS` constant** — Shared between live render and export to prevent divergence.

### Phase 4 — Export System
- [x] **SVG export** — Full-fidelity vector export via `XMLSerializer`, filename auto-stamped with date/time.
- [x] **JPEG export (color)** — 3400×2200px (17"×11" @ 200dpi), black background, colored layers — via Canvas `drawImage` from SVG data URL.
- [x] **JPEG export (linework)** — Same resolution, white background, original Rhino hatching/lineweights preserved (stroke colors kept, fills cleared).
- [x] **Export uses live-viewer visibility** — Only elements visible in the 2D panel are included in exports.

### Phase 5 — Save / Load System
- [x] **localStorage compositions** — Save and reload named compositions (full stack state). Autosave on every stack change.
- [x] **Composition slot UI** — Named slots with delete buttons in the left panel.

### Phase 6 — Lofi 3D Inset
- [x] **Three.js isometric inset** (`#remix-inset-canvas`) — Live orthographic preview in the 2D tab, updates on every stack change.
- [x] **`updateRemixInset()`** — Renders stack layers as flat extruded shapes in an orthographic isometric camera.

### Phase 7 — Deploy to 3D (Fixed)
- [x] **`deployTo3D()` rewritten** — Now iterates `MemoryState.stack` instead of removed `MemoryState.precedentSVG`. Mirrors the exact 2D transform math:
  - `fitScale = Math.min(bbox.w / precVB.w, bbox.h / precVB.h)`
  - `ts = fitScale * item.transform.scale`
  - SVG → Three.js: scale → center on origin → `rotateX(-π/2)` → `rotateY` → translate to boundary center + offset
  - Per-item color (`item.color`) and extrusion height from `LAYER_HEIGHT` table.
  - Guard changed from `!precedentSVG` → `stack.length === 0`.

---

## Known Issues / In Progress

- [ ] **3D viewer renders but geometry may not be visible** — Transform math is implemented but the scene may need camera/scale calibration. `SVG_SCALE = 0.04` may need tuning. Possible Y-flip issue in precedent center offset step.
- [ ] **`deployTo3D()` does not yet show Pershing Square base geometry** (BUILDINGS, STREET) in the 3D view as context. Currently only stack items are extruded.

---

## TODO — Next Steps

### Phase 8: AI Parametric Sculptor & ComfyUI Prep
- [x] **Task 15: UI Toggle for Draft vs. Dream Mode (`index.html`, `style.css`)**
  - Draft/Dream toggle added above Deploy button. `MemoryState.dreamMode` tracks state. Button label changes to "Dream to 3D" when active.
- [x] **Task 16: 2D Footprint Math Extraction (`index.html`)**
  - `extractFootprints()` computes `{ cx, cz, width, depth, rotRad }` per visible stack item in Three.js world units, mirroring the deployTo3D transform math.
- [x] **Task 17: Backend ComfyUI Bridge Prep (`app.py`)**
  - `/api/generate-3d` endpoint added. Queries ChromaDB per layer, prompts Gemini for per-footprint architectural description. `generate_comfyui_mesh(prompt, footprint)` stub returns `glb_url: null` — structured to swap in the `localhost:8188` API call when ComfyUI is running.
- [x] **Task 18: Dynamic .glb Loading (`index.html`)**
  - `GLTFLoader` added via CDN. Dream mode branch in `deployTo3D()` POSTs footprints to `/api/generate-3d`, loads each `.glb` response, scales/rotates/positions mesh to fit its footprint bbox. Falls back gracefully when `glb_url` is null (stub phase). Scene setup extracted to shared `initSceneShell()`.

### High Priority

- [ ] **Debug 3D viewer geometry placement** — Verify that stack layers appear in the scene. Likely issues: (1) `SVG_SCALE` factor too small/large for the scene camera distance; (2) Y-axis flip in the `geom.translate(-precCx * SVG_SCALE * ts, precCy * SVG_SCALE * ts, 0)` step; (3) camera starting position may not be looking at the geometry centroid.
  - Suggested debug: add a bright `BoxGeometry(5,5,5)` at `(bboxCx3d, 2.5, bboxCy3d)` to verify scene center.

- [ ] **Add Pershing Square base geometry to 3D view** — Extrude BUILDINGS from PershingSquare.svg as grey context masses. Extrude STREET as thin dark slabs. This gives the remix layers spatial grounding.

- [ ] **AI-informed 3D generation** — When "Generate 3D Intervention" is clicked, send the current stack composition (site names, layer types, positions, scales) + ChromaDB narrative context to the AI. Use the response to drive richer geometry: variable-height attractors, canopy structures, programmatic massing — not just flat extrusions.

### Medium Priority

- [ ] **Rhino bake from stack** — `bakeToRhino()` should write stack layers back to Rhino with correct world coordinates, matching the 2D/3D placement math.
- [ ] **Diagram tab auto-generate** — After Generate, auto-populate the Diagram tab with a Mermaid or SVG diagram summarizing the spatial logic of the remix.
- [ ] **Precedents tab from stack** — Auto-populate Precedents tab with the review cards for each site currently in the stack (from ChromaDB).
- [ ] **Layer opacity control** — Add per-item opacity slider (currently hardcoded to 0.85).

### Low Priority / Stretch

- [ ] **Mobile / touch support** — Pan/zoom gestures on 2D canvas.
- [ ] **Undo/redo** — Stack history with Ctrl+Z.
- [ ] **Export to Rhino via Grasshopper** — Write geometry as GH-readable JSON for parametric downstream workflow.
- [ ] **Multi-site boundary** — Allow non-Pershing-Square sites as the base boundary frame (clip to any park's BOUNDARY, not just Pershing).

---

## Architecture Summary (for Gemini handoff)

```
Memory Machine
├── app.py                          FastAPI server
│   ├── /api/generate               Claude AI → narrative + Three.js JSON
│   ├── /api/diagram-data/{site}    Serves SVGs from data/ParkSVG/
│   ├── /api/site-context           Returns surrounding building geometry
│   └── /api/bake                   Triggers Rhino bake
│
├── templates/index.html            Single-page app (all JS inline)
│   ├── MemoryState                 { stack[], svgCache{}, editingId, ... }
│   ├── renderRemixSVG()            2D SVG compositor (clip + transform)
│   ├── buildExportSVG()            Export-faithful copy of renderRemixSVG
│   ├── deployTo3D()                Stack → Three.js ExtrudeGeometry
│   ├── updateRemixInset()          Orthographic isometric inset preview
│   └── localStorage save/load      Named composition persistence
│
├── static/style.css                All layout + component styles
│
├── data/ParkSVG/                   Rhino-exported SVGs (4 parks)
│   ├── PershingSquare.svg
│   ├── Schouwburgplein.svg
│   ├── ParcdelaVillette.svg
│   └── ZaryadyePark.svg
│
├── data/pershing_osm.json          OpenStreetMap data (2,129 elements)
│
└── logic/
    ├── rhino_osm_builder.py        OSM → Rhino geometry
    ├── batch_rhino_parser.py       Batch SVG export from Rhino
    ├── autonomous_diagram_orchestrator.py
    ├── zine_compiler.py
    └── scrapbook_compiler.py

Key constants in index.html:
  SITE_CONTEXT_LAYERS = ['BUILDINGS','BUILDINGS::hatch','STREET','PARKING','INFRASTRUCTURE_CONNECTIONS']
  TARGET_LAYERS       = [BOUNDARY, GREEN_SPACE, SHADE, WATER_FEATURES, STREET, PEDESTRIAN_PATH,
                         MAJOR_ATTRACTORS, MINOR_ATTRACTORS, UNIQUE_ELEMENTS, STREET_FURNITURE, PARKING]
  LAYER_HEIGHT        = { per-layer extrusion heights in Three.js units }
  SVG_SCALE           = 0.04  (SVG pts → Three.js world units)
```
