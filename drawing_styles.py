"""
drawing_styles.py
------------------
Three drawing-style renderers backing the live "Drawings" tab
(logic/pershing_api.py::generate_drawings()/save_drawing()):

1. render_lineweight_svg/_png -- clean traditional plan/section/axo, reusing
   vector_export.py's existing, untouched mesh-cut pipeline.
2. render_color_svg/_png -- bright categorized plan (originally referencing
   Zago/Bowman's saturated site-plan palette -- renamed 2026-07-23 once this
   became a permanent UI feature, not a design-exploration codename),
   extending stylized_pattern_export.py's existing, untouched
   categorize_site_geometry with extra fine detail layers (columns, trees,
   terracing contours).
3. render_diagram_svg/_png -- an abstract stacked program-band diagram
   (originally referencing the OMA Les Halles competition diagram's stacked
   strata + peak silhouettes -- renamed 2026-07-23, same reasoning as
   render_color_*).

Each style factors "compute the geometry" apart from "write SVG"/"write PNG"
so both formats render from the exact same structured data, computed once.
PNG uses matplotlib (already a project dependency, already proven via
vector_export.py::export_png) rather than rasterizing the SVG text --
cairosvg and svglib/reportlab were both tried and both need a native cairo
library that isn't installed on this machine (confirmed 2026-07-23), so
matplotlib is the dependency-free path already available.

Reads from vector_export.py and stylized_pattern_export.py -- neither
existing module is modified by this one.
"""
import json
import os
import tempfile

import vector_export
import stylized_pattern_export as spe

# Shared per-program color registry (2026-07-28 consolidation pass) -- same
# single-source-of-truth pattern, and same frontend/src/ location, that
# kindRegistry.json already established for structural kinds. See that
# file's own _meta for why it lives under frontend/src/ rather than data/.
_PROGRAM_COLORS_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "frontend", "src", "programColors.json")
with open(_PROGRAM_COLORS_PATH) as _f:
    _PROGRAM_COLORS = json.load(_f)


def _unavailable_svg(message, width=600.0, height=100.0):
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width:.0f} {height:.0f}">'
        f'<rect width="{width:.0f}" height="{height:.0f}" fill="#050505"/>'
        f'<text x="20" y="{height/2:.0f}" font-family="sans-serif" font-size="12" '
        f'fill="#ff8a80">{message}</text></svg>'
    )


def _unavailable_png(message):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import io

    fig, ax = plt.subplots(figsize=(6, 1.2))
    ax.text(0.02, 0.5, message, color="#ff8a80", fontsize=9, va="center", wrap=True)
    ax.set_facecolor("#050505")
    fig.patch.set_facecolor("#050505")
    ax.axis("off")
    buf = io.BytesIO()
    fig.savefig(buf, format="png", facecolor="#050505")
    plt.close(fig)
    return buf.getvalue()


# --- Style 1: clean traditional lineweight -----------------------------

# Same nudge-off-the-nominal-elevation convention run_vector_export_demo.py's
# own CUT_EPSILON_FT uses -- cutting exactly coplanar with a slab/column top
# is a degenerate case for mesh-plane intersection.
PLAN_CUT_EPSILON_FT = 0.05

# LEVEL_NAMES: the ordered list of valid `level` values for a "plan" view --
# same 4 named elevations run_vector_export_demo.py's own
# GARAGE_LEVEL_ELEVATIONS_FT already establishes (SURFACE/LEVEL 1/LEVEL 2/
# LEVEL 3), reused here rather than inventing a second naming scheme. Added
# 2026-07-23: a single fixed plan-cut height (previously hardcoded at
# z=-0.05, i.e. SURFACE) can't show a meaningful plan when the current
# design has no continuous surface at grade -- this site's default state
# excavates the whole square to varying depths, so which of the 4 levels
# actually has visible geometry depends entirely on the current design.
LEVEL_NAMES = [name for name, _z in vector_export.GARAGE_LEVEL_ELEVATIONS_FT]


def lineweight_layers(real_geometry, engine, voxels, view, level="SURFACE"):
    """Builds the same cut geometry run_vector_export_demo.py already
    exercises. `level` only matters for view="plan" -- one of LEVEL_NAMES.
    Returns (layers, title) or (None, message) for the known axo
    memory-limitation case (see render_lineweight_svg's docstring)."""
    combined = vector_export.build_combined_mesh(real_geometry, engine, voxels)

    if view == "section":
        entrance_y = real_geometry["secondary_entrance_anchor"]["z"]
        path = vector_export.section_cut(combined, plane_origin=[0, entrance_y, 0], plane_normal=[0, 1, 0])
        segs = vector_export.path3d_to_2d_segments(path)[0] if path is not None else []
        layers = {vector_export.LAYER_CUT: segs, vector_export.LAYER_PROJECTION: [], vector_export.LAYER_BOTANICAL: []}
        return layers, f"SECTION THRU METRO ENTRANCE (y={entrance_y:.1f}ft)"

    if view == "axo":
        # axonometric_projection()'s hidden-line-removal ray-triangle search
        # has a known, pre-existing memory blowup on the real site's full
        # combined mesh (confirmed 2026-07-23: run_vector_export_demo.py
        # itself hits the identical "~9.5 GiB array" MemoryError in this
        # environment -- a vector_export.py limitation that predates and is
        # out of scope for this feature, not something introduced here).
        #
        # WARNING (confirmed live 2026-07-24): this `except MemoryError`
        # is NOT a reliable safety net -- triggering this path through the
        # live app actually crashed the whole shared FastAPI process
        # instead of hitting this handler (root cause: the real failure
        # mode here is the OS killing the process outright under memory
        # pressure from a real, pre-existing trimesh/rtree ray-candidate-
        # search pathology triggered by this site's many touching/coplanar
        # terrace boxes -- a ~33k-face mesh, not simply "too big" -- which
        # happens before/instead of a clean Python-level MemoryError).
        # frontend/src/components/DrawingsPanel.jsx deliberately does NOT
        # expose an AXO button for this reason -- do not wire one up again
        # without first isolating this call in a subprocess (so a crash
        # here can't take the main server down with it) or fixing the
        # underlying trimesh issue.
        try:
            axo_mesh = vector_export.mirror_mesh_y(combined, engine.site_length_ft)
            polylines = vector_export.filter_short_polylines(vector_export.axonometric_projection(axo_mesh))
            return {vector_export.LAYER_PROJECTION: polylines}, "AXONOMETRIC (isometric, hidden-line-removed)"
        except MemoryError:
            return None, (
                "AXO view is temporarily unavailable -- the hidden-line-removal "
                "pass runs out of memory on the current site mesh (a known "
                "vector_export.py limitation). Try PLAN or SECTION instead."
            )

    level_elevations = dict(vector_export.GARAGE_LEVEL_ELEVATIONS_FT)
    nominal_z = level_elevations.get(level, 0.0)
    p = vector_export.plan_cut(combined, nominal_z - PLAN_CUT_EPSILON_FT)
    segs = vector_export.path3d_to_2d_segments(p)[0] if p is not None else []
    grid_pts = [[pt] for pt in vector_export.grid_layer_points(real_geometry)]
    layers = {
        vector_export.LAYER_CUT: segs, vector_export.LAYER_PROJECTION: [], vector_export.LAYER_BOTANICAL: [],
        vector_export.LAYER_GRID: grid_pts,
    }
    return layers, f"PLAN -- {level} ({vector_export.format_elevation_ft(nominal_z)})"


def _lineweight_labels(real_geometry, engine, title, show_labels):
    """Resolves (display_title, labels) for the vector_export.py title/
    labels params -- street-edge labels (street_label_points) weren't
    wired in at all before 2026-07-23 (this function is new); bundled with
    the title under one show_labels toggle since both are text annotations
    a user might want off for a clean drawing."""
    if not show_labels:
        return None, None
    return title, vector_export.street_label_points(engine.site_width_ft, engine.site_length_ft)


def render_lineweight_svg(real_geometry, engine, voxels, view="plan", level="SURFACE", show_labels=True):
    """view: "plan" | "section" | "axo". `level` only matters for
    view="plan" -- one of LEVEL_NAMES. vector_export.py's export_svg only
    writes to disk (no in-memory string API), so this writes to a
    throwaway temp file and reads the text back rather than modifying that
    module to add one."""
    layers, title = lineweight_layers(real_geometry, engine, voxels, view, level=level)
    if layers is None:
        return _unavailable_svg(title)
    display_title, labels = _lineweight_labels(real_geometry, engine, title, show_labels)

    fd, tmp_path = tempfile.mkstemp(suffix=".svg")
    os.close(fd)
    try:
        vector_export.export_svg(tmp_path, layers, title=display_title, labels=labels)
        with open(tmp_path, "r", encoding="utf-8") as f:
            return f.read()
    finally:
        os.remove(tmp_path)


def export_lineweight_dxf(real_geometry, engine, layers, title, out_path, show_labels=True):
    """Thin wrapper so callers (logic/pershing_api.py) only ever talk to
    this module, not vector_export.py directly -- keeps the same one-way
    dependency shape (pershing_api.py -> drawing_styles.py -> vector_export.py)
    every other function here already has."""
    display_title, labels = _lineweight_labels(real_geometry, engine, title, show_labels)
    return vector_export.export_dxf(out_path, layers, title=display_title, labels=labels)


def render_lineweight_png(real_geometry, engine, voxels, view="plan", level="SURFACE", show_labels=True):
    """PNG counterpart to render_lineweight_svg -- same layers/title,
    written via vector_export.py's existing, untouched export_png
    (matplotlib-based)."""
    layers, title = lineweight_layers(real_geometry, engine, voxels, view, level=level)
    if layers is None:
        return _unavailable_png(title)
    display_title, labels = _lineweight_labels(real_geometry, engine, title, show_labels)

    fd, tmp_path = tempfile.mkstemp(suffix=".png")
    os.close(fd)
    try:
        vector_export.export_png(tmp_path, layers, title=display_title, labels=labels)
        with open(tmp_path, "rb") as f:
            return f.read()
    finally:
        os.remove(tmp_path)


# --- Style 2: COLOR -- bright categorized plan, extra fine detail ------

DETAIL_COLORS_HEX = {
    "COLUMNS": "#B0BEC5",
    "TREES": "#A5D6A7",
    "CONTOURS": "#78909C",
}


def _circle_polyline(cx, cy, radius, segments=10):
    import math
    pts = [
        (cx + radius * math.cos(2 * math.pi * i / segments), cy + radius * math.sin(2 * math.pi * i / segments))
        for i in range(segments)
    ]
    return pts + [pts[0]]


def _contour_layers(voxels, voxel_ft):
    """Terracing step outlines: one merged-rectangle set per distinct
    z_ft band -- same grid-rect-merge idiom stylized_pattern_export.py's
    categorize_site_geometry already uses for LANDSCAPE/PATHS."""
    by_z = {}
    for v in voxels:
        by_z.setdefault(round(v.z_ft, 2), []).append((v.gx, v.gy))
    polylines = []
    for _z, cells in by_z.items():
        for gx0, gy0, gx1, gy1 in spe.merge_grid_rectangles(cells):
            polylines.append(spe.grid_rect_polygon(gx0, gy0, gx1, gy1, voxel_ft))
    return polylines


def _color_geometry(program_boxes, circulation_specs, voxels, voxel_ft,
                     real_geometry, typology_specs, site_width_ft, site_length_ft):
    """Extends the prior session's categorize_site_geometry (4 blocky
    categories) with thinner, more delicate detail layers -- real column
    positions, tree positions, and terracing contour lines -- per the
    user's ask for "more detailed... more delicate" than the original.
    Returns (base_layers, detail_layers, width, height) in plain site-feet
    (x, y) -- no SVG-specific y-flip applied here, callers do their own."""
    categorized = spe.categorize_site_geometry(program_boxes, circulation_specs, voxels, voxel_ft)

    columns = [_circle_polyline(c["x"], c["z"], 1.1) for c in real_geometry.get("column_positions", [])]
    trees = [_circle_polyline(t.x_ft, t.y_ft, 3.0) for t in typology_specs if t.kind == "tree_canopy"]
    contours = _contour_layers(voxels, voxel_ft)
    detail = {"COLUMNS": columns, "TREES": trees, "CONTOURS": contours}

    margin = 20.0
    width = site_width_ft + 2 * margin
    height = site_length_ft + 2 * margin
    return categorized, detail, width, height


def render_color_svg(program_boxes, circulation_specs, voxels, voxel_ft,
                      real_geometry, typology_specs, site_width_ft, site_length_ft, show_labels=True):
    categorized, detail, width, height = _color_geometry(
        program_boxes, circulation_specs, voxels, voxel_ft,
        real_geometry, typology_specs, site_width_ft, site_length_ft,
    )
    margin = 20.0

    def flip(pt):
        return (pt[0] + margin, (site_length_ft - pt[1]) + margin)

    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width:.2f} {height:.2f}">']
    parts.append(f'<rect width="{width:.2f}" height="{height:.2f}" fill="#050505"/>')
    for category in spe.CATEGORIES:
        color = spe.STYLE_COLORS_HEX[category]
        parts.append(f'<g id="{category}" stroke="{color}" fill="none" stroke-width="0.4" opacity="0.7">')
        for pts in categorized.get(category, []):
            if len(pts) >= 2:
                pts_str = " ".join(f"{p[0]:.2f},{p[1]:.2f}" for p in (flip(p) for p in pts))
                parts.append(f'<polyline points="{pts_str}" />')
        parts.append("</g>")
    for category, polylines in detail.items():
        color = DETAIL_COLORS_HEX[category]
        parts.append(f'<g id="{category}" stroke="{color}" fill="none" stroke-width="0.2" opacity="0.5">')
        for pts in polylines:
            if len(pts) >= 2:
                pts_str = " ".join(f"{p[0]:.2f},{p[1]:.2f}" for p in (flip(p) for p in pts))
                parts.append(f'<polyline points="{pts_str}" />')
        parts.append("</g>")
    if show_labels:
        parts.append('<g id="LABELS" fill="#ffffff">')
        for text, pos in vector_export.street_label_points(site_width_ft, site_length_ft):
            fx, fy = flip(pos)
            parts.append(
                f'<text x="{fx:.2f}" y="{fy:.2f}" font-family="sans-serif" '
                f'font-size="10" text-anchor="middle">{text}</text>'
            )
        parts.append("</g>")
    parts.append("</svg>")
    return "\n".join(parts)


def render_color_png(program_boxes, circulation_specs, voxels, voxel_ft,
                      real_geometry, typology_specs, site_width_ft, site_length_ft, show_labels=True):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.collections import LineCollection
    import io

    categorized, detail, width, height = _color_geometry(
        program_boxes, circulation_specs, voxels, voxel_ft,
        real_geometry, typology_specs, site_width_ft, site_length_ft,
    )

    fig, ax = plt.subplots(figsize=(10.0, 10.0 * (height / width) if width > 0 else 10.0))
    fig.patch.set_facecolor("#050505")
    ax.set_facecolor("#050505")

    for category in spe.CATEGORIES:
        color = spe.STYLE_COLORS_HEX[category]
        lines = [pts for pts in categorized.get(category, []) if len(pts) >= 2]
        if lines:
            ax.add_collection(LineCollection(lines, colors=color, linewidths=0.6, alpha=0.7))
    for category, polylines in detail.items():
        color = DETAIL_COLORS_HEX[category]
        lines = [pts for pts in polylines if len(pts) >= 2]
        if lines:
            ax.add_collection(LineCollection(lines, colors=color, linewidths=0.3, alpha=0.5))
    if show_labels:
        for text, (x, y) in vector_export.street_label_points(site_width_ft, site_length_ft):
            ax.text(x, y, text, color="#ffffff", fontsize=8, ha="center", va="center")

    ax.set_xlim(0, site_width_ft)
    ax.set_ylim(0, site_length_ft)
    ax.set_aspect("equal")
    ax.axis("off")

    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=150, facecolor="#050505", bbox_inches="tight")
    plt.close(fig)
    return buf.getvalue()


def export_color_dxf(program_boxes, circulation_specs, voxels, voxel_ft,
                      real_geometry, typology_specs, site_width_ft, site_length_ft, out_path, show_labels=True):
    """DXF counterpart -- one named layer per category (base 4 + the 3
    detail layers), real site-feet coordinates, for CAD/Rhino import with
    layers and colors preserved (see save_drawing()'s docstring for why
    DXF, not PNG, is the right format for "preserve layers and colors")."""
    import ezdxf

    categorized, detail, _width, _height = _color_geometry(
        program_boxes, circulation_specs, voxels, voxel_ft,
        real_geometry, typology_specs, site_width_ft, site_length_ft,
    )

    doc = ezdxf.new("R2010")
    msp = doc.modelspace()
    for category in spe.CATEGORIES:
        doc.layers.add(category, dxfattribs={"color": spe.STYLE_COLORS_ACI[category]})
        for pts in categorized.get(category, []):
            if len(pts) >= 2:
                msp.add_lwpolyline(list(pts), dxfattribs={"layer": category})
    # Detail layers use the closest standard ACI colors to their hex swatches
    # (DXF's base palette has no arbitrary true-color layer setting in R2010).
    detail_aci = {"COLUMNS": 9, "TREES": 3, "CONTOURS": 8}
    for category, polylines in detail.items():
        doc.layers.add(category, dxfattribs={"color": detail_aci[category]})
        for pts in polylines:
            if len(pts) >= 2:
                msp.add_lwpolyline(list(pts), dxfattribs={"layer": category})
    if show_labels:
        doc.layers.add("LABELS", dxfattribs={"color": 7})  # white
        for text, (x, y) in vector_export.street_label_points(site_width_ft, site_length_ft):
            msp.add_text(text, dxfattribs={"layer": "LABELS", "height": 8.0}).set_placement((x, y))
    doc.saveas(out_path)
    return out_path


# --- Style 3: DIAGRAM -- abstract stacked program bands -----------------

# Read from frontend/src/programColors.json (2026-07-28) -- this used to be
# a hand-maintained copy of Viewport.jsx's map, with its own comment
# admitting it was "a duplicated source of truth, kept in sync manually."
# A third copy then appeared in DiagnosticsPanel.jsx, which is what
# prompted the consolidation. Names kept identical so every existing
# reference below still reads the same.
PROGRAM_COLOR = _PROGRAM_COLORS["programs"]
PROGRAM_FALLBACK_COLOR = _PROGRAM_COLORS["fallback"]

BAND_HEIGHT_PX = 14.0
BAND_GAP_PX = 3.0
UNIT_WIDTH_PX = 6.0       # px per claimed bay, along a band
PEAK_HEIGHT_SCALE = 0.6   # fraction of BAND_HEIGHT_PX the tallest program's peak reaches
MARGIN_PX = 20.0


def _diagram_rows(zones, program_boxes):
    """One row per program category present in `zones` -- width by
    claimed-bay count, peak points from that program's per-bay box
    heights. Returns (rows, width, height) where rows is a list of
    dicts: {item, color, band_width, y, peak_pts}."""
    by_program = {}
    for zone in zones:
        item = zone.get("program_item") or "Unassigned"
        by_program.setdefault(item, []).append(zone)

    heights_by_program = {}
    for box in program_boxes:
        if box.program_item:
            heights_by_program.setdefault(box.program_item, []).append(box.height_ft)

    max_height_ft = max((h for hs in heights_by_program.values() for h in hs), default=1.0)

    sorted_items = sorted(by_program.items(), key=lambda kv: -sum(len(z["bays"]) for z in kv[1]))
    max_bays = max((sum(len(z["bays"]) for z in zs) for _item, zs in sorted_items), default=1)

    rows = []
    for row_i, (item, zs) in enumerate(sorted_items):
        n_bays = sum(len(z["bays"]) for z in zs)
        band_width = n_bays * UNIT_WIDTH_PX
        y = MARGIN_PX + row_i * (BAND_HEIGHT_PX + BAND_GAP_PX)
        color = PROGRAM_COLOR.get(item, PROGRAM_FALLBACK_COLOR)
        heights = heights_by_program.get(item, [])
        peak_pts = []
        if heights and band_width > 0:
            step = band_width / len(heights)
            for i, h in enumerate(heights):
                px = MARGIN_PX + i * step
                peak_h = (h / max_height_ft) * BAND_HEIGHT_PX * PEAK_HEIGHT_SCALE
                peak_pts.append((px, y - peak_h))
                peak_pts.append((px + step, y - peak_h))
        rows.append({"item": item, "color": color, "band_width": band_width, "y": y, "peak_pts": peak_pts})

    width = max_bays * UNIT_WIDTH_PX + 2 * MARGIN_PX
    height = len(rows) * (BAND_HEIGHT_PX + BAND_GAP_PX) + 2 * MARGIN_PX
    return rows, width, height


def render_diagram_svg(zones, program_boxes, show_labels=True):
    """An abstract program-distribution diagram (not a site plan), adapting
    the OMA Les Halles reference's own abstraction (existing/proposed
    comparison: stacked color strata + outlined peak silhouettes). This
    tool has no literal "existing" state to compare against, so this
    renders ONE row per program for the current design only. First pass --
    expect to iterate on this one visually once it's running."""
    rows, width, height = _diagram_rows(zones, program_boxes)

    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width:.2f} {height:.2f}">']
    parts.append(f'<rect width="{width:.2f}" height="{height:.2f}" fill="#000000"/>')
    for row in rows:
        parts.append(
            f'<rect x="{MARGIN_PX:.2f}" y="{row["y"]:.2f}" width="{row["band_width"]:.2f}" '
            f'height="{BAND_HEIGHT_PX:.2f}" fill="{row["color"]}" />'
        )
        if row["peak_pts"]:
            pts_str = " ".join(f"{x:.2f},{y:.2f}" for x, y in row["peak_pts"])
            parts.append(f'<polyline points="{pts_str}" stroke="#000000" stroke-width="1.2" fill="none" />')
        if show_labels:
            parts.append(
                f'<text x="{MARGIN_PX + row["band_width"] + 4:.2f}" y="{row["y"] + BAND_HEIGHT_PX - 3:.2f}" '
                f'font-family="sans-serif" font-size="8" fill="#ffffff">{row["item"]}</text>'
            )
    parts.append("</svg>")
    return "\n".join(parts)


def render_diagram_png(zones, program_boxes, show_labels=True):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Rectangle
    import io

    rows, width, height = _diagram_rows(zones, program_boxes)

    fig, ax = plt.subplots(figsize=(10.0, max(2.0, 10.0 * (height / width) if width > 0 else 2.0)))
    fig.patch.set_facecolor("#000000")
    ax.set_facecolor("#000000")

    for row in rows:
        # matplotlib patches are anchored bottom-left; this diagram's `y`
        # (from _diagram_rows, an SVG-style top-down coordinate) is
        # converted by drawing the rect from (y) down by BAND_HEIGHT_PX in
        # a y-flipped axis below, matching the SVG version's page-down reading.
        ax.add_patch(Rectangle((MARGIN_PX, row["y"]), row["band_width"], BAND_HEIGHT_PX, facecolor=row["color"]))
        if row["peak_pts"]:
            xs = [p[0] for p in row["peak_pts"]]
            ys = [p[1] for p in row["peak_pts"]]
            ax.plot(xs, ys, color="#000000", linewidth=1.2)
        if show_labels:
            ax.text(MARGIN_PX + row["band_width"] + 4, row["y"] + BAND_HEIGHT_PX - 3, row["item"],
                    color="#ffffff", fontsize=7, va="top")

    ax.set_xlim(0, width)
    ax.set_ylim(0, height)
    ax.invert_yaxis()  # rows were laid out top-down (SVG convention)
    ax.axis("off")

    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=150, facecolor="#000000", bbox_inches="tight")
    plt.close(fig)
    return buf.getvalue()


def export_diagram_dxf(zones, program_boxes, out_path, show_labels=True):
    """DXF counterpart -- one named layer per program-category band, real
    true-color RGB (not an approximate ACI palette lookup like
    export_color_dxf's detail layers use -- this is new code, and true-color
    is a strictly more accurate match to PROGRAM_COLOR's hex values, which
    is the whole point per the user's "preserve... colors" ask). Each layer
    gets the band rectangle (closed 4-point LWPOLYLINE), the peak polyline
    (if any), and a TEXT entity for the label."""
    import ezdxf
    from ezdxf.colors import rgb2int

    rows, _width, _height = _diagram_rows(zones, program_boxes)

    doc = ezdxf.new("R2010")
    msp = doc.modelspace()
    for i, row in enumerate(rows):
        # DXF layer names can't repeat and have restricted characters --
        # sanitize + disambiguate (two programs could share a display name
        # in principle, though PROGRAM_COLOR's keys are already unique).
        layer_name = f"{i:02d}_{row['item']}"[:255].replace("/", "-")
        hex_color = row["color"].lstrip("#")
        rgb = tuple(int(hex_color[j:j + 2], 16) for j in (0, 2, 4))
        doc.layers.add(layer_name, dxfattribs={"true_color": rgb2int(rgb)})

        x0, y0 = MARGIN_PX, row["y"]
        x1, y1 = MARGIN_PX + row["band_width"], row["y"] + BAND_HEIGHT_PX
        band = [(x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0)]
        msp.add_lwpolyline(band, dxfattribs={"layer": layer_name})

        if row["peak_pts"]:
            msp.add_lwpolyline(list(row["peak_pts"]), dxfattribs={"layer": layer_name})

        if show_labels:
            msp.add_text(row["item"], dxfattribs={"layer": layer_name, "height": 6.0}).set_placement(
                (x1 + 4, y0)
            )

    doc.saveas(out_path)
    return out_path
