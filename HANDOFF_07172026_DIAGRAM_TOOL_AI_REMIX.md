# Handoff — 2026-07-17: diagram_tool gets AI Remix, folder-wiring correction, launcher fix

No blocking issues — everything below is verified working, safe to build on directly.

## 1. `diagram_tool` (port 8006) gained a conversational AI Remix panel

`diagram_tool/` previously had **no AI code at all** (confirmed via full read of every file in the tree) — it only let you manually pick a precedent site + `<g>` layer and place it with X/Y/scale/rot sliders. The AI-curated "Precedent Remixer" (prompt → LLM picks 5 layers → narrative) already existed, but only in the **main** app (port 8000: `logic/pershing_api.py`'s `remix_precedent()`, `PrecedentRemixerPanel.jsx`).

diagram_tool is now the intended home for AI-remixed diagrams (per the user), made **conversational** and reusing the existing pipeline rather than new AI plumbing:

- **New `logic/diagram_remix_chat.py`** — `DiagramRemixChatAgent`, mirrors `logic/juror_chat.py`'s `JurorChatAgent` history pattern (bounded in-process turn history folded into a composite prompt string). Wraps `logic.ai_synthesizer.generate_spatial_seed()` + `logic.urban_engine.remix_layers()` completely unmodified.
- **`diagram_tool/app.py`**: new `POST /api/remix-diagram` (one turn) + `POST /api/remix-diagram/reset` (clears history, wired to the existing CLR button).
- **New `diagram_tool/static/js/remixChat.js`**: converts the API's `transform.x_frac/y_frac` (fraction of base boundary size) into `MemoryState.stack`'s `transform.x/y` (absolute pixel offset from boundary center) — same math `ingest_diagram_svg.py`'s `rasterize_precedent_layers()` does server-side for the main app, done client-side here since the boundary bbox only exists in the browser. Each remix turn **replaces** non-locked stack items, keeping locked base-context rows (BOUNDARY/STREET/etc.) untouched.
- New "AI REMIX" collapsible panel in `diagram_tool/index.html`/`style.css` (own `.remix-editor` class — don't reuse `.stack-editor`, the existing toggle handlers use `querySelector` which would fight over which element to collapse).
- **Verified live** with a real Ollama round-trip: sent a prompt, got a real narrative + 5 layer picks; sent a follow-up, and the response explicitly referenced the prior turn ("continues to inspire," "still Parc Villette"), confirming history-folding actually works.

Existing manual site-picker/slider placement and "Export SVG" are untouched.

## 2. Folder-wiring correction — `remixedGeneratedSVGs`/`remixedGeneratedPNGs` belong to diagram_tool, not the 3D viewport

Earlier the same day, "Export Current View" (the 3D viewport's PNG/Blender-line-art-SVG export in the main app) was briefly wired to save into `data/PershingMetabolizer/parkSVG/remixedGeneratedSVGs`/`remixedGeneratedPNGs` — a wrong guess at what those folder names meant. **Reverted:**

- `logic/pershing_blender.py`: Line Art SVG lives only in `outputs/blender_headless/` again (no copy elsewhere).
- `app.py`: `PERSHING_EXPORT_PNG_DIR` now points at `outputs/pershing_current_view_png/`.

If you see any other code/docs referencing `remixedGeneratedSVGs`/`remixedGeneratedPNGs` as a 3D-viewport-export target, that's stale — those folders are diagram_tool's AI Remix output home now (item 1 above).

## 3. `start.bat`/`start.sh` repointed to launch diagram_tool

Both scripts previously ran a plain `http.server` serving `PershingMetabolizer_Prototype/index.html` — explicitly marked "superseded" in `PIPELINE_STATUS_AND_NEXT_STEPS.md`, effectively dead weight. They now launch `diagram_tool/app.py` (venv Python, falls back to system Python with a warning about `pip install -r requirements.txt`) and auto-open `http://127.0.0.1:8006`.

Two real bugs hit and fixed while verifying `start.bat`, worth knowing if you touch batch scripts in this repo again:
- `::`-style comments break if a `(`/`)` pair spans multiple comment lines (classic cmd.exe footgun) — switched to `REM` for the multi-line header comment.
- `timeout /t N` fails with "Input redirection is not supported" under any redirected/piped stdin (automation, remote invocation, some non-interactive contexts) even with `/nobreak`. Replaced with the standard portable delay trick, `ping -n 3 127.0.0.1 >nul`, which never touches stdin.

Reminder for both of us: **root `npm run dev`** still launches the OLD Digital Palimpsest app (root `index.html` + `static/main.js`) — that's a third, separate thing, not touched by any of this.
