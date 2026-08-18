"""
Composites a spatial_seed (remix_layers()'s output -- a list of
{site, layerId, transform, ...} picks) into ONE flat PNG image: the "source
diagram" a design iteration started from. There was no prior function that
rendered a spatial_seed as a picture at all (confirmed by direct code
reading) -- everywhere else it either stays an abstract JSON list, gets
rasterized into boolean paint-mask grids (ingest_diagram_svg.
rasterize_precedent_layers, no visible shape/color info survives that), or
is only ever composited live in the browser DOM (frontend/src/
spatializerEngine.js's render(), no server-side equivalent).

Reuses ingest_diagram_svg.py's already-proven per-layer fit/rotate/
translate math (the exact same transform rasterize_precedent_layers()
applies before rasterizing) rather than porting spatializerEngine.js's
DOM-based <g transform="..."> cloning -- operates on real polygon vertex
arrays (_group_polygons), which is both simpler and gets PNG output
directly via matplotlib (already a project dependency, see
vector_export.py's own export_png) with no SVG rasterizer (cairosvg etc,
confirmed NOT installed) needed at all.
"""
import numpy as np

import ingest_diagram_svg

# Mirrors frontend/src/spatializerEngine.js's getLayerColor() (lines
# 449-453) for visual consistency with the live SPATIALIZE canvas.
_LAYER_COLORS = [
    ("SHADE", "#FFEB3B"),
    ("GREEN", "#4CAF50"),
    ("WATER", "#03A9F4"),
    ("ATTRACTOR", "#FF9800"),
    ("UNIQUE", "#FF9800"),
]
_DEFAULT_LAYER_COLOR = "#9E9E9E"


def _layer_color(layer_id):
    upper = (layer_id or "").upper()
    for substr, color in _LAYER_COLORS:
        if substr in upper:
            return color
    return _DEFAULT_LAYER_COLOR


def compose_spatial_seed_png(composed_layers, out_path, dpi=150):
    """composed_layers: remix_layers()'s output (already-resolved site/
    layerId/transform picks, NOT the raw seed_items random_spatial_seed()
    produces). Writes a flat PNG to out_path. Silently skips any layer that
    fails to resolve (missing SVG/layer id/empty polygons) -- same
    tolerance rasterize_precedent_layers() already shows, an unresolvable
    pick shouldn't blank the whole diagram."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Rectangle

    pershing_root = ingest_diagram_svg._load_precedent_svg("PershingSquare")
    pcx, pcy, pw, ph = ingest_diagram_svg._boundary_bbox_center_and_size(pershing_root)

    fig, ax = plt.subplots(figsize=(8, 8))
    fig.patch.set_facecolor("#050505")
    ax.set_facecolor("#050505")
    ax.add_patch(Rectangle((pcx - pw / 2, pcy - ph / 2), pw, ph,
                            fill=False, edgecolor="#ffffff", linewidth=1.5))

    resolved_count = 0
    for item in composed_layers or []:
        layer_id = item.get("layerId", "")
        try:
            src_root = ingest_diagram_svg._load_precedent_svg(item["site"])
        except FileNotFoundError:
            continue
        layer_g = ingest_diagram_svg._find_layer_group(src_root, layer_id)
        if layer_g is None:
            continue
        src_polys_px = ingest_diagram_svg._group_polygons(layer_g)
        if not src_polys_px:
            continue

        scx, scy, sw, sh = ingest_diagram_svg._boundary_bbox_center_and_size(src_root)
        fit_scale = min(pw / (sw or 1.0), ph / (sh or 1.0))
        t = item.get("transform") or {}
        final_scale = fit_scale * (t.get("scale") or 1.0)
        rot = np.radians(t.get("rot") or 0.0)
        cos_r, sin_r = np.cos(rot), np.sin(rot)
        offset_x = pcx + (t.get("x_frac") or 0.0) * pw
        offset_y = pcy + (t.get("y_frac") or 0.0) * ph
        color = _layer_color(layer_id)

        for poly_px in src_polys_px:
            shifted = poly_px - np.array([scx, scy])
            rotated = np.stack([
                shifted[:, 0] * cos_r - shifted[:, 1] * sin_r,
                shifted[:, 0] * sin_r + shifted[:, 1] * cos_r,
            ], axis=1)
            placed = rotated * final_scale + np.array([offset_x, offset_y])
            ax.fill(placed[:, 0], placed[:, 1], color=color, alpha=0.85, linewidth=0)
        resolved_count += 1

    ax.set_xlim(pcx - pw * 0.6, pcx + pw * 0.6)
    ax.set_ylim(pcy - ph * 0.6, pcy + ph * 0.6)
    ax.invert_yaxis()  # SVG pixel space is Y-down; matches the source diagrams' own orientation
    ax.set_aspect("equal")
    ax.axis("off")
    fig.savefig(out_path, dpi=dpi, facecolor=fig.get_facecolor())
    plt.close(fig)
    return resolved_count
