"""
Memory Machine -- Structural Grid Analyzer.

Derives real-world column-grid spacing, column/ramp-void positions, slab
bounds, and garage depth from Rhino SVG plan/elevation exports. Extracted
from urban_interference_solver.py so it can be reused by any site, not just
Pershing Square: nothing here is Pershing-specific -- the site identity lives
entirely in the arguments callers pass in (SVG paths, the known reference
spacing used to calibrate scale, and the Rhino layer names the geometry was
exported on).

Ingestion contract this module assumes of the Rhino SVG export:
  - Columns live in a <g id="{column_layer}"> group (possibly with nested
    sublayer <g> children -- searched recursively, not just direct children)
    as <circle> tags (plan view) or as single vertical <path> line segments,
    one per column (elevation view).
  - Site extent/origin is read from a <g id="{boundary_layer}"> group when
    present (a purpose-drawn boundary curve, default id "BOUNDARY") --
    PREFERRED over inferring it from the slab outline. Falls back to the
    slab/site outline in a <g id="{slab_layer}"> group (combined bounding
    box of every <path> found anywhere inside it, including nested
    sublayers, e.g. STRUC__Slabs::L1/L2/L3) only when no boundary layer
    exists in the export.
    Switched to boundary-preferred 2026-07-08: the slab-bbox approach --
    "combine every <path> anywhere inside this group into one bbox" -- was
    fixed once already (2026-07-05, see below) but proved fragile again:
    three separate real re-exports of the same site each gave a
    DIFFERENTLY wrong site-dimension result (not the same bug recurring,
    three distinct failure shapes), pointing to sensitivity to whatever
    incidental geometry a given export sweeps into that group rather than
    one fixable parsing assumption. A boundary curve doesn't have that
    ambiguity -- it's drawn to mean exactly one thing.
    The slab-bbox path is still fixed as originally corrected 2026-07-05:
    an earlier version took only the *first* <path> found, which silently
    measured the wrong (small, unrelated) shape once the real Rhino model
    started drawing STRUC__Slabs as several separate paths/sublayers
    instead of one outline curve -- confirmed via a live Rhino MCP check
    that the real column grid spacing in this SVG is isotropic (dx_pt/dy_pt
    ratio ~0.9998), so that bug was the parsing assumption, not a
    non-uniform page-fit scale. Kept only as a fallback + cross-validation
    reference now, not the primary source.
  - The SVG carries no reliable real-world scale on its own -- callers must
    supply one known on-center spacing (spacing_ft) to calibrate pt-to-ft.
    A single scale factor is valid as long as the export isn't stretched to
    a different aspect ratio than the model (confirmed true for the exports
    checked so far) -- it does not need to be an unscaled/1:1 export; a
    fixed page size (e.g. matching the same sheet size used for hand
    sketches) works fine.
  - An optional single marker <circle> anywhere inside a <g id="{entrance_layer}">
    group (default "metroEntrance") gives a transit-entrance anchor point,
    read the same way column circles are. Added 2026-07-08 specifically to
    retire the live-Rhino-MCP-query workflow that had previously produced a
    real, hard-to-catch bug (secondary_entrance_anchor's z was off by
    ~532ft, see PIPELINE_STATUS_AND_NEXT_STEPS.md) -- a plain Rhino POINT
    object was tried first and confirmed NOT to survive this SVG export at
    all (Rhino's exporter has no fill/stroke to emit for a point with no
    geometry), so a small circle is the marker convention, matching
    columns. Cross-validated against the live-query value on the real site:
    the two independent measurement paths agreed to within 2ft on a 600+ft
    site. Optional and gracefully absent (returns None) for any export that
    doesn't have this layer -- not every site needs a transit anchor.
"""
import re
import math
import statistics
import xml.etree.ElementTree as ET

DEFAULT_COLUMN_LAYER = "STRUC__Columns"
DEFAULT_SLAB_LAYER = "STRUC__Slabs"
DEFAULT_BOUNDARY_LAYER = "BOUNDARY"
DEFAULT_ENTRANCE_LAYER = "metroEntrance"

_SVG_NS = "{http://www.w3.org/2000/svg}"


def _find_group(root, target_id):
    """Find a <g id="target_id"> anywhere in the tree (not just direct children)."""
    for el in root.iter():
        if el.get("id") == target_id:
            return el
    return None


def _all_descendant_ds(group, tag="path"):
    """'d' attributes from every <tag> anywhere inside group, including nested sublayers."""
    return [el.get("d") for el in group.iter(_SVG_NS + tag) if el.get("d")]


def _cluster(values, tol=2.0):
    """Collapse near-duplicate coordinates (Rhino SVG export jitter) into grid lines."""
    values = sorted(values)
    clusters, current = [], [values[0]]
    for v in values[1:]:
        if v - current[-1] <= tol:
            current.append(v)
        else:
            clusters.append(sum(current) / len(current))
            current = [v]
    clusters.append(sum(current) / len(current))
    return clusters


def load_structural_grid_from_svg(svg_path, spacing_ft,
                                   column_layer=DEFAULT_COLUMN_LAYER,
                                   slab_layer=DEFAULT_SLAB_LAYER,
                                   boundary_layer=DEFAULT_BOUNDARY_LAYER,
                                   entrance_layer=DEFAULT_ENTRANCE_LAYER,
                                   cluster_tol=2.0):
    """
    Parse a structural column grid and site extent out of a Rhino plan-view
    SVG export (layers `column_layer` / `boundary_layer` / `slab_layer` /
    `entrance_layer`).

    The SVG only carries abstract drawing units ("pt"), so the real-world
    scale is derived from a known on-center column spacing (spacing_ft) --
    this is the one site-specific fact the caller must supply; everything
    else here is generic parsing/derivation.

    Origin (0,0) is anchored to the bottom-left corner of the site-extent
    bounding box as drawn (boundary curve if present, slab outline
    otherwise) -- true compass orientation in the original Rhino file is
    not confirmed, so flip axes at the call site if north/south end up
    reversed for a given site.
    """
    tree = ET.parse(svg_path)
    root = tree.getroot()

    cols_group = _find_group(root, column_layer)
    raw_columns_pt = [(float(el.get("cx")), float(el.get("cy")))
                       for el in cols_group.iter(_SVG_NS + "circle")]
    # Some Rhino exports duplicate each column (exact-identical cx/cy repeats,
    # e.g. one per rebar/level pass) -- de-dupe by rounded position before use.
    seen = set()
    columns_pt = []
    for x, y in raw_columns_pt:
        key = (round(x, 1), round(y, 1))
        if key not in seen:
            seen.add(key)
            columns_pt.append((x, y))

    # Site footprint/origin: prefer a purpose-drawn BOUNDARY curve over
    # inferring it from the slab outline's combined path bounding box --
    # see module docstring for why the slab-bbox approach was demoted to a
    # fallback (fragile in practice, three different real re-exports of the
    # same site each broke a different way).
    boundary_group = _find_group(root, boundary_layer)
    boundary_corners = []
    if boundary_group is not None:
        boundary_paths = _all_descendant_ds(boundary_group, "path")
        boundary_corners = [(float(a), float(b)) for d in boundary_paths
                             for a, b in re.findall(r'([-\d.]+),([-\d.]+)', d)]

    slab_group = _find_group(root, slab_layer)
    slab_paths = _all_descendant_ds(slab_group, "path")
    slab_corners = [(float(a), float(b)) for d in slab_paths for a, b in re.findall(r'([-\d.]+),([-\d.]+)', d)]

    if boundary_corners:
        corners, extent_source = boundary_corners, "BOUNDARY"
    else:
        corners, extent_source = slab_corners, "STRUC__Slabs (no BOUNDARY layer found -- fallback)"

    min_x = min(c[0] for c in corners)
    max_x = max(c[0] for c in corners)
    min_y = min(c[1] for c in corners)
    max_y = max(c[1] for c in corners)

    cx_lines = _cluster([p[0] for p in columns_pt], tol=cluster_tol)
    cy_lines = _cluster([p[1] for p in columns_pt], tol=cluster_tol)
    dx = statistics.median([cx_lines[i + 1] - cx_lines[i] for i in range(len(cx_lines) - 1)])
    dy = statistics.median([cy_lines[i + 1] - cy_lines[i] for i in range(len(cy_lines) - 1)])
    scale_ft_per_pt = spacing_ft / ((dx + dy) / 2.0)

    site_width_ft = (max_x - min_x) * scale_ft_per_pt
    site_height_ft = (max_y - min_y) * scale_ft_per_pt
    print(f"[grid] site extent from {extent_source}: {site_width_ft:.2f} x {site_height_ft:.2f} ft")

    # Cross-validate against the fallback source whenever both are present,
    # even though BOUNDARY wins -- a silent switch-over gives no signal if
    # the boundary curve itself is ever wrong someday. Same warn-don't-block
    # pattern load_garage_depth_from_svg already uses for multi-elevation
    # cross-validation below.
    if boundary_corners and slab_corners:
        s_min_x = min(c[0] for c in slab_corners); s_max_x = max(c[0] for c in slab_corners)
        s_min_y = min(c[1] for c in slab_corners); s_max_y = max(c[1] for c in slab_corners)
        slab_width_ft = (s_max_x - s_min_x) * scale_ft_per_pt
        slab_height_ft = (s_max_y - s_min_y) * scale_ft_per_pt
        spread_w = abs(slab_width_ft - site_width_ft)
        spread_h = abs(slab_height_ft - site_height_ft)
        if spread_w > 5.0 or spread_h > 5.0:
            print(f"[grid][WARN] STRUC__Slabs-derived extent disagrees with BOUNDARY by "
                  f"{spread_w:.1f}ft (width) / {spread_h:.1f}ft (height) -- "
                  f"slab gives {slab_width_ft:.2f} x {slab_height_ft:.2f} ft. "
                  f"Using BOUNDARY, but this gap is worth checking.")

    # Transit-entrance anchor (optional): a single marker circle anywhere
    # inside `entrance_layer`, converted through the same column-calibrated
    # scale/origin as columns_ft. A plain Rhino POINT object was tried
    # first and confirmed NOT to survive this SVG export at all (no fill/
    # stroke to emit for a point with no geometry) -- a small circle is the
    # working convention, same as columns. Cross-validated 2026-07-08
    # against a live Rhino MCP query of the real connector geometry: the
    # two independent measurement paths agreed to within 2ft on a 600+ft
    # site (see PIPELINE_STATUS_AND_NEXT_STEPS.md). None if the layer is
    # absent or empty -- not every site export will have this marker, and
    # callers should treat that as "not provided," not an error.
    entrance_anchor_ft = None
    entrance_group = _find_group(root, entrance_layer)
    if entrance_group is not None:
        entrance_circles = [(float(c.get("cx")), float(c.get("cy")))
                             for c in entrance_group.iter(_SVG_NS + "circle")]
        if entrance_circles:
            if len(entrance_circles) > 1:
                print(f"[grid][WARN] {len(entrance_circles)} circles found in "
                      f"{entrance_layer!r}, expected exactly one entrance-anchor "
                      f"marker -- using the first.")
            ex, ey = entrance_circles[0]
            entrance_anchor_ft = ((ex - min_x) * scale_ft_per_pt, (max_y - ey) * scale_ft_per_pt)

    columns_ft = [((cx - min_x) * scale_ft_per_pt, (max_y - cy) * scale_ft_per_pt) for cx, cy in columns_pt]

    # Gaps in the regular column grid are where non-column structure (e.g.
    # spiral parking ramps) sits -- treat them as excavation-exclusion points
    # alongside real columns.
    tol = spacing_ft * 0.3
    gaps_ft = []
    for cx_pt in cx_lines:
        for cy_pt in cy_lines:
            gx_ft = (cx_pt - min_x) * scale_ft_per_pt
            gy_ft = (max_y - cy_pt) * scale_ft_per_pt
            if not any(math.hypot(gx_ft - fx, gy_ft - fy) < tol for fx, fy in columns_ft):
                gaps_ft.append((gx_ft, gy_ft))

    return {
        "columns_ft": columns_ft,
        "gaps_ft": gaps_ft,
        "site_width_ft": site_width_ft,
        "site_height_ft": site_height_ft,
        "entrance_anchor_ft": entrance_anchor_ft,
    }


def load_garage_depth_from_svg(svg_paths, spacing_ft, column_layer=DEFAULT_COLUMN_LAYER):
    """
    Derive real structural column height (surface/roof-slab level down to
    the lowest level) from one or more Rhino elevation SVG exports. Each
    column is drawn as a single vertical line segment with a uniform
    top/bottom y -- i.e. a single level. The same on-center column spacing
    used for the plan view calibrates each elevation's independent
    pt-to-ft scale, so depths derived from multiple elevations can
    cross-validate each other.
    """
    depths_ft = []
    for svg_path in svg_paths:
        root = ET.parse(svg_path).getroot()
        cols_group = _find_group(root, column_layer)
        segs = [re.match(r'M([-\d.]+),([-\d.]+) L([-\d.]+),([-\d.]+)', d).groups()
                for d in _all_descendant_ds(cols_group, "path")
                if re.match(r'M([-\d.]+),([-\d.]+) L([-\d.]+),([-\d.]+)', d)]
        verticals = [(float(x1), float(y1), float(y2)) for x1, y1, x2, y2 in segs if abs(float(x1) - float(x2)) < 0.01]
        if not verticals:
            continue
        height_pt = statistics.median([abs(y2 - y1) for _, y1, y2 in verticals])
        x_lines = _cluster([v[0] for v in verticals])
        dx_pt = statistics.median([x_lines[i + 1] - x_lines[i] for i in range(len(x_lines) - 1)])
        depths_ft.append(height_pt * (spacing_ft / dx_pt))

    if not depths_ft:
        raise ValueError("no column elevation segments found in any elevation SVG")

    depth_ft = statistics.mean(depths_ft)
    spread = max(depths_ft) - min(depths_ft)
    if spread > 1.0:
        print(f"[WARN] Elevation SVGs disagree on depth by {spread:.2f} ft -- using mean {depth_ft:.2f} ft.")
    else:
        print(f"[BRIDGE] Depth cross-validated across {len(depths_ft)} elevation(s): "
              f"{depth_ft:.2f} ft (spread {spread:.3f} ft)")
    return depth_ft
