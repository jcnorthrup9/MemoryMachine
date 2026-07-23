"""
Rotatable "site grid" -- a 2D spatial organizer for the Digital Palimpsest
diagram (root app.py, port 8000), distinct from terracing_engine.py's
build_bay_grid(): that grid is axis-aligned with a fixed 27ft structural
bay size, built for the 3D column/framing pipeline. This one has a
caller-adjustable cell size AND rotation angle, built for live visual
exploration on the 2D canvas -- see logic/pershing_api.py's
_bay_grid_from_engine() for the pattern this loosely follows (site-anchored
in REAL_GEOMETRY's real feet, corner-origin), generalized with rotation.

Each cell's center is expressed both in real feet (corner-origin, matching
build_bay_grid()'s x_ft/z_ft convention) and in normalized site-fraction
space (x_frac/y_frac, 0.0 at site center, matching
ingest_diagram_svg.LOCATION_OFFSET_FRAC's convention) so a cell can be used
directly as a placement anchor by the same code that already resolves
LOCATION_OFFSET_FRAC strings, without inventing a third coordinate system.

2026-07-22: single-grid foundation only. Overlapping a second rotated grid
to detect "double-programmed" zones (the canyon-cut / light-well idea) is a
deliberately deferred follow-up -- not implemented here.
"""
import math


def build_site_grid(width_ft, length_ft, cell_size_ft, rotation_deg=0.0):
    """
    Returns a dict: {cell_size_ft, rotation_deg, width_ft, length_ft, cells},
    where each cell in `cells` is
    {gx, gy, x_ft, z_ft, x_frac, y_frac, corners_ft, corners_frac}.

    Cells are generated over a square grid, centered on and rotated about
    the site's own center, oversized enough to cover the site at any
    rotation angle, then filtered down to only cells whose (post-rotation)
    center actually falls inside the site's [0,width_ft] x [0,length_ft]
    rectangle -- so the returned grid never includes cells whose center
    lands off-site, though corners of edge cells may extend slightly past
    the boundary (expected for a rotated overlay; the frontend clips the
    rendered lines to the BOUNDARY path itself).

    gx/gy are stable per-cell grid indices in the grid's own (rotated) axes,
    not a positional index into the filtered `cells` list -- useful for a
    caller that wants to identify "the cell next to this one" later, e.g.
    for the deferred overlap-detection follow-up.
    """
    if cell_size_ft <= 0:
        raise ValueError("cell_size_ft must be > 0")
    if width_ft <= 0 or length_ft <= 0:
        raise ValueError("width_ft and length_ft must be > 0")

    cx_ft, cy_ft = width_ft / 2.0, length_ft / 2.0
    rot = math.radians(rotation_deg or 0.0)
    cos_r, sin_r = math.cos(rot), math.sin(rot)

    def to_world(local_x, local_y):
        # Rotate a point from the grid's own local axes into site (world) space
        wx = cx_ft + local_x * cos_r - local_y * sin_r
        wy = cy_ft + local_x * sin_r + local_y * cos_r
        return wx, wy

    # Oversized square (in the grid's local axes) guaranteed to cover the
    # site rectangle regardless of rotation angle.
    diag = math.hypot(width_ft, length_ft)
    half_span = diag / 2.0 + cell_size_ft
    n_steps = max(1, math.ceil((2 * half_span) / cell_size_ft))
    half = cell_size_ft / 2.0

    cells = []
    for i in range(n_steps):
        local_cx = -half_span + (i + 0.5) * cell_size_ft
        for j in range(n_steps):
            local_cy = -half_span + (j + 0.5) * cell_size_ft

            wx, wy = to_world(local_cx, local_cy)
            if not (0.0 <= wx <= width_ft and 0.0 <= wy <= length_ft):
                continue

            corners_ft = [
                to_world(local_cx - half, local_cy - half),
                to_world(local_cx + half, local_cy - half),
                to_world(local_cx + half, local_cy + half),
                to_world(local_cx - half, local_cy + half),
            ]

            cells.append({
                "gx": i, "gy": j,
                "x_ft": wx, "z_ft": wy,
                "x_frac": (wx - cx_ft) / width_ft,
                "y_frac": (wy - cy_ft) / length_ft,
                "corners_ft": corners_ft,
                "corners_frac": [
                    ((cfx - cx_ft) / width_ft, (cfy - cy_ft) / length_ft)
                    for cfx, cfy in corners_ft
                ],
            })

    return {
        "cell_size_ft": cell_size_ft,
        "rotation_deg": rotation_deg,
        "width_ft": width_ft,
        "length_ft": length_ft,
        "cells": cells,
    }
