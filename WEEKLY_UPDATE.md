# 🧠 Memory Machine // Development Sprint Log
**Date:** March 30, 2026
**Focus:** Rhino MCP Integration, Spatial Data Expansion, and AI Vision Calibration

## 1. Rhino MCP & Local Environment Setup
- Successfully migrated the pipeline to new hardware.
- Initialized the **Claude Rhino MCP**, establishing a live websocket bridge to the active `.3dm` document.
- **Validation:** Proved read/write capabilities by having Claude autonomously query the document for unknown `?` text objects, report their coordinates, and overwrite them with actual site names using injected `rhinoscriptsyntax`.
- *Resolved:* Diagnosed and fixed runaway annotation line weights caused by the `printDisplay` viewport scale toggle.

## 2. Precedent Corpus Expansion & Calibration
- Refactored `satellite_scraper.py` into a flexible CLI utility to allow targeted image harvesting.
- Expanded the core precedent dataset to 15 sites, removing poor-visibility sites and adding highly diagrammatic spaces (*Piazza del Campo, The High Line, Federation Square, Pioneer Courthouse Square*).
- Mapped exact GPS coordinates (lat/lon) into the `SOURCE_INFO` registry in `app.py` to anchor all future generative geometry to real-world math.

## 3. The Autonomous Orchestrator (Experiments in Generative Drafting)
- Developed `autonomous_diagram_orchestrator.py` to bypass LLM geometric hallucination.
- **OpenStreetMap (OSM) Integration:** The script queries the Overpass API for real-world building footprints around precedent sites and translates them into local Cartesian coordinates (meters).
- **Image Scaling:** Added functionality to import satellite screenshots as Rhino `PictureFrame` underlays, scaling them perfectly to the OSM geometry using Web Mercator projection formulas.
- **The 4x5 Masterplan:** Calibrated the generated Python scripts to accept `offset_x` and `offset_y` parameters, allowing the MCP to place sites neatly into a 800-unit spaced grid.

## 4. The Strategic Pivot: AI as Architectural Analyst
- *Observation:* While the MCP can draw math, it is "blind" to the viewport. Generative drafting from scratch proved brittle and misaligned with the project's core visual language.
- *Pivot:* Shifted the AI's role from "Draftsman" to "Analyst". The machine's primary directive is now to read and interpret human-authored architectural diagrams to extract "Spatial DNA."

## 5. Upgrading the Diagram Agent (`diagram_agent.py`)
- Upgraded the agent to utilize the new `google-genai` SDK and the Gemini 2.5 Flash model.
- **Visual Ground-Truthing:** Added a `Pillow` (PIL) annotation function. When Gemini parses a diagram, it now returns 0-1000 normalized bounding box coordinates for every Zone and Path it identifies. The Python script then physically draws red and blue boxes onto the image and saves a `_annotated.jpg` copy.
- **Successful Benchmark:** Tested the agent on unfinished, manual diagrams of *Parc de la Villette* and *Pershing Square*. 
  - The agent successfully read custom hatch patterns (differentiating water vs. grass) and line weights via the legend.
  - It correctly deduced urban context, such as Pershing Square's relationship to the diagonal DTLA street grid.
  - It output highly structured, 3D-ready JSON containing programmatic zones, path connections, and spatial relationships.

## ⏭️ Next Steps
1. **Manual Diagramming:** Complete the stylized, manual Rhino diagrams for the remaining precedent sites on the 4x5 masterplan grid.
2. **Batch Analysis:** Run the perfected `diagram_agent.py` across all exported PNGs to populate the `archive/diagrams/` folder with their respective JSON blueprints.
3. **Intervention Engine:** Link the extracted "Spatial DNA" JSONs to the semantic search prompt so that generated 3D interventions inherit the specific geometries and logic of their matched precedents.