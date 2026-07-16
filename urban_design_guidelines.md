# URBAN DESIGN GUIDELINES // MEMORY MACHINE v1.2

## Site: Pershing Square, DTLA

This document serves as the geometric and programmatic logic for the Cross-Pollination Engine. All generated interventions must adhere to the zonal constraints and primitive hierarchies defined herein.

---

## 1. PROGRAMMATIC ZONES (ZONAL_METADATA)

These zones define the qualitative and quantitative targets for any spatial remix.

| Zone ID | Label | Target % | Description | Hex Color |
| :--- | :--- | :--- | :--- | :--- |
| **SOFT_01** | Softscape | 30-50% | Permeable surfaces, lawn, and climate-resilient planting. | #4CAF50 |
| **HARD_01** | Hardscape | 40-60% | Civic plazas, transit-oriented paving, and flexible gathering space. | #9E9E9E |
| **PROG_01** | Active Program | 10-20% | Kiosks, stages, playgrounds, or designated social nodes. | #FF9800 |
| **BLUE_01** | Blue Space | 2-10% | Water features, shallow wading pools, and acoustic buffers. | #03A9F4 |

---

## 2. GEOMETRIC PRIMITIVES

The engine uses three primary "Geometries" for 3D massing.

### The Mound (LANDSCAPE_MOUND)
- **Logic:** Topographic interventions that provide shade and seating.
- **Max Height:** 12.0m
- **Materiality:** Grass, Rammed Earth, or Recycled Concrete.

### The Canopy (FLOATING_CANOPY)
- **Logic:** High-level shade structures that cross-pollinate with existing building heights.
- **Clearance:** Minimum 4.5m for pedestrian flow.
- **Materiality:** Perforated Metal, ETFE, or Tensile Fabric.

### The Basin (SUNKEN_PLAZA)
- **Logic:** Sub-surface gathering areas for acoustic isolation from 5th Street traffic.
- **Depth:** Maximum -3.0m
- **Materiality:** Polished Stone or Blue Glass.

---

## 3. SPATIAL RELATIONSHIPS

1. **The Edge Rule:** No active program (`PROG_01`) shall be placed within 5.0m of the site boundary to maintain pedestrian clearways.
2. **The Sightline Rule:** Interventions taller than 8.0m must maintain a 15.0m clearance from the Biltmore Hotel axis.
3. **The Water Logic:** All `BLUE_01` features must be adjacent to at least one `SOFT_01` zone for natural filtration logic.

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
- **2026-07-16:** Restored to the live path after the 2026-07-13 `2dfbb9e` reorg commit silently swapped this file's content for an unrelated document (`logic/April7thSpatialLogicMarkdown.md`, the Spatial Logic Refactor v1.3 report — preserved there, not deleted). `GuidelineManager.parse()` had been silently falling back to hardcoded Python defaults since then; the fallback values happened to match this table exactly, so the app looked correct while the doc→code link was actually dead. Also fixed: the archived copy (`archive/memoryMachine/urban_design_guidelinesOLD.md`) had every markdown special character backslash-escaped (`\*\*SOFT\_01\*\*`), which would have broken `GuidelineManager`'s exact-string match against `layer_map` even with a table present — restored here with clean markdown instead of copying that escaping verbatim.
