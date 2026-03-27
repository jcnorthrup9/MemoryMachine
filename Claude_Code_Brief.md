# Memory Machine // Digital Palimpsest
**System Architecture & Enhancement Brief for Claude Code**

## 1. Thesis Overview: The Machine That Forgets
The "Memory Machine" is a computational design project exploring the intersection of human memory decay, artificial intelligence, and procedural architecture. 

Memory is not a static archive but an unstable process of encoding, retrieval, and decay. In parallel, AI systems (like LoRAs and LLM hallucinations) operate with inherent biases, missing data, and the capacity to mistake noise for meaning—a phenomenon known as *Apophenia*. 

Architecture contains memory. Spaces are torn down, modified, and rebuilt, leaving behind "witness marks." Treating degradation not as a failure, but as a generative starting point, the Memory Machine harvests fragmented data (reviews, historical texts, spatial coordinates) and procedurally rebuilds spaces. It binds the logic of machine learning, dementia, and architectural decay, resulting in a synthesized "Forensic Palimpsest."

## 2. Current System Pipeline
The current architecture is divided into four distinct phases:

1. **Data Harvest (`Phase 1`):** Autonomous discovery using scripts (`machine_os.py`, `free_scraper.py`, `satellite_scraper.py`, `osm_scraper.py`) to scrape historical archives, visitor reviews (Yelp, TripAdvisor), and spatial coordinates.
2. **Processing & Extraction (`Phase 2`):** Parsing qualitative data (atmospheric memory fragments) and quantitative data (hard dimensional limits). Extracts text sentiment and compiles a `memory_manifest.json`.
3. **The Rhino 3D Canvas (`Phase 3`):** Procedurally rebuilding structural massing via scripts (`rhino_universal.py`, `site_reconstruction.py`, `intervention_engine.py`) to generate a 3D masterplan.
4. **Archival & Synthesis (`Phase 4`):** Applying memory decay and material inference via AI visual workflows (Flux/LoRAs), and compiling the forensic architectural dossier via `deck_compiler.py` into a zine/HTML presentation.

## 3. The Target Site: Pershing Square
Pershing Square is a historic five-acre public park in the heart of Downtown Los Angeles. It has undergone constant demolition and redesign over the last century (most notably Ricardo Legorreta’s 1992 postmodern intervention). 

Because it is currently being erased once again, it represents the *ultimate urban palimpsest*—a site continuously overwritten, perfectly embodying the unstable, shifting nature of human and machine memory.

## 4. Proposed Feature: Qualitative Cross-Pollination Engine
**Goal:** We want to enhance the Memory Machine so it can accept natural language inputs describing *qualitative site conditions*, search the database/web for matching architectural spaces, extract their logic, and "cross-pollinate" them as new physical objects/interventions onto the Pershing Square masterplan.

### User Flow & Expected Output:
1. **Natural Language Input:** 
   * The user inputs a normal language query based on desired qualitative experiences. 
   * *Example:* "I want a space with lots of shade, shallow wading pools, and water features that create a pleasant acoustic hum."
2. **Semantic Search & Harvest:**
   * The system parses the prompt and searches external sources (or the existing scraped review database, e.g., TripAdvisor/Yelp data) to find real-world spaces that match these atmospheric qualities.
3. **Architectural Extraction:**
   * The system extracts the structural and spatial logic of the found spaces (e.g., depth of the pool, height of the canopy, materials).
4. **Synthesis & Generation:**
   * **The Object:** The system generates a structured JSON object (a "Memory Node" or "Intervention") containing the physical parameters needed to build this space in Rhino 3D.
   * **The Diagram:** The system dynamically generates a Mermaid.js diagram illustrating the logic of how the qualitative data was translated into structural parameters.
   * **The Explanation:** An AI-generated architectural narrative explaining what the object is, the witness marks it brings from its original site, and how it collides with the existing Pershing Square palimpsest.

## 5. Instructions for Claude Code
As an autonomous AI coding assistant, your task is to design and implement the logic for the **Qualitative Cross-Pollination Engine**. 

**Key Deliverables:**
1. **NLP Parser & Search Script:** Write a Python script (e.g., `qualitative_search.py`) that takes a natural language prompt, calls the Gemini/Claude API to extract search keywords, and cross-references them against our scraped review data or performs an OS web search.
2. **Object Generator (`intervention_engine.py` update):** Create a function that translates the search results into a structured JSON payload representing 3D spatial parameters (dimensions, coordinates, materials) meant for Rhino.
3. **Markdown/HTML Output:** Write a function that takes the generated JSON and outputs:
   * A beautifully formatted explanation of the intervention.
   * A Mermaid diagram mapping the flow from *Qualitative Input* -> *Memory Source* -> *Quantitative Output*.

Please review the current directory structure and existing scripts (like `deck_compiler.py`) to ensure seamless integration with the existing Archival & Synthesis phase.