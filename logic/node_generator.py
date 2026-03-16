import os
import csv
import json

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, 'data')

def generate_node_json():
    csv_path = os.path.join(DATA_DIR, 'bottega_massing.csv')
    json_path = os.path.join(DATA_DIR, 'target_node.json')

    if not os.path.exists(csv_path):
        print(f"❌ Error: Could not find {csv_path}")
        return

    elements = []
    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            elements.append({
                "element": row['Element'],
                "instances": int(row['Instances']),
                "dimensions": {
                    "x": float(row['DimX']),
                    "y": float(row['DimY']),
                    "z": float(row['DimZ'])
                },
                "layer": row['Layer']
            })

    node_data = {
        "node_id": "BOTTEGA_LOUIE",
        "iteration": "DTLA_RECONSTRUCTION_V1",
        "geo_lock": {"lat": 34.0470, "lon": -118.2568}, 
        "dimensions": {"unit": "feet", "length": 150, "width": 100, "height": 20},
        "chromatic_palette": [
            {"material": "marble_floor", "hex": "#f5f5f5"},
            {"material": "gold_accents", "hex": "#d4af37"},
            {"material": "white_wall", "hex": "#ffffff"}
        ],
        "spatial_logic": elements
    }

    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(node_data, f, indent=2)

    print(f"✅ Generated new target node JSON.")
    print(f"✅ Saved to: {json_path}")

if __name__ == "__main__":
    generate_node_json()