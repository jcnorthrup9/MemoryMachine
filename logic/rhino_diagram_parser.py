try:
    import rhinoscriptsyntax as rs
    import Rhino.Geometry as rg
    INSIDE_RHINO = True
except ImportError:
    rs = rg = None
    INSIDE_RHINO = False

import os
import json
import argparse

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# This dictionary maps the layer names in your Rhino diagrams to the types in the JSON output.
# This is the "brain" of the parser.
LAYER_MAP = {
    "Streets": {"type": "Vehicular Street", "system": "lines"},
    "Pedestrian Pathways": {"type": "Primary Pedestrian", "system": "lines"},
    "Boundary": {"type": "Site Boundary", "system": "lines"},
    "Green Space": {"type": "Green Space", "system": "surfaces"},
    "Water Features": {"type": "Water Feature", "system": "surfaces"},
    "Main Attractors": {"type": "Main Attractor", "system": "points"},
    "Minor Attractors": {"type": "Minor Attractor", "system": "points"},
    "Unique Elements": {"type": "Unique Element", "system": "points"},
    "Shade": {"type": "Shade", "system": "surfaces"},
    "Hardscape Plaza": {"type": "Hardscape Plaza", "system": "surfaces"},
}

def get_object_properties(obj_id):
    """Extracts properties from a single Rhino object."""
    # Placeholder for logic to get bounding box, text, etc.
    bbox = rs.BoundingBox(obj_id)
    if not bbox: return None
    
    # For now, just return a simplified representation
    center = rs.BoundingBoxCenter(bbox)
    label = rs.ObjectName(obj_id) or "Unnamed"
    
    # Convert Rhino BBox to a 4-point polygon
    poly_points = [
        [bbox[0].X, bbox[0].Y], [bbox[1].X, bbox[1].Y],
        [bbox[2].X, bbox[2].Y], [bbox[3].X, bbox[3].Y]
    ]
    
    return {
        "label": label,
        "bounding_polygon": poly_points
    }

def parse_rhino_diagram():
    """
    Analyzes the active Rhino document's layers and objects to generate a spatial JSON blueprint.
    """
    print("--- Analyzing active Rhino diagram ---")
    
    output_data = {
        "site": os.path.splitext(os.path.basename(rs.DocumentName()))[0],
        "orientation_analysis": "Analysis pending...",
        "zones": [],
        "paths": [],
        "erasure_targets": [],
        "relationships": [],
        "design_logic": "Logic extracted directly from Rhino geometry."
    }
    
    zone_id_counter = 1
    path_id_counter = 1

    for layer_name, mapping in LAYER_MAP.items():
        if rs.IsLayer(layer_name):
            objects = rs.ObjectsByLayer(layer_name)
            print(f"  -> Found {len(objects)} objects on layer '{layer_name}'")
            for obj in objects:
                props = get_object_properties(obj)
                if not props: continue

                item = {
                    "label": props["label"],
                    "type": mapping["type"],
                    "system": mapping["system"],
                    "character": "Extracted from Rhino",
                    "bounding_polygon": props["bounding_polygon"]
                }

                if mapping["system"] == "lines":
                    item["id"] = f"P{path_id_counter}"
                    item["connects"] = [] # Placeholder
                    output_data["paths"].append(item)
                    path_id_counter += 1
                else: # points or surfaces
                    item["id"] = f"Z{zone_id_counter}"
                    output_data["zones"].append(item)
                    zone_id_counter += 1

    # Save the JSON file
    doc_name = os.path.splitext(os.path.basename(rs.DocumentName()))[0]
    save_path = os.path.join(BASE_DIR, 'archive', 'diagrams', f"{doc_name}_rhino_parsed.json")
    os.makedirs(os.path.dirname(save_path), exist_ok=True)
    with open(save_path, 'w', encoding='utf-8') as f:
        json.dump(output_data, f, indent=2)
        
    print(f"\n✅ Successfully parsed diagram. Saved to: {save_path}")
    return output_data

if __name__ == "__main__":
    if INSIDE_RHINO:
        parse_rhino_diagram()
    else:
        print("This script is designed to be run from within a Rhino instance via the MCP or ScriptEditor.")