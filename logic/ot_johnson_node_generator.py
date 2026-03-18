import os
import csv
import json
import random

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, 'data')

def generate_node_json():
    csv_path = os.path.join(DATA_DIR, 'ot_johnson_massing.csv')
    json_path = os.path.join(DATA_DIR, 'target_node_ot_johnson.json')
    txt_path = os.path.join(DATA_DIR, 'redacted_ot_johnson_data.txt')

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

    # 1. Pull in the historical anecdotes to act as memory fragments
    anecdotes = []
    if os.path.exists(txt_path):
        with open(txt_path, 'r', encoding='utf-8') as f:
            fragments = [line.strip() for line in f.read().split('\n\n') if line.strip()]
            # Pick 4 random fragments to simulate fractured memory recall
            anecdotes = random.sample(fragments, min(4, len(fragments)))

    node_data = {
        "node_id": "OT_JOHNSON_BLDG",
        "iteration": "DTLA_RECONSTRUCTION_V2",
        "geo_lock": {"lat": 34.0496, "lon": -118.2491}, 
        "dimensions": {"unit": "feet", "length": 100, "width": 80, "height": 85},
        "narrative_fragments": anecdotes,
        "chromatic_palette": [
            {"material": "glazed_brick", "hex": "#b22222"},
            {"material": "iron_columns", "hex": "#323232"},
            {"material": "marble_lobby", "hex": "#f5f5f5"}
        ],
        "spatial_logic": elements
    }

    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(node_data, f, indent=2)

    print(f"✅ Generated new target node JSON.")
    print(f"✅ Saved to: {json_path}")

if __name__ == "__main__":
    generate_node_json()