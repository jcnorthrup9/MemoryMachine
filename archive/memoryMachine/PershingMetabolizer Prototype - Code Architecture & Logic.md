**Tags:** #pershing-metabolizer #threejs #architecture-reference #handoff
**Purpose:** Full code-logic reference for `PershingMetabolizer_Prototype/index.html`, written for handoff to another agent who will work on specific functions and how they play out aesthetically. Covers what each piece of code does, why it's structured that way, what's real data vs. diagrammatic stand-in, and where the open aesthetic knobs are.
**As of:** 2026-06-29, after the real-geometry rebuild (see [[Vault Conventions]] for how this file fits the rest of the vault).

---

## 1. What this prototype is

A single-page Three.js WebGL visualization of an excavation/intervention strategy for Pershing Square's 1951 underground parking garage. A 354×602ft plaza is tiled into 9ft voxels; each voxel gets an "intervention score" from its distance to a real Metro tunnel and (diagrammatically) to hospitality/amenity deficits; voxels above a threshold sink downward in quantized steps, colored on an amber→violet heat scale. Three buttons step through three cumulative "development phases."

It is **not** a generative/historical tool like `urban_interference_solver.py` (the Python engine elsewhere in this repo) — it's a fast, hand-tuned, real-geometry-grounded study model for visualizing one specific design hypothesis.

## 2. Two files, one pipeline

```
data/PershingMetabolizer/OBJ/PershingMetablismGridBase.obj   (68MB, Rhino export)
        │
        │  extract_real_geometry.py   (offline, run manually, ~1s)
        ▼
PershingMetabolizer_Prototype/real_geometry.json   (~290KB)
        │
        │  fetch() at module load (top-level await)
        ▼
PershingMetabolizer_Prototype/index.html   (the actual running app)
```

**Why split like this:** the source OBJ is 68MB `extract_real_geometry.py` parses the OBJ once, pulls out only the handful of real objects that matter (columns, tunnel, entrance, ramps, site footprint), and writes a small JSON the browser can `fetch()` directly. **This means `index.html` now requires being served over HTTP — it can no longer be opened via `file://` (double-click), because browsers block `fetch()` under the file protocol.** Run `python -m http.server 8000` from inside `PershingMetabolizer_Prototype/` and open `http://localhost:8000/index.html`.

If the Rhino model changes and a new OBJ is exported, re-run `extract_real_geometry.py` (edit the path constants at the top if the filename changes) to regenerate `real_geometry.json`. Nothing else needs to change unless the *names* of the objects inside the OBJ shift (see §3).

## 3. `extract_real_geometry.py` — how it identifies things inside the OBJ

The OBJ has 293 named objects, but Rhino's export **does not preserve the original layer/object names** — everything comes out as `object_1`, `object_2`, etc. The script identifies what's what purely by **vertex-count bucketing**, discovered by one-time manual inspection:

| Bucket (vertex count) | Count | What it is |
|---|---|---|
| 24v each | `object_1`, `object_2` | `object_1` = the real Metro tunnel (60×74×913.8ft box). `object_2` = the secondary Hill/4th entrance (60×60×54.5ft box), positioned near the tunnel's north end. |
| 3042v each | `object_3`..`object_6` | 4 thin (1ft-thick) slabs spanning the full site footprint at different elevations — the unfinished stepped terrace levels. **Used only for the site footprint bounding box; not rendered.** |
| 424v each | `object_7`..`object_12` | Two spiral-ramp structures, each modeled as 3 stacked 12ft-thick plates (one per parking level). Two clusters of 3 = the two real ramps. |
| 1085–1105v each | 274 objects (`object_13` is the prototype) | The 274 real garage columns. Vertex count varies slightly per column (modeling noise), but they're geometrically near-identical, 2.2×2.2ft footprint, 30ft tall. |

**If you ever need to re-identify objects after a re-export:** run the bucketing scan again (see the `mesh_for`/bucket logic pattern in the script, or just re-derive vertex-count histograms) — don't assume `object_1` is always the tunnel; confirm via bounding-box dimensions (tunnel is the one box-shaped object that's exactly 60ft wide and ~900ft+ long).

### Coordinate system gymnastics (important)

1. **Global vs local vertex indices:** OBJ face lines (`f 14795/... 15761/...`) use indices that are **global and cumulative across the whole file**, not reset per object. The script tracks a running `global_verts` list and remaps to compact local indices per extracted object.
2. **Grade plane:** All 274 real columns share the **exact same** `top_y` value (3.728271245956421 in raw OBJ units) — this is the unambiguous, real "grade" (plaza surface) reference. Every other depth in the output (tunnel, entrance, ramps) is pre-shifted so **y=0 means real grade** in the JSON, matching how `index.html` already treats y.
3. **Site-local origin:** The 4 terrace slabs give a clean axis-aligned bounding rectangle (354.14 × 602.40ft) — its SW corner (`site_min_x`, `site_min_z` in OBJ units) becomes site-local `(0,0)`. Every other extracted object's x/z is shifted by this same offset, so columns/tunnel/entrance/ramps are all guaranteed to land in one consistent frame **without needing to cross-reference the SVG at all** (this was the old, unsolved problem — the tunnel used to be anchored by a proportional guess because the OBJ and SVG exports had different unconfirmed origins; now the tunnel and columns come from the *same* OBJ export, so they're trivially co-registered).
4. **Axis mapping:** OBJ `x` → site-local `x` (the 354ft short axis). OBJ `z` (third coordinate on each `v` line) → site-local `z`, called `y` inside `index.html`'s own "logical site coordinate" naming (a holdover from the old square-grid version — see §6). OBJ `y` → vertical, shifted to be grade-relative.
5. **Tunnel endpoints:** The tunnel box's two end-caps are separated by a simple `z > 600` threshold (the two ends are ~900ft apart in raw z, so there's no ambiguity). The script does **not** assume which end is shallower — it computes both endpoints' depths and assigns "shallow"/"deep" by direct comparison. (An earlier version of this script had the labels backwards from a bad manual read of interleaved vertex data — worth remembering if depth-related numbers ever look surprising again.)

### What's real vs. what's still a placeholder

- **Real:** site footprint, all 274 column positions + real column mesh, tunnel mesh + position + slope, secondary entrance, both ramps.
- **Diagrammatic (unchanged from before this rebuild):** the two `DEFICIT_HOTSPOTS` in `index.html` — stand-ins for real hospitality/amenity deficit data that exists in `data/amenity_deficits.json` but hasn't been spatially integrated into this prototype yet. If someone wants to make this real too, that JSON is the source.
- **Excluded by design (not a bug):** the 4 terrace slabs (`object_3..6`) are extracted only for their bounding box, never rendered as geometry — per an earlier explicit decision to keep the plaza surface clean/abstract rather than show the unfinished stepped terrain. Easy to add back later (the meshes are sitting right there in the OBJ, same extraction pattern as the ramps) if wanted.

## 4. `real_geometry.json` schema

```jsonc
{
  "_meta": "...",                         // explains the coordinate convention in prose
  "site": { "width_ft": 354.14, "length_ft": 602.4 },
  "grade_y_raw": 3.728271245956421,       // raw OBJ units, informational only -- everything else is already shifted
  "column_prototype_mesh": { vertices: [...flat xyz, local to own base-center...], faces: [...], vertex_count, face_count, centroid_xz, top_y, bbox },
  "column_height_ft": 30.0,
  "column_positions": [ { "x": ..., "z": ... }, ... ]   // 274 entries, site-local, NOT including height/rotation (mesh is symmetric enough to ignore rotation)
  "tunnel_mesh": { vertices, faces, ... },               // site-local absolute coords, y already grade-relative
  "tunnel_endpoints": { "shallow": {x,z,depth_ft}, "deep": {x,z,depth_ft} },
  "secondary_entrance_mesh": { ... },
  "secondary_entrance_anchor": { x, z, top_depth_ft, bottom_depth_ft },
  "ramp_meshes": { "cluster_a": [mesh, mesh, mesh], "cluster_b": [mesh, mesh, mesh] },  // 3 stacked levels each
  "ramp_anchors": { "cluster_a": {x,z,half_width_ft,half_length_ft,top_depth_ft,bottom_depth_ft}, "cluster_b": {...} }
}
```

`column_prototype_mesh` is the **only** column mesh — it's recentered to its own local base (x/z centroid → 0, top → y=0), then instanced 274 times in `index.html` via `THREE.InstancedMesh`, one transform per `column_positions` entry. This is why there's one mesh definition but 274 columns on screen.

All other meshes (`tunnel_mesh`, `secondary_entrance_mesh`, each `ramp_meshes` level) are **not** recentered — their vertices are already absolute site-local coordinates, so `index.html` just builds geometry from them directly and offsets the whole thing once by `toWorld(0,0,0)` (see §5.6).

## 5. `index.html` walkthrough

### 5.1 HTML/CSS shell (lines 1–56)
Static UI chrome: the `#ui` panel (title + 3 phase buttons + description text), the `#legend` color key, and the `#hint` text. Pure CSS, no logic. The importmap pins `three@0.160.0` from a CDN — if you upgrade Three.js versions, check `OrbitControls`, `InstancedMesh.instanceColor`, and `TubeGeometry` API stability (the latter is no longer used, see §5.7).

### 5.2 Constants block (lines 62–122)
- `const REAL = await (await fetch('./real_geometry.json')).json();` — **top-level await**, which only works because the script tag is `type="module"`. Everything below this line can assume `REAL` is fully loaded.
- `SITE_WIDTH_FT` / `SITE_LENGTH_FT` — the real rectangle, replacing the old `SITE_FT` square.
- `VOXEL_FT = 9`, `NX`/`NZ` — the heat-map resolution. 9ft was inherited from the old `27ft bay / 3` subdivision; it's an arbitrary aesthetic/performance choice, not tied to anything real. **Lowering this increases voxel count quadratically (NX×NZ) — currently ~40×67 ≈ 2680 voxels; dropping to 6ft would be ~605×... check performance before going much finer.**
- `GARAGE_DEPTH_FT = 30` — real, cross-validated independently from both elevation SVGs (see `urban_interference_solver.py`).
- `MAX_EXCAVATION_FT = 90` — purely a Z-formula scaling ceiling, picked to give headroom over the real tunnel's ~70ft max depth. **Aesthetic knob:** raising this makes the violet "deep excavation" end of the heat gradient reach further before maxing out.
- `STEP_FT = 9` — the quantization step for the stepped-displacement look. **Aesthetic knob:** smaller = smoother/more organic terrain, larger = more brutalist/blocky terracing.
- `COLUMN_CLEARANCE_FT = 13.5` — Phase 3's "structural jacket" radius around real columns/ramps where excavation depth gets dampened.
- `TRANSIT_FALLOFF_FT = 37.8` — controls how tight/wide the transit-influence gradient is around the tunnel line. **Aesthetic knob:** smaller = a narrower, more dramatic cut hugging the tunnel; larger = a broader, gentler basin.
- `THRESHOLD = 0.35` — the score a voxel needs before it excavates at all. **Aesthetic knob:** this is the single biggest lever on how much of the plaza looks "activated" vs. flat.
- `METRO_LINE` — built directly from `REAL.tunnel_endpoints`, no more guessing.
- `METRO_DEPTH_FALLBACK_FT` — used only where `transitInfluence ≈ 0` (far from the tunnel), so the depth-floor lerp has something sane to fall back to.
- `DEFICIT_HOTSPOTS` — **the one remaining diagrammatic array.** Two hard-coded points with strength/radius, proportionally placed on the real footprint's west edge. Anyone doing aesthetic work on Phase 2's "Metabolic Expansion" scoops should look here first.
- `PHASE_DESCRIPTIONS` — the UI copy show under the phase buttons. Purely textual, no logic dependency.

### 5.3 Helpers (lines 124–162)
- `clamp01`, `lerp` — trivial.
- `distToSegment` — closest point + parametric `t` (0–1) along a 2D line segment; used to find where on the tunnel line a voxel projects, both for distance *and* for interpolating depth along the slope.
- `nearestColumnDist(x, y)` — **brute-force** nearest-neighbor scan over all 274 real column positions. Runs once per voxel inside `buildBaseVoxels()` (not per-frame), so ~2680 voxels × 274 columns ≈ 734K ops one-time — trivially fast. If voxel count ever grows by 10×+, consider a spatial grid/quadtree, but there's no evidence it's needed yet.
- `nearestRampDist(x, y)` — point-to-rectangle distance against the two real ramp footprints (`ramp_anchors`), mirroring the exclusion logic already in the Python solver (`is_on_ramp_void`).

### 5.4 Voxel grid builder — `buildBaseVoxels()` (lines 164–193)
Builds a flat array of `NX × NZ` voxel records, **once**, independent of phase. Each voxel stores: grid index, world position, `localMetroDepth` (the tunnel's depth interpolated to this voxel's nearest point on the tunnel line), `transitInfluence` (exponential falloff from the tunnel), `deficitInfluence` (sum of exponential falloffs from each diagrammatic hotspot, clamped 0–1), and `colDist` (distance to nearest real column OR ramp, whichever is closer). This separation — compute once, re-score per phase — is why phase-switching is instant with no rebuild.

### 5.5 Scoring & displacement — `scoreForPhase()`, `zForVoxel()` (lines 195–228)
This is the conceptual core of the whole prototype:

- **`scoreForPhase`**: phases are **additive, not averaged**. Phase 1 = transit only. Phase 2 = transit + 60% of deficit. Phase 3 = transit + 100% of deficit (clamped to 1). This was a deliberate earlier fix — averaging made Phase 2's active area *shrink* relative to Phase 1, which fought the "expansion" narrative the phases are supposed to tell.
- **`zForVoxel`**: implements `Z_target = max(-depthFloor, -score × MAX_EXCAVATION_FT)`, then quantizes to `STEP_FT` increments, then clamps so it never exceeds the real tunnel depth at that point (`depthFloor`, itself a blend of the far-field fallback and the real local tunnel depth, weighted by transit influence). Phase 3 additionally softens the cut near real columns/ramps (`stepped * 0.4`) — the "structural jacket."

**If another agent is asked to change how the excavation *behaves*, this function and `scoreForPhase` are where that logic lives — not in the rendering code below.**

### 5.6 Heat-map color — `voxelColor()` (lines 230–243)
Amber (`#FFF4CA`→`#FF6B00`) represents shallow/deficit-driven surface scoops; violet (`#4D00FF`→`#0A002F`) represents deep transit-anchored excavation. `depthT` (0–1, how close to `MAX_EXCAVATION_FT`) blends between them. Flat/inactive voxels are a neutral dark grey (`#3a3a3a`). **Pure aesthetic territory** — changing these four color constants is the most direct way to retheme the whole heat-map without touching any logic.

### 5.7 Scene setup (lines 245–290)
Standard Three.js boilerplate, with two things worth flagging because they were both live bugs fixed today:

1. **Fog/zoom dead zone:** `MAX_ORBIT_DISTANCE_FT` is now defined once and used for *both* `scene.fog`'s far distance (`× 1.4` for margin) and `controls.maxDistance`. They used to be computed independently (`SITE_FT * 2` for fog, `SITE_FT * 3` for max zoom), and fog faded to pure black before you hit the actual zoom limit — meaning there was a range you could scroll into where the whole scene appeared to vanish. **If you ever change one, change the other, or re-introduce this bug.**
2. **Zoom sensitivity:** `controls.zoomSpeed = 0.35` (default is `1.0`). At default speed, because `minDistance`/`maxDistance` now span a much wider real-world range than the old version, a single wheel notch could swing the camera from fully zoomed-in to fully zoomed-out. 0.35 was tuned by testing actual wheel-delta-to-distance-change ratios; if min/maxDistance change significantly, re-check this.

`toWorld(wx, wy, y)` recenters site-local coordinates (origin at the real footprint's SW corner) to a THREE.js world position centered at the origin — this is the one function basically everything else routes through before adding anything to the scene.

### 5.8 `buildRealGeometry()` (lines 292–299)
Tiny helper: turns one of the flat `{vertices, faces}` mesh objects from `real_geometry.json` into a `THREE.BufferGeometry` with computed normals. Used for the column prototype, tunnel, entrance, and all 6 ramp-level meshes. There is no shared material/instancing logic here — that's handled by each call site.

### 5.9 Plaza voxels — `InstancedMesh` (lines 301–335)
One `BoxGeometry` (the 9ft voxel module), instanced `NX × NZ` times. Two non-obvious bits:
- The base geometry needs its own dummy per-vertex `color` attribute (`fill(1)`, i.e. white) — `InstancedMesh.instanceColor` is silently ignored by the `vertexColors` shader path otherwise, and every instance renders pure black. This was a real bug found early in this prototype's life; don't remove that line.
- `applyPhase(phase)` is the **only** function that touches the instanced transforms/colors after initial load — it's called once per button click, looping over all voxels, calling `zForVoxel`/`voxelColor`, and writing the result into the instance matrix/color buffers. Not run per-frame.

### 5.10 Real columns — `InstancedMesh` (lines 337–350)
Same instancing pattern as the voxels, but static (set once, never updated after initial placement) and using the real column mesh instead of a box. 274 instances, one `dummy.position.copy(toWorld(c.x, c.z, 0))` each. No rotation is applied — the column mesh is roughly axially symmetric enough that this doesn't matter visually.

### 5.11 Floor plate (lines 352–357)
Just a wireframe box at `-GARAGE_DEPTH_FT`, sized to the real rectangle. Purely a depth-reference visual, not load-bearing for any logic.

### 5.12 Real tunnel / entrance / ramps (lines 359–382)
`placeRealMesh()` is a tiny factory: build geometry, assign material, offset by the single shared `realOffset = toWorld(0,0,0)`, add to scene. Because every one of these meshes' vertices are already absolute site-local coordinates (per §3.3), they all need exactly this one offset and nothing else — no per-element anchoring math. Materials are currently: tunnel = dark green + cyan-green emissive (`#00ff99`), entrance = dark brown + amber emissive (`#ff8a2b`, matching the UI's accent color), ramps = neutral grey concrete-like. **All pure aesthetic choices, easy to retheme independently of the geometry.**

### 5.13 UI wiring (lines 384–396)
Three buttons, each calling `setPhase(n)`, which updates the active-button styling, swaps the description text, and calls `applyPhase(n)`. `setPhase(1)` is called once on load to establish the initial state.

### 5.14 Animation loop (lines 398–410)
Standard `requestAnimationFrame` loop calling `controls.update()` (needed for damping) and `renderer.render()`. Nothing per-frame touches voxel/column data — all of that is event-driven from `setPhase`.

## 6. Naming quirk to know about

Inside the scoring code (`buildBaseVoxels`, `distToSegment`, `METRO_LINE`, `DEFICIT_HOTSPOTS`), the second horizontal axis is called `y` (as in `wx, wy`), even though everywhere else (camera, `toWorld`, real_geometry.json) the same axis is the 602ft-long `z`. This is a holdover from the original square-grid version's "logical site coordinates" convention (x = Olive→Hill, y = 6th→5th, separate from the vertical axis). It's not a bug, just an inconsistent naming convention across two halves of the same file — worth normalizing if doing a larger refactor, but low priority.

## 7. Known open items / honest caveats

- **Axis orientation is assumed, not confirmed.** The terrace footprint's SW corner (min x, min z) is treated as site-local `(0,0)`, but which real-world corner (NW/SW/etc. relative to actual Olive St / 5th St / 6th St / Hill St) that corresponds to has not been independently verified against a site plan — only the *relative* geometry (columns/tunnel/ramps all correctly positioned *relative to each other*) is guaranteed.
- **Deficit hotspots are still diagrammatic** (§3, "What's real vs. placeholder").
- **Terrace/stepped terrain is extracted but deliberately not rendered** — easy to add back, same pattern as the ramps.
- **No rotation is applied to instanced columns** — fine for this roughly-square column profile, would need fixing if a future column mesh is asymmetric.
- **VOXEL_FT, STEP_FT, COLUMN_CLEARANCE_FT, TRANSIT_FALLOFF_FT, THRESHOLD, MAX_EXCAVATION_FT** are all aesthetic/behavioral tuning constants with no single "correct" real-world value — they were chosen by eye for a legible heat-map, not derived from any code or research. Treat them as the primary knobs for anyone iterating on how the visualization *feels*.

## 8. Quick reference: where to make common changes

| Want to change...                                    | Look at                                                                                                                       |
| ---------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------- |
| How much of the plaza excavates                      | `THRESHOLD`                                                                                                                   |
| How dramatic/contained the cut near the tunnel looks | `TRANSIT_FALLOFF_FT`                                                                                                          |
| Smooth vs. terraced/blocky excavation                | `STEP_FT`                                                                                                                     |
| Heat-map colors                                      | `AMBER_A/B`, `VIOLET_A/B`, `FLAT_COLOR` in `voxelColor()`                                                                     |
| Deficit hotspot locations/strength (Phase 2/3)       | `DEFICIT_HOTSPOTS`                                                                                                            |
| Column/tunnel/ramp/entrance materials                | the `*Mat` constants in §5.9–5.12                                                                                             |
| Camera framing on load                               | `camera.position.set(...)` in §5.7                                                                                            |
| Zoom feel                                            | `controls.zoomSpeed`, `controls.minDistance`/`maxDistance`                                                                    |
| Whether terraces render                              | would need new code following the ramp-placement pattern, pulling `object_3..6` back into `extract_real_geometry.py`'s output |
| Real geometry itself (if Rhino model changes)        | `extract_real_geometry.py`, then re-run it                                                                                    |
