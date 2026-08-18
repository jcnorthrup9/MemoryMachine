# Handoff — 2026-08-01: source located for the "grow legs into the site buildings" algorithm; port not started

This handoff comes from a *different* chat session whose only job was to locate a script the user
half-remembered ("a simple three.js app I made ~2 months ago, texture input, color input"). That chat
found the source and discussed porting strategy but was told to stop and hand off here rather than
continue, since the actual porting work belongs in this project's context. No code has been written
yet — this is pure context transfer.

## 1. What the user actually wants (READ THIS FIRST)

Apply an existing agent-based growth algorithm (currently three.js/Processing, image-driven) to
**building massing/program footprints** instead of an image, to grow the structural "legs" of a
**physical pedestal model** up into the site's actual buildings. Two explicit constraints from the
user, both already decided, not open questions:

- **No image input at all.** The mask that currently comes from image pixel color needs to come from
  footprint geometry (polygons/breps) instead.
- **Constant thickness**, not the variable/texture-driven thickness the original script has. Reason
  given directly by the user: the legs are being fabricated as **physical lumber pieces for a real
  scale model**, so every grown member needs to be the same stock size. This also means whatever gets
  built needs to generalize beyond just "program massing" — the user's stated end goal is to run the
  *same* algorithm against the full site model so the pedestal legs grow up into the actual site
  buildings, not just abstract massing blocks. Don't build something that only works for one footprint
  type.

**Still open, not yet decided** — was mid-discussion when the user redirected to this handoff instead:
how attractor points should be generated from a footprint polygon now that there's no image edge-detect
to trace. Three options were on the table, no answer given yet:
1. Points resampled along the footprint's boundary curve (closest analog to what the original
   edge-detection was doing — tracing the mask outline).
2. Just the polygon's corners (sparser, more faceted-looking growth).
3. A grid of points across the interior of the roof/top face (denser, growth reaches up across the
   whole footprint, not just toward its edges).

Ask the user this directly before committing to an attractor strategy.

## 2. Where the source script actually is

`C:\Users\jcnor\OneDrive - SCI-Arc\2026_Summer\Thesis\Processing\mainTk4\`

- `agent.pde` — the original Processing agent class. **This is the canonical "grid logic"** the user
  is referring to: axis-snapped voxel walk (`forceOrtho()`), nearest-attractor seek (`targetFind()`,
  `attractorCoh()`), and a swarm-cohesion term (`aggregate()`, sums direction to nearby *other* agents'
  history within `tLength*2`) that the later three.js port replaced with explicit voxel-collision
  avoidance instead (see below). `mainTk4.pde` also contains a second, unrelated, much simpler `agent`
  class (continuous-velocity seek/steer, no grid-snapping) that appears to be dead/superseded code —
  two classes named `agent` in the same Processing sketch would not actually compile together, so
  treat `mainTk4.pde`'s inline class as noise, not a lead.
- `app_tk4.js` (the live three.js port, referenced as "mainTk4 STRIDE GROWTH" in its own header comment)
  — functionally the more complete version to port from. Key pieces, with line refs from that file:
  - `isTargetColor()` (line 296) — pixel-color mask test. **Replace with point-in-polygon** against the
    footprint.
  - `edgeCheck()` (line 310) — image edge-detection used only to place attractors. **Replace** per the
    open question in section 1.
  - `Agent.update()` (line 369) — the core per-step loop: find nearest attractor within
    `maxAttractorDist` → steer vector → `forceOrtho()` axis-snap → voxel-collision fallback chain
    (primary direction → horizontal dodge → vertical escape → terminate, lines 427–450) → stray
    mitigation (must land back inside the mask + in-bounds, lines 456–481, **swap the mask check for
    point-in-polygon**) → thickness via `lerp` on texture brightness (line 499, **delete — use a flat
    constant instead**, matching `agent.pde`'s original `baseThickness` model) → bake one oriented box
    per step (`renderVoxelSegment`, line 603).
  - `forceOrtho()` (line 515) — the axis-snap itself, ports over completely unchanged. This is the
    heart of "the grid logic."
  - `occupiedVoxels` (a `Set` of rounded-grid-coord string keys, `getGridKey()` line 560) — also ports
    over unchanged; a Python `set` of coordinate tuples does the same job inside GhPython.
  - Seeding (`regenerateSimulation()`, line 702): attractors from mask-edge pixels lofted to a fixed
    `ceiling` height; agents from a strided (`step`) grid scan filtered by the mask. **Replace the pixel
    scans with a 2D point lattice clipped to each footprint polygon.**

Sibling folders in the same `Processing/` directory (`mainTk` through `mainTk8`) are earlier iterations
of the same lineage — not needed for the port, but there if any Processing-side behavior needs
cross-checking. `mainTk7` in particular used a `colorBlocks.jpg` "channel matrix" as its mask, an even
more literal precursor to the image-masking approach that's now being removed entirely.

## 3. One thing worth checking before starting, not yet confirmed

`HANDOFF_07242026_CANOPY_GRID_SYNC_HIFI.md` (this repo, section 1) documents a *previous* session where
the user referenced "the grid logic ... from a processing script ... applied to the site in 2D," which
that session traced to `logic/site_grid.py`'s `build_site_grid()` (a rotatable cell-size/rotation
overlay, currently driving canopy panel faceting via `logic/canopy_engine.py`). It is **not confirmed**
whether that's the same "processing script" lineage as `mainTk4`'s agent-based growth algorithm above,
or a completely unrelated grid utility that happens to share the description. Worth a quick check with
the user — if they're the same source, there may already be partial infrastructure in this repo
(`build_site_grid()`) that's relevant to the footprint-grid-seeding step in section 2, rather than
needing it built from scratch.

## 4. Suggested next step

Ask the user the open attractor-strategy question from section 1, then write a GhPython component
(or a component pair: one for seeding/attractors, one for the per-agent growth loop) implementing the
`app_tk4.js` `Agent.update()` logic against footprint polygons instead of pixels, with thickness fixed
constant. Bake output as oriented boxes sized to the constant thickness, matching real lumber stock
dimensions the user will specify.
