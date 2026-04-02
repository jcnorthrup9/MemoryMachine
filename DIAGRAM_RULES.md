# 📐 Memory Machine // Diagramming Standards

This document serves as the absolute rule set for both human-authored and AI-generated architectural diagrams in the Memory Machine pipeline. 

## 1. The Coordinate System
All AI-generated diagrams MUST be drawn perfectly scaled over the existing satellite `PictureFrame` surface in Rhino. 
- The Python script must locate the `PictureFrame` surface in the `.3dm` file, calculate its bounding box, and map its 0-1 UV coordinates directly to the physical dimensions of that surface.
- The drawing agent can realistically start blindly at the world origin `(0,0,0)`, as this is consistently set up as the bottom-left corner of the drawing/map.

## 2. The Layer Dictionary
All geometry must be placed on one of the following exact layer names. If the layer does not exist, the drawing script must create it.

### 🟩 Surfaces (Closed Polylines)
- `Hardscape Plaza`: The primary connective ground plane.
- `Green Space`: Parks, lawns, and planted areas.
- `Water Features`: Pools, fountains, and natural water bodies.
- `Shade`: Canopy cover or shaded regions.

### 🟦 Lines (Open Polylines)
- `Boundary`: The absolute perimeter of the site.
- `Streets`: Vehicular circulation edges.
- `Pedestrian Pathways`: Primary and secondary pedestrian circulation.

### 🟥 Points (Circles or Polygons)
- `Main Attractors`: Primary programmatic anchors (e.g., museums, large pavilions).
- `Minor Attractors`: Secondary nodes (e.g., kiosks, small fountains).
- `Unique Elements`: Bespoke site-specific artifacts (e.g., kinetic masts, supertrees).

## 3. Geometric Constraints
- **Z-Axis:** All 2D diagram lines must be drawn flat at `Z = 0.0` relative to the map surface.
- **Redraw:** Scripts must disable Rhino redraw (`rs.EnableRedraw(False)`) before drafting and enable it after to prevent performance lag.

## 4. Export & App Integration (The SVG Standard)
- **Visual Export:** All manually authored diagrams must be exported from Rhino as scalable `.svg` files into `data/ParkSVG/`, ensuring layers are preserved as SVG groups (e.g., `<g id="Main_Attractors">`).
- **Data Export:** Every `.svg` must be accompanied by its corresponding `_rhino_parsed.json` file containing the spatial analysis, relationships, and narrative.
- **App Consumption:** The JavaScript frontend will load the `.svg` alongside the JSON narrative, creating an interactive dossier of the precedent's "Spatial DNA."