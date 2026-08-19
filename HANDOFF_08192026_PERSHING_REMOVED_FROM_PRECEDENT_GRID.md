# Handoff: Pershing Square removed from the page-04 precedent grid (deck-only)

**Date:** 2026-08-19
**Touched:** `html/final_deck.html` only. `data/precedent_park_list.py` and Pershing's own SVG/thumbnail were deliberately left alone.

## What happened

While your 150-park dynamic grid (`#precedent-grid`, the `PRECEDENT_GRID_DATA_START/END` JSON block, `buildPrecedentGrid`/`startPrecedentGrid` in the `<script>`) was mid-build in the shared working tree, the user asked to remove Pershing Square from that grid specifically — it's the site being designed for, not a comparison precedent (matches the reasoning already in your `data/precedent_park_list.py` docstring: "Pershing Square is deliberately NOT flagged... it's the scale/coordinate anchor for the live generation app, not a comparison precedent").

The user's explicit scope: *"it can live everywhere else in the pipeline, just remove it from the tiled precedent page."* So:

- **`data/precedent_park_list.py`** (`EXISTING_PARKS`, `ALL_PARKS`, `TILE_GROUPS`) — **untouched**. Pershing Square is still entry #1 there, still used by whatever else in the pipeline reads that module.
- **Pershing's SVG/thumbnail** (`data/PershingMetabolizer/parkSVG/PrecedentSVG/PershingSquare.svg`, `static/thumbnails/precedent/PershingSquare.jpg`) — **untouched**, still on disk.
- **Only the embedded JSON in `html/final_deck.html`** was edited: the tile that used to cycle `["Pershing Square", "Menara Gardens", "Fairmount Park"]` now cycles `["Balboa Park", "Menara Gardens", "Fairmount Park"]`, keeping the deck's displayed total at exactly 150 (50 tiles × 3) without touching your tile-grouping algorithm's output for every other tile.

To keep that swap real rather than another broken tile, I fetched Balboa Park (San Diego) through your existing pipeline:

```
.venv/Scripts/python.exe -c "from fetch_park_precedent import fetch_and_write_precedent; fetch_and_write_precedent('San Diego', 'Balboa Park')"
.venv/Scripts/python.exe harvest/generate_precedent_thumbnails.py
```

That created `data/PershingMetabolizer/parkSVG/PrecedentSVG/BalboaPark.svg` and `static/thumbnails/precedent/BalboaPark.jpg`, same as any other entry. Balboa Park is **not** added to `data/precedent_park_list.py` — it only exists as this one manual tile substitution in the deck's JSON. If you later regenerate `PRECEDENT_GRID_DATA` from `build_precedent_grid_data.py`, this substitution will get overwritten and Pershing will reappear in the grid unless you either re-apply the swap or add Balboa Park (or some other 151st park) to the roster and re-run the build with Pershing excluded.

I also ran `harvest/generate_precedent_thumbnails.py` once without `--force`, which filled in 21 thumbnails for already-fetched-but-unthumbnailed parks (pure bonus fill-in of existing gaps, didn't change any roster data). As of this writing, 77 of the 150 roster parks still have no fetched SVG at all — that's your in-progress fetch work, I didn't touch it or try to complete it.

## Why nothing was pushed to `main` / GitHub Pages

`html/final_deck.html` is one file — my two small edits (Pershing swap + removing a leftover `★` from the "Park Iteration" label on page 05) are textually inside your much larger uncommitted grid-feature diff. There's no way to commit just my part without also shipping your feature as-is, and with 77/150 parks still unfetched, a lot of tiles currently render as broken-image icons with just the alt-text name showing. The user chose to hold off rather than put that on the public site, so `main` is still serving the old static-wallpaper version of page 04. Everything above is verified working only on the local dev server (`localhost:8765`).

**Next step is yours**: once the grid is far enough along that you want it live, either push `html/final_deck.html` as-is (Pershing stays excluded per this note), or let me know if you'd rather I redo the swap after you've regenerated the JSON from a roster that already excludes Pershing.
