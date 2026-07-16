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
            "**HARD_01**": (["STREET", "PEDESTRIAN_PATH", "STREET_FURNITURE", "PARKING", "BOUNDARY", "HARDSCAPE"], "box", True),
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
                "HARD": ["STREET", "PEDESTRIAN_PATH", "STREET_FURNITURE", "PARKING", "BOUNDARY", "HARDSCAPE"],
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
                "STREET": "box", "PEDESTRIAN_PATH": "box", "STREET_FURNITURE": "box", "PARKING": "box", "BOUNDARY": "box", "HARDSCAPE": "box",
                "MAJOR_ATTRACTORS": "cylinder", "MINOR_ATTRACTORS": "cylinder", "UNIQUE_ELEMENTS": "cylinder"
            }
        if not locked:
            locked = ["PARKING", "STREET", "BOUNDARY"]

        return {"guidelines": guidelines, "metadata": metadata, "primitives": primitives, "locked": locked}

guideline_manager = GuidelineManager(os.path.join(BASE_DIR, "urban_design_guidelines.md"))

def remix_layers(seed_items):
    """
    Offsets and scales the selected SVG layers within the Pershing Square bounds.
    Cardinal location from AI is translated to fractional offsets (of
    Pershing's own detected boundary size) relative to site center -- see
    LOCATION_OFFSET_FRAC in ingest_diagram_svg.py, which is what actually
    resolves these into real placement (this function only picks WHICH
    layer/site/location, not the final pixel math).
    """
    import random
    import math

    # Pull exclusively from GuidelineManager
    gm_data = guideline_manager.parse()
    zonal_metadata = gm_data.get("metadata", {})
    primitives_map = gm_data.get("primitives", {})
    urban_guidelines = gm_data.get("guidelines", {})

    valid_layers = [layer for category in zonal_metadata.values() for layer in category]

    # Bug fix #4: HARDSCAPE exists in SVGs but wasn't in valid_layers
    if "HARDSCAPE" not in valid_layers:
        valid_layers.append("HARDSCAPE")

    # 2026-07-16: repointed at the current canonical precedent SVG dir
    # (data/ParkSVG was the OLD, stale source -- huge multi-MB files with
    # sync-conflict artifacts, superseded 2026-07-14 by this cleaner,
    # solid-filled export set that diagram_tool/ and ingest_diagram_svg.py
    # already use as the single source of truth).
    SVG_DIR = os.path.join(BASE_DIR, 'data', 'PershingMetabolizer', 'parkSVG', 'PrecedentSVG')

    # Bug fix #3: normalize site names to match the canonical SVG filenames
    # in SVG_DIR above (2026-07-16: corrected to match those exact
    # filenames -- "ParcVillette"/"GardensBytheBay", not the old
    # "ParcdelaVillette"/"GardensByTheBay" spellings, which don't exist in
    # the current directory and would have silently failed to resolve).
    SITE_NAME_CANONICAL = {
        "pershingsquare":    "PershingSquare",
        "parcdelavillette":  "ParcVillette",
        "parcvillette":      "ParcVillette",
        "zaryadyepark":      "ZaryadyePark",
        "schouwburgplein":   "Schouwburgplein",
        "gardensbythebay":   "GardensBytheBay",
    }
    valid_sites = list(SITE_NAME_CANONICAL.values())
    if os.path.exists(SVG_DIR):
        for f in os.listdir(SVG_DIR):
            if f.lower().endswith(".svg"):
                raw = f[:-4].replace("_", "").replace(" ", "").lower()
                canonical = SITE_NAME_CANONICAL.get(raw, f[:-4])
                if canonical not in valid_sites:
                    valid_sites.append(canonical)

    # Layers that only exist in specific SVGs — always route to their canonical site
    LAYER_SITE_AFFINITY = {
        "SHADE":            "Schouwburgplein",
        "HARDSCAPE":        "Schouwburgplein",   # also in ZaryadyePark
        "AMPHITHEATRE":     "ZaryadyePark",
        # Bug fix #2: MAJOR/MINOR_ATTRACTORS don't exist — alias to UNIQUE_ELEMENTS
        "MAJOR_ATTRACTORS": "PershingSquare",
        "MINOR_ATTRACTORS": "PershingSquare",
    }

    # Bug fix #2: layer name aliases — remap to the geometry that actually exists
    LAYER_ALIAS = {
        "MAJOR_ATTRACTORS": "UNIQUE_ELEMENTS",
        "MINOR_ATTRACTORS": "UNIQUE_ELEMENTS",
    }

    # Bug fix #1: cardinal location -> FRACTIONAL offsets (2026-07-16,
    # replacing hand-tuned pixel values calibrated against a since-replaced
    # precedent SVG -- see ingest_diagram_svg.py's LOCATION_OFFSET_FRAC,
    # the single source of truth for these fractions now; kept here as a
    # plain re-export so this function's own composed["transform"] shape
    # doesn't need a second copy of the same table).
    from ingest_diagram_svg import LOCATION_OFFSET_FRAC as LOCATION_OFFSETS

    composed = []

    if not isinstance(seed_items, list):
        return composed

    seed_items = seed_items[:5]

    for item in seed_items:
        raw_site  = item.get("site", "PershingSquare")
        layer     = item.get("layer", "GREEN_SPACE")
        location  = item.get("location", "Center")

        # Bug fix #2: alias before validity check
        layer = LAYER_ALIAS.get(layer, layer)

        if layer not in valid_layers:
            layer = "GREEN_SPACE"

        # Normalize site name
        raw_key = raw_site.replace("_", "").replace(" ", "").lower()
        site = SITE_NAME_CANONICAL.get(raw_key, raw_site)

        # Override site if the layer only exists in a specific SVG
        if layer in LAYER_SITE_AFFINITY:
            site = LAYER_SITE_AFFINITY[layer]
        elif site not in valid_sites:
            site = "PershingSquare"

        prim = primitives_map.get(layer, "box")

        # Bug fix #1: translate cardinal location to a fractional offset
        x_frac, y_frac = LOCATION_OFFSETS.get(location, (0.0, 0.0))

        transform = {
            "x_frac": x_frac,
            "y_frac": y_frac,
            "scale": 1.0,
            "rot": 0
        }

        composed.append({
            "site": site,
            "layerId": layer,
            "transform": transform,
            "opacity": 0.85,
            "target_width": 400,
            "target_height": 400,
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