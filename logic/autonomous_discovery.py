import os
import sys
import json
import time
import subprocess
import re

try:
    from ddgs import DDGS
except ImportError:
    from duckduckgo_search import DDGS

try:
    from dotenv import load_dotenv
    import google.generativeai as genai
except ImportError:
    genai = None

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOGIC_DIR = os.path.join(BASE_DIR, 'logic')
DATA_DIR = os.path.join(BASE_DIR, 'data')
MANIFEST_PATH = os.path.join(DATA_DIR, 'memory_manifest.json')

def run_subprocess(command, description):
    print(f"\n>>> {description}")
    time.sleep(1)
    try:
        subprocess.run(command, check=True)
    except subprocess.CalledProcessError as e:
        print(f"❌ ERROR IN PIPELINE: {e}")

def main():
    print("=====================================================")
    print(" 🛰️  MEMORY MACHINE // AUTONOMOUS DISCOVERY PROTOCOL")
    print("=====================================================\n")
    
    query = input("Enter search parameters (e.g., 'Highly rated public spaces in Arizona'): ")
    
    print(f"\n🔎 Scanning the open web for '{query}'...")
    snippets = []
    try:
        import warnings
        warnings.filterwarnings("ignore")
        with DDGS() as ddgs:
            results = list(ddgs.text(query + " architecture public space reviews", max_results=15))
            for res in results:
                snippets.append(res.get('title', '') + " - " + res.get('body', ''))
    except Exception as e:
        print(f"❌ Search Error: {e}")
        return
        
    if not snippets:
        print("❌ No data found.")
        return

    print("🧠 AI is analyzing search results to identify optimal targets...")
    load_dotenv(os.path.join(BASE_DIR, '.env'))
    api_key = os.environ.get("GEMINI_API_KEY")
    
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel('gemini-2.5-flash')
    prompt = f"Analyze these search results. Extract up to 5 specific, highly-rated public parks, plazas, or buildings. Return ONLY a valid JSON list of objects with 'target' (the name of the space) and 'location' (city/state/country) keys.\n\nData:\n{snippets}"
    
    response = model.generate_content(prompt)
    clean_json = response.text.strip().replace("```json", "").replace("```", "")
    
    try:
        spaces = json.loads(clean_json)
    except Exception as e:
        print(f"❌ AI failed to format the response: {e}")
        return
        
    print("\n✨ DISCOVERED SPACES:")
    for idx, space in enumerate(spaces):
        print(f"  [{idx+1}] {space['target']} ({space['location']})")
        
    choice = input("\nSelect a number to ingest, or type 'ALL' to harvest the entire list: ").strip().lower()
    
    targets_to_process = spaces if choice == 'all' else [spaces[int(choice)-1]] if choice.isdigit() and 1 <= int(choice) <= len(spaces) else []
        
    for t in targets_to_process:
        t_name = t['target']
        t_loc = t['location']
        print(f"\n=====================================================")
        print(f" 🚀 PROCESSING: {t_name}")
        print(f"=====================================================")
        
        target_slug = re.sub(r'[^a-z0-9]+', '_', t_name.lower()).strip('_')
        
        # Trigger the entirely free pipeline sequence
        run_subprocess([sys.executable, os.path.join(LOGIC_DIR, "free_scraper.py"), "--target", t_name, "--location", t_loc], f"Scraping spatial data...")
        run_subprocess([sys.executable, os.path.join(LOGIC_DIR, "spatial_extractor.py"), "--target", t_name, "--slug", target_slug], f"Extracting spatial fragments...")
        run_subprocess([sys.executable, os.path.join(LOGIC_DIR, "spatial_mapper.py"), "--slug", target_slug], f"Generating massing blueprint...")
        run_subprocess([sys.executable, os.path.join(LOGIC_DIR, "machine_os.py")], f"Updating Manifest (Handled by OS)...") # Quick hack to use OS manifest updater if needed, but we can rely on our standalone scripts.

if __name__ == "__main__":
    main()