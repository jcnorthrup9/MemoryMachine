# Weekly Progress Update // Memory Machine

## 1. Case Study Research Integration
Over the past week, extensive qualitative and quantitative data was harvested, parsed, and integrated into the generative pipeline for our three primary case studies. Each explores a different facet of human memory decay, structural palimpsest, and atmospheric hallucination:

*   **Bottega Louie (Los Angeles):** 
    *   **Focus:** Sensory excess and acoustic reverberation.
    *   **Data Harvested:** Parsed hundreds of visitor reviews extracting atmospheric qualities (high vaulted ceilings, noise, vibrant displays) alongside structural massing data. 
    *   **Goal:** Testing the translation of qualitative, atmospheric memories into rigid, quantitative architectural geometry.
*   **O.T. Johnson Building (Los Angeles):**
    *   **Focus:** Architectural dissonance and the physical palimpsest.
    *   **Data Harvested:** Historical and architectural records detailing its 1902 Romanesque Revival origins, subsequent alterations, and the 2007 fire that exposed its long-hidden architectural "witness marks."
    *   **Goal:** Exploring how architecture never fully erases its past, but rather hides it beneath new interventions.
*   **Nakagin Capsule Tower (Tokyo):**
    *   **Focus:** Algorithmic modularity and urban entropy.
    *   **Data Harvested:** Structural logic parameters (140 capsules, 2.5x4.0x2.5m constraints) and qualitative reviews describing the retro-futuristic decay.
    *   **Goal:** Utilizing its strict Metabolism design as a direct mirror to computational architecture and procedural generation.

## 2. Pershing Square: The Cross-Pollination Strategy
The conceptual direction for our final masterplan site, **Pershing Square**, has evolved. Recognized as the ultimate urban palimpsest due to its constant cycle of demolition and redesign, the site is now being used as a testbed for architectural cross-pollination.

*   **The Problem:** Review data harvested for Pershing Square highlights a dysfunctional public space—criticized for its fortress-like concrete walls, lack of shade, confusing elevation changes, and overall disconnect from the surrounding pedestrian flow.
*   **The New Direction:** The Memory Machine pipeline will attempt to **cross-pollinate Pershing Square with spatial parameters and atmospheric qualities extracted from successful, highly-enjoyed public spaces**. 
*   **Current Site Data Extraction:** 
    *   Successfully executed OpenCV contour analysis on satellite imagery to map the exact X/Y coordinates of existing trees.
    *   Harvested OpenStreetMap (OSM) GIS data to procedurally generate the surrounding urban context in Rhino.
    *   Compiled a memory manifest highlighting the spatial failures that the new cross-pollinated interventions will need to overwrite or negotiate with.

## 3. Generative Pipeline & Presentation Updates
In order to properly document and visualize these new findings, the system's output mechanisms were heavily upgraded:

*   **Dynamic Deck Compiler (`deck_compiler.py`):** Added new slide typologies (`dual_text_slide`, `workflow_slide`, and `text_and_mermaid_slide`) to better display the juxtaposition of qualitative "hallucinations" alongside hard quantitative binary/CSV data.
*   **Live Systems Mapping:** Replaced static workflow images with live `Mermaid.js` diagrams that render directly in the HTML presentation.
*   **Figma Integration:** Completely rewrote the TypeScript logic for the Figma plugin (`code.ts`) so that it perfectly mirrors the new dynamic HTML layouts, including auto-scaling image grids and justified typography.
*   **AI Engine Migration:** Upgraded the AI summarization logic to use the new `google-genai` SDK, ensuring the system remains stable as we begin asking Gemini to hallucinate cross-pollinated spatial parameters.

## Daily Log: March 25, 2026
### Code Changes & System Upgrades
* **Merge Conflict Resolution:** Cleanly resolved Git branching conflicts in `deck_compiler.py`, prioritizing new dynamic slide layouts (`dual_text_slide`, `workflow_slide`) while restoring missing image compilation logic.
* **Gemini SDK Migration:** Upgraded `deck_compiler.py` from the deprecated `google-generativeai` library to the officially supported `google-genai` package for stable architectural summarization.
* **Live Render Integrations:** Implemented the `webbrowser` module to auto-launch the compiled HTML presentation, and swapped the static system pipeline image for a live, dark-themed Mermaid.js diagram.
* **Figma Plugin Overhaul:** Rewrote the TypeScript engine (`code.ts`) to perfectly mimic HTML/CSS flexbox properties, dynamic image scaling, `1.4` line-heights, and justified typography.
* **Data Pipeline Fixes:** Repathed Bottega Louie references to specific `.jpg` assets, integrated the new `pershing_square_hero_resized.webp` image, and corrected layout clipping issues for quantitative text.
* **Obsidian Bridge:** Built `obsidian_logger.py` to seamlessly append these markdown logs directly into the local Obsidian Vault.