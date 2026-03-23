import requests
import json
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, 'data')
OUTPUT_PATH = os.path.join(DATA_DIR, 'pershing_osm.json')

def download_osm_context():
    # Bounding box around Pershing Square (South, West, North, East)
    bbox = "34.045,-118.256,34.051,-118.248"
    
    # Overpass Query Language: Get all buildings and their structural nodes
    query = f"""
    [out:json];
    (
      way["building"]({bbox});
    );
    (._;>;);
    out body;
    """
    
    url = "https://overpass-api.de/api/interpreter"
    print("🔎 Querying OpenStreetMap via Overpass API for Pershing Square context...")
    response = requests.post(url, data={'data': query})
    
    if response.status_code == 200:
        data = response.json()
        os.makedirs(DATA_DIR, exist_ok=True)
        with open(OUTPUT_PATH, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)
        print(f"✅ Saved {len(data.get('elements', []))} structural elements to {OUTPUT_PATH}")
    else:
        print(f"❌ Failed to fetch data. HTTP Status: {response.status_code}")

if __name__ == "__main__":
    download_osm_context()