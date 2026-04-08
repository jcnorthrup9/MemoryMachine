# Memory Machine // Developer Handoff & State Summary

## 🏗️ Architecture Overview
**Memory Machine** is a generative architectural layout tool. 
- **Backend (Python/FastAPI):** Uses a local Ollama (Llama 3) LLM via RAG to select SVG layers from precedent parks based on atmospheric text prompts. The Python engine then mathematically sizes and places these layers to comply with strict APA zoning percentages (e.g., Hardscape 40-60%).
- **Frontend (Vanilla JS/Three.js):** Renders the SVG layouts (`engine2D.js`), mathematically calculates the visible clipped area to update a live Zonal Constraints HUD (`state.js`), and auto-exports documentation (`main.js`).

## 🔄 Current State & Recent Changes (In Codebase)
We have recently introduced several advanced features, but they have caused stability and mathematical compliance issues. The current code includes:

1. **Semantic Grid & APA Rules (AI -> Python):** 
   - `ai_synthesizer.py` now feeds Llama 3 specific APA rules (e.g., Water must be next to Softscape) and asks for semantic locations (`North`, `South-East`, `Center`) instead of arbitrary X/Y coordinates.
   - `urban_engine.py` translates these semantic strings into absolute X/Y base coordinates and applies an organic random jitter.
2. **15-Step Spatial Physics Solver (Python):** 
   - Instead of a static multiplier, `urban_engine.py` uses a 15-step iterative loop to mathematically "test drop" shapes. It calculates how much of the bounding box gets sliced off by the park boundary and dynamically scales the object up until the *visible* rectangular area hits the exact target percentage.
3. **AABB Intersection Math (Frontend JS):** 
   - `state.js` abandons pixel-buffer counting and uses an Axis-Aligned Bounding Box (AABB) overlap algorithm to calculate the HUD percentages. It uses Regex (`/(-?\d+\.?\d*)/g`) to parse SVG paths, explicitly stripping out SVG Arc (`A/a`) parameters to avoid massive false bounding boxes.
4. **Staggered Auto-Exports (Frontend JS):** 
   - `main.js` sequentially triggers SVG and high-res JPG exports with `300ms` asynchronous delays to allow the browser's Garbage Collector to run. `html2canvas` (UI Capture) has been reverted to manual-only to prevent Out-of-Memory (OOM) tab crashes.

## ⚠️ The Symptoms / Bugs to Fix
Despite the rollbacks and recent implementations, the following issues persist:

1. **Browser Tab Crashes / Freezes:** The application is still prone to locking up or crashing the browser tab after the first generation. 
2. **Zonal Compliance Failure:** Elements are spawning wildly out of scale (either tiny or massive). The initial generation almost always results in the Zonal HUD displaying Red (Over/Under limit), meaning the Python Physics Solver and the Frontend AABB math are completely out of sync.

## 🔍 Debugging Leads for the AI Assistant
Please investigate the following areas:

1. **Math Discrepancy (Python vs. JS):** 
   - In `urban_engine.py`, the 15-step solver assumes the layer is a perfect square (`base_side = math.sqrt(base_layer_area)`). 
   - In `state.js`, the AABB calculates the bounding box of the *actual* parsed SVG paths. 
   - *Hypothesis:* If Python scales a layer assuming it's a solid square, but the actual SVG is a thin, winding path, the JS HUD will read a drastically lower percentage than Python intended.
2. **The 15-Step Solver Runaway (`urban_engine.py`):** 
   - Check the loop: `for _ in range(15):`. If an object's center is placed outside the site boundary, or if the target area is too large, the `final_scale` can multiply exponentially. Even with the `max(0.2, min(final_scale, 3.0))` cap, a scale of 3.0 on a large layer might be blowing out the frontend bounds.
3. **Regex Memory Leak / Infinite Loop (`state.js`):** 
   - The `getProgramStats()` function runs a heavy Regex `while ((m = re.exec(d)) !== null)` on every single path of every single SVG layer. During a slider drag or initial render, parsing tens of thousands of coordinates synchronously on the main thread might be causing the browser to lock up or OOM.
4. **Auto-Export Canvas Bloat (`main.js`):** 
   - Check `handleExport('jpg')`. We create a `1224 x 792` canvas, but we might not be clearing the image or canvas contexts properly from memory.

Please review the provided Python logic and Javascript state/rendering files to align the mathematical scaling and resolve the memory bottlenecks.