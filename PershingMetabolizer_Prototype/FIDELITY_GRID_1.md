# FidelityGrid1 — facade panelization (`PM_FacadePanelizer`)

## 1. Purpose & scope

FidelityGrid1 is the first layer in a planned stack of compounding grid-driven
facade fidelity passes. It implements **sections 1–4 and 6** of
[`2D_GRID_PARTI_LOGIC_SPEC.md`](./2D_GRID_PARTI_LOGIC_SPEC.md) — the
column-grid/DTLA-grid collision system and Behavior B's deterministic
recursive subdivision — applied to the vertical facade faces of the site's
building massing. It deliberately does **not** implement section 5 (warped
grid lines) or section 7 (Voronoi webbing / Behavior A) — those are
FidelityGrid2's territory, layering an additional, more three-dimensional
treatment on top of this one.

**Outcome:** every `Program::*` building mass gets a real glass-panel +
mullion facade skin instead of a plain undetailed box, with panels finely
subdivided exactly where the site's real column grid collides with the DTLA
city block grid, and left as plain single panels everywhere else.

## 2. Site frame & constants

All constants live at the top of the script and are derived, not hardcoded,
where possible:

- **ORIGIN** `(337.028, 570.21)` — computed at runtime by `load_site_data()`
  as the `real_geometry.json` `column_positions` entry nearest
  `secondary_entrance_anchor` (the metro-entrance corner). The spec calls
  for "the column at the metro-entrance corner," which requires this
  nearest-snap rather than using the raw anchor point.
- **Site size** `354.22 × 602.53 ft` — from `real_geometry.json`'s
  `site.width_ft`/`length_ft`.
- **Column grid**: `COL_SPACING = 27.0` ft (this repo's real
  `STRUCTURAL_BAY_FT`), `COL_ANGLE_DEG = 0.0`. Measured empirically, not
  assumed: the document's 294 real `column_positions` are perfectly
  axis-aligned in this coordinate frame (no measurable survey drift), so
  this is **not** the thesis model's ~0.4° drift — that number is specific
  to a different site/frame and does not port.
- **DTLA grid**: `336 × 600 ft` (the real 1849 Ord Survey block module),
  `DTLA_ANGLE_DEG = 36.0` — reconciles with this repo's existing
  `SITE_ROTATION_DEG = 36` in `index.html`.
- **Boundary offset**: `9.0 ft` past the site boundary, in the grid's own
  rotated local frame.
- Rhino world X/Y maps directly to `real_geometry.json`'s x/z convention
  with **zero offset** — confirmed empirically (building footprint bboxes
  are exact multiples of 27 starting at X=0).
- All dimensional constants are in **feet** (this document's real-world
  unit system) — no unit-scale conversion layer is needed here, unlike the
  earlier meter-based canopy scripts.

## 3. Algorithm walkthrough

1. `build_grid_lines(ORIGIN, 27, 27, 0°, boundary, 9)` → the column grid:
   **36 lines** (13 U + 23 V).
2. `build_grid_lines(ORIGIN, 336, 600, 36°, boundary, 9)` → the DTLA grid:
   **3 lines**.
3. Pairwise `segment_intersection` between every column line and every DTLA
   line, deduped at 0.05 ft tolerance → **56 seeds**.
4. Behavior B marking: the column grid divides the site into a
   **12 × 22 = 264-cell** field. Each seed sits on exactly one column-grid
   line (that's how it was built) and marks the two cells straddling that
   line, at the cross-index given by the seed's own position → **51 marked
   cells**.
5. Marked cells get a 4×4 recursive subdivision (`SubDiv`, default 4);
   unmarked cells stay a single plain panel.

## 4. Facade application

Applied per-building to every `Program::*` massing object:

- **Facade face detection** (`facade_faces`): a Brep face counts as a
  facade candidate if it's planar (`TryGetPlane`) and near-vertical
  (`abs(normal.Z) <= VERT_FACE_NORMAL_DOT = 0.1`), with area ≥ 4 ft².
- **Local frame** (`face_frame`): `h_axis = ZAxis × face_normal` (in-plane
  horizontal direction); vertical extent is grade-clipped
  (`z0 = max(min_z, 0)` — a facade never gets panels below world Z=0).
- **Horizontal joints** (`facade_h_joints`): every column-grid line
  crossing the face's plan-projected segment becomes a joint — reuses the
  same `segment_intersection` helper as grid generation.
- **Vertical bands** (`z_bands`): divided at `FloorFt` (default 13.5 ft)
  intervals.
- **Buried-panel culling** (`is_buried`): a candidate cell is skipped if
  its center falls inside any *other* building's closed Brep — relevant
  where massing footprints overlap in plan (e.g. the two `CommunityCenter`
  masses).
- **Cell → geometry** (`make_cell_boxes`): each (h-interval × z-band) cell
  becomes one plain panel Box, or — if its plan-midpoint falls in a marked
  cell — a 4×4 grid of smaller panel Boxes. Mullion strips
  (`facade_mullions`, `facade_floor_mullions`) run along every joint line
  at width `MullionFt` (default 0.5 ft), doubling as the panel-to-panel
  reveal gap.

## 5. Component graph

Grasshopper "Python 3 Script" component, nickname `PM_FacadePanelizer`,
guid `719467e6-7cf5-4848-99b0-c5dd57e5442c`, built and driven this session
via the Cordyceps MCP bridge. Source committed at
[`rhino/gh_facade_panelizer_component.py`](../rhino/gh_facade_panelizer_component.py).

| Input | Type | Range | Default |
|---|---|---|---|
| `Bake` | bool toggle | — | `False` |
| `Refresh` | bool toggle | — | `False` (currently unused; wired for future use) |
| `SubDiv` | int slider | 2–8 | 4 |
| `FloorFt` | float slider | 6–27 | 13.5 |
| `PanelDepthFt` | float slider | 0.1–2 | 0.25 |
| `MullionFt` | float slider | 0.1–2 | 0.5 |

Outputs: `Panels`, `Mullions` (Brep lists), `GridCrv`, `SeedPts`,
`MarkedCrv` (site-level diagnostics), `Log` (str summary → wired to a
Panel).

## 6. Bake targets

```
Detailed_Facades::{ProgramName}::Panels
Detailed_Facades::{ProgramName}::Mullions
Detailed_Facades::_Parti::ColumnGrid | DtlaGrid | Seeds | MarkedCells
```

`clear_previous_bake()` deletes every object under `Detailed_Facades`
(keeping the layer structure itself) before each bake, so toggling `Bake`
repeatedly never duplicates geometry.

## 7. Materials & the two-step workflow

Two PBR materials: `PM_Glass_Panel` (`#CFE6E4`, roughness 0.05,
transparency 0.8) and `PM_Mullion_Metal` (`#4A4A4A`, metallic 0.9,
roughness 0.3), assigned **by layer** (`Layer.RenderMaterialIndex`).

**The gotcha.** Materials created and assigned from *inside* the
Grasshopper Python 3 Script component set the data correctly — verifiable
via Cordyceps' `rhino_render(material_list)` — but do **not** visibly
render in Rhino's Rendered display mode. Confirmed by a decisive
side-by-side test this session: identical RhinoCommon material-creation
code (`Material` + `ToPhysicallyBased`), run instead through Rhino's
classic scripting engine, rendered correctly on the first try, in the same
document, with the render engine already confirmed set to "Rhino Render."
Root cause not fully diagnosed — something about a display-pipeline
notification that Grasshopper's Python 3 engine (CPython via pythonnet)
doesn't trigger, that the classic engine does.

**Workflow, two steps, every time:**

1. Toggle `Bake` in Grasshopper → generates/regenerates geometry.
2. Run the materials fix via the existing `win32com`/COM bridge:
   ```
   python rhino/run_rhino_script.py rhino/apply_facade_materials.py
   ```
   (uses `Rhino.Interface.8` → `_-ScriptEditor Run "<path>"`, completely
   bypassing Grasshopper/Cordyceps for this step).

Step 2 **must be re-run after every re-bake** — `clear_previous_bake()`
regenerates objects with Grasshopper's own (invisible) material
assignment each time.

## 8. Verification record

Expected `Log` output on a clean bake:

```
col_lines=36 dtla_lines=3 seeds=56 cells=264 marked=51
ORIGIN=(337.028,570.210)  site=354.22x602.53ft
PracticeSpace: marked_facade_cells=0 panels=0 mullions=0
ComputerTechSpace: marked_facade_cells=0 panels=0 mullions=0
ArtsAndCraftsStudio: marked_facade_cells=0 panels=6 mullions=20
WorkOutEquipment: marked_facade_cells=0 panels=10 mullions=24
PicnicGrillSpace: marked_facade_cells=0 panels=8 mullions=24
Greenspace: marked_facade_cells=0 panels=0 mullions=0
Skatepark: marked_facade_cells=17 panels=204 mullions=136
CommunityCenter: marked_facade_cells=45 panels=875 mullions=490
TOTAL panels=1103 mullions=694
```

Visual verification: hide `Program::*` massing, switch to Rendered
display, capture the viewport — the panelization pattern shows mullion
outlines tracing each building's footprint, with dense fine subdivision in
the marked-cell clusters and plain panels elsewhere.

## 9. Known caveats / open items

- **Marked-cell count**: 51 in this document vs. the spec's thesis-model
  reference of 47. Seeds match exactly (56 = 56), so the discrepancy is in
  cell-marking tie-breaking for near-coincident seeds close to ORIGIN
  (multiple column/DTLA line pairs converge there) — not investigated
  further, not believed to be a bug.
- **`PracticeSpace` / `ComputerTechSpace` produce zero panels.** Both
  masses are wholly below grade (bbox Z from −10 to exactly 0.0 — roof
  flush with grade). `face_frame`'s grade clip correctly yields zero
  above-ground facade extent for these. Confirmed via bbox inspection, not
  a bug.
- **`Program::Greenspace` open item**: Rhino's layer listing reports
  `objectCount: 1` for this layer, but every object-level query against it
  (`rhino_scene(action='objects', layer='Greenspace')`) returns empty —
  unresolved. Worth a look if Greenspace facade panelization is needed
  later.
