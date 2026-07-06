Handoff: live 2D sketch-painting mechanism + typology mixing engine -- current status
========================================================================================
*2026-07-05, end of session. For Gemini to pick up from here. Blender is running with
BlenderMCP connected (`mcp__blender__execute_blender_code`, `get_viewport_screenshot`,
`get_scene_info` etc.) against the live cockpit session -- USE THESE to test against the
real running Blender instance rather than guessing at API behavior. This session hit
several real API surprises that only showed up by testing live (see "Traps hit" below);
don't skip that step.

## Where this fits in the project

Memory Machine / Pershing Metabolizer: a real subterranean-canyon excavation-planning
tool. `terracing_engine.py` (pure Python, no bpy, no numpy even) owns the actual
excavation-depth math (`TerracingEngine`) and structural framing/salvage math
(`StructuralFramingEngine`), driven by real site data (`real_geometry.json`) plus
designer input. `blender_cockpit.py` imports both directly into Blender's own bundled
Python and is the live "cockpit" -- sliders/buttons that rerun the engine and rebuild
the 3D terrace mesh in-viewport on every change (`rebuild_all(scene)`, the one and only
rebuild entrypoint -- everything funnels through it).

## What happened this session, in order

1. Picked up a paused "Grease Pencil painting interface" task (see
   `HANDOFF_07052026_GREASE_PENCIL_INTERFACE.md`) -- built it, verified GPv3's actual
   stroke-creation API live (it differs from GPv2 examples online), wired up Draw
   Canyon / Draw Hardscape / Bake Sketch buttons drawing on an invisible 3D-viewport
   plane.
2. **User flagged a misunderstanding**: they wanted to paint semi-opaque color washes
   directly onto the *uploaded 2D hand-drawn sketch image*, not draw abstract lines in
   the 3D viewport. Also wanted more categories than just Canyon/Hardscape.
3. Clarified via conversation: canvas = the 2D sketch image; new categories =
   Water/Shade, Greenscape, Amenity/Resting (this last one is a NEW zone-paint category,
   explicitly NOT the same thing as the pre-existing point-dab "Amenities" CSV pipeline
   -- see "Two different 'Amenity' things" below, this naming collision is a real trap).
4. User then dropped a fully-specified design doc excerpt ("## 4. Programmatic
   Typology Mixing Engine") describing composite voxel states (GROTTO, SANCTUARY) from
   overlapping zone types, with real asset-instancing rules and a "Vertical
   Disbursement Rule". Implemented this in `terracing_engine.py` -- see below.
5. User then asked "can greenscape be painted into canyon, can categories bleed into
   one another, what happens when they meet" -- a real open design question. Wrote
   `HANDOFF_07052026_ZONE_OVERLAP_SEMANTICS.md` (still unresolved, see below) since the
   user wanted outside input (yours) on hard-veto-vs-soft-compromise semantics before
   committing further.
6. User said "let's go for the painting mechanism" -- built the real 2D image-painting
   interface (replacing the GP interface entirely, per explicit user choice), verified
   end-to-end live.

## Current state of the code -- read this before touching anything

### `terracing_engine.py`

- `Voxel` dataclass gained `is_water_shade`, `is_greenscape`, `is_amenity_resting`
  (bool, default False) and `typology` (str, default None).
- `TerracingEngine.__init__` gained `water_shade_regions=None`, `greenscape_regions=None`,
  `amenity_resting_regions=None` -- same `[{"mask": (nx,nz) bool grid}, ...]` OR-list
  shape as the existing `hardscape_regions`. These NEVER appear in `_z_for_voxel` (the
  real depth-excavation function) -- they only feed a new post-process classification
  step, `_classify_typology(v)`:
  ```python
  def _classify_typology(self, v):
      if v.z_ft < 0 and v.is_water_shade:
          return "GROTTO"
      if v.is_greenscape and v.is_amenity_resting:
          return "SANCTUARY"
      return None
  ```
  Called from `run()`, phase 3 only, after `_relax_depths` -- i.e. GROTTO requires the
  voxel to have ACTUALLY excavated (real depth < 0), not just be painted Water/Shade.
  This was a confirmed user decision (asked directly, "excavated result" was chosen over
  "painted mark regardless of depth").
- New `TypologyAssetEngine` class (same file, after `StructuralFramingEngine`): walks
  the already-classified voxel field and emits `StructuralElement` specs (same dataclass
  the structural engine already uses, so no new instancing plumbing needed) --
  `grotto_specs()` (water_plane always; water_cascade_block + column-adjacent
  misting_line only at `level <= -2`, deduped per real column) and `sanctuary_specs()`
  (bench_assembly always; restroom_pod only if `level >= -1 and transit_influence > 0.5`;
  fountain only if `level <= -2`) -- this is the "Vertical Disbursement Rule" from the
  user's spec, implemented as conditional additions, not exclusive alternatives.
  **Important finding**: under the real site's default depth cap
  (`max_canyon_depth_ft` = `column_height_ft` = 30ft), excavation only ever reaches
  level 0 or -1 -- level -2 (needed for the "deep" branch: cascade blocks, misting,
  fountains) genuinely does not occur without a designer painting Canyon strongly
  enough, near-transit, to push a cell past 20ft depth. Verified via a level histogram
  on the real site (`{0: 2557, -1: 123}`, zero cells at -2 under defaults). Not a bug --
  just means the deep-branch assets won't show up until someone paints hard enough.

### `blender_cockpit.py` -- the paint mechanism (GP interface is GONE, fully removed)

- `PAINT_CATEGORIES` (module-level tuple): `(key, label, tint_rgb, continuous)` for
  Canyon (continuous=True, painted alpha IS the weight, no falloff math needed -- the
  brush's own soft edge gives the falloff for free), Hardscape/Water-Shade/Greenscape/
  Amenity-Resting (continuous=False, thresholded at `PAINT_ZONE_THRESHOLD = 0.3` into a
  boolean zone mask).
- `setup_paint_canvas()`: one-time (idempotent) creation of `mm_paint_canvas`, a flat
  plane at real site-feet `(0,0)-(W,L)` displaying the real sketch photo
  (`data/sketches/b84c0d16-....jpg`, found via `sketch_weight_mapper.find_latest_sketch()`)
  as a background texture, PLUS 5 paintable Image datablocks (one per category,
  `mm_paint_<key>`, `bpy.data.images.new(..., alpha=True)`, resolution
  `PAINT_GRID_NX*8 x PAINT_GRID_NZ*8` = 320x536 px for the current real site). A shader
  node graph (`ShaderNodeUVMap` -> sketch `ShaderNodeTexImage` -> chain of 5
  `ShaderNodeMixRGB`, each mask's Alpha output driving Fac, Color2 = that category's
  tint -> `ShaderNodeEmission` -> output) composites all 5 masks live over the sketch,
  so painting shows as real semi-opaque color washes -- verified visually via
  screenshot, confirmed the live viewport updates as pixels change.
- **UV registration is the trickiest part -- read this before changing it.** The
  canvas plane's four corners get explicit UVs: `real(0,0)->uv(1,0)`,
  `real(W,0)->uv(0,0)`, `real(W,L)->uv(0,1)`, `real(0,L)->uv(1,1)`. This was NOT
  guessed -- it was derived to exactly match `sketch_weight_mapper.py`'s
  `load_image_sketch`'s already-calibrated `flip_x=True, flip_y=True` convention
  (`real_x=(1-fx)*W`, `real_y=(1-fy)*L`, where fx/fy are PIL-style top-down pixel
  fractions), AFTER empirically confirming (via a marker-colored 2x2 test image +
  screenshot, since this was NOT obvious from documentation) that **Blender's
  `image.pixels` flat array is bottom-up row-major** (row 0 = bottom of the displayed
  image, matching UV's V=0), the OPPOSITE of PIL's top-down convention. Do not change
  this UV assignment without re-deriving through that same empirical check --
  getting it wrong wouldn't crash anything, it would just silently mis-register
  painted marks against the real site (e.g. paint near the sketch's "entrance" label
  and have it land on the wrong real-world corner).
- `_sample_mask_grid(img, continuous)`: inverts that exact UV mapping to sample each
  mask image's alpha into an `(nx, nz)` grid matching `TerracingEngine`'s own cell
  indexing. `pixel col = (1 - real_x/W) * w`, `pixel row = (real_y/L) * h` (Blender's
  own bottom-up row convention, no further inversion needed here since we're reading
  Blender's own `image.pixels`, not a PIL array).
- `_set_paint_view(active)`: toggles between the normal 3D axo view and the paint
  canvas's own dedicated top-down ortho camera (`mm_paint_cam`, unmirrored --
  deliberately NOT given the axo mirror the terrace/columns/etc. get, since it lives
  in its own straight top-down view) -- hides whichever set of objects would otherwise
  visually clash, since the canvas plane and the real terrace occupy the same
  real-feet footprint.
- `MM_OT_paint_category` (one parametrized operator, `category: StringProperty`, not 5
  separate classes) -- sets `tool_settings.image_paint.canvas` to that category's
  image, `mode='IMAGE'` (paints directly into the named image regardless of material
  node setup -- confirmed live this works with zero material dependency), sets the
  brush color to the category's tint, switches to the paint view, enters
  `TEXTURE_PAINT` mode on the canvas object.
- `bake_paint_canvas(scene)` / `MM_OT_bake_paint`: samples all 5 images, overwrites
  `SKETCH_WEIGHTS` / `HARDSCAPE_MASK` / `WATER_SHADE_MASK` / `GREENSCAPE_MASK` /
  `AMENITY_RESTING_MASK` (full replace, not merge -- baking again completely
  overwrites, it does not accumulate across bakes the way the old GP version's
  max()-based accumulation did), switches back to the 3D view, exits to Object mode,
  calls `rebuild_all(scene)`.
- Panel (`MM_PT_cockpit.draw`): "Live Sketch (Paint on Photo)" box with 5 "Paint
  <Category>" buttons + "Bake Painted Sketch". Falls back to a text label if no sketch
  image was found in `data/sketches/`.

## Traps hit this session (don't repeat)

- **GPv3 stroke API differs from GPv2** (now moot since GP was removed, but worth
  remembering for any future GP work): `frame.drawing.strokes` has no `.new()` --
  strokes are created via `drawing.add_strokes(sizes=[n_points, ...])`, and paint mode
  is `PAINT_GREASE_PENCIL` not `PAINT_GPENCIL` (renamed in Blender 5.0).
- **`bpy.data.images.new()` defaults to opaque black** (alpha=1.0 on all pixels), not
  transparent -- had to explicitly zero the alpha channel after creation for a "nothing
  painted yet" default.
- **Blender's `image.pixels` row order is bottom-up**, opposite of PIL -- confirmed via
  a real empirical test (marker-colored 2x2 image + screenshot), not assumed. This
  cancelled out cleanly against `sketch_weight_mapper.py`'s own flip convention, but
  would have been very easy to get backwards without testing.
- **The 3D viewport has an independent `region_3d.view_camera_zoom`/`view_camera_offset`**
  that persists across camera changes and silently overrides `ortho_scale` framing --
  spent real time debugging an apparently-broken camera setup that was actually just a
  leftover zoom offset from earlier navigation. Reset both to 0 whenever camera framing
  looks wrong before assuming the camera math itself is broken.
- **Placing test geometry at the scene's real origin risks silent occlusion** by the
  actual (huge, ~354x602ft) site geometry already there -- an orientation-verification
  test plane appeared to render as nothing until moved to an offset far away
  (`+5000,+5000,+5000`) from the real scene.
- **Leftover viewport shading mode from an earlier test silently breaks later
  screenshots** -- `shading.type = 'RENDERED'` (set during the orientation test) made
  the real terrace geometry look like a near-invisible dark outline in a later,
  unrelated screenshot; switching to `'SOLID'` (or `'MATERIAL'` when texture visibility
  is actually needed, e.g. while painting) fixed it. If a screenshot looks
  inexplicably empty/wrong, check `shading.type` before assuming the scene data itself
  is broken.

## Two different "Amenity" things -- do not conflate these

1. **`amenity_deficit.py`'s point-dab Amenities** (pre-existing, unrelated to this
   session's paint work): a CSV of `{x_frac, y_frac, strength, radius_ft}` points,
   feeds `deficit_hotspots` -> `deficit_influence` on each voxel. Confirmed this
   session to explicitly stay **diagnostic-only** -- `deficit_influence` does NOT
   currently affect real excavation depth (`_z_for_voxel` never reads it), only a
   separate `score` field. User explicitly decided NOT to change this as part of this
   work.
2. **The new "Amenity/Resting" paint category** (this session, `PAINT_CATEGORIES`):
   an area/zone paint mask, boolean, used ONLY for `TypologyAssetEngine`'s SANCTUARY
   classification (combined with Greenscape). Has nothing to do with `deficit_hotspots`.

These are two completely separate mechanisms that happen to share the word "Amenity."
Don't merge them or assume painting "Amenity/Resting" affects the CSV-driven deficit
pipeline -- it doesn't, by design.

## Still open / unresolved -- genuinely needs a decision, not guessing

1. **`HANDOFF_07052026_ZONE_OVERLAP_SEMANTICS.md` is still live and unanswered.** The
   user explicitly asked for outside input (originally framed as "talk to Gemini")
   on: when painted zone types overlap (e.g. Canyon painted across Greenscape), should
   resolution be a hard veto (matches Hardscape's existing shipped precedence -- veto
   always wins, no partial compromise) or a soft continuous dampening (Greenscape would
   need to become a continuous weight like Canyon, not a boolean mask -- bigger
   structural change)? Read that file in full before deciding; it has the real
   `_z_for_voxel` precedence code and the exact options already scoped.
2. **Canyon directionality** (raised, never resolved): today's math is symmetric
   distance/weight around wherever painted, no "one side only" concept. User asked how
   to control which side of a canyon mark the excavation "starts from" -- no concrete
   example was given yet to design against. If this comes up again, ask for one
   concrete example before designing a mechanism (see the zone-overlap handoff's
   framing of this same open question).
3. **`PAINT_ZONE_THRESHOLD = 0.3` and `PAINT_PX_PER_CELL = 8`** are reasonable-guess
   defaults, not tuned against real designer painting -- only verified via direct
   `img.pixels` array writes simulating a stroke (a filled circle with a radial alpha
   falloff), never an actual human mouse-drag. Brush defaults (size/strength/brush
   type) are whatever Blender's stock defaults are -- not customized, not verified for
   real painting feel.
4. **No real interactive painting has been tested** -- everything above was verified
   by writing directly into `image.pixels` arrays via code, not by an actual mouse
   drag in the viewport. The mechanism (paint canvas, mode switching, bake sampling)
   is proven correct end-to-end for how Blender's Image Paint system works, but the
   actual UX of painting with a real brush/tablet/mouse has not been exercised. If
   something feels off once a real person paints (brush too small/large, canvas
   framing awkward, etc.), that's the first place to look -- not the underlying
   mechanism.
5. **Concurrent editing**: another process was independently evolving the Structural
   Framing Engine (STEEL/WOOD box-cylinder-hex instancing system) in both files during
   this session -- re-read current file state before trusting exact line numbers here;
   things may have moved again.

## Quick re-verification snippet

Same reload pattern used throughout this session (module cache doesn't auto-clear
across `execute_blender_code` calls):
```python
import sys
for mod in ["terracing_engine", "sketch_weight_mapper", "amenity_deficit"]:
    if mod in sys.modules:
        del sys.modules[mod]
exec(open(r"D:\MemoryMachine\blender_cockpit.py").read())
```
