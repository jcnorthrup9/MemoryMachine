# Qualitative Cross-Pollination Engine
## Implementation Notes // Memory Machine // Digital Palimpsest

---

## Project Understanding

### The Thesis

The Memory Machine is a generative design project that treats architectural spaces the way memory itself works — not as stable archives, but as unstable, decaying processes. The analogy is layered:

- **Human memory** encodes, retrieves, and distorts. Dementia fragments it.
- **AI systems** hallucinate, pattern-match noise into meaning (Apophenia), and operate with missing data.
- **Architecture** is physically overwritten over time, leaving "witness marks" — traces of what existed before.

Pershing Square in Downtown LA is the thesis site precisely because it has been demolished and rebuilt repeatedly. It is the *ultimate urban palimpsest*: a five-acre void in DTLA that has been erased so many times it embodies the project's entire argument.

### The Four-Phase Pipeline

```
[Phase 1] DATA HARVEST
    machine_os.py orchestrates:
    free_scraper.py      → Wikipedia + DuckDuckGo text
    satellite_scraper.py → Google Maps imagery
    osm_scraper.py       → OpenStreetMap building footprints

        ↓

[Phase 2] PROCESSING & EXTRACTION
    spatial_extractor.py → pulls atmospheric + dimensional data from text
    spatial_mapper.py    → converts extractions to CSV massing blueprints
    opencv_site_mapper.py → detects trees/vegetation from satellite imagery
    Output: memory_manifest.json

        ↓

[Phase 3] RHINO 3D CANVAS
    site_reconstruction.py   → rebuilds Pershing Square base geometry
    intervention_engine.py   → deploys memory assets as procedural 3D objects
    Output: Rhino .3dm masterplan

        ↓

[Phase 4] ARCHIVAL & SYNTHESIS
    deck_compiler.py   → Gemini-narrated HTML presentation deck
    zine_compiler.py   → dark-theme interactive HTML zine with decay effects
    figmaPlugin/       → TypeScript plugin to auto-build Figma slides
    Output: html/presentation_deck.html, html/digitalPalimpsest.html
```

### The Data

The review archive is the emotional core of the system. Real visitor language — messy, subjective, atmospheric — is the raw material:

| File | Source | Purpose |
|---|---|---|
| `anonymized_bottega_louie_reviews.json` | Yelp (Scrapfly) | 11,985-line structured JSON; acoustic/material descriptions |
| `bottega_louie_reviews.txt` | Raw text | Marble, light, sound, crowd |
| `nakagin.txt` | TripAdvisor | Capsule tower; claustrophobia, intimacy, decay |
| `zaryadye_park_reviews.txt` | Reviews | Wild nature in the city; Moscow |
| `queens_gardens_bridge_reviews.txt` | Mixed | Water, gardens, bridges |
| `pershing_square_reviews.txt` | Google Maps | Emptiness, heat, nostalgia |
| `exit_reviews.txt` | Reviews | Threshold, liminal space |
| `ot_johnson_data.txt` | Wikipedia/scraped | Historic DTLA lobby; marble columns, cast iron |

### The memory_manifest.json

This is the bridge between Phase 2 (data) and Phase 3 (Rhino). Each node in the array becomes a 3D object placed on the Pershing Square masterplan. Prior to this implementation, nodes looked like:

```json
{
  "name": "Bottega Louie Marble Floor",
  "sentiment_score": 0.9,
  "raw_text": "The sound of heels clicking on the white marble..."
}
```

Geometry type was inferred by keyword matching on the `name` field inside `intervention_engine.py`.

---

## What Was Built

### 1. `logic/qualitative_search.py` — New File

The Qualitative Cross-Pollination Engine. A standalone script that closes the loop between qualitative human experience and quantitative 3D geometry.

#### How It Works

**Step 1 — Keyword Extraction (Gemini)**

The natural language prompt is parsed by Gemini into four structured categories:

```json
{
  "qualities":        ["shade", "water", "acoustic"],
  "spatial_elements": ["canopy", "wading pool", "fountain"],
  "sensory_keywords": ["cool", "humid", "gentle sound", "dappled light"],
  "mood":             "tranquil and restorative"
}
```

**Step 2 — Corpus Search (local)**

Each keyword is scored against all local review files using simple substring matching. The top 3 scoring real-world spaces become the "memory sources" — the actual buildings and parks whose atmospheric qualities will be cross-pollinated into Pershing Square. Relevant text excerpts are extracted and attached to the node.

**Step 3 — Spatial Synthesis (Gemini)**

Gemini is given the original prompt, the extracted keywords, and the matched review excerpts. It is asked to produce precise, dimensioned spatial parameters:

```json
{
  "footprint_m":        { "width": 20, "depth": 20 },
  "height_m":           8.0,
  "canopy_overhang_m":  2.5,
  "pool_depth_m":       0.3,
  "pool_width_m":       12.0,
  "column_count":       8,
  "column_height_m":    6.0,
  "column_radius_m":    0.3,
  "materials":          ["concrete", "water", "weathered_steel"],
  "geometry_type":      "pavilion_with_water",
  "acoustic_elements":  ["recirculating_water_jets", "textured_ceiling"],
  "shade_coverage_pct": 80,
  "sentiment_score":    0.88
}
```

The `geometry_type` field constrains Gemini to one of six values that map directly to procedural geometry handlers in Rhino.

**Step 4 — Architectural Narrative (Gemini)**

A 3–4 paragraph architectural theorist's text is generated. It must address:
- What the space feels like (sensory, atmospheric)
- The "witness marks" carried from source spaces
- How the intervention collides with the Pershing Square palimpsest

**Step 5 — Mermaid Diagram**

A flowchart diagram is constructed programmatically (no AI call) tracing the exact logic path:

```
User Query → AI Keyword Extraction → [quality nodes] → [memory source nodes]
         → Spatial Synthesis → [geometry type, height, materials] → Deploy
```

#### Outputs

Every run produces three artifacts in `data/cross_pollination/`:

| File | Contents |
|---|---|
| `CP_YYYYMMDD_HHMMSS.json` | Full Memory Node: all parameters, narrative, diagram source, matched excerpts |
| `CP_YYYYMMDD_HHMMSS.html` | Self-contained dark-theme HTML: narrative + source cards + params table + live Mermaid diagram |

The node is also appended to `memory_manifest.json` immediately, making it available for the next Rhino session without any manual steps.

#### Usage

```bash
# Interactive
python logic/qualitative_search.py

# Direct prompt
python logic/qualitative_search.py "I want a space with lots of shade, shallow wading pools, and water features that create a pleasant acoustic hum."
```

---

### 2. `logic/intervention_engine.py` — Modified

Two additions were made to the existing Rhino script. The existing logic was not changed.

#### Addition 1 — Spatial Parameter Extraction (lines ~68–76)

After `radius` and `height` are calculated from `sentiment_score`, the script now checks whether the current asset has a `spatial_parameters` block. If it does, the precise dimensions override the sentiment-derived estimates:

```python
spatial_params = asset.get('spatial_parameters', {})
geometry_type  = spatial_params.get('geometry_type', None)
if spatial_params:
    footprint = spatial_params.get('footprint_m', {})
    if isinstance(footprint, dict) and 'width' in footprint:
        radius = float(footprint['width']) / 2.0
    if 'height_m' in spatial_params:
        height = float(spatial_params['height_m'])
```

This means cross-pollination nodes get geometry at the scale the AI specified, not a random sentiment-scaled estimate.

#### Addition 2 — Cross-Pollination Geometry Handlers (before existing if/elif chain)

Six new geometry types were added as `elif` branches that check `geometry_type` before the existing keyword-based fallbacks. This means the original tree/water/pavilion/tower logic is fully preserved for all existing nodes:

| geometry_type | Rhino Geometry |
|---|---|
| `pavilion_with_water` | Sunken pool basin + circular plinth + N columns (parametric count) + overhanging roof disc |
| `shade_canopy` | Perimeter columns + thin flat canopy disc (minimal, tensile feel) |
| `water_garden` | Outer ring channel + inner pool + organic mound sphere + central jet pedestal |
| `acoustic_screen` | Row of thin vertical fins (count derived from radius) |
| `memory_tower` | Base plinth + tapered shaft + flared crown + spire |
| `landscape_mound` | 4 stacked diminishing spheres (topographic landform approximation) |

All geometry shares the same grouping, layer assignment (`01_INTERVENTION_ASSETS`), and user text tagging (`Asset_Name`, `Memory_Data`) as the existing procedural fallbacks.

---

## Design Decisions

**Why Gemini and not Claude for the cross-pollination engine?**
The existing project stack is already built around Gemini (`google-generativeai` in requirements.txt, `GEMINI_API_KEY` in `.env`, Gemini calls throughout `machine_os.py` and `deck_compiler.py`). Matching the existing API keeps the `.env` file simple and avoids adding a dependency.

**Why keyword scoring instead of embeddings for corpus search?**
The review files are plain text and the project has no vector database infrastructure. Simple substring scoring is fast, transparent, and produces readable `matched_terms` lists that flow directly into the Mermaid diagram and the narrative prompt. Embedding-based semantic search would require adding `sentence-transformers` or a vector store — a meaningful infrastructure change for marginal gain given the small corpus size.

**Why six geometry types?**
The six types cover the primary spatial moves available in the project brief (shade, water, acoustic, memory marker, landscape) while remaining implementable with `rhinoscriptsyntax` primitives (cylinders, spheres, boxes). More complex forms (NURBS surfaces, meshes) would require a different approach inside Rhino.

**Why output to `data/cross_pollination/` instead of `html/`?**
The `html/` directory is the output of the Phase 4 compilers (`deck_compiler.py`, `zine_compiler.py`). Cross-pollination outputs are intermediate artifacts — they belong in `data/` alongside the other node JSON files. If the designer wants to fold a cross-pollination output into the final deck, they can run the compiler after adding the node.

---

## Integration Map

```
qualitative_search.py
    ↓ writes
data/cross_pollination/CP_*.json     (full node record)
data/cross_pollination/CP_*.html     (standalone viewer)
data/memory_manifest.json            (Rhino-ready node appended)
    ↓ read by
intervention_engine.py               (deploys geometry in Rhino 3D)
    ↓ reads new fields
spatial_parameters.geometry_type     → selects geometry handler
spatial_parameters.footprint_m       → overrides radius
spatial_parameters.height_m          → overrides height
spatial_parameters.*                 → pools, columns, fins, etc.
```

---

*Memory Machine // Digital Palimpsest // Implementation Notes*
*Claude Code — 2026-03-26*
