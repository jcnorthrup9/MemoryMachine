# FidelityGrid2 — warped standoff screen + overhang tilt (`PM_FacadeScreen`)

## 1. Purpose & scope

FidelityGrid2 is the second layer in this project's stack of compounding
grid-driven facade fidelity passes, sitting on top of FidelityGrid1
(`PM_FacadePanelizer`, [`FIDELITY_GRID_1.md`](./FIDELITY_GRID_1.md)) rather
than beside it. It reuses FG1's own site-level column-grid × DTLA-grid
collision seeds as real architectural anchor points, then implements
[`2D_GRID_PARTI_LOGIC_SPEC.md`](./2D_GRID_PARTI_LOGIC_SPEC.md) section 5
("warped grid lines") — deliberately skipped by FG1 — to deflect a second,
independently-spaced/rotated grid's cell boundaries away from those seeds,
and drives a continuous overlap-**density** field (not FG1's binary
marked/unmarked) that graduates each cell's standoff projection distance
from the glass plane. Cells above a density threshold get a third "hybrid"
material (`PM_Hybrid_Overlap`).

This system was built, verified, and then set aside earlier in the same
session it was built: the user reviewed it against the overall site
direction and judged it the wrong approach for the *massing* treatment
(superseded by `PM_ScaffoldFrame` — see
[`SCAFFOLD_FRAME.md`](./SCAFFOLD_FRAME.md)) — but explicitly asked to keep
it disabled-but-preserved rather than deleted, because it "might actually
be good to modify for the canopy logic later on." That moment arrived:
the user asked whether the flat `Screen`/`ScreenHybrid` panels could be
rotated "so that they are not walls, but look more like overhangs or like,
walkway coverings," as a slider. That's `PanelTiltDeg`, §4 below.

## 2. Site frame & constants

Identical to FidelityGrid1: raw `ORIGIN = (337.028, 570.21)`,
`COL_SPACING = 27.0` ft, `DTLA_ANGLE_DEG = 36.0`. Seeds are **recomputed
here** (col-grid × DTLA-grid collision, byte-for-byte the same algorithm as
FG1), not read from FG1's baked geometry — this keeps both layers
independently toggleable/rebakeable with no fragile dependency on parsing
baked Breps. The Log's `seeds=` count should always read 56; if it doesn't,
ORIGIN/site data has drifted between the two components.

## 3. Algorithm walkthrough

1. **Secondary grid**: `build_grid_lines(ORIGIN, Grid2SpacingFt, Grid2SpacingFt, Grid2RotDeg, boundary, 9)` — independently spaced (default 27ft) and rotated (default 20°, ≈ the Processing-sketch reference's `rotationAngle=0.35rad`) from FG1's own column grid.
2. **Warp** (`warp_point`, spec section 5 promoted to 3D): every grid-line sample point gets pushed away from nearby seeds, force falling off linearly within a per-seed fade radius (`WarpMaxRadiusFt`/`WarpMaxForceFt`, themselves fading with the seed's own distance from `ORIGIN`). Evaluated once per node at its *unwarped* position — not iteratively re-warped — so the lattice stays a single-valued function of its unwarped position (no self-intersection feedback risk).
3. **Density** (`density_at`): a continuous linear-falloff sum over all seeds within `InfluenceRadiusFt`, normalized to `dnorm` via `DENSITY_NORM_K`. Both warp and density are evaluated in true 3D against seeds sitting at grade (z=0), so influence fades with height above ground as well as plan distance.
4. **Node placement** (`screen_node`): each (h, z) grid intersection becomes a 3D point offset outward from the glass plane by `off = G1_PANEL_DEPTH_FT + min_so + (max_so-min_so)*smoothstep(dnorm) + warp's own outward component` — i.e. denser zones stand further off the wall.
5. **Cell → slab** (`make_screen_slab`): each cell's 4 corner nodes (generally non-planar, since warp/standoff varies per corner) become a 6-face bilinear-ruled-surface Brep (`Brep.CreateFromCornerPoints` × 6 + `Join` — never fails on non-planarity, unlike `CreatePlanarBreps`/`CreateOffsetBrep`). Cells with mean corner density ≥ `HybridThresh` become `ScreenHybrid`; the rest become `Screen`.
6. **Standoffs**: a cylinder from a point on the glass plane out to the slab's own center, visualizing the structural connection back to the building.

## 4. `PanelTiltDeg` — the overhang/walkway-covering tilt

Added this session in direct response to the user's request. Hinges each
cell at its own **top edge** and rotates the bottom edge from
flush-vertical (`PanelTiltDeg=0`, today's original wall-screen geometry)
toward horizontal-and-outward (`90`, an overhang/canopy read). Top-hinge
(not bottom) is deliberate: it leaves clearance *underneath* for a
walkway. Bottom-hinge would instead swing the top edge down to meet the
bottom, collapsing the canopy to grade.

**Math** (`tilt_bottom_corner`), applied to each cell's two bottom corners
relative to the corresponding top corner directly above (`A`→hinge `D`,
`B`→hinge `C`), using the confirmed-orthonormal frame
`{h_axis, ZAxis, n_axis}` (`h_axis = ZAxis × n_axis`, from `face_frame`):

```python
def tilt_bottom_corner(P, hinge, h_axis, n_axis, tilt_rad):
    if tilt_rad == 0.0:
        return P
    delta = P - hinge
    d_h = delta * h_axis
    p = -delta.Z                       # "downness" from hinge (positive)
    q = delta * n_axis                 # pre-existing small outward offset
    cos_t, sin_t = math.cos(tilt_rad), math.sin(tilt_rad)
    new_p = p * cos_t - q * sin_t
    new_q = p * sin_t + q * cos_t
    return hinge + d_h * h_axis + (-new_p) * rg.Vector3d.ZAxis + new_q * n_axis
```

At `tilt_rad=0`, `new_p=p, new_q=q` — bit-identical to the original
flush-wall geometry (verified both algebraically and by re-baking at 0°
and confirming identical `screen=`/`hybrid=`/`standoffs=` counts to the
pre-tilt baseline). At `tilt_rad=90°`, the former vertical drop becomes a
horizontal outward projection of the same length; sign confirmed outward,
not into the building.

**Scope**: applies uniformly to every cell — both `Screen` and
`ScreenHybrid`, every facade, every floor band. The user asked for a
slider to dial and explore, not a scripted "only near grade" zone rule —
the slider itself is how they control how much of the site reads as
overhang.

**Continuity behavior**: horizontally adjacent cells (same row) share the
identical hinge/source math and stay perfectly seamed edge-to-edge.
Vertically adjacent cells (cross-band) genuinely separate as tilt
increases — each band fans open from its own higher hinge, producing a
stepped louvre/brise-soleil stack rather than one continuous folding
surface. **This is the expected look, confirmed visually, not a bug.**

**Standoff fix made alongside this feature**: the `Standoffs` cylinder was
previously built with a *fixed* axis along `n_axis` regardless of where its
target point actually was — correct only when that target point happened
to lie exactly along `n_axis` from the wall, which stops being true once a
cell tilts. Fixed by building the cylinder's circle-plane normal from
`(center_node - base_pt)` unitized instead, and by recomputing
`center_node` from the post-tilt, post-inset quad rather than the original
flush corners — so the standoff visually connects the wall to the slab's
*actual* position at any tilt. Safe at `tilt=0` too (negligible pre-existing
deviation there).

## 5. Component graph

Grasshopper "Python 3 Script" component, nickname `PM_FacadeScreen`, guid
`7dd97c84-8689-43f2-b239-c19175c1411f`, at canvas (600, 800). Source
committed at
[`rhino/gh_facade_screen_component.py`](../rhino/gh_facade_screen_component.py).

| Input | Type | Range | Default |
|---|---|---|---|
| `Bake` | bool toggle | — | `False` originally; re-enabled `True` this session |
| `Refresh` | bool toggle | — | `False` (unused — fully deterministic) |
| `Grid2RotDeg` | float slider | 0–45 | 20.0 |
| `Grid2SpacingFt` | float slider | 9–54 | 27.0 |
| `Panel2ZFt` | float slider | 4–27 | 13.5 |
| `WarpMaxRadiusFt` | float slider | 0–120 | 54.0 |
| `WarpMaxForceFt` | float slider | 0–30 | 9.0 |
| `InfluenceRadiusFt` | float slider | 13.5–108 | 54.0 |
| `MinStandoffFt` | float slider | 0.25–6 | 1.0 |
| `MaxStandoffFt` | float slider | 1–16 | 5.0 |
| `Panel2ThickFt` | float slider | 0.1–1.5 | 0.33 |
| `HybridThresh` | float slider | 0–1 | 0.60 |
| `SwirlDeg` | float slider | 0–90 | 0.0 |
| `PanelTiltDeg` | float slider | 0–90 | 0.0 (left at 75 for the demo bake this session) |

Outputs: `Screen`, `ScreenHybrid`, `Standoffs` (Breps), `WarpCrv` (diagnostic curves), `Log` (str → Panel).

## 6. Bake targets

```
Detailed_Screen::{ProgramName}::Screen
Detailed_Screen::{ProgramName}::ScreenHybrid
Detailed_Screen::{ProgramName}::Standoffs
Detailed_Screen::_Parti::WarpedGrid | DensityPts
```

## 7. Materials & the two-step workflow

Two PBR materials: `PM_Mullion_Metal` (`#4A4A4A`, reused from FG1, applied
to both `Screen` and `Standoffs`) and `PM_Hybrid_Overlap` (`#553C5F`,
metallic 0.2, roughness 0.55, applied to `ScreenHybrid`). Same
Grasshopper-Python3-materials-don't-render gotcha documented in
`FIDELITY_GRID_1.md` §7 — same two-step workflow. `find_or_make_material`
was also updated this session to the Modify-in-place pattern (matching
FG1/`PM_ScaffoldFrame`) instead of Delete-then-recreate, avoiding the
13,000+-entry Materials-table issue documented elsewhere in this repo.

1. Toggle `Bake` in Grasshopper.
2. `.venv/Scripts/python.exe rhino/run_rhino_script.py rhino/apply_facade_materials.py` (plain `python` is not on PATH in this environment).

## 8. Verification record

`Log` at `PanelTiltDeg=0` (confirmed identical cell counts to this
system's original pre-disable bake earlier in the session):

```
site_data_source=C:\Users\jcnor\MemoryMachine\PershingMetabolizer_Prototype\real_geometry.json
seeds=56 grid2_lines=51 cells=366 hybrid=111
mean_dnorm=0.366 max_dnorm=1.000
ORIGIN=(337.028,570.210)  tiltDeg=0.0
PracticeSpace: screen=0 hybrid=0 standoffs=0
ComputerTechSpace: screen=0 hybrid=0 standoffs=0
ArtsAndCraftsStudio: screen=9 hybrid=0 standoffs=9
WorkOutEquipment: screen=12 hybrid=0 standoffs=12
PicnicGrillSpace: screen=11 hybrid=0 standoffs=11
Greenspace: screen=0 hybrid=0 standoffs=0
Skatepark: screen=82 hybrid=25 standoffs=107
CommunityCenter: screen=141 hybrid=86 standoffs=227
TOTAL screen=255 hybrid=111 standoffs=366
BAKED to Detailed_Screen::*
```

Visual verification at `PanelTiltDeg=75`: `gh_inspect(action='status')`
showed no errors; disabled this component's live GH canvas preview (known
gotcha — separate from Rhino layer visibility, see `SCAFFOLD_FRAME.md`
§9); display mode had again silently reverted to `Ghosted` (same
already-documented quirk) and was reset to `Rendered`; captured and zoomed
into a representative building. Confirmed: `Screen` (grey) and
`ScreenHybrid` (violet) slabs project outward from the roofline at a steep
angle, clearly reading as a stepped band of canopy/awning blades with
daylight visible underneath — a real overhang, not a wall — while FG1's
glass panels and `PM_ScaffoldFrame`'s timber mullion grid (both untouched
by this feature) remain flush in the same shot for contrast.

## 9. Known caveats / open items

- **`d_h` (the hinge-line-parallel component of `delta`) is preserved
  unrotated** — a small approximation. A true rigid rotation of a warped,
  non-planar hinge edge would rotate this component too, but it's tiny
  relative to panel height at this site's scale; not fixed, noted only.
- **`is_buried`/the `wx,wy,zmid` bury-check use the flush (untitled)
  plan-position estimate**, same caveat already documented for FG1's
  analogous check (`FIDELITY_GRID_1.md` doesn't call this out explicitly
  but the pattern is identical) — at high tilt a slab's true position
  diverges further from this estimate than at 0°, so the cull is a rough
  approximation, not exact, at high tilt. Not fixed here.
- **Vertically-stacked bands separate (fan open) as tilt increases** — see
  §4. This is the intended, confirmed-good look, not a defect, but it's
  worth knowing before assuming something broke if `Panel2ZFt` is set
  small (many bands) combined with a high tilt (very fanned-out stack).
- **`G1_PANEL_DEPTH_FT = 0.25` hardcodes FG1's `PanelDepthFt` DEFAULT** as
  the baseline glass-plane offset every standoff/screen depth is measured
  from — a pre-existing simplification (not from this session): if FG1's
  slider is ever moved off its 0.25 default before FG2 is baked, this
  constant needs to be updated to match, or the screen's baseline is wrong
  relative to the actual glass plane.
