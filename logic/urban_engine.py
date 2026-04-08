import os
import re
import json
import random
import math
import xml.etree.ElementTree as ET

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

class GuidelineManager:
    """Parses urban_design_guidelines.md table for dynamic Zonal Metadata."""
    def __init__(self, filepath):
        self.filepath = filepath
        self.all_exact_layers = [
            "BOUNDARY", "GREEN_SPACE", "SHADE", "WATER_FEATURES", 
            "STREET", "PEDESTRIAN_PATH", "MAJOR_ATTRACTORS", 
            "MINOR_ATTRACTORS", "UNIQUE_ELEMENTS", "STREET_FURNITURE", "PARKING"
        ]

    def parse(self):
        guidelines, metadata, primitives, locked = {}, {}, {}, []
        
        # Translation Bridge: Maps Markdown theory to exact Rhino layer IDs
        layer_map = {
            "**SOFT_01**": (["GREEN_SPACE", "SHADE"], "sphere", False),
            "**HARD_01**": (["STREET", "PEDESTRIAN_PATH", "STREET_FURNITURE", "PARKING", "BOUNDARY"], "box", True),
            "**PROG_01**": (["MAJOR_ATTRACTORS", "MINOR_ATTRACTORS", "UNIQUE_ELEMENTS"], "cylinder", False),
            "**BLUE_01**": (["WATER_FEATURES"], "disc", False)
        }

        if os.path.exists(self.filepath):
            with open(self.filepath, "r", encoding="utf-8") as f:
                content = f.read()

            table_lines = re.findall(r"\|.*\|", content)
            
            for line in table_lines:
                if "Zone ID" in line or "---" in line:
                    continue
                cols = [c.strip() for c in line.split('|')][1:-1]
                if len(cols) >= 5:
                    cat = cols[0].strip()
                    label = cols[1].strip()
                    targets = cols[2].replace("%", "").strip()
                    
                    t_min, t_max = 0, 100
                    if "-" in targets or "–" in targets:
                        parts = targets.replace("–", "-").split("-")
                        t_min, t_max = int(parts[0]), int(parts[1])
                        
                    base_cat = cat.replace("*", "").split("_")[0] # Maps "**SOFT_01**" to "SOFT"
                    guidelines[base_cat] = {"min": t_min, "max": t_max, "label": label}
                    
                    if cat in layer_map:
                        layers, prim, is_locked = layer_map[cat]
                        metadata[base_cat] = layers
                        for l in layers:
                            primitives[l] = prim
                            if is_locked and l in ["PARKING", "STREET", "BOUNDARY"] and l not in locked:
                                locked.append(l)

        if not metadata:
            metadata = {
                "SOFT": ["GREEN_SPACE", "SHADE"],
                "HARD": ["STREET", "PEDESTRIAN_PATH", "STREET_FURNITURE", "PARKING", "BOUNDARY"],
                "PROG": ["MAJOR_ATTRACTORS", "MINOR_ATTRACTORS", "UNIQUE_ELEMENTS"],
                "BLUE": ["WATER_FEATURES"]
            }
        if not guidelines:
            guidelines = {
                "SOFT": {"min": 30, "max": 50},
                "HARD": {"min": 40, "max": 60},
                "PROG": {"min": 10, "max": 20},
                "BLUE": {"min": 2, "max": 10},
                "Infrastructure": {"min": 100, "max": 100}
            }
        if not primitives:
            primitives = {
                "GREEN_SPACE": "sphere", "SHADE": "sphere",
                "WATER_FEATURES": "disc",
                "STREET": "box", "PEDESTRIAN_PATH": "box", "STREET_FURNITURE": "box", "PARKING": "box", "BOUNDARY": "box",
                "MAJOR_ATTRACTORS": "cylinder", "MINOR_ATTRACTORS": "cylinder", "UNIQUE_ELEMENTS": "cylinder"
            }
        if not locked:
            locked = ["PARKING", "STREET", "BOUNDARY"]

        return {"guidelines": guidelines, "metadata": metadata, "primitives": primitives, "locked": locked}

guideline_manager = GuidelineManager(os.path.join(BASE_DIR, "urban_design_guidelines.md"))

def remix_layers(seed_items):
    """
    Offsets and scales the selected SVG layers within the Pershing Square bounds.
    Uses a deterministic mathematical check to ensure the initial 'Draft' layout 
    strictly complies with the URBAN_GUIDELINES target percentages.
    Includes a locked static layer injection for Infrastructure layers.
    """
    import random
    import math
    
    # Pull exclusively from GuidelineManager
    gm_data = guideline_manager.parse()
    zonal_metadata = gm_data.get("metadata", {})
    primitives_map = gm_data.get("primitives", {})
    locked_layers = gm_data.get("locked", [])
    urban_guidelines = gm_data.get("guidelines", {})

    valid_layers = [layer for category in zonal_metadata.values() for layer in category]
    
    SVG_DIR = os.path.join(BASE_DIR, 'data', 'ParkSVG')
    valid_sites = []
    if os.path.exists(SVG_DIR):
        valid_sites = [f[:-4].replace("_", "").replace(" ", "") for f in os.listdir(SVG_DIR) if f.lower().endswith(".svg")]
    if not valid_sites: valid_sites = ["PershingSquare", "ParcdelaVillette", "ZaryadyePark", "Schouwburgplein"]
    
    composed = []
    
    if not isinstance(seed_items, list):
        return composed
        
    seed_items = seed_items[:5]
    
    for item in seed_items:
        site = item.get("site", "PershingSquare")
        layer = item.get("layer", "GREEN_SPACE")
        
        if site not in valid_sites: site = "PershingSquare"
        if layer not in valid_layers: layer = "GREEN_SPACE"
        
        prim = primitives_map.get(layer, "box")
        
        # CLEAN SLATE: Flat 1.0 scale at origin (0,0)
        final_scale = 1.0
        x = 0
        y = 0
            
        # Smart dimensions based on the calculated scale
        width = int(400 * final_scale)
        height = int(400 * final_scale)

        transform = {
            "x": x,
            "y": y,
            "scale": final_scale,
            "rot": 0
        }
        
        composed.append({
            "site": site, 
            "layerId": layer, 
            "transform": transform, 
            "opacity": 0.85,
            "target_width": width,
            "target_height": height,
            "primitive": prim
        })
    return composed

def apply_zonal_grid(stack_items: list):
    """
    Calculates the current programmatic coverage percentage 
    to feed back into the HUD (Zonal Constraints).
    """
    total_area = 800 * 600 # Total site bounding box area
    coverage = {"SOFT": 0, "HARD": 0, "PROG": 0, "BLUE": 0}
    
    for item in stack_items:
        area = item.get("width", 1) * item.get("height", 1)
        layer_type = item.get("layer", "").split('_')[0]
        if layer_type in coverage:
            coverage[layer_type] += (area / total_area) * 100
            
    return coverage