"""
Memory Machine -- SVG Diagram Ingestion (2026-07-14).

Reads a solid-fill site diagram exported by diagram_tool/ (the standalone
2D zone-placement tool forked from the old Digital Palimpsest app,
archived at archive/diagrams/site_svgs/site_diagram_<epoch_ms>.svg) and
converts it into the SAME JSON shape ingest_legacy_diagram.py's
rasterize_to_paint_state() already produces: {"canyon", "hardscape",
"water", "trees", "greenscape", "amenity_resting"}, each an (nx, nz)
nested list matching TerracingEngine's voxel grid.

WHY THIS MODULE EXISTS, AND WHY IT'S NOT JUST A ingest_legacy_diagram.py
EDIT: that module reverse-engineers design intent from a RASTERIZED PHOTO
(pixel colors, thresholds, antialiasing noise) of an exported diagram --
fragile by construction, and the direct cause of two real bugs chased in
this repo (boundary-line antialiasing misread as hardscape/shade, 2026-07-13;
zone fills rendering ~5x too dark to match any color threshold at all,
also 2026-07-13, root-caused 2026-07-14 to diagram_tool's predecessor
applying a hardcoded 30% fill-opacity that survived into every export).
This module instead parses the SVG's actual vector data directly -- exact
`fill` attributes as color strings, exact shape vertex coordinates, and
group `id` attributes carrying the ORIGINAL Rhino layer name (e.g.
"GREEN_SPACE") through the whole pipeline unchanged. No color thresholds,
no antialiasing, no pixel classification of any kind.

THE ROTATION PROBLEM still applies and is NOT solved by moving to SVG --
per direct user confirmation (2026-07-14), diagram_tool's SVG export is
"the same size and orientation as the other images", i.e. still true-north
rotated, same as ingest_legacy_diagram.py's original JPG pipeline. So the
exact same rectification approach is reused here, just fed exact SVG
vertex coordinates (from the boundary group's path/polygon geometry)
instead of a cv2-thresholded white-pixel point cloud -- cv2.minAreaRect
works identically on either kind of point cloud, and exact vector
coordinates should if anything be MORE reliable than thresholded pixels,
never less.

Reuses ingest_legacy_diagram.py's BoundaryAffine class and calibrated
FLIP_X/FLIP_Y constants unchanged -- the rectification math doesn't care
whether its input points came from pixels or vectors. Rasterization,
however, is NOT reused as-is: rasterize_to_paint_state() marks the grid
cell under each individual input POINT, which was correct for the pixel
pipeline (every matching pixel densely samples the filled area) but wrong
for vector shapes (a polygon's own vertices are just its corners, not a
sampling of its interior). This module's rasterize_zone_polygons() instead
tests every grid cell's center against each shape via proper
point-in-polygon fill testing (reusing sketch_weight_mapper's
_points_in_polygon, the same routine find_closed_svg_regions() already
uses for SVG-sourced regions elsewhere in this codebase).
"""
import os
import re
import xml.etree.ElementTree as ET

import cv2
import numpy as np

from ingest_legacy_diagram import (
    BoundaryAffine, FLIP_X, FLIP_Y, SANITY_ANGLE_RANGE_DEG,
    VOXEL_FT, _load_real_geometry, _require_calibration,
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SVG_DIAGRAM_DIR = os.path.join(BASE_DIR, "archive", "diagrams", "site_svgs")

SVG_NS = "http://www.w3.org/2000/svg"

# Same precedence/keyword rule as diagram_tool/static/js/main.js's
# _getLayerColor() -- SHADE checked before GREEN so a layer whose id
# contains both substrings (shouldn't happen, but matches the JS side's
# own ordering exactly) never misclassifies. Anything matching none of
# these falls through to hardscape, same as the JS fallback.
_ZONE_KEYWORD_ORDER = [
    ("trees", ["SHADE"]),
    ("greenscape", ["GREEN"]),
    ("water", ["WATER"]),
]

# Point-marker categories (2026-07-14), confirmed via direct inspection of
# data/PershingMetabolizer/parkSVG/PrecedentSVG/*.svg -- MAJOR_ATTRACTORS/
# MINOR_ATTRACTORS/AMPHITHEATRE are always circles, one per placed asset
# (a future pavilion/vending-building/tennis-court/etc. 3D model, per user
# decision: NOT carved into the terrain via canyon/excavation logic or
# scored against target_sf like program_placement.py's zones -- these are
# points a 3D asset gets seated on top of, same pattern as the old Digital
# Palimpsest app's loadGLBIntoScene()). Kept as a SEPARATE keyword list
# from _ZONE_KEYWORD_ORDER above -- these never contribute to the
# hardscape/water/trees/greenscape area grid at all, not even as a
# fallback, since they're not area content.
_ATTRACTOR_KEYWORD_ORDER = [
    ("major_attractor", ["MAJOR_ATTRACTOR"]),
    ("minor_attractor", ["MINOR_ATTRACTOR"]),
    ("amphitheatre", ["AMPHITHEATRE"]),
]


def _local_tag(el):
    """Strip the SVG XML namespace off a tag name, e.g. '{...}path' -> 'path'."""
    return el.tag.rsplit('}', 1)[-1] if '}' in el.tag else el.tag


def _extract_vertices(el):
    """(N, 2) pixel-coordinate array for one SVG shape element, or None if
    it contributes no area/length. Mirrors diagram_tool's own
    static/js/state.js _extractVertices() exactly, so a shape parses to the
    same points here as it did when the tool computed its own HUD stats."""
    tag = _local_tag(el)

    if tag == 'rect':
        x = float(el.get('x', 0)); y = float(el.get('y', 0))
        w = float(el.get('width', 0)); h = float(el.get('height', 0))
        if w == 0 or h == 0:
            return None
        return np.array([[x, y], [x + w, y], [x + w, y + h], [x, y + h]])

    if tag == 'circle':
        cx = float(el.get('cx', 0)); cy = float(el.get('cy', 0)); r = float(el.get('r', 0))
        if r == 0:
            return None
        angles = np.linspace(0, 2 * np.pi, 16, endpoint=False)
        return np.column_stack([cx + np.cos(angles) * r, cy + np.sin(angles) * r])

    if tag == 'line':
        return None  # no area

    d = el.get('d') or el.get('points') or ''
    if not d:
        return None

    # Strip SVG arc parameters (rx ry x-rot large-arc sweep) so arc radii
    # aren't mistaken for coordinate pairs -- same regex as
    # ingest_legacy_diagram.py doesn't need this (it never saw arcs), but
    # state.js's own _extractVertices() does this exact strip first.
    d = re.sub(r'[Aa]\s*[-+]?[\d.]+\s*[,\s]+[-+]?[\d.]+\s*[,\s]+[-+]?[\d.]+\s*[,\s]+[01]\s*[,\s]+[01]\s*[,\s]*', '', d)

    nums = [float(m) for m in re.findall(r'-?\d+\.?\d*(?:[eE][-+]?\d+)?', d)]
    if len(nums) < 4:
        return None
    if len(nums) % 2 != 0:
        nums = nums[:-1]
    return np.array(nums).reshape(-1, 2)


def _find_groups_by_id_substring(root, substrings):
    """All <g id="..."> elements anywhere in the tree whose id contains any
    of substrings (case-insensitive) -- same matching convention as
    engine2D.js's querySelector('g[id*="X"]') / main.js's KNOWN_LAYERS scan."""
    matches = []
    for g in root.iter():
        if _local_tag(g) != 'g':
            continue
        gid = (g.get('id') or '').upper()
        if any(s in gid for s in substrings):
            matches.append(g)
    return matches


def _group_vertices(group_el):
    """All shape vertices inside one <g>, concatenated into one (N, 2)
    array -- used ONLY for boundary detection, where the shape is always
    stroke-only (never filled) and cv2.minAreaRect just needs the overall
    point cloud's extent/orientation, not a real filled region. Zone
    classification uses _group_polygons() instead, which requires an
    actual fill and keeps each shape separate for point-in-polygon fill
    testing."""
    pts = []
    for child in group_el.iter():
        if child is group_el:
            continue
        if _local_tag(child) in ('path', 'polyline', 'polygon', 'rect', 'circle'):
            v = _extract_vertices(child)
            if v is not None:
                pts.append(v)
    if not pts:
        return np.zeros((0, 2))
    return np.vstack(pts)


def _has_real_fill(el):
    """True if this element is actually filled (fill != none/absent/empty).
    Required check, not optional -- a shape with no fill is linework, not a
    zone region, and its vertex loop must not be treated as one. This is
    the exact semantic diagram_tool's engine2D.js itself uses (`hadFill`)
    to decide whether to color a shape's fill at all."""
    fill = el.get('fill') or ''
    style = el.get('style') or ''
    m = re.search(r'fill\s*:\s*([^;]+)', style)
    if m:
        fill = m.group(1).strip()
    return fill not in ('', 'none')


def _group_polygons(group_el):
    """Each individually-filled shape inside one <g>, as a separate (Ni, 2)
    vertex-loop array -- kept as separate polygons (not concatenated into
    one point cloud) so each can be properly filled via point-in-polygon
    testing rather than just plotting its corner vertices. Skips any shape
    without a real fill (see _has_real_fill) -- pure linework contributes
    no zone area, matching diagram_tool's own on-screen semantics."""
    polys = []
    for child in group_el.iter():
        if child is group_el:
            continue
        if _local_tag(child) in ('path', 'polyline', 'polygon', 'rect', 'circle'):
            if not _has_real_fill(child):
                continue
            v = _extract_vertices(child)
            if v is not None and len(v) >= 3:
                polys.append(v)
    return polys


def detect_boundary_affine_from_svg(root, site_width_ft, site_length_ft, flip_x, flip_y,
                                     sanity_angle_range=SANITY_ANGLE_RANGE_DEG):
    """SVG-native equivalent of ingest_legacy_diagram.py's
    detect_boundary_affine(): find the BOUNDARY group's exact vertices
    (instead of thresholding near-white pixels) and run the identical
    cv2.minAreaRect rectification on them. Returns (BoundaryAffine,
    boundary_points_px, raw_angle) -- same shape as the pixel version."""
    boundary_groups = _find_groups_by_id_substring(root, ["BOUNDARY"])
    if not boundary_groups:
        raise ValueError("no <g id=\"...BOUNDARY...\"> group found in this SVG")

    pts = np.vstack([_group_vertices(g) for g in boundary_groups])
    # >= 3 (not the pixel-scan version's >= 10): that threshold guarded
    # against noisy thresholded-pixel point clouds where a handful of
    # stray matches could be JPEG artifacts, not real boundary; exact
    # vector geometry has no such noise, and cv2.minAreaRect only needs
    # 3 non-collinear points to fit a rectangle.
    if len(pts) < 3:
        raise ValueError(f"boundary group has only {len(pts)} vertices, need >= 3 to detect orientation")

    (cx, cy), (w, h), raw_angle = cv2.minAreaRect(pts.astype(np.float32))

    affine = BoundaryAffine(
        center_px=(cx, cy), raw_angle_deg=raw_angle, raw_w_px=w, raw_h_px=h,
        site_width_ft=site_width_ft, site_length_ft=site_length_ft,
        flip_x=flip_x, flip_y=flip_y,
    )

    normalized = raw_angle % 90.0
    lo, hi = sanity_angle_range
    if not (lo <= normalized <= hi or lo <= (90 - normalized) <= hi):
        print(f"WARNING: detected boundary angle {raw_angle:.1f} deg (normalized "
              f"{normalized:.1f}) falls outside the sanity range {sanity_angle_range}. "
              f"Proceeding anyway (per-diagram detection is trusted over that range) "
              f"-- double check this export.")

    return affine, pts, raw_angle


def classify_svg_zones(root):
    """Find each known zone category's placed, FILLED shapes by their
    group `id` substring (the ORIGINAL Rhino layer name, preserved through
    diagram_tool's clone-and-transform export) -- NOT by color. Returns
    {"hardscape": [poly, poly, ...], "water": [...], "trees": [...],
    "greenscape": [...]} -- a list of separate (Ni,2) pixel-space vertex
    loops per category (NOT concatenated into one point cloud: each shape
    needs to be filled independently via point-in-polygon testing, see
    rasterize_zone_polygons()).

    Only searches inside .intervention-group-wrapped content (shapes the
    user actually placed) -- diagram_tool's own context-group clones of
    these same layer ids for on-screen base-context display are always
    stroke-only (fill:none, see engine2D.js), so excluding them isn't just
    an optimization, it's necessary: they'd contribute zero real area but
    could still match the same id substrings. _group_polygons() also
    drops any shape lacking a real fill for the same reason.
    """
    intervention_wrappers = [
        g for g in root.iter()
        if _local_tag(g) == 'g' and 'intervention-group' in (g.get('class') or '')
    ]

    classified = {"hardscape": [], "water": [], "trees": [], "greenscape": []}
    for wrapper in intervention_wrappers:
        # The wrapper contains one cloned original layer group, e.g.
        # <g id="GREEN_SPACE_042">...</g> -- id substring match decides
        # its category, same precedence order as _getLayerColor().
        layer_groups = [g for g in wrapper.iter() if _local_tag(g) == 'g' and g is not wrapper]
        for lg in layer_groups:
            gid = (lg.get('id') or '').upper()
            category = 'hardscape'  # fallback, matches _getLayerColor()'s STREET/PATH/etc. default
            for cat, keywords in _ZONE_KEYWORD_ORDER:
                if any(k in gid for k in keywords):
                    category = cat
                    break
            classified[category].extend(_group_polygons(lg))

    return classified


def classify_svg_points(root):
    """Find each attractor category's placed markers by group `id`
    substring, same convention as classify_svg_zones() -- but returns a
    single (cx, cy) CENTROID per marker (pixel space), not a filled
    polygon, since these are discrete asset-placement points, not area
    regions.

    Does NOT assume the filled shape is a <circle> -- confirmed via a real
    exported diagram_tool file that a marker's actual fill lives on an
    organic <path> "icon" shape, while a genuine <circle> sibling is
    present but fill:none (just a decorative selection ring). Accepts any
    filled shape type (same set _group_polygons() checks) and takes the
    mean of its extracted vertices as the centroid -- exact for a real
    <circle> (mean of 16 evenly-spaced points around it = its true
    center), and a reasonable centroid for an arbitrary filled blob shape.

    Same intervention-group-only scoping and real-fill requirement as
    classify_svg_zones() -- context-group clones of these same layer ids
    are stroke-only and must not double-count as placed markers.
    """
    intervention_wrappers = [
        g for g in root.iter()
        if _local_tag(g) == 'g' and 'intervention-group' in (g.get('class') or '')
    ]

    classified = {"major_attractor": [], "minor_attractor": [], "amphitheatre": []}
    for wrapper in intervention_wrappers:
        layer_groups = [g for g in wrapper.iter() if _local_tag(g) == 'g' and g is not wrapper]
        for lg in layer_groups:
            gid = (lg.get('id') or '').upper()
            category = None
            for cat, keywords in _ATTRACTOR_KEYWORD_ORDER:
                if any(k in gid for k in keywords):
                    category = cat
                    break
            if category is None:
                continue  # not an attractor/amphitheatre layer -- classify_svg_zones handles it instead

            for poly in _group_polygons(lg):
                centroid = poly.mean(axis=0)
                classified[category].append((float(centroid[0]), float(centroid[1])))

    return classified


def extract_attractor_points(svg_path):
    """Full pipeline for one SVG export's point markers only: parse ->
    detect boundary/rectify -> classify placed attractor/amphitheatre
    circles by id -> transform centroids to site-feet. Returns
    {"major_attractor": [{"x_ft":.., "y_ft":..}, ...], "minor_attractor":
    [...], "amphitheatre": [...]} -- deliberately NOT part of
    convert_svg_to_paint_state()'s 6-key grid dict, since these are
    discrete placement points for a future 3D-asset-library step, not
    area masks (see this module's _ATTRACTOR_KEYWORD_ORDER comment)."""
    _require_calibration()
    real_geometry = _load_real_geometry()
    site_width_ft = real_geometry["site"]["width_ft"]
    site_length_ft = real_geometry["site"]["length_ft"]

    tree = ET.parse(svg_path)
    root = tree.getroot()

    affine, _boundary_pts, _angle = detect_boundary_affine_from_svg(
        root, site_width_ft, site_length_ft, FLIP_X, FLIP_Y)

    category_points_px = classify_svg_points(root)
    result = {}
    for cat, pts_px in category_points_px.items():
        if not pts_px:
            result[cat] = []
            continue
        pts_ft = affine.transform(np.array(pts_px))
        result[cat] = [{"x_ft": float(x), "y_ft": float(y)} for x, y in pts_ft]
    return result


def rasterize_zone_polygons(category_polygons_ft, nx, nz, voxel_ft):
    """Proper polygon-fill rasterization: for each category, test every
    grid cell's CENTER point against each of that category's (already
    site-feet) polygons via point-in-polygon (even-odd rule, reusing
    sketch_weight_mapper._points_in_polygon -- same algorithm
    find_closed_svg_regions() already uses for SVG-sourced regions
    elsewhere in this codebase). A cell counts if it falls inside ANY
    polygon of that category.

    This replaces naively marking only each polygon's own VERTEX
    coordinates (which -- confirmed via a real test export -- rasterizes
    a shape's outline/corners, not its filled interior, since a large
    polygon's few corner points cover only a small fraction of the grid
    cells actually inside it).

    canyon/amenity_resting stay all-zero -- diagram_tool has no layer that
    maps to either, same limitation the old JPG pipeline had.
    """
    from sketch_weight_mapper import _points_in_polygon

    gx_centers = (np.arange(nx) + 0.5) * voxel_ft
    gy_centers = (np.arange(nz) + 0.5) * voxel_ft
    gxx, gyy = np.meshgrid(gx_centers, gy_centers, indexing="ij")
    grid_pts = np.stack([gxx.ravel(), gyy.ravel()], axis=1)

    masks = {}
    # amenity_resting added 2026-07-16 (Precedent Remixer) -- the only
    # caller that ever populates this category is rasterize_precedent_layers
    # below; convert_svg_to_paint_state's own classify_svg_zones() never
    # produces an "amenity_resting" key, so .get(..., []) keeps that path's
    # existing all-zero behavior unchanged.
    for category in ("hardscape", "water", "trees", "greenscape", "amenity_resting"):
        inside_any = np.zeros(len(grid_pts), dtype=bool)
        for poly in category_polygons_ft.get(category, []):
            if len(poly) < 3:
                continue
            inside_any |= _points_in_polygon(poly, grid_pts)
        masks[category] = inside_any.reshape(nx, nz)

    return {
        "canyon": np.zeros((nx, nz)).tolist(),
        "hardscape": masks["hardscape"].tolist(),
        "water": masks["water"].tolist(),
        "trees": masks["trees"].tolist(),
        "greenscape": masks["greenscape"].tolist(),
        "amenity_resting": masks["amenity_resting"].tolist(),
    }


# Intentional overlap effects (2026-07-23) -- see spatialize_preview()'s
# docstring in logic/pershing_api.py for the full reasoning. First (and so
# far only) case: HARDSCAPE + WATER overlapping in a 2D diagram becomes a
# deliberate rupture -- water breaking through pavement -- rather than
# silently resolving via terracing_engine.py's implicit hardscape-veto-wins
# rule. Other pairs (hardscape+greenscape as a blended material, etc.) are
# explicitly future iterations, not handled here yet.
OVERLAP_CANYON_WEIGHT = 0.85  # tunable; passes through _effective_influence()'s clamp01


def apply_hardscape_water_overlap(grids):
    """
    Mutates and returns `grids` (the standard 6-key rasterize_zone_polygons()
    shape) in place: wherever `hardscape` and `water` are BOTH True for a
    cell, treat it as a deliberate rupture instead of leaving it to
    terracing_engine.py's implicit resolution.

    Why "leaving it to terracing_engine.py" wouldn't work at all here, not
    just "wouldn't look right": _z_for_voxel() (terracing_engine.py
    ~line 429) has `elif v.is_hardscape: return 0.0` -- an UNCONDITIONAL
    early return, checked before the canyon/sketch_weight blend a few lines
    later is ever reached. So a cell left with hardscape=True cannot be
    excavated by ANY canyon weight, however high -- the veto silences it
    completely. This function clears `hardscape` on overlap cells (this
    cell is no longer "designer-protected, stay flat"), leaves `water`
    True (so once the canyon weight below actually excavates it below
    grade, _classify_typology()'s existing `if v.z_ft < 0 and v.is_water:
    return "GROTTO"` rule picks it up automatically -- no new typology
    needed), and sets `canyon` to OVERLAP_CANYON_WEIGHT so
    _effective_influence() has something to actually dig with.

    Returns (grids, overlap_cell_count) -- the count is purely informational
    (e.g. for a log line), not used by the mutation itself.
    """
    hardscape = np.array(grids["hardscape"], dtype=bool)
    water = np.array(grids["water"], dtype=bool)
    canyon = np.array(grids["canyon"], dtype=float)

    overlap = hardscape & water
    hardscape = hardscape & ~overlap
    canyon = np.where(overlap, OVERLAP_CANYON_WEIGHT, canyon)

    grids["hardscape"] = hardscape.tolist()
    grids["canyon"] = canyon.tolist()
    return grids, int(overlap.sum())


def convert_svg_to_paint_state(svg_path, nx=None, nz=None, voxel_ft=VOXEL_FT):
    """Full pipeline for one SVG export: parse -> detect boundary/rectify
    -> classify placed zones by id (filled shapes only) -> transform each
    shape's vertices to site-feet -> fill-rasterize onto the voxel grid.
    Returns the web_paint_state.json-shaped dict (same 6 keys
    ingest_legacy_diagram.py's convert_one() also returns)."""
    _require_calibration()
    real_geometry = _load_real_geometry()
    site_width_ft = real_geometry["site"]["width_ft"]
    site_length_ft = real_geometry["site"]["length_ft"]

    if nx is None or nz is None:
        import math
        nx = math.ceil(site_width_ft / voxel_ft)
        nz = math.ceil(site_length_ft / voxel_ft)

    tree = ET.parse(svg_path)
    root = tree.getroot()

    affine, _boundary_pts, _angle = detect_boundary_affine_from_svg(
        root, site_width_ft, site_length_ft, FLIP_X, FLIP_Y)

    category_polygons_px = classify_svg_zones(root)
    category_polygons_ft = {
        cat: [affine.transform(poly) for poly in polys]
        for cat, polys in category_polygons_px.items()
    }
    return rasterize_zone_polygons(category_polygons_ft, nx, nz, voxel_ft)


# ---------------------------------------------------------------------------
# Precedent Remixer rasterization (2026-07-16)
# ---------------------------------------------------------------------------
# logic.urban_engine.remix_layers() picks precedent layers (site/layerId)
# and a placement transform for a curated design intent, but only ever
# returned that curated stack for PREVIEW -- see logic/pershing_api.py's
# remix_precedent() docstring, which explicitly deferred "rasterize these
# layers into real paint-mask grids" as separate follow-up work. This
# closes that gap by reusing this module's own machinery (BoundaryAffine,
# _group_polygons, rasterize_zone_polygons) instead of writing a parallel
# SVG-to-grid pipeline.
#
# Unlike convert_svg_to_paint_state() above (one already-placed diagram,
# one boundary to rectify), this pulls layers from MULTIPLE precedent
# SVGs, each with its OWN boundary/coordinate space, and places them onto
# Pershing Square's. The placement math mirrors diagram_tool/static/js/
# engine2D.js's render() exactly (uniform fit-scale by boundary bbox size,
# rotate, translate by an offset relative to Pershing's own boundary
# center) -- same operation, same "drop a precedent layer onto Pershing's
# boundary" intent, just executed in Python against raw SVG data instead
# of the DOM. Only once a layer's points land in PERSHING's own SVG pixel
# space do they go through Pershing's calibrated BoundaryAffine to become
# real site feet -- there is no real-world calibration for the SOURCE
# site's own pixel space, nor does one make sense (a precedent's SVG units
# have no real-feet meaning on their own, only relative to Pershing's
# boundary once placed).
PRECEDENT_SVG_DIR = os.path.join(
    BASE_DIR, "data", "PershingMetabolizer", "parkSVG", "PrecedentSVG")

# Parsed-SVG-per-site cache -- a remix commonly reuses the same site for
# multiple curated layers (e.g. several ZaryadyePark picks in one prompt),
# and each site's SVG can be a few hundred KB; re-parsing per layer would
# be wasteful for no benefit within one rasterize_precedent_layers() call.
_precedent_svg_cache = {}


def _load_precedent_svg(site):
    if site not in _precedent_svg_cache:
        path = os.path.join(PRECEDENT_SVG_DIR, f"{site}.svg")
        if not os.path.exists(path):
            raise FileNotFoundError(f"no precedent SVG for site {site!r} at {path}")
        _precedent_svg_cache[site] = ET.parse(path).getroot()
    return _precedent_svg_cache[site]


def _boundary_bbox_center_and_size(root):
    """(cx, cy, w, h) of the BOUNDARY group's cv2.minAreaRect, in this SVG's
    own pixel space -- the same detection detect_boundary_affine_from_svg
    already does, factored out here so it can run on a precedent's SOURCE
    SVG too (which has no real-feet calibration of its own, so the full
    detect_boundary_affine_from_svg -- which needs site_width_ft/
    site_length_ft -- doesn't apply; only the raw pixel-space bbox does).

    Falls back to a content bbox (union of every shape's vertices across
    the whole document) when no BOUNDARY group exists -- confirmed
    2026-07-16 that only 3 of the 5 canonical precedent SVGs actually have
    one (PershingSquare/ParcVillette/GardensBytheBay do, ZaryadyePark/
    Schouwburgplein don't). Deliberately NOT the SVG's own <svg viewBox>
    (all 5 files share an identical "0 0 2592 1728" page-size viewBox --
    confirmed by direct inspection -- a fixed export-canvas size, not a
    per-site content extent, so it would silently produce a wrong
    fit-scale for every layer pulled from a boundary-less site; the same
    fallback engine2D.js's getBoundaryBBox() uses client-side, which this
    module deliberately does NOT mirror here since it's demonstrably wrong
    for this use)."""
    boundary_groups = _find_groups_by_id_substring(root, ["BOUNDARY"])
    if boundary_groups:
        pts = np.vstack([_group_vertices(g) for g in boundary_groups])
    else:
        all_pts = []
        for el in root.iter():
            if _local_tag(el) in ('path', 'polyline', 'polygon', 'rect', 'circle'):
                v = _extract_vertices(el)
                if v is not None:
                    all_pts.append(v)
        if not all_pts:
            raise ValueError("no BOUNDARY group and no shape geometry at all in this precedent SVG")
        pts = np.vstack(all_pts)
    (cx, cy), (w, h), _angle = cv2.minAreaRect(pts.astype(np.float32))
    return cx, cy, w, h


def _find_layer_group(root, layer_id):
    """First group whose id contains layer_id (case-insensitive) -- same
    fuzzy-match convention diagram_tool's engine2D.js render() and picker
    UI already use for the identical lookup."""
    matches = _find_groups_by_id_substring(root, [layer_id])
    return matches[0] if matches else None


# Cardinal placement as a FRACTION of Pershing's own detected boundary
# width/height, not a fixed pixel offset -- logic/urban_engine.py's
# original LOCATION_OFFSETS were hand-tuned pixel values ("~436x468 SVG
# units") calibrated against a since-replaced precedent SVG; the current
# canonical PershingSquare.svg's boundary is ~924x991 units (confirmed via
# live cv2.minAreaRect detection, 2026-07-16), roughly double -- a fixed
# pixel offset from the old file would place everything at the wrong
# fraction of the (now larger) site. Fractions are resolution-independent,
# so this can't drift out of calibration again the same way.
LOCATION_OFFSET_FRAC = {
    "Center":      (0.0, 0.0),
    "North":       (0.0, -0.3),
    "South":       (0.0, 0.3),
    "East":        (0.3, 0.0),
    "West":        (-0.3, 0.0),
    "North-East":  (0.22, -0.22),
    "North-West":  (-0.22, -0.22),
    "South-East":  (0.22, 0.22),
    "South-West":  (-0.22, 0.22),
}


def rasterize_precedent_layers(composed_layers, nx=None, nz=None, voxel_ft=VOXEL_FT):
    """
    Converts remix_precedent()'s composed layer stack (each item: site,
    layerId, transform, role) into the SAME 6-key paint-state grid shape
    every other ingestion path in this module produces, ready for bake().

    Per layer:
    1. Load the named precedent site's SVG (PRECEDENT_SVG_DIR -- the same
       canonical source diagram_tool/ and this module's own
       convert_svg_to_paint_state() already use).
    2. Find the named layer group inside it (fuzzy id match) and extract
       its filled polygons (_group_polygons -- no wrapper-scoping
       assumption, unlike classify_svg_zones's intervention-group-only
       scoping above, since these come straight from a precedent source
       file, not a diagram_tool export).
    3. Fit-and-place into PERSHING's own SVG pixel space: uniform scale by
       min(pershing_bbox / source_bbox) on each axis, rotate by the
       transform's rot, translate by the transform's x_frac/y_frac (of
       Pershing's own boundary size) relative to Pershing's boundary
       center -- the exact placement operation engine2D.js's render()
       performs for a live picker-driven placement, just executed here in
       Python against parsed SVG data instead of the DOM.
    4. Feed those now-Pershing-pixel-space points through Pershing's own
       calibrated BoundaryAffine to get real site feet.
    5. Rasterize per role via rasterize_zone_polygons (point-in-polygon at
       each voxel cell's center) -- multiple layers sharing a role OR
       together (a cell counts if ANY same-role layer covers it), same
       "any stroke marks it" semantics manual painting already has. A cell
       CAN end up True in multiple DIFFERENT roles if their layers overlap
       -- see spatialize_preview() (logic/pershing_api.py) and
       apply_hardscape_water_overlap() below for the one overlap pair that
       currently gets a deliberate, specific treatment; everything else
       still falls through to terracing_engine.py's own per-module rules.

    Layers whose site/layerId don't resolve to real geometry (missing SVG,
    layer id not found, empty polygon list) are silently skipped, not
    fatal -- an AI-curated layer pick failing to resolve shouldn't abort
    the whole remix, same tolerance this module's puncture/footprint
    lookups already show elsewhere.
    """
    _require_calibration()
    real_geometry = _load_real_geometry()
    site_width_ft = real_geometry["site"]["width_ft"]
    site_length_ft = real_geometry["site"]["length_ft"]

    if nx is None or nz is None:
        import math
        nx = math.ceil(site_width_ft / voxel_ft)
        nz = math.ceil(site_length_ft / voxel_ft)

    pershing_root = _load_precedent_svg("PershingSquare")
    pcx, pcy, pw, ph = _boundary_bbox_center_and_size(pershing_root)
    affine, _pts, _angle = detect_boundary_affine_from_svg(
        pershing_root, site_width_ft, site_length_ft, FLIP_X, FLIP_Y)

    category_polygons_ft = {"hardscape": [], "water": [], "trees": [], "greenscape": [], "amenity_resting": []}
    resolved_count = 0

    for item in composed_layers:
        role = item.get("role")
        if role not in category_polygons_ft:
            continue  # e.g. "canyon" has no rasterization target -- see remix_precedent()'s docstring

        try:
            src_root = _load_precedent_svg(item["site"])
        except FileNotFoundError:
            continue
        layer_g = _find_layer_group(src_root, item["layerId"])
        if layer_g is None:
            continue
        src_polys_px = _group_polygons(layer_g)
        if not src_polys_px:
            continue

        scx, scy, sw, sh = _boundary_bbox_center_and_size(src_root)
        fit_scale = min(pw / (sw or 1.0), ph / (sh or 1.0))
        t = item.get("transform") or {}
        final_scale = fit_scale * (t.get("scale") or 1.0)
        rot = np.radians(t.get("rot") or 0.0)
        cos_r, sin_r = np.cos(rot), np.sin(rot)
        offset_x = pcx + (t.get("x_frac") or 0.0) * pw
        offset_y = pcy + (t.get("y_frac") or 0.0) * ph

        for poly_px in src_polys_px:
            shifted = poly_px - np.array([scx, scy])
            rotated = np.stack([
                shifted[:, 0] * cos_r - shifted[:, 1] * sin_r,
                shifted[:, 0] * sin_r + shifted[:, 1] * cos_r,
            ], axis=1)
            placed_px = rotated * final_scale + np.array([offset_x, offset_y])
            category_polygons_ft[role].append(affine.transform(placed_px))
        resolved_count += 1

    masks = rasterize_zone_polygons(category_polygons_ft, nx, nz, voxel_ft)
    return masks, resolved_count


def extract_attractor_points_from_composed_layers(composed_layers):
    """
    Companion to rasterize_precedent_layers() -- same composed layer stack,
    same per-item load/fit-scale/rotate/translate/affine pipeline, but
    pulls out MAJOR_ATTRACTOR/MINOR_ATTRACTOR/AMPHITHEATRE point-marker
    centroids instead of filling area polygons for hardscape/water/trees/
    greenscape/amenity_resting. Added 2026-07-17 so the Precedent Remixer
    (AI/random generator) can place real attractor markers that flow into
    3D program placement the same way a manually-composed diagram_tool
    export already does via extract_attractor_points() above -- see that
    function's docstring for why these are discrete points, not area
    masks, and logic/pershing_api.py's _bay_grid_from_engine()/
    program_placement.py for how they get consumed.

    Returns the same shape extract_attractor_points() does:
    {"major_attractor": [{"x_ft":.., "y_ft":..}, ...], "minor_attractor":
    [...], "amphitheatre": [...]}.
    """
    _require_calibration()
    real_geometry = _load_real_geometry()
    site_width_ft = real_geometry["site"]["width_ft"]
    site_length_ft = real_geometry["site"]["length_ft"]

    pershing_root = _load_precedent_svg("PershingSquare")
    pcx, pcy, pw, ph = _boundary_bbox_center_and_size(pershing_root)
    affine, _pts, _angle = detect_boundary_affine_from_svg(
        pershing_root, site_width_ft, site_length_ft, FLIP_X, FLIP_Y)

    result = {"major_attractor": [], "minor_attractor": [], "amphitheatre": []}

    for item in composed_layers:
        layer_id = (item.get("layerId") or "").upper()
        category = None
        for cat, keywords in _ATTRACTOR_KEYWORD_ORDER:
            if any(k in layer_id for k in keywords):
                category = cat
                break
        if category is None:
            continue  # not an attractor/amphitheatre layer -- rasterize_precedent_layers() handles it instead

        try:
            src_root = _load_precedent_svg(item["site"])
        except FileNotFoundError:
            continue
        layer_g = _find_layer_group(src_root, item["layerId"])
        if layer_g is None:
            continue
        src_polys_px = _group_polygons(layer_g)
        if not src_polys_px:
            continue

        scx, scy, sw, sh = _boundary_bbox_center_and_size(src_root)
        fit_scale = min(pw / (sw or 1.0), ph / (sh or 1.0))
        t = item.get("transform") or {}
        final_scale = fit_scale * (t.get("scale") or 1.0)
        rot = np.radians(t.get("rot") or 0.0)
        cos_r, sin_r = np.cos(rot), np.sin(rot)
        offset_x = pcx + (t.get("x_frac") or 0.0) * pw
        offset_y = pcy + (t.get("y_frac") or 0.0) * ph

        for poly_px in src_polys_px:
            centroid_px = poly_px.mean(axis=0)
            shifted = centroid_px - np.array([scx, scy])
            rotated = np.array([
                shifted[0] * cos_r - shifted[1] * sin_r,
                shifted[0] * sin_r + shifted[1] * cos_r,
            ])
            placed_px = rotated * final_scale + np.array([offset_x, offset_y])
            x_ft, y_ft = affine.transform(placed_px.reshape(1, 2))[0]
            result[category].append({"x_ft": float(x_ft), "y_ft": float(y_ft)})

    return result
