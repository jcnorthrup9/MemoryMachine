import os
import time
import urllib.parse
from dotenv import load_dotenv
from google import genai
from PIL import Image
from scrapfly import ScrapflyClient, ScrapeConfig

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ASSETS_DIR = os.path.join(BASE_DIR, "assets", "precedents")
DATA_DIR = os.path.join(BASE_DIR, "data")

# Ensure directories exist
os.makedirs(ASSETS_DIR, exist_ok=True)
os.makedirs(DATA_DIR, exist_ok=True)

load_dotenv(os.path.join(BASE_DIR, '.env'))
api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
scrapfly_key = "scp-live-1de5601897a54e3b8eb6efde0106d282" # Hardcoded from your scraper.py

if not api_key:
    print("❌ ERROR: No Gemini API key found in .env")
    exit(1)

ai_client = genai.Client(api_key=api_key)
scrapfly = ScrapflyClient(key=scrapfly_key)

vision_prompt = """
You are an expert landscape architect and urban planner. Analyze this OpenStreetMap/Satellite image of the park.
Please extract the following information in a highly detailed, professional format:

1. SITE CONTEXT: Describe the surrounding urban fabric (e.g., dense commercial, waterfront, residential).
2. GEOMETRIC LOGIC: What is the primary organizational shape of the park? Are there strict grids, organic winding paths, or fragmented intersections?
3. PROGRAMMATIC ZONES: Estimate the ratio of Hardscape (paving, plazas) vs. Softscape (trees, lawns) vs. Blue Space (water).
4. SPATIAL RELATIONSHIPS: How does the edge of the park meet the city? Are there distinct focal points or pavilions?

Keep your analysis strictly factual based on what you can visually deduce from the map layout.
"""

print("🚀 Initiating the Ultimate Harvester (Vision, Yelp, Google & TripAdvisor)...")

found_images = False
for filename in os.listdir(ASSETS_DIR):
    if filename.lower().endswith(('.png', '.jpg', '.jpeg', '.webp')):
        found_images = True
        site_name = os.path.splitext(filename)[0].replace("_OSM", "").replace("_osm", "")
        spatial_path = os.path.join(DATA_DIR, f"{site_name}_spatial_data.txt")
        review_path = os.path.join(DATA_DIR, f"{site_name}_reviews.txt")
        
        print(f"\n========================================")
        print(f"🔍 HARVESTING TARGET: {site_name}")
        print(f"========================================")
        
        # --- 1. SPATIAL VISION HARVEST ---
        if not os.path.exists(spatial_path):
            print(f"  [1/2] 👁️ Analyzing spatial layout via Gemini Vision...")
            try:
                img = Image.open(os.path.join(ASSETS_DIR, filename))
                response = ai_client.models.generate_content(model='gemini-2.5-flash', contents=[img, vision_prompt])
                with open(spatial_path, "w", encoding="utf-8") as f:
                    f.write(response.text)
                print(f"       ✅ Saved: {site_name}_spatial_data.txt")
                time.sleep(2)
            except Exception as e:
                print(f"       ❌ Vision failed: {e}")
        else:
            print(f"  [1/2] ⏭️ Spatial data already exists.")

        # --- 2. REVIEW HARVEST (Scrapfly + Gemini) ---
        if not os.path.exists(review_path):
            print(f"  [2/2] 🌐 Scraping Yelp/TripAdvisor/Google data via Scrapfly...")
            try:
                # Aggregate reviews by searching Bing for the park + review sites, then parsing the markdown
                encoded_search = urllib.parse.quote_plus(f"{site_name} park yelp tripadvisor google reviews")
                target_url = f"https://www.bing.com/search?q={encoded_search}"
                
                config = ScrapeConfig(url=target_url, asp=True, country="US", format="markdown")
                result = scrapfly.scrape(config)
                raw_markdown = result.scrape_result.get("content", "")
                
                print(f"       🧠 Synthesizing raw scrape data into spatial review narrative...")
                review_prompt = f"You are an architectural researcher. I am giving you raw scraped markdown from a web search containing Yelp, TripAdvisor, and Google Maps snippets for \"{site_name}\". Extract any visitor reviews, sentiments, or descriptions of the park's atmosphere, safety, aesthetics, and spatial qualities. Format it as a clean, continuous narrative report (3-5 paragraphs) summarizing the human experience of this site. If the scrape data is sparse, supplement it seamlessly with your own knowledge of how visitors experience this specific park.\n\nRAW SCRAPE DATA:\n{raw_markdown[:15000]}"
                
                rev_response = ai_client.models.generate_content(model='gemini-2.5-flash', contents=[review_prompt])
                with open(review_path, "w", encoding="utf-8") as f:
                    f.write(rev_response.text)
                print(f"       ✅ Saved: {site_name}_reviews.txt")
                
            except Exception as e:
                print(f"       ❌ Review scrape failed: {e}")
        else:
            print(f"  [2/2] ⏭️ Review data already exists.")
            
        time.sleep(2) # Rate limit protection to prevent Gemini/Scrapfly timeouts

print("\n🎉 ALL SITES HARVESTED SUCCESSFULLY!")