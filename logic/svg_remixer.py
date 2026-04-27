import os
import re
import json
import random
import xml.etree.ElementTree as ET

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SVG_IN_DIR = os.path.join(BASE_DIR, "data", "ParkSVG", "ParkSVGcurves")
SVG_OUT_DIR = os.path.join(BASE_DIR, "archive", "diagrams", "remixed_svgs")
GUIDELINES_PATH = os.path.join(BASE_DIR, "urban_design_guidelines.md")

# Map typologies to distinct hex colors for the Blender parser to pick up
TYPOLOGY_COLORS = {
    "walkway": "#A9A9A9",          # Dark Gray
    "shade_canopy": "#228B22",     # Forest Green
    "water_feature": "#0096FF",    # Bright Blue
    "playground": "#FFD700",       # Gold
    "landscape_mound": "#8B4513",  # Saddle Brown
    "buffer_zone": "#98FB98"       # Pale Green
}

def load_guidelines():
    """Extracts the JSON ruleset from the APA markdown file."""
    if not os.path.exists(GUIDELINES_PATH):
        return {}
    with open(GUIDELINES_PATH, 'r', encoding='utf-8') as f:
        content = f.read()
    match = re.search(r'```json\n(.*?)\n```', content, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass
    return {}

def remix_svg(source_path, iteration, guidelines_data):
    tree = ET.parse(source_path)
    root = tree.getroot()
    
    # Preserve standard SVG namespaces
    ns = 'http://www.w3.org/2000/svg'
    ET.register_namespace('', ns)
    
    primitives = guidelines_data.get("primitives", list(TYPOLOGY_COLORS.keys()))
    constraints = guidelines_data.get("guidelines", {})
    
    # Enforce APA Constraint: 40% Shade Coverage
    shade_target = constraints.get("shade_coverage_target_pct", 40) / 100.0
    
    # Gather all geometric shapes in the SVG
    shapes = []
    for tag in [f'{{{ns}}}path', f'{{{ns}}}rect', f'{{{ns}}}circle', f'{{{ns}}}polygon', f'{{{ns}}}ellipse']:
        shapes.extend(root.findall(f'.//{tag}'))
        
    # Also try without namespace just in case
    for tag in ['path', 'rect', 'circle', 'polygon', 'ellipse']:
        shapes.extend(root.findall(f'.//{tag}'))
        
    if not shapes:
        print(f"⚠️ No valid shapes found in {os.path.basename(source_path)}")
        return
        
    # Calculate required distributions
    num_shade = max(1, int(len(shapes) * shade_target))
    remaining_count = len(shapes) - num_shade
    
    other_prims = [p for p in primitives if p != 'shade_canopy']
    assignments = ['shade_canopy'] * num_shade
    assignments.extend(random.choices(other_prims, k=remaining_count))
    random.shuffle(assignments) # Shuffle the array so assignments are random
    
    # Apply the remix logic to each curve
    for idx, shape in enumerate(shapes):
        typology = assignments[idx]
        color = TYPOLOGY_COLORS.get(typology, "#CCCCCC")
        
        # Assign layer ID and styling
        shape.set('id', f'{typology}_{idx}')
        shape.set('fill', color)
        shape.set('stroke', '#000000')
        shape.set('stroke-width', '0.5')
        
        # Remix spatially: Randomize position slightly and scale
        dx = random.uniform(-15.0, 15.0)
        dy = random.uniform(-15.0, 15.0)
        scale = random.uniform(0.85, 1.15)
        
        existing_transform = shape.get('transform', '')
        new_transform = f"translate({dx:.2f}, {dy:.2f}) scale({scale:.2f})"
        shape.set('transform', f"{existing_transform} {new_transform}".strip())

    # Save remixed SVG
    os.makedirs(SVG_OUT_DIR, exist_ok=True)
    base_name = os.path.splitext(os.path.basename(source_path))[0]
    out_file = os.path.join(SVG_OUT_DIR, f"{base_name}_remix_v{iteration}.svg")
    tree.write(out_file, encoding='utf-8', xml_declaration=True)
    print(f"✅ Generated Iteration {iteration}: {out_file}")

def main():
    print("\n--- 🌿 Memory Machine: SVG Spatial Remixer ---")
    guidelines = load_guidelines()
    
    if not os.path.exists(SVG_IN_DIR):
        print(f"❌ Directory not found: {SVG_IN_DIR}")
        return
        
    svg_files = [f for f in os.listdir(SVG_IN_DIR) if f.endswith('.svg')]
    for svg_file in svg_files:
        source_path = os.path.join(SVG_IN_DIR, svg_file)
        for i in range(1, 4):  # Create 3 unique iterations per raw SVG
            remix_svg(source_path, i, guidelines)

if __name__ == "__main__":
    main()