# PinGrid — real columns as scaffolding, binary mullion zones (`PM_PinGrid`)

> **Revision 2, same session as Revision 1.** Revision 1 (below, §1-2 for
> context) generated two UNIFORM grids of freestanding pins, every pin's
> height driven by a continuous density gradient — every point got *some*
> pin, just varying in height. The user reviewed it ("starting off sound")
> but corrected the core approach, verbatim: *"the points at 27 feet can be
> the columns on site, this operates as the scaffolding, then the other
> implements such as mullions and open spaces are determined by the
> algorithm."* Sections 3 onward describe the current (Revision 2) system.
> The component was revised in place (same GUID, same file) — this is not
> a new component.

## 1. Purpose & scope

PinGrid was built in response to two reference images the user shared:

- **"Media as spatial organization"** — a dense interlocking orthogonal
  bar lattice with elements of clearly varying thickness and length.
- **A wood-block model** — bands of parallel sticks of varying *height*
  per position, like a pin-art height field, stacked into a terraced
  skyline, each band a different stain color.

Unlike FG1/FG2/`PM_ScaffoldFrame` (which skin a building's own facade
faces), PinGrid fills the **plan interior** of a footprint — closer to a
landscape/plaza treatment than a wall or overhang.

## 2. Revision 1 (superseded) — continuous density field

The first version generated a coarse grid (9ft) and fine grid (1.5ft) of
freestanding pins, both anchored at a phase-corrected `GRID_ORIGIN`, every
pin's height = `base_ft + range_ft * dnorm` where `dnorm` came from FG2's
own `density_at()` seed-crowding function — a direct answer to "is there a
way to base this off of the grid logic we designed for the pershing
site?" It worked (verified with real 0.448–1.000 `dnorm` variation after
relocating the test square to a real seed cluster), but read as too
uniform/continuous — the 27ft grid, used only as an abstract subdivision
module, didn't distinguish real structure from algorithmic infill.

## 3. Revision 2 — real columns + FG1's binary MARKED field

Recombines three pieces of logic already proven elsewhere in this session,
rather than inventing a new algorithm:

- **Scaffolding = real surveyed columns.** `real_geometry.json`'s
  `column_positions` (294 actual points, irregularly spaced ~27ft apart
  with real gaps) — not an idealized uniform grid. Literal structure, so
  it gets a literal height: `ScaffoldHeightFt` defaults to the JSON's own
  `column_height_ft` (30.0), not an algorithmic field.
- **Mullions/voids = FG1's own MARKED cells, byte-for-byte.**
  `col_lines`/`dtla_lines`/`seeds`/`MARKED`/`is_marked_world` are ported
  verbatim from `rhino/gh_facade_panelizer_component.py` — the same
  "structurally interesting zone" definition FG1's panels and
  `PM_ScaffoldFrame`'s growth bays already use, so all three components
  agree on the same zones rather than each inventing its own. A 27ft cell
  that's `MARKED` gets a mullion screen; an unmarked overlapping cell gets
  **nothing** — a genuine open void, not a shorter pin.
- **Mullion form = FG1's own mullion-strip idiom, applied in plan.**
  Within a marked cell, `subdivide_interval` (same helper FG1 and
  `PM_ScaffoldFrame` already use) divides the cell's local extent into
  `MullionSubDiv` steps; at each fine line, one straight strip `Box`
  (`make_strip`) runs the cell's full width, `MullionHeightFt` tall,
  `MullionWidthFt` thick — both U-direction and V-direction lines, giving
  a criss-cross screen, not isolated posts.

`col_lines`/`seeds`/`MARKED` use the **raw** `ORIGIN = (337.028, 570.21)`
here — deliberately NOT `PM_GrowthScaffold`'s phase-corrected
`GROWTH_ORIGIN` — so this component's zones agree with FG1's own
already-accepted field rather than introducing a second convention.

**A real gotcha hit and fixed during this revision**: the test footprint,
still sitting near `(324,567)` from Revision 1's fix, produced
`cellsOverlapping=0` even after enlarging it to 81×81ft. Root cause: the
raw-`ORIGIN`-based grid (`ORIGIN.X=337.028`) sits almost exactly at the
edge of the generated grid's coverage (`SITE_SIZE.X=354.22` plus a 9ft
boundary offset barely clears one more grid line past `ORIGIN`) — a
footprint positioned right at `ORIGIN`'s own corner can straddle the edge
of the `Us`/`Vs` cell-index arrays entirely, so no cell's sampled midpoint
ever falls inside such a narrow footprint. This is a variant of the
already-documented raw-vs-phase-corrected `ORIGIN` mismatch (first found
during `PM_GrowthScaffold`'s development), not a new bug class. Fixed by
moving the test footprint well into the site's interior, away from the
edge — see §6.

## 4. Component graph

Grasshopper "Python 3 Script" component, nickname `PM_PinGrid`, guid
`360b4697-61ef-492c-a541-2c1cd1a79fcd`, at canvas (600, 3200). Source
committed at
[`rhino/gh_pin_grid_component.py`](../rhino/gh_pin_grid_component.py).

| Input | Type | Range | Default |
|---|---|---|---|
| `Bake` | bool toggle | — | `True` |
| `Refresh` | bool toggle | — | `False` (unused — deterministic) |
| `ScaffoldHeightFt` | float slider | 0–60 | 30.0 (= real `column_height_ft`) |
| `ScaffoldStickFt` | float slider | 0.25–3 | 1.2 |
| `MullionSubDiv` | int slider | 2–30 | 10 (≈2.7ft spacing on a 27ft cell) |
| `MullionHeightFt` | float slider | 0–30 | 8.0 |
| `MullionWidthFt` | float slider | 0.05–2 | 0.35 |

Outputs: `ScaffoldPosts`, `MullionMembers` (Breps), `Log` (str → Panel).

Note on cross-section: unlike FG1's facade mullions (which have a
"width" in-plane and a "depth" projecting away from the glass plane), a
plan-fill vertical strip has no facade normal to project along — so only
one thickness parameter (`MullionWidthFt`) is meaningful here. A planned
second `MullionDepthFt` was deliberately dropped during implementation as
not applicable to this orientation.

## 5. Bake targets

```
Detailed_PinGrid::Footprint{i}::Scaffold
Detailed_PinGrid::Footprint{i}::Mullion
```

One `{i}` index per footprint curve found on `FOOTPRINT_LAYER`
("Default" for this prototype — see §7).

## 6. Verification record

Test footprint moved to world `(150,450)`–`(231,531)` (81×81ft, 3×3 bays,
well inside the site's grid coverage, clear of the edge issue in §3):

```
site_data_source=...\real_geometry.json
ORIGIN=(337.028,570.210)  column_height_ft=30.0
seeds=56 footprints=1 realColumnsInSite=294
scaffoldHeight=30.0 scaffoldStick=1.2
mullionSub=10 mullionHeight=8.0 mullionWidth=0.35
columnsInFootprints=9
cellsOverlapping=9 cellsMarked=3
scaffoldPosts=9 mullionMembers=66
BAKED to Detailed_PinGrid::*
```

Sanity checks that held: `9` real columns and `9` overlapping cells for a
3×3-bay footprint (one of each per bay, plausible); `66 = 3 marked cells ×
22 strips` (`MullionSubDiv=10` → 11 lines per axis × 2 axes = 22 strips
per cell) — exact.

Visual verification: disabled `PM_PinGrid`'s live GH canvas preview (same
gotcha as every other component in this stack), confirmed display mode was
Rendered, captured from two angles. Confirmed: sparse tall gray real-column
posts standing across the whole footprint — including in genuinely open
ground with no mullions at all — and dense teal criss-cross mullion-strip
screens confined to exactly the marked cells, with a clearly visible empty
void in the unmarked cell. A close-up confirmed the mullion screen reads
as a crisp waffle-grid of thin strips, not blobby freestanding posts.

## 7. Known caveats / open items — path to Pershing integration

- **Footprint source is still a placeholder.** `FOOTPRINT_LAYER =
  "Default"` only works because the test file has one lone curve there.
  Porting to the real Pershing document: replace `gather_footprints()`
  with something that derives a closed plan curve per `Program::*`
  building — everything downstream (`scaffold_columns`, `mullion_cells`,
  materials, bake targets) is already written generically against "a
  closed planar curve" and needs no other change.
- **No `is_buried()` culling.** A lone test footprint has no "other
  building" to collide with. Real multi-building integration needs the
  same culling pattern FG1/`PM_ScaffoldFrame` already use.
- **`MARKED`-cell overlap is tested at each cell's local-grid midpoint**
  against the footprint curve (same "sample the cell center" idiom used
  throughout this project), not a true polygon clip — an acceptable
  approximation at this prototype stage, consistent with how the rest of
  the project already treats cell/footprint overlap.
- **The mullion screen currently reads fairly dense/solid** at the default
  `MullionSubDiv=10`/`MullionWidthFt=0.35` — closer to a solid waffle
  panel than an airy screen from a distance. Tunable live; not adjusted
  further this session since it's within the slider's intended range.
- **No multi-bay tiling test across a real building's full footprint yet**
  — this revision validated a 3×3-bay area in isolation. Confirming the
  `MARKED` field and real-column filtering behave sensibly across a whole
  building (dozens of bays) is the natural next step before treating this
  as production-ready.
