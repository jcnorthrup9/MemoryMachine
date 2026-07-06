import os
import time
from dotenv import load_dotenv
from google import genai
from PIL import Image

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # repo root (this file lives one level down)
ASSETS_DIR = os.path.join(BASE_DIR, "assets", "precedents")
DATA_DIR = os.path.join(BASE_DIR, "data")

load_dotenv(os.path.join(BASE_DIR, '.env'))
api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")

if not api_key:
    print("❌ ERROR: No Gemini API key found in .env")
    exit(1)

client = genai.Client(api_key=api_key)

SITE_LOCATIONS = {
    "pershingsquare": "Downtown Los Angeles, CA",
    "schouwburgplein": "Rotterdam, Netherlands",
    "grandparkla": "Los Angeles, CA",
    "grandpark": "Los Angeles, CA",
    "tannerspringspark": "Portland, Oregon",
    "tannersprings": "Portland, Oregon",
    "gardensbythebay": "Singapore",
    "superkilen": "Copenhagen, Denmark",
    "paleypark": "New York City, NY",
    "klydewarrenpark": "Dallas, Texas",
    "millenniumpark": "Chicago, Illinois",
    "parcdelavillette": "Paris, France",
    "zaryadyepark": "Moscow, Russia",
    "bottegalouie": "Downtown Los Angeles, CA",
    "nakagincapsuletower": "Tokyo, Japan",
    "otjohnsonbuilding": "Downtown Los Angeles, CA",
    "piazzadelcampo": "Siena, Italy",
    "thehighline": "New York City, NY",
    "federationsquare": "Melbourne, Australia",
    "pioneercourthousesquare": "Portland, Oregon"
}

def get_prompt(site_name):
    normalized_name = site_name.lower().replace("_", "").replace(" ", "")
    location = SITE_LOCATIONS.get(normalized_name, "its respective city")
    return f"""
You are an expert landscape architect and urban planner. Analyze this OpenStreetMap/Satellite image of {site_name} located in {location}.
Please extract the following information in a highly detailed, professional format:

1. SITE CONTEXT: Describe the surrounding urban fabric (e.g., dense commercial, waterfront, residential).
2. GEOMETRIC LOGIC: What is the primary organizational shape of the park? Are there strict grids, organic winding paths, or fragmented intersections?
3. PROGRAMMATIC ZONES: Estimate the ratio of Hardscape (paving, plazas) vs. Softscape (trees, lawns) vs. Blue Space (water).
4. SPATIAL RELATIONSHIPS: How does the edge of the park meet the city? Are there distinct focal points or pavilions?

Keep your analysis strictly factual based on what you can visually deduce from the map layout.
"""

print("👁️ Initiating Gemini Vision OSM Harvester...")

for filename in os.listdir(ASSETS_DIR):
    if filename.endswith("_OSM.png"):
        site_name = filename.replace("_OSM.png", "")
        output_path = os.path.join(DATA_DIR, f"{site_name}_spatial_data.txt")
        
        if os.path.exists(output_path):
            print(f"⏭️  Skipping {site_name} (Data already harvested)")
            continue
            
        image_path = os.path.join(ASSETS_DIR, filename)
        print(f"🔍 Analyzing {site_name}...")
        
        try:
            img = Image.open(image_path)
            response = client.models.generate_content(model='gemini-2.5-flash', contents=[img, get_prompt(site_name)])
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(response.text)
            print(f"   ✅ Saved spatial data to {site_name}_spatial_data.txt")
            time.sleep(2)  # Pause briefly to respect API rate limits
        except Exception as e:
            print(f"   ❌ Failed to analyze {site_name}: {e}")