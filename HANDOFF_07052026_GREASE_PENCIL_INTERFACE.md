Handoff: Build the live in-Blender Grease Pencil painting interface
=====================================================================
*2026-07-05. For a fresh chat picking this up. Blender is already running with BlenderMCP connected (`mcp__blender__execute_blender_code`, `get_scene_info`, `get_viewport_screenshot` etc.) against the live cockpit session — use those tools to test against the real running Blender instance rather than guessing at API behavior. That practice already caught two real bugs this session (see "Traps already hit" below); don't skip it.

## The task

Add a third designer-input path to the Blender cockpit: instead of only ingesting a pre-drawn sketch file (via `sketch_weight_mapper.py` + `precompute_sketch_cache.py`, which needs PIL/svgpathtools and runs in the normal venv, not Blender's Python) or a hand-typed amenity CSV, let the user draw canyon (black) and hardscape (blue) marks **directly in the Blender viewport** and have them react live — same as the existing Sketch Alpha / Protect Hardscape / Use Real Amenity Data toggles already do.

**Design direction already confirmed with the user** (do not re-litigate): Grease Pencil strokes in the 3D viewport, converted to the weight/mask grids via **pure vector distance-falloff math implemented natively in Blender's own Python** — NOT a PIL/image round-trip, NOT a precompute-cache step. This keeps it fully live and self-contained inside Blender, consistent with how the hardscape/amenity toggles already work. The alternative considered (texture-paint on a ground plane, reusing `sketch_weight_mapper.py`'s literal raster code) was explicitly rejected because it would require bouncing out to the venv (no PIL in Blender's Python) and wouldn't be live.

## Current state of `blender_cockpit.py` — read this before writing any code

This file has grown substantially since the Grease Pencil work was paused — a separate "Structural Framing Engine" feature (canyon width/depth sliders, STEEL/WOOD material mode, shoring density, slab-harvest tonnage readout, instanced structural elements) was added independently. This is unrelated to the painting interface but **shares the same file and the same single rebuild entrypoint**. Critically:

- The function to call after baking new strokes is now **`rebuild_all(scene)`**, not `rebuild_terrace` (that name no longer exists — it was renamed when the structural engine was merged in).
- `terracing_engine.py` now also exports `StructuralFramingEngine` and `STRUCTURAL_BAY_FT` alongside `TerracingEngine`.
- The panel class `MM_PT_cockpit.draw()` currently ends after the Structural Framing Engine box (line ~348 as of this writing) — new GP-related UI goes after that, in the same `draw()` method.
- `register()`/`unregister()` currently only register `MM_PT_cockpit`. **Any new Operator classes you add must follow the same unregister-then-register pattern** already used for the panel (see "Traps already hit" below) — do not copy the old buggy `if name not in dir(bpy.types): register()` guard.
- Module-level state you'll be reading/mutating: `SKETCH_WEIGHTS` (nx×nz nested list of floats, 0..1) and `HARDSCAPE_MASK` (nx×nz nested list of bool), both loaded at import time from `outputs/cockpit/sketch_weights_cache.json`. Baking GP strokes should overwrite these two module-level globals (via `global SKETCH_WEIGHTS, HARDSCAPE_MASK` inside the bake function) and then call `rebuild_all(scene)`.

## Where this got blocked

Mid-implementation, discovered that **this Blender version is 5.0.1**, which uses the newer **Grease Pencil v3 data model** — most GP code examples/docs online (and my first attempt) assume the older API and will silently fail. Confirmed via live introspection against the running session:

- `bpy.data.grease_pencils.new(name)` still works the same (creates a `GreasePencil` data-block).
- `gp_data.layers.new(name)` still works; `layer.frames.new(frame_number)` still works and returns a `GreasePencilFrame`.
- **`frame.strokes` does NOT exist** on `GreasePencilFrame` in this version — raises `AttributeError: 'GreasePencilFrame' object has no attribute 'strokes'`.
- The correct path is **`frame.drawing.strokes`** — `frame.drawing` attribute was confirmed to exist via `dir(frame)` → `['bl_rna', 'drawing', 'frame_number', 'keyframe_type', 'rna_type', 'select']`.
- **Not yet verified**: the exact call chain for creating a stroke and adding points under this model (i.e. whether `frame.drawing.strokes.new()` + `stroke.points.add(n)` + `stroke.points[i].co = (...)` still works as in GPv2, or whether the `GreasePencilDrawing`/`GreasePencilStroke`/`GreasePencilStrokePoint` types changed shape too). **Test this live first** before writing the real implementation — same pattern as the isolated API-test snippet below, extended one level further into `frame.drawing.strokes.new()`.

Quick way to re-verify Blender version and re-run the isolated API probe if anything seems off:
```python
import bpy
print(bpy.app.version)  # was (5, 0, 1) this session
gp_data = bpy.data.grease_pencils.new("mm_gp_apitest3")
gp_obj = bpy.data.objects.new("mm_gp_apitest3", gp_data)
bpy.context.collection.objects.link(gp_obj)
layer = gp_data.layers.new("TestLayer")
frame = layer.frames.new(1)
print("frame.drawing:", frame.drawing, type(frame.drawing))
print("drawing attrs:", [a for a in dir(frame.drawing) if not a.startswith("_")])
# then try frame.drawing.strokes.new() and inspect what it returns before
# assuming the old .points.add(n) / .points[i].co = (...) pattern still applies
bpy.data.objects.remove(gp_obj, do_unlink=True)
```

## The intended design (not yet built)

1. **A dedicated flat ground plane** (`mm_sketch_ground`, a simple quad mesh sized to the site footprint + margin, at z=0), used purely as a Grease Pencil "Surface" stroke-placement target. Reason: the real terrace mesh's top surface is irregular (stepped voxel boxes), so projecting GP strokes onto it directly would put stroke points at inconsistent Z heights depending on where the user clicks. Since the bake only cares about (x, y) — not z — projecting onto a guaranteed-flat, guaranteed-full-coverage plane instead avoids that irregularity and guarantees strokes always land somewhere valid regardless of where within the site the user draws. Set `bpy.context.scene.tool_settings.gpencil_stroke_placement_view3d = 'SURFACE'`.

2. **One GP object (`mm_sketch_gp`), two layers**: `"Canyon"` (black material, additive weight — same semantics as file-based sketch_weight) and `"Hardscape"` (blue material, hard veto — same semantics as the existing hardscape toggle). Use **which layer a stroke belongs to** to decide canyon-vs-hardscape when baking — don't rely on material index, it's simpler and more robust to just read `layer.frames[0].drawing.strokes` per named layer.

3. **Apply the same Y-mirror transform** to `mm_sketch_gp` (and `mm_sketch_ground`) that `setup_axo_view()` already applies to the terrace/columns/tunnel/etc. objects, so strokes drawn on-screen visually line up with what's displayed in the mirrored axo view. The mirror is self-inverse: `mirror = Matrix(((1,0,0,0),(0,-1,0,L),(0,0,1,0),(0,0,0,1)))` where `L = REAL_GEOMETRY["site"]["length_ft"]`. To convert a stroke point's **world-space** coordinate back to real site feet for baking: `real_x = world_x` (mirror doesn't touch x), `real_y = L - world_y` (undoing the mirror — same formula either direction since it's self-inverse).

4. **Bake function** (`bake_sketch_gp(scene)`): for each of the two layers, collect stroke points as world-space polylines, convert to real (x, y) via the mirror-undo above, then for every grid cell `(gx, gy)` in the `SKETCH_WEIGHTS`/`HARDSCAPE_MASK` grids (cell center at `((gx+0.5)*voxel_ft, (gy+0.5)*voxel_ft)`), compute the minimum distance from that cell center to the nearest point on any Canyon-layer polyline and any Hardscape-layer polyline (standard point-to-segment distance, clamped projection onto each segment). Within a brush-radius constant (e.g. 12ft, tune by feel), set `SKETCH_WEIGHTS[gx][gy] = max(existing, 1.0 - dist/radius)` for Canyon hits, and `HARDSCAPE_MASK[gx][gy] = True` for Hardscape hits. Then call `rebuild_all(scene)`. `voxel_ft` comes from a `TerracingEngine(REAL_GEOMETRY).voxel_ft` instance (cheap to construct just for the constant, or read it off the already-built terrace object's engine if you thread it through).

5. **Two small Operators + panel buttons**: one to set the active GP layer and enter Draw mode (`bpy.ops.object.mode_set(mode='PAINT_GPENCIL')` after making `mm_sketch_gp` the active/selected object — two buttons, "Draw Canyon" / "Draw Hardscape", each setting `gp_data.layers.active` to the right layer first), and one "Bake Sketch" button calling `bake_sketch_gp(context.scene)`. Remember to register both operator classes using the same unregister-then-register-safe pattern as the panel.

6. **One-time setup call** at the bottom of the file (alongside the existing `register(); import_static_context(); rebuild_all(...); setup_axo_view(...)` sequence): a `setup_sketch_gp()` function that creates the ground plane + GP object + two layers + two materials, idempotently (check `bpy.data.objects.get("mm_sketch_gp") is not None` and skip if already present, same pattern `import_static_context()` already uses).

## Traps already hit this session (don't repeat)

- **Registration guard bug**: an earlier version of `register()` had `if "MM_PT_cockpit" not in dir(bpy.types): register_class(...)`. Once anything is registered once in a long-lived Blender session, that guard means *every later script reload silently skips re-registering it* — so a stale, outdated class stays active no matter how many times you reload the file, while Scene properties (which have no such guard) update fine, making it look like only the properties changed. Root-caused by directly inspecting the live registered class's bytecode constants via `execute_blender_code`, not by guessing. **Always unregister a class (if already present) before re-registering it, for every class you add.**
- **Blender's Python session persists across separate `execute_blender_code` calls, but each call gets a fresh exec namespace.** `sys.modules` (the imported-module cache) DOES persist though, so picking up edits to `terracing_engine.py`/`amenity_deficit.py`/`sketch_weight_mapper.py`/`blender_cockpit.py` itself requires clearing them from `sys.modules` before re-running:
  ```python
  import sys
  for mod in ["terracing_engine", "sketch_weight_mapper", "amenity_deficit"]:
      if mod in sys.modules:
          del sys.modules[mod]
  exec(open(r"D:\MemoryMachine\blender_cockpit.py").read())
  ```
- **Verify Blender API assumptions live before trusting them** — this exact GPv3-vs-v2 surprise is the second time an assumed API shape turned out wrong (`rs.doc` vs `scriptcontext.doc` in Rhino was the first, earlier in the project). Use `dir(obj)`, `inspect.getsource`, or bytecode-constant inspection against the real running session rather than writing a full implementation on assumption.

## Repo-organization note (unrelated to this task, just context)

Root was reorganized this session — many loose one-off scripts moved into new `blender/`, `rhino/`, `harvest/` subfolders. **None of that touched this task's files**: `blender_cockpit.py`, `terracing_engine.py`, `amenity_deficit.py`, `sketch_weight_mapper.py`, `precompute_sketch_cache.py` all still live at repo root, untouched, since they bare-import each other and moving them would need real import-path surgery, not a plain move.
