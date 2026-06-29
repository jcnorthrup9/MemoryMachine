# Memory Machine — Claude Handoff: UI & Visibility Fixes
**Date:** 2026-04-07
**Focus:** Restoring SVG Visibility & Enhancing the Stack Editor

---

## Priority 1: Fix the Invisible Interventions (`engine2d.js`)
Currently, `Engine2D.render()` applies a clip-path to the generated layers: `wrapper.setAttribute('clip-path', 'url(#clip-boundary)');`. 
However, the `<defs>` block that actually creates `#clip-boundary` was accidentally deleted from the file! Because the clip-path doesn't exist, the browser renders the layers completely invisible.
- **Task:** Re-add the `<defs>` block to the top of the `svg` generation in `engine2d.js` using `this.buildBoundaryClipPath(baseSVGEl, ns, 'clip-boundary')`. Make sure this is appended to the `svg` *before* the intervention layers are drawn so they become visible again.

---

## Priority 2: Enhancing the "Added Pieces" UI (`main.js` & `index.html`)
The user requested a clearer way to see exactly which pieces of the park have been added to the canvas. We already have the `stack-editor` list, but it needs to be much more interactive.
- **Task (Clarity):** Update `refreshStackUI()` in `main.js` so each list item clearly displays the source site and the layer type (e.g., "Parc de la Villette — Water Feature").
- **Task (Visibility Toggles):** Add a small "Eye" icon (or toggle checkbox) next to each item in the stack list UI. 
- **Task (Wiring):** Wire that toggle to update the `item.visible` boolean in `MemoryState.stack`. When clicked, it should instantly call `window.renderRemixSVG()` so the user can toggle specific pieces of the generated park on and off to clearly see what was added!

---

## Rules of Engagement
- Focus strictly on `static/js/engine2d.js` and `static/main.js`. 
- Do not touch the Python backend.