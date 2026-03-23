import json
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, 'data')

RAW_DATA_FILE = os.path.join(DATA_DIR, 'memories.txt') 
OUTPUT_JSON = os.path.join(DATA_DIR, 'memory_manifest.json')

def compile_spatial_data():
    if not os.path.exists(RAW_DATA_FILE):
        print(f"Error: {RAW_DATA_FILE} not found. Create it first!")
        return

    compiled_library = []

    with open(RAW_DATA_FILE, 'r') as f:
        # Logic: Split your text file by a delimiter like '---'
        entries = f.read().split('---')
        
        for entry in entries:
            if not entry.strip(): continue
            
            # Simple parsing logic to extract name and sentiment
            lines = entry.strip().split('\n')
            name = lines[0].replace('Name:', '').strip()
            sentiment = 0.9 # Default high sentiment for "successful" spaces
            
            asset_entry = {
                "name": name,
                "sentiment_score": sentiment,
                "raw_text": entry.strip()
            }
            compiled_library.append(asset_entry)

    # Write the 'Manifest' that Rhino will read
    with open(OUTPUT_JSON, 'w') as f:
        json.dump(compiled_library, f, indent=4)
    
    print(f"Success: {len(compiled_library)} assets compiled to {OUTPUT_JSON}")

if __name__ == "__main__":
    compile_spatial_data()