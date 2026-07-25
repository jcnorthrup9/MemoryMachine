# Handoff — Zonal Constraints HUD Percentages (port 8000, 2D only) — 2026-07-22

## Goal (scoped, don't expand)

Port 8000 (root `app.py` + `static/main.js`, the "Digital Palimpsest" 2D app) shows a
"ZONAL CONSTRAINTS" HUD with target ranges (Softscape 30-50%, Hardscape 40-60%,
Activators 10-20%, Water 2-10%) and live computed percentages. The computed
percentages were reading near-zero regardless of what was visibly drawn. This
session is scoped to fixing *that* — 2D diagram only. Do not touch `diagram_tool/`
(port 8006, separate standalone app) or the React Metabolizer (port 5173) as part
of this task.

This doc is a same-day handoff to a Claude session on the other machine
(`D:\MemoryMachine`) because Syncthing on the `jcnor` machine had been down since
2026-07-10 and re-syncing `data/PershingMetabolizer/parkSVG/PrecedentSVG/` (large
SVGs) was going to take a while. Syncthing has since been restarted there and is
mid-transfer, but no need to wait for it — this doc is self-contained.

## Fix #1 — already applied, will arrive via Syncthing (not urgent to redo)

`static/main.js`'s `_injectBaseContext()` seeds the HUD's baseline stack with a
fixed list of "locked" layers so the HUD has a real reading even before any
generation. That list omitted `GREEN_SPACE` and `WATER_FEATURES`, even though
`engine2D.js`'s context-group renderer draws both as visible base-park geometry
unconditionally (see its `contextKeywords` list). Since the HUD only tallies
`MemoryState.stack`, the visible lawn/water were invisible to the percentage math
— hard 0% no matter what was on screen.

Already fixed on the `jcnor` machine (verified live via Chrome automation —
Softscape moved 0%→2%, Water 0%→1% immediately after the fix + hard reload):

```js
// static/main.js, function _injectBaseContext()
const BASE_LAYERS = [
  'BOUNDARY', 'STREET', 'PARKING', 'PEDESTRIAN_PATH', 'STREET_FURNITURE',
  'GREEN_SPACE', 'WATER_FEATURES'
];
```

This file is git-tracked (not in `data/`, not `.stignore`'d), so it should show up
on this machine via Syncthing/git on its own. Diff it against the above if you
want to confirm before Fix #2 below.

## Fix #2 — the actual blocker, needs doing HERE

Even with Fix #1, percentages stayed far below their real visual size (Softscape
2% vs. a lawn that visually covers ~15-20% of the site; Hardscape stuck at ~4%
against a 40-60% target). Root cause: `app.py`'s own base-geometry endpoint reads
from the **wrong, stale SVG source**.

```python
# app.py:48
SVG_DIR = os.path.join(BASE_DIR, 'data', 'ParkSVG')   # <- stale, April-dated
```

`get_diagram()` (`app.py` ~line 206-220, serves `GET /api/diagram-data/{site}`)
resolves site SVGs from this dir. `static/main.js`'s `fetchSVG()` calls this
endpoint to populate `MemoryState.svgCache['PershingSquare']` — the **single**
SVG that both `engine2D.js` (visual context render) and `state.js`'s
`getProgramStats()` (the HUD math) read from.

Diagnosed on the `jcnor` machine: `data/ParkSVG/Pershing_Square.svg` (last
modified 2026-04-15) represents almost every zone as dense Rhino hatch-line
decoration — thousands of individual 2-point `<path>` strokes with
`fill="none"` — not closed filled polygons. Only `WATER_FEATURES`'s one
`<circle>` element has real closed-shape area; everything else nets to ~0 no
matter what code wires it into the HUD stack. Counts from that file:

| Layer | Total paths | Paths big enough to be a real closed shape (>20 numbers) |
|---|---|---|
| HARDSCAPE | 5,332 | **0** |
| STREET | 4 | 0 |
| GREEN_SPACE | ~6,488 | ~5 (unclear if real or just longer hatch strokes) |
| WATER_FEATURES | 802 paths + 1 circle | 1 (the circle) |
| PEDESTRIAN_PATH | 270 | 2 |

Meanwhile `logic/ai_synthesizer.py` and `logic/urban_engine.py`'s
`remix_layers()` were **already repointed on 2026-07-16** at the canonical,
cleaner site library:

```python
# logic/urban_engine.py, inside remix_layers()
SVG_DIR = os.path.join(BASE_DIR, 'data', 'PershingMetabolizer', 'parkSVG', 'PrecedentSVG')
```

`app.py`'s own `/api/diagram-data/{site}` endpoint was never updated to match —
so the app has had two different site-geometry sources in play since 07-16, and
the HUD/2D-context path is stuck on the old one.

The user confirmed (this session, on the `D:\MemoryMachine` machine) that
`PrecedentSVG/` already has the zones re-exported as real closed
polylines/polygons per the earlier ask — so the fix here is very likely **just
repointing `SVG_DIR`**, not another re-export. But confirm geometry before
declaring done — don't assume.

### What to actually do here

1. **Verify `PrecedentSVG/PershingSquare.svg` (or whatever it's actually named
   there) has real closed-boundary geometry**, not hatch lines, for at least
   `GREEN_SPACE`, `HARDSCAPE`, and `WATER_FEATURES`. Quick check — a real
   closed polygon layer will have paths with many more than 2 points (i.e. more
   than 4 numbers) per `d` attribute, or use `<polygon>`. A `grep -c` for
   `<path` inside a layer's `<g>` vs. how many of those paths have long `d`
   strings is enough to tell hatch-soup from real shapes (same technique used
   in the table above — extract each `<path d="...">`, count numeric tokens,
   flag ones with >20 as plausibly real).

2. **Check the exact filename** `PrecedentSVG/` uses for Pershing Square.
   `urban_engine.py`'s `SITE_NAME_CANONICAL` expects `PershingSquare.svg` (no
   underscore) — different convention from `data/ParkSVG/Pershing_Square.svg`
   (underscore + space variants). `get_diagram()`'s matching is
   case/underscore/space-insensitive (`file.lower().replace("_","").replace(" ","")`),
   so it should resolve fine either way, but confirm the file is actually
   there under some near-match of that name.

3. **Repoint `app.py`'s `SVG_DIR`** (line 48) at
   `os.path.join(BASE_DIR, 'data', 'PershingMetabolizer', 'parkSVG', 'PrecedentSVG')`
   — matching what `urban_engine.py` already uses. This is the one-line fix,
   *if* step 1 confirms the geometry is actually there and correct.

4. **Restart the port-8000 process**, hard-reload the browser (`Ctrl+Shift+R`
   — static JS/data is aggressively cached; a normal reload will silently keep
   serving stale content, this bit us once already this session), and check the
   ZONAL CONSTRAINTS HUD. Expect Softscape/Hardscape/Water to now read
   somewhere in the neighborhood of their real visual proportions — they don't
   need to land inside the target range (that's a design/intervention problem,
   not a measurement bug), they just need to stop reading near-zero.

5. **If `PrecedentSVG`'s geometry turns out to still be hatch-only** (i.e. step
   1 fails), the fix isn't code — it needs a genuine re-export: one closed
   polyline/polygon per contiguous patch per zone (multiple disjoint patches
   per zone are fine, just each as its own closed shape, same group id), same
   coordinate system as the existing `BOUNDARY` layer (which already exports
   correctly and is what the site clip-path relies on).

## Also worth knowing

- `app.py`'s `get_diagram()` does a **loose filename match** — case-insensitive,
  strips `_` and spaces — so multiple candidate files in a directory (e.g. old
  `.svgbak`, `sync-conflict` copies) could theoretically collide. Sanity-check
  `PrecedentSVG/` doesn't have stale duplicate/conflict files before trusting
  which one gets picked up (the old `data/ParkSVG/` dir had several —
  `Pershing_Square 1.svg`, `.svgbak`, `.sync-conflict-*.svg` — all sitting
  next to the real one).
- Don't change `logic/ai_synthesizer.py` or `logic/urban_engine.py`'s
  `SVG_DIR` — those are already correct; only `app.py:48` is stale.
- Everything above is about the **base/context** SVG path
  (`/api/diagram-data/{site}` → `get_diagram()`). It is separate from
  `remix_layers()`'s own site-picking logic, which is unaffected by this bug.
