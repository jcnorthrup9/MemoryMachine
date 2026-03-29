# System Architecture Update // Transition to Full-Stack

## 1. The Bottleneck Resolution
The Memory Machine has officially migrated from a disjointed series of Python/Rhino scripts into a cohesive, interactive web application. 
* **The API Brain:** Logic is now wrapped in a FastAPI backend (`app.py`), creating a centralized orchestrator for AI generation and data harvesting.
* **Live 3D Canvas:** By decoupling the preview environment from Rhino, the system now uses **Three.js** to instantly render the AI's hallucinated spatial parameters in the browser. This dramatically tightens the iteration loop.
* **Dynamic Systems Mapping:** Implemented live Mermaid.js diagrams directly into the frontend to visually map the apophenic translation from *Qualitative Input* to *Quantitative Output*.

## 2. Future Roadmap: Diagrammatic Remixing
As the system scales, it is transitioning from purely text-based logic to visual/spatial intelligence:
* **Manual Site Diagramming:** Creating abstract spatial diagrams of harvested precedent sites (Google Maps satellite captures) and a baseline diagram of Pershing Square in its current state.
* **Vision-Language Sub-Agent:** Training a specialized Vision-Language model (Gemini Pro Vision / Claude 3 Opus) to "read" these 2D spatial diagrams.
* **Cross-Pollination:** The sub-agent will synthesize the precedent diagrams with their corresponding spatial data to procedurally "remix" the layouts, generating novel, cross-pollinated interventions for the Pershing Square 3D masterplan.

## 3. Rhino Integration (Next Steps)
Once a user is satisfied with the Three.js web preview, the JSON payload will be beamed directly to a Grasshopper watch-folder or a Rhino Compute headless server to bake the final geometries into the physical `.3dm` masterplan.