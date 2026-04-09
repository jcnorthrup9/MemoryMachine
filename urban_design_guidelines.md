# URBAN DESIGN GUIDELINES // MEMORY MACHINE v1.4
## Site: Pershing Square, DTLA

This document serves as the geometric and programmatic logic for the Cross-Pollination Engine. All generated interventions must adhere to the zonal constraints and primitive hierarchies defined herein.

---

## 1. PROGRAMMATIC ZONES (ZONAL_METADATA)

These zones define the qualitative and quantitative targets for any spatial remix. 

| Zone ID | Label | Target % | Description | Hex Color |
| :--- | :--- | :--- | :--- | :--- |
| **SOFT_01** | Softscape | 30–50% | Permeable surfaces, lawn, and climate-resilient planting. | #4CAF50 |
| **HARD_01** | Hardscape | 40–60% | Civic plazas, transit-oriented paving, and flexible gathering space. | #9E9E9E |
| **PROG_01** | Active Program | 10–20% | Kiosks, stages, playgrounds, or designated social nodes. | #FF9800 |
| **BLUE_01** | Blue Space | 2–10% | Water features, shallow wading pools, and acoustic buffers. | #03A9F4 |

---

## 2. GEOMETRIC PRIMITIVES

The engine uses three primary "Geometries" for 3D massing.

### ◆ The Mound (LANDSCAPE_MOUND)
- **Logic:** Topographic interventions that provide shade and seating.
- **Max Height:** 12.0m
- **Materiality:** Grass, Rammed Earth, or Recycled Concrete.

### ◆ The Canopy (FLOATING_CANOPY)
- **Logic:** High-level shade structures that cross-pollinate with existing building heights.
- **Clearance:** Minimum 4.5m for pedestrian flow.
- **Materiality:** Perforated Metal, ETFE, or Tensile Fabric.

### ◆ The Basin (SUNKEN_PLAZA)
- **Logic:** Sub-surface gathering areas for acoustic isolation from 5th Street traffic.
- **Depth:** Maximum -3.0m
- **Materiality:** Polished Stone or Blue Glass.

---

## 3. SPATIAL RELATIONSHIPS

1. **The Edge Rule:** No active program (`PROG_01`) shall be placed within 5.0m of the site boundary to maintain pedestrian clearways. Do NOT assign `PROG_01` to extreme corners.
2. **The Sightline Rule:** Interventions taller than 8.0m must maintain a 15.0m clearance from the Biltmore Hotel axis.
3. **The Water Logic:** All `BLUE_01` features must be adjacent to at least one `SOFT_01` zone for natural filtration logic. If `BLUE_01` is selected, it must share the exact same grid location as `SOFT_01`.
4. **The Grid Rule (Semantic Placement):** All generated interventions must be explicitly assigned to one of the 9 Semantic Grid locations: `North`, `North-East`, `East`, `South-East`, `South`, `South-West`, `West`, `North-West`, or `Center`.

---

## 4. METADATA FOR AI SYNTHESIS

When the AI generates a 'Spatial Seed', it must refer to these Precedent Sites for specific geometry types:

- **PershingSquare:** Default Context / Rectilinear Grid.
- **ParcdelaVillette:** Point/Grid Logic (Follies).
- **ZaryadyePark:** Hybrid/Topographic Logic (The Mound).
- **Schouwburgplein:** Modular/Elevated Logic (The Platform).

---

## 5. REVISION HISTORY
- **v1.0:** Initial draft for Pershing Square.
- **v1.1:** Integrated hex codes for 2D Engine compatibility.
- **v1.2:** Added Site Precedent metadata for cross-pollination logic.
- **v1.3:** Transition from Heuristic Approximation to Geometric Precision.
- **v1.4:** Re-integrated Urban Planner rules with Semantic Grid logic.

---

## 6. TECHNICAL REPORT: SPATIAL LOGIC REFACTOR (v1.3)
**Subject:** Transition from Heuristic Approximation to Geometric Precision  

### 6.1 THE LEGACY LOGIC: "The 15-Step Square Solver"
The initial solver utilized a heuristic "test-drop" method to predict the scale of architectural interventions.
* **Geometry Assumption:** All incoming SVG layers were simplified into a solid $255 \times 255$ square (Area: $65,000$ units).
* **The Loop:** A 15-step iterative process adjusted the `final_scale` by measuring how much of the square's bounding box was clipped by the site boundary.

### 6.2 THE REFACTORED LOGIC: "Centroid & Shoelace Integration"
The refactored logic replaces "guessing" with a direct geometric handshake between the backend (Python) and frontend (JS).
* **Shoelace Formula:** Python now calculates the "True Area" of actual SVG path coordinates ($Area = \frac{1}{2} | \sum (x_i y_{i+1} - x_{i+1} y_i) |$), ensuring the solver knows the exact "ink" coverage.
* **Density Ratio:** The engine calculates the ratio of "True Area" to "Bounding Box Area." This allows the solver to accurately predict how large a winding path needs to be scaled to hit a specific zoning target.
* **Semantic Centroid Anchoring:** All elements are anchored to the **Pershing Square Centroid** (the mathematical center of the `BOUNDARY` layer). 

### 6.3 ARCHITECTURAL IMPACT
By moving to this logic, the **Memory Machine** transitions from a 2D collage tool to an **Architectural Solver**:
1.  **Zonal Compliance:** It ensures that when the AI proposes "30% Softscape," the physical area is mathematically verified against Pershing Square’s true bounds.
2.  **Design Intent:** Semantic Grid logic allows for directional intent (e.g., "Cluster program at the North edge") rather than random dispersion.
3.  **3D Readiness:** Precisely calculated 2D areas and overlaps translate directly into accurate 3D massing for the `geometry_engine` (Mounds, Basins, and Canopies).