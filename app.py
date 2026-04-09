from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import uvicorn, subprocess, sys, os, json, re, math
from datetime import datetime, timezone
import time

# --- MODULAR LOGIC IMPORTS ---
# These pull the "Heavy Lifting" from your specialized sub-files
from logic.geometry_engine import build_geometries
from logic.urban_engine import GuidelineManager, remix_layers, apply_zonal_grid
from logic.ai_synthesizer import (
    generate_spatial_seed, generate_mermaid_diagram, 
    load_spatial_blueprints, format_blueprints_for_prompt, 
    generate_comfyui_mesh, generate_blender_mesh
)

# --- CONFIGURATION ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_DIR = os.path.join(BASE_DIR, 'db')
SVG_DIR = os.path.join(BASE_DIR, 'data', 'ParkSVG')
os.makedirs(os.path.join(BASE_DIR, "models"), exist_ok=True)

app = FastAPI(title="Memory Machine API")

# --- AI & DB INITIALIZATION ---
try:
    from dotenv import load_dotenv
    from google import genai
    import chromadb
    load_dotenv(os.path.join(BASE_DIR, '.env'))
    api_key = os.environ.get("GEMINI_API_KEY")
    ai_client = genai.Client(api_key=api_key) if api_key else None
    chroma_client = chromadb.PersistentClient(path=DB_DIR)
    collection = chroma_client.get_or_create_collection(name="memory_machine_corpus")
    AI_ENABLED = True
    print("✅ AI Services Online")
except Exception as e:
    print(f"⚠️ AI Services Offline: {e}")
    AI_ENABLED = False

# --- STATIC MOUNTS ---
app.mount("/static", StaticFiles(directory="static"), name="static")
app.mount("/models", StaticFiles(directory="models"), name="models")
app.mount("/archive", StaticFiles(directory="html"), name="archive")

# --- DATA MODELS ---
class MemoryPrompt(BaseModel): prompt: str
class BakeRequest(BaseModel):
    name: str = "Unnamed Intervention"
    geometries: list
    svg_scale: float = 0.04
    stack_footprints: list = []

# --- PASSIVE UI ROUTES (Required to "Wake Up" the App) ---

@app.get("/", response_class=HTMLResponse)
async def read_root():
    """Serves the main landing page."""
    return FileResponse(os.path.join(BASE_DIR, "templates", "index.html"))

@app.get("/diagrams", response_class=HTMLResponse)
async def viewer_2d():
    """Serves the 2D interactive SVG viewer dashboard."""
    return FileResponse(os.path.join(BASE_DIR, "templates", "viewer_2d.html"))

@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    favicon_path = os.path.join(BASE_DIR, "static", "favicon.ico")
    if os.path.exists(favicon_path):
        return FileResponse(favicon_path)
    return JSONResponse(status_code=204, content=None)

@app.get("/api/site-context")
async def get_site_context():
    """Loads the base Rhino/DTLA context for the 3D viewer."""
    context_path = os.path.join(BASE_DIR, 'data', 'pershing_site_context.json')
    if os.path.exists(context_path):
        with open(context_path) as f:
            return json.load(f)
    return {"geometries": []}

@app.get("/api/guidelines")
async def get_guidelines():
    """Returns the parsed urban design guidelines for the HUD."""
    gm = GuidelineManager(os.path.join(BASE_DIR, "urban_design_guidelines.md"))
    data = gm.parse()
    return {"guidelines": data["guidelines"], "metadata": data["metadata"], "primitives": data["primitives"]}

@app.get("/api/diagram-data/{site}")
async def get_diagram(site: str):
    """Returns SVG content for the 2D remixer."""
    svg_path = os.path.join(SVG_DIR, f"{site}.svg")
    if not os.path.exists(svg_path):
        return JSONResponse(status_code=404, content={"error": "SVG not found"})
    with open(svg_path, encoding="utf-8") as f:
        return {"site": site, "svg": f.read()}

# --- ACTIVE INTERVENTION ROUTES ---

@app.post("/api/generate")
async def generate_memory_node(payload: MemoryPrompt):
    """Core synthesis route - delegates to logic/ai_synthesizer.py."""
    if not AI_ENABLED:
        return {"status": "error", "narrative": "AI Core Offline."}
    
    prompt = payload.prompt
    results = collection.query(query_texts=[prompt], n_results=5)
    matches = [{"metadata": m, "document": d} for m, d in zip(results['metadatas'][0], results['documents'][0])]
    
    spatial_seed_raw = generate_spatial_seed(prompt, ai_client)
    spatial_seed = remix_layers(spatial_seed_raw)
    
    spatial_params = {"geometry_type": "landscape_mound", "height_m": 10}
    geometries = build_geometries(spatial_params)
    diagram = generate_mermaid_diagram(prompt, matches, spatial_params)

    return {
        "status": "success",
        "name": "Draft Intervention",
        "narrative": "Modular synthesis complete.",
        "geometries": geometries,
        "diagram": diagram,
        "spatial_seed": spatial_seed
    }

@app.post("/api/bake")
async def bake_to_rhino(payload: BakeRequest):
    """Triggers the Rhino Integration Script."""
    intervention_path = os.path.join(BASE_DIR, 'data', 'current_intervention.json')
    with open(intervention_path, 'w') as f:
        json.dump(payload.dict(), f, indent=2)
    subprocess.Popen([sys.executable, os.path.join(BASE_DIR, 'logic', 'bake_to_rhino.py')])
    return {"status": "success", "message": "Bake initiated."}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)