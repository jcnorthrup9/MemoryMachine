# ScaffoldFrame — 3D mullion-grid buildup (`PM_ScaffoldFrame`)

## 1. Purpose & scope

ScaffoldFrame replaces `PM_GrowthScaffold` (the agent-based voxel-growth
system — see [`GROWTH_SCAFFOLD.md`](./GROWTH_SCAFFOLD.md), now disabled and
preserved) after direct user feedback that it wasn't the right approach.
Verbatim: *"the growth should be contained within the footprint of the
buildings. they also don't need to be voxelized growths that go out at an
angle like that. they should be made of straight components, orthogonal
vertical and horizontal pieces. maybe the mullion and fenestration script
that you made first was closer to that logic."*

So this is not a new simulation — it is a direct **3D extension of
FidelityGrid1's own proven logic** (`PM_FacadePanelizer`,
[`FIDELITY_GRID_1.md`](./FIDELITY_GRID_1.md)): the same site data, the same
column-grid × DTLA-grid collision field, the same per-building facade
detection, reused near-verbatim. There is no agent, no voxel-collision set,
no diagonal-reading zigzag. Every member is a single straight `Box`
oriented to either a facade's own horizontal axis or world Z, built with
FidelityGrid1's own box-primitive idiom. Because every face is processed
one building at a time, from that building's own Brep only, structure can
never leave that building's footprint or bridge to another mass — there is
no site-wide pooled target set of any kind.

**Outcome:** every `Program::*` building gets a real orthogonal timber
frame (posts + rails) tracing its own real column grid and floor lines,
with extra structural density automatically appearing in the same
"marked" bays FidelityGrid1 already treats as structurally significant —
reading as a scaffold that has genuinely built up out of that one
building's own massing.

## 2. What "growth" means here

Two layers, both always straight, both always confined to one facade:

1. **Baseline frame** — every facade always gets FG1's own mullion grid:
   one vertical post at every real column-grid crossing
   (`facade_h_joints`), one horizontal rail at every real floor line
   (`FloorFt` spacing). This alone is a plain orthogonal skeleton on every
   building, everywhere — the "mullion and fenestration" reference point.
2. **Growth layer** — bays (the h-interval between two consecutive
   column-grid verticals) whose plan-footprint falls inside one of FG1's
   own **marked cells** (the same column × DTLA grid collision field that
   already drives FG1's dense panel subdivision, already validated and
   accepted by the user) get an extra, denser sub-grid of posts and rails
   within that one bay only — `SubDiv` extra verticals across the bay's own
   width, `SubDiv` extra rails within each floor band. Unmarked bays stay
   the plain baseline frame.

This reuses the exact "interesting zone" definition FG1 already
established, rather than inventing a new attractor/height-tier concept —
the direct answer to "closer to that logic."

## 3. Site frame & constants

Identical to FidelityGrid1, on purpose: raw (non-phase-corrected)
`ORIGIN = (337.028, 570.21)`, `COL_SPACING = 27.0` ft,
`DTLA_ANGLE_DEG = 36.0`. This component deliberately does **not** use
GrowthScaffold's phase-corrected `GROWTH_ORIGIN` — its vertical member
positions come from the same `facade_h_joints()` FG1's mullions already
use, in the same raw-ORIGIN frame FG1 was already verified and accepted
in. Two components drawing lines on the same facades in two different
ORIGIN conventions would visibly disagree with each other for no benefit.

## 4. Algorithm walkthrough

Per building, per facade face (`facade_faces` → `face_frame` → identical to
FG1):

1. `h_joints = facade_h_joints(...)` — real column-grid crossings.
2. `bands = z_bands(z0, z1, FloorFt)` → `z_lines` — real floor levels.
3. **Baseline** (unconditional, unculled — matches FG1's own `Mullions`
   output, which is likewise never buried-culled): one vertical `Box` per
   `h_joints` entry at full `z0..z1` height; one horizontal `Box` per
   `z_lines` entry spanning the full `h0..h1` width.
4. **Growth** (per bay, `is_buried`-culled — matches FG1's per-panel
   culling in `make_cell_boxes`): for each `h_joints[i], h_joints[i+1]`
   bay, evaluate `is_marked_world` once at the bay's plan midpoint
   (constant across the bay's full height, exactly like FG1's own check,
   which also never depends on z). If marked: `subdivide_interval` the
   bay's own h-range into `SubDiv` extra verticals (full `z0..z1` height),
   and `subdivide_interval` each floor band's own z-range into `SubDiv`
   extra rails (spanning just that bay's width).

Every member — baseline or growth — is one straight axis-aligned `Box`:
`facade_mullions()` for verticals (extent along world Z),
`facade_floor_mullions()` for horizontals (extent along the facade's own
in-plane horizontal axis). Never diagonal, never voxel-hopped.

## 5. Component graph

Grasshopper "Python 3 Script" component, nickname `PM_ScaffoldFrame`, guid
`335d5dd5-7c0a-41d9-a4e2-ce783ff1ea8b`, at canvas (600, 2550). Source
committed at
[`rhino/gh_scaffold_frame_component.py`](../rhino/gh_scaffold_frame_component.py).

| Input | Type | Range | Default |
|---|---|---|---|
| `Bake` | bool toggle | — | `True` |
| `Refresh` | bool toggle | — | `False` (unused — fully deterministic) |
| `SubDiv` | int slider | 2–8 | 3 |
| `FloorFt` | float slider | 6–27 | 13.5 |
| `MemberFt` | float slider | 0.25–2.0 | 0.75 (square cross-section — one fixed stock size, same "uniform dimensional lumber" reasoning as the old GrowthScaffold's `StickSizeFt`) |

Outputs: `Members` (Breps), `Log` (str → wired to a Panel).

## 6. Bake targets

```
Detailed_ScaffoldFrame::{ProgramName}::Members
```

`clear_previous_bake()` deletes every object under `Detailed_ScaffoldFrame`
(keeping the layer structure) before each bake — same pattern as every
other component in this stack.

## 7. Materials & the two-step workflow

One PBR material, `PM_Scaffold_Timber` (`#B07C4A`, roughness 0.75,
metallic 0.0) — carried over unchanged from GrowthScaffold, applied by
layer across all eight `{ProgramName}::Members` layers. Same
Grasshopper-Python3-materials-don't-render gotcha documented in
`FIDELITY_GRID_1.md` §7; same two-step workflow, and
`rhino/apply_facade_materials.py` was extended this session with a loop
over all eight `Detailed_ScaffoldFrame::{name}::Members` layers (alongside
its existing FG1/FG2/GrowthScaffold handling):

1. Toggle `Bake` in Grasshopper.
2. `python rhino/run_rhino_script.py rhino/apply_facade_materials.py`

## 8. Verification record

First successful run, `Log` output:

```
site_data_source=C:\Users\jcnor\MemoryMachine\PershingMetabolizer_Prototype\real_geometry.json
col_lines=36 dtla_lines=3 seeds=56 marked_cells=51
ORIGIN=(337.028,570.210)  site=354.22x602.53ft
sub=3 floorFt=13.5 memberFt=0.75
PracticeSpace: bays=0 marked_bays=0 base_members=0 grown_members=0 total=0
ComputerTechSpace: bays=0 marked_bays=0 base_members=0 grown_members=0 total=0
ArtsAndCraftsStudio: bays=8 marked_bays=0 base_members=20 grown_members=0 total=20
WorkOutEquipment: bays=12 marked_bays=0 base_members=24 grown_members=0 total=24
PicnicGrillSpace: bays=12 marked_bays=0 base_members=24 grown_members=0 total=24
Greenspace: bays=0 marked_bays=0 base_members=0 grown_members=0 total=0
Skatepark: bays=56 marked_bays=8 base_members=136 grown_members=96 total=232
CommunityCenter: bays=202 marked_bays=45 base_members=490 grown_members=360 total=850
TOTAL members=1150
BAKED to Detailed_ScaffoldFrame::*
```

Sanity check: `CommunityCenter marked_bays=45` matches FG1's own
`marked_facade_cells=45` for the same building exactly (see
`FIDELITY_GRID_1.md` §8) — confirming the growth layer is keying off the
identical marked-cell field FG1 already validated, not a new one.
`PracticeSpace`/`ComputerTechSpace` correctly produce zero members, same
below-grade reason as FG1 (§9).

Visual verification: disabled live canvas preview on `PM_ScaffoldFrame`
(GH preview, not Rhino layer visibility — see caveat below), hid the
disabled `Detailed_Scaffold` layer, restored `Program::*` massing
visibility, confirmed Rhino's display mode was actually `Rendered` (it had
silently reverted to `Ghosted`, which briefly looked like a materials bug
— translucent rainbow-colored blocks per layer — before being caught and
fixed), then captured and zoomed into a `CommunityCenter` bay. Confirmed: a
real straight orthogonal timber-colored (`#B07C4A`) post-and-rail frame
tracing that building's own roofline and column grid, with a visibly denser
cluster of extra rails in the marked bay — fully contained within the
building's own footprint, no diagonal members, no cross-building
connections.

## 9. Known caveats / open items

- **Display mode can silently revert.** Mid-session, the Perspective
  view's display mode changed from `Rendered` to `Ghosted` with no
  explicit action by either party (not reproduced/diagnosed further).
  Ghosted mode shows plain per-layer color with transparency, ignoring PBR
  materials entirely — which looked exactly like a materials-application
  failure (translucent multi-hue blocks) until `rhino_render(action=
  'display')` was queried directly and showed the real cause. Worth
  checking display mode directly before assuming a materials bug in any
  future session.
- **A newly added component's live GH preview is a separate switch from
  Rhino layer visibility**, confirmed again this session (see
  `GROWTH_SCAFFOLD.md` §9, first discovered there) — `PM_ScaffoldFrame`
  needed its own `gh_canvas(action='preview', enabled=false)` call after
  being added; this is now a standing step for any new bake-producing
  component in this document, not a one-off.
- **`Refresh` is unused**, same as every other component in this stack —
  the algorithm is fully deterministic (no RNG), so there is no state to
  reset. Wired for future use, harmless if left unwired.
- **`FidelityGrid2`'s baked `Detailed_Screen::*` geometry and purple
  hybrid material remain visible** in full-site renders alongside this
  system, same as noted in `GROWTH_SCAFFOLD.md` §9 — intentional, per the
  user's explicit request to preserve it for a possible future canopy
  pass, not a bug.
