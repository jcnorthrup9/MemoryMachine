import os
import csv

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, 'data')

def generate_architectural_massing_data():
    input_path = os.path.join(DATA_DIR, 'redacted_spatial_data.txt')
    output_path = os.path.join(DATA_DIR, 'bottega_massing.csv')

    if not os.path.exists(input_path):
        print(f"❌ Error: Could not find {input_path}")
        return

    with open(input_path, 'r', encoding='utf-8') as f:
        text = f.read().lower()

    # Dictionary of spatial elements to search for
    # Values represent basic starting dimensions (x, y, z) for our proxy massing in feet/meters
    # We classify them as 'singular' (only one exists, frequency increases size) 
    # or 'plural' (multiple exist, frequency increases quantity)
    # We also assign RGB colors derived from the qualitative review data (e.g., white walls, pink macarons, gold accents)
    spatial_elements = {
        'kitchen': {'dims': [30, 20, 12], 'layer': '01_INTERIOR', 'type': 'singular', 'color': [200, 200, 200]},
        'bar': {'dims': [20, 5, 4], 'layer': '01_INTERIOR', 'type': 'singular', 'color': [139, 69, 19]},
        'patio': {'dims': [20, 20, 1], 'layer': '02_EXTERIOR', 'type': 'singular', 'color': [150, 150, 150]},
        'bathroom': {'dims': [10, 10, 10], 'layer': '01_INTERIOR', 'type': 'singular', 'color': [255, 250, 240]},
        'display': {'dims': [15, 4, 5], 'layer': '03_FIXTURES', 'type': 'plural', 'color': [255, 182, 193]}, # Pink for macarons
        'seating': {'dims': [5, 5, 3], 'layer': '03_FIXTURES', 'type': 'plural', 'color': [160, 82, 45]},
        'window': {'dims': [1, 10, 15], 'layer': '04_ENCLOSURE', 'type': 'plural', 'color': [173, 216, 230]},
        'ceiling': {'dims': [50, 50, 2], 'layer': '04_ENCLOSURE', 'type': 'singular', 'color': [255, 255, 255]},
        'marble': {'dims': [50, 50, 1], 'layer': '05_FINISHES', 'type': 'singular', 'color': [245, 245, 245]},
        'oven': {'dims': [8, 8, 8], 'layer': '01_INTERIOR', 'type': 'singular', 'color': [178, 34, 34]}, # Wood-fired brick
        'patisserie': {'dims': [20, 5, 4], 'layer': '03_FIXTURES', 'type': 'singular', 'color': [255, 228, 225]},
        'flower': {'dims': [2, 2, 3], 'layer': '03_FIXTURES', 'type': 'plural', 'color': [255, 20, 147]}, # Bright pink
        'wall': {'dims': [2, 20, 20], 'layer': '04_ENCLOSURE', 'type': 'plural', 'color': [255, 255, 255]}, # White walls
        'gold': {'dims': [1, 1, 1], 'layer': '05_FINISHES', 'type': 'plural', 'color': [212, 175, 55]}, # Gold
        'door': {'dims': [4, 1, 10], 'layer': '04_ENCLOSURE', 'type': 'plural', 'color': [139, 69, 19]},
        'beam': {'dims': [1, 50, 1], 'layer': '04_ENCLOSURE', 'type': 'plural', 'color': [200, 200, 200]}
    }

    found_elements = []
    for element, props in spatial_elements.items():
        count = text.count(element)
        if count > 0:
            instances = count if props['type'] == 'plural' else 1
            
            # Apply a scale multiplier based on the number of mentions for singular items
            # Reduced the multiplier slightly to account for the larger dataset
            scale = 1.0 + (count * 0.02) if props['type'] == 'singular' else 1.0
            
            found_elements.append({
                'Element': element.capitalize(),
                'Instances': instances,
                'DimX': round(props['dims'][0] * scale, 2),
                'DimY': round(props['dims'][1] * scale, 2),
                'DimZ': props['dims'][2], # Height usually stays standard
                'Layer': props['layer'],
                'ColorR': props['color'][0],
                'ColorG': props['color'][1],
                'ColorB': props['color'][2]
            })

    with open(output_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=['Element', 'Instances', 'DimX', 'DimY', 'DimZ', 'Layer', 'ColorR', 'ColorG', 'ColorB'])
        writer.writeheader()
        writer.writerows(found_elements)

    print(f"✅ Generated massing logic from reviews.")
    print(f"✅ Saved blueprint to: {output_path}")

if __name__ == "__main__":
    generate_architectural_massing_data()