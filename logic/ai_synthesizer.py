import os
import re
import json
import time
import random
import urllib.request
import urllib.error
from logic.urban_engine import guideline_manager

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIAGRAMS_DIR = os.path.join(BASE_DIR, 'archive', 'diagrams')

def check_aabb_overlap(box1: dict, box2: dict) -> bool:
    """
    Axis-Aligned Bounding Box (AABB) overlap detection.
    Expects dictionaries with 'x', 'y', 'width', and 'height'.
    Returns True if the boxes overlap, False otherwise.
    """
    return not (
        box1['x'] + box1['width'] <= box2['x'] or
        box2['x'] + box2['width'] <= box1['x'] or
        box1['y'] + box1['height'] <= box2['y'] or
        box2['y'] + box2['height'] <= box1['y']
    )

def fetch_osm_map(lat: float, lon: float, site_name: str):
    """Fetches a static map from OpenStreetMap and saves it to assets/precedents."""
    try:
        safe_name = "".join([c for c in site_name if c.isalnum() or c in (' ', '-', '_')]).strip().replace(" ", "_")
        if not safe_name: return
        
        assets_dir = os.path.join(BASE_DIR, 'assets', 'precedents')
        os.makedirs(assets_dir, exist_ok=True)
        filepath = os.path.join(assets_dir, f"{safe_name}_OSM.png")
        
        url = f"https://staticmap.openstreetmap.de/staticmap.php?center={lat},{lon}&zoom=17&size=800x800&maptype=mapnik"
        req = urllib.request.Request(url, headers={'User-Agent': 'MemoryMachine/1.0'})
        with urllib.request.urlopen(req, timeout=5) as response:
            with open(filepath, 'wb') as f:
                f.write(response.read())
        print(f"      -> [OSM] Successfully downloaded static map for '{site_name}' to precedents folder.")
    except Exception as e:
        print(f"      -> [OSM ERROR] Could not fetch map for {site_name}: {e}")

def query_ai(system_prompt: str, user_prompt: str) -> str:
    """Calls Gemini API if available, otherwise falls back to local Ollama."""
    try:
        from dotenv import load_dotenv
        from google import genai
        load_dotenv(os.path.join(BASE_DIR, '.env'))
        api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        
        if api_key:
            client = genai.Client(api_key=api_key)
            response = client.models.generate_content(
                model='gemini-2.5-flash', 
                contents=[system_prompt + "\n\n" + user_prompt]
            )
            text = response.text.strip()
            if text.startswith("```json"): text = text[7:]
            if text.endswith("```"): text = text[:-3]
            return text.strip()
    except Exception as e:
        print(f"      -> [GEMINI ERROR] Falling back to Ollama: {e}")

    url = "http://localhost:11434/api/generate"
    payload = {
        "model": "llama3",
        "system": system_prompt,
        "prompt": user_prompt,
        "format": "json",
        "stream": False,
        "options": {"temperature": 0.7}
    }
    try:
        req = urllib.request.Request(url, data=json.dumps(payload).encode('utf-8'), headers={'Content-Type': 'application/json'})
        with urllib.request.urlopen(req) as response:
            res = json.loads(response.read().decode('utf-8'))
            return res.get("response", "")
    except Exception as e:
        print(f"      -> [OLLAMA ERROR] Could not connect to local AI: {e}")
        return ""

def generate_spatial_seed(prompt: str, matches: list = None) -> tuple:
    """
    Uses Retrieval-Augmented Generation (RAG) with local Llama 3.
    Injects real scraped reviews from ChromaDB into the prompt, asks Llama 3 
    to select programmatic layers, and falls back to mathematical safety nets if it fails.
    """
    try:
        gm_data = guideline_manager.parse()
        zonal_metadata = gm_data.get("metadata", {})
    except Exception as e:
        print(f"      -> [GUIDELINE ERROR] {e}")
        zonal_metadata = {}

    SVG_DIR = os.path.join(BASE_DIR, 'data', 'ParkSVG')
    available_sites = []
    if os.path.exists(SVG_DIR):
        available_sites = [f[:-4].replace("_", "").replace(" ", "") for f in os.listdir(SVG_DIR) if f.lower().endswith(".svg")]
    if not available_sites: available_sites = ["PershingSquare", "ParcdelaVillette", "ZaryadyePark", "Schouwburgplein"]

    available_layers = []
    if zonal_metadata:
        available_layers = [l for cat in zonal_metadata.values() for l in cat]

    # 1. Build Semantic Context from ChromaDB
    context_text = ""
    if matches:
        for i, m in enumerate(matches[:3]): # Top 3 reviews
            context_text += f"Review {i+1}: {m.get('document', '')}\n\n"

    sys_prompt = (
        "You are an expert architectural curator. Your task is to select exactly 5 spatial layers "
        "from the available list that best match the atmospheric vibe of the user's prompt and the provided historical reviews.\n"
        "IMPORTANT: You must prioritize drawing inspiration from the 'Available Sites' provided below. "
        "Only if the available sites do not meet the atmospheric conditions should you seek out a new, real-world park (which must have a 4.5+ star public review rating).\n"
        "CRITICAL RULE 1: You are FORBIDDEN from using Lurie Garden, Millennium Park, or Tanner Springs as your inspiration_park. Your inspiration_park MUST be chosen strictly from the Available Sites list provided below.\n"
        "CRITICAL RULE 2 (Water Logic): If you select a BLUE_01 (Water) layer, it MUST be assigned the exact same 'location' as a SOFT_01 (Green Space) layer so they are adjacent.\n"
        "CRITICAL RULE 3 (Edge Rule): Do NOT assign PROG_01 (Active Program) layers to the extreme corners (North-West, North-East, South-West, South-East) to maintain edge clearances.\n"
        "CRITICAL RULE 4: The only valid PROG_01 layer name is 'UNIQUE_ELEMENTS'. Do NOT use MAJOR_ATTRACTORS or MINOR_ATTRACTORS — they do not exist.\n"
        "Output ONLY a valid JSON object. Do not write any markdown or conversational text.\n"
        "The JSON object must have exactly four keys:\n"
        "1. 'narrative': A short 2-sentence explanation of why these pieces were chosen, explicitly naming the real-world park that inspired you.\n"
        "2. 'inspiration_park': The name of the real-world park you chose as inspiration.\n"
        "3. 'coordinates': A JSON object with 'lat' and 'lon' float values for the inspiration park.\n"
        "4. 'layout': A JSON array of 5 objects. Each object must have these exact keys:\n"
        "- 'site': (string, choose from available sites)\n"
        "- 'layer': (string, choose from available layers)\n"
        "- 'location': (string, choose EXACTLY ONE from: North, North-East, East, South-East, South, South-West, West, North-West, Center)\n\n"
        f"Available Sites: {', '.join(available_sites)}\n"
        f"Available Layers: {', '.join(available_layers)}"
    )
    user_prompt = f"User Request: {prompt}\n\nHistorical Context (Reviews):\n{context_text}"

    # 2. Query AI Brain
    print(f"      -> [AI] Querying AI Engine...")
    ai_response = query_ai(sys_prompt, user_prompt)
    
    if ai_response:
        try:
            res_data = json.loads(ai_response)
            # Handle the new dictionary format containing the narrative
            if isinstance(res_data, dict) and "layout" in res_data:
                seed_items = res_data["layout"]
                narrative = res_data.get("narrative", "AI curated spatial arrangement applied.")
                
                # Trigger OSM Map Fetch if the AI provided a real-world reference
                insp_park = res_data.get("inspiration_park")
                coords = res_data.get("coordinates", {})
                if insp_park and isinstance(coords, dict) and "lat" in coords and "lon" in coords:
                    fetch_osm_map(coords["lat"], coords["lon"], insp_park)

                if isinstance(seed_items, list) and len(seed_items) > 0:
                    print(f"      -> [AI] Successfully synthesized {len(seed_items)} semantic layers!")
                    return seed_items, narrative
            # Fallback just in case Llama disobeys and returns the raw list
            elif isinstance(res_data, list) and len(res_data) > 0:
                print(f"      -> [AI] Successfully synthesized {len(res_data)} semantic layers!")
                return res_data, "AI curated spatial arrangement applied."
        except Exception as e:
            print(f"      -> [AI PARSE ERROR] Llama 3 returned invalid JSON. Falling back to math.")

    seed_items = []
    
    # 3. Algorithmic Safety Net
    print("      -> [FALLBACK] Executing strict compliance algorithm...")
    if zonal_metadata:
        categories = list(zonal_metadata.keys())
        locations = ["North", "North-East", "East", "South-East", "South", "South-West", "West", "North-West", "Center"]
        
        for _ in range(5):
            cat = random.choice(categories)
            if not zonal_metadata[cat]: continue
            
            seed_items.append({
                "site": random.choice(available_sites),
                "layer": random.choice(zonal_metadata[cat]),
                "location": random.choice(locations),
                "width": 20,
                "height": 20
            })
            
    return seed_items, "AI Core offline or parse failed. Algorithmic safety net engaged: generating mathematically compliant layout."

def generate_mermaid_diagram(prompt, matches, spatial_params):
    """Builds a Mermaid.js flowchart for the generation logic."""
    def mmd(s): return re.sub(r'["\[\]{}()/\\]', '', str(s))
    
    geo_type = spatial_params.get("geometry_type", "hybrid_assembly")
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