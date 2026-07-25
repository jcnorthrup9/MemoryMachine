from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import uvicorn, os, json, base64, time
import xml.etree.ElementTree as ET
import sys
import asyncio

# Windows' default console codepage (cp1252) can't encode the emoji used in
# a few startup log lines below, crashing the process before it can even
# report the real error. Force UTF-8 stdout so those prints (and any
# future ones) never take the whole app down over a log message.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# --- MODULAR LOGIC IMPORTS ---
from logic.geometry_engine import build_geometries
from logic.urban_engine import GuidelineManager, remix_layers, guideline_manager
from logic.ai_synthesizer import (
    generate_spatial_seed, generate_mermaid_diagram, apply_deficit_weighting
)
from logic.comfy_client import ping as comfy_ping, load_workflow, patch_workflow, queue_workflow, poll_for_output
from logic.pershing_api import (
    RebuildParams, BakeGrids, GrowNetworkRequest, GenerateCanopyRequest, GenerateDrawingsRequest,
    SaveDrawingRequest, JurorChatRequest, CritiqueRequest,
    get_config as pershing_get_config,
    rebuild as pershing_rebuild, grow_network as pershing_grow_network,
    carve_network_canyon as pershing_carve_network_canyon,
    generate_canopy as pershing_generate_canopy,
    generate_drawings as pershing_generate_drawings,
    save_drawing as pershing_save_drawing,
    juror_chat as pershing_juror_chat, critique as pershing_critique,
    get_sketch_info as pershing_get_sketch_info, save_uploaded_sketch as pershing_save_uploaded_sketch,
    bake as pershing_bake, SKETCH_DIR as PERSHING_SKETCH_DIR,
    get_bay_grid as pershing_get_bay_grid, get_program_zones as pershing_get_program_zones,
    ArchiveSaveRequest, save_build_to_archive as pershing_save_build_to_archive,
    list_archived_builds as pershing_list_archived_builds,
    get_archived_build as pershing_get_archived_build,
    delete_archived_build as pershing_delete_archived_build,
    _deficit_weighted_location_weights as pershing_get_deficit_weights,
    REAL_GEOMETRY,
    Preview2DGenerationRequest,
    list_2d_generations as pershing_list_2d_generations,
    preview_2d_generation as pershing_preview_2d_generation,
    SpatializePreviewRequest,
    spatialize_preview as pershing_spatialize_preview,
    get_deficit_weights as pershing_get_deficit_weights_public,
    get_deficit_hotspots as pershing_get_deficit_hotspots,
)
from logic.site_grid import build_site_grid
from logic import pershing_blender
from logic.legacy_diagram_bridge import (
    PreviewLegacyDiagramRequest, list_recent_diagrams as pershing_list_legacy_diagrams,
    preview_import as pershing_preview_legacy_diagram, DIAGRAM_DIR as LEGACY_DIAGRAM_DIR,
)

# --- CONFIGURATION ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SVG_DIR = os.path.join(BASE_DIR, 'data', 'PershingMetabolizer', 'parkSVG', 'PrecedentSVG')

app = FastAPI(title="Memory Machine API")

# Dev-only CORS: the React/Vite frontend runs on its own dev-server port and
# calls this API cross-origin. Local single-user tool, no auth boundary to
# protect yet -- tighten this before any real deployment.
#
# Regex, not a fixed ["...:5173"] allowlist (2026-07-09 fix): Vite picks the
# next free port whenever 5173 is already taken (e.g. a second dev server, a
# stray process from an earlier session) -- with a hardcoded single-port
# allowlist that silently mismatches origin, every fetch to this API gets
# CORS-blocked, an unhandled rejection crashes whichever component made the
# request (StaticContextGroup's OBJ fetch, in the reported case), and that
# takes the whole WebGLRenderer down with it ("shows for a second then goes
# black"). Matching any localhost/127.0.0.1 port keeps the same dev-only
# security posture (still not a real origin allowlist) while not depending
# on exactly one port being free.
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"http://(localhost|127\.0\.0\.1):\d+",
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- AI & DB INITIALIZATION ---
# 2026-07-17: decoupled from the Gemini/google-genai import -- this repo's
# AI text-generation path is now Ollama-only (see logic/ai_synthesizer.py),
# but AI_ENABLED was previously gated behind `from google import genai`
# succeeding, which silently kept ChromaDB's real 4001-document review
# corpus offline the whole time too (the "historical reviews" RAG context
# in generate_spatial_seed() was always empty). ChromaDB now inits on its
# own, independent of any Gemini/API-key availability.
AI_ENABLED = False

try:
    from dotenv import load_dotenv
    import chromadb
    load_dotenv(os.path.join(BASE_DIR, '.env'))

    db_path = os.path.join(BASE_DIR, 'db')
    chroma_client = chromadb.PersistentClient(path=db_path)
    collection = chroma_client.get_or_create_collection(name="memory_machine_corpus")

    AI_ENABLED = True
    print(f"✅ ChromaDB corpus online ({collection.count()} documents)")
except Exception as e:
    print(f"⚠️ ChromaDB unavailable: {e}")

# Ensure static mount directories exist to prevent startup crashes
os.makedirs(os.path.join(BASE_DIR, "static"), exist_ok=True)
os.makedirs(os.path.join(BASE_DIR, "html"), exist_ok=True)

# --- STATIC MOUNTS ---
app.mount("/static", StaticFiles(directory="static"), name="static")
app.mount("/archive", StaticFiles(directory="html"), name="archive")

models_dir = os.path.join(BASE_DIR, 'models')
os.makedirs(models_dir, exist_ok=True)
app.mount("/models", StaticFiles(directory="models"), name="models")

comfy_output_dir = r"C:\ComfyUI_windows_portable\ComfyUI\output"
if os.path.exists(comfy_output_dir):
    app.mount("/comfy-output", StaticFiles(directory=comfy_output_dir), name="comfy-output")

# Static real-world context (columns/tunnel/secondary_entrance/ramps) for
# the Pershing viewport -- same site_named.obj blender_cockpit.py's
# import_static_context() loads once for visual reference; it does not
# participate in the live TerracingEngine rebuild.
pershing_context_dir = os.path.join(BASE_DIR, "outputs", "vector_export_test")
if os.path.exists(pershing_context_dir):
    app.mount("/pershing-context", StaticFiles(directory=pershing_context_dir), name="pershing-context")

# Serves whatever sketch photo is currently active (uploaded or pre-existing)
# so the frontend's paint canvas can load it as an <img> background.
app.mount("/pershing-sketch", StaticFiles(directory=PERSHING_SKETCH_DIR), name="pershing-sketch")

# Serves OBJs produced by the headless-Blender "build" tier (see
# logic/pershing_blender.py) -- distinct from /pershing-context, which
# serves the one static, unchanging reference OBJ.
app.mount("/blender-headless-output", StaticFiles(directory=pershing_blender.OUTPUT_DIR), name="blender-headless-output")

# Serves diagram_tool/'s exported SVGs so DiagramInputPanel.jsx can show
# thumbnails without a dedicated download endpoint -- same pattern as
# /pershing-context above. Guarded by os.path.exists since this directory
# only exists once diagram_tool/ has actually exported something to it.
if os.path.exists(LEGACY_DIAGRAM_DIR):
    app.mount("/legacy-diagrams", StaticFiles(directory=LEGACY_DIAGRAM_DIR), name="legacy-diagrams")

def archive_generation_record(prompt, narrative, spatial_seed, diagram=""):
    """Writes a memory_machine_generation_<ms>.json record -- same shape/dir/
    naming convention (archive/diagrams/generated/, millisecond timestamp)
    every 2D-generation consumer already expects (list_2d_generations(),
    preview_2d_generation() in logic/pershing_api.py), so anything archived
    here shows up in the SPATIALIZE tab's "Recent 2D Generations" panel for
    free -- no separate list/read path needed.

    Extracted (2026-07-24) from generate_memory_node()'s own inline archive
    step so a second caller (pershing_archive_route below, "Save Build" in
    RECONSTRUCT) can write the exact same record shape for whatever diagram
    was live in SPATIALIZE at save time, instead of a build only ever living
    in outputs/pershing_archive/ with no trace back to the 2D layout that
    produced it -- closing the loop the user asked for: diagram -> bake ->
    3D build -> save should keep the diagram discoverable from the 2D side
    too, not just the 3D one.

    Best-effort: a write failure here shouldn't fail the caller's own
    action (a generation, or a build save) -- same tolerance the original
    inline version already had."""
    try:
        archive_dir = os.path.join(BASE_DIR, 'archive', 'diagrams', 'generated')
        os.makedirs(archive_dir, exist_ok=True)
        timestamp_ms = int(time.time() * 1000)
        record = {
            "timestamp_ms": timestamp_ms,
            "prompt": prompt,
            "narrative": narrative,
            "diagram": diagram,
            "spatial_seed": spatial_seed,
        }
        record_path = os.path.join(archive_dir, f"memory_machine_generation_{timestamp_ms}.json")
        with open(record_path, "w", encoding="utf-8") as f:
            json.dump(record, f, indent=2)
        return os.path.basename(record_path)
    except Exception as e:
        print(f"      -> [GENERATION ARCHIVE ERROR] {e}")
        return None


# --- DATA MODELS ---
class MemoryPrompt(BaseModel): prompt: str

class ExportPayload(BaseModel):
    filename: str
    data: str
    type: str

class ExportViewPngPayload(BaseModel):
    filename: str
    data: str  # data:image/png;base64,... straight from canvas.toDataURL()

class CapturePayload(BaseModel):
    prompt: str
    spatial_seed: list
    geometries: list
    narrative: str
    isLightMode: bool
    activeTab: str

class ComfyTextTo3DPayload(BaseModel):
    prompt: str          # spatial narrative / zone description
    zone_type: str       # e.g. "GREEN_SPACE", "WATER_FEATURES", "UNIQUE_ELEMENTS"
    position_x: float = 0.0   # Three.js world X (from 2D transform)
    position_z: float = 0.0   # Three.js world Z (from 2D transform Y)

class ComfyRenderPayload(BaseModel):
    image_b64: str       # base64 PNG from Three.js canvas
    narrative: str       # spatial quality narrative for the prompt

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
                # Ensure site_id is consistently formatted to prevent 404s in the picker
                raw_name = file[:-4].replace("_", " ").title()
                site_id = raw_name.replace(" ", "")
                site_name = raw_name
                
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

@app.get("/api/site-grid")
async def get_site_grid(cell_size_ft: float = 27.0, rotation_deg: float = 0.0):
    """Rotatable spatial-organizer grid for the 2D diagram canvas -- see
    logic/site_grid.py's module docstring. Site dimensions come from the
    same REAL_GEOMETRY the 3D bay grid uses, so both grids stay anchored to
    the same real-world site regardless of which SVG is loaded client-side."""
    try:
        width_ft = REAL_GEOMETRY["site"]["width_ft"]
        length_ft = REAL_GEOMETRY["site"]["length_ft"]
        grid = build_site_grid(width_ft, length_ft, cell_size_ft, rotation_deg)
        return {"status": "success", "grid": grid}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

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

# "Export Current View" (Viewport.jsx) -- user asked (2026-07-17) for the
# PNG screenshot to land next to the vector-linework SVG exports instead of
# the browser's Downloads folder, with no save dialog. Same base64-dataURL
# decode as export_diagram() above, different fixed target directory.
PERSHING_EXPORT_PNG_DIR = os.path.join(BASE_DIR, "data", "PershingMetabolizer", "parkSVG", "remixedGeneratedPNGs")

@app.post("/api/pershing/export-view-png")
async def pershing_export_view_png(payload: ExportViewPngPayload):
    os.makedirs(PERSHING_EXPORT_PNG_DIR, exist_ok=True)
    filepath = os.path.join(PERSHING_EXPORT_PNG_DIR, os.path.basename(payload.filename))
    try:
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

    # 2.5 Ground the PROG (amenity/attractor) pick's location in the 3D
    # side's real amenity-deficit signal -- same bridge remix_precedent()
    # already uses for its empty-prompt path, applied here to every
    # generate_spatial_seed() call so 2D placement reflects the same deficit
    # data the 3D Pershing Metabolizer does. Best-effort: a slow/unavailable
    # bay-grid rebuild shouldn't block the 2D generate flow.
    try:
        deficit_weights = pershing_get_deficit_weights()
        gm_data = guideline_manager.parse()
        spatial_seed_raw = apply_deficit_weighting(spatial_seed_raw, gm_data.get("metadata", {}), deficit_weights)
    except Exception as e:
        print(f"      -> [DEFICIT WEIGHTING ERROR] {e}")

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

    # 5. Archive the generation's own data alongside the frontend's SVG/JPG
    # auto-export (static/main.js's autoExportEnabled pipeline) -- that only
    # ever saved the rendered image, never the prompt/narrative/layer picks
    # that produced it, so past generations couldn't be reviewed or
    # reconstructed. Best-effort: a write failure here shouldn't fail the
    # actual generation.
    archive_generation_record(prompt, ai_narrative, spatial_seed, diagram)

    return {
        "status": "success",
        "narrative": ai_narrative,
        "diagram": diagram,
        "spatial_seed": spatial_seed,
        "geometries": geometries
    }

# ── COMFY: HEALTH CHECK ───────────────────────────────────────────────────────
@app.get("/api/comfy-status")
async def comfy_status():
    """Quick check — is ComfyUI reachable?"""
    alive = comfy_ping()
    return {"online": alive, "url": "http://127.0.0.1:8188"}


# ── COMFY: TEXT → IMAGE → 3D (TripoSR) ───────────────────────────────────────
@app.post("/api/comfy-text-to-3d")
async def comfy_text_to_3d(payload: ComfyTextTo3DPayload):
    """
    Phase 2: Text prompt → Flux image → TripoSR GLB.
    Patches textToimageTo3D.json, queues it, polls for the GLB output.
    Returns the GLB path served via /comfy-output/ static mount.
    """
    try:
        if not comfy_ping():
            return JSONResponse(status_code=503, content={"error": "ComfyUI not reachable at localhost:8188"})

        wf_path = os.path.join(BASE_DIR, "data", "comfy", "textToimageTo3D.json")
        if not os.path.exists(wf_path):
            return JSONResponse(status_code=500, content={"error": f"Workflow not found: {wf_path}"})

        workflow = load_workflow(wf_path)

        zone_style = {
            "GREEN_SPACE":     "lush green park landscape element, trees and vegetation, architectural plan view",
            "WATER_FEATURES":  "urban water feature, fountain or reflecting pool, architectural model",
            "UNIQUE_ELEMENTS": "urban architectural activator, pavilion or public sculpture, clean white model",
            "SHADE":           "shade structure or canopy, architectural pergola, clean model",
            "HARDSCAPE":       "urban hardscape element, paving or plaza surface, architectural model",
        }.get(payload.zone_type, "urban park architectural element, clean white model")

        full_prompt = f"{payload.prompt}. {zone_style}. Isolated on white background, architectural massing model, no shadows."

        patched = patch_workflow(workflow, {
            "9":  {"text": full_prompt},
            "10": {"text": ""},
            "11": {"width": 1024, "height": 1024, "batch_size": 1},
        })

        prompt_id = queue_workflow(patched)
        if not prompt_id:
            return JSONResponse(status_code=500, content={"error": "Failed to queue workflow"})

        glb_path = await asyncio.get_running_loop().run_in_executor(
            None, lambda: poll_for_output(prompt_id, ".glb")
        )

        if not glb_path:
            return JSONResponse(status_code=504, content={"error": "Timed out waiting for GLB output"})

        rel_path = os.path.relpath(glb_path, r"C:\ComfyUI_windows_portable\ComfyUI\output")
        return {
            "status": "success",
            "prompt_id": prompt_id,
            "glb_path": glb_path,
            "glb_url": f"/comfy-output/{rel_path.replace(os.sep, '/')}",
            "position": {"x": payload.position_x, "y": 0, "z": payload.position_z}
        }
    except Exception as e:
        import traceback
        print(f"[comfy-text-to-3d ERROR] {traceback.format_exc()}")
        return JSONResponse(status_code=500, content={"error": str(e)})


# ── COMFY: 3D SCENE CAPTURE → FLUX KONTEXT RENDER ────────────────────────────
@app.post("/api/comfy-render")
async def comfy_render(payload: ComfyRenderPayload):
    """
    Phase 3: Three.js canvas capture + narrative → Flux Kontext atmospheric render.
    Writes the base64 image to a temp file, patches flux1dev.json, queues, polls.
    Returns the output image URL.
    """
    if not comfy_ping():
        return JSONResponse(status_code=503, content={"error": "ComfyUI not reachable at localhost:8188"})

    wf_path = os.path.join(BASE_DIR, "data", "comfy", "flux1dev.json")
    if not os.path.exists(wf_path):
        return JSONResponse(status_code=500, content={"error": f"Workflow not found: {wf_path}"})

    # Write the canvas capture to ComfyUI's input folder so LoadImage can find it
    comfy_input_dir = r"C:\ComfyUI_windows_portable\ComfyUI\input"
    os.makedirs(comfy_input_dir, exist_ok=True)
    temp_filename = f"mm_capture_{int(time.time()*1000)}.png"
    temp_path = os.path.join(comfy_input_dir, temp_filename)

    try:
        # Strip base64 header if present
        img_data = payload.image_b64
        if "," in img_data:
            img_data = img_data.split(",", 1)[1]
        with open(temp_path, "wb") as f:
            f.write(base64.b64decode(img_data))
    except Exception as e:
        return JSONResponse(status_code=400, content={"error": f"Bad image data: {e}"})

    workflow = load_workflow(wf_path)

    # Build atmospheric architectural prompt from narrative
    full_prompt = (
        f"{payload.narrative}. "
        "Architectural visualization, urban park, golden hour lighting, "
        "photorealistic render, high detail, cinematic composition."
    )

    patched = patch_workflow(workflow, {
        "6":   {"text": full_prompt},          # Positive prompt
        "142": {"image": temp_filename},        # Input image → LoadImageOutput → use temp file
    })

    # Node 142 is LoadImageOutput which loads from ComfyUI output folder.
    # Since we're providing a capture (not a prior output), swap to a standard LoadImage node approach
    # by injecting the filename directly. ComfyUI will find it in the input/ folder.
    patched["142"]["class_type"] = "LoadImage"
    patched["142"]["inputs"] = {"image": temp_filename}

    prompt_id = queue_workflow(patched)
    if not prompt_id:
        return JSONResponse(status_code=500, content={"error": "Failed to queue render workflow"})

    img_path = await asyncio.get_running_loop().run_in_executor(
        None, lambda: poll_for_output(prompt_id, ".png")
    )

    if not img_path:
        # Try jpg fallback
        img_path = await asyncio.get_running_loop().run_in_executor(
            None, lambda: poll_for_output(prompt_id, ".jpg")
        )

    if not img_path:
        return JSONResponse(status_code=504, content={"error": "Timed out waiting for render output"})

    rel_path = os.path.relpath(img_path, r"C:\ComfyUI_windows_portable\ComfyUI\output")
    return {
        "status": "success",
        "prompt_id": prompt_id,
        "image_path": img_path,
        "image_url": f"/comfy-output/{rel_path.replace(os.sep, '/')}"
    }


@app.get("/api/pershing/config")
async def pershing_config():
    return pershing_get_config()


@app.get("/api/pershing/bay-grid")
async def pershing_bay_grid_route():
    """27ft structural bay grid + per-bay placement signals (painted/imported
    masks primary, transit/deficit secondary) -- see get_bay_grid()'s
    docstring. Consumed by the frontend's program-placement layer and by
    logic/program_placement.py directly (not over HTTP) when run offline."""
    return pershing_get_bay_grid()


@app.get("/api/pershing/program-zones")
async def pershing_program_zones_route():
    """Bay-grid program placement (data/program_requirements.json's
    NEEDED/Suggested items packed onto the bay grid) -- see
    get_program_zones()'s docstring."""
    return pershing_get_program_zones()


@app.post("/api/pershing/archive")
async def pershing_archive_save_route(payload: ArchiveSaveRequest):
    """ARCHIVE tab: persist a build snapshot server-side (outputs/pershing_archive/)
    -- see save_build_to_archive()'s docstring for how this differs from the
    client-side-only "Save Build" download."""
    return pershing_save_build_to_archive(payload)


@app.get("/api/pershing/archive")
async def pershing_archive_list_route():
    return pershing_list_archived_builds()


@app.get("/api/pershing/archive/{filename}")
async def pershing_archive_get_route(filename: str):
    try:
        return pershing_get_archived_build(filename)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.delete("/api/pershing/archive/{filename}")
async def pershing_archive_delete_route(filename: str):
    return pershing_delete_archived_build(filename)


@app.post("/api/pershing/rebuild")
async def pershing_rebuild_route(params: RebuildParams):
    return pershing_rebuild(params)


@app.post("/api/pershing/grow-network")
async def pershing_grow_network_route(payload: GrowNetworkRequest):
    """Grows the Space Colonization pedestrian circulation network against
    whatever terrain params the frontend currently has set -- synchronous
    (see grow_network()'s own docstring for why this doesn't need the
    async job-polling pattern the Blender build tier below uses)."""
    return pershing_grow_network(payload)


@app.post("/api/pershing/carve-network-canyon")
async def pershing_carve_network_canyon_route(payload: GrowNetworkRequest):
    """Carves a canyon along the grown circulation network's primary trunk
    into the live SKETCH_WEIGHTS -- explicit, deliberate action (unlike
    network growth itself, automatic since 2026-07-23) since carving
    reshapes terrain that growth itself reads from; see
    carve_network_canyon()'s own docstring for why auto-carving on every
    rebuild would risk a drift loop. Frontend calls /rebuild right after,
    same pattern bake() already establishes."""
    return pershing_carve_network_canyon(payload)


@app.post("/api/pershing/generate-canopy")
async def pershing_generate_canopy_route(payload: GenerateCanopyRequest):
    """Generates the organic panelized canopy roof + branching supports
    against whatever terrain/program params the frontend currently has
    set -- explicit action, synchronous (see generate_canopy()'s own
    docstring for why this doesn't need the async job-polling pattern the
    Blender build tier below uses)."""
    return pershing_generate_canopy(payload)


@app.post("/api/pershing/generate-drawings")
async def pershing_generate_drawings_route(payload: GenerateDrawingsRequest):
    """Renders one of the Drawings tab's 3 styles (lineweight/color/diagram)
    against whatever terrain/program params the frontend currently has set
    -- explicit action, synchronous (see generate_drawings()'s own
    docstring)."""
    return pershing_generate_drawings(payload)


@app.post("/api/pershing/save-drawing")
async def pershing_save_drawing_route(payload: SaveDrawingRequest):
    """Writes the current Drawings tab style/view to disk as SVG+PNG+DXF --
    see save_drawing()'s own docstring for why DXF, not PNG, is what
    actually preserves layers/colors for CAD import)."""
    return pershing_save_drawing(payload)


@app.post("/api/pershing/juror-chat")
async def pershing_juror_chat_route(payload: JurorChatRequest):
    """Grounded Q&A for the live thesis-defense juror chat -- see
    logic/juror_chat.py's module docstring for the reply/action contract."""
    return pershing_juror_chat(payload)


@app.post("/api/pershing/critique")
async def pershing_critique_route(payload: CritiqueRequest):
    """"The Metabolist" -- on-demand qualitative critique of the current
    design, built from the spatial_summary rebuild() already returns. See
    logic/juror_chat.py's CRITIC_PERSONA_SYSTEM_TEXT for the persona."""
    return pershing_critique(payload)


@app.get("/api/pershing/sketch")
async def pershing_sketch_info():
    return pershing_get_sketch_info()


@app.post("/api/pershing/sketch/upload")
async def pershing_sketch_upload(file: UploadFile = File(...)):
    content = await file.read()
    return pershing_save_uploaded_sketch(file.filename, content)


@app.post("/api/pershing/bake")
async def pershing_bake_route(grids: BakeGrids):
    return pershing_bake(grids)


# Diagram Input mode (2026-07-11) -- a separate design-input mechanism from
# the paint canvas above, reading colors off an existing legacy-diagram
# export instead of freehand brush strokes. Read-only preview; the frontend
# commits via the EXISTING /api/pershing/bake route above with the returned
# grids, so there's no parallel commit path to keep in sync.
@app.get("/api/pershing/legacy-diagrams")
async def pershing_legacy_diagrams_list():
    return pershing_list_legacy_diagrams()


@app.post("/api/pershing/legacy-diagrams/preview")
async def pershing_legacy_diagrams_preview(payload: PreviewLegacyDiagramRequest):
    return pershing_preview_legacy_diagram(payload.filename)


# Import a saved 2D-app generation (2026-07-22) -- same read-only
# list-then-preview-then-bake shape as the legacy-diagrams routes above, but
# reading archive/diagrams/generated/memory_machine_generation_*.json
# (written by generate_memory_node() below) instead of a rasterized/vector
# diagram export. See logic/pershing_api.py's preview_2d_generation()
# docstring for why this needs no SVG re-parsing at all.
@app.get("/api/pershing/2d-generations")
async def pershing_2d_generations_list():
    return pershing_list_2d_generations()


@app.post("/api/pershing/2d-generations/preview")
async def pershing_2d_generations_preview(payload: Preview2DGenerationRequest):
    try:
        return pershing_preview_2d_generation(payload.filename)
    except (ValueError, FileNotFoundError) as e:
        return JSONResponse(status_code=404, content={"error": str(e)})


class ArchiveGenerationRequest(BaseModel):
    prompt: str = ""
    narrative: str = ""
    spatial_seed: list = []


# "Save Build" -> "Recent 2D Generations" bridge (2026-07-24) -- App.jsx's
# handleSaveBuild calls this (in addition to its own /api/pershing/archive
# 3D-snapshot save) with whatever SPATIALIZE diagram was live at save time,
# so the diagram that produced a saved build stays discoverable from the 2D
# side too -- see archive_generation_record()'s own docstring for the full
# "why." Silently a no-op (empty spatial_seed) when the build wasn't
# produced via SPATIALIZE at all (e.g. freehand painting only).
@app.post("/api/archive-generation")
async def archive_generation_route(payload: ArchiveGenerationRequest):
    filename = archive_generation_record(payload.prompt, payload.narrative, payload.spatial_seed)
    return {"filename": filename}


# SPATIALIZE tab (2026-07-23) -- 2D authoring ported natively into the 3D
# React app. Same preview-then-bake shape as the 2d-generations routes
# above, but takes the live in-memory spatial_seed directly (no saved-file
# round-trip) and rasterizes with z-order occlusion, since the SPATIALIZE
# canvas's stack order is an intentional authoring signal.
@app.post("/api/pershing/spatialize-preview")
async def pershing_spatialize_preview_route(payload: SpatializePreviewRequest):
    return pershing_spatialize_preview(payload.spatial_seed)


@app.get("/api/pershing/deficit-weights")
async def pershing_deficit_weights_route():
    return pershing_get_deficit_weights_public()


@app.get("/api/pershing/deficit-hotspots")
async def pershing_deficit_hotspots_route(top_n: int = 12):
    """Real per-bay deficit-hotspot positions (not the coarse 9-cardinal-
    point summary /deficit-weights returns) -- see
    get_deficit_hotspots()'s own docstring. Used by SPATIALIZE's live
    overlay so hotspot circles sit at their actual site positions."""
    return pershing_get_deficit_hotspots(top_n)


@app.post("/api/pershing/blender-build")
async def pershing_blender_build_route(
    payload: dict, lineart: bool = False, view_dir: str = None, include_real_context: bool = False,
    tag: str = None,
):
    """Kicks off the headless-Blender "build" tier (see
    logic/pershing_blender.py) on whatever rebuild result the frontend
    currently has on screen -- payload is exactly the JSON /rebuild already
    returned, passed straight through, so the built OBJ is guaranteed to
    match what's visible, not a server-side recomputation that could drift
    from it. Returns immediately; the browser polls the job-status route
    below rather than blocking this request on the Blender subprocess.

    lineart/view_dir/include_real_context are query params, not body
    fields -- keeps the POST body exactly the raw rebuild-result dict,
    unpolluted, since it's forwarded straight through to Blender as the
    input JSON. view_dir is a comma-separated "x,y,z" string
    (?view_dir=0.3,-0.6,0.75) -- only meaningful alongside lineart=true
    (see pershing_blender.start_build_job's docstring); the frontend's
    "Export Current View" trigger (Viewport.jsx) derives this from the
    live OrbitControls camera direction."""
    view_dir_tuple = tuple(float(v) for v in view_dir.split(",")) if view_dir else None
    job_id = pershing_blender.start_build_job(
        payload, lineart=lineart, view_dir=view_dir_tuple, include_real_context=include_real_context, tag=tag)
    return {"job_id": job_id, "status": "queued"}


@app.get("/api/pershing/blender-build/{job_id}")
async def pershing_blender_build_status(job_id: str):
    job = pershing_blender.get_job(job_id)
    if job is None:
        return JSONResponse(status_code=404, content={"error": "unknown job_id"})
    return job


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)