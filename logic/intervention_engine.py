import rhinoscriptsyntax as rs
import json
import os
import random
import math
import sys

try:
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    DATA_DIR = os.path.join(BASE_DIR, 'data')
    LOGIC_DIR = os.path.join(BASE_DIR, 'logic')
    MODEL_DIR = os.path.join(BASE_DIR, 'archive', 'assets', 'models')
    JSON_FILE = os.path.join(DATA_DIR, 'memory_manifest.json')
except NameError:
    # Fallback to the exact path on your machine
    BASE_DIR = r"c:\Users\john\MemoryMachine"
    DATA_DIR = os.path.join(BASE_DIR, 'data')
    LOGIC_DIR = os.path.join(BASE_DIR, 'logic')
    MODEL_DIR = os.path.join(BASE_DIR, 'archive', 'assets', 'models')
    JSON_FILE = os.path.join(DATA_DIR, 'memory_manifest.json')

if LOGIC_DIR not in sys.path:
    sys.path.append(LOGIC_DIR)

import site_reconstruction

# If the file wasn't found automatically, prompt the user to locate it
if not JSON_FILE or not os.path.exists(JSON_FILE):
    JSON_FILE = rs.OpenFileName("Select memory_manifest.json", "JSON Files (*.json)|*.json||")

def run_intervention_app():
    if not JSON_FILE or not os.path.exists(JSON_FILE):
        print("Error: Could not find memory_manifest.json")
        return

    with open(JSON_FILE, 'r') as f:
        asset_data = json.load(f)

    if not asset_data:
        print("No assets found in the manifest.")
        return

    print("\n========================================")
    print("1. LOADING PERSHING SQUARE BASE SITE...")
    site_reconstruction.reconstruct_pershing_square_base()

    rs.AddLayer("01_INTERVENTION_ASSETS", (0, 255, 128))
    rs.AddLayer("06_LABELS", (255, 255, 255))
    rs.EnableRedraw(False)

    print("========================================")
    print("2. DEPLOYING {} MEMORY ASSETS TO SITE...".format(len(asset_data)))

    # Auto-Deploy all assets across the site
    for asset in asset_data:
        selected = asset.get('name', 'Unknown')
        sentiment = float(asset.get('sentiment_score', 0.5))
        raw_text = asset.get('raw_text', '')

        # Auto-generate a location within Pershing Square bounds (roughly 330x550)
        pt = [random.uniform(20, 310), random.uniform(20, 530), 0]
        
        # Auto-calculate a slight organic scale variation
        scale = random.uniform(0.8, 1.5)

        radius = 15.0 * sentiment * scale
        height = 40.0 * sentiment * scale
        
        # High-Fidelity Check: Look for a matching 3D model in the archive
        safe_name = selected.lower().replace(" ", "_").replace("'", "")
        obj_path = os.path.join(MODEL_DIR, safe_name + ".obj")
        rhino_path = os.path.join(MODEL_DIR, safe_name + ".3dm")
        
        imported_objs = []
        if os.path.exists(obj_path):
            rs.Command('_-Import "{}" _Enter'.format(obj_path))
            imported_objs = rs.LastCreatedObjects()
        elif os.path.exists(rhino_path):
            rs.Command('_-Import "{}" _Enter'.format(rhino_path))
            imported_objs = rs.LastCreatedObjects()
            
        if imported_objs:
            # Group, move, and scale the imported high-fidelity asset
            rs.AddObjectsToGroup(imported_objs, rs.AddGroup())
            rs.MoveObjects(imported_objs, pt)
            rs.ScaleObjects(imported_objs, pt, [scale, scale, scale])
            
            for obj in imported_objs:
                rs.ObjectLayer(obj, "01_INTERVENTION_ASSETS")
                rs.SetUserText(obj, "Asset_Name", selected)
                rs.SetUserText(obj, "Memory_Data", raw_text)
        else:
            # HIGH-FIDELITY PROCEDURAL FALLBACK
            base_plane = rs.MovePlane(rs.WorldXYPlane(), pt)
            geo_list = []
            
            name_lower = selected.lower()
            if "tree" in name_lower or "garden" in name_lower or "park" in name_lower:
                # High-Fidelity Tree: Trunk and organic multi-sphere canopy
                trunk = rs.AddCylinder(base_plane, height * 0.5, radius * 0.15)
                c1 = rs.AddSphere([pt[0], pt[1], pt[2] + height * 0.6], radius * 0.8)
                c2 = rs.AddSphere([pt[0] + radius*0.4, pt[1] + radius*0.2, pt[2] + height * 0.7], radius * 0.6)
                c3 = rs.AddSphere([pt[0] - radius*0.3, pt[1] - radius*0.4, pt[2] + height * 0.5], radius * 0.5)
                geo_list.extend([trunk, c1, c2, c3])
                
            elif "water" in name_lower or "basin" in name_lower or "fountain" in name_lower:
                # High-Fidelity Fountain: Tiered basins and pedestal
                base_rim = rs.AddCylinder(base_plane, height * 0.05, radius)
                inner_pool = rs.AddCylinder(base_plane, height * 0.06, radius * 0.9)
                rs.ObjectColor(water, (0, 150, 255))
                pedestal = rs.AddCylinder(base_plane, height * 0.25, radius * 0.2)
                top_tier = rs.AddCylinder(rs.MovePlane(rs.WorldXYPlane(), [pt[0], pt[1], pt[2] + height * 0.25]), height * 0.05, radius * 0.5)
                geo_list.extend([base_rim, inner_pool, pedestal, top_tier])
                
            elif "pavilion" in name_lower or "lobby" in name_lower:
                # High-Fidelity Pavilion: Plinth, 8 circular columns, and overhanging roof
                plinth = rs.AddCylinder(base_plane, height * 0.05, radius)
                geo_list.append(plinth)
                for idx in range(8):
                    theta = idx * (math.pi / 4)
                    cx = pt[0] + (radius * 0.8) * math.cos(theta)
                    cy = pt[1] + (radius * 0.8) * math.sin(theta)
                    col = rs.AddCylinder(rs.MovePlane(rs.WorldXYPlane(), [cx, cy, pt[2] + height * 0.05]), height * 0.75, radius * 0.08)
                    geo_list.append(col)
                roof = rs.AddCylinder(rs.MovePlane(rs.WorldXYPlane(), [pt[0], pt[1], pt[2] + height * 0.8]), height * 0.15, radius * 1.1)
                geo_list.append(roof)
                
            elif "tower" in name_lower or "campanile" in name_lower:
                # High-Fidelity Tower: Base plinth, main shaft, tapered top, and spire
                base_box = rs.AddBox([[pt[0]-radius, pt[1]-radius, pt[2]], [pt[0]+radius, pt[1]-radius, pt[2]], [pt[0]+radius, pt[1]+radius, pt[2]], [pt[0]-radius, pt[1]+radius, pt[2]],
                                      [pt[0]-radius, pt[1]-radius, pt[2]+height*0.8], [pt[0]+radius, pt[1]-radius, pt[2]+height*0.8], [pt[0]+radius, pt[1]+radius, pt[2]+height*0.8], [pt[0]-radius, pt[1]+radius, pt[2]+height*0.8]])
                top_box = rs.AddBox([[pt[0]-radius*0.8, pt[1]-radius*0.8, pt[2]+height*0.8], [pt[0]+radius*0.8, pt[1]-radius*0.8, pt[2]+height*0.8], [pt[0]+radius*0.8, pt[1]+radius*0.8, pt[2]+height*0.8], [pt[0]-radius*0.8, pt[1]+radius*0.8, pt[2]+height*0.8],
                                     [pt[0]-radius*0.8, pt[1]-radius*0.8, pt[2]+height], [pt[0]+radius*0.8, pt[1]-radius*0.8, pt[2]+height], [pt[0]+radius*0.8, pt[1]+radius*0.8, pt[2]+height], [pt[0]-radius*0.8, pt[1]+radius*0.8, pt[2]+height]])
                spire = rs.AddCylinder(rs.MovePlane(rs.WorldXYPlane(), [pt[0], pt[1], pt[2]+height]), height*0.3, radius*0.1)
                geo_list.extend([base_box, top_box, spire])
                
            else:
                # High-Fidelity Default: Artistic Monument with rotating stacked blocks
                block1 = rs.AddBox([[pt[0]-radius, pt[1]-radius, pt[2]], [pt[0]+radius, pt[1]-radius, pt[2]], [pt[0]+radius, pt[1]+radius, pt[2]], [pt[0]-radius, pt[1]+radius, pt[2]],
                                    [pt[0]-radius, pt[1]-radius, pt[2]+height*0.3], [pt[0]+radius, pt[1]-radius, pt[2]+height*0.3], [pt[0]+radius, pt[1]+radius, pt[2]+height*0.3], [pt[0]-radius, pt[1]+radius, pt[2]+height*0.3]])
                
                b2_rad = radius * 0.7
                block2 = rs.AddBox([[pt[0]-b2_rad, pt[1]-b2_rad, pt[2]+height*0.3], [pt[0]+b2_rad, pt[1]-b2_rad, pt[2]+height*0.3], [pt[0]+b2_rad, pt[1]+b2_rad, pt[2]+height*0.3], [pt[0]-b2_rad, pt[1]+b2_rad, pt[2]+height*0.3],
                                    [pt[0]-b2_rad, pt[1]-b2_rad, pt[2]+height*0.6], [pt[0]+b2_rad, pt[1]-b2_rad, pt[2]+height*0.6], [pt[0]+b2_rad, pt[1]+b2_rad, pt[2]+height*0.6], [pt[0]-b2_rad, pt[1]+b2_rad, pt[2]+height*0.6]])
                rs.RotateObject(block2, [pt[0], pt[1], pt[2]], 45, [0,0,1])
                
                b3_rad = radius * 0.4
                block3 = rs.AddBox([[pt[0]-b3_rad, pt[1]-b3_rad, pt[2]+height*0.6], [pt[0]+b3_rad, pt[1]-b3_rad, pt[2]+height*0.6], [pt[0]+b3_rad, pt[1]+b3_rad, pt[2]+height*0.6], [pt[0]-b3_rad, pt[1]+b3_rad, pt[2]+height*0.6],
                                    [pt[0]-b3_rad, pt[1]-b3_rad, pt[2]+height], [pt[0]+b3_rad, pt[1]-b3_rad, pt[2]+height], [pt[0]+b3_rad, pt[1]+b3_rad, pt[2]+height], [pt[0]-b3_rad, pt[1]+b3_rad, pt[2]+height]])
                rs.RotateObject(block3, [pt[0], pt[1], pt[2]], 15, [0,0,1])
                
                geo_list.extend([block1, block2, block3])

            # Group and tag the procedural geometry
            group = rs.AddGroup()
            rs.AddObjectsToGroup(geo_list, group)
            for g in geo_list:
                rs.ObjectLayer(g, "01_INTERVENTION_ASSETS")
                rs.SetUserText(g, "Asset_Name", selected)
                rs.SetUserText(g, "Memory_Data", raw_text)
        
        dot = rs.AddTextDot(selected, [pt[0], pt[1], pt[2] + height + 2])
        rs.ObjectLayer(dot, "06_LABELS")
        
    rs.EnableRedraw(True)
    print("✅ Auto-deployment complete!")

    # Take an automatic high-res screenshot of the final masterplan
    archive_dir = os.path.join(BASE_DIR, 'archive', 'render_output')
    if not os.path.exists(archive_dir):
        os.makedirs(archive_dir)
    capture_path = os.path.join(archive_dir, 'intervention_masterplan_capture.png')
    
    rs.Command('_-ViewCaptureToFile "{}" _Width=1920 _Height=1080 _TransparentBackground=_No _Enter'.format(capture_path))
    print("📸 Saved final masterplan capture to: {}".format(capture_path))

if __name__ == "__main__":
    run_intervention_app()