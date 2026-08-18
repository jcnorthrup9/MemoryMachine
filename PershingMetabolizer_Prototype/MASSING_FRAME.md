# Massing Frame — real seeds, orthogonal L-system, digital pedestal undercroft

## 1. Why this exists

This session's earlier agent-growth work (`PM_GrowthColumns` /
`PM_GrowthAgents_Major` / `PM_GrowthAgents_Mullion`, see
`GROWTH_COLUMNS.md`) was seeded on an idealized test grid and unrelated to
the real site data. The user's verdict: *"i think that made it worse...
where we are now is not what i want."*

Three references clarified the actual target:

- **`Rhino/scripts/*.py`** (OneDrive SCI-Arc Thesis project, same folder
  tree as `FidelityGrid1.gh` itself) — a real, already-fabricated pipeline:
  real column-grid × DTLA-grid collision seeds, a canopy height-field
  falloff, and a physical pedestal (legs of real lumber hanging below a
  site model, floating by distance from a real datum, with a convex-hull
  "forced-touch" trick guaranteeing stability).
- **`modelGRIDinspo.png`** — a photograph of that built pedestal: *"a site
  model where the grid is used to create a pedestal, which grows down out
  of the site's building massing."*
- **`shared image (1).png`** ("Media as spatial organization") — the
  instructor's reference for the massing's *form language*: a dense,
  strictly orthogonal, interlocking frame of members at clearly varying
  length, crossing at multiple heights. Not a Voronoi/cellular pattern —
  flagged directly by the user as *"a pretty basic and overused pattern,"*
  and topologically wrong besides (Voronoi cells read organic, not
  orthogonal-interlocking).

Exploration confirmed the two projects are the **same site, same column
survey**, related by a coordinate-frame offset — not different data — and
that the OneDrive project's `ORIGIN` is measurably more accurate (this
session's `real_geometry.json`-derived `ORIGIN` silently missed the true
corner column, one of exactly 5 columns absent from the OBJ extraction).

Four decisions shaped the rebuild (`AskUserQuestion`):
1. Correct the real site frame everywhere in `FidelityGrid1.gh`, not just
   in new work.
2. Build and verify in phases.
3. Drive the massing frame with an **orthogonal L-system** (recursive,
   axis-constrained branching), not Voronoi.
4. Bring the pedestal into the **digital massing** itself, not just the
   physical model.

## 2. Real site frame correction (Phase 1)

Source of truth: `Rhino/scripts/grid_ortho.py` + `grid_dtla.py`.

```
ORIGIN        = (319.89, 596.22)   # Hill St / metro corner column, real feet
COL_SPACING   = 27.0
COL_ANGLE_DEG = 0.4                # real as-surveyed drift -- previously 0.0
DTLA_SPACING_U = 336.0
DTLA_SPACING_V = 600.0
DTLA_ANGLE_DEG = 36.4              # composed: 36.0 + COL_ANGLE_DEG
BOUNDARY_PTS  = [(-12.98,-3.09), (337.01,-0.67), (332.87,599.31), (-17.12,596.90)]
BOUNDARY_OFFSET = 9.0
```

Applied identically to `PM_FacadePanelizer` (FG1), `PM_ScaffoldFrame`,
`PM_PinGrid`, and `PM_GrowthColumns` — all four previously used a
runtime-derived `ORIGIN=(337.028,570.21)` with `COL_ANGLE_DEG=0.0` and a
synthesized axis-aligned rectangle boundary instead of the true
quadrilateral. `real_geometry.json`'s 294 `column_positions` live in a
different local frame (bottom-left column ≈ `(13.028,3.124)`, not
`(0,0)`-ish) — translated by `(-13.028,-3.124)` wherever used
(`PM_PinGrid`, `PM_GrowthColumns`). Translation-only; a residual
sub-degree rotation between the two frames is not corrected — a known,
documented approximation, consistent with how this project already
treats its own precision limits.

**Verification**: FG1's `Log` now reports `col_lines=36 dtla_lines=3
seeds=55 cells=264` — an **exact match** to the OneDrive `.md`'s
documented real numbers (13×23=36 column-grid lines, 3 DTLA lines, 55
seeds, 12×22=264 cells). `marked=50` vs. the doc's `47` is expected (this
test document's placeholder buildings aren't positioned identically to
the real thesis massings).

## 3. `PM_HeightField` — real falloff (Phase 1)

Near-verbatim port of `canopy_height_field.py`'s pure `height_field()`/
`smoothstep()`. Real defaults: `MinHeightFt=9.0`, `MaxHeightFt=24.0`,
`RadiusFt=54.0`. Distance is 2D (plan), from each query point to its
nearest real seed. Verified: querying at the seeds themselves gives
`heightRange=(9.00,9.00)` (exact, expected — zero distance means minimum
height); querying at `PM_GrowthColumns.MullionPoints` gives
`heightRange=(9.33,24.00)` (real variation, both bounds reached).

## 4. `PM_MassingFrame_Lsystem` — the massing form language (Phase 2)

Orthogonal L-system: each real seed inside the massing footprint becomes
a branching root. At each node, up to 5 of the 6 signed axis directions
(excluding only the reverse of the arrival direction — continuing
straight is a valid candidate) independently roll against `BranchProb`
to spawn children. Branch length comes from `PM_HeightField`'s
`height_field()` at the branch's start point (called inline, not through
a separate component pass, since positions are generated live during
recursion), scaled down by recursion depth so branches shorten as they
go. Recursion stops at `MaxDepth` or when a branch would exit the
massing's actual volume (same `IsPointInside` containment pattern as
`PM_GrowthAgents`).

Deterministic: a simple FNV-style integer hash of
`(round(x*1000), round(y*1000), round(z*1000), depth, direction_index)`
drives the branch/no-branch roll — no unseeded `Random()`, so identical
seed positions always produce the identical frame (same reproducibility
principle as the OneDrive project's `mulberry32`-keyed Voronoi jitter).

**Verification**: with the single real seed that falls inside the test
massing (`rootsInMassing=1`), 36 valid solid Breps were generated
(`maxDepthReached=4`, full depth), confirmed bounding box `18.3×10.3×9.4
ft` — real extent, not degenerate. Visual confirmation required hiding
the massing (the frame grows *inside* the solid volume by design, so it's
naturally occluded from outside — correct containment behavior, not a
bug): with the massing hidden, the result is a dense, interlocking,
strictly orthogonal lattice of members at clearly varying length crossing
at multiple heights — a close visual match to "Media as spatial
organization."

## 5. `PM_PedestalUndercroft` — digital pedestal (Phase 3)

Ported from `pedestal_leg_distribution.py`'s pure `hull_2d()` /
`compute_forced_touch_set()` — same monotone-chain convex hull, same
"force the hull-perimeter legs to touch, let every interior leg float by
distance from `ORIGIN`" logic. Adapted to real feet (the source script's
own values are inches, for the ~1:192 physical model) and legs hang
**below** the massing's own underside rather than a separate site-model
slab — bringing the pedestal into the digital massing itself, per
decision 4.

A volume-weighted center of mass is guaranteed to lie within the convex
hull of the points it's averaged from — forcing exactly the hull legs to
touch and letting every interior leg float at the full range therefore
guarantees stability by construction, independent of how dramatic the
interior float is. This is the source script's own key insight, reused
verbatim rather than re-derived.

**Verification** (using `PM_GrowthColumns.MajorPoints` — 9 real-grid
positions under the test massing, since only 1 of the 55 site-wide real
seeds falls under this small footprint): `candidateLegs=9
forcedTouchHullLegs=6 legsBuilt=9`. Viewport capture from below confirmed
multiple legs of clearly varying length hanging under the massing's
underside, consistent with the photographed pedestal's read.

## 6. Re-seeding `PM_GrowthAgents` (Phase 4)

Per "keep both, layer them": `PM_GrowthAgents_Major` and
`PM_GrowthAgents_Mullion`'s `Points` input moved from
`PM_GrowthColumns.MajorPoints`/`MullionPoints` (idealized grid) to FG1's
real `SeedPts` — unifying the whole pipeline around one real data source.
`RigidityBias`/`MaxGens`/`Speed` unchanged.

**Verification**: `frozenByContainment=55/55` for both instances —
expected, not a bug: only 1 of the 55 real site-wide seeds falls inside
this small test massing, so the other 54 agents' very first step attempt
fails containment immediately (their seed position itself sits outside
the massing's footprint). Consistent with `PM_MassingFrame_Lsystem`'s own
`rootsInMassing=1` finding on the same massing.

## 7. Component graph (new pieces, `FidelityGrid1.gh`)

```
PM_FacadePanelizer (FG1, corrected constants)
  SeedPts (55 real seeds) ---+--> PM_HeightField.Seeds
                              +--> PM_GrowthAgents_Major.Points
                              +--> PM_GrowthAgents_Mullion.Points
                              +--> PM_ElasticGrid.Seeds
                              +--> PM_CellOccupancy.Seeds
                              +--> Merge (input 1)
  DtlaLines (3 real lines)  ------> PM_ElasticGrid.DtlaLines

Massing (shared Brep param) --> PM_HeightField (indirectly, via query points)
                              --> PM_MassingFrame_Lsystem.Massing
                              --> PM_PedestalUndercroft.Massing
                              --> PM_CellOccupancy.Massing

PM_CellOccupancy.OccupiedCells --> Merge (input 2)
Merge --> Flatten Tree --> PM_MassingFrame_Lsystem.Seeds
                            (117 = 55 real + 62 cell-occupancy, replaces
                            the direct FG1.SeedPts wire from §6)

PM_ElasticGrid.DistortedLines --> (independent visual layer, not wired
                                    into massing generation -- §1.6's own
                                    original role, a diagram/canopy-scale
                                    motif, not a structural driver)

PM_GrowthColumns.MajorPoints --> PM_PedestalUndercroft.Seeds
                                  (idealized grid retained here only,
                                  since too few real seeds fall under
                                  this small test footprint for a
                                  meaningful hull/float demo)
```

## 8. Elastic grid distortion + cell-occupancy placement guide (this pass)

A Gemini-authored spec ("GHPython Field Interference & Elastic Grid
Generator") was reviewed for reuse. Two of its ideas held up; a third was
rejected outright:

- **Kept, ported properly**: "elastic Grid B buckling" turned out to
  independently re-derive `GRID_LOGIC_AND_MODEL_ALGORITHMS.md` §1.6's
  "threshold markers + warped DTLA lines" — real, already fabricated for
  this exact site, but never saved as its own script (same gap as
  Behavior A/B) or ported into Grasshopper. Built as `PM_ElasticGrid`.
- **Kept, repurposed**: the spec's stair-stepped solid voxel massing was
  rejected as visible geometry — it risks reintroducing the "doesn't
  match the open interlocking bar-frame" problem that got Attempt 1
  rejected — but its underlying voxel-occupancy test is a real fix for a
  real problem: this session's small test massing only contained 1–9 of
  the 55 site-wide real seeds, giving `PM_MassingFrame_Lsystem` a sparse,
  near-degenerate single-root result. Built as `PM_CellOccupancy`, a
  **placement guide only** — qualifying cell centers feed the L-system as
  additional candidate roots, gated by real-seed proximity so they stay
  anchored to real data rather than an arbitrary uniform grid.
- **Rejected**: the spec's straight-down pedestal-leg logic was a
  stability-unguaranteed regression from `PM_PedestalUndercroft`
  (§5 above), which already ports the real fabricated pedestal's
  forced-touch convex-hull + distance-float guarantee. Not reused.

### `PM_ElasticGrid`

DTLA grid lines (FG1's new `DtlaLines` output — previously only exposed
combined with `col_lines` as `GridCrv`) resampled at `SampleStepFt` (3.0
ft, matching the doc). Each sample point is pushed away from every real
seed within a radius, force **accumulating** across all seeds in range
(not nearest-only, per the doc). Both radius and force scale by that
seed's own distance from `ORIGIN` via `smoothstep()` — the same falloff
convention as `PM_HeightField`, not a linear falloff a from-scratch spec
might guess at — full strength at `ORIGIN`, fading to zero at the
farthest real seed. Rebuilt via `Curve.CreateInterpolatedCurve` (a bug
surfaced live: the first push used the nonexistent
`NurbsCurve.CreateInterpolatedPoints`, corrected on the spot).

**Calibration**: the doc describes the effect (~7-9ft max deviation from
straight) but saves no exact constants. Default `MaxRadiusFt=60,
MaxForceFt=9` overshot badly (`maxDisplacementFt=15.22`) because
accumulated push across overlapping seed radii compounds fast — not a
per-seed cap. Recalibrated live against FG1's real 55 seeds / 3 DTLA
lines: `MaxRadiusFt=35, MaxForceFt=5` lands `maxDisplacementFt=8.26`,
inside the documented target. Viewport capture confirms visibly bent
lines, not a diagram artifact.

### `PM_CellOccupancy`

For each `CellSizeFt` cell (default 9.0 ft — independent of the 27ft
column-module `MARKED` field, a finer placement-guide resolution) whose
center falls inside the massing footprint (reuses
`PM_GrowthColumns.footprint_from_massing()`'s section-cut pattern
verbatim), qualifies if within `InfluenceRadiusFt` (default 54.0,
matching `PM_HeightField`'s own `RadiusFt`) of at least one real seed —
binary in/out, not a density field, matching this project's established
"real open voids, not everywhere" convention.

**Verification** (same small test massing used throughout this doc):
`seeds=55 cellSizeFt=9.0 influenceRadiusFt=54.0` → `candidateCells=81
occupiedCells=62`.

### Wiring change: merged root set feeds the L-system

`PM_MassingFrame_Lsystem.Seeds` no longer reads FG1's `SeedPts` directly.
A native `Merge` (FG1 `SeedPts` + `PM_CellOccupancy.OccupiedCells`) feeds
a `Flatten Tree` (required — `Merge` preserves each input as a separate
tree branch, and the L-system script reads `Seeds` as one flat list; an
unflattened merge would make the script iterate per-branch instead of
over the combined set) into `Seeds`.

**Verification, before/after**:

| | Before (§4, real `SeedPts` only) | After (merged) |
|---|---|---|
| Seeds in | 55 | 117 (55 real + 62 cell-occupancy) |
| `rootsInMassing` | 1 | 63 |
| `members` | 36 | 759 |

The sparsity problem flagged as an open caveat below is directly
addressed, not just theoretically — same small test massing, real
seed-anchored placement guide, order-of-magnitude denser frame.

## 9. Known caveats / open items

- `PM_HeightField`'s falloff math is duplicated inline inside
  `PM_MassingFrame_Lsystem` (can't wire the two components directly,
  since L-system branch positions are generated live during recursion,
  not pre-computable) — keep both copies in sync if the math changes.
- `PM_PedestalUndercroft`'s "massing underside" is a flat bounding-box
  `Min.Z`, not a true per-point ray-cast against the actual solid —
  correct for this prototype's simple prismatic test massing; a real
  massing with a non-flat underside would need the source script's own
  `ground_z_at()`-style ray-cast.
- All new components were verified against this one small test massing.
  Prior to §8, this footprint only contained 1–9 of the site's 55 real
  seeds depending on which point set was used; `PM_CellOccupancy` raises
  that to 63 roots on the same footprint, but real `Program::*` building
  footprints elsewhere on the real site will still contain more real
  seeds and give denser, less degenerate results — not yet tested against
  those.
- `PM_ElasticGrid`'s `MaxRadiusFt`/`MaxForceFt` are a calibrated
  approximation, not an exact port — `GRID_LOGIC_AND_MODEL_ALGORITHMS.md`
  §1.6 documents the ~7-9ft max-deviation effect but saves no source
  script or exact constants. If the real seed population or DTLA line
  count changes materially, re-verify `maxDisplacementFt` against the
  ~7-9ft target and re-tune rather than trusting the current sliders.
- The residual sub-degree rotation between `real_geometry.json`'s column
  frame and `grid_ortho.py`'s frame (noted in §2) is not corrected —
  translation-only.
- `FidelityGrid1.gh` is modified but unsaved as of this writing.
