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
  - The slab/site outline lives in a <g id="{slab_layer}"> group -- its
    real footprint is taken from the combined bounding box of every <path>
    found anywhere inside that group (including nested sublayers, e.g.
    STRUC__Slabs::L1/L2/L3), not assumed to be one single outline path.
    Fixed 2026-07-05: an earlier version took only the *first* <path> found,
    which silently measured the wrong (small, unrelated) shape once the real
    Rhino model started drawing STRUC__Slabs as several separate paths/
    sublayers instead of one outline curve -- confirmed via a live Rhino MCP
    check that the real column grid spacing in this SVG is isotropic
    (dx_pt/dy_pt ratio ~0.9998), so the bug was this parsing assumption, not
    a non-uniform page-fit scale.
  - The SVG carries no reliable real-world scale on its own -- callers must
    supply one known on-center spacing (spacing_ft) to calibrate pt-to-ft.
    A single scale factor is valid as long as the export isn't stretched to
    a different aspect ratio than the model (confirmed true for the exports
    checked so far) -- it does not need to be an unscaled/1:1 export; a
    fixed page size (e.g. matching the same sheet size used for hand
    sketches) works fine.
"""
import re
import math
import statistics
import xml.etree.ElementTree as ET

DEFAULT_COLUMN_LAYER = "STRUC__Columns"
DEFAULT_SLAB_LAYER = "STRUC__Slabs"

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
                                   cluster_tol=2.0):
    """
    Parse a structural column grid and slab outline out of a Rhino plan-view
    SVG export (layers `column_layer` / `slab_layer`).

    The SVG only carries abstract drawing units ("pt"), so the real-world
    scale is derived from a known on-center column spacing (spacing_ft) --
    this is the one site-specific fact the caller must supply; everything
    else here is generic parsing/derivation.

    Origin (0,0) is anchored to the bottom-left corner of the slab bounding
    box as drawn -- true compass orientation in the original Rhino file is
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

    # Site footprint = combined bounding box of every <path> anywhere inside
    # the slab group (including nested sublayers like L1/L2/L3) -- NOT just
    # the first path found, which may be a small unrelated decorative mark
    # rather than a single full-site outline curve (see module docstring).
    slab_group = _find_group(root, slab_layer)
    slab_paths = _all_descendant_ds(slab_group, "path")
    corners = [(float(a), float(b)) for d in slab_paths for a, b in re.findall(r'([-\d.]+),([-\d.]+)', d)]
    min_x = min(c[0] for c in corners)
    max_x = max(c[0] for c in corners)
    min_y = min(c[1] for c in corners)
    max_y = max(c[1] for c in corners)

    cx_lines = _cluster([p[0] for p in columns_pt], tol=cluster_tol)
    cy_lines = _cluster([p[1] for p in columns_pt], tol=cluster_tol)
    dx = statistics.median([cx_lines[i + 1] - cx_lines[i] for i in range(len(cx_lines) - 1)])
    dy = statistics.median([cy_lines[i + 1] - cy_lines[i] for i in range(len(cy_lines) - 1)])
    scale_ft_per_pt = spacing_ft / ((dx + dy) / 2.0)

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
        "site_width_ft": (max_x - min_x) * scale_ft_per_pt,
        "site_height_ft": (max_y - min_y) * scale_ft_per_pt,
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
