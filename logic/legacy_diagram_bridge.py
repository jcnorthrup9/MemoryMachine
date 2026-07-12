"""
logic/legacy_diagram_bridge.py
-------------------------------
HTTP-reachable wrapper around ingest_legacy_diagram.py's already-built,
already-calibrated rectify+color-segment pipeline -- the "Diagram Input"
mode (2026-07-11): a genuinely separate design-input mechanism from
PaintOverlay.jsx's freehand painting, not routed through it. Lists recent
exports from the legacy diagram tool (archive/diagrams/generated/) and
converts one on request for the frontend to preview before committing.

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

import ingest_legacy_diagram
from logic.pershing_api import NX, NZ, VOXEL_FT

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIAGRAM_DIR = os.path.join(BASE_DIR, "archive", "diagrams", "generated")


class PreviewLegacyDiagramRequest(BaseModel):
    filename: str


def list_recent_diagrams(limit=20):
    """Recent memory_machine_jpg-color_*.jpg exports from the legacy
    diagram tool, newest first by mtime -- freshly-generated diagrams
    naturally sort to the top without needing a session-start marker."""
    pattern = os.path.join(DIAGRAM_DIR, "memory_machine_jpg-color_*.jpg")
    paths = glob.glob(pattern)
    paths.sort(key=os.path.getmtime, reverse=True)
    return [
        {"filename": os.path.basename(p), "mtime": os.path.getmtime(p)}
        for p in paths[:limit]
    ]


def preview_import(filename):
    """
    Convert one archived diagram into the live pipeline's 6-key paint-state
    grid shape, for the frontend to preview before committing via the
    existing bake() endpoint. `filename` is resolved via os.path.basename()
    only -- same path-traversal guard save_uploaded_sketch() already uses in
    pershing_api.py, never trust a client-supplied filename as a path.

    Passes pershing_api's own NX/NZ/VOXEL_FT explicitly (rather than relying
    on ingest_legacy_diagram.py's own defaults, which happen to match today
    but aren't guaranteed to) so the returned grid shape is guaranteed
    compatible with BakeGrids regardless of either module's own defaults
    drifting independently in the future.

    Read-only -- does not touch PAINT_STATE_PATH or any live mask global.
    """
    safe_name = os.path.basename(filename)
    if not safe_name:
        raise ValueError("empty filename")
    path = os.path.join(DIAGRAM_DIR, safe_name)
    if not os.path.exists(path):
        raise FileNotFoundError(f"no such diagram: {safe_name}")

    paint_state = ingest_legacy_diagram.convert_one(path, nx=NX, nz=NZ, voxel_ft=VOXEL_FT)

    counts = {
        key: sum(row.count(True) for row in paint_state[key])
        for key in ("hardscape", "water", "shade", "greenscape", "amenity_resting")
    }
    counts["canyon"] = sum(1 for row in paint_state["canyon"] for v in row if v > 0.01)

    return {"filename": safe_name, "grids": paint_state, "counts": counts}
