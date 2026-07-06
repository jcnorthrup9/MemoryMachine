# Memory Machine — Session Log
**Date:** 2026-04-01

---

## Summary

This session completed Task 11 (Interactive SVG Diagram Viewer) and resolved several bugs across the diagram pipeline.

---

## Changes Made

### 1. `templates/diagram_viewer.html` — NEW FILE
Created the Interactive SVG Diagram Viewer page, served at `/diagrams`.

**Features:**
- Split-screen layout: white SVG pane (left) + dark data panel (right)
- Site selector dropdown auto-populated from the API
- Raw SVG injected directly into the DOM from Rhino exports
- Right panel displays: Design Logic, Zones (cards), Paths (cards), Relationships
- Hover interactivity: hovering a zone card dims all non-matching SVG layers and glows the matching one; hovering an SVG layer highlights the corresponding data cards
- CSS transitions for glow/dim effects using `drop-shadow` filters
- Layer name mapping: zone types (e.g. "Green Space") mapped to Rhino SVG group IDs (e.g. `GREEN SPACE`)
- Empty state messaging when no SVG is loaded
- Dark theme (Courier New, `#050505` bg) matching `index.html`; SVG pane set to white for readability

---

### 2. `app.py` — Updated endpoints

**Added `SVG_DIR`** (was already defined, now actively used):
```
SVG_DIR = BASE_DIR/data/ParkSVG
```

**`GET /diagrams`** — serves `diagram_viewer.html`

**`GET /api/diagram-data`** — updated:
- Scans `data/ParkSVG/` for `.svg` files (not `archive/diagrams/`)
- JSON in `archive/diagrams/` is now optional (sites appear even without a parsed JSON)
- Returns `{ site, has_json }` per entry

**`GET /api/diagram-data/{site}`** — updated:
- Loads SVG from `data/ParkSVG/{site}.svg`
- Case-insensitive JSON lookup in `archive/diagrams/`
- Returns empty zones/paths/relationships if no JSON found (graceful degradation)

---

## Current SVG Files
Located in `data/ParkSVG/`:
- `Pershing_Square.svg` — no JSON yet
- `parc_de_la_villette.svg` — matched to `parc_de_la_villette_rhino_parsed.json`

---

## Bugs Fixed

| Bug | Cause | Fix |
|---|---|---|
| Dropdown empty | JS syntax error from linter truncating `renderAll()` | Restored `showEmptyState(...)` and `designLogicText.textContent` lines |
| HTML layout broken | Linter truncated `<div class="hint">` mid-line, leaving unclosed divs | Restored closing tags for `#empty-state`, `#svg-container`, `#svg-pane` |
| Sites not appearing in dropdown | Endpoint required exact case match between SVG stems and JSON stems | Switched to case-insensitive matching; made JSON optional |
| SVG hard to read | SVG pane background was `#050505` (near black) | Changed `#svg-pane` background to `#ffffff` |

---

## Pending

- **Task 5:** Auto-populate new Rhino `.3dm` files for High Line, Federation Square, Pioneer Courthouse Square, Superkilen — create file, insert satellite image at correct scale, apply full layer + layout structure
- Export SVGs from remaining Rhino diagrams (ZaryadyePark, GrandParkLA, MaggieDaleyPark) and add to `data/ParkSVG/` to populate the viewer
- Add a Pershing Square `_rhino_parsed.json` to enable the full hover-interactivity for that site
