# Memory Machine — Gemini Handoff
**Date:** 2026-04-07  
**Prepared by:** Claude (Sonnet 4.6) for handoff to Gemini

---

## 1. Project Overview

Memory Machine is a FastAPI + Three.js/SVG architectural cross-pollination tool.  
- A **local Llama 3 LLM** (via Ollama) selects SVG layers from precedent parks  
- Python (`urban_engine.py`) places/scales those layers onto a base map (Pershing Square)  
- The frontend renders a live 2D SVG canvas and a Three.js 3D scene  
- A **Zonal Constraints HUD** shows real-time APA zoning compliance (SOFT/HARD/PROG/BLUE percentages)

---

## 2. File Structure

```
MemoryMachine/
├── app.py                        # FastAPI router (204 lines) ← MODIFIED (untracked in static/)
├── index.html                    # SPA entry — served directly by app.py ← MODIFIED
├── main.js                       # OLD root-level file (7 lines changed) — NOT the active file
├── templates/index.html          # Jinja template — legacy, not used by app.py
├── static/
│   ├── main.js                   # ← ACTIVE main controller (833 lines, UNTRACKED by git)
│   ├── style.css                 # ← ACTIVE styles (635 lines, UNTRACKED)
│   ├── master_style.css          # backup / reference
│   └── js/
│       ├── constants.js          # Site/layer definitions, COORDINATE_SYSTEM
│       ├── state.js              # MemoryState store + getProgramStats() (178 lines)
│       └── engine2D.js           # SVG render engine (236 lines)
├── logic/
│   ├── urban_engine.py           # remix_layers(), GuidelineManager (237 lines)
│   ├── ai_synthesizer.py         # LLM calls, generate_spatial_seed()
│   └── geometry_engine.py        # build_geometries() for Three.js
├── data/ParkSVG/
│   ├── Pershing_Square.svg       # Base site (modified — SVG content updated)
│   ├── parc_de_la_villette.svg   # Precedent (modified — SVG content updated)
│   ├── ZaryadyePark.svg
│   ├── Schouwburgplein.svg
│   └── GardensByTheBay.svg
└── urban_design_guidelines.md    # APA zoning targets parsed by GuidelineManager
```

**Key point:** `index.html` (root) loads `static/style.css`, `static/js/constants.js`, `static/js/state.js`, `static/js/engine2D.js`, `static/main.js` — in that order. The root `main.js` is **not loaded** by the current app.

---

## 3. Script Load Order (index.html)

```html
<script src="/static/js/constants.js"></script>   <!-- window.SITES, TARGET_LAYERS -->
<script src="/static/js/state.js"></script>         <!-- window.MemoryState -->
<script src="/static/js/engine2D.js"></script>      <!-- window.Engine2D, window.renderRemixSVG -->
<script src="/static/main.js"></script>             <!-- orchestrator, init(), generate() -->
```

All modules attach to `window.*` — no ES modules, for compatibility.

---

## 4. Backend API Endpoints (app.py)

| Route | Method | Purpose |
|-------|--------|---------|
| `/` | GET | Serves `index.html` via `FileResponse` |
| `/api/available-sites` | GET | Scans `data/ParkSVG/`, returns `{sites:[{id,name,bounds}]}` |
| `/api/diagram-data/{site}` | GET | Returns raw SVG text for a site, case-insensitive match |
| `/api/guidelines` | GET | Returns `{status, data:{guidelines,metadata,primitives,locked}}` |
| `/api/generate` | POST | LLM → remix_layers → geometries → returns `{spatial_seed, geometries, narrative, diagram}` |
| `/api/export-diagram` | POST | Saves SVG/JPG/UI-capture to archive folder |
| `/static/*` | GET | StaticFiles mount |

**Important shape from `/api/guidelines`:**
```python
{
  "status": "success",
  "data": {
    "guidelines": { "SOFT": {"min":30,"max":50}, "HARD": {"min":40,"max":60}, ... },
    "metadata":   { "SOFT": ["GREEN_SPACE","SHADE"], "HARD": [...], ... },
    "primitives": { "GREEN_SPACE": "sphere", ... },
    "locked":     ["PARKING", "STREET", "BOUNDARY"]
  }
}
```
Frontend remaps this in `init()` — the remap handles both `Softscape/SOFT` key variants.

---

## 5. Key Data Flow

```
User types prompt → generate() → POST /api/generate
  → ai_synthesizer.generate_spatial_seed()  [Llama 3 via Ollama]
  → urban_engine.remix_layers(seed)          [scale + place layers]
  → geometry_engine.build_geometries()       [Three.js primitives]
  → returns {spatial_seed, geometries}

Frontend:
  spatial_seed → MemoryState.stack (array of stack items)
  Engine2D.render() → draws 2D SVG canvas from stack
  MemoryState.getProgramStats() → calculates zone percentages
  updateHUD() → updates SOFT/HARD/PROG/BLUE bars
```

---

## 6. MemoryState.stack Item Schema

```js
{
  id:          Number,           // unique; negative = locked base context
  site:        String,           // e.g. 'ParcdelaVillette'
  layerId:     String,           // e.g. 'GREEN_SPACE'
  color:       String,           // hex color
  transform:   { x, y, scale, rot },
  visible:     Boolean,          // eye-toggle
  locked:      Boolean,          // true = not editable (base context items)
  contextLayer: Boolean,         // true = skip in engine2D stack render pass
  opacity:     Number,           // optional, 0.85 default
  primitive:   String,           // 'sphere'|'disc'|'cylinder'|'box'
}
```

---

## 7. Bug Fixes Applied This Session

### Bug 1 — `cat_counts` key mismatch ✅ FIXED
**File:** `logic/urban_engine.py` line ~125  
**Problem:** `cat_counts` used `{"Softscape":0, "Hardscape":0, ...}` but `layer_to_cat` returns `"SOFT"/"HARD"` keys. Every `.get()` missed → count always 0 → solver skipped → `final_scale = 1.0` for everything → AI-generated layers ignored zoning targets.  
**Fix:**
```python
# BEFORE (broken)
cat_counts = {"Softscape": 0, "Hardscape": 0, "Active": 0, "Blue_Space": 0}
cat = layer_to_cat.get(item.get("layer", "GREEN_SPACE"), "Hardscape")

# AFTER (fixed)
cat_counts = {"SOFT": 0, "HARD": 0, "PROG": 0, "BLUE": 0}
cat = layer_to_cat.get(item.get("layer", "GREEN_SPACE"), "HARD")
```

### Bug 2 — Solver scale cap ✅ FIXED
**File:** `logic/urban_engine.py` after the 15-iteration loop  
**Problem:** If a layer lands fully outside the park boundary, `visible_area = 0` every iteration → scale grows unconstrained.  
**Fix:** Add after the loop, before jitter:
```python
final_scale = max(0.2, min(final_scale, 3.0))
```

### Bug 3 — Browser OOM crash on auto-export ✅ FIXED
**File:** `static/main.js`  
**Problem 1:** `captureDashboardUI()` (html2canvas at scale:2 on entire `.main-grid`) was firing automatically after every generation → ~31MB canvas → OOM.  
**Fix:** Removed from auto-export pipeline. Now manual-only via "Capture UI" button.  
**Problem 2:** JPG export created 2448×1584 canvas (2× scale) and never freed it.  
**Fix:** Dropped to 1× (1224×792), wrap in `Promise`, explicitly `canvas.width = 0; canvas.height = 0` after `toDataURL` to release bitmap.

### Bug 4 — Missing SVG `<defs>` block ✅ FIXED
**File:** `static/js/engine2D.js` in `render()`  
**Problem:** Intervention layers had `clip-path: url(#clip-boundary)` but `#clip-boundary` was never defined in `<defs>` → all intervention layers invisible.  
**Fix:** Insert defs block immediately after SVG creation:
```js
const defs = document.createElementNS(ns, 'defs');
defs.appendChild(this.buildBoundaryClipPath(baseSVGEl, ns, 'clip-boundary'));
svg.appendChild(defs);
```

---

## 8. Changes Applied This Session (State at Handoff)

### `static/js/state.js` — getProgramStats() rewrite ✅ APPLIED
- **Removed** the `PEDESTRIAN_PATH` early-return so those layers count as HARD
- **Removed** the residual `HARD = siteArea - occupiedArea` calculation
- **Added** direct area measurement for HARD layers (same path-bbox logic as SOFT/PROG/BLUE)
- **Changed** initial fallback from `{HARD:100}` to `{HARD:0}` — no more fake 100% on load
- **Fixed** regex `lastIndex` bleed: moved `const re = /…/g` inside the path loop (fresh regex per path)

### `static/js/engine2D.js` — contextLayer skip ✅ APPLIED
Added one guard in the stack render loop:
```js
if (item.contextLayer) return; // Already drawn by context-group pass
```

### `static/main.js` — base context injection + manual picker ✅ APPLIED

**New functions added:**
- `_getLayerColor(layerId)` — maps layer ID to hex color by zone type
- `_injectBaseContext()` — pushes STREET, PARKING, PEDESTRIAN_PATH, STREET_FURNITURE from PershingSquare into the stack as `locked:true, contextLayer:true` items on init and after Clear
- `_populateLayerPicker(siteId)` — fetches site SVG, scans `g[id]` elements, populates layer dropdown
- `refreshStackUI()` updated — locked items show `⬡` icon, not eye toggle; clicking locked items is a no-op

**init() changes:**
- After `fetchSVG('PershingSquare')`: calls `_injectBaseContext()` then `refreshStackUI()`
- Clear Stack button: calls `_injectBaseContext()` after `MemoryState.clear()`
- New event listeners for `picker-site`, `picker-layer`, `picker-add-btn`

### `index.html` — Manual layer picker HTML ✅ APPLIED
Added inside `.stack-editor`, between `#stack-list` and `#xform-panel`:
```html
<div class="layer-picker">
  <select id="picker-site" class="picker-select">...</select>
  <select id="picker-layer" class="picker-select" disabled>...</select>
  <button id="picker-add-btn" class="picker-add-btn" disabled>+ ADD</button>
</div>
```

### `static/style.css` — New rules ✅ APPLIED
- `.stack-list` max-height: `110px → 180px`
- `.layer-picker`, `.picker-select`, `.picker-add-btn` — new picker styles
- `.stack-item.locked-layer` — dimmed, non-hoverable
- `.stack-lock-icon` — `⬡` glyph styling
- `.stack-eye-btn` — eye toggle button
- `.stack-item.hidden-layer` — dimmed + grayscale swatch

---

## 9. Pending / Not Yet Working

### Manual layer picker — site ID mismatch risk
The picker populates from `data/ParkSVG/*.svg` filenames. The site IDs in the picker HTML (`ParcdelaVillette`) must exactly match what `/api/diagram-data/{site}` expects. The backend normalizes: `file.lower().replace("_","").replace(" ","")`. So `parc_de_la_villette.svg` → `id = "parcdelavillette"` (all lowercase). But the picker option values use `ParcdelaVillette` (camel case). **This will cause a 404.** The picker site IDs need to match the `id` field returned by `/api/available-sites`.

**Recommended fix:** Populate the picker from `/api/available-sites` dynamically in `init()`, same way the header dropdown is populated. The picker HTML can have static fallbacks but the JS should overwrite them.

### HUD baseline accuracy
`getProgramStats()` uses AABB (axis-aligned bounding box) of each layer's path coordinates, not the actual clipped polygon area. For complex multi-path layers (e.g., STREET with many disconnected segments), the AABB will be much larger than the real drawn area, inflating percentages. This is a known approximation — good enough for HUD guidance, not pixel-accurate.

### `/api/available-sites` site ID casing
`get_available_sites()` returns `site_id = file[:-4].replace("_","").replace(" ","")` — this produces lowercase IDs like `pershingsquare` (since filename is `Pershing_Square.svg` → `PershingSquare` after replace, but `.replace("_","")` on `Pershing_Square` gives `PershingSquare` — wait, actually it preserves case). Check: `Pershing_Square.svg` → `[:-4]` = `Pershing_Square` → `.replace("_","")` = `PershingSquare` → `.replace(" ","")` = `PershingSquare`. OK, that's correct camel case. But `parc_de_la_villette.svg` → `parcdelavillette` (all lowercase because filename is lowercase). This inconsistency between sites will cause mismatches.

**Recommended fix:** Normalize all site IDs to a single consistent format in both backend and frontend.

### `GardensByTheBay` not in `MemoryState.svgCache`
`svgCache` in `state.js` only pre-declares keys for 4 sites. `GardensByTheBay` will work (the cache is just a plain object, missing keys return `undefined`), but `fetchSVG` checks `if (MemoryState.svgCache[siteId]) return` — this works correctly since `undefined` is falsy.

---

## 10. Architecture Decisions to Keep

- **BOUNDARY-based registration:** `fitScale = Math.min(baseBBox.w/precBBox.w, baseBBox.h/precBBox.h)` — this is canonical and used identically in `engine2D.render()` and `getProgramStats()`. Do not change independently.
- **Negative IDs for base context:** `id: -(i+1)` for locked layers. Never use `parseInt` to identify them — use `item.locked` or `item.contextLayer`.
- **No ES modules:** All JS uses `window.*` globals. Do not convert to `import/export` without updating all script tags to `type="module"`.
- **RAF loop ownership:** `_startRenderLoop()` always calls `_stopRenderLoop()` first. `_initOrbitControls(canvas)` no-ops if same canvas is passed twice. Both protect against listener accumulation across Draft↔Dream mode switches.
