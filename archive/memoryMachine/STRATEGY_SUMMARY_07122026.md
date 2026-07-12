# Design & Integration Strategy Session: Summary (2026-07-12)

This document summarizes the key architectural decisions, bug fixes, and integration strategies discussed for the Memory Machine project.

#### 1. Core Strategy: Automation for Rapid Design Iteration

The primary goal is to leverage the application's automated, data-driven engines to quickly generate complex and defensible design proposals. The designer's role shifts from manual placement of every element to curating the output of these systems, using tools like live painting to refine and guide the results. This is the most effective strategy for locking in a sophisticated design under a tight deadline.

#### 2. Key System Integrations

We identified several key feedback loops to create between the application's independent engines. The goal is to move from a linear pipeline to a more integrated, circular one where the output of one system informs the input of another.

*   **Program Placement → Building Massing:** The `ProgramPlacementEngine` currently places 2D footprints for amenities. The plan is to have it also generate 3D `BuildingSpec` objects for programs that imply a structure (e.g., "Cafe," "Gym"). This will provide immediate 3D massing feedback based on programmatic needs.
*   **Program Placement → Pedestrian Network Growth:** The circulation engine (to be renamed "Pedestrian Network Growth") currently uses painted masks to generate "attraction points." The plan is to enhance this by having it also create strong attractors at the entrances of the placed program zones. This ensures the generated pathways connect directly to the amenities people will be using.
*   **Circulation Network → Terracing Engine:** A future feedback loop was identified where the generated pedestrian network could, in turn, influence the excavation. By creating a "circulation weight" map, the `TerracingEngine` could be encouraged to carve canyons and paths along the primary desire lines, creating a more cohesive landscape.

#### 3. New & Improved Workflows

We planned two major feature enhancements to make the application a more intelligent design partner.

*   **The "Metabolist": An AI Architectural Critic:** We will create a new AI persona named "The Metabolist." Its role is not to answer simple questions, but to provide a qualitative, experiential critique of the generated design. After a design is generated, a summary of the spatial layout (adjacencies of shade, water, amenities, etc.) will be passed to this agent, which will return a short, evocative narrative describing what it might *feel* like to be in that space. This adds a crucial layer of qualitative analysis to the quantitative outputs.

*   **"Precedent Remixer": Integrating the Legacy Diagram Generator:** We analyzed the flaws of the old, disconnected diagram generation tool (`static/main.js`). Its primary issues were its dead-end image output (losing all semantic data), brittle AI connection, and UI/logic bugs (incorrect program percentages, color collisions).

    The plan is to build a new, fully integrated "Precedent Remixer" panel inside the live application. This workflow will:
    1.  Use an LLM to select and collage layers from the existing `data/ParkSVG/` library based on a text prompt.
    2.  Present this collage as an **interactive layer stack** in the UI, allowing the designer to edit, re-order, or replace the AI's suggestions.
    3.  Allow the designer to assign **semantic roles** (e.g., `Excavation`, `Water`, `Shade`) to these precedent layers.
    4.  Convert the final 2D composition into the same paint mask grids that the `TerracingEngine` uses, directly driving the 3D model generation.

    This transforms the old tool's concept from a static image generator into a powerful, interactive starting point for design.

#### 4. Bug Fixes & Clarifications

*   **Programmatic Overlap:** We clarified that the old diagram tool's ability to show >100% area was a simple math bug (double-counting pixels) and not a feature. The *new* system, however, correctly handles overlaps as a feature: the `TerracingEngine`'s `_classify_typology` function uses the intersection of different paint masks (e.g., `water` and an excavated `canyon` zone) to define new, hybrid typologies like `GROTTO`.
*   **Diagram Percentage Bug:** The root cause of the incorrect percentages in `static/main.js` was identified in the `MemoryState.getProgramStats` function. It was iterating through pixels multiple times. The fix is to iterate only once and, for each pixel, identify the single topmost layer, ensuring every pixel is counted exactly once.
*   **Surface vs. Underground Programming:** We established a clear logic for this. **Underground** programs (like `GROTTO`) are emergent properties defined by the `TerracingEngine`'s rules where a specific paint mask (e.g., `water`) overlaps with an area that has been physically excavated. All other programs placed by the `ProgramPlacementEngine` are considered **surface-level** by default.