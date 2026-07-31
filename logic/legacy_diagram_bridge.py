"""
logic/legacy_diagram_bridge.py
-------------------------------
HTTP-reachable wrapper around diagram export ingestion for the frontend's
"Diagram Input" mode (2026-07-11): a genuinely separate design-input
mechanism from PaintOverlay.jsx's freehand painting, not routed through it.
Lists recent exports and converts one on request for the frontend to
preview before committing.

Switched 2026-07-14 from ingest_legacy_diagram.py's pixel-color
classification of rasterized JPG exports (archive/diagrams/generated/) to
ingest_diagram_svg.py's direct SVG parsing of diagram_tool/'s exports
(archive/diagrams/site_svgs/) -- see ingest_diagram_svg.py's module
docstring for why. Function names/signatures here are unchanged on
purpose so DiagramInputPanel.jsx and api.js need no changes at all.

Kept as its own module rather than folded into logic/pershing_api.py,
matching the existing pattern of amenity_deficit.py/foot_traffic.py/
circulation_network.py as separate concern-scoped modules pershing_api.py
imports from.

Deliberately read-only: preview_import() never touches PAINT_STATE_PATH or
any live in-memory mask global. The frontend's actual "commit this diagram"
step reuses the EXISTING POST /api/pershing/bake endpoint (see
DiagramInputPanel.jsx) with the grids this module returns -- bake() doesn't
care about a grid's source, only its shape, so no parallel commit path is
needed here.
"""
import glob
import os

from pydantic import BaseModel

import ingest_diagram_svg
from logic.pershing_api import NX, NZ, VOXEL_FT

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIAGRAM_DIR = os.path.join(BASE_DIR, "archive", "diagrams", "site_svgs")


class PreviewLegacyDiagramRequest(BaseModel):
    filename: str


def list_recent_diagrams(limit=20):
    """Recent site_diagram_*.svg exports from diagram_tool/, newest first
    by mtime -- freshly-generated diagrams naturally sort to the top
    without needing a session-start marker."""
    pattern = os.path.join(DIAGRAM_DIR, "site_diagram_*.svg")
    paths = glob.glob(pattern)
    paths.sort(key=os.path.getmtime, reverse=True)
    return [
        {"filename": os.path.basename(p), "mtime": os.path.getmtime(p)}
        for p in paths[:limit]
    ]


def preview_import(filename):
    """
    Convert one archived SVG diagram into the live pipeline's 6-key
    paint-state grid shape, for the frontend to preview before committing
    via the existing bake() endpoint. `filename` is resolved via
    os.path.basename() only -- same path-traversal guard
    save_uploaded_sketch() already uses in pershing_api.py, never trust a
    client-supplied filename as a path.

    Passes pershing_api's own NX/NZ/VOXEL_FT explicitly (rather than relying
    on ingest_diagram_svg.py's own defaults, which happen to match today
    but aren't guaranteed to) so the returned grid shape is guaranteed
    compatible with BakeGrids regardless of either module's own defaults
    drifting independently in the future.

    Also returns `attractor_points` (2026-07-14): MAJOR_ATTRACTORS/
    MINOR_ATTRACTORS/AMPHITHEATRE marker positions in site-feet, extracted
    separately from the area grid (see ingest_diagram_svg.py's
    extract_attractor_points() -- these are discrete future-3D-asset
    placement points, not area masks, and aren't committed via bake() at
    all yet; no consumer of this response depends on the key existing, so
    adding it here doesn't break DiagramInputPanel.jsx).

    Read-only -- does not touch PAINT_STATE_PATH or any live mask global.
    """
    safe_name = os.path.basename(filename)
    if not safe_name:
        raise ValueError("empty filename")
    path = os.path.join(DIAGRAM_DIR, safe_name)
    if not os.path.exists(path):
        raise FileNotFoundError(f"no such diagram: {safe_name}")

    paint_state = ingest_diagram_svg.convert_svg_to_paint_state(path, nx=NX, nz=NZ, voxel_ft=VOXEL_FT)
    attractor_points = ingest_diagram_svg.extract_attractor_points(path)

    counts = {
        key: sum(row.count(True) for row in paint_state[key])
        for key in ("hardscape", "water", "trees", "greenscape", "amenity_resting")
    }
    counts["canyon"] = sum(1 for row in paint_state["canyon"] for v in row if v > 0.01)
    counts.update({f"{cat}_count": len(pts) for cat, pts in attractor_points.items()})

    return {
        "filename": safe_name,
        "grids": paint_state,
        "counts": counts,
        "attractor_points": attractor_points,
    }
