import os
import re
import json
import random
import math

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
    
    layer_to_cat = {l: cat for cat, layers in zonal_metadata.items() for l in layers}
    
    composed = []
    
    if not isinstance(seed_items, list):
        return composed
        
    seed_items = seed_items[:5]
    
    # 2. Count categories in this specific generation
    # Keys must match zonal_metadata keys: "SOFT", "HARD", "PROG", "BLUE"
    cat_counts = {"SOFT": 0, "HARD": 0, "PROG": 0, "BLUE": 0}
    for item in seed_items:
        cat = layer_to_cat.get(item.get("layer", "GREEN_SPACE"), "HARD")
        if cat in cat_counts:
            cat_counts[cat] += 1

    # 3. Define safe middle-ground targets based on parsed guidelines
    safe_targets = {}
    for cat, limits in urban_guidelines.items():
        safe_targets[cat] = (limits["min"] + limits["max"]) / 2.0
        
    # Realistic average footprint of a native SVG layer
    base_layer_area = 65000  

    for item in seed_items:
        site = item.get("site", "PershingSquare")
        layer = item.get("layer", "GREEN_SPACE")
        
        if site not in valid_sites: site = "PershingSquare"
        if layer not in valid_layers: layer = "GREEN_SPACE"
        
        cat = layer_to_cat.get(layer, "HARD")
        prim = primitives_map.get(layer, "box")
        count = cat_counts.get(cat, 0)
        
        # Semantic Grid Translation Matrix
        grid_map = {
            "North": (0, -150), "North-East": (200, -150), "East": (200, 0),
            "South-East": (200, 150), "South": (0, 150), "South-West": (-200, 150),
            "West": (-200, 0), "North-West": (-200, -150), "Center": (0, 0)
        }
        
        loc_str = item.get("location", "Center")
        base_x, base_y = grid_map.get(loc_str, (0, 0))
        
        # Apply organic clustering jitter so objects in the same cell don't perfectly overlap
        x = base_x + random.randint(-40, 40)
        y = base_y + random.randint(-40, 40)
        
        # 4. Calculate deterministic scale using a Spatial Physics Solver
        if count > 0 and cat in safe_targets:
            target_layer_pct = safe_targets[cat] / count
            site_w, site_h = 1224, 792
            site_area = site_w * site_h
            target_layer_area = site_area * (target_layer_pct / 100.0)
            
            base_side = math.sqrt(base_layer_area)
            
            # Iterative solver to find the perfect scale that results in the target VISIBLE area
            final_scale = 1.0
            step = 1.0
            
            for _ in range(15):
                w = base_side * final_scale
                h = base_side * final_scale
                
                # Calculate visible overlap with site boundary (origin is 0,0)
                left = max(x - w/2, -site_w/2)
                right = min(x + w/2, site_w/2)
                top = max(y - h/2, -site_h/2)
                bottom = min(y + h/2, site_h/2)
                
                visible_area = max(0, right - left) * max(0, bottom - top)
                
                if visible_area < target_layer_area:
                    final_scale += step
                else:
                    final_scale -= step
                step /= 1.5
            
            # Cap scale: prevent runaway values when object lands outside boundary
            final_scale = max(0.2, min(final_scale, 3.0))
            final_scale = round(final_scale * random.uniform(0.95, 1.05), 2)
        else:
            final_scale = 1.0
            
        # Smart dimensions based on the calculated scale
        width = int(400 * final_scale)
        height = int(400 * final_scale)

        transform = {
            "x": x,
            "y": y,
            "scale": final_scale,
            "rot": random.choice([0, 90, 180, 270])
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