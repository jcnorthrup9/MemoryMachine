from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
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

os.makedirs(os.path.join(BASE_DIR, "models"), exist_ok=True)
app.mount("/models", StaticFiles(directory="models"), name="models")

class MemoryPrompt(BaseModel):
    prompt: str

class HarvestRequest(BaseModel):
    target: str

class BakeRequest(BaseModel):
    name: str = "Unnamed Intervention"
    geometries: list

class FootprintItem(BaseModel):
    site: str
    layerId: str
    label: str
    color: str
    footprint: dict  # { cx, cz, width, depth, rotRad }

class Generate3DRequest(BaseModel):
    footprints: list[FootprintItem]

@app.get("/", response_class=HTMLResponse)
async def read_root():
    """Serves the main landing page with the Three.js canvas."""
    return FileResponse(os.path.join(BASE_DIR, "templates", "index.html"))

# Real-world location + source metadata for each ingested dataset
SOURCE_INFO = {
    "Pershing Square": {
        "full_name":   "Pershing Square",
        "location":    "532 S Olive St, Downtown Los Angeles, CA",
        "source_type": "Google Maps Reviews",
        "notes":       "Five-acre public plaza in the heart of DTLA. Subject of this project — currently being redesigned for the third time in three decades.",
        "logic":       "target_site",
        "coordinates": {"lat": 34.0483, "lon": -118.2525}
    },
    "Schouwburgplein": {
        "full_name":   "Schouwburgplein",
        "location":    "Rotterdam, Netherlands",
        "source_type": "Spatial Observations",
        "notes":       "Vast elevated hard plaza defined by four 35m hydraulic lighting masts operable by the public. Epoxy-coated steel deck, no conventional furniture.",
        "logic":       "vertical_actuated",
        "coordinates": {"lat": 51.9226, "lon": 4.4726}
    },
    "Grand Park LA": {
        "full_name":   "Grand Park",
        "location":    "200 N Grand Ave, Downtown Los Angeles, CA",
        "source_type": "Spatial Observations",
        "notes":       "Four-block civic park with a signature bright pink rubber splash pad membrane. Cooling social focal point in a hot urban climate.",
        "logic":       "surface_membrane",
        "coordinates": {"lat": 34.0563, "lon": -118.2462}
    },
    "Tanner Springs Park": {
        "full_name":   "Tanner Springs Park",
        "location":    "NW 10th Ave & NW Marshall St, Portland, OR",
        "source_type": "Spatial Observations",
        "notes":       "Naturalistic stormwater wetland park bounded by 368 reclaimed railway tracks set vertically, with fused glass inlays. Strong acoustic baffle effect.",
        "logic":       "boundary_texture",
        "coordinates": {"lat": 45.5258, "lon": -122.6841}
    },
    "Gardens by the Bay": {
        "full_name":   "Gardens by the Bay — Supertree Grove",
        "location":    "18 Marina Gardens Dr, Singapore",
        "source_type": "Spatial Observations",
        "notes":       "18 vertical gardens 25-50m tall; concrete and steel armatures supporting living plant canopies that shade, collect rainwater, and vent the greenhouses below.",
        "logic":       "infrastructure_vent",
        "coordinates": {"lat": 1.2816, "lon": 103.8636}
    },
    "Superkilen": {
        "full_name":   "Superkilen",
        "location":    "Norrebro, Copenhagen, Denmark",
        "source_type": "Spatial Observations",
        "notes":       "750m linear park in three color-coded zones; the Red Square features undulating black-and-white stripe patterns on modeled topography. Global furniture collection.",
        "logic":       "ground_pattern",
        "coordinates": {"lat": 55.6964, "lon": 12.5476}
    },
    "Paley Park": {
        "full_name":   "Paley Park",
        "location":    "3 E 53rd St, New York, NY",
        "source_type": "Spatial Observations",
        "notes":       "42x100ft vest-pocket park with a 20ft full-width water wall generating ~75dB white noise that masks Midtown Manhattan traffic. Movable chairs, honey locust canopy.",
        "logic":       "acoustic_wall",
        "coordinates": {"lat": 40.7601, "lon": -73.9714}
    },
    "Klyde Warren Park": {
        "full_name":   "Klyde Warren Park",
        "location":    "2012 Woodall Rodgers Fwy, Dallas, TX",
        "source_type": "Spatial Observations",
        "notes":       "5.2-acre deck park over a freeway in a hot continental climate. Shade trees, splash pad, food truck row, dog park — programmatic activation as primary strategy.",
        "logic":       "deck_program",
        "coordinates": {"lat": 32.7893, "lon": -96.8021}
    },
    "Millennium Park": {
        "full_name":   "Millennium Park",
        "location":    "201 E Randolph St, Chicago, IL",
        "source_type": "Spatial Observations",
        "notes":       "24.5-acre park over a rail yard. Crown Fountain: twin 50ft towers projecting faces that periodically jet water into a shallow black granite plaza. Cloud Gate reflects city at multiple scales.",
        "logic":       "interactive_surface",
        "coordinates": {"lat": 41.8826, "lon": -87.6226}
    },
    "Parc de la Villette": {
        "full_name":   "Parc de la Villette",
        "location":    "211 Av. Jean Jaures, Paris, France",
        "source_type": "Spatial Observations",
        "notes":       "55ha park by Tschumi; 26 red steel follies on a 120m grid provide wayfinding and distributed program across a landscape of lines, surfaces, and thematic gardens.",
        "logic":       "folly_grid",
        "coordinates": {"lat": 48.8937, "lon": 2.3931}
    },
    "Zaryadye Park": {
        "full_name":   "Zaryadye Park",
        "location":    "Varvarka St, Moscow, Russia",
        "source_type": "Spatial Observations",
        "notes":       "35-acre park adjacent to Red Square compressing four Russian biomes — tundra, steppe, forest, wetland. Floating cantilevered bridge over the Moscow River.",
        "logic":       "landscape_hybrid",
        "coordinates": {"lat": 55.7510, "lon": 37.6262}
    },
    "Piazza del Campo": {
        "full_name":   "Piazza del Campo",
        "location":    "Siena, Italy",
        "source_type": "Spatial Observations",
        "notes":       "Medieval public square known for its shell shape and sloping brick paving divided into nine segments.",
        "logic":       "radial_sloped_plaza",
        "coordinates": {"lat": 43.3183, "lon": 11.3315}
    },
    "The High Line": {
        "full_name":   "The High Line",
        "location":    "New York, NY",
        "source_type": "Spatial Observations",
        "notes":       "Elevated linear park built on a historic freight rail line. Combines hardscape paths with wild, naturalistic planting.",
        "logic":       "linear_infrastructure",
        "coordinates": {"lat": 40.7475, "lon": -74.0048}
    },
    "Federation Square": {
        "full_name":   "Federation Square",
        "location":    "Melbourne, Australia",
        "source_type": "Spatial Observations",
        "notes":       "Modern civic plaza with complex deconstructivist geometry, intricate paving, and mixed cultural programming.",
        "logic":       "fractal_plaza",
        "coordinates": {"lat": -37.8179, "lon": 144.9690}
    },
    "Pioneer Courthouse Square": {
        "full_name":   "Pioneer Courthouse Square",
        "location":    "Portland, OR",
        "source_type": "Spatial Observations",
        "notes":       "Terraced urban amphitheater known as 'Portland's living room' featuring brick paving and steps.",
        "logic":       "terraced_amphitheater",
        "coordinates": {"lat": 45.5191, "lon": -122.6793}
    },
}


# ---------------------------------------------------------------------------
# Pershing Square static site context — loaded from Rhino-derived geometry JSON.
# Generated by logic/site_to_threejs.py (run standalone to regenerate).
# 1 Three.js unit = 5 real metres = 16.4042 ft
# Origin = centre of the park block. X=E(+)/W(-), Y=Up, Z=S(+)/N(-)
# ---------------------------------------------------------------------------
_B = "#111116"   # close buildings
_T = "#0d0d12"   # background towers

# Surrounding building / skyline context kept here (not in Rhino model)
_DTLA_CONTEXT = [
    # ── Surrounding buildings — immediate context ──────────────────────────
    {"type": "box", "args": [9,  8, 14], "position": [-19, 4.0,  -6], "color": _B, "opacity": 0.85},
    {"type": "box", "args": [9,  6, 10], "position": [-19, 3.0,  +8], "color": _B, "opacity": 0.85},
    {"type": "box", "args": [7, 12, 10], "position": [+18, 6.0,  -7], "color": _B, "opacity": 0.85},
    {"type": "box", "args": [6, 17,  8], "position": [+18, 8.5,  +8], "color": _B, "opacity": 0.85},
    {"type": "box", "args": [14, 6,  8], "position": [ -3, 3.0, -22], "color": _B, "opacity": 0.85},
    {"type": "box", "args": [ 7, 5,  6], "position": [+9,  2.5, -21], "color": _B, "opacity": 0.85},
    {"type": "box", "args": [14, 9, 10], "position": [ -4, 4.5, +23], "color": _B, "opacity": 0.85},
    {"type": "box", "args": [ 8, 6,  8], "position": [ +9, 3.0, +24], "color": _B, "opacity": 0.85},
    # ── Background towers — DTLA skyline ──────────────────────────────────
    {"type": "box", "args": [5, 40, 5], "position": [-36, 20, -22], "color": _T, "opacity": 0.65},
    {"type": "box", "args": [5, 22, 5], "position": [-28, 11, -10], "color": _T, "opacity": 0.65},
    {"type": "box", "args": [5, 30, 5], "position": [-26, 15, +20], "color": _T, "opacity": 0.65},
    {"type": "box", "args": [4, 18, 4], "position": [+27, 9,  +20], "color": _T, "opacity": 0.65},
    {"type": "box", "args": [4, 14, 4], "position": [+32, 7,  -15], "color": _T, "opacity": 0.65},
    {"type": "box", "args": [4, 16, 4], "position": [-14, 8,  -28], "color": _T, "opacity": 0.65},
]

# Load park geometry from Rhino-derived JSON; fall back to empty list if missing.
_SITE_JSON = os.path.join(BASE_DIR, 'data', 'pershing_site_context.json')
try:
    with open(_SITE_JSON) as _f:
        _park_geo = json.load(_f).get("geometries", [])
    print(f"[OK] Loaded {len(_park_geo)} park geometry descriptors from {_SITE_JSON}")
except Exception as _e:
    print(f"[WARN] Could not load park geometry JSON ({_e}). Run logic/site_to_threejs.py to generate it.")
    _park_geo = []

PERSHING_SQUARE_CONTEXT = _park_geo + _DTLA_CONTEXT


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

    elif geo_type == "supertree":
        # Gardens by the Bay supertree: tapering trunk + crown disc + hanging fronds
        trunk_r_base = max(0.4, radius * 0.25)
        trunk_r_top  = max(0.15, radius * 0.08)
        trunk_h      = height * 0.80
        crown_r      = radius
        crown_h      = height * 0.12

        # Trunk — tapered as stacked cylinders
        taper_steps = 6
        for i in range(taper_steps):
            frac   = i / taper_steps
            seg_r  = trunk_r_base + frac * (trunk_r_top - trunk_r_base)
            seg_h  = trunk_h / taper_steps
            cyl(seg_r, seg_h, py=i * seg_h + seg_h / 2, color=primary)

        # Crown disc (living canopy)
        cyl(crown_r, crown_h, py=trunk_h + crown_h / 2, color=green_col)

        # Radial frond spokes hanging from crown edge
        spoke_count = 10
        frond_l = crown_r * 0.55
        frond_r = max(0.05, crown_r * 0.04)
        for i in range(spoke_count):
            a   = i * (2 * math.pi / spoke_count)
            sx  = (crown_r * 0.72) * math.sin(a)
            sz  = (crown_r * 0.72) * math.cos(a)
            cyl(frond_r, frond_l,
                px=sx, py=trunk_h - frond_l * 0.5, pz=sz, color=green_col)

        # Skybridge walkway at crown level (flat horizontal ring approximated by 16 boxes)
        bridge_r = crown_r * 0.6
        bridge_w = crown_r * 0.08
        seg = 16
        for i in range(seg):
            a  = i * (2 * math.pi / seg)
            bx = bridge_r * math.sin(a)
            bz = bridge_r * math.cos(a)
            box(bridge_w, bridge_w * 0.5, bridge_w,
                px=bx, py=trunk_h, pz=bz, color="#404038")

    elif geo_type == "kinetic_mast":
        # Schouwburgplein hydraulic lighting mast: tall pole + rotating boom + lamp head
        mast_r      = max(0.12, radius * 0.10)
        mast_h      = height
        boom_l      = radius * 1.4
        boom_r      = max(0.06, mast_r * 0.5)
        lamp_r      = max(0.18, radius * 0.22)
        lamp_h      = height * 0.10
        base_r      = radius * 0.35
        base_h      = height * 0.04
        pivot_h     = mast_h * 0.92   # where the boom pivots

        # Ground base plate
        cyl(base_r, base_h, color="#303030")

        # Vertical mast
        cyl(mast_r, mast_h, py=base_h + mast_h / 2, color=primary)

        # Counter-weight box below pivot
        cw_l = boom_l * 0.28
        box(cw_l * 0.4, cw_l * 0.4, cw_l * 0.4,
            px=-boom_l * 0.14, py=pivot_h - cw_l * 0.2, pz=0, color="#505050")

        # Horizontal boom arm extending from mast pivot
        box(boom_l, boom_r * 2, boom_r * 2,
            px=boom_l / 2, py=pivot_h, pz=0, color=primary)

        # Lamp head at tip of boom
        cyl(lamp_r, lamp_h,
            px=boom_l, py=pivot_h - lamp_h / 2, pz=0, color="#d0b840")

        # Second mast offset for cluster effect (halved size)
        if radius > 1.5:
            cyl(mast_r * 0.7, mast_h * 0.85,
                px=radius * 0.55, py=base_h + mast_h * 0.425, pz=radius * 0.3,
                color=primary)

    else:
        box(width, height, depth)

    # After generating the base shapes, apply the master position offset.
    # The AI is instructed to provide this based on the host site DNA.
    position_offset = spatial_params.get("position", {"x": 0, "y": 0, "z": 0})
    offset_x = position_offset.get("x", 0)
    offset_y = position_offset.get("y", 0) # This is the vertical offset in Three.js
    offset_z = position_offset.get("z", 0)

    # Apply the main position offset to all generated geometries
    for g in geos:
        g["position"][0] += offset_x
        g["position"][1] += offset_y
        g["position"][2] += offset_z

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

DIAGRAMS_DIR = os.path.join(BASE_DIR, 'archive', 'diagrams')
SVG_DIR = os.path.join(BASE_DIR, 'data', 'ParkSVG')

def _source_to_diagram_key(source_name: str) -> str:
    """'Parc de la Villette' → 'parc_de_la_villette'"""
    return re.sub(r'[^a-z0-9]+', '_', source_name.lower()).strip('_')

def load_spatial_blueprints(matches: list) -> dict:
    """
    For each ChromaDB match, look for a spatial blueprint JSON in priority order:
      1. archive/diagrams/{site}_rhino_parsed.json  (Rhino-native, most accurate)
      2. archive/diagrams/{site}_diagram.json        (vision-agent fallback)
    Returns {source_name: blueprint_dict} for every file that exists.
    """
    blueprints = {}
    seen = set()
    for m in matches:
        src = m['metadata'].get('source', '')
        if not src or src in seen:
            continue
        seen.add(src)
        key = _source_to_diagram_key(src)
        candidates = [
            os.path.join(DIAGRAMS_DIR, f"{key}_rhino_parsed.json"),
            os.path.join(DIAGRAMS_DIR, f"{key}_diagram.json"),
        ]
        for path in candidates:
            if os.path.exists(path):
                try:
                    with open(path, encoding='utf-8') as f:
                        blueprints[src] = json.load(f)
                    print(f"      -> Blueprint loaded: {os.path.basename(path)}")
                except Exception as e:
                    print(f"      -> Blueprint load failed ({path}): {e}")
                break  # stop at first found
    return blueprints

def format_blueprints_for_prompt(blueprints: dict) -> str:
    """Serialise loaded blueprints into a compact prompt section."""
    if not blueprints:
        return ""
    parts = []
    for src, bp in blueprints.items():
        zones = bp.get("zones", [])
        paths = bp.get("paths", [])
        rels  = bp.get("relationships", [])
        logic = bp.get("design_logic", "")
        zone_lines = "; ".join(f'{z["id"]}={z["label"]}' for z in zones[:8])
        path_lines = "; ".join(f'{p["id"]}={p["label"]}({p["type"]})' for p in paths[:6])
        rel_lines  = "\n  ".join(f'- {r}' for r in rels[:6])
        parts.append(
            f"BLUEPRINT: {src}\n"
            f"  Design Logic: {logic[:300]}\n"
            f"  Zones: {zone_lines}\n"
            f"  Paths: {path_lines}\n"
            f"  Relationships:\n  {rel_lines}"
        )
    return "\n\n".join(parts)


@app.get("/api/site-context")
async def get_site_context():
    """Returns the static Pershing Square site geometry for the Three.js base layer."""
    return {"geometries": PERSHING_SQUARE_CONTEXT}


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
    context_excerpts = "\n\n".join([
        f"Source: {m['metadata'].get('source', 'Unknown')}\nFragment: \"...{m['document']}...\""
        for m in matches
    ])

    # --- HOST SITE INJECTION ---
    # Load any spatial blueprint JSONs that correspond to matched sources
    blueprints     = load_spatial_blueprints(matches)
    blueprint_text = format_blueprints_for_prompt(blueprints)

    host_blueprint = {}
    host_blueprint_path = os.path.join(DIAGRAMS_DIR, "pershing_square_rhino_parsed.json")
    if os.path.exists(host_blueprint_path):
        try:
            with open(host_blueprint_path, encoding='utf-8') as f:
                host_blueprint = json.load(f)
            print("      -> Host site blueprint loaded: pershing_square_rhino_parsed.json")
        except Exception as e:
            print(f"      -> Host blueprint load failed: {e}")

    blueprint_section = (
        f"\n\n[ RETRIEVED SPATIAL BLUEPRINTS ]\n"
        f"The following diagram analyses were extracted from precedent site drawings.\n"
        f"Use the zones, paths, and relationships to ground the spatial_parameters output —\n"
        f"the generated geometry should inherit and reinterpret this spatial DNA.\n\n"
        f"{blueprint_text}"
    ) if blueprint_text else ""

    host_site_section = ""
    if host_blueprint:
        erasure_targets = host_blueprint.get("erasure_targets", [])
        erasure_text = ", ".join(erasure_targets) if erasure_targets else "None"
        host_site_section = (
            f"\n\n[ HOST SITE DNA - PERSHING SQUARE ]\n"
            f"The intervention will be placed on this existing site. You MUST use this data for placement.\n"
            f"Host Site Logic: {host_blueprint.get('design_logic', 'N/A')[:300]}\n"
            f"Erasure Targets: These are hostile elements to be overwritten or collided with: {erasure_text}\n"
        )

    system_prompt = (
        'You are an expert architect for the "Memory Machine" project. Your task is to translate a user\'s qualitative desire into a concrete architectural intervention for Pershing Square, Los Angeles. '
        'You will be given a user prompt, "memory fragments" from a review database, and (when available) spatial blueprint data extracted from precedent diagrams. '
        'Synthesize all of this into a single, valid JSON object with NO additional text or markdown. The JSON object must have three top-level keys: "name", "narrative", and "spatial_parameters".\n\n'
        f'USER PROMPT:\n"{prompt}"\n\n'
        f'RETRIEVED MEMORY FRAGMENTS:\n{context_excerpts}'
        f'{host_site_section}'
        f'{blueprint_section}\n\n'
        'INSTRUCTIONS:\n'
        '1.  **name**: Create a poetic name for the intervention (e.g., "Canopy of Whispers").\n'
        '2.  **narrative**: Write a short (2-paragraph) architectural narrative describing the space, its "witness marks" from the memory fragments, and how it collides with Pershing Square.'
        + (' Reference at least one specific zone, path, or relationship from the spatial blueprints to show the design logic is grounded in the precedent DNA.' if blueprint_text else '') + '\n'
        '3.  **spatial_parameters**: Generate precise parameters for a 3D model. Your geometry should be positioned to interact with the [ HOST SITE DNA ], specifically targeting elements listed in `erasure_targets`. This object MUST contain:\n'
        '    - "geometry_type": (string) Choose one: "pavilion_with_water", "shade_canopy", "water_garden", "acoustic_screen", "memory_tower", "landscape_mound", "amphitheater", "supertree", "kinetic_mast".\n'
        '    - "footprint_m": (object) with "width" and "depth" keys.\n'
        '    - "position": (object) with "x", "y", and "z" keys in Three.js units (1 unit = 5m) to place the object relative to the park center (0,0,0). Use the Erasure Targets to inform this position.\n'
        '    - "height_m": (float) The overall height in meters.\n'
        '    - "materials": (list of strings) e.g., ["concrete", "water", "steel", "glass", "wood", "vegetation", "stone"].\n'
        + ('    - "blueprint_sources": (list of strings) Name the precedent sites whose spatial DNA most influenced this design.\n' if blueprint_text else '')
        + '    - **Specific parameters based on geometry_type (add 2-3 relevant keys):**\n'
        '        - If "shade_canopy": "canopy_shape" (string, e.g., "flat_grid", "curved_fabric", "perforated_mesh"), "column_count" (integer), "shade_percentage" (float 0.0-1.0).\n'
        '        - If "water_garden": "pool_depth_m" (float), "water_feature_type" (string, e.g., "shallow_wading_pool", "bubbler_fountain", "trickling_stream"), "seating_elements" (list of strings, e.g., ["integrated_benches", "loose_stones"]).\n'
        '        - If "pavilion_with_water": "roof_type" (string, e.g., "flat", "pitched", "domed"), "wall_material" (string, e.g., "glass", "wood_slats", "perforated_metal"), "water_body_shape" (string, e.g., "rectangular", "organic", "circular").\n'
        '        - If "acoustic_screen": "screen_pattern" (string, e.g., "perforated", "slatted", "textured"), "screen_height_m" (float), "screen_length_m" (float), "orientation" (string, e.g., "linear", "curved").\n'
        '        - If "memory_tower": "levels" (integer), "facade_material" (string, e.g., "concrete_panels", "reclaimed_wood", "reflective_glass"), "observation_deck_height_m" (float), "base_shape" (string, e.g., "square", "circular").\n'
        '        - If "landscape_mound": "slope_angle_degrees" (float, 0-90), "vegetation_type" (string, e.g., "grass", "succulents", "wildflowers"), "path_material" (string, e.g., "gravel", "paving_stones", "dirt").\n'
        '        - If "amphitheater": "tiers" (integer, number of seating levels), "seating_material" (string), "stage_width_m" (float), "orientation" (string, e.g., "circular", "fan_shaped", "rectangular").\n'
        '        - If "supertree": "trunk_height_m" (float), "crown_radius_m" (float), "frond_count" (integer, 6-16), "canopy_material" (string, e.g., "living_plants", "solar_panels", "perforated_steel").\n'
        '        - If "kinetic_mast": "mast_height_m" (float), "boom_length_m" (float), "lamp_type" (string, e.g., "spotlight", "diffuse_ring", "programmable_rgb"), "mast_count" (integer, 1-4).\n'
        'Choose "amphitheater" whenever the memory fragments reference tiered seating, stepped plazas, auditoriums, bowl-shaped spaces, or performance venues.\n'
        'Choose "supertree" whenever fragments reference vertical gardens, living infrastructure, canopy structures, or Gardens by the Bay.\n'
        'Choose "kinetic_mast" whenever fragments reference hydraulic masts, actuated elements, movable lighting, or Schouwburgplein.\n\n'
        + ('When spatial blueprints are provided, let the zones and relationships guide the geometry_type choice and footprint. '
           'For example: a blueprint with a strong linear promenade and distributed attractors suggests "acoustic_screen" or multiple "shade_canopy" elements; '
           'a blueprint with a central anchor building and radiating paths suggests "pavilion_with_water" or "amphitheater".\n\n'
           if blueprint_text else '')
        + 'Respond with ONLY the raw JSON object.'
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
        "status":       "success",
        "name":         name,
        "narrative":    narrative,
        "sources":      sources,
        "geometries":   geometries,
        "site_context": PERSHING_SQUARE_CONTEXT,
        "diagram":      diagram,
    }

@app.post("/api/bake")
async def bake_to_rhino(payload: BakeRequest):
    """
    Saves the active intervention geometry to data/current_intervention.json
    and triggers bake_to_rhino.py to inject it into the live Rhino session.
    """
    data_dir = os.path.join(BASE_DIR, 'data')
    os.makedirs(data_dir, exist_ok=True)
    intervention_path = os.path.join(data_dir, 'current_intervention.json')

    try:
        with open(intervention_path, 'w', encoding='utf-8') as f:
            json.dump(payload.geometries, f, indent=2)
        print(f"[bake] Wrote {len(payload.geometries)} geometries to {intervention_path}")
    except Exception as e:
        return {"status": "error", "message": f"Could not write intervention file: {e}"}

    bake_script = os.path.join(BASE_DIR, 'logic', 'bake_to_rhino.py')
    try:
        process = subprocess.Popen(
            [sys.executable, bake_script],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        print(f"[bake] Launched bake_to_rhino.py (PID {process.pid}) for '{payload.name}'")
    except Exception as e:
        return {"status": "error", "message": f"Could not launch bake script: {e}"}

    return {"status": "success", "message": f"Bake initiated for '{payload.name}'. Check Rhino — layer MEM_GENERATED."}


def generate_comfyui_mesh(prompt: str, footprint: dict) -> dict:  # noqa: ARG001
    """
    ComfyUI bridge — structured to call localhost:8188 when ComfyUI is running.
    Currently returns a stub so the rest of the pipeline can be validated.

    When ComfyUI is operational, replace the stub block below with:
        workflow = build_comfyui_workflow(prompt, footprint)
        res = requests.post("http://localhost:8188/prompt", json={"prompt": workflow})
        glb_path = poll_comfyui_output(res.json()["prompt_id"])
        return {"glb_url": f"/static/generated/{os.path.basename(glb_path)}", "footprint": footprint}
    """
    # STUB — returns None so the frontend skips GLB loading gracefully
    return {"glb_url": None, "footprint": footprint}


@app.post("/api/generate-3d")
async def generate_3d_meshes(payload: Generate3DRequest):
    """
    Task 17: Receives 2D footprint data from the remix stack, queries ChromaDB
    for spatial context, prompts Gemini for an architectural description per layer,
    and calls generate_comfyui_mesh() for each footprint.

    Returns a list of mesh descriptors (glb_url + footprint) for the frontend
    to load via GLTFLoader and fit to the footprint bbox.
    """
    if not AI_ENABLED:
        return {"status": "error", "message": "AI core disabled — check server logs."}

    meshes = []
    narrative_parts = []

    for item in payload.footprints:
        query = f"{item.site} {item.layerId} {item.label} spatial design"
        try:
            results = collection.query(query_texts=[query], n_results=3, include=["documents", "metadatas"])
            context = "\n".join(results["documents"][0]) if results["documents"][0] else ""
        except Exception:
            context = ""

        fp = item.footprint
        dim_str = f"{fp.get('width', 0):.1f}m wide × {fp.get('depth', 0):.1f}m deep"

        prompt_text = f"""You are an architectural sculptor working on a park intervention.
Layer: {item.label} ({item.layerId}) from {item.site}
Footprint: {dim_str}, centered at world position ({fp.get('cx',0):.1f}, {fp.get('cz',0):.1f})
Relevant precedent memory:
{context}

Describe in 2-3 sentences the 3D massing, material quality, and spatial experience of this element
as it would appear in Pershing Square, DTLA. Be specific about height, form, and materiality."""

        try:
            model = genai.GenerativeModel("gemini-2.0-flash")
            response = model.generate_content(prompt_text)
            description = response.text.strip()
        except Exception as e:
            description = f"[AI description unavailable: {e}]"

        narrative_parts.append(f"**{item.label}** ({item.site}): {description}")

        mesh_result = generate_comfyui_mesh(description, fp)
        mesh_result["site"]    = item.site
        mesh_result["layerId"] = item.layerId
        mesh_result["label"]   = item.label
        mesh_result["description"] = description
        meshes.append(mesh_result)

    return {
        "status": "success",
        "message": f"AI descriptions generated for {len(meshes)} layers. ComfyUI mesh generation pending.",
        "meshes": meshes,
        "narrative": "\n\n".join(narrative_parts),
    }


@app.get("/diagrams", response_class=HTMLResponse)
async def diagram_viewer():
    """Serves the interactive SVG diagram viewer."""
    return FileResponse(os.path.join(BASE_DIR, "templates", "diagram_viewer.html"))


@app.get("/api/diagram-data")
async def list_diagrams():
    """Returns all sites that have an SVG in data/ParkSVG. JSON is optional."""
    if not os.path.isdir(SVG_DIR):
        return {"sites": []}
    svg_files = sorted(f for f in os.listdir(SVG_DIR) if f.lower().endswith(".svg"))
    # Build lowercase→actual-stem map for available JSONs
    json_map = {}
    if os.path.isdir(DIAGRAMS_DIR):
        for f in os.listdir(DIAGRAMS_DIR):
            if f.endswith("_rhino_parsed.json"):
                stem = f.replace("_rhino_parsed.json", "")
                json_map[stem.lower()] = stem
    sites = []
    for svg_f in svg_files:
        stem = os.path.splitext(svg_f)[0]
        sites.append({"site": stem, "has_json": stem.lower() in json_map})
    return {"sites": sites}


@app.get("/api/diagram-data/{site}")
async def get_diagram(site: str):
    """Returns SVG content and parsed JSON data for a single site."""
    svg_path = os.path.join(SVG_DIR, f"{site}.svg")
    if not os.path.exists(svg_path):
        return {"error": f"SVG for '{site}' not found in data/ParkSVG/"}
    with open(svg_path, encoding="utf-8", errors="replace") as f:
        svg_content = f.read()
    # Case-insensitive JSON lookup
    data = {"site": site, "zones": [], "paths": [], "relationships": [], "design_logic": ""}
    if os.path.isdir(DIAGRAMS_DIR):
        for f in os.listdir(DIAGRAMS_DIR):
            if f.endswith("_rhino_parsed.json") and f.replace("_rhino_parsed.json", "").lower() == site.lower():
                with open(os.path.join(DIAGRAMS_DIR, f), encoding="utf-8") as jf:
                    data = json.load(jf)
                break
    data["svg"] = svg_content
    return data


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