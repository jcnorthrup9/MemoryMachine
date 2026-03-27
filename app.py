from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
import uvicorn, subprocess, sys, os, json, re, math
from datetime import datetime

# --- AI & DB IMPORTS ---
try:
    from dotenv import load_dotenv
    import google.generativeai as genai
    import chromadb
    from chromadb.utils import embedding_functions # Keep this for consistency, but DefaultEmbeddingFunction is used
    AI_ENABLED = True
except ImportError:
    AI_ENABLED = False

# --- CONFIGURATION ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_DIR = os.path.join(BASE_DIR, 'db')

app = FastAPI(title="Memory Machine API")

# --- AI & DB INITIALIZATION ---
if AI_ENABLED:
    load_dotenv(os.path.join(BASE_DIR, '.env'))
    api_key = os.environ.get("GEMINI_API_KEY")
    if api_key:
        genai.configure(api_key=api_key)
        print("✅ Gemini AI Initialized.")
    else:
        print("⚠️ Gemini API key not found in .env file. AI features will be disabled.")
        AI_ENABLED = False

    try:
        chroma_client = chromadb.PersistentClient(path=DB_DIR)
        embedding_function = embedding_functions.DefaultEmbeddingFunction() # Ensure this matches data_ingest.py
        collection = chroma_client.get_collection(name="memory_machine_corpus", embedding_function=embedding_function)
        print(f"✅ ChromaDB connection successful. Collection count: {collection.count()}")
    except Exception as e:
        print(f"❌ ChromaDB connection failed: {e}\n   Please run 'python logic/data_ingest.py' first.")
        AI_ENABLED = False

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

class MemoryPrompt(BaseModel):
    prompt: str

class HarvestRequest(BaseModel):
    target: str

@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    """Serves the main landing page with the Three.js canvas."""
    return templates.TemplateResponse("index.html", {"request": request})

# Real-world location + source metadata for each ingested dataset
SOURCE_INFO = {
    "Bottega Louie Reviews": {
        "full_name":   "Bottega Louie",
        "location":    "700 S Grand Ave, Downtown Los Angeles, CA",
        "source_type": "Yelp Reviews",
        "notes":       "Grand Beaux-Arts patisserie and restaurant; celebrated for its marble floors, soaring atrium, acoustic liveliness, and dense social energy.",
    },
    "Nakagin Capsule Tower Data": {
        "full_name":   "Nakagin Capsule Tower",
        "location":    "8-16 Ginza, Chuo City, Tokyo, Japan (demolished 2022)",
        "source_type": "TripAdvisor Reviews",
        "notes":       "Kisho Kurokawa's 1972 Metabolism landmark; 140 prefabricated capsule units stacked around two concrete cores. Iconic for its compressed domesticity and material decay.",
    },
    "Pershing Square Reviews": {
        "full_name":   "Pershing Square",
        "location":    "532 S Olive St, Downtown Los Angeles, CA",
        "source_type": "Google Maps Reviews",
        "notes":       "Five-acre public plaza in the heart of DTLA. Subject of this project — currently being demolished and redesigned for the third time in three decades.",
    },
    "O.T. Johnson Building Data": {
        "full_name":   "O.T. Johnson Building",
        "location":    "112 W 5th St, Downtown Los Angeles, CA",
        "source_type": "Historical Archive",
        "notes":       "1923 commercial loft building in the Broadway Historic District. Known for its cast iron columns, terrazzo floors, and preserved lobby atmosphere.",
    },
}


MATERIAL_COLORS = {
    "concrete": "#6b6460", "water": "#1a5f7a", "steel": "#8a8a9a",
    "glass": "#a8d8ea",    "wood": "#7a5535",  "vegetation": "#3a6535",
    "stone": "#7a7060",    "weathered_steel": "#7a5a45",
}

def build_geometries(spatial_params):
    """Translate AI spatial parameters into a list of Three.js geometry descriptors."""
    import math
    if not spatial_params:
        return []

    geo_type = spatial_params.get("geometry_type", "")
    footprint = spatial_params.get("footprint_m", {})
    width     = float(footprint.get("width", 10) if isinstance(footprint, dict) else 10)
    depth     = float(footprint.get("depth", 10) if isinstance(footprint, dict) else 10)
    height    = float(spatial_params.get("height_m", 5))

    # Normalise to preview scale — cap at 12 units radius so nothing dominates the scene
    MAX_RADIUS = 12.0
    raw_radius = width / 2.0
    scale      = min(1.0, MAX_RADIUS / raw_radius) if raw_radius > 0 else 1.0
    radius     = raw_radius * scale
    height     = height * scale
    depth      = depth  * scale

    materials = spatial_params.get("materials", [])
    primary   = next((MATERIAL_COLORS[m] for m in materials if m in MATERIAL_COLORS), "#666666")
    water_col = MATERIAL_COLORS["water"]
    green_col = MATERIAL_COLORS["vegetation"]

    geos = []

    def cyl(r, h, px=0, py=None, pz=0, color=None):
        geos.append({
            "type": "cylinder",
            "args": [r, r, h],
            "position": [px, (h / 2) if py is None else py, pz],
            "color": color or primary,
        })

    def box(w, h, d, px=0, py=None, pz=0, color=None):
        geos.append({
            "type": "box",
            "args": [w, h, d],
            "position": [px, (h / 2) if py is None else py, pz],
            "color": color or primary,
        })

    def sphere(r, px=0, py=0, pz=0, color=None):
        geos.append({
            "type": "sphere",
            "args": [r],
            "position": [px, py, pz],
            "color": color or green_col,
        })

    if geo_type == "pavilion_with_water":
        col_count = int(spatial_params.get("column_count", 8))
        col_h     = float(spatial_params.get("column_height_m", height * 0.75))
        col_r     = max(0.2, radius * 0.06)
        pool_r    = float(spatial_params.get("pool_width_m", radius * 1.1)) / 2
        pool_d    = float(spatial_params.get("pool_depth_m", 0.3))
        cyl(pool_r, pool_d, color=water_col)
        cyl(radius * 1.05, height * 0.05, color="#454540")
        for i in range(col_count):
            a = i * (2 * math.pi / col_count)
            cyl(col_r, col_h, radius * 0.8 * math.sin(a), None, radius * 0.8 * math.cos(a), color=primary)
        cyl(radius * 1.2, height * 0.1, py=col_h + height * 0.05, color="#363630")

    elif geo_type == "shade_canopy":
        col_count = int(spatial_params.get("column_count", 6))
        col_h     = float(spatial_params.get("column_height_m", height * 0.9))
        col_r     = max(0.15, radius * 0.05)
        for i in range(col_count):
            a = i * (2 * math.pi / col_count)
            cyl(col_r, col_h, radius * 0.85 * math.sin(a), None, radius * 0.85 * math.cos(a))
        cyl(radius * 1.1, height * 0.06, py=col_h + height * 0.03, color="#303030")

    elif geo_type == "water_garden":
        cyl(radius, height * 0.05, color="#454540")
        cyl(radius * 0.85, height * 0.07, color=water_col)
        mound_r = radius * 0.35
        sphere(mound_r, py=height * 0.07 + mound_r * 0.6)   # sits on top of pool rim
        cyl(radius * 0.1, height * 0.28, py=height * 0.14, color=primary)

    elif geo_type == "acoustic_screen":
        screen_h = float(spatial_params.get("screen_height_m", height))
        screen_l = float(spatial_params.get("screen_length_m", width))
        fin_count = max(3, int(screen_l / 2))
        fin_w = screen_l / (fin_count * 1.5)
        fin_d = max(0.2, fin_w * 0.35)
        for i in range(fin_count):
            fx = -screen_l / 2 + i * (screen_l / fin_count) + fin_w / 2
            box(fin_w, screen_h, fin_d, px=fx)

    elif geo_type == "memory_tower":
        cyl(radius,        height * 0.08,  color="#404040")
        cyl(radius * 0.35, height * 0.75,  py=height * 0.08 + height * 0.375, color=primary)
        cyl(radius * 0.55, height * 0.10,  py=height * 0.83 + height * 0.05,  color="#606060")
        cyl(radius * 0.06, height * 0.28,  py=height * 0.93 + height * 0.14,  color="#888888")

    elif geo_type == "landscape_mound":
        # Stacked flat discs — low earthwork mound, not a tower
        layers = 6
        for i in range(layers):
            frac    = 1.0 - i * (0.75 / layers)
            disc_h  = max(0.3, height * 0.18)
            cyl(radius * frac, disc_h, py=i * disc_h * 0.7, color=green_col)

    elif geo_type == "amphitheater":
        # Stepped concentric tiers — auditorium / bowl seating form
        tiers    = min(int(spatial_params.get("tiers", 6)), 10)
        tier_h   = max(0.4, height / tiers)
        stage_r  = radius * 0.25
        # Stage floor at centre
        cyl(stage_r, tier_h * 0.4, color="#303028")
        # Seating tiers radiating outward and upward
        for i in range(tiers):
            inner_r = stage_r + i * ((radius - stage_r) / tiers)
            outer_r = stage_r + (i + 1) * ((radius - stage_r) / tiers)
            seat_w  = outer_r - inner_r
            mid_r   = (inner_r + outer_r) / 2
            # Use a box ring approximated by 12 short arc-segments
            seg     = 12
            for s in range(seg):
                a0 = s * (2 * math.pi / seg)
                px = mid_r * math.sin(a0)
                pz = mid_r * math.cos(a0)
                box(seat_w * 0.92, tier_h, seat_w * 0.92,
                    px=px, py=i * tier_h + tier_h / 2, pz=pz, color=primary)

    else:
        box(width, height, depth)

    return geos


def generate_mermaid_diagram(prompt, matches, spatial_params):
    """Builds a Mermaid.js flowchart for the generation logic."""
    def mmd(s): return re.sub(r'["\[\]{}()/\\]', '', str(s))
    
    geo_type = spatial_params.get("geometry_type", "intervention")
    source_names = [mmd(m['metadata'].get('source', 'Unknown')) for m in matches] if matches else ["Inferred from Prompt"]

    lines = ["graph TD"]
    lines.append(f'    A[/"User Query: {mmd(prompt[:40])}..."/]')
    lines.append('    B{{Semantic Search}}')
    lines.append('    A --> B')
    
    for i, src in enumerate(source_names):
        lines.append(f'    S{i}("{src}")')
        lines.append(f'    B --> S{i}')

    lines.append('    C{{AI Synthesis}}')
    for i in range(len(source_names)):
        lines.append(f'    S{i} --> C')

    lines.append(f'    D["Geometry: {mmd(geo_type)}"]')
    lines.append(f'    E["Height: {spatial_params.get("height_m", "?")}m"]')
    lines.append(f'    F["Materials: {mmd(", ".join(spatial_params.get("materials", [])))}"]')
    lines.append('    C --> D & E & F')
    
    return "\n".join(lines)

@app.post("/api/generate")
async def generate_memory_node(payload: MemoryPrompt):
    """
    The live AI core logic endpoint.
    """
    if not AI_ENABLED:
        return {"status": "error", "narrative": "AI Core is disabled. Check server logs for errors (API key or DB connection)."}

    prompt = payload.prompt
    print(f"\n--- Received Prompt: '{prompt}' ---")

    # 1. Semantic Search
    print("[1/3] Searching memory archive for matching fragments...")
    try:
        results = collection.query(query_texts=[prompt], n_results=5, include=["metadatas", "documents"])
        matches = [{"metadata": m, "document": d} for m, d in zip(results['metadatas'][0], results['documents'][0])]
        for m in matches:
            print(f"      -> Match found: {m['metadata'].get('source', 'Unknown')}")
    except Exception as e:
        return {"status": "error", "narrative": f"Error querying vector database: {e}"}

    # 2. AI Synthesis
    print("[2/3] Synthesizing spatial parameters and narrative with Gemini...")
    context_excerpts = "\n\n".join([f"Source: {m['metadata'].get('source', 'Unknown')}\nFragment: \"...{m['document']}...\"" for m in matches])
    
    system_prompt = (
        'You are an expert architect for the "Memory Machine" project. Your task is to translate a user\'s qualitative desire into a concrete architectural intervention for Pershing Square, Los Angeles. '
        'You will be given a user prompt and several "memory fragments" from a database. '
        'Synthesize this information into a single, valid JSON object with NO additional text or markdown. The JSON object must have three top-level keys: "name", "narrative", and "spatial_parameters".\n\n'
        f'USER PROMPT:\n"{prompt}"\n\n'
        f'RETRIEVED MEMORY FRAGMENTS:\n{context_excerpts}\n\n'
        'INSTRUCTIONS:\n'
        '1.  **name**: Create a poetic name for the intervention (e.g., "Canopy of Whispers").\n'
        '2.  **narrative**: Write a short (2-paragraph) architectural narrative describing the space, its "witness marks" from the memory fragments, and how it collides with Pershing Square.\n'
        '3.  **spatial_parameters**: Generate precise parameters for a 3D model. This object MUST contain:\n'
        '    - "geometry_type": (string) Choose one: "pavilion_with_water", "shade_canopy", "water_garden", "acoustic_screen", "memory_tower", "landscape_mound", "amphitheater".\n'
        '    - "footprint_m": (object) with "width" and "depth" keys.\n'
        '    - "height_m": (float) The overall height in meters.\n'
        '    - "materials": (list of strings) e.g., ["concrete", "water", "steel", "glass", "wood", "vegetation", "stone"].\n'
        '    - **Specific parameters based on geometry_type (add 2-3 relevant keys):**\n'
        '        - If "shade_canopy": "canopy_shape" (string, e.g., "flat_grid", "curved_fabric", "perforated_mesh"), "column_count" (integer), "shade_percentage" (float 0.0-1.0).\n'
        '        - If "water_garden": "pool_depth_m" (float), "water_feature_type" (string, e.g., "shallow_wading_pool", "bubbler_fountain", "trickling_stream"), "seating_elements" (list of strings, e.g., ["integrated_benches", "loose_stones"]).\n'
        '        - If "pavilion_with_water": "roof_type" (string, e.g., "flat", "pitched", "domed"), "wall_material" (string, e.g., "glass", "wood_slats", "perforated_metal"), "water_body_shape" (string, e.g., "rectangular", "organic", "circular").\n'
        '        - If "acoustic_screen": "screen_pattern" (string, e.g., "perforated", "slatted", "textured"), "screen_height_m" (float), "screen_length_m" (float), "orientation" (string, e.g., "linear", "curved").\n'
        '        - If "memory_tower": "levels" (integer), "facade_material" (string, e.g., "concrete_panels", "reclaimed_wood", "reflective_glass"), "observation_deck_height_m" (float), "base_shape" (string, e.g., "square", "circular").\n'
        '        - If "landscape_mound": "slope_angle_degrees" (float, 0-90), "vegetation_type" (string, e.g., "grass", "succulents", "wildflowers"), "path_material" (string, e.g., "gravel", "paving_stones", "dirt").\n'
        '        - If "amphitheater": "tiers" (integer, number of seating levels), "seating_material" (string), "stage_width_m" (float), "orientation" (string, e.g., "circular", "fan_shaped", "rectangular").\n'
        'Choose "amphitheater" whenever the memory fragments reference tiered seating, stepped plazas, auditoriums, bowl-shaped spaces, or performance venues.\n\n'
        'Respond with ONLY the raw JSON object.'
    )
    
    try:
        model = genai.GenerativeModel('gemini-2.5-flash')
        response = model.generate_content(system_prompt)
        clean_json_str = response.text.strip().replace("```json", "").replace("```", "").replace("```JSON", "") # Robust cleaning
        ai_data = json.loads(clean_json_str)
        
        spatial_params = ai_data.get("spatial_parameters", {})
        narrative = ai_data.get("narrative", "[NARRATIVE GENERATION FAILED]")
        name = ai_data.get("name", "Generated Intervention")
        print(f"      -> AI synthesis complete. Generated: {name}")

    except Exception as e:
        return {"status": "error", "narrative": f"Error during AI synthesis: {e}"}

    # 3. Generate 3D Geometries and Diagram
    print("[3/3] Translating parameters into 3D geometry and logic diagram...")
    geometries = build_geometries(spatial_params)

    diagram = generate_mermaid_diagram(prompt, matches, spatial_params)

    # Build precedent cards from matched review fragments
    sources = []
    seen = set()
    for m in matches:
        source_key = m['metadata'].get('source', 'Unknown')
        if source_key in seen:
            continue
        seen.add(source_key)
        info = SOURCE_INFO.get(source_key, {
            "full_name": source_key, "location": "Unknown", "source_type": "Review", "notes": ""
        })
        sources.append({
            "name":        info["full_name"],
            "location":    info["location"],
            "source_type": info["source_type"],
            "notes":       info["notes"],
            "excerpt":     m["document"].strip(),
        })

    return {
        "status":    "success",
        "name":      name,
        "narrative": narrative,
        "sources":   sources,
        "geometries": geometries,
        "diagram":   diagram,
    }

@app.post("/api/harvest")
async def trigger_harvest(payload: HarvestRequest):
    """
    Endpoint to trigger the data harvesting process.
    This will run the machine_os.py script in the background.
    """
    script_path = "d:/MemoryMachine/logic/machine_os.py"
    print(f"Received harvest request for target: {payload.target}")
    
    # Use Popen for non-blocking execution
    process = subprocess.Popen([sys.executable, script_path, payload.target])
    
    print(f"Started harvest process with PID: {process.pid}")
    return {"status": "success", "message": f"Harvesting process initiated for '{payload.target}'. Check server logs for progress."}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)