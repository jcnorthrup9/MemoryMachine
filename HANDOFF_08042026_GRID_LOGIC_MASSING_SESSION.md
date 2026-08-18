# Handoff — 2026-08-04: Grid logic / massing design session — status and open questions

## 1. Read this first — where we actually stand

Two full build-and-verify passes were completed this session on "the grid
logic for building massings." Both are technically working — no errors,
numbers check out against real documented values, visuals were captured
and confirmed. The user's own words after the **second** pass: *"i dont
think what we just did is the what i want either."* Neither attempt is
the answer. This document exists so the next session doesn't have to
re-derive any of this history, and — importantly — surfaces a **third,
unexplored lead** (§5) found while writing this handoff that neither
attempt this session was aware of.

Do not resume by building. Read §5 and ask the user directly before
touching code again.

## 2. Attempt 1: agent-based growth (cohesion + gravity + orthogonal snap) — REJECTED

Built fresh this session, not tied to any prior precedent:
- `PM_GrowthColumns` (`rhino/gh_growth_columns_component.py`) — point
  generator on an **idealized** uniform 27ft major-grid / 9ft
  mullion-grid, over a single small test massing polysurface.
- `PM_GrowthAgents_Major` / `PM_GrowthAgents_Mullion`
  (`rhino/gh_growth_agents_component.py`) — per-agent simulation: decaying
  upward "gravity" + cohesion toward other agents, unitized and
  axis-snapped (`force_ortho`) each step, `RigidityBias` blending toward
  pure-vertical to make major columns read more structural than mullions.
  Volumetric containment against the massing (`IsPointInside`, with a
  `CapPlanarHoles` fallback for non-solid breps).
- Module-stamping (`Center Box` + `Vector2Pt` + `Move`) at two
  thicknesses, `0.75ft` (`=3÷4`, exact match to the real site's column
  thickness) and `0.375ft` mullions.

Verified working (correct falloff at the massing top surface via
containment, correct thickness hierarchy, no errors). User's verdict,
verbatim: *"i think that made it worse... where we are now is not what i
want."*

## 3. What that rejection led to: real reference materials surfaced

The user then shared three references and asked for them to be inspected
before continuing:

- **`C:\Users\jcnor\OneDrive - SCI-Arc\2026_Summer\Thesis\Rhino\scripts\*.py`**
  and its companion **`GRID_LOGIC_AND_MODEL_ALGORITHMS.md`** (same folder
  tree as the live `FidelityGrid1.gh` document) — a real, already-built
  and **physically fabricated** pipeline: real column-grid × DTLA-grid
  collision seeds (55 of them, real survey), a canopy height-field
  falloff, and a physical pedestal (legs of real lumber hanging below a
  site model, floating by distance from a real datum, with a convex-hull
  "forced-touch" trick guaranteeing stability without flattening the
  dramatic float).
- **`modelGRIDinspo.png`** — a photograph of that built pedestal: *"a site
  model where the grid is used to create a pedestal, which grows down out
  of the site's building massing."*
- **`shared image (1).png`** ("Media as spatial organization") — the
  instructor's reference for the massing's *form language*: a dense,
  strictly orthogonal, interlocking frame of members at clearly varying
  length, crossing at multiple heights.

Exploration confirmed the OneDrive Thesis project and this repo
(MemoryMachine / "Pershing Metabolizer") are the **same site, same real
column survey**, related by a coordinate-frame offset — and that the
OneDrive project's `ORIGIN` is measurably more accurate (this repo's
`real_geometry.json`-derived `ORIGIN` silently missed the true corner
column — one of exactly 5 columns absent from the OBJ extraction).

## 4. Attempt 2: real seeds + orthogonal L-system + digital pedestal undercroft — ALSO REJECTED

Four-phase rebuild, each phase verified before moving on:

1. **Corrected the real site frame everywhere** in `FidelityGrid1.gh`
   (`PM_FacadePanelizer`/FG1, `PM_ScaffoldFrame`, `PM_PinGrid`,
   `PM_GrowthColumns`) — real `ORIGIN=(319.89,596.22)`, the real 0.4°
   column-grid drift (previously assumed 0.0°), the true boundary
   quadrilateral (previously a synthesized axis-aligned rectangle). FG1's
   `Log` now reports `col_lines=36 dtla_lines=3 seeds=55 cells=264` — an
   **exact match** to the OneDrive doc's documented real numbers.
2. **`PM_HeightField`** (`rhino/gh_height_field_component.py`) — near-
   verbatim port of `canopy_height_field.py`'s real falloff math.
3. **`PM_MassingFrame_Lsystem`** (`rhino/gh_massing_frame_lsystem_component.py`)
   — replaced a Voronoi idea (the user's own pushback: *"is there an
   algorithm that is more interesting or suitable for this project other
   than a voronoi? that's a pretty basic and overused pattern"*) with an
   **orthogonal L-system**: real seeds as branching roots, axis-
   constrained recursive branching, branch length from the real height
   field, deterministic (hash-based, reproducible) branch/no-branch
   decisions, volumetric massing containment.
4. **`PM_PedestalUndercroft`** (`rhino/gh_pedestal_undercroft_component.py`)
   — ported the OneDrive project's own `pedestal_leg_distribution.py`
   forced-touch convex-hull + distance-float logic, adapted to real feet,
   applied as legs hanging below the **digital massing's own underside**
   (not just the physical model) — per the user's explicit *"bring it
   into the digital massing"* answer.
5. **Re-seeded `PM_GrowthAgents_Major`/`_Mullion`** from FG1's real
   `SeedPts` instead of the idealized grid, unifying the whole pipeline
   around one real data source.

Verified at every step — `gh_inspect(status)` clean throughout (18/18
components), branch counts and bounding-box extents checked numerically,
and a visual capture (with the test massing temporarily hidden, since the
L-system frame grows *inside* the solid volume by design) showed a dense,
interlocking, strictly orthogonal lattice with varying member lengths —
a real visual match to "Media as spatial organization." The pedestal
undercroft showed legs of clearly varying length hanging below the
massing, matching the photographed pedestal's read.

Despite all of that, the user's verdict: *"i dont think what we just did
is the what i want either."* No further specifics were given about what
about it is wrong before this handoff was requested.

## 5. IMPORTANT — a third, likely-relevant thread not yet explored this session

While writing this handoff, found **`HANDOFF_08012026_PROCESSING_GROWTH_ALGO_FOR_MASSING.md`**
(this repo, 3 days old — written by a *different* prior session, not
today's). It documents yet a **third** candidate answer to "what is the
grid logic," distinct from both attempts above, that neither attempt this
session was aware of:

**`C:\Users\jcnor\OneDrive - SCI-Arc\2026_Summer\Thesis\Processing\mainTk4\`**
— `agent.pde` (Processing) and `app_tk4.js` (a more complete three.js
port). An agent-based growth algorithm with:

- **`forceOrtho()`** axis-snapping — the same orthogonal-only principle
  used throughout every version of "the grid logic" across all three
  candidates, the one constant.
- **Attractor-seeking**: each agent steers toward its *nearest attractor
  point* within `maxAttractorDist`, not a generic cohesion-toward-other-
  agents force like this session's Attempt 1 used.
- **Explicit voxel-collision avoidance**: an `occupiedVoxels` set tracks
  claimed grid cells; an agent whose primary direction is blocked tries a
  horizontal dodge, then a vertical escape, then terminates — a real
  collision-resolution chain, not just a containment check.
- Originally **image-driven** (pixel-color mask + edge-detection placed
  the attractors) — that prior session's already-decided brief (per the
  user, in that session) was to **replace the image mask with footprint/
  polygon geometry** instead, and use **constant member thickness** (real
  lumber stock dimensions), not the original's texture-driven variable
  thickness.
- **Intended use, per that handoff**: grow pedestal legs **up into** the
  site's actual buildings — the reverse direction from this session's
  Attempt 2, which grew pedestal legs *down* from the massing's
  underside.

That prior session was interrupted before implementation began — an open
question about attractor-seeding strategy was left unanswered (footprint
boundary points vs. corners vs. interior grid — see that handoff's
section 1) — and, as far as either this session or that one shows, was
never picked back up. This session pursued the cohesion/gravity direction
(Attempt 1), then the Rhino/scripts real-data direction (Attempt 2)
instead, apparently without either session's context reaching the other.

**Put this in front of the user before building anything else.** Three
different sessions, three different candidate answers to "what is the
grid logic supposed to do" — it's entirely possible `mainTk4`'s
attractor-seeking + voxel-collision agent (still unbuilt, never
attempted) is the actual missing piece, or it's possible it's a fourth
wrong turn. The point is: don't guess a fourth time. Ask directly.

## 6. Current live state, `FidelityGrid1.gh`

All of the following are live in the open Grasshopper document
(`OneDrive - SCI-Arc\2026_Summer\Thesis\Rhino\grasshopper\FidelityGrid1.gh`),
`gh_inspect(status)` clean (18/18 OK), **document modified but unsaved**:

| Component | Role | Status |
|---|---|---|
| `PM_FacadePanelizer` (FG1) | Real seeds/grid, corrected constants, now also outputs `SeedPts` | Live, corrected |
| `PM_FacadeScreen`, `PM_GrowthScaffold`, `PM_ScaffoldFrame` | Earlier-session components, `PM_ScaffoldFrame` constants corrected | Live, untouched otherwise |
| `PM_PinGrid` | Repo file corrected, **not currently placed on this canvas** | Repo-only |
| `PM_GrowthColumns` | Point generator, corrected constants; `MajorPoints` now only feeds `PM_PedestalUndercroft` | Live |
| `PM_GrowthAgents_Major` / `_Mullion` | Attempt 1's agent sim, re-seeded from real `SeedPts` in Phase 4 | Live, rejected direction |
| `PM_HeightField` | Real height-field falloff | Live, verified |
| `PM_MassingFrame_Lsystem` | Orthogonal L-system massing frame | Live, verified, rejected direction |
| `PM_PedestalUndercroft` | Digital pedestal undercroft | Live, verified, rejected direction |

Repo source files (all mirror their live components):
`rhino/gh_facade_panelizer_component.py`, `gh_scaffold_frame_component.py`,
`gh_pin_grid_component.py`, `gh_growth_columns_component.py`,
`gh_growth_agents_component.py`, `gh_height_field_component.py`,
`gh_massing_frame_lsystem_component.py`,
`gh_pedestal_undercroft_component.py`. Full technical writeups:
`PershingMetabolizer_Prototype/GROWTH_COLUMNS.md` (Attempt 1),
`PershingMetabolizer_Prototype/MASSING_FRAME.md` (Attempt 2).

The real site-frame correction (§3's `ORIGIN`/rotation/boundary fix) is
**not rejected** — that part is a factual correction (traced to the more
accurate real survey), independent of which growth/massing algorithm ends
up being right, and should stay regardless of which direction is chosen
next.

## 7. Suggested opening move for the next session

1. Show the user this document, specifically §5.
2. Ask directly: does `mainTk4`'s attractor-seeking + voxel-collision
   agent match what "the grid logic" means to them, better or worse than
   either of this session's two attempts?
3. If yes — the next step is the unanswered attractor-seeding question
   from `HANDOFF_08012026...md` §1 (footprint boundary points, corners,
   or interior grid), plus deciding how it reconciles with the *real*
   seed/height-field/pedestal data this session surfaced (that prior
   handoff predates knowing the Rhino/scripts/ pipeline existed).
4. If no — ask what specifically about Attempt 2's result still isn't
   right. *"Not what I want either"* alone doesn't say which part failed:
   the L-system branching character itself, the pedestal-growing-*down*
   direction (vs. `mainTk4`'s growing-*up*-into-buildings framing), the
   real-seed density on a small test footprint, or something about the
   reference images none of the three candidate algorithms have actually
   captured yet.

Do not build a fourth version speculatively. Get the answer first.
