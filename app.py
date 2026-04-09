from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import uvicorn, os, json, base64
import xml.etree.ElementTree as ET
import sys
import asyncio

# --- MODULAR LOGIC IMPORTS ---
from logic.geometry_engine import build_geometries
from logic.urban_engine import GuidelineManager, remix_layers, guideline_manager
from logic.ai_synthesizer import (
    generate_spatial_seed, generate_mermaid_diagram
)

# --- CONFIGURATION ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SVG_DIR = os.path.join(BASE_DIR, 'data', 'ParkSVG')

app = FastAPI(title="Memory Machine API")

# --- AI & DB INITIALIZATION ---
AI_ENABLED = False
ai_client = None

try:
    from dotenv import load_dotenv
    from google import genai
    import chromadb
    load_dotenv(os.path.join(BASE_DIR, '.env'))
    
    # FIX: Your logs show both GOOGLE_API_KEY and GEMINI_API_KEY are set.
    # Standard GOOGLE_API_KEYs often lack the GenAI API permission.
    # We explicitly prioritize the AI Studio Key (GEMINI_API_KEY).
    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    
    if api_key:
        # Initialize client for the google-genai SDK
        ai_client = genai.Client(api_key=api_key)
        
        # Init ChromaDB
        db_path = os.path.join(BASE_DIR, 'db')
        chroma_client = chromadb.PersistentClient(path=db_path)
        collection = chroma_client.get_or_create_collection(name="memory_machine_corpus")
        
        AI_ENABLED = True
        print(f"✅ AI Services Online (Using Key: {'GEMINI' if os.environ.get('GEMINI_API_KEY') else 'GOOGLE'})")
    else:
        print("⚠️ No API Key found in .env")
except Exception as e:
    print(f"⚠️ AI Services Offline: {e}")

# --- STATIC MOUNTS ---
app.mount("/static", StaticFiles(directory="static"), name="static")
app.mount("/archive", StaticFiles(directory="html"), name="archive")

models_dir = os.path.join(BASE_DIR, 'models')
os.makedirs(models_dir, exist_ok=True)
app.mount("/models", StaticFiles(directory="models"), name="models")

# --- DATA MODELS ---
class MemoryPrompt(BaseModel): prompt: str

class ExportPayload(BaseModel):
    filename: str
    data: str
    type: str

class CapturePayload(BaseModel):
    prompt: str
    spatial_seed: list
    geometries: list
    narrative: str
    isLightMode: bool
    activeTab: str

# --- ROUTES ---

@app.get("/", response_class=HTMLResponse)
async def read_root():
    return FileResponse(os.path.join(BASE_DIR, "index.html"))

@app.get("/api/available-sites")
async def get_available_sites():
    """Dynamically scans the ParkSVG folder and extracts site bounds."""
    sites = []
    if os.path.exists(SVG_DIR):
        for file in os.listdir(SVG_DIR):
            if file.lower().endswith(".svg"):
                # Normalize names to PascalCase to ensure frontend alignment and prevent 404s
                base_name = file[:-4].replace("_", " ").title()
                site_id = base_name.replace(" ", "")
                site_name = base_name
                
                width, height = 1224, 792 # Default fallback
                try:
                    tree = ET.parse(os.path.join(SVG_DIR, file))
                    root = tree.getroot()
                    if "viewBox" in root.attrib:
                        _, _, w, h = root.attrib["viewBox"].split()
                        width, height = float(w), float(h)
                    elif "width" in root.attrib and "height" in root.attrib:
                        width = float(root.attrib["width"].replace("pt","").replace("px",""))
                        height = float(root.attrib["height"].replace("pt","").replace("px",""))
                except Exception as e:
                    print(f"⚠️ Could not parse bounds for {file}: {e}")
                
                sites.append({
                    "id": site_id,
                    "name": site_name,
                    "bounds": {"width": width, "height": height}
                })
    return {"sites": sites}

@app.get("/api/diagram-data/{site}")
async def get_diagram(site: str):
    target_path = None
    if os.path.exists(SVG_DIR):
        for file in os.listdir(SVG_DIR):
            if file.lower().replace("_", "").replace(" ", "") == f"{site}.svg".lower():
                target_path = os.path.join(SVG_DIR, file)
                break
                
    if not target_path:
        print(f"\n❌ [ERROR] SVG NOT FOUND: '{site}'")
        return JSONResponse(status_code=404, content={"error": f"SVG file missing: {site}"})
        
    with open(target_path, encoding="utf-8") as f:
        return {"site": site, "svg": f.read()}

@app.get("/api/guidelines")
async def get_guidelines():
    """Exposes the parsed urban_design_guidelines.md to the frontend for the Zonal HUD."""
    try:
        data = guideline_manager.parse()
        return {"status": "success", "data": data}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

@app.post("/api/export-diagram")
async def export_diagram(payload: ExportPayload):
    """Receives exported canvas/SVG data and saves it locally to the archive."""
    export_dir = os.path.join(BASE_DIR, 'archive', 'diagrams', 'generated')
        
    os.makedirs(export_dir, exist_ok=True)
    
    filepath = os.path.join(export_dir, payload.filename)
    try:
        if payload.type == "svg":
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(payload.data)
        elif payload.type == "jpg":
            header, encoded = payload.data.split(",", 1)
            with open(filepath, "wb") as f:
                f.write(base64.b64decode(encoded))
        return {"status": "success", "path": filepath}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

@app.post("/api/capture-dashboard")
def capture_dashboard(payload: CapturePayload):
    """Uses headless Playwright to take a pixel-perfect snapshot of the UI."""
    try:
        from playwright.sync_api import sync_playwright
        import time
        export_dir = os.path.join(BASE_DIR, 'archive', 'workflowScreenshots', 'appTests')
        os.makedirs(export_dir, exist_ok=True)
        filepath = os.path.join(export_dir, f"dashboard_capture_{int(time.time()*1000)}.jpg")
        
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1920, "height": 1080})
            page.goto("http://127.0.0.1:8000/", wait_until="networkidle")
            
            if payload.isLightMode:
                page.evaluate("document.body.classList.add('light-mode'); document.body.classList.remove('dark-mode');")
                
            state_script = f"""
                async () => {{
                    document.getElementById('prompt-input').value = {json.dumps(payload.prompt)};
                    window.MemoryState.stack = {json.dumps(payload.spatial_seed)};
                    window.MemoryState.lastGeneration = {{
                        narrative: {json.dumps(payload.narrative)},
                        geometries: {json.dumps(payload.geometries)},
                        diagram: ''
                    }};
                    const sites = [...new Set(window.MemoryState.stack.map(s => s.site || 'PershingSquare'))];
                    if (!sites.includes('PershingSquare')) sites.push('PershingSquare');
                    for (const site of sites) {{
                        if (!window.MemoryState.svgCache[site]) {{
                            const res = await fetch('/api/diagram-data/' + site);
                            const data = await res.json();
                            window.MemoryState.svgCache[site] = data.svg;
                        }}
                    }}
                    window.MemoryState.baseCleared = true;
                    if (window.renderRemixSVG) window.renderRemixSVG();
                    if (typeof refreshStackUI !== 'undefined') refreshStackUI();
                    
                    if ({json.dumps(payload.activeTab)} === '3d') {{
                        if (typeof switchToTab !== 'undefined') switchToTab('3d');
                        if (typeof initThreeScene !== 'undefined') initThreeScene();
                        if (typeof renderGeometries !== 'undefined') renderGeometries(window.MemoryState.lastGeneration.geometries);
                    }}
                    
                    const out = document.getElementById('narrative-output');
                    if (out) {{
                        out.innerHTML = '';
                        const p1 = document.createElement('pre');
                        p1.textContent = '> ' + {json.dumps(payload.prompt)};
                        const p2 = document.createElement('pre');
                        p2.className = 'success';
                        p2.textContent = {json.dumps(payload.narrative)};
                        out.appendChild(p1);
                        out.appendChild(p2);
                    }}
                }}
            """
            page.evaluate(f"({state_script})()")
            page.wait_for_timeout(1500) # Give 1.5 seconds for ThreeJS/SVG to render
            
            page.screenshot(path=filepath, type="jpeg", quality=95)
            browser.close()
            
        return {"status": "success", "path": filepath}
    except Exception as e:
        print(f"Capture error: {e}")
        return JSONResponse(status_code=500, content={"error": str(e)})

@app.post("/api/generate")
async def generate_memory_node(payload: MemoryPrompt):
    prompt = payload.prompt
    
    # 1. Retrieval (ChromaDB)
    matches = []
    try:
        if AI_ENABLED:
            results = collection.query(query_texts=[prompt], n_results=5)
            matches = [{"metadata": m, "document": d} for m, d in zip(results['metadatas'][0], results['documents'][0])]
    except: pass
    
    # 2. AI Synthesis (Now routing to Local Ollama API)
    spatial_seed_raw, ai_narrative = generate_spatial_seed(prompt, matches)
    
    # 3. Remix
    spatial_seed = remix_layers(spatial_seed_raw)
    
    # 3.1 Geometric Truth: Base Seed
    base_seed = {
        "site": "PershingSquare",
        "layerId": "BOUNDARY",
        "label": "Site Boundary",
        "transform": {"x": 0, "y": 0, "scale": 1.0, "rot": 0},
        "visible": True,
        "opacity": 1.0,
        "target_width": 1224,
        "target_height": 792,
        "primitive": "box"
    }
    spatial_seed.insert(0, base_seed)

    # 3.5. 3D Geometry Generation
    geometries = []
    for item in spatial_seed:
        width = item.get("target_width", 20)
        depth = item.get("target_height", 20)
        x = item.get("transform", {}).get("x", 0)
        z = item.get("transform", {}).get("y", 0) # Map 2D Y to 3D Z
        
        layer_id = item.get("layerId", "")
        geo_type = "box"
        if "WATER" in layer_id: geo_type = "water_garden"
        elif "SHADE" in layer_id: geo_type = "shade_canopy"
        elif "GREEN_SPACE" in layer_id: geo_type = "landscape_mound"
        elif "MAJOR_ATTRACTOR" in layer_id: geo_type = "memory_tower"
        elif "MINOR_ATTRACTOR" in layer_id: geo_type = "supertree"
        elif "UNIQUE" in layer_id: geo_type = "kinetic_mast"
        elif "AMPHITHEATER" in layer_id: geo_type = "amphitheater"
        
        params = {
            "geometry_type": geo_type,
            "footprint_m": {"width": width, "depth": depth},
            "height_m": 15.0,
            "position": {"x": x, "y": 0, "z": z},
            "materials": ["concrete", "vegetation"] if "GREEN" in layer_id else ["weathered_steel", "glass"]
        }
        geometries.extend(build_geometries(params))

    # 4. Metadata
    diagram = generate_mermaid_diagram(prompt, matches, {"geometry_type": "Hybrid Assembly", "height_m": 15})

    return {
        "status": "success",
        "narrative": ai_narrative,
        "diagram": diagram,
        "spatial_seed": spatial_seed,
        "geometries": geometries
    }

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)