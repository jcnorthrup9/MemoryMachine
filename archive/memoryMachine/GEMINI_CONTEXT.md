# Project Context & Session Briefing: Memory Machine Midterm Mutation

## 1. Project Overview
* **Project Name:** Memory Machine (System 9.0)
* **Site:** Pershing Square, Los Angeles (Constrained by the 1951 subterranean parking garage structure).
* **Core Objective:** Evolve the project from a passive subterranean archive (modular cassette bays) into an **Urban-Environmental Metabolic Engine**. The system must computationally calculate where and how to puncture/excavate the park surface based on surrounding contextual pressures, blurring the line between surface landscape and subterranean infrastructure.

---

## 2. Technical Infrastructure
* **Figma Frontend:** A custom local development Figma plugin controlled via `code.ts`. It generates automated presentation layouts ($1920 \times 1080$ frames) using absolute coordinate layouts and hardcoded styling variables (`#050505` background, `#fff4ca` accent headers).
* **Backend Pipeline Goal:** A Python/Rhino/Grasshopper engine that parses a $30' \times 30'$ spatial grid mapping Pershing Square to calculate structural interventions.

---

## 3. Today's Core Task
We are setting up the integration between our structural translation data (JSON format) and the Figma generation engine to visualize multiple system iterations quickly, eliminating slow design decision-making tasks.

### Active Data Streams (To be factored into logic):
* **Vector A (Transit Flux):** Proximity to the underground Metro station core.
* **Vector B (Urban Envelope):** Surrounding building heights (solar exposure/enclosure).
* **Vector C (Programmatic Assets):** Neighboring hospitality (hotels) and food deficits.
* **Vector D (Structural Boundaries):** Load bearing limits/column lines of the 1951 garage lid.

---

## 4. Sidecar AI Action Items (TODO List)

### [ ] Task 1: Verify Figma Manifest & Build Loop
* Check the workspace root for `manifest.json` and ensure it targets the correct compiled JavaScript output file.
* Help me run the compiler watch command (`npm run watch` or `npx tsc -w`) in the VS Code terminal to sync code changes dynamically to Figma.

### [ ] Task 2: Review `code.ts` Capabilities
* Look at the existing `code.ts` file. 
* Note how it maps specific JSON keys (`title_slide`, `workflow_slide`, `dual_text_slide`) into custom frames and geometries on the canvas.

### [ ] Task 3: Ingest Next Iteration Payload
* Prepare to ingest a test JSON structure containing our new urban vector descriptions, data parameters, and structural cut logic definitions.
* Help me paste this payload into the plugin's active UI panel inside the Figma Desktop App to verify the canvas renders the system diagram accurately.