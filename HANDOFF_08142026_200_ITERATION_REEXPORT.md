# Handoff: re-run the color-diagram batch export at 200 iterations

**Date:** 2026-08-14 · **For:** a fresh chat (context-credit handoff)

## What the user wants

Re-run the randomized design/diagram batch export using the now-expanded 50-park precedent library, at **200 iterations** (previous run was 50, on 2026-08-12).

## Confirmed: the 50 parks are already live, no wiring needed

Checked `logic/ai_synthesizer.py:368-372` and `batch_export_worker.py:68-69` — both build their `available_sites` list by listing `data/PershingMetabolizer/parkSVG/PrecedentSVG/*.svg` **fresh at call time**, not from a cached/hardcoded list. `app.py`, `diagram_tool/app.py`, and `urban_engine.py` all point at the same directory. The 16 newly-added parks (Central Park, Griffith Park, Millennium Park, Regent's Park, Bois de Boulogne, Englischer Garten, Kadriorg Park, Peterhof, Nara Park, Yuyuan Garden, Lodhi Gardens, Hibiya Park, Kings Park, Fitzroy Gardens, Parque Tres de Febrero, High Line) are already selectable by every entry point — nothing to change before running this.

Full context on how the library got to 50 parks (geometry + review scrape pipeline, bugs fixed, rating-check caveat) is in `HANDOFF_08142026_50_PARK_PRECEDENT_LIBRARY.md`, committed this session at `c2983c6` (pushed to `origin/feature/blender-mcp-pipeline`).

## The two-stage pipeline (both confirmed by reading the actual scripts, not assumed)

1. **`python run_batch_export.py 200`**
   Driver → spawns `batch_export_worker.py` once per iteration as its own subprocess (isolation from crashes/shared state — see that script's SAFETY docstring, it never calls `pershing_api.bake()`, never touches `outputs/cockpit/web_paint_state.json`). Each iteration: picks a random spatial seed (drawing from the live 50-park `available_sites` list), composes the diagram, runs the real massing pipeline, writes `outputs/batchExport/iter{N:03d}/{source_diagram.png, plan.png, axo.png, long_section.png, params.json}`.
   - Has built-in retry (3 attempts) + inter-launch delay for a known transient Windows issue (`STATUS_DLL_NOT_FOUND` under rapid back-to-back `python.exe` launches) — already handled, no action needed.
   - **Iteration numbering starts at 1 every run.** The existing `outputs/batchExport/iter001`…`iter050` from the 2026-08-12 run will be **overwritten** by a fresh 200-iteration run using the same default output dir. **User has confirmed this is fine** — they already saved their own backup copy of the Aug 12 run elsewhere (referred to as "colordiagramstk1"). `outputs/batchExport/colorDiagrams` is the live/current folder and all individual files in it can be freely overwritten. No need to back anything up before running.
   - Budget significant wall-clock time — each iteration runs the real massing/geometry pipeline (matplotlib/trimesh/embreex), and this is 4x the previous 50-iteration run. Recommend running in the background and checking progress via `outputs/batchExport/batch_log.txt` (written incrementally... actually written once at the end — check subprocess stdout/the task's live output instead while it runs).

2. **`python add_color_drawing.py`**
   Post-process → for every `outputs/batchExport/iter*/` folder containing a `params.json`, reproduces that exact saved design (no re-randomization) and writes `color.png` into that same `iter{N:03d}/` folder. Run this after step 1 completes.

## Known discrepancy — worth 2 minutes of sanity-checking before assuming anything

The Aug 12 output on disk right now is `outputs/batchExport/colorDiagrams/iter001_color.png` … `iter050_color.png` (a separate `colorDiagrams/` subfolder, flat files with an `_color` suffix). But `add_color_drawing_worker.py` (read directly, line 72) writes to `iter_dir/color.png` — i.e. `outputs/batchExport/iter001/color.png`, no separate subfolder, no suffix. These don't match. Possibilities: an older script version produced the `colorDiagrams/` layout and was later refactored to the current in-place `color.png` scheme, or something copied/renamed the files afterward for a different purpose (e.g. a presentation deck — `html/final_deck.html` exists untracked in this repo, might be the consumer). Worth a quick check of `iter_dir` contents after running the current scripts to confirm where output actually lands before telling the user "done."

## Not yet done — nothing else pending

The precedent library work itself (50 parks, geometry + reviews + ChromaDB ingestion) is fully complete, committed, and pushed. This handoff is purely about the next ask: the 200-iteration re-export.
