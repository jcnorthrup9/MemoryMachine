# Memory Machine Integration Plan - 2026-07-12

This is a plan to better integrate the disparate systems in the Pershing Metabolizer application, based on a planning session. This file is intended as a handoff for an AI coding assistant.

### 1. Connect Program Placement to Building Massing

-   [ ] **Task:** Modify the `ProgramPlacementEngine` to output 3D building specifications, and have the main API pipeline consume them.
-   **Files to Modify:**
    -   `d:\MemoryMachine\logic\program_placement.py`
    -   `d:\MemoryMachine\logic\pershing_api.py`
-   **Implementation Steps:**
    1.  **In `logic/program_placement.py`:**
        -   Define a `BUILDING_CATEGORIES` set containing `{"enrichment_civic", "health_care"}`.
        -   Define a `DEFAULT_BUILDING_HEIGHT_FT` constant (e.g., `15.0`).
        -   Inside the `place_programs` function, after a program's bays have been determined, check if its `category` is in `BUILDING_CATEGORIES`.
        -   If it is, calculate the bounding box of the `placed_bays` to find the min/max grid coordinates.
        -   Convert these grid coordinates to real-world feet to define the `x_ft`, `y_ft`, `width_ft`, and `depth_ft` of the building.
        -   Add a new `building_spec` key to the program's result dictionary, containing a dictionary with the calculated dimensions and the default height. If the program is not a building category, this should be `None`.
    2.  **In `logic/pershing_api.py`:**
        -   Locate the `rebuild` function.
        -   After calling `get_program_zones()` to get the placed amenity zones, extract the `building_spec` from each zone that has one.
        -   The `rebuild` function's `RebuildParams` already accepts a `buildings: list[BuildingSpec]`. Append the new programmatically-generated building specs to this list before passing the combined list to the `_run_pipeline` function. A good approach is to extend the `params.buildings` list in place before the pipeline call.

### 2. Rename Circulation Engine

-   [ ] **Task:** Rename the "Circulation Colonization" feature to "Pedestrian Network Growth" for clarity.
-   **Files to check:**
    -   `d:\MemoryMachine\circulation_network.py`: Rename the class `CirculationNetworkEngine` and update its docstring and any internal comments.
    -   `d:\MemoryMachine\logic\pershing_api.py`: Update the `grow_network` endpoint name and/or comments if necessary to reflect the new name.
    -   Frontend: Check `ParamPanel.jsx` and any other UI components for labels or button text that use the old name and update them.

### 3. Fix Legacy Diagram Percentage Calculation

-   [ ] **Task:** Correct the pixel-counting logic in the old application's program statistics calculation to prevent double-counting and ensure accuracy.
-   **Files to Modify:**
    -   `d:\MemoryMachine\static\main.js`
-   **Implementation Steps:**
    1.  Locate the `MemoryState.getProgramStats` function.
    2.  Rewrite the core logic to iterate through the canvas pixels **once**.
    3.  A robust method is to render the entire SVG stack to a hidden offscreen canvas.
    4.  Then, get the `imageData` from that canvas and loop through the pixel data array.
    5.  For each pixel, use its color to determine which single category it belongs to (the one on top).
    6.  Increment the area for that single category only. This prevents double-counting and ensures the final percentages sum to 100%.

### 4. Implement AI Critic Persona: "The Metabolist"

-   [ ] **Task:** Create a new AI agent persona for qualitative design critique.
-   **Files to Modify:**
    -   `d:\MemoryMachine\logic\juror_chat.py`
    -   `d:\MemoryMachine\logic\pershing_api.py`
-   **Implementation Steps:**
    1.  **In `logic/juror_chat.py`:**
        -   Add a new `CRITIC_PERSONA_SYSTEM_TEXT` constant with the persona and instructions for generating an experiential narrative.
        -   Create a new function `critique_design(spatial_summary: dict) -> str` that takes a simplified layout, formats it into a prompt with the new persona, calls Ollama, and returns the critique text.
    2.  **In `logic/pershing_api.py`:**
        -   In the `rebuild` function, after all engines have run, create a `spatial_summary` dictionary from the `voxels` and `program_zones` data. This summary should contain high-level information like "a large area of `SHADE` is located in the northeast" or "a `GROTTO` is adjacent to a `CIRCULATION` path."
        -   Call the new `critique_design` function with this summary.
        -   Add the returned "critique" text to the main response payload so the frontend can display it.