# Handoff — Diagram Generator Fixes & Precedent Remixer Build (2026-07-17)

## Context

Started from a report that "the diagram generator" only ever produced Pershing Square grass, ignored the other precedent parks, and ignored the Recreation & Parks guideline percentages. That turned into a full-day pass across three separate apps that all share backend code, plus a real feature build (empty-prompt random remix + amenity-driven program placement) in the live Metabolizer app.

Three distinct apps got touched, and clearing up which is which was itself half the work:

| Port | App | Role |
|---|---|---|
| 8000 | root `app.py` | Legacy "Digital Palimpsest" UI at `/`, **and** hosts all `/api/pershing/*` routes the real app depends on (same process) |
| 5173 | React/Vite (`frontend/`) | The real Metabolizer app — this is the one to actually use |
| 8006 | `diagram_tool/` | Standalone manual 2D layer-stacking tool (no AI, by design) |
| 8003 | — | Dead. Old address for diagram_tool before a 2026-07-14 port move to 8006. Ignore. |

## 1. Diagnosis

- `diagram_tool`'s Zonal Constraints HUD (`diagram_tool/static/js/main.js`) read `data.guidelines` from `/api/guidelines`, but the endpoint actually nests it under `data.data.guidelines` — the HUD was silently showing hardcoded JS defaults, never the real values from `urban_design_guidelines.md`. Same bug existed in the root app's copy of the same code (`static/main.js`).
- The AI generator (`logic/ai_synthesizer.py`) built its "available sites" list from a stale, deprecated folder (`data/ParkSVG/`, superseded 2026-07-14) instead of the real 5-site `PrecedentSVG/` library `remix_layers()` actually validates against — most non-Pershing picks silently collapsed back to Pershing Square + grass.
- `logic/urban_engine.py`'s `LAYER_SITE_AFFINITY` hardcoded HARDSCAPE→Schouwburgplein and AMPHITHEATRE→ZaryadyePark regardless of the AI's pick, even though HARDSCAPE is real in 3 of 5 sites and AMPHITHEATRE in 4 of 5 (confirmed via direct SVG inspection) — collapsed site variety.
- Gemini was coded as the primary AI path but never actually ran — the environment serving the app has no `google-genai` installed, so every call silently fell through to local Ollama. Removed the dead path per user request; Ollama is now the only path, explicit and correct instead of an accidental fallback.
- ChromaDB (the "historical reviews" RAG context) was gated behind that same broken Gemini import in `app.py`, so the real 4001-document review corpus was never actually queried. Decoupled the gate; then found the *installed* chromadb version couldn't read the existing on-disk index (stale/incompatible format) — backed up all 4001 docs, verified the backup, rebuilt the index clean, confirmed real semantic search results.

## 2. Root app (`app.py` / `logic/ai_synthesizer.py` / `logic/urban_engine.py`) fixes

- Repointed `generate_spatial_seed()`'s site list at the real `PrecedentSVG/` folder.
- Removed the Gemini branch from `query_ai()`; Ollama-only now, temperature bumped 0.7→1.0 for more sampling variety, added a "don't repeat yourself" rule to the system prompt, shuffled the site/layer lists fed to the prompt each call.
- Replaced `LAYER_SITE_AFFINITY`'s single-site hardcodes with real per-layer site membership (`LAYER_SITE_MEMBERSHIP`), only overriding the AI's/random pick's site when it's actually invalid for that layer, chosen randomly among valid alternatives otherwise.
- Decoupled ChromaDB init from the Gemini import gate in `app.py`; rebuilt its index from a verified backup.
- Removed `apply_zonal_grid()` — confirmed dead code (never called, and broken field names even if it were).
- Verified live: repeated identical-prompt calls now produce genuinely different site/layer layouts; a single generation now regularly spans 3-5 of the 5 real sites.

## 3. Precedent Remixer — empty-prompt random remix + amenity-driven placement

Found the real "copy of the old diagram generator ported into the Metabolizer" the user was recalling: `frontend/src/components/PrecedentRemixerPanel.jsx` + `remix_precedent()` in `logic/pershing_api.py`, reusing the same `generate_spatial_seed()`/`remix_layers()` functions fixed above. Built out four pieces on top of it:

1. **Empty-prompt → random remix.** `generate_spatial_seed()`'s old "algorithmic safety net" fallback loop was extracted into a standalone `random_spatial_seed()` (`logic/ai_synthesizer.py`) — no AI/network call, directly callable. Generate button now reads "Random Remix" when the prompt box is empty and actually does something instead of no-op'ing.
2. **Recreation & Parks guideline weighting.** Category selection (SOFT/HARD/PROG/BLUE) used to be uniform-random; now weighted by each category's target-percentage midpoint from `urban_design_guidelines.md`. Verified over 500 runs: picks tracked the guideline midpoints within a few points (e.g. HARD 45.4% picked vs. 50% target).
3. **Fixed a false "these layers don't exist" bug.** `MAJOR_ATTRACTORS`/`MINOR_ATTRACTORS` were being silently aliased away to a generic layer based on a comment claiming they weren't real — false, confirmed present in 4 of 5 precedent SVGs. Both the AI and random paths now genuinely pick them.
4. **Amenities now actually drive 3D program placement.** Added `extract_attractor_points_from_composed_layers()` (`ingest_diagram_svg.py`), mirroring the existing multi-site rasterization pipeline but pulling point-marker centroids instead of area fills. Wired into `remix_precedent()`'s response and `PrecedentRemixerPanel.jsx`'s bake call. This reuses the diagram-import path's *already-live* attractor→bay-proximity→`program_placement.py` scoring — nothing downstream needed to change.
5. **Deficit-hotspot-weighted amenity placement.** Added `_deficit_weighted_location_weights()` (`logic/pershing_api.py`), bucketing the live bay grid's real `deficit_influence` field into the same 9 cardinal zones the placement math already uses, biasing *where* random amenity/attractor picks land toward areas the 3D side's own amenity-deficit scoring already flags as underserved. Verified statistically over 300 runs: amenity picks landed in the highest-weighted buckets ~85% of the time, matching the underlying deficit-weight distribution almost exactly, while non-amenity categories stayed uniform as scoped.

Also reordered `frontend/src/components/ParamPanel.jsx` so "Design Input" (Paint / Precedent Remixer) is the first section in the panel instead of 8th of 10 — matches the actual design workflow (diagram first, everything else builds off it).

## Verification

All of the above was checked against the live, running apps (not just read from source) — curl timing tests confirming the random path skips Ollama, statistical distribution checks over hundreds of runs confirming the guideline/deficit weighting actually works, and Playwright browser tests confirming the UI renders, generates, and bakes without errors end to end.

## Outstanding, not done today

- 9 of 14 precedent parks (Federation Square, Klyde Warren, Millennium Park, Paley Park, Piazza del Campo, Pioneer Courthouse Square, Superkilen, Tanner Springs, The High Line) only exist as unrun Rhino draw scripts in `data/orchestrator_scripts/` — someone needs to run them in Rhino, export SVGs, and ingest them before the generator can use more than the current 5 real sites.
- This session's changes were layered on top of a large, separate pre-existing uncommitted feature-branch state (canopy engine, circulation network, juror chat, blender pipeline work) that this handoff does not cover or vouch for — only the diagram-generator-related files listed above were reviewed and committed alongside this note.
