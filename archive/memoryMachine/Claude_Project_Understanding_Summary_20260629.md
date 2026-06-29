# MemoryMachine — Claude's Understanding of the Project (as of 2026-06-29)

## What this is
A Master of Architecture thesis ("The Machine That Forgets") by John C. Northrup II, treating the 1951 underground parking garage beneath **Pershing Square, Downtown LA** not as a buried constraint to ignore, but as the generative driver for a new park design. The project layers qualitative "memory" (scraped reviews, historical sentiment) with quantitative urban data (transit proximity, building heights, amenity deficits) to decide *where* the surface should "puncture" down into the subterranean structure.

## How the idea evolved
1. **Forensic Palimpsest (Mar–Apr 2026)** — scraping/parsing reviews and historical data on three precedents (Bottega Louie, O.T. Johnson Building, Nakagin Capsule Tower) into a "digital zine," establishing the memory-as-data methodology.
2. **Autonomous Discovery (Apr–May 2026)** — pivot to prospective design: web-search agents, satellite-image scraping + OpenCV tree extraction, Figma plugin for auto-generating slides.
3. **Urban Metabolizer Engine (May–Jun 2026)** — the real engine: a scored 30×30 grid over the Pershing Square site (330×550ft), weighing **transit flux**, **building enclosure**, and **amenity deficit** to flag "puncture zone" cells (`urban_interference_solver.py`). Real data now backs this (`building_heights.json`, `transit_flux.json`, `amenity_deficits.json`, `program_requirements.json`).
4. **Generative Diagramming & Visualization (Jun 2026–present)** — a Gemini-vision "Diagram Agent" extracts spatial DNA from precedent diagrams (Parc de la Villette, Superkilen, SESC Pompeia, etc.); geometry pipeline moved from a crude bounding-box heuristic to a **centroid + shoelace-formula** approach for true-area scaling. Current flagship artifact: **PershingMetabolizer_Prototype**, a Three.js viewer driven by *real* Rhino-exported geometry (274 structural columns, tunnel mesh, metro entrance, spiral ramps), showing three cumulative excavation phases as a 9ft voxel grid.

## Current state of the generative diagramming logic
- Real structural geometry (not placeholder boxes) now drives the model: column grid, garage depth, tunnel mesh, metro entrance position all extracted from Rhino OBJ exports.
- Scoring formula: `intervention_score = 0.4×memory_volatility + 0.6×asset_pressure`, where `asset_pressure = 0.3×enclosure + 0.3×transit + 0.4×amenity`. Memory-volatility is still a placeholder (0).
- Three phases visualize cumulative excavation: (1) transit-driven cuts, (2) + deficit-driven scoops, (3) + structural "jacket" damping near columns.
- Diagram taxonomy is standardized (`DIAGRAM_RULES.md`): surfaces / lines / points, all on Z=0 plan, exported as SVG+JSON.

## Known gaps (going into today's questions)
- The **tunnel-alignment logic currently treats the whole tunnel OBJ as the target**, when it should only care about the cut reaching `metroEntrance` — the tunnel mesh is diagrammatic, not a literal excavation target. *(today's Q1)*
- **Amenity-deficit program** (food court, truck parking, lounging, sports) is scored but not yet assigned to specific cassettes or resolved as surface-vs-underground, nor phased over time. SESC Pompeia is named as a precedent but not yet spatially mined. *(today's Q2)*
- **Light/shade/tree/lightwell logic** exists conceptually in `program_requirements.json` (LA Landscape Ordinance shade targets) and `building_heights.json` (enclosure/solar data), but is **not yet rendered** in the prototype — it's the most underdeveloped of the three systems. *(today's Q3)*

## App / codebase shape
- Backend: FastAPI (`app.py`), ChromaDB memory store, modular engines (`geometry_engine.py`, `urban_engine.py`, `ai_synthesizer.py`, `comfy_client.py` for ComfyUI renders).
- Frontend: Three.js viewport (`templates/index.html`) + standalone `PershingMetabolizer_Prototype`.
- Tooling: Figma plugin for slide generation, satellite/OpenCV tree extraction, Gemini-driven diagram analysis agent.

## Open items beyond today's three questions
- Memory-volatility overlay never wired into the scorer.
- Program-to-cassette assignment (which deficit gets which puncture zone) unresolved.
- No constructability pass yet (ramp slopes, egress, waterproofing) — may constrain how literal the terracing/conical excavation toward `metroEntrance` can be.
