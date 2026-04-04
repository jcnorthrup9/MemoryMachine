# Memory Machine // App Scaffolding & AI Core
**Brief for Claude Code**

## 1. Project Goal
We are transitioning the "Memory Machine" from a series of Python scripts into a full-stack web application. The goal is to create an interactive experience where a user can input a natural language prompt describing a spatial quality, and the application will generate a 3D architectural object, a narrative, and a logic diagram in response.

## 2. Current App Architecture
The project manager has set up the following application scaffold:

*   **Backend (`app.py`):** A **FastAPI** server that serves the frontend and has a single API endpoint: `POST /api/generate`.
*   **Frontend (`templates/index.html`):** An HTML page with a **Three.js** canvas for 3D rendering, a terminal-style input for user prompts, and containers for a narrative and a Mermaid.js logic diagram.
*   **Client-side Logic (`static/main.js`):** JavaScript that handles user input, calls the `/api/generate` endpoint, and renders the 3D objects, narrative, and diagram returned by the API.

## 3. Your Task: Implement the AI Core in `app.py`

Your primary task is to replace the **mock response** in the `app.py` file's `/api/generate` endpoint with the real AI-powered logic.

### Key Deliverables:

1.  **Data Ingestion & Vectorization:**
    *   Create a new Python script (e.g., `data_ingest.py`).
    *   This script should read the raw text files from our `data/` directory (like `bottega_louie_reviews.txt`, `ot_johnson_data.txt`, etc.).
    *   Using a sentence-transformer library and a local vector database like **ChromaDB**, convert these text files into vector embeddings and store them. This only needs to be run once to populate the database.

2.  **Implement the `/api/generate` Endpoint Logic:**
    *   **Receive Prompt:** Take the `payload.prompt` from the user.
    *   **Semantic Search:** Convert the user's prompt into an embedding and query the ChromaDB vector store to find the most semantically similar text chunks (the "memory fragments").
    *   **LLM Synthesis:** Construct a new prompt for an LLM (like Gemini or Claude). This prompt should include:
        *   The original user query.
        *   The top 3-5 memory fragments found in the semantic search.
        *   A clear instruction to synthesize this information into a set of simple 3D geometric parameters (for Three.js), an architectural narrative, and a Mermaid.js diagram.
    *   **Return Structured JSON:** Parse the LLM's response and return it in the exact JSON format the frontend expects: `{"status": "...", "narrative": "...", "geometries": [...], "diagram": "..."}`.

Please start by writing the `data_ingest.py` script. We need to get our qualitative data into a searchable format first.