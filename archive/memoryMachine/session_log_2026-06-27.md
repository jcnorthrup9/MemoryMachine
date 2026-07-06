# Memory Machine — Session Log
**Date:** 2026-06-27
**Topic:** Pershing Metabolizer — real-data bridging + WebGL prototype

---

## Summary

This session built the **Urban Interference Solver** pipeline for the Pershing Square midterm, progressively replaced every placeholder data layer with real measurements pulled from the user's Rhino model and local research, then built a standalone Three.js WebGL prototype ("The Pershing Metabolizer") visualizing the resulting excavation logic across three development phases.

---

## Files Created

### `urban_interference_solver.py` (project root) — NEW FILE
Core Python pipeline. 30×30 analytical grid over the real Pershing Square site.

- **Step 1:** `init_directory_schema()` — bootstraps `/data`, `/archive`, `/outputs`.
- **Step 2:** `MemoryMachineEngine` class — numpy-backed grid, ingest layers for building heights, transit flux, amenity deficits, memory overlay.
- **Step 3:** Interference loop — `intervention_score = memory_volatility*0.4 + asset_pressure_deficit*0.6`. Excavation solver checks each cell against `INTERVENTION_THRESHOLD = 0.75`, real garage column clearance, and Metro proximity.
- **Step 4:** Auto-exports `outputs/midterm_punctures.csv` (coordinates, puncture type, footprint, excavation depth, volume).

### `normalize_amenity_data.py` (project root) — NEW FILE
Converts the real hospitality/amenity venue list (transcribed from the user's Obsidian note `PershingContext.md`) into `data/amenity_deficits.json`, replacing the placeholder. Re-run any time the source venue list changes.

### `PershingMetabolizer_Prototype/index.html` — NEW FILE
Standalone Three.js WebGL prototype (CDN import map, no build step). 30×30 primary grid of real 27ft bays, each subdivided 3×3 into 9ft voxels. Stepped excavation driven by distance-to-Metro and deficit hotspots, heat-mapped amber→violet, real garage column wireframe + floor plate, glowing green Metro tube, 3-phase HTML toggle panel.

### `data/PershingMetabolizer/AMENITY_DEFICITS_GUIDE.md` — NEW FILE
Schema/handoff doc explaining what `amenity_deficits.json` needs and how to supply raw venue data instead of pre-computed density scores.

---

## Real Data Bridged In (replacing placeholders)

| Layer | Source | Real value derived |
|---|---|---|
| Garage column grid | `data/PershingMetabolizer/pershingRhinoPlanView.svg` (`STRUC__Columns`/`STRUC__Slabs` layers) | 274 real columns, on-center spacing confirmed by user at **27'-0"** |
| Real site dimensions | Same plan SVG, calibrated by the 27ft spacing | **~354ft × 602ft** — matches the actual Pershing Square block |
| Garage depth | `pershingRhinoLongElevation.svg` + `pershingRhinoShortElevation.svg` | **30.00 ft**, cross-validated independently from both elevations (0.00ft spread) |
| Grid orientation | User-confirmed against the Rhino Top view | x: 0=west(Olive St)→29=east(Hill St); y: 0=south(6th St)→29=north(5th St) |
| Perimeter building heights | `data/PershingMetabolizer/BuildingHeights.txt` (user-transcribed Rhino/Google measurements) | 9 real buildings + addresses (see `data/building_heights.json`) |
| Hospitality/amenity venues | `D:\boxy_player\obsidian\boxy_player\PershingContext.md` | 6 real venues (Biltmore, Nomad/Perla, Pershing Sq Building retail, Subway, Grand Central Market, Bottega Louie) |
| Metro node position | `data/pershing_site_context.json` (`transit_pavilion`), normalized onto the grid | Cell `(3, 12)` |

---

## Bugs Found & Fixed

| Bug | Cause | Fix |
|---|---|---|
| Metro node placed on wrong side of site | `METRO_NODE_CELL` derived from a different file's coordinate frame than the SVG-plan grid, with an unverified north/south handedness assumption | Confirmed orientation with user (5th St = top, Hill St = right), corrected `(3,18)` → `(3,12)`; also fixed `perimeter_north`/`perimeter_south` placeholder swap |
| Biltmore Hotel height implausible (52ft) | Source measurement likely caught a wing/parapet, not the main tower | Corrected to 170ft per user |
| WebGL: Phase 1 excavated ~32% of the site instead of an isolated band | `TRANSIT_FALLOFF_FT`/hotspot radii too large relative to site scale | Tightened to bay-relative units (`BAY_FT * 1.4`, etc.) |
| WebGL: Phase 2 showed *fewer* active cells than Phase 1 | Score formula averaged transit+deficit influence instead of adding — diluted Phase 1's transit cuts | Made scoring additive so phases monotonically grow (795 → 907 → 1089 active voxels) |
| WebGL: deficit scoops near the shallow Metro portal end were clamped too shallow | Metro-depth floor used the *locally interpolated* tunnel depth for all excavation, including cells far from the line | Blend the floor toward the global `METRO_DEPTH_FT` where transit influence is low |
| WebGL: every voxel rendered black regardless of computed color | `InstancedMesh.instanceColor` is silently ignored unless the base geometry also has its own per-vertex `color` attribute | Added a white `color` attribute to `voxelGeom` |

---

## Known Caveats (carry forward)

- `INTERVENTION_THRESHOLD = 0.75` in the Python solver still doesn't fire on current real data (max observed score ~0.43) — a calibration question, not a data gap, now that all four layers (columns, depth, buildings, amenity) are real.
- **Future Solutions Media** (365.5ft, `data/building_heights.json`) was flagged by the user as possibly inaccurate (~2x actual) — not yet corrected, unlike the Biltmore fix.
- Off-site amenity venues (Grand Central Market, Bottega Louie) use directional extrapolation beyond the grid edges, not precise geocoding — fine for relative influence weighting, not for survey accuracy.
- `STRUCTURAL_BAY_SPACING`/garage column bay assumption is now real (27ft, confirmed), but the WebGL prototype's Metro tunnel depth (70ft) and exact deficit-hotspot weighting are still diagrammatic, not surveyed.
- Building/amenity left-right ordering along each street frontage uses a DTLA address-number heuristic (lower number = closer to the Spring/Main baseline), not precise geocoding.

---

## How to Run

- **Python pipeline:** `python urban_interference_solver.py` from the project root (regenerates `outputs/midterm_punctures.csv`).
- **Re-normalize amenity data:** `python normalize_amenity_data.py` after editing `RAW_VENUES` to match `PershingContext.md`.
- **WebGL prototype:** open `PershingMetabolizer_Prototype/index.html` directly in a browser (double-click, or `start` on Windows). Requires internet on first load (Three.js via CDN import map); no server or build step needed.
