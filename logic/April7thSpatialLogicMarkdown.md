# TECHNICAL REPORT: SPATIAL LOGIC REFACTOR (v1.3)
**Project:** Memory Machine  
**Author:** John C. Northrup II  
**Date:** April 2026  
**Subject:** Transition from Heuristic Approximation to Geometric Precision  

---

## 1. THE LEGACY LOGIC: "The 15-Step Square Solver"
**Status:** Deprecated (Logic Version 1.2)

### Description
The initial solver utilized a heuristic "test-drop" method to predict the scale of architectural interventions.

* **Geometry Assumption:** All incoming SVG layers were simplified into a solid $255 \times 255$ square (Area: $65,000$ units).
* **The Loop:** A 15-step iterative process adjusted the `final_scale` by measuring how much of the square's bounding box was clipped by the site boundary.
* **Failure Mode:** Because actual SVG paths are organic (thin lines, clusters, and winding curves) rather than solid squares, the solver would "run away," over-scaling elements to compensate for the "missing" square area.

---

## 2. THE REFACTORED LOGIC: "Centroid & Shoelace Integration"
**Status:** Current Implementation (Logic Version 1.3)

### Description
The refactored logic replaces "guessing" with a direct geometric handshake between the backend (Python) and frontend (JS).

* **Shoelace Formula:** Python now calculates the "True Area" of actual SVG path coordinates ($Area = \frac{1}{2} | \sum (x_i y_{i+1} - x_{i+1} y_i) |$), ensuring the solver knows the exact "ink" coverage.
* **Density Ratio:** The engine calculates the ratio of "True Area" to "Bounding Box Area." This allows the solver to accurately predict how large a winding path needs to be scaled to hit a specific zoning target.
* **Semantic Centroid Anchoring:** All elements are anchored to the **Pershing Square Centroid** (the mathematical center of the `BOUNDARY` layer). 

---

## 3. COMPARATIVE ANALYSIS

| Feature | Legacy (v1.2) | Refactored (v1.3) |
| :--- | :--- | :--- |
| **Area Math** | Square Bounding Box ($Area = side^2$) | Shoelace Formula (True Polygon Area) |
| **Origin** | Canvas Center ($0,0$) | Site Centroid (Boundary-Specific) |
| **Placement** | Arbitrary X/Y coordinates | 3x3 Semantic Grid (North/South/East/West) |
| **HUD Sync** | Constant Drift ("Red HUD") | Verified Handshake via `solved_area_px` |
| **Stability** | High Regex overhead; OOM Crashes | Numeric caching; Main-thread optimization |

---

## 4. ARCHITECTURAL IMPACT
By moving to this logic, the **Memory Machine** transitions from a 2D collage tool to an **Architectural Solver**:

1.  **Zonal Compliance:** It ensures that when the AI proposes "30% Softscape," the physical area is mathematically verified against Pershing Square’s true bounds.
2.  **Design Intent:** Semantic Grid logic allows for directional intent (e.g., "Cluster program at the North edge") rather than random dispersion.
3.  **3D Readiness:** Precisely calculated 2D areas and overlaps translate directly into accurate 3D massing for the `geometry_engine` (Mounds, Basins, and Canopies).

---
*End of Report*