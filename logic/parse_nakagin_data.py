import os
import csv

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TXT_PATH = os.path.join(BASE_DIR, 'data', 'nakagin.txt')
CSV_PATH = os.path.join(BASE_DIR, 'data', 'nakagin_massing.csv')
MD_PATH = os.path.join(BASE_DIR, 'data', 'nakagin_parsed_data.md')

def generate_nakagin_data():
    if os.path.exists(TXT_PATH):
        with open(TXT_PATH, 'r', encoding='utf-8') as f:
            text = f.read().lower()
    else:
        text = ""
        print(f"⚠️ Warning: {TXT_PATH} not found. Relying on default metabolism blueprint.")

    # Strict dimensional parameters based on the Nakagin Capsule Tower
    spatial_elements_dict = {
        'core': {'dims': [4.0, 4.0, 45.0], 'layer': '02_STRUCTURE', 'color': [150, 150, 150], 'default_instances': 2},
        'capsule': {'dims': [2.5, 4.0, 2.5], 'layer': '01_INTERIOR', 'color': [220, 220, 220], 'default_instances': 140},
        'window': {'dims': [1.3, 0.1, 1.3], 'layer': '04_ENCLOSURE', 'color': [173, 216, 230], 'default_instances': 140},
        'bridge': {'dims': [2.0, 6.0, 1.0], 'layer': '02_STRUCTURE', 'color': [100, 100, 100], 'default_instances': 4},
        'staircase': {'dims': [2.0, 3.0, 45.0], 'layer': '02_CIRCULATION', 'color': [120, 120, 120], 'default_instances': 2}
    }

    found_elements = []
    for element, props in spatial_elements_dict.items():
        count = text.count(element)
        # Prioritize historical hard constraints over text mentions
        instances = props['default_instances'] if count == 0 else max(count, props['default_instances'])
        if element in ['capsule', 'window']: instances = 140
        elif element in ['core', 'staircase']: instances = 2

        found_elements.append({
            'Element': element.capitalize(),
            'Instances': instances,
            'DimX': props['dims'][0],
            'DimY': props['dims'][1],
            'DimZ': props['dims'][2],
            'Layer': props['layer'],
            'ColorR': props['color'][0],
            'ColorG': props['color'][1],
            'ColorB': props['color'][2]
        })

    headers = ['Element', 'Instances', 'DimX', 'DimY', 'DimZ', 'Layer', 'ColorR', 'ColorG', 'ColorB']
    
    # 1. Write the CSV Blueprint
    os.makedirs(os.path.dirname(CSV_PATH), exist_ok=True)
    with open(CSV_PATH, 'w', newline='', encoding='utf-8') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=headers)
        writer.writeheader()
        writer.writerows(found_elements)
    print(f"✅ Generated Nakagin CSV blueprint at: {CSV_PATH}")

    # 2. Write the Markdown Table (The Chart)
    md_content = "# Nakagin Capsule Tower Spatial Data\n\n"
    md_content += f"| {' | '.join(headers)} |\n|{'|'.join(['---'] * len(headers))}|\n"
    for row in found_elements:
        md_content += f"| {' | '.join([str(row[h]) for h in headers])} |\n"
    with open(MD_PATH, 'w', encoding='utf-8') as mdfile:
        mdfile.write(md_content)
    print(f"✅ Generated Nakagin markdown chart at: {MD_PATH}")

if __name__ == "__main__":
    generate_nakagin_data()