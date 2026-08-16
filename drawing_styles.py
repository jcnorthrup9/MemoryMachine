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

import terracing_engine
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


def lineweight_layers(real_geometry, engine, voxels, view, level="SURFACE", typology_specs=None, zones=None):
    """Builds the same cut geometry run_vector_export_demo.py already
    exercises. view: "plan" | "section" | "long_section" | "axo" (any other
    value falls through to the legacy per-elevation cut below). `level`
    only matters for the legacy per-elevation cut -- the aerial view="plan"
    mode ignores it. `typology_specs` (optional) supplies tree positions for
    the aerial plan's LAYER_BOTANICAL. `zones` (optional,
    `_program_zones_from_engine()`'s return -- the same placement data
    RECONSTRUCT's own massing boxes come from) supplies real building
    footprints for view="plan" (2D polygons, via _building_footprint_polygons),
    masks terrace-contour cells a building sits on top of, AND (2026-08-12)
    real 3D building massing for view="section"/"axo"/"long_section" (via
    _program_massing_specs -- these three views never included massing at
    all before this). Returns (layers, title,
    hatch_layers) or (None, message, {}) for the known axo memory-
    limitation case (see render_lineweight_svg's docstring). `hatch_layers`
    (2026-08-04) names which returned layer(s) hold closed building/massing
    polygons that should render as a solid hatched tonal shape rather than
    a plain outline -- only view="plan" ever populates it (LAYER_CUT there
    holds real building footprints; every other view's LAYER_CUT holds cut/
    section line segments, not closed massing polygons)."""
    if view == "section":
        combined = vector_export.concat_meshes(
            [vector_export.build_combined_mesh(real_geometry, engine, voxels),
             vector_export.build_massing_mesh(_program_massing_specs(zones))])
        entrance_y = real_geometry["secondary_entrance_anchor"]["z"]
        path = vector_export.section_cut(combined, plane_origin=[0, entrance_y, 0], plane_normal=[0, 1, 0])
        segs = vector_export.path3d_to_2d_segments(path)[0] if path is not None else []
        layers = {vector_export.LAYER_CUT: segs, vector_export.LAYER_PROJECTION: [], vector_export.LAYER_BOTANICAL: []}
        return layers, f"SECTION THRU METRO ENTRANCE (y={entrance_y:.1f}ft)", {}

    if view == "axo":
        # axonometric_projection()'s hidden-line-removal ray-triangle search
        # had a known, pre-existing memory blowup on the real site's full
        # combined mesh (confirmed 2026-07-23, and live again 2026-07-24:
        # triggering this through the live app crashed the whole shared
        # FastAPI process outright -- an OS-level kill under memory
        # pressure, not a catchable Python exception, since the failure
        # mode was a real, pre-existing trimesh/rtree ray-candidate-search
        # pathology triggered by this site's many touching/coplanar terrace
        # boxes, not simply "mesh too big"). frontend/src/components/
        # DrawingsPanel.jsx hid its AXO button for this reason from
        # 2026-07-24 to 2026-08-12.
        #
        # Root-caused and fixed 2026-08-12: trimesh was falling back to its
        # slow rtree-based ray intersector because the fast Embree backend
        # wasn't installed (`embreex`, requirements.txt, fixes that
        # directly) -- and vector_export._batch_visible() now also chunks
        # its ray batch with a bounded-memory, fail-open fallback
        # regardless of which backend is active, so a still-pathological
        # case degrades (partial hidden-line removal on just the offending
        # chunk) instead of crashing. The `except MemoryError` below is a
        # secondary backstop, now far more likely to actually catch
        # something (bounded per-chunk allocations raise real Python
        # exceptions much more reliably than the old one-shot multi-GB
        # allocation did) rather than the primary line of defense.
        try:
            combined = vector_export.concat_meshes(
                [vector_export.build_combined_mesh(real_geometry, engine, voxels),
                 vector_export.build_massing_mesh(_program_massing_specs(zones))])
            axo_mesh = vector_export.mirror_mesh_y(combined, engine.site_length_ft)
            polylines = vector_export.filter_short_polylines(vector_export.axonometric_projection(axo_mesh))
            return ({vector_export.LAYER_PROJECTION: polylines}, "AXONOMETRIC (isometric, hidden-line-removed)",
                    {})
        except MemoryError:
            return None, (
                "AXO view is temporarily unavailable -- the hidden-line-removal "
                "pass runs out of memory on the current site mesh (a known "
                "vector_export.py limitation). Try PLAN or SECTION instead."
            ), {}

    if view == "long_section":
        # 2026-08-12: cut perpendicular to X (the site's SHORT axis,
        # ~354ft) rather than "section"'s perpendicular-to-Y cut (which is
        # itself perpendicular to the LONG axis, ~602ft, at a single fixed
        # Y through the metro entrance) -- so this shows the full site
        # LENGTH + height profile instead of the short-axis width profile.
        # Positioned at the site's width centerline by default (no
        # equivalent fixed real-world anchor point like the metro entrance
        # exists for this cut).
        combined = vector_export.concat_meshes(
            [vector_export.build_combined_mesh(real_geometry, engine, voxels),
             vector_export.build_massing_mesh(_program_massing_specs(zones))])
        cut_x = engine.site_width_ft / 2
        path = vector_export.section_cut(combined, plane_origin=[cut_x, 0, 0], plane_normal=[1, 0, 0])
        segs = vector_export.path3d_to_2d_segments(path)[0] if path is not None else []
        layers = {vector_export.LAYER_CUT: segs, vector_export.LAYER_PROJECTION: [], vector_export.LAYER_BOTANICAL: []}
        return layers, f"LONG SECTION (x={cut_x:.1f}ft)", {}

    if view == "plan":
        # 2026-08-04: whole-site aerial plan, replacing the old single-
        # elevation section cut below (which sliced edge-on through this
        # site's terraces/retaining walls/ramps) AND the previous session's
        # whole-mesh feature-edge flatten (which drew that same buried
        # terrace/retaining-wall geometry regardless of depth -- i.e. showed
        # what a covering surface would actually hide, violating real site-
        # plan convention). Real site-plan correctness needs actual
        # occlusion: building massing should hide the terrace/ground
        # underneath it, and nothing below a covering surface should draw at
        # all. Bays are claimed exclusively by place_programs() (never
        # shared between two programs), so occlusion here is just a boolean
        # coverage mask -- no z-buffer, no mesh ray-casting needed:
        #   - building footprints (LAYER_CUT, bold): merged per-zone
        #     polygons from `zones` -- the SAME placement data RECONSTRUCT's
        #     own massing boxes come from, so this now actually correlates.
        #   - terrace/excavation contours (LAYER_PROJECTION): the existing
        #     voxel-band contour merge, over only the OPEN (uncovered-by-any-
        #     building) voxels -- open excavation is genuinely visible from
        #     directly above (it's unroofed), covered cells are not.
        #   - small real context objects at/near grade (secondary entrance,
        #     metro connector, columns, ramps) via mesh_top_edges() -- each
        #     one individually, not the whole combined mesh, so skipping
        #     hidden-line removal on these small shallow objects is a safe
        #     simplification (see mesh_top_edges' own docstring). `tunnel`
        #     is deliberately dropped -- a fully-covered underground
        #     passage isn't visible from directly above.
        bays_per_side = _bays_per_side(engine.voxel_ft)
        covered = _covered_voxel_cells(zones, bays_per_side)
        open_voxels = [v for v in voxels if (v.gx, v.gy) not in covered]

        building_polylines = [poly for poly, _item in _building_footprint_polygons(zones)]
        terrace_polylines = [poly for _z, polys in _contour_layers(open_voxels, engine.voxel_ft) for poly in polys]
        greenscape_polylines = _greenscape_layer(open_voxels, engine.voxel_ft)

        context = vector_export.build_context_meshes(real_geometry)
        context_meshes = [context["secondary_entrance"], context["metro_connector"],
                           *context["columns"], *context["ramps"]]
        context_polylines = vector_export.filter_short_polylines(
            [edge for mesh in context_meshes for edge in vector_export.mesh_top_edges(mesh)]
        )

        grid_pts = [[pt] for pt in vector_export.grid_layer_points(real_geometry)]
        tree_polylines = [
            poly for t in (typology_specs or []) if t.kind == "tree_canopy"
            for poly in _tree_symbol_polylines(t.x_ft, t.y_ft)
        ]
        layers = {
            vector_export.LAYER_CUT: building_polylines,
            vector_export.LAYER_PROJECTION: terrace_polylines + context_polylines,
            vector_export.LAYER_BOTANICAL: tree_polylines, vector_export.LAYER_GRID: grid_pts,
            vector_export.LAYER_GREENSCAPE: greenscape_polylines,
        }
        # 2026-08-04: building/grass/tree each get their own named hatch
        # pattern (see vector_export.HATCH_*) so massing, ground cover, and
        # canopy all read as distinct solid tonal shapes instead of thin
        # outlines indistinguishable from each other and from the terrace
        # contours/context linework on LAYER_PROJECTION.
        hatch_layers = {
            vector_export.LAYER_CUT: vector_export.HATCH_BUILDING,
            vector_export.LAYER_GREENSCAPE: vector_export.HATCH_GRASS,
            vector_export.LAYER_BOTANICAL: vector_export.HATCH_TREE,
        }
        return layers, "PLAN -- AERIAL (whole site)", hatch_layers

    # Legacy single-elevation cut, kept for any other/unrecognized view
    # value -- "plan" itself is handled above and never reaches here.
    combined = vector_export.build_combined_mesh(real_geometry, engine, voxels)
    level_elevations = dict(vector_export.GARAGE_LEVEL_ELEVATIONS_FT)
    nominal_z = level_elevations.get(level, 0.0)
    p = vector_export.plan_cut(combined, nominal_z - PLAN_CUT_EPSILON_FT)
    segs = vector_export.path3d_to_2d_segments(p)[0] if p is not None else []
    grid_pts = [[pt] for pt in vector_export.grid_layer_points(real_geometry)]
    layers = {
        vector_export.LAYER_CUT: segs, vector_export.LAYER_PROJECTION: [], vector_export.LAYER_BOTANICAL: [],
        vector_export.LAYER_GRID: grid_pts,
    }
    return layers, f"PLAN -- {level} ({vector_export.format_elevation_ft(nominal_z)})", {}


def _lineweight_labels(real_geometry, engine, title, show_labels):
    """Resolves (display_title, labels) for the vector_export.py title/
    labels params -- street-edge labels (street_label_points) weren't
    wired in at all before 2026-07-23 (this function is new); bundled with
    the title under one show_labels toggle since both are text annotations
    a user might want off for a clean drawing."""
    if not show_labels:
        return None, None
    return title, vector_export.street_label_points(engine.site_width_ft, engine.site_length_ft)


def render_lineweight_svg(real_geometry, engine, voxels, view="plan", level="SURFACE", show_labels=True,
                           typology_specs=None, zones=None):
    """view: "plan" | "section" | "axo". vector_export.py's export_svg only
    writes to disk (no in-memory string API), so this writes to a
    throwaway temp file and reads the text back rather than modifying that
    module to add one."""
    layers, title, hatch_layers = lineweight_layers(real_geometry, engine, voxels, view, level=level,
                                                      typology_specs=typology_specs, zones=zones)
    if layers is None:
        return _unavailable_svg(title)
    display_title, labels = _lineweight_labels(real_geometry, engine, title, show_labels)

    fd, tmp_path = tempfile.mkstemp(suffix=".svg")
    os.close(fd)
    try:
        vector_export.export_svg(tmp_path, layers, title=display_title, labels=labels, hatch_layers=hatch_layers)
        with open(tmp_path, "r", encoding="utf-8") as f:
            return f.read()
    finally:
        os.remove(tmp_path)


def export_lineweight_dxf(real_geometry, engine, layers, title, out_path, show_labels=True, hatch_layers=None):
    """Thin wrapper so callers (logic/pershing_api.py) only ever talk to
    this module, not vector_export.py directly -- keeps the same one-way
    dependency shape (pershing_api.py -> drawing_styles.py -> vector_export.py)
    every other function here already has."""
    display_title, labels = _lineweight_labels(real_geometry, engine, title, show_labels)
    return vector_export.export_dxf(out_path, layers, title=display_title, labels=labels, hatch_layers=hatch_layers)


def render_lineweight_png(real_geometry, engine, voxels, view="plan", level="SURFACE", show_labels=True,
                           typology_specs=None, zones=None):
    """PNG counterpart to render_lineweight_svg -- same layers/title,
    written via vector_export.py's existing, untouched export_png
    (matplotlib-based)."""
    layers, title, hatch_layers = lineweight_layers(real_geometry, engine, voxels, view, level=level,
                                                      typology_specs=typology_specs, zones=zones)
    if layers is None:
        return _unavailable_png(title)
    display_title, labels = _lineweight_labels(real_geometry, engine, title, show_labels)

    fd, tmp_path = tempfile.mkstemp(suffix=".png")
    os.close(fd)
    try:
        vector_export.export_png(tmp_path, layers, title=display_title, labels=labels, hatch_layers=hatch_layers)
        with open(tmp_path, "rb") as f:
            return f.read()
    finally:
        os.remove(tmp_path)


# --- Style 2: COLOR -- bright categorized plan, extra fine detail ------

# 2026-08-15: COLUMNS/TREES swapped to match the muted pastel palette
# adopted in stylized_pattern_export.STYLE_COLORS_HEX -- see that dict's
# own comment for the full rationale/how-to-revert.
DETAIL_COLORS_HEX = {
    "COLUMNS": "#CBD3D9",
    "TREES": "#96B08A",
    # CONTOURS has no flat entry -- each elevation band gets its own color
    # from _contour_gradient_colors() below instead, so relative height
    # (which band is higher/lower) is visible at a glance.
}

# 2026-08-14: grey->white gradient endpoints for CONTOURS elevation bands
# (darker = lower, lighter = higher), per user ask "do the grey terracing
# lines indicate which ones are higher... is there a way to show this?"
# 2026-08-15: endpoints nudged warmer (near-white instead of pure #e8e8e8)
# to sit with the muted pastel palette -- see STYLE_COLORS_HEX's comment.
CONTOUR_GRADIENT_LOW = "#3a3a3a"
CONTOUR_GRADIENT_HIGH = "#f0ebe3"


def _hex_to_rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def _rgb_to_hex(rgb):
    return "#{:02x}{:02x}{:02x}".format(*(max(0, min(255, round(c))) for c in rgb))


def _contour_gradient_colors(z_values):
    """Maps each distinct elevation band's z_ft to a grey->white hex color,
    lowest->highest. Plain per-channel RGB lerp is sufficient (not HSL):
    both endpoints and every intermediate value are true greys (R=G=B), so
    there's no hue/saturation for HSL to get right that RGB lerp wouldn't."""
    low = _hex_to_rgb(CONTOUR_GRADIENT_LOW)
    high = _hex_to_rgb(CONTOUR_GRADIENT_HIGH)
    distinct = sorted(set(z_values))
    z_min, z_max = (min(distinct), max(distinct)) if distinct else (0.0, 0.0)
    colors = {}
    for z in distinct:
        # A single flat band isn't meaningfully "highest" or "lowest" --
        # render it mid-grey rather than implying it's the tallest.
        t = 0.5 if z_max == z_min else (z - z_min) / (z_max - z_min)
        colors[z] = _rgb_to_hex(tuple(lo + t * (hi - lo) for lo, hi in zip(low, high)))
    return colors


def _circle_polyline(cx, cy, radius, segments=10):
    import math
    pts = [
        (cx + radius * math.cos(2 * math.pi * i / segments), cy + radius * math.sin(2 * math.pi * i / segments))
        for i in range(segments)
    ]
    return pts + [pts[0]]


def _tree_symbol_polylines(cx, cy, canopy_radius=3.0):
    """Low-fidelity 2D plan symbol for a tree (2026-08-03) -- a canopy ring
    plus a small trunk dot, in place of a single plain circle, so plan/color
    drawings read a little more like a tree at a glance while staying
    deliberately simple/low-res. Two polylines: [canopy, trunk]."""
    return [
        _circle_polyline(cx, cy, canopy_radius),
        _circle_polyline(cx, cy, canopy_radius * 0.22, segments=6),
    ]


def _contour_layers(voxels, voxel_ft):
    """Terracing step outlines: one merged-rectangle set per distinct
    z_ft band -- same grid-rect-merge idiom stylized_pattern_export.py's
    categorize_site_geometry already uses for LANDSCAPE/PATHS.

    Returns list[(z_ft, polylines)], one entry per distinct band (not a
    flattened single list) -- 2026-08-14: callers need the z_ft back to
    color-code each band by relative elevation (see
    _contour_gradient_colors). This function stays pure geometry -- no
    color knowledge -- callers look up colors themselves."""
    by_z = {}
    for v in voxels:
        by_z.setdefault(round(v.z_ft, 2), []).append((v.gx, v.gy))
    bands = []
    for z, cells in by_z.items():
        polylines = [
            spe.grid_rect_polygon(gx0, gy0, gx1, gy1, voxel_ft)
            for gx0, gy0, gx1, gy1 in spe.merge_grid_rectangles(cells)
        ]
        bands.append((z, polylines))
    return bands


def _greenscape_layer(voxels, voxel_ft):
    """Grass/greenscape ground-cover footprint -- merged rectangles over
    voxel cells flagged is_greenscape, same grid-rect-merge idiom
    categorize_site_geometry's own LANDSCAPE category uses (2026-08-04,
    for LINEWEIGHT's aerial plan's grass hatch)."""
    cells = [(v.gx, v.gy) for v in voxels if v.is_greenscape]
    return [spe.grid_rect_polygon(gx0, gy0, gx1, gy1, voxel_ft) for gx0, gy0, gx1, gy1 in spe.merge_grid_rectangles(cells)]


def _bays_per_side(voxel_ft):
    """How many voxel-grid cells (voxel_ft, e.g. engine.voxel_ft) fit across
    one real structural bay (terracing_engine.STRUCTURAL_BAY_FT) -- 3 at
    this site's default voxel_ft=9.0 (see aggregate_grid_to_bays's own
    docstring in terracing_engine.py, which establishes the same ratio for
    the same reason: the bay grid and voxel grid share one origin at a
    fixed integer ratio)."""
    return max(1, round(terracing_engine.STRUCTURAL_BAY_FT / voxel_ft))


def _covered_voxel_cells(zones, bays_per_side):
    """Voxel-grid (gx, gy) cells claimed by any placed program's bay --
    used to mask ground-level layers (terrace contours, hardscape/
    landscape hatch) so they don't draw underneath a building footprint,
    per real site-plan convention (nothing a covering surface would hide).
    place_programs() is a bin-packer that claims each bay exclusively for
    one program (bays are never shared between two programs), so a plain
    membership test is enough -- no height comparison/z-buffer needed."""
    covered = set()
    for zone in zones or []:
        for gx, gy, _floor_elev_ft in zone["bays"]:
            for dx in range(bays_per_side):
                for dy in range(bays_per_side):
                    covered.add((gx * bays_per_side + dx, gy * bays_per_side + dy))
    return covered


# Mirrors pershing_api.py's REAL_LEVEL_HEIGHT_FT = 10.0 -- duplicated
# rather than imported, since pershing_api.py -> drawing_styles.py ->
# vector_export.py is this module's one-way dependency (see this file's own
# top-of-file docstring); importing pershing_api.py here would invert it.
_LEVEL_HEIGHT_FT = 10.0


def _program_massing_specs(zones):
    """Building_mass StructuralElement per claimed bay (terracing_engine.
    BuildingMassEngine) -- 3D counterpart to _building_footprint_polygons
    above, for section/axo/long_section (2026-08-12: these views never
    included building massing at all before this -- only the "plan" aerial
    view did, via _building_footprint_polygons' 2D path). One box PER BAY,
    not merged across a zone's contiguous run like the 2D footprint path
    does -- different bays in the same zone can sit at different real
    floor_elev_ft, which a single merged rectangle can't represent. Mirrors
    pershing_api.py's _drawing_program_boxes() (same per-bay construction,
    duplicated here rather than imported for the same one-way-dependency
    reason _LEVEL_HEIGHT_FT above is)."""
    building_dicts = [
        {
            "x_ft": gx * terracing_engine.STRUCTURAL_BAY_FT,
            "y_ft": gy * terracing_engine.STRUCTURAL_BAY_FT,
            "width_ft": terracing_engine.STRUCTURAL_BAY_FT,
            "depth_ft": terracing_engine.STRUCTURAL_BAY_FT,
            "height_ft": _LEVEL_HEIGHT_FT * (2 if zone.get("double_height") else 1),
            "z_ft": floor_elev_ft,
        }
        for zone in (zones or [])
        for gx, gy, floor_elev_ft in zone["bays"]
    ]
    return terracing_engine.BuildingMassEngine(building_dicts).run()


def _building_footprint_polygons(zones):
    """One merged closed polygon per contiguous run of a zone's claimed
    bays (27ft structural-bay grid) -- real building outlines instead of
    one small square per bay. Returns [(polygon_points, program_item), ...]."""
    polys = []
    for zone in zones or []:
        cells = {(gx, gy) for gx, gy, _floor_elev_ft in zone["bays"]}
        if not cells:
            continue
        for gx0, gy0, gx1, gy1 in spe.merge_grid_rectangles(cells):
            polys.append((
                spe.grid_rect_polygon(gx0, gy0, gx1, gy1, terracing_engine.STRUCTURAL_BAY_FT),
                zone.get("program_item"),
            ))
    return polys


def _color_geometry(program_boxes, circulation_specs, voxels, voxel_ft,
                     real_geometry, typology_specs, site_width_ft, site_length_ft, zones=None):
    """Extends the prior session's categorize_site_geometry (4 blocky
    categories) with thinner, more delicate detail layers -- real column
    positions, tree positions, and terracing contour lines -- per the
    user's ask for "more detailed... more delicate" than the original.

    2026-08-04: BUILDING now comes from `zones` (merged per-program
    footprints -- see _building_footprint_polygons) instead of
    categorize_site_geometry's own one-square-per-bay `program_boxes` loop,
    and CONTOURS/LANDSCAPE/HARDSCAPE are computed only from voxels NOT
    covered by a building, so ground detail no longer shows through
    underneath a building footprint (categorize_site_geometry itself is
    untouched -- it's a deliberately standalone module -- its own BUILDING
    output is simply discarded and replaced here). `program_boxes` is kept
    for LANDSCAPE/CIRCULATION/HARDSCAPE compatibility and because some
    callers (the DIAGRAM style) still need real box heights; `zones` is
    optional so callers that don't have it yet still work (empty BUILDING
    layer, no masking -- same behavior as before this change).

    Returns (base_layers, detail_layers, width, height) in plain site-feet
    (x, y) -- no SVG-specific y-flip applied here, callers do their own."""
    bays_per_side = _bays_per_side(voxel_ft)
    covered = _covered_voxel_cells(zones, bays_per_side)
    open_voxels = [v for v in voxels if (v.gx, v.gy) not in covered]

    categorized = spe.categorize_site_geometry(program_boxes, circulation_specs, open_voxels, voxel_ft)
    categorized[spe.CATEGORY_BUILDING] = [poly for poly, _item in _building_footprint_polygons(zones)]

    columns = [_circle_polyline(c["x"], c["z"], 1.1) for c in real_geometry.get("column_positions", [])]
    trees = [
        poly for t in typology_specs if t.kind == "tree_canopy"
        for poly in _tree_symbol_polylines(t.x_ft, t.y_ft)
    ]
    contours = _contour_layers(open_voxels, voxel_ft)
    detail = {"COLUMNS": columns, "TREES": trees, "CONTOURS": contours}

    margin = 20.0
    width = site_width_ft + 2 * margin
    height = site_length_ft + 2 * margin
    return categorized, detail, width, height


def render_color_svg(program_boxes, circulation_specs, voxels, voxel_ft,
                      real_geometry, typology_specs, site_width_ft, site_length_ft, show_labels=True, zones=None):
    categorized, detail, width, height = _color_geometry(
        program_boxes, circulation_specs, voxels, voxel_ft,
        real_geometry, typology_specs, site_width_ft, site_length_ft, zones=zones,
    )
    margin = 20.0

    def flip(pt):
        return (pt[0] + margin, (site_length_ft - pt[1]) + margin)

    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width:.2f} {height:.2f}">']
    parts.append(f'<rect width="{width:.2f}" height="{height:.2f}" fill="#050505"/>')
    # 2026-08-14: HARDSCAPE hatch pattern def -- deliberately NOT reusing
    # vector_export._SVG_HATCH_DEFS (those assume an opaque white backing
    # rect, which would blot out this canvas's near-black #050505
    # background). No backing rect here keeps the pattern transparent so
    # only the diagonal stroke shows, in the HARDSCAPE yellow.
    hardscape_color = spe.STYLE_COLORS_HEX[spe.CATEGORY_HARDSCAPE]
    parts.append(
        '<defs><pattern id="hatch-hardscape" patternUnits="userSpaceOnUse" '
        'width="4" height="4" patternTransform="rotate(45)">'
        f'<line x1="0" y1="0" x2="0" y2="4" stroke="{hardscape_color}" stroke-width="1.1"/>'
        '</pattern></defs>'
    )
    for category in spe.CATEGORIES:
        color = spe.STYLE_COLORS_HEX[category]
        # 2026-08-04: BUILDING and LANDSCAPE (grass) get a solid translucent
        # tonal fill (poche) instead of the other categories' outline-only
        # treatment, so massing/ground-cover read as solid shapes at a
        # glance instead of thin outlines indistinguishable from
        # circulation/hardscape linework.
        # 2026-08-14: HARDSCAPE gets a third treatment -- hatch-fill only
        # (no tint), so paved surface reads as a distinct texture rather
        # than a fourth variant of solid fill or getting lost among
        # CIRCULATION's plain outline lines.
        is_filled = category in (spe.CATEGORY_BUILDING, spe.CATEGORY_LANDSCAPE)
        is_hatched = category == spe.CATEGORY_HARDSCAPE
        if is_filled:
            parts.append(f'<g id="{category}" stroke="{color}" fill="{color}" fill-opacity="0.35" stroke-width="0.9">')
        elif is_hatched:
            parts.append(f'<g id="{category}" stroke="{color}" fill="url(#hatch-hardscape)" stroke-width="0.7">')
        else:
            parts.append(f'<g id="{category}" stroke="{color}" fill="none" stroke-width="0.4" opacity="0.7">')
        for pts in categorized.get(category, []):
            if len(pts) >= 2:
                pts_str = " ".join(f"{p[0]:.2f},{p[1]:.2f}" for p in (flip(p) for p in pts))
                tag = 'polygon' if (is_filled or is_hatched) else 'polyline'
                parts.append(f'<{tag} points="{pts_str}" />')
        parts.append("</g>")
    for category, polylines in detail.items():
        # 2026-08-14: CONTOURS carries a different shape than COLUMNS/TREES
        # -- list[(z_ft, polylines)] bands instead of a flat polyline list
        # -- so each elevation band can render in its own gradient color
        # (see _contour_gradient_colors) instead of one flat CONTOURS color.
        if category == "CONTOURS":
            gradient = _contour_gradient_colors([z for z, _ in polylines])
            for z, band_polylines in polylines:
                band_color = gradient[z]
                parts.append(f'<g id="CONTOURS" stroke="{band_color}" fill="none" stroke-width="0.2" opacity="0.5">')
                for pts in band_polylines:
                    if len(pts) >= 2:
                        pts_str = " ".join(f"{p[0]:.2f},{p[1]:.2f}" for p in (flip(p) for p in pts))
                        parts.append(f'<polyline points="{pts_str}" />')
                parts.append("</g>")
            continue
        color = DETAIL_COLORS_HEX[category]
        # TREES gets the same solid translucent fill treatment as BUILDING/
        # LANDSCAPE above -- each tree's canopy ring reads as a filled dot
        # instead of a nearly-invisible thin circle outline.
        is_filled = category == "TREES"
        if is_filled:
            parts.append(f'<g id="{category}" stroke="{color}" fill="{color}" fill-opacity="0.6" stroke-width="0.3">')
        else:
            parts.append(f'<g id="{category}" stroke="{color}" fill="none" stroke-width="0.2" opacity="0.5">')
        for pts in polylines:
            if len(pts) >= 2:
                pts_str = " ".join(f"{p[0]:.2f},{p[1]:.2f}" for p in (flip(p) for p in pts))
                tag = 'polygon' if is_filled else 'polyline'
                parts.append(f'<{tag} points="{pts_str}" />')
        parts.append("</g>")
    if show_labels:
        parts.append('<g id="LABELS" fill="#ffffff">')
        for text, pos, angle in vector_export.street_label_points(site_width_ft, site_length_ft):
            fx, fy = flip(pos)
            rotate = f' transform="rotate({angle} {fx:.2f} {fy:.2f})"' if angle else ''
            parts.append(
                f'<text x="{fx:.2f}" y="{fy:.2f}" font-family="sans-serif" '
                f'font-size="10" text-anchor="middle"{rotate}>{text}</text>'
            )
        parts.append("</g>")
    parts.append("</svg>")
    return "\n".join(parts)


def render_color_png(program_boxes, circulation_specs, voxels, voxel_ft,
                      real_geometry, typology_specs, site_width_ft, site_length_ft, show_labels=True, zones=None):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.collections import LineCollection
    from matplotlib.patches import Polygon as MplPolygon
    import io

    categorized, detail, width, height = _color_geometry(
        program_boxes, circulation_specs, voxels, voxel_ft,
        real_geometry, typology_specs, site_width_ft, site_length_ft, zones=zones,
    )

    fig, ax = plt.subplots(figsize=(10.0, 10.0 * (height / width) if width > 0 else 10.0))
    fig.patch.set_facecolor("#050505")
    ax.set_facecolor("#050505")

    for category in spe.CATEGORIES:
        color = spe.STYLE_COLORS_HEX[category]
        if category in (spe.CATEGORY_BUILDING, spe.CATEGORY_LANDSCAPE):
            # Solid translucent tonal fill (poche) -- see render_color_svg's
            # own comment for why building/landscape get different treatment.
            for pts in categorized.get(category, []):
                if len(pts) >= 3:
                    ax.add_patch(MplPolygon(
                        pts, closed=True, facecolor=color, edgecolor=color, alpha=0.55, linewidth=1.2))
            continue
        if category == spe.CATEGORY_HARDSCAPE:
            # 2026-08-14: hatch-fill only (no tint) -- see render_color_svg's
            # own comment for why hardscape gets a third treatment distinct
            # from both solid fill and plain outline.
            hatch_char = vector_export._PNG_HATCH_CHARS[vector_export.HATCH_BUILDING]
            for pts in categorized.get(category, []):
                if len(pts) >= 3:
                    ax.add_patch(MplPolygon(
                        pts, closed=True, facecolor='none', edgecolor=color,
                        hatch=hatch_char, linewidth=0.9, alpha=0.9))
            continue
        lines = [pts for pts in categorized.get(category, []) if len(pts) >= 2]
        if lines:
            ax.add_collection(LineCollection(lines, colors=color, linewidths=0.6, alpha=0.7))
    for category, polylines in detail.items():
        # 2026-08-14: CONTOURS carries list[(z_ft, polylines)] bands instead
        # of a flat polyline list -- see render_color_svg's own comment --
        # so each band renders in its own gradient color.
        if category == "CONTOURS":
            gradient = _contour_gradient_colors([z for z, _ in polylines])
            for z, band_polylines in polylines:
                lines = [pts for pts in band_polylines if len(pts) >= 2]
                if lines:
                    ax.add_collection(LineCollection(lines, colors=gradient[z], linewidths=0.3, alpha=0.5))
            continue
        color = DETAIL_COLORS_HEX[category]
        if category == "TREES":
            for pts in polylines:
                if len(pts) >= 3:
                    ax.add_patch(MplPolygon(pts, closed=True, facecolor=color, edgecolor=color, alpha=0.6, linewidth=0.6))
            continue
        lines = [pts for pts in polylines if len(pts) >= 2]
        if lines:
            ax.add_collection(LineCollection(lines, colors=color, linewidths=0.3, alpha=0.5))
    if show_labels:
        for text, (x, y), angle in vector_export.street_label_points(site_width_ft, site_length_ft):
            ax.text(x, y, text, color="#ffffff", fontsize=8, ha="center", va="center", rotation=angle)

    ax.set_xlim(0, site_width_ft)
    ax.set_ylim(0, site_length_ft)
    ax.set_aspect("equal")
    ax.axis("off")

    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=150, facecolor="#050505", bbox_inches="tight")
    plt.close(fig)
    return buf.getvalue()


def export_color_dxf(program_boxes, circulation_specs, voxels, voxel_ft,
                      real_geometry, typology_specs, site_width_ft, site_length_ft, out_path, show_labels=True,
                      zones=None):
    """DXF counterpart -- one named layer per category (base 4 + COLUMNS/
    TREES, plus one CONTOURS_<z> true-color layer per elevation band --
    see the CONTOURS handling below), real site-feet coordinates, for
    CAD/Rhino import with layers and colors preserved (see
    save_drawing()'s docstring for why DXF, not PNG, is the right format
    for "preserve layers and colors")."""
    import ezdxf
    from ezdxf.colors import rgb2int

    categorized, detail, _width, _height = _color_geometry(
        program_boxes, circulation_specs, voxels, voxel_ft,
        real_geometry, typology_specs, site_width_ft, site_length_ft, zones=zones,
    )

    doc = ezdxf.new("R2010")
    msp = doc.modelspace()
    for category in spe.CATEGORIES:
        aci = spe.STYLE_COLORS_ACI[category]
        doc.layers.add(category, dxfattribs={"color": aci})
        for pts in categorized.get(category, []):
            if len(pts) >= 2:
                msp.add_lwpolyline(list(pts), dxfattribs={"layer": category})
                # Solid fill (poche) for BUILDING/LANDSCAPE -- see
                # render_color_svg's own comment for why they get different
                # treatment.
                if category in (spe.CATEGORY_BUILDING, spe.CATEGORY_LANDSCAPE) and len(pts) >= 3:
                    hatch = msp.add_hatch(dxfattribs={"layer": category, "color": aci})
                    hatch.set_solid_fill(color=aci)
                    hatch.paths.add_polyline_path(list(pts), is_closed=True)
                # 2026-08-14: HARDSCAPE gets a pattern hatch (not solid) --
                # see render_color_svg's own comment for why it gets a third
                # treatment distinct from solid fill and plain outline.
                if category == spe.CATEGORY_HARDSCAPE and len(pts) >= 3:
                    pattern = vector_export._DXF_HATCH_PATTERN[vector_export.HATCH_BUILDING]
                    hatch = msp.add_hatch(dxfattribs={"layer": category, "color": aci})
                    hatch.set_pattern_fill(pattern, scale=2.0)
                    hatch.paths.add_polyline_path(list(pts), is_closed=True)
    # Detail layers use the closest standard ACI colors to their hex swatches
    # (DXF's base palette has no arbitrary true-color layer setting in R2010).
    # CONTOURS is handled separately below -- it needs true_color (one layer
    # per elevation band, ACI's 256-color palette can't represent a smooth
    # grey ramp), same true-color pattern export_diagram_dxf already
    # establishes for per-group layers.
    detail_aci = {"COLUMNS": 9, "TREES": 3}
    for category, polylines in detail.items():
        if category == "CONTOURS":
            gradient = _contour_gradient_colors([z for z, _ in polylines])
            for z, band_polylines in polylines:
                layer_name = f"CONTOURS_{z:.2f}"
                rgb = _hex_to_rgb(gradient[z])
                doc.layers.add(layer_name, dxfattribs={"true_color": rgb2int(rgb)})
                for pts in band_polylines:
                    if len(pts) >= 2:
                        msp.add_lwpolyline(list(pts), dxfattribs={"layer": layer_name})
            continue
        aci = detail_aci[category]
        doc.layers.add(category, dxfattribs={"color": aci})
        for pts in polylines:
            if len(pts) >= 2:
                msp.add_lwpolyline(list(pts), dxfattribs={"layer": category})
                if category == "TREES" and len(pts) >= 3:
                    hatch = msp.add_hatch(dxfattribs={"layer": category, "color": aci})
                    hatch.set_solid_fill(color=aci)
                    hatch.paths.add_polyline_path(list(pts), is_closed=True)
    if show_labels:
        doc.layers.add("LABELS", dxfattribs={"color": 7})  # white
        for text, (x, y), angle in vector_export.street_label_points(site_width_ft, site_length_ft):
            msp.add_text(
                text, dxfattribs={"layer": "LABELS", "height": 8.0, "rotation": angle}
            ).set_placement((x, y))
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
