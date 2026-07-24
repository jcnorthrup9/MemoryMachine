"""
stylized_pattern_export.py
---------------------------
Standalone, isolated export: categorizes the Metabolizer's real site
geometry (buildings, circulation, landscape, hardscape paths) into four
plan-view line/polygon groups and writes them out as a layered DXF (for
Rhino) plus a quick-look SVG -- the plain, un-styled geometry a Grasshopper
definition will apply the actual pattern-language styling to (see
run_stylized_export_demo.py and the "Categorized-geometry export for a
Rhino+Grasshopper styling pass" plan).

Deliberately standalone: imported by nothing in the live app
(logic/pershing_api.py, app.py, blender_cockpit.py, frontend/) and does not
touch vector_export.py, diagram_tool/, or logic/svg_remixer.py -- those
existing export paths stay byte-identical to before this file existed. No
jitter/offset/hand-drawn styling here on purpose -- that pattern-language
pass is Grasshopper's job downstream, not reimplemented in Python.
"""

CATEGORY_BUILDING = "BUILDING"
CATEGORY_CIRCULATION = "CIRCULATION"
CATEGORY_LANDSCAPE = "LANDSCAPE"
CATEGORY_HARDSCAPE = "HARDSCAPE"  # renamed 2026-07-23 from "PATHS" -- was
# confusable with the CIRCULATION layer (the actual pedestrian path network);
# this category is painted hardscape/paved surfaces (plazas etc.), not paths.

CATEGORIES = (CATEGORY_BUILDING, CATEGORY_CIRCULATION, CATEGORY_LANDSCAPE, CATEGORY_HARDSCAPE)

# Standard site-plan color convention (per user confirmation): magenta
# buildings, blue circulation, green landscape, yellow hardscape.
STYLE_COLORS_HEX = {
    CATEGORY_BUILDING: "#FF00AA",
    CATEGORY_CIRCULATION: "#29B6F6",
    CATEGORY_LANDSCAPE: "#66BB6A",
    CATEGORY_HARDSCAPE: "#FDD835",
}

# AutoCAD Color Index approximations of the same palette -- DXF's basic
# layer-color scheme has no native hex-RGB, only ACI indices.
STYLE_COLORS_ACI = {
    CATEGORY_BUILDING: 6,    # magenta
    CATEGORY_CIRCULATION: 5, # blue
    CATEGORY_LANDSCAPE: 3,   # green
    CATEGORY_HARDSCAPE: 2,   # yellow
}


def _building_footprint(building_spec):
    """Closed 4-point polygon for a building_mass StructuralElement --
    x_ft/y_ft is the box CENTER, scale/scale_y are width/depth (same
    convention BuildingMassEngine.run() uses, see terracing_engine.py)."""
    cx, cy = building_spec.x_ft, building_spec.y_ft
    hw = building_spec.scale / 2.0
    hd = (building_spec.scale_y if building_spec.scale_y is not None else building_spec.scale) / 2.0
    corners = [(cx - hw, cy - hd), (cx + hw, cy - hd), (cx + hw, cy + hd), (cx - hw, cy + hd)]
    return corners + [corners[0]]


def merge_grid_rectangles(cells):
    """Greedy rectangle-merge over a set of (gx, gy) grid indices -- turns
    "one square per voxel" into "one rectangle per contiguous same-category
    region." Small, self-contained, independently written (not imported
    from vector_export.py) to keep this module fully decoupled from the
    existing export path, per the isolation requirement this whole file
    exists to satisfy. Public (not underscore-prefixed): drawing_styles.py
    reuses this for its own CONTOURS layer rather than duplicating it."""
    remaining = set(cells)
    rects = []
    while remaining:
        gx0, gy0 = min(remaining)
        gx1 = gx0
        while (gx1 + 1, gy0) in remaining:
            gx1 += 1
        gy1 = gy0
        while all((gx, gy1 + 1) in remaining for gx in range(gx0, gx1 + 1)):
            gy1 += 1
        rects.append((gx0, gy0, gx1, gy1))
        for gx in range(gx0, gx1 + 1):
            for gy in range(gy0, gy1 + 1):
                remaining.discard((gx, gy))
    return rects


def grid_rect_polygon(gx0, gy0, gx1, gy1, voxel_ft):
    x0, y0 = gx0 * voxel_ft, gy0 * voxel_ft
    x1, y1 = (gx1 + 1) * voxel_ft, (gy1 + 1) * voxel_ft
    corners = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
    return corners + [corners[0]]


def categorize_site_geometry(program_boxes, circulation_specs, voxels, voxel_ft):
    """
    program_boxes: list of building_mass StructuralElements
        (BuildingMassEngine.run() output).
    circulation_specs: list of footpath/ramp/escalator[_bridge]/lookout_point
        StructuralElements (CirculationNetworkEngine.run() output).
    voxels: flat list of terracing_engine.Voxel (TerracingEngine.run() output).
    voxel_ft: engine.voxel_ft, grid cell size in feet.

    Returns {category: [polylines/polygons]}, each a list of (x, y) point
    lists in site-feet -- plain, un-styled geometry.
    """
    categorized = {c: [] for c in CATEGORIES}

    for b in program_boxes:
        categorized[CATEGORY_BUILDING].append(_building_footprint(b))

    for spec in circulation_specs:
        if spec.x2_ft is None:
            continue  # single-point kinds (e.g. lookout_point) -- not a plan line
        categorized[CATEGORY_CIRCULATION].append([(spec.x_ft, spec.y_ft), (spec.x2_ft, spec.y2_ft)])

    greenscape_cells = [(v.gx, v.gy) for v in voxels if v.is_greenscape]
    hardscape_cells = [(v.gx, v.gy) for v in voxels if v.is_hardscape]
    for gx0, gy0, gx1, gy1 in merge_grid_rectangles(greenscape_cells):
        categorized[CATEGORY_LANDSCAPE].append(grid_rect_polygon(gx0, gy0, gx1, gy1, voxel_ft))
    for gx0, gy0, gx1, gy1 in merge_grid_rectangles(hardscape_cells):
        categorized[CATEGORY_HARDSCAPE].append(grid_rect_polygon(gx0, gy0, gx1, gy1, voxel_ft))

    return categorized


def export_categorized_dxf(categorized, out_path):
    """One named, colored DXF layer per category -- opens in Rhino as real
    curves on real layers, ready for a Grasshopper definition to reference
    by layer name directly. Independent of vector_export.py::export_dxf on
    purpose (reuses the ezdxf library the project already depends on, but
    calls none of that module's functions)."""
    import ezdxf
    doc = ezdxf.new("R2010")
    msp = doc.modelspace()
    for category in CATEGORIES:
        if category not in doc.layers:
            doc.layers.add(category, dxfattribs={"color": STYLE_COLORS_ACI[category]})
    for category, polylines in categorized.items():
        for pts in polylines:
            if len(pts) >= 2:
                msp.add_lwpolyline(list(pts), dxfattribs={"layer": category})
    doc.saveas(out_path)
    return out_path


def export_categorized_svg(categorized, site_width_ft, site_length_ft, out_path, margin=20.0):
    """Plain quick-look SVG of the same categorized geometry, for eyeballing
    the export without opening Rhino -- no jitter/offset styling (that's
    Grasshopper's job downstream). A hand-rolled writer independent of
    vector_export.py::export_svg on purpose, keeping this module fully
    decoupled from the existing export path."""
    width = site_width_ft + 2 * margin
    height = site_length_ft + 2 * margin

    def flip(pt):
        return (pt[0] + margin, (site_length_ft - pt[1]) + margin)

    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width:.2f} {height:.2f}">']
    parts.append(f'<rect width="{width:.2f}" height="{height:.2f}" fill="#050505"/>')
    for category in CATEGORIES:
        color = STYLE_COLORS_HEX[category]
        parts.append(f'<g id="{category}" stroke="{color}" fill="none" stroke-width="0.75" opacity="0.85">')
        for pts in categorized.get(category, []):
            if len(pts) >= 2:
                pts_str = " ".join(f"{p[0]:.2f},{p[1]:.2f}" for p in (flip(p) for p in pts))
                parts.append(f'<polyline points="{pts_str}" />')
        parts.append("</g>")
    parts.append("</svg>")

    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(parts))
    return out_path
