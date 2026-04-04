# 🏛️ Memory Machine // System Architecture

This document serves as the master rulebook for the "Memory Machine" application. AI agents and developers must strictly adhere to these architectural standards when modifying or expanding the codebase.

## 1. Core Philosophy & Vibe
- **Forensic Palimpsest:** The app is a forensic tool. It layers memories, erasures, and physical space on top of each other. 
- **Brutalist / Functional Aesthetic:** The UI should look like an architectural dossier or a piece of technical software. 
- **No Fluff:** Avoid rounded corners (`border-radius`), drop shadows, gradients, or playful animations unless specifically requested for a glitch effect.

## 2. Tech Stack Constraints
- **Frontend:** Vanilla JavaScript, HTML5, and CSS3. **NO React, Vue, or other frontend frameworks.**
- **Backend:** Python and FastAPI (`app.py`).
- **3D Engine:** Three.js (WebGL).
- **Vector Math:** Rely on standard SVG bounding box logic and Three.js matrices.
- **AI Integration:** Google Gemini via the `google-generativeai` SDK.
- **Vector Database:** ChromaDB.
- **Diagrams:** Mermaid.js.

## 3. UI & CSS Style Guide
All new UI elements must use the established CSS variables located in `static/style.css`.

- **Palette:**
  - `--bg`: Background color (dark/light toggled).
  - `--surface`: Elevated surfaces like cards or inputs.
  - `--panel`: Main layout divisions (left panel, header).
  - `--accent`: The primary interaction color (e.g., `#fff4ca`).
  - `--text`: Main text color.
  - `--muted`: Secondary or deactivated text/borders.
  - `--border`: Standard 1px solid separator.
- **Typography:** 
  - Strictly `Courier New`, `Courier`, `monospace`. Do not import web fonts.
  - Elements should favor uppercase letters with wide letter-spacing (`0.15em` to `0.25em`) for labels.

## 4. The Presentation Portal (Routing Structure)
The application uses an iframe-based portal system to keep code modular while presenting a single unified interface.

- **`/` (Root):** Serves `templates/index.html` (The Remix Engine).
- **`/diagrams`:** Serves `templates/diagram_viewer.html`.
- **`/archive`:** A static mount serving generated HTML files from the `html/` directory.
  - `/archive/digitalPalimpsest.html` (The Digital Zine)
  - `/archive/precedent_scrapbook.html` (The Scrapbook)
  - `/archive/presentation_deck.html` (The Slide Deck)

## 5. Event-Driven Autonomous Compilers
The Zine and Scrapbook act as "living documents." They are not manually compiled. 
- Whenever a user finalizes a composition and triggers a "Bake" action via FastAPI, the backend automatically triggers `zine_compiler.py` and `scrapbook_compiler.py` via subprocesses. 
- The iframe portal ensures the user can instantly view the freshly generated HTML output without leaving the app.

## 6. The 2D-to-3D Math Bridge
- 2D SVG footprints scale exactly to the Pershing Square base map (`getBoundaryBBox()`).
- **SVG_SCALE = 0.04**: This constant is used to map 2D SVG points (pts) directly into Three.js world coordinates (units). Do not alter this scale without recalibrating the entire camera frustum and OBJ loader.