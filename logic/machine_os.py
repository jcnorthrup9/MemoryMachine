import os
import subprocess
import time
import json
import sys
import re

try:
    from dotenv import load_dotenv
    import google.generativeai as genai
except ImportError:
    genai = None

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOGIC_DIR = os.path.join(BASE_DIR, 'logic')
DATA_DIR = os.path.join(BASE_DIR, 'data')
MANIFEST_PATH = os.path.join(DATA_DIR, 'memory_manifest.json')

def print_header():
    print(r"""
     __  __                               __  __         _    _         
    |  \/  |___ _ __  ___ _ _ _  _       |  \/  |__ _ __| |_ (_)_ _  ___
    | |\/| / -_) '  \/ _ \ '_| || |      | |\/| / _` / _| ' \| | ' \/ -_)
    |_|  |_\___|_|_|_\___/_|  \_, |      |_|  |_\__,_\__|_||_|_|_||_\___|
                              |__/                                       
    """)
    print("SYSTEM ONLINE // WAITING FOR DIRECTIVE...\n")

def run_subprocess(command, description):
    print(f"\n>>> {description}")
    time.sleep(1) # Dramatic pause for terminal effect
    try:
        subprocess.run(command, check=True)
    except subprocess.CalledProcessError as e:
        print(f"❌ ERROR IN PIPELINE: {e}")
        exit(1)

def update_manifest(target_name, target_slug):
    # This injects the new asset into the master manifest so Rhino sees it immediately
    if os.path.exists(MANIFEST_PATH):
        with open(MANIFEST_PATH, 'r') as f:
            manifest = json.load(f)
    else:
        manifest = []
        
    # Add the new node to the manifest
    manifest.append({
        "name": target_name,
        "sentiment_score": 0.85, # We will eventually make the AI calculate this dynamically
        "raw_text": f"Scraped data for {target_name}. Awaiting spatial reconstruction.",
        "node_id": target_slug.upper()
    })
    
    with open(MANIFEST_PATH, 'w') as f:
        json.dump(manifest, f, indent=4)
    print(f"\n✅ SYSTEM UPDATED: '{target_name}' injected into memory_manifest.json")

def main():
    print_header()
    
    # Step 1: The Prompt
    user_input = input("Enter directive (e.g., 'Generate spatial data for Zaryadye Park in Moscow'): ")
    
    target_name, location = user_input, ""
    
    if genai:
        load_dotenv(os.path.join(BASE_DIR, '.env'))
        api_key = os.environ.get("GEMINI_API_KEY")
        if api_key:
            print(f"\n>>> [0/5] INTERPRETING NATURAL LANGUAGE DIRECTIVE...")
            try:
                genai.configure(api_key=api_key)
                model = genai.GenerativeModel('gemini-2.5-flash')
                sys_prompt = f"Extract the architectural target (building, park, plaza, etc.) and location from the user's prompt. Return ONLY a valid JSON object in this format: {{\"target\": \"Name\", \"location\": \"City, Country/State\"}}. Prompt: '{user_input}'"
                response = model.generate_content(sys_prompt)
                clean_json = response.text.strip().replace("```json", "").replace("```", "")
                data = json.loads(clean_json)
                target_name = data.get("target", user_input)
                location = data.get("location", "")
                print(f"    Target Locked: {target_name} | Location: {location}")
            except Exception as e:
                print(f"    [AI Parsing Failed: {e}] Falling back to exact input.")
    
    target_slug = re.sub(r'[^a-z0-9]+', '_', target_name.lower()).strip('_')
    
    # Step 2: Data Harvest (Using Free Wikipedia/DDGS Scraper)
    run_subprocess(
        [sys.executable, os.path.join(LOGIC_DIR, "free_scraper.py"), "--target", target_name, "--location", location],
        f"[1/5] INITIATING DATA HARVEST: Scraping spatial data for {target_name} using Wikipedia & DuckDuckGo..."
    )
    
    # Step 3: Spatial Parsing (Universal Extractor)
    run_subprocess(
        [sys.executable, os.path.join(LOGIC_DIR, "spatial_extractor.py"), "--target", target_name, "--slug", target_slug],
        f"[2/5] PARSING SPATIAL & ATMOSPHERIC DATA: Extracting key elements for {target_name}..."
    )
    
    # Step 4: Logic Generation (Universal Mapper)
    run_subprocess(
        [sys.executable, os.path.join(LOGIC_DIR, "spatial_mapper.py"), "--slug", target_slug],
        f"[3/5] GENERATING MASSING BLUEPRINT: Translating data into spatial logic..."
    )
    
    # Step 5: Update the Manifest for Rhino
    update_manifest(target_name, target_slug)
    
    print(f"\n==================================================================")
    print(f"✅ PIPELINE COMPLETE: Open Rhino and run 'intervention_engine.py'")

if __name__ == "__main__":
    main()