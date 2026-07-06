Handoff to Gemini: Sloped-Floor Helix Topology Question
=========================================================
*2026-07-05. Claude (working in this session via Rhino MCP against `PershingInterventionMidterm.3dm`) needs one clarification before implementing the sloped-floor helix slab request before building anything.*

## Context: what's already been done this session

- Fixed a real bug in `terracing_engine.py`: general canyon excavation was capped using `entrance_base_depth_ft` (63.29ft, the entrance/tunnel's own real depth) instead of the real column height (30ft). Now a separate `max_canyon_depth_ft` parameter, derived from `real_geometry["column_height_ft"]`, caps it correctly. Verified working end-to-end (terracing engine, vector_export, Blender cockpit).
- Corrected `real_geometry.json`'s `secondary_entrance_anchor` using a live Rhino MCP query (old value was measuring a different, deeper object than intended).
- Confirmed via live Rhino MCP query: `STRUC__Slabs::L1/L2/L3` exist and sit at 9.75-10.75 / 19.75-20.75 / 29.75-30.75 ft below grade (grade = real column top, Z=3.728 in the raw Rhino file) — matching the assumed 0/-10/-20/-30 scheme almost exactly. **These are flat, ~1ft-thick plates** (confirmed directly from bounding boxes) — user has since confirmed this was a known, deliberate simplification, not an error.
- Confirmed via live Rhino MCP query: `CIRC__Ramps` (4 objects) are 2 circular spiral cores (~54ft outer radius measured, matching a separate handoff's "outer radius 54ft, inner radius 27ft" spec) — these are the *existing* vertical circulation.
- Built and verified (live, via Rhino MCP `create_object`/`pipe`) the twin running-tunnel cylinders + station box per a separate handoff: 18'10" diameter tubes, invert at exactly -55ft, station box 65×600×30ft spanning -30 to -60ft (top ties into Subfloor 3). User has since Boolean'd these into the surrounding mass in Rhino directly.
- Attempted to automate SVG/OBJ export of the pipeline's saved views (`Plan`, `longElevation`, `shortElevation`, `axoNW`, `axoSE`) via Rhino MCP scripting. Found along the way: the *existing* SVG exports were done via "Export Selected" onto an 11×17 sheet — a non-uniform "fit to page" scale, which explains an earlier-found bug (the plan-view SVG's derived site dimensions were wrong by *different* ratios on each axis: 5.5x vs 11.8x too small — the signature of anisotropic page-fit scaling, not a uniform one). Recommended re-exporting at real/uniform scale instead. Attempted `Make2D` via RhinoScript to build a from-scratch export path at 1:1 scale; **this got stuck mid-command in the live Rhino session** (user had to cancel manually) — not resolved yet, paused in favor of the slab-helix work below per user request.

## The new ask: sloped-floor helix slabs

Latest handoff (verbatim, already given to Claude) requests replacing the flat `STRUC__Slabs::L1/L2/L3` plates with a continuous sloped-floor helix:
- Long aisles (north-south, parallel to Hill/Olive St, along the 600ft axis): continuous **3.5% grade**.
- End trays (east-west, near 5th/6th St, ~350ft axis): **flat, 0% grade** landings where the ramp switches back.
- Deconstruct by the real 27×27ft column bay grid; warp longitudinal bay boundaries along the 3.5% line; stitch seamlessly to the flat end trays.
- Confirmed by user: this replaces the function of the circular ramp cores (`CIRC__Ramps`) — the continuous slope *is* the vertical circulation once built; the cores likely become redundant (not deleted yet, pending this).
- Confirmed by user: the current flat L1/L2/L3 slabs were a known, deliberate simplification — this is the right time to correct them, not a factual dispute.

## The specific ambiguity blocking implementation

A single continuous 3.5% ramp covering the *full* 30ft drop (grade to Subfloor 3) would need ~857ft of horizontal run (30 ÷ 0.035) — longer than the 600ft site length even before any switchback. But the handoff's own phrasing ("drops the geometry dynamically **between floor levels**") reads like each individual 10ft level-to-level transition (grade→L1, L1→L2, L2→L3) gets its *own* continuous ramp run — 10 ÷ 0.035 ≈ 286ft, which comfortably fits within the 600ft aisle length even with margin for the flat end-tray landings.

**Question for Gemini:** which topology is actually intended?

1. **Three separate ramp decks**, one per level transition (grade→L1, L1→L2, L2→L3), each its own continuous 3.5% run over ~286ft, connecting to flat landing trays at both the 5th St and 6th St ends. (This is Claude's best-guess interpretation of the handoff's own wording, and the one that fits the stated numbers cleanly.)
2. **One continuous ramp system** spanning the full 30ft, switching back multiple times along the 600ft length to fit the required ~857ft of total run.
3. Something else — if so, please describe the actual intended topology explicitly, including:
   - How many parallel long aisles run side-by-side across the 354ft width (e.g., one "down" aisle + one "up" aisle, or more)?
   - Where exactly along the 600ft length do the flat end-tray landings begin/end (what fraction of the 600ft is ramp vs. flat landing)?
   - Does each of the 3 existing level slabs (L1/L2/L3) get fully replaced by a warped deck, or do some stay as flat reference datums with only certain bays warped?

Once this is resolved, Claude will deconstruct the slabs by the real 27ft column bay grid (already verified in the live model) and build the warped surfaces via Rhino MCP, the same way the tunnel cylinders were verified against real numbers before being committed to the file.
