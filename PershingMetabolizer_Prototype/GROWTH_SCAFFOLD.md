> **Superseded, 2026-08-01.** After reviewing this system, the user rejected
> it directly: the short zigzagging voxel steps read as diagonal rather than
> orthogonal, and the cross-building bridging left buildings' own footprints
> entirely, which was not the intent. Replaced by **PM_ScaffoldFrame** — see
> [`SCAFFOLD_FRAME.md`](./SCAFFOLD_FRAME.md) — a direct 3D extension of
> FidelityGrid1's own mullion-grid logic instead of a new simulation. Per
> this project's established pattern, `PM_GrowthScaffold`'s component and
> baked geometry are preserved, not deleted: its `Bake` toggle is off and
> its `Detailed_Scaffold` layer is hidden. Everything below this notice
> documents the disabled system as built.

# GrowthScaffold — cross-building agent lattice (`PM_GrowthScaffold`)

## 1. Purpose & scope

GrowthScaffold is the replacement for FidelityGrid2 as this project's second
compounding-grid layer. Where FidelityGrid1 skins each building's own facade
with a panel/mullion grid, GrowthScaffold does something categorically
different: it grows a **3D interlocking bar lattice** — architectural
scaffolding — that builds up out of the massing and **bridges between
separate buildings**, rather than staying confined to one facade plane. It
is an agent-based, grid-snapped, attractor-seeking growth system ported
from an external Processing/three.js sketch (`app_tk4.js`'s
`Agent.update()`, documented in this repo's
[`HANDOFF_08012026_PROCESSING_GROWTH_ALGO_FOR_MASSING.md`](../HANDOFF_08012026_PROCESSING_GROWTH_ALGO_FOR_MASSING.md)).

This was a direct response to user feedback that FidelityGrid2 (warped
panel/standoff screens) was the wrong direction — the brief was "more of a
3D logic that builds up walls, based on the current building's massing,"
referencing a framework/scaffolding image. FidelityGrid2's component and
baked geometry are preserved (not deleted), disabled, and reserved for a
possible future canopy-design pass; see
[`FIDELITY_GRID_1.md`](./FIDELITY_GRID_1.md) for that system.

**Outcome:** a dense lattice of uniform timber-colored box "sticks,"
uniform length and cross-section, growing from footprint-edge/column-grid
intersections on every `Program::*` building, climbing and cantilevering
toward a pooled, site-wide set of attractor points — producing genuine
cross-building bridges rather than 8 independent per-building clusters.

## 2. The double-grid concept

The user's framing, implemented directly:

- **Large organizer** — the site's real 27ft structural column grid.
  Determines *where agents spawn*: every point where a building's plan
  footprint edge crosses a column-grid line.
- **Small patterning grid** — the growth algorithm's own fixed step length
  / voxel size (`TLengthFt`, default 1.5ft), scaled down from the 27ft bay.
  1.5ft divides evenly into both 27ft (18 steps/bay) and the attractor
  height tiers (20/10 steps at defaults), so agents can land exactly on a
  voxel plane rather than approaching it asymptotically.

## 3. Site frame & constants

Reuses FidelityGrid1's site-data plumbing (`load_site_data()`,
`build_grid_lines()`, `segment_intersection()`) with one addition specific
to this component:

- **Grid phase mismatch — discovered and fixed this session.** The site's
  real column-survey `ORIGIN = (337.028, 570.21)` is **not** in phase with
  the building massing module: `337.028 mod 27 = 13.028`,
  `570.21 mod 27 = 3.21`. Every building footprint IS bay-snapped to exact
  multiples of 27 from world (0,0) — but FidelityGrid1's `col_lines`,
  anchored at the raw survey `ORIGIN`, never actually pass through any
  footprint corner. This doesn't matter for FG1 (a pure facade panelizer,
  no reason to change it), but it matters here, where attractor placement
  is defined as footprint-edge × grid-line intersections.
- **Fix, scoped to this component only:** when `SnapGridPhase` (default
  `True`) is on, the grid is rebuilt from a phase-corrected anchor,
  `GROWTH_ORIGIN = (round(337.028/27)*27, round(570.21/27)*27) = (324.0,
  567.0)` — independently verified correct, since that exact point is
  `CommunityCenter`'s own far corner. `SnapGridPhase=False` uses the raw
  survey `ORIGIN` instead, for comparison (expect ~zero footprint-corner
  hits in that mode).
- `COL_SPACING = 27.0` ft, same real structural bay as FG1.
- All dimensions in feet, matching the rest of the repo's real-world unit
  convention.

## 4. Algorithm walkthrough

1. **Attractor/spawn construction** (`build_attractors`): for every
   `Program::*` building, get its 4 axis-aligned bounding-box plan edges
   (`footprint_edges` — buildings are simple axis-aligned boxes in plan,
   confirmed via bbox inspection, so no face-extraction is needed).
   Intersect each edge against every phase-corrected column-grid line.
   Pool the hits from **all buildings into one site-wide list** (the
   user's explicit choice — this is what makes cross-building bridging
   possible), dedupe at 0.05ft.
   - These grade-level points become `SpawnPts` (Z=0).
   - The same point set, lofted to one of two roof-height tiers via a
     deterministic checkerboard on bay index (`(nu+nv) % 2` — no RNG),
     becomes `AttractorPts` (Z = `AttractorZFt` or
     `AttractorZFt * AttractorZSplit`).
   - Attractors and spawns are deliberately **disjoint in Z**: if both
     existed at the same (x,y), the Z=0 copy would always be nearer and
     nothing would ever climb. An agent's own directly-overhead attractor
     is excluded from its own target search for the same reason — else
     every agent just grows a trivial straight column.
2. **Agent init**: one agent per spawn point (or the first `MaxAgents` in
   fixed order, if capped), `pos = spawn`, `age = 0`, empty history.
   `occupied` (the shared voxel-collision set) is pre-seeded with every
   spawn voxel.
3. **Driver**: agents step **round-robin** (one step each per tick,
   repeated up to `MaxLifespan` ticks) rather than each agent running to
   completion before the next starts — this is what makes the shared
   `occupied` voxel set actually produce mutual dodging/interlocking
   instead of a spawn-order bias where early agents claim every voxel
   before later agents move at all.
4. **Per-agent step** (`step_agent`):
   - Find the nearest in-range attractor (excluding own-overhead),
     respecting `MaxAttractorDistFt`; no attractor in range → terminate
     immediately, `cause="no_target"` (no fallback "ceiling" target — the
     source sketch's image-brightness ceiling concept doesn't port here).
   - Steer toward it, then `force_ortho()`: zero every axis except the
     largest-magnitude one, normalize — always yields a unit vector along
     ±X/±Y/±Z. This is the algorithm's core "grid logic," reused verbatim
     from the Processing/three.js source.
   - Try to commit a `TLengthFt`-long step in that direction; on voxel
     collision, try a horizontal dodge, then a vertical escape; if all
     three candidates are blocked, terminate, `cause="cornered"` — an
     **expected, healthy outcome**, not a bug. These produce the
     cantilevered dead-end tips visible in the reference image
     (`DeadEndPts`).
   - Reaching within one step of the target terminates with
     `cause="arrived"`; hitting `MaxLifespan` terminates with
     `cause="aged"`.
5. **Geometry**: every committed step becomes one `make_stick()` box —
   fixed `StickSizeFt` cross-section, oriented along the step's axis —
   appended to `Members`. Each agent's full committed-point history also
   becomes one `PathCrv` polyline.

## 5. Component graph

Grasshopper "Python 3 Script" component, nickname `PM_GrowthScaffold`, guid
`24f4b53c-578d-4ef5-9fde-20b1f9a61f02`, at canvas (600, 1750). Source
committed at
[`rhino/gh_growth_scaffold_component.py`](../rhino/gh_growth_scaffold_component.py).

| Input | Type | Range | Default |
|---|---|---|---|
| `Bake` | bool toggle | — | `True` |
| `Refresh` | bool toggle | — | `False` (unused — fully deterministic, no RNG) |
| `TLengthFt` | float slider | 0.75–6.0 | 1.5 |
| `StickSizeFt` | float slider | 0.25–3.0 | 0.5 |
| `Dna0` | float slider | 1.0–4.0 | 2.0 (mathematically inert — see caveats) |
| `MaxLifespan` | int slider | 10–500 | 120 |
| `MaxAttractorDistFt` | float slider | 27–600 | 135 (5 bays) |
| `AttractorZFt` | float slider | 0–60 | 30.0 (matches `column_height_ft`) |
| `AttractorZSplit` | float slider | 0–1 | 0.5 (lower tier = 15ft) |
| `MaxAgents` | int slider | 0–400 | 0 (0 = uncapped, one per spawn point) |
| `SnapGridPhase` | bool toggle | — | `True` |

Outputs: `Members` (Breps), `PathCrv` (Curves), `AttractorPts`, `SpawnPts`,
`DeadEndPts` (Points), `Log` (str → wired to a Panel).

## 6. Bake targets

```
Detailed_Scaffold::Members::X | Y | Z          (sticks, grouped by axis)
Detailed_Scaffold::_Parti::Attractors | Spawns | DeadEnds | Paths
```

`clear_previous_bake()` deletes every object under `Detailed_Scaffold`
(keeping the layer structure) before each bake, same pattern as FG1/FG2.

## 7. Materials & the two-step workflow

One PBR material, `PM_Scaffold_Timber` (`#B07C4A`, roughness 0.75,
metallic 0.0), assigned by layer across all three `Members::*` axis
layers. Subject to the same Grasshopper-Python3-materials-don't-render
gotcha documented in FIDELITY_GRID_1.md §7 — same two-step workflow:

1. Toggle `Bake` in Grasshopper.
2. `python rhino/run_rhino_script.py rhino/apply_facade_materials.py`
   (now applies all four materials — glass, mullion, hybrid, and
   scaffold-timber — in one run).

## 8. Verification record

First successful run, `Log` output:

```
site_data_source=C:\Users\jcnor\MemoryMachine\PershingMetabolizer_Prototype\real_geometry.json
grid_phase=SNAPPED origin=(324.000,567.000)  [raw ORIGIN=(337.028,570.210)]
col_lines=37  breps=10  raw_edge_hits=188  attractors=112  spawns=112
tLength=1.50ft stick=0.50ft  attr_z=30.0/15.0  maxLife=120 (need>=143)  maxAttrDist=135ft
agents=112  steps_run=39
terminations: arrived=87 cornered=25 aged=0 no_target=0
segments=3517  axis X=918 Y=1029 Z=1570  occupied_voxels=3629
```

Sanity checks that held: `segments (3517) == occupied_voxels (3629) -
spawns (112)`; `cornered` rate 22.3%, within the 10–35% "healthy" range
(too low means agents never interlock, too high means the field is too
congested to grow); `arrived + cornered + aged + no_target == agents`
(87+25+0+0=112).

Visual verification: hid the `_Parti::Paths/Attractors/Spawns/DeadEnds`
diagnostic layers and disabled live canvas preview on `PM_GrowthScaffold`,
`PM_FacadePanelizer`, and `PM_FacadeScreen` (see §9 — layer visibility
alone does not hide GH's own live preview), then captured the Perspective
viewport in Rendered mode. Confirmed: real timber-colored interlocking
zigzag lattices climbing from building corners and cantilevering out over
open ground toward the site's sports courts — genuine cross-building
bridging, matching the reference image's "framework/scaffolding" intent.

## 9. Known caveats / open items

- **`Dna0` is currently mathematically inert.** The Processing original
  used attractor-affinity as one of two steering terms, counterbalanced by
  a swarm-cohesion force; this port only has the attractor-seeking term,
  and `force_ortho()` discards vector magnitude entirely (keeps only
  sign). The slider is wired and documented for parity / in case a second
  steering term is added later, but changing its value currently has zero
  effect on the output.
- **Rhino layer visibility does not hide live Grasshopper canvas
  preview.** Discovered during this verification pass: setting
  `_Parti::Paths` etc. to `visible=false` via `rhino_scene(layer_set)`
  correctly updated the Rhino layer (confirmed via re-query), but the
  dense red diagonal lines/cross-markers dominating the viewport persisted
  — because they were GH's own *unbaked* live preview of the `PathCrv`/
  `AttractorPts`/`SpawnPts`/`DeadEndPts` output wires (and, separately, of
  FidelityGrid1/2's site-wide `col_lines`/`dtla_lines` debug outputs),
  which render directly in the Rhino viewport independent of any Rhino
  layer's visibility. Fixed via `gh_canvas(action='preview', enabled=false)`
  on the three components (`PM_GrowthScaffold`, `PM_FacadePanelizer`,
  `PM_FacadeScreen`). Worth remembering for any future diagnostic-cleanup
  pass: **disable component preview, not just layer visibility**, when a
  component has multiple diagnostic/debug outputs wired to canvas panels
  or points.
- **`steps_run=39` vs `maxLife=120`**: the driver loop exits early once no
  agent is still alive, not at the slider's cap — expected, not a bug
  (most agents reach `arrived`/`cornered` well before 120 ticks at this
  site's scale).
- **FidelityGrid2's baked `Detailed_Screen::*` geometry and purple hybrid
  material remain visible** in full-site renders (its `Bake` toggle is
  off, but disabling `Bake` does not retroactively clear a prior bake).
  This is intentional per the user's explicit request to preserve it, not
  a bug — hide the `Detailed_Screen` layer manually if a render needs to
  isolate GrowthScaffold alone.
