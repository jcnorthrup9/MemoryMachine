"""
diagram_tool/app.py
--------------------
Standalone 2D diagram-authoring tool, forked 2026-07-14 from the root
app.py's Digital Palimpsest routes (GET /, /api/available-sites,
/api/diagram-data/{site}, /api/guidelines, /api/export-diagram). Runs as
its own process on its own port -- deliberately NOT folded into the root
app.py/uvicorn process, so this tool's lifecycle is fully decoupled from
Pershing Metabolizer's (today's session hit repeated port/stale-process
issues on that shared process; this tool has no reason to share the risk).

Scope: 2D zone-layer placement + solid-fill SVG export only. No 3D, no
AI-hallucinate/ComfyUI/Blender generation, no /api/available-sites (the
site picker in index.html is a fixed 4-option <select>, never actually
wired to that endpoint in the live app either).
"""
import os
import sys

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import uvicorn

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(BASE_DIR)

# Real Rhino-exported site/precedent SVGs. Switched 2026-07-14 from the old
# data/ParkSVG/ (which had no real zone fills -- see ingest_diagram_svg.py's
# module docstring) to this new location once the user re-exported all 5
# sites with real solid fills and the fuller MAJOR_ATTRACTORS/
# MINOR_ATTRACTORS/AMPHITHEATRE/BUILDINGS/HARDSCAPE/UNIQUE_ELEMENTS/
# INFRASTRUCTURE_CONNECTIONS layer set. This is now the one canonical
# source -- data/ParkSVG/ is no longer read by this tool.
SVG_DIR = os.path.join(REPO_ROOT, "data", "PershingMetabolizer", "parkSVG", "PrecedentSVG")

# New, dedicated output folder for this tool's exports -- distinct from
# archive/diagrams/generated (the old JPG-classification pipeline) and
# archive/diagrams/remixed_svgs (the unrelated Precedent Remixer feature).
EXPORT_DIR = os.path.join(REPO_ROOT, "archive", "diagrams", "site_svgs")

sys.path.insert(0, REPO_ROOT)
from logic.urban_engine import guideline_manager  # noqa: E402

app = FastAPI(title="Memory Machine // Diagram Tool")

app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")


@app.get("/", response_class=HTMLResponse)
async def read_root():
    return FileResponse(os.path.join(BASE_DIR, "index.html"))


@app.get("/api/diagram-data/{site}")
async def get_diagram(site: str):
    target_path = None
    if os.path.exists(SVG_DIR):
        for file in os.listdir(SVG_DIR):
            if file.lower().replace("_", "").replace(" ", "") == f"{site}.svg".lower():
                target_path = os.path.join(SVG_DIR, file)
                break

    if not target_path:
        return JSONResponse(status_code=404, content={"error": f"SVG file missing: {site}"})

    with open(target_path, encoding="utf-8") as f:
        return {"site": site, "svg": f.read()}


@app.get("/api/guidelines")
async def get_guidelines():
    """Exposes urban_design_guidelines.md to the frontend for the Zonal HUD --
    same shared parser the root app uses, so both tools' HUD targets always
    agree."""
    try:
        data = guideline_manager.parse()
        return {"status": "success", "data": data}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


class ExportPayload(BaseModel):
    filename: str
    data: str


@app.post("/api/export-diagram")
async def export_diagram(payload: ExportPayload):
    """SVG only -- see main.js's handleExport() docstring for why JPG
    rasterization was dropped entirely in this fork."""
    os.makedirs(EXPORT_DIR, exist_ok=True)
    filepath = os.path.join(EXPORT_DIR, payload.filename)
    try:
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(payload.data)
        return {"status": "success", "path": filepath}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


if __name__ == "__main__":
    # Moved 8003 -> 8006 (2026-07-14): the SAME Windows ghost-listener
    # corruption chased repeatedly elsewhere this session (Stop-Process
    # -Force leaving a stale "LISTENING" entry for a PID that no longer
    # exists, confirmed via Get-Process/Get-CimInstance finding nothing)
    # hit this port too. Moving to an unused port is the proven fix.
    uvicorn.run(app, host="127.0.0.1", port=8006)
