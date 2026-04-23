import requests
import json
import random
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

def get_random_archive_prompt():
    """Reads a random line from the redacted spatial data archive to use as inspiration."""
    archive_path = os.path.join(BASE_DIR, 'data', 'redacted_spatial_data.txt')
    if os.path.exists(archive_path):
        with open(archive_path, 'r', encoding='utf-8') as f:
            # Filter out empty lines
            lines = [line.strip() for line in f if line.strip()]
            if lines:
                return random.choice(lines)
    
    # Fallback if the file isn't found
    return "A beautiful open space with lush greenery and classical architecture."

def test_generation():
    url = "http://127.0.0.1:8000/api/generate"
    
    # Automatically generate a prompt from the archives
    payload = { "prompt": get_random_archive_prompt() }

    print(f"🚀 Sending prompt to {url}...")
    print(f"📝 Prompt: '{payload['prompt']}'\n")
    print("⏳ Waiting for AI synthesis and geometry engine... (this may take a moment)\n")

    try:
        response = requests.post(url, json=payload)
        response.raise_for_status()
        
        data = response.json()
        print("✅ SUCCESS! Received response from server.\n")
        
        print("=== 📖 AI NARRATIVE ===")
        print(data.get("narrative", "No narrative found."))
        
        print("\n=== 🏗️ SPATIAL SEED (First 2 elements) ===")
        seed = data.get("spatial_seed", [])
        print(json.dumps(seed[:2], indent=2))
        if len(seed) > 2: print(f"... and {len(seed) - 2} more items.")
            
        print("\n=== 📦 3D GEOMETRIES (First 2 elements) ===")
        geos = data.get("geometries", [])
        print(json.dumps(geos[:2], indent=2))
        if len(geos) > 2: print(f"... and {len(geos) - 2} more items.")
            
    except requests.exceptions.RequestException as e:
        print(f"❌ ERROR: Failed to connect to the API. Is app.py running?\nDetails: {e}")

if __name__ == "__main__":
    test_generation()