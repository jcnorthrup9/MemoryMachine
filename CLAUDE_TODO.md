# 🤖 Claude Autonomous Task List

**Instructions for Claude:**
Read this document top to bottom. Execute the pending tasks sequentially. When a task is fully complete, tested, and functioning, update this file to check the box `[x]` and proceed to the next item.

## ⏳ Pending Tasks

- [ ] **Task 4: The Rhino Export Bridge**
  - **Target Files:** `app.py`, `templates/index.html`, `logic/bake_to_rhino.py`
  - **Objective:** Allow the user to "Bake" the web-generated Three.js intervention directly into their live Rhino `.3dm` masterplan.
  - **Requirements:**
    1. **Frontend:** Update `templates/index.html` (and any associated JS) to include a "Bake to Rhino" button. When clicked, it should send the active generation's JSON data to a new `/api/bake` endpoint.
    2. **Backend:** In `app.py`, create the `/api/bake` endpoint. It must save the incoming JSON data to `data/current_intervention.json` and then execute `logic/bake_to_rhino.py` via a background subprocess.
    3. **Rhino Script:** Create `logic/bake_to_rhino.py`. It should read `data/current_intervention.json` and use `rhinoscriptsyntax` to draw the geometries (boxes, cylinders, spheres) matching the Three.js coordinates. Assign the new geometry to a layer named `MEM_GENERATED`.
    4. **COM Dispatch:** Ensure `logic/bake_to_rhino.py` includes the `win32com` dispatch logic at the bottom of the file (borrowed from `rhino_precedent_generator.py`) so it can successfully inject the commands into an active Rhino 8 session when triggered from the web server.

## ✅ Completed Tasks

- [x] **Task 1: Build the Precedent Scrapbook** (`logic/scrapbook_compiler.py`)
- [x] **Task 2: Vision-Language Diagram Agent** (`logic/diagram_agent.py`)
- [x] **Task 3: Diagrammatic DNA Integration** (`app.py`)