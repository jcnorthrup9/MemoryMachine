# Program Placement on the Structural Bay Grid — Code Overview

2026-07-12. Written to track what this feature touches — both code that
already existed and was just investigated, and the new code this pass adds.
Not a permanent spec; a snapshot for reorienting later without re-reading
everything from scratch.

## Why this exists

The ask: place site programming (soccer field, gym, community garden,
etc.) onto Pershing Metabolizer's site, informed by amenity-deficit data,
using the **27ft parking-garage structural bay grid** — not the finer 9ft
voxel grid the terracing pipeline already uses — to decide where and how
much square footage to give each program. The starting point was a
Grasshopper definition, `ProgramDiagram.gh`, in
`C:\Users\bletch\OneDrive - SCI-Arc\2026_3GB_Spring\SP26-Studio\Grasshopper\`.

## Existing code investigated

### `ProgramDiagram.gh` itself: a dead end, but its companion Python isn't

The `.gh` file is a modern Grasshopper archive — internally a compressed
binary blob, high-entropy from byte 0, no readable strings, no extractable
component logic. Nothing in it can be read or ported directly.

The real logic lives alongside it as two zip files in the same folder:
`ProgramDeveloper.zip` (older) and `pythonProjects.zip` (newer, containing
`EllipseAgent.py` / `ProgramDeveloperEllipseBoundary.py`). That pipeline:
a rough program list → OpenAI (`gpt-5-mini`) expansion into a detailed
floor-by-floor table → an agent-based simulation (boids-style separation/
cohesion, elliptical footprints, boundary-avoidance vectors, fixed-core
anchoring, adjacency rules like "toilets near fire stairs") that packs the
program blocks spatially → a text file handed back to Grasshopper for
geometry generation. It's a **continuous-space physics simulation**, built
for a retail-store program with a smooth site boundary and a couple of
fixed circulation cores — a poor fit for a discrete 27ft grid, so this pass
does not port it. What *is* reused is the underlying idea: priority-ordered
placement with adjacency rules, adapted to a greedy grid algorithm instead
(see `logic/program_placement.py` below).

### `amenity_deficit.py` and the placeholder-vs-real-data state

`amenity_deficit.py` loads spatial deficit *hotspots* (`x_frac, y_frac,
strength, radius_ft`) from a CSV in `data/amenity_survey/` — but no such
CSV exists yet on this machine, so the live pipeline still runs on
`terracing_engine.py`'s 2-point `DEFAULT_DEFICIT_HOTSPOTS` placeholder.
This is a different, older data channel from the one this feature actually
needed: it's spatial-only (a location + strength), with no category
(no "which program type" attached), and no notion of *how much* square
footage to build. The `andres/` needs-report data (below) fills the gap
this channel can't.

### The two grid representations in `terracing_engine.py`

- **Voxel grid** (`TerracingEngine`): dense, 9ft cells, `nx × nz` (40×67 at
  this site), every cell has a real `Voxel` object with
  `transit_influence`/`deficit_influence`/mask flags/`z_ft`/`typology`.
  This is what `rebuild()` already returns to the frontend.
- **Structural bay grid**: 27ft cells (`STRUCTURAL_BAY_FT = 3 ×` the 9ft
  voxel size — the same relationship `circulation_network.py` calls
  `BUCKET_VOXELS = 3`). Before this pass, this only existed as a private,
  on-demand, **sparse** dict inside `StructuralFramingEngine._column_grid()`
  — built solely so framing code could look up "is there a column at bay
  (gx±1, gy)" for strut/X-brace adjacency, never cached, never exposed via
  the API. Only `NX_BAYS` (13) existed anywhere as a scalar (UI slider
  bounds); there was no `NZ_BAYS` at all.

This feature needed a *dense*, reusable, whole-site version of the bay
grid — hence `build_bay_grid()` (new code, below). `_column_grid()` itself
was left untouched: it returns raw column dicts for framing math that
still needs them, a different shape/purpose than the new dense `BayCell`
grid, and refactoring it carried real regression risk for no benefit to
this feature.

### Disconnected legacy scoring systems (not reused)

- `urban_interference_solver.py`: a 30×30 grid scorer, only used by the
  standalone `generate_prototype_data.py` script — not wired into the live
  app (`app.py`/`logic/pershing_api.py`). Its `solve_punctures()` scores
  cells and computes candidate volumes but never actually matches a cell
  against a program's `target_sf`, despite `program_requirements.json`'s
  own `_meta` claiming that's what it's for.
- `logic/urban_engine.py` / `logic/ai_synthesizer.py`: a wholly separate
  2D "collage" system — an LLM assigns named layers to one of 9 cardinal
  zones on a flat bounding box. No relationship to either grid in
  `terracing_engine.py`. Legacy, still wired into `app.py`'s older
  `/api/generate` route, unrelated to the Pershing Metabolizer pipeline.

Neither system does what this feature needed (allocate program square
footage onto grid cells), so neither was extended — this pass adds a new,
purpose-built module instead (`logic/program_placement.py`).

### The two live design-intent ingestion channels (why this matters for placement)

Two channels already exist and converge on the same signal:
1. **Freehand paint canvas** (`PaintOverlay.jsx`) — the designer paints
   directly; the browser samples the canvas into 6 grids client-side and
   `POST`s to `bake()`.
2. **Legacy diagram ingestion** (`ingest_legacy_diagram.py` +
   `logic/legacy_diagram_bridge.py`, "Diagram Input" mode) — converts an
   old color-coded diagram export into the *same* 6-grid shape via pixel
   color segmentation (green→greenscape, blue→water, gray→hardscape,
   tan→shade), previews it, then commits through that same `bake()`
   endpoint. It's an alternate *source* for the same signal, not a
   separate pipeline.

Both populate `SKETCH_WEIGHTS`/canyon, `HARDSCAPE_MASK`, `WATER_MASK`,
`SHADE_MASK`, `GREENSCAPE_MASK`, `AMENITY_RESTING_MASK` — module globals in
`logic/pershing_api.py`, persisted to `outputs/cockpit/web_paint_state.json`.
Before this pass, `AMENITY_RESTING_MASK`'s only consumer was
`terracing_engine.py`'s typology tagger: `is_greenscape AND
is_amenity_resting` → tag a voxel `"SANCTUARY"` — a fine-grained (9ft)
decorative surface-typology classification for asset selection (benches,
seating), **not** a program-block allocator. Nothing read any of these
masks at bay-grid scale. This pass's placement engine is the first thing
to do that (see below) — it's how a designer's paint strokes or an
imported diagram actually influence where a soccer field or gym ends up,
rather than that intent only affecting decorative asset choice.

## New code this pass adds

### `data/amenityData/amenity_needs.csv` + `program_needs.py`

The user pointed to `data/amenityData/andres/` — 11 screenshots that turn
out to be one continuous scroll capture of a site-specific "Amenity Needs
Report": neighborhood demographics, per-category need level (NEEDED /
Suggested / Optional), and suggested square footage per program item. This
data was transcribed by hand (read via the Read tool, not OCR software — a
second manual diff against the screenshots before trusting the numbers
further is a standing to-do) into `amenity_needs.csv`
(`category, program_item, need_level, target_sf, notes`).

`program_needs.py` (repo root, same location/pattern as
`amenity_deficit.py`/`foot_traffic.py`) loads that CSV into structured
records. It's a documentation/reconciliation aid — the actual source of
truth `logic/program_placement.py` reads from is
`data/program_requirements.json`, reconciled against this CSV (see next).

### `data/program_requirements.json` reconciliation

The existing file already had 10 programs whose `target_sf` values matched
the needs-report numbers exactly — strong evidence it was already seeded
from the same report at some point, just missing a priority signal. This
pass added: a `need_level` field (NEEDED/Suggested/Optional) on every
entry; two new Health Care items (Individual Practice Office, Veterinary —
both Optional); three new Outdoor items (Playground, Picnic/Grill Site,
Workout Equipment) that existed in the needs report but had no program
entry yet. No entry was added for Fresh Food — the report assessed it as
Optional with 0 target_sf ("already served nearby"), so there's nothing to
place.

### `terracing_engine.py`: `BayCell`, `build_bay_grid()`, `voxel_attr_grid()`, `aggregate_grid_to_bays()`

- `build_bay_grid(real_geometry)` — the new dense, reusable bay grid: every
  `(gx, gy)` bay in the site gets a `BayCell` (world center, `column_id` if
  a real column rounds into it, `is_buildable`). Also computes the
  previously-nonexistent `nz_bays` alongside `nx_bays`.
- `voxel_attr_grid()` / `aggregate_grid_to_bays()` — generic helpers to
  pull a voxel-resolution grid (a painted mask, or a `Voxel` attribute like
  `transit_influence`) down to bay resolution (3×3 voxels average into one
  bay, matching `STRUCTURAL_BAY_FT / voxel_ft == 3`).

**Real-data surprise**: 282 of this site's 286 bays contain at least one
real column (`is_buildable = False`). Treating column occupancy as a hard
placement exclusion would leave almost nowhere to place anything — so
`is_buildable`/`column_id` are kept as descriptive metadata, and
`logic/program_placement.py` only treats it as a *soft* penalty, not an
exclusion (real programs like a gym or soccer field routinely span a
column grid anyway).

### `logic/pershing_api.py`: `get_bay_grid()`, `get_program_zones()` + routes

- `get_bay_grid()` — builds the bay grid, aggregates the four live masks
  (`GREENSCAPE_MASK`/`HARDSCAPE_MASK`/`AMENITY_RESTING_MASK`/`WATER_MASK`,
  the **primary** placement signal — whatever the designer actually
  painted or imported) plus `transit_influence`/`deficit_influence` (the
  **secondary** tie-breaker signal, used when a region has no painted/
  imported intent yet) to bay resolution, and returns both per bay. Uses
  default `RebuildParams()` — the primary signal doesn't depend on slider
  state, and the tie-breaker only needs to be roughly current.
  New route: `GET /api/pershing/bay-grid`.
- `get_program_zones()` — runs the placement engine (below) against that
  bay grid and the reconciled program list.
  New route: `GET /api/pershing/program-zones`.

### `logic/program_placement.py` — the placement engine itself

Not a port of `EllipseAgent.py`'s continuous simulation — a purpose-built
**greedy region-growing / bin-packing** algorithm for the discrete bay
grid:

1. `load_programs()` filters `program_requirements.json` to NEEDED +
   Suggested by default (Optional/Health Care excluded unless asked for),
   sorted NEEDED → Suggested → Optional, then largest `target_sf` first
   within a tier (place the biggest asks while the most contiguous open
   area is still available).
2. `place_programs()`: per program, score every unclaimed bay — primary
   weight on the category-matched mask (green_space → greenscape fraction,
   sports_recreation/outdoor → hardscape fraction), a general
   amenity_resting bonus across all categories, a hard exclusion for
   majority-water bays, a soft penalty for column-occupied bays, the
   transit/deficit tie-breaker at much lower weight, and one adjacency rule
   ported from `EllipseAgent.py`'s *concept* (not its code): enrichment_civic
   programs (study rooms, music practice) penalized near high-transit
   bays, since those want to be quiet.
3. Seed at the best-scoring bay, then greedily grow into the best-scoring
   4-connected unclaimed neighbor until cumulative area meets `target_sf`
   or no valid neighbor remains (partial fulfillment recorded, not an
   error — confirmed in testing: Volleyball Court, placed after several
   much larger programs already claimed the best contiguous space, only
   achieved 1,458 of its 4,500 target sf).

Verified directly against the real site: all NEEDED/Suggested programs
placed in the expected priority order, 201 of 286 bays claimed, one
partial-fulfillment case as described above — see the plan file's
Verification section for the exact commands run.

### Frontend: `api.js`, `App.jsx`, `Viewport.jsx`

- `api.js`: `getProgramZones()`, same fetch-wrapper pattern as `getConfig()`.
- `App.jsx`: fetches program zones once on load (alongside config),
  stores in state, passes down to `Viewport`. Deliberately *not* re-fetched
  after every `bake()`/`rebuild()` yet — that's a natural follow-up once
  "does the pipeline work end-to-end" is confirmed, not done in this pass.
- `Viewport.jsx`: new `ProgramZones` component, same
  instancedMesh-per-group technique as the existing `CategoryGroundCap`
  (used for greenscape/circulation ground caps), just keyed on bay `(gx,
  gy)` at `STRUCTURAL_BAY_FT` resolution instead of voxel resolution — one
  translucent colored footprint per claimed bay, one billboard `Text` label
  per program at its bay-cluster centroid, marked "(partial)" when a
  program didn't reach its target. Placeholder solid colors per category
  (green_space/sports_recreation/enrichment_civic/outdoor/health_care),
  same "cheap now, swap for real assets later" posture the rest of the
  pipeline already uses.
