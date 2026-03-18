import os
import csv

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, 'data')

def generate_architectural_massing_data():
    input_path = os.path.join(DATA_DIR, 'redacted_ot_johnson_data.txt')
    output_path = os.path.join(DATA_DIR, 'ot_johnson_massing.csv')

    if not os.path.exists(input_path):
        print(f"❌ Error: Could not find {input_path}")
        return

    with open(input_path, 'r', encoding='utf-8') as f:
        text = f.read().lower()

    spatial_elements = {
        'lobby': {'dims': [40, 30, 15], 'layer': '01_INTERIOR', 'type': 'singular', 'color': [240, 235, 225]},
        'elevator': {'dims': [8, 8, 85], 'layer': '01_INTERIOR', 'type': 'singular', 'color': [100, 100, 100]},
        'staircase': {'dims': [12, 20, 85], 'layer': '01_INTERIOR', 'type': 'singular', 'color': [139, 69, 19]},
        'office': {'dims': [20, 20, 10], 'layer': '01_INTERIOR', 'type': 'plural', 'color': [255, 250, 240]},
        'corridor': {'dims': [10, 50, 10], 'layer': '01_INTERIOR', 'type': 'plural', 'color': [220, 220, 220]},
        'desk': {'dims': [5, 3, 3], 'layer': '03_FIXTURES', 'type': 'plural', 'color': [139, 69, 19]},
        'window': {'dims': [4, 1, 8], 'layer': '04_ENCLOSURE', 'type': 'plural', 'color': [173, 216, 230]},
        'ceiling': {'dims': [50, 50, 1], 'layer': '04_ENCLOSURE', 'type': 'singular', 'color': [255, 255, 255]},
        'marble': {'dims': [20, 20, 1], 'layer': '05_FINISHES', 'type': 'plural', 'color': [245, 245, 245]},
        'facade': {'dims': [100, 2, 85], 'layer': '04_ENCLOSURE', 'type': 'singular', 'color': [180, 150, 120]},
        'brick': {'dims': [100, 2, 85], 'layer': '05_FINISHES', 'type': 'singular', 'color': [178, 34, 34]},
        'iron': {'dims': [2, 2, 15], 'layer': '04_ENCLOSURE', 'type': 'plural', 'color': [50, 50, 50]},
        'wall': {'dims': [2, 20, 10], 'layer': '04_ENCLOSURE', 'type': 'plural', 'color': [240, 240, 240]},
        'door': {'dims': [4, 1, 9], 'layer': '04_ENCLOSURE', 'type': 'plural', 'color': [101, 67, 33]},
        'cornice': {'dims': [100, 3, 3], 'layer': '04_ENCLOSURE', 'type': 'singular', 'color': [150, 140, 130]}
    }

    found_elements = []
    for element, props in spatial_elements.items():
        count = text.count(element)
        if count > 0:
            instances = count if props['type'] == 'plural' else 1
            scale = 1.0 + (count * 0.02) if props['type'] == 'singular' else 1.0
            
            found_elements.append({
                'Element': element.capitalize(),
                'Instances': instances,
                'DimX': round(props['dims'][0] * scale, 2),
                'DimY': round(props['dims'][1] * scale, 2),
                'DimZ': props['dims'][2],
                'Layer': props['layer'],
                'ColorR': props['color'][0],
                'ColorG': props['color'][1],
                'ColorB': props['color'][2]
            })

    with open(output_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=['Element', 'Instances', 'DimX', 'DimY', 'DimZ', 'Layer', 'ColorR', 'ColorG', 'ColorB'])
        writer.writeheader()
        writer.writerows(found_elements)

    print(f"✅ Generated massing logic from O.T. Johnson data.")
    print(f"✅ Saved blueprint to: {output_path}")

if __name__ == "__main__":
    generate_architectural_massing_data()