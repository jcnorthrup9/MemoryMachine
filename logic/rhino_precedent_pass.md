# Memory Machine: Pershing Square Precedent Generator
**Context:** Master of Architecture Thesis - John C. Northrup II
**Target Environment:** VS Code + Rhino 8 (Rhino.Python 3)
**Objective:** Procedurally generate 3D spatial assets and a research deck based on "Successful Public Space" data.

---

## 1. Precedent Data & Research Synthesis
The following data was harvested by the Memory Machine's discovery engine. It maps qualitative sentiment to quantitative spatial parameters and forms the basis for both the HTML research deck and the procedural Rhino geometry.

```json
{
  "precedents": [
    {"id": "KINETIC_MAST", "site": "Schouwburgplein", "sentiment": 0.85, "logic": "vertical_actuated"},
    {"id": "WADABLE_POOL", "site": "Grand Park", "sentiment": 0.92, "logic": "surface_membrane"},
    {"id": "ART_WALL", "site": "Tanner Springs", "sentiment": 0.78, "logic": "boundary_texture"},
    {"id": "SUPERTREE", "site": "Gardens by the Bay", "sentiment": 0.95, "logic": "infrastructure_vent"},
    {"id": "GRAPHIC_PLAZA", "site": "Superkilen", "sentiment": 0.88, "logic": "ground_pattern"}
  ],
  "site_bounds": {"width": 110, "height": 150}
}