# Project Evolution: Memory Machine
**From Procedural Scripts to a Full-Stack Application**

## 1. The Initial State & Critical Bottlenecks
The Memory Machine began as a brilliant computational design thesis, but architecturally, it was a collection of disjointed Python scripts and manual processes. To transition it into a "real app," we had to address three critical bottlenecks:

*   **The Data Bottleneck (Static Files vs. Semantic Search):** 
    *   *The Problem:* The "hunter-gatherer" scripts (`machine_os.py`, scrapers) were dumping qualitative data into flat text and JSON files. Attempting semantic NLP searches over raw text files for prompts like "shallow wading pools" is inefficient and doesn't scale.
    *   *The Solution:* Implementation of a **Vector Database**.
*   **The Rhino Wall (Compute vs. Preview):**
    *   *The Problem:* The `intervention_engine.py` output a JSON payload meant for Rhino 3D, requiring the user to manually open Rhino/Grasshopper to see the result. This broke the interactive user loop.
    *   *The Solution:* Decoupling the *web preview* from the *heavy architectural compute* using **Three.js**.
*   **The Frontend Disconnect:**
    *   *The Problem:* The final output (`temp_html.txt`) was a beautiful but static Brutalist zine.
    *   *The Solution:* An orchestrator backend to dynamically generate and serve content to a live browser interface.

---

## 2. The Architectural Paradigm Shift
We shifted the tech stack to support a modern web application architecture:
*   **Backend/Orchestrator:** `FastAPI` (Python)
*   **Vector Memory:** `ChromaDB` with `sentence-transformers` embeddings
*   **AI Synthesis Core:** `Google Gemini 2.5 Flash` (LLM)
*   **Interactive Frontend:** `Three.js` (3D), `Mermaid.js` (Logic Diagrams), Vanilla JS/CSS

---

## 3. Key Changes Implemented

### A. Data Ingestion Pipeline (`data_ingest.py`)
Instead of relying on raw text, we created a pipeline to parse the scraped data (Bottega Louie, Nakagin, Pershing Square), chunk it, and convert it into vector embeddings stored in a persistent ChromaDB collection. This gave the Memory Machine a true, searchable "memory."

### B. The API Brain (`app.py`)
We wrapped the logic in a FastAPI server, creating two main endpoints:
1.  **`/api/generate`**: The AI Core. It takes user input, performs a semantic similarity search in ChromaDB, feeds the found "memory fragments" to Gemini, and synthesizes a structured JSON containing spatial parameters, an architectural narrative, and diagram logic.
2.  **`/api/harvest`**: A bridge endpoint that allows the web app to trigger the original `machine_os.py` scraping scripts in the background via subprocesses.

### C. The Browser App (`index.html`, `style.css`, `main.js`)
We built a live UI replacing the command-line interface:
*   **Terminal Input:** Accepts natural language spatial desires.
*   **Live 3D Canvas:** Uses Three.js to instantly translate the AI's JSON spatial parameters (width, height, materials, geometry types like `shade_canopy` or `water_garden`) into an interactive 3D preview, completely bypassing the need to open Rhino for initial ideation.
*   **Dynamic Logic Diagrams:** Implemented Mermaid.js to visually map the apophenic translation from *Qualitative Input* -> *Memory Fragment* -> *Quantitative Output*.

---

## 4. Current Status & Next Steps
The application is now a fully functioning prototype running in the browser. It successfully harvests data, recalls memories, synthesizes them into physical forms, and renders them in 3D.

**Upcoming Milestones:**
1.  **The Rhino Bridge:** Standardize the JSON output so that once a user is happy with the Three.js web preview, the payload can be automatically pushed to a Grasshopper watch-folder or a Rhino Compute headless server to bake into the Pershing Square `.3dm` masterplan.
2.  **Dynamic Zine Compilation:** Convert the `temp_html.txt` static layout into a Jinja2 templating system so that approved memory nodes are automatically formatted and published as the final Forensic Palimpsest dossier.