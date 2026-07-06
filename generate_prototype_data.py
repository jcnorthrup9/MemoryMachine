"""
Memory Machine - Prototype Data Generator

This script orchestrates the analysis of Pershing Square and generates a 
data payload (`site_data.json`) for the `PershingMetabolizer_Prototype`.

Workflow:
1.  Loads the real site boundary from the Rhino-exported SVG.
2.  Initializes the `MemoryMachineEngine` from `urban_interference_solver.py`.
3.  Runs the solver to identify high-priority "dig zones" (punctures).
4.  (Placeholder) Defines zones for "shade" and "green_space".
5.  Exports all data into the `site_data.json` format for the prototype.
"""
import os
import json
import re
from xml.etree import ElementTree as ET

# Import the existing engine from the urban_interference_solver
from urban_interference_solver import MemoryMachineEngine, init_directory_schema, BASE_DIR, SVG_PLAN_PATH


def get_svg_boundary_path(svg_path):
    """
    Parses an SVG file to find the path data within the 'STRUC__Slabs' group.

    Args:
        svg_path (str): The absolute path to the SVG file.

    Returns:
        str: The SVG path data string, or None if not found.
    """
    try:
        # Register the SVG namespace to handle the file correctly
        ET.register_namespace("", "http://www.w3.org/2000/svg")
        tree = ET.parse(svg_path)
        root = tree.getroot()
        
        # Define the namespace map for XPath queries
        ns = {'svg': 'http://www.w3.org/2000/svg'}
        
        # Find the path element within the specific group
        slab_group = root.find(".//*[@id='STRUC__Slabs']", ns)
        if slab_group is not None:
            path_element = slab_group.find('svg:path', ns)
            if path_element is not None:
                return path_element.get('d')
        
        # Fallback for SVGs that might not have the group but have the path
        # This is less specific and might grab the wrong path if the SVG is complex
        # Based on pershingRhinoPlanView.svg, the path is unique.
        content = open(svg_path, 'r').read()
        slab_block_match = re.search(r'<g id="STRUC__Slabs">.*?</g>', content, re.DOTALL)
        if slab_block_match:
            path_match = re.search(r'd="([^"]+)"', slab_block_match.group(0))
            if path_match:
                return path_match.group(1)

    except Exception as e:
        print(f"[ERROR] Could not parse SVG file at {svg_path}: {e}")
    
    return None

def main():
    """Main execution function."""
    print("--- Starting Prototype Data Generation ---")

    # --- 1. Initialize Paths & Engine ---
    init_directory_schema()
    engine = MemoryMachineEngine()
    
    prototype_dir = os.path.join(BASE_DIR, "PershingMetabolizer_Prototype")
    output_path = os.path.join(prototype_dir, "site_data.json")
    svg_path = SVG_PLAN_PATH

    # --- 2. Run the Interference Solver ---
    print("[SOLVER] Running urban interference analysis...")
    punctures = engine.solve_punctures()
    print(f"[SOLVER] Identified {len(punctures)} potential dig zones.")

    # --- 3. Extract Real Site Geometry ---
    print(f"[SVG] Parsing real site boundary from {svg_path}...")
    boundary_path = get_svg_boundary_path(svg_path)
    if not boundary_path:
        print("[FATAL] Could not extract boundary path from SVG. Aborting.")
        return

    # --- 4. Assemble the JSON Payload ---
    print("[ASSEMBLY] Compiling data for site_data.json...")
    site_data = {
        "site_dimensions": {
            "width_ft": round(engine.cell_size_ft[0] * engine.grid_size, 2),
            "height_ft": round(engine.cell_size_ft[1] * engine.grid_size, 2)
        },
        "boundary_svg_path": boundary_path,
        "grid_size": engine.grid_size,
        "zones": {
            "shade": [], # Placeholder for future logic
            "green_space": [], # Placeholder for future logic
            "dig_zones": [
                {"grid_x": p["coordinates"][0], "grid_y": p["coordinates"][1], "depth_ft": p["bounds"]["excavation_depth_ft"], "score": p["intervention_score"]}
                for p in punctures
            ]
        }
    }

    # --- 5. Export the JSON file ---
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(site_data, f, indent=2)
    
    print(f"\n[SUCCESS] Exported prototype data to:\n{output_path}")
    print("--- Generation Complete ---")

if __name__ == "__main__":
    main()