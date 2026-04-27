from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import uvicorn, os, json, re

# --- MODULAR LOGIC IMPORTS (LITE VERSION) ---
from logic.svg_parser import parse_svg_to_json

# --- CONFIGURATION ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_DIR = os.path.join(BASE_DIR, 'db')
SVG_DIR = os.path.join(BASE_DIR, 'data', 'ParkSVG')
os.makedirs(os.path.join(BASE_DIR, "models"), exist_ok=True)

app = FastAPI(title="Memory Machine API - Blender Lite")

# --- INLINE HELPERS (Replaces heavy dependencies) ---
class GuidelineManager:
    def __init__(self, filepath):
        self.filepath = filepath
        
    def parse(self):
        if not os.path.exists(self.filepath):
            return {"guidelines": {}, "metadata": {}, "primitives": []}
        with open(self.filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        match = re.search(r'```json\n(.*?)\n```', content, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                pass
        return {"guidelines": {}, "metadata": {}, "primitives": []}

def generate_mermaid_diagram(prompt, matches, spatial_params):
    safe_prompt = re.sub(r'["\[\]{}()/\\]', '', prompt[:40])
    return f"""graph TD
    A["Prompt: {safe_prompt}..."] --> B["ChromaDB Search"]
    B --> C["Context Aggregation"]
    C --> D["Compile Blender Payload"]
    D --> E["Claude MCP Handoff"]
    E --> F["Blender Execution"]"""

# --- AI & DB INITIALIZATION ---
try:
    from dotenv import load_dotenv
    import chromadb
    load_dotenv(os.path.join(BASE_DIR, '.env'))
    chroma_client = chromadb.PersistentClient(path=DB_DIR)
    collection = chroma_client.get_or_create_collection(name="memory_machine_corpus")
    AI_ENABLED = True
    print("✅ AI Services Online (Blender Branch)")
except Exception as e:
    print(f"⚠️ AI Services Offline: {e}")
    AI_ENABLED = False

# --- STATIC MOUNTS ---
os.makedirs(os.path.join(BASE_DIR, "static"), exist_ok=True)
os.makedirs(os.path.join(BASE_DIR, "html"), exist_ok=True)
os.makedirs(os.path.join(BASE_DIR, "templates"), exist_ok=True)

app.mount("/static", StaticFiles(directory="static"), name="static")
app.mount("/archive", StaticFiles(directory="html"), name="archive")

# --- DATA MODELS ---
class MemoryPrompt(BaseModel): 
    prompt: str
    site_name: str = "pershing_boundary"

# --- PASSIVE UI ROUTES ---

@app.get("/", response_class=HTMLResponse)
async def read_root():
    """Serves the main landing page."""
    return FileResponse(os.path.join(BASE_DIR, "templates", "index.html"))

@app.get("/api/guidelines")
async def get_guidelines():
    """Returns the parsed urban design guidelines for the HUD."""
    gm = GuidelineManager(os.path.join(BASE_DIR, "urban_design_guidelines.md"))
    data = gm.parse()
    return {"guidelines": data["guidelines"], "metadata": data["metadata"], "primitives": data["primitives"]}

# --- BLENDER MCP PAYLOAD COMPILER ---

@app.post("/api/compile-blender-payload")
async def compile_blender_payload(payload: MemoryPrompt):
    """
    Aggregates RAG memory, APA constraints, and SVG coordinates into a 
    single strict JSON payload for Claude and the Blender MCP.
    """
    
    # 1. RAG Query (The Narrative Context)
    narrative_context = ""
    matches = []
    if AI_ENABLED:
        try:
            results = collection.query(query_texts=[payload.prompt], n_results=5)
            if results['documents'] and results['documents'][0]:
                narrative_context = "\n".join(results['documents'][0])
                matches = [{"document": d} for d in results['documents'][0]]
        except Exception as e:
            print(f"RAG Error: {e}")

    # 2. Parse APA Constraints (The Ruleset)
    gm = GuidelineManager(os.path.join(BASE_DIR, "urban_design_guidelines.md"))
    try:
        guidelines_data = gm.parse()
    except Exception as e:
        guidelines_data = {"error": f"Could not parse guidelines: {e}"}

    # 3. Parse SVGs (The Spatial Boundary & Generated Diagram)
    svg_file_primary = os.path.join(SVG_DIR, f"{payload.site_name}.svg")
    svg_file_archive = os.path.join(BASE_DIR, 'archive', 'diagrams', 'generatedDiagramsColor', f"{payload.site_name}.svg")
    svg_file_remixed = os.path.join(BASE_DIR, 'archive', 'diagrams', 'remixed_svgs', f"{payload.site_name}.svg")
    
    target_svg = None
    if os.path.exists(svg_file_primary):
        target_svg = svg_file_primary
    elif os.path.exists(svg_file_archive):
        target_svg = svg_file_archive
    elif os.path.exists(svg_file_remixed):
        target_svg = svg_file_remixed
        
    site_coords = []
    svg_debug_info = ""
    if target_svg:
        try:
            # Apply a scaling factor if your SVG requires conversion from pixels to meters
            site_coords = parse_svg_to_json(target_svg, scale_factor=0.1)
            svg_debug_info = f"Success: Parsed {len(site_coords)} layers from {target_svg}"
        except Exception as e:
            svg_debug_info = f"Error parsing {target_svg}: {e}"
            print(svg_debug_info)
    else:
        svg_debug_info = f"Error: Could not find SVG file. Looked in: 1) {svg_file_primary}  2) {svg_file_archive}  3) {svg_file_remixed}"
        print(svg_debug_info)

    # Generate lightweight diagram for UI/Verification
    spatial_params = {"geometry_type": "landscape_mound", "height_m": 10}
    diagram = generate_mermaid_diagram(payload.prompt, matches, spatial_params)

    return {
        "status": "success",
        "intervention_name": "Blender MCP Generation",
        "diagram": diagram,
        "mcp_payload": {
            "rag_narrative": narrative_context,
            "apa_parks_constraints": guidelines_data.get("guidelines", {}),
            "zoning_primitives": guidelines_data.get("primitives", []),
            "site_coordinates_3d": site_coords,
            "svg_debug": svg_debug_info
        }
    }

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8001) # Running on 8001 to avoid port clashing with app.py