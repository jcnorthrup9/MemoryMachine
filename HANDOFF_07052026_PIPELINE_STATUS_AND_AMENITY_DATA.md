Handoff to Gemini: Pipeline status check + amenity-deficit data sourcing question
=====================================================================
*2026-07-05. Claude, working in the Blender cockpit (`blender_cockpit.py`) live against a running Blender 5.0.1 session via BlenderMCP.*

## Where the pipeline is right now

Architecture (locked, from prior sessions): Blender is the live cockpit. `terracing_engine.py` (pure stdlib) and `amenity_deficit.py` (stdlib `csv` only) import directly into Blender's bundled Python and rerun live on toggle. Anything needing PIL/svgpathtools (`sketch_weight_mapper.py`) is precomputed in the normal venv by `precompute_sketch_cache.py` and cached to plain JSON instead.

This session's work, in order:

1. **Hardscape veto wired end-to-end.** `terracing_engine.py` now takes `hardscape_regions`, and any voxel flagged hardscape is forced to `z=0` (hard veto, same mechanism as the existing ramp-clearance check) — distinct from `sketch_weight`, which is additive (can *create* excavation). Added a "Protect Hardscape" toggle to the Blender cockpit panel. Verified numerically both standalone and inside Blender's own Python (exact expected cell-count deltas against a synthetic mask).
2. **Real amenity-deficit CSV ingestion** (`amenity_deficit.py`, new file): reads a Google-Forms-style CSV (`x_frac, y_frac, strength`, optional `radius_ft`) and returns hotspots in real feet, replacing `terracing_engine.py`'s old 2-point diagrammatic `DEFAULT_DEFICIT_HOTSPOTS` placeholder. Wired into the cockpit with a "Use Real Amenity Data" toggle (auto-disabled if no CSV is found). Verified the real data is genuinely used, not silently ignored, via a 2674/2680-cell deficit-influence diff against a synthetic test CSV.
3. **Found and fixed a real registration bug** in `blender_cockpit.py`'s `register()`: `if "MM_PT_cockpit" not in dir(bpy.types): register_class(...)` meant that once the panel was first registered early in a Blender session, *every later script reload silently skipped re-registering it* — so the Scene properties (toggles) updated fine on each reload, but the visible N-panel kept showing the original, pre-toggle `draw()` method. User correctly reported "I don't see the toggles" despite multiple reloads; root-caused by directly inspecting the live registered class's bytecode constants (not by guessing), fixed to unregister-then-register, confirmed live.
4. **In progress, paused mid-build:** a live in-Blender Grease Pencil painting interface (canyon + hardscape marks drawn directly in the viewport, "Bake Sketch" operator converts stroke geometry to the same weight/mask grids — pure vector distance-falloff math, no PIL/image round-trip, so it stays fully live like the toggles above). Mid-implementation, discovered this Blender version (5.0.1) uses the newer Grease Pencil v3 data model — `frame.drawing.strokes`, not `frame.strokes` as most existing docs/examples assume. Paused here to finish verifying the correct API surface before wiring it in for real.

## Open question: amenity-deficit data sourcing

User asked to use a Gemini-generated SVG (`gemini-svg.svg`, now saved at `data/PershingMetabolizer/amenityData/`) as amenity-deficit input. On inspection, it's a demographics/programming-targets dashboard (population, income, required square footage per program type) with a proximity diagram whose own code comment admits the angles are "illustrative... not [real] geographic distributions" — it contains **no site x/y coordinates at all**, so there's nothing in it to map to the `x_frac,y_frac,strength` CSV contract `amenity_deficit.py` expects.

Checked the other candidate source too: `PershingMetabolizer_Prototype/index.html`'s own `DEFICIT_HOTSPOTS` JS constant turns out to be the *exact same* 2-point diagrammatic placeholder ("west/Olive St edge") as `terracing_engine.py`'s old default — not real data, just duplicated. The app's only export feature is a PNG screenshot button; there's no click-to-survey UI, no localStorage, nothing real to pull from it either.

So: **there is currently no real spatial amenity-deficit data anywhere in this pipeline** — Python, JS, or the SVG. `amenity_deficit.py`'s docstring already anticipates this gap (expects an organizer to curate raw survey responses into approximate `x_frac`/`y_frac` before dropping a CSV in), but no actual curation or collection has happened yet.

**Question for Gemini:** given the thesis context, what's the legitimate way to source this?

- Should this stay a designer-curated diagrammatic input (same status as the hand-drawn sketch marks already driving `sketch_weight`) — i.e., the user just picks real x/y points themselves based on judgment, no pretense of an actual public survey?
- Or is there a more defensible real-data source worth pursuing (e.g. an actual short Google Form circulated to real respondents, 311/city open-data amenity-gap reporting, census/ACS-derived proxy)? The SVG's qualitative signal ("Green Space & Parks: CRITICAL NEED" city-wide vs. "Fresh Food/Health Care: OPTIONAL, well-served") is real-ish research but at neighborhood scale, not site-relative — is there a reasonable way to translate a citywide qualitative need into site-relative hotspot placement without just guessing?
- If hand-curation is the right call, is an interactive click-to-place tool (extending the in-progress Grease Pencil painting interface with a third "amenity point" mode, writing straight to CSV) worth building, or is manually typing rows into a CSV good enough given this is a diagrammatic design input, not a scientific dataset?

Claude will hold off building either the hand-curated CSV or the click-to-place tool until this is resolved, same practice as the earlier portal-ramps conflict — don't want to bake in a data-sourcing approach that turns out to misrepresent what kind of "real" this data actually is.
