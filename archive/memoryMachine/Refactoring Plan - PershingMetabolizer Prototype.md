# Refactoring Plan: PershingMetabolizer Prototype

**Date:** June 29, 2026
**Author:** Gemini Code Assist
**Status:** Plan Approved. Implementation Pending.

---

## 1. Goal

Transform the static `PershingMetabolizer_Prototype` from a conceptual diagram into a dynamic, data-driven tool. The refactored prototype will accurately render intervention zones (e.g., shade, green space, excavation areas) onto the true geometric footprint of Pershing Square, driven by a new, standards-based analytical engine.

## 2. Strategy: Two-Part Plan

The refactoring will proceed in two parallel steps to cleanly separate data analysis from visualization.

*   **Part 1: Data Generation (Python):** A new script will be created to analyze the site and export all necessary data into a single, clean JSON file.
*   **Part 2: Data Visualization (JavaScript):** The prototype's `index.html` will be rewritten to fetch the JSON file and render its contents dynamically using `three.js`.

This approach ensures that the analytical logic can be refined independently in Python, with the visual prototype simply needing a page refresh to display the latest results.

---

## 3. Part 1: Create a Data Generation Script

A new Python script, `generate_prototype_data.py`, will be created. Its sole responsibility is to prepare data for the visualization.

*   **Parse Real Site Boundary:** It will load `data/PershingMetabolizer/parkSVG/pershingRhinoPlanView.svg` and extract the precise SVG path string for the park's outline.
*   **Analyze Needs:** It will incorporate logic from `urban_engine.py` and `urban_design_guidelines.md` to calculate the deficit/need for `green_space`, `shade`, and `hardscape` based on real-world standards.
*   **Identify Intervention Zones:** It will use the core logic from `urban_interference_solver.py` to identify high-priority zones for digging ("punctures") based on structural data, transit proximity, and amenity pressure.
*   **Export `site_data.json`:** The script will output a single `site_data.json` file into the `PershingMetabolizer_Prototype` directory. This file will contain all the necessary data for rendering, including the boundary path and arrays of polygons for `shade_zones`, `green_space_zones`, and `dig_zones`.

## 4. Part 2: Refactor the Prototype's JavaScript

The JavaScript currently inside `PershingMetabolizer_Prototype/index.html` will be refactored to be a data-driven renderer.

*   **Load External Data:** The script will be modified to fetch the `site_data.json` file on page load.
*   **Render Real Boundary:** The hardcoded 810x810 ft square will be removed. The script will use `three.js`'s `SVGLoader` to create the park's base shape from the SVG path string provided in the JSON file.
*   **Render Data Layers:** The prototype will loop through the data arrays in the JSON (e.g., `shade_zones`, `dig_zones`) and render them as distinct, color-coded geometries on top of the accurate site model. The existing "sinking" logic will be adapted to create voids or extrusions based on the `dig_zones` data.

## 5. Outcome

This plan will result in a clean, robust, and accurate workflow. The Python backend will handle all complex analysis, and the client-side prototype will serve as a lightweight, fast, and precise visualization tool.
