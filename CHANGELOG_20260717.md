# Changelog — 2026-07-17

Session covering the Canopy Engine redesign, several rounds of program-placement correlation logic, a program-boxes rework, and cleanup. Chronological order.

Note: a concurrent session working in this same directory committed separately (`bab95f4`, diagram-generator/Gemini/ChromaDB fixes) while this session was in progress. Since both sessions edited some of the same files on disk, a chunk of this session's own work (parts of `logic/pershing_api.py`, `frontend/src/App.jsx`, `frontend/src/api.js`, `ParamPanel.jsx`, `PrecedentRemixerPanel.jsx`, `requirements.txt`) ended up captured in that commit instead of this one — it's real and present in history, just under a commit message that doesn't mention it. This changelog covers the full scope of this session's work regardless of which commit it physically landed in.

## 1. Windows ghost-listener port bug

Diagnosed a recurring stale-TCP-listener issue where a killed `uvicorn --reload` process could leave a socket answering requests with pre-restart data. Confirmed fixed by a Windows reboot; `frontend/vite.config.js`'s dev proxy reverted from its temporary port hop back to `:8000` and consolidated into a single shared `API_PROXY` object (also used by `preview.proxy`, which previously had no proxy config at all).

## 2. 2D diagram tool fixes

Root-caused `diagram_tool`'s SVG export cropping most content to a hardcoded, stale viewBox in `main.js` — fixed by keeping the live dynamic viewBox. Restored `urban_design_guidelines.md` after finding it had been silently overwritten, which had broken `GuidelineManager.parse()`.

## 3. Canopy Engine full redesign (`logic/canopy_engine.py`, `terracing_engine.py`, `logic/pershing_api.py`, `frontend/src/components/Viewport.jsx`, `blender_cockpit.py`)

Rebuilt from a flat 27ft rectilinear beam grid into an organic, doubly-curved panelized roof: painted `canopy_mask` now controls WHERE the canopy exists (a footprint, thresholded at 0.05), while wave/sculpt/dip sliders control its shape unconditionally wherever a panel exists. Individually-oriented panels (real surface normals) plus branching support columns that tie back to real structural columns when one's within range. Moved to an explicit "Generate Canopy" action (mirroring `grow_network()`'s pattern) instead of running inside the live 200ms-debounced rebuild loop.

Verified end-to-end this session: isolated backend test (zero panels when unpainted; real height/normal variation and full footprint fidelity when painted), and live UI test (paint → auto-bake → Generate Canopy → rendered in viewport). Also diagnosed that an apparent "painting doesn't do anything" report was caused by my own verification scripts overwriting the shared live paint state on the dev server mid-session — not a real bug; confirmed by re-testing with a visual before/after comparison showing the footprint correctly tracking each new paint location.

## 4. UI/cleanup batch

Removed "Ask the Metabolist." Finished wiring the Precedent Remixer. Merged 8 separate paint buttons plus the standalone Diagram Input panel into one unified Paint dialog (`frontend/src/components/PaintOverlay.jsx`) with a source-tab switch. Extended program-zone box massing to all program categories (previously only `enrichment_civic`/`health_care`).

## 5. Program Boxes semantic fix

Corrected "Program Boxes" from an independently-stackable layer into a mode-switch on the same Program Zones data — the toggle swaps flat footprint plates for extruded massing, it doesn't add a second layer on top.

## 6. Program Boxes per-bay extrusion + real level height

Replaced one bounding-box-per-zone (which misrepresented any non-contiguous claimed shape) with one box per claimed bay, matching the real flat-plane footprint exactly. Extrusion height now uses `REAL_LEVEL_HEIGHT_FT = 10.0`, grounded in `real_geometry.json`'s uniform 10ft real floor-slab spacing, with double-height support for programs that need it (`public_gym`, `skatepark` — flagged in `data/program_requirements.json`). Added per-program box coloring (`Viewport.jsx`'s `PROGRAM_COLOR` map) — boxes previously all shared one uniform grey `building_mass` kind color.

## 7. Program-placement correlation logic (`logic/program_placement.py`, `logic/pershing_api.py`)

Wired real signals into bay-scoring that previously had no effect on placement:
- Painted "trees" (shade) correlated against each program's `shade_target_pct`.
- Diagram-derived major/minor attractor points (previously extracted but never consumed) now pull/repel placement per category (`CATEGORY_ATTRACTOR_AFFINITY`).
- New `AttractorMarkers` viewport layer to visualize them.

## 8. Restrooms (`data/program_requirements.json`, `logic/program_placement.py`)

Added `restrooms_metro` and `restrooms_recreation`, sized per user-supplied IPC/ADA reference data (not from the real neighborhood-deficit CSV, which has no restroom line item — explicitly labeled as an estimate). Placement uses "host attachment": a hard requirement that each restroom's bay be 4-connected-adjacent to a real host zone's footprint (nearest-to-entrance program for `restrooms_metro`, largest recreation-category zone for `restrooms_recreation`), not just a soft distance pull — so each reads as a real annex rather than a floating box.

## 9. Demand-driven excavation (`terracing_engine.py`, `logic/pershing_api.py`)

Root-caused "programming doesn't reach below-grade levels": excavation depth was driven only by metro-entrance proximity and manual canyon painting, with real neighborhood program-deficit data (`deficit_influence`, already computed) never touching the depth formula at all. Folded `deficit_influence` into `TerracingEngine._effective_influence()` at co-equal weight with transit proximity. Added a demand-vs-capacity ceiling scale, sourced to a real standard (ASPO Planning Advisory Service Report No. 194, 1965: "30 to 50 per cent of park and recreation land should be set aside for active recreation") rather than an arbitrary fraction. Raised the `canyon_depth` default so the real -20/-30ft slab levels are reachable out of the box.

Verified: excavated footprint grew from 2/286 to 27/286 bays; depth now reaches -20ft where it previously capped at -10ft; program zones now genuinely spread across 4 distinct real elevations instead of only grade.

## 10. Removed manual "Add Building" feature

Removed the manual box-placement UI (`ParamPanel.jsx`) and its backend wiring (`RebuildParams.buildings`, `manual_buildings` in `rebuild()`) — fully redundant with Program Boxes, which produces the same massing automatically from real program placement. Confirmed safe: no saved/archived builds had any data in this field, and the backend silently ignores the now-unused key on old snapshots.

## 11. PROGRAMS legend collapse toggle

The 3D viewport's program-color legend (`ProgramLegend` in `Viewport.jsx`) can now be collapsed to a small header bar and re-expanded, so it doesn't permanently obstruct the view.
