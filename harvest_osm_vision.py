import os
import time
from dotenv import load_dotenv
from google import genai
from PIL import Image

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ASSETS_DIR = os.path.join(BASE_DIR, "assets", "precedents")
DATA_DIR = os.path.join(BASE_DIR, "data")

load_dotenv(os.path.join(BASE_DIR, '.env'))
api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")

if not api_key:
    print("❌ ERROR: No Gemini API key found in .env")
    exit(1)

client = genai.Client(api_key=api_key)

prompt = """
You are an expert landscape architect and urban planner. Analyze this OpenStreetMap/Satellite image of the park.
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
            response = client.models.generate_content(model='gemini-2.5-flash', contents=[img, prompt])
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(response.text)
            print(f"   ✅ Saved spatial data to {site_name}_spatial_data.txt")
            time.sleep(2)  # Pause briefly to respect API rate limits
        except Exception as e:
            print(f"   ❌ Failed to analyze {site_name}: {e}")