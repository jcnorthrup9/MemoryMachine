# Milestone: 50-park precedent library (geometry + reviews)

**Date:** 2026-08-14

## What happened

Grew the real-world park precedent library from 34 to 50 parks, with both halves of the pipeline run for each:

1. **Geometry** — `fetch_park_precedent.py`'s `fetch_and_write_precedent(city, park_name)` geocodes via Nominatim and pulls tagged features via the Overpass API (both free, no key), writing an SVG into `data/PershingMetabolizer/parkSVG/PrecedentSVG/` matching the app's existing precedent schema.
2. **Reviews** — `logic/free_scraper.py`'s `scrape_info(target_name, location)` pulls Wikipedia summaries + DuckDuckGo text search results, writing `data/{slug}_reviews.txt`.
3. **Ingestion** — `harvest/ingest_to_chroma.py` chunks and embeds all `data/*.txt`/`*.md` files into the ChromaDB collection `memory_machine_corpus` (`db/`), which `generate_spatial_seed()` queries live at generation time.

## The 16 new parks added this session

Central Park (New York), Griffith Park (LA), Millennium Park (Chicago), Regent's Park (London), Bois de Boulogne (Paris), Englischer Garten (Munich), Kadriorg Park (Tallinn), Peterhof (Russia), Nara Park (Nara), Yuyuan Garden (Shanghai), Lodhi Gardens (Delhi), Hibiya Park (Tokyo), Kings Park (Perth), Fitzroy Gardens (Melbourne), Parque Tres de Febrero (Buenos Aires), High Line (New York).

Combined with the prior 34, the library is now at **50 parks**, each with both geometry and review text present and ChromaDB-indexed.

## Fixes made along the way

- **`logic/free_scraper.py`**: was missing the `ddgs` dependency entirely (uncaught `ImportError`) and crashed on Windows console output (`UnicodeEncodeError` on emoji in `print()`). Both fixed — added `ddgs` to `requirements.txt`, added a `_log()` helper that encodes/decodes with `errors="replace"` instead of reconfiguring stdout globally.
- **`harvest/ingest_to_chroma.py`**: was generating a random UUID per chunk on every run, so re-running it after any new scrape would duplicate the *entire* existing corpus, not just add the new content. Switched to deterministic content-hash IDs + `collection.upsert()`, so re-running is now safe. Also fixed the same Windows console emoji crash.
- **Overpass rate limiting**: batch-fetching many parks back-to-back with only ~1s spacing caused most calls to fail with 429/504. Spacing calls ~25s apart fixed it (8/8 succeeded on retry vs. 8/16 on the first, fast pass).

## Known gap: no verified star ratings

The original 5 hand-built precedents were meant to be "high-performing" parks (implicitly >4 stars), but the free scraper pipeline was never designed to capture structured ratings — Wikipedia/DuckDuckGo give history and description, not Google/Yelp star data. Getting real per-park ratings would require either a paid API (Google Places/Yelp Fusion) or direct scraping of a specific ratings page per park, neither of which fits the explicit no-budget constraint on this project (a live Scrapfly key exists in `scraper.py` but is intentionally unused — see feedback memory).

Tried a best-effort free workaround: DuckDuckGo search + regex for numeric rating mentions across all 50 parks. Only 3/50 returned a parseable rating (Cheviot Hills Park 4.5, Frognerparken 4.7, Prospect Park 4.9 — all comfortably above 4.0). The other 47 "no signal found" results are **not evidence of a bad rating** — just a limitation of matching a specific numeric string in a handful of search snippets. Results saved at `data/park_rating_check.json` (not tracked in git — `data/` is gitignored, synced via Syncthing instead).

Decision: left as-is. All 50 parks are globally recognized landmark parks, not obscure picks, so reputation stands in for verified rating data for now.

## Note on `data/`

`data/` is gitignored in this repo (synced across machines via Syncthing, not git — see project sync memory). The 16 new SVGs, all 50 review `.txt` files, and `park_rating_check.json` live there and will NOT show up in `git status` or get committed by default. This commit only captures the code/script changes (`fetch_park_precedent.py`, `logic/free_scraper.py`, `harvest/ingest_to_chroma.py`, `requirements.txt`) plus this note.
