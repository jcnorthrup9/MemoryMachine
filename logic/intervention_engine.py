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

        # Cross-pollination nodes carry precise spatial_parameters — use them
        spatial_params = asset.get('spatial_parameters', {})
        geometry_type  = spatial_params.get('geometry_type', None)
        if spatial_params:
            footprint = spatial_params.get('footprint_m', {})
            if isinstance(footprint, dict) and 'width' in footprint:
                radius = float(footprint['width']) / 2.0
            if 'height_m' in spatial_params:
                height = float(spatial_params['height_m'])

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

            # ── Cross-Pollination Geometry (geometry_type from spatial_parameters) ──
            if geometry_type == "pavilion_with_water":
                # Shade pavilion: plinth + columns + overhanging roof + integrated wading pool
                pool_w    = float(spatial_params.get('pool_width_m',   radius * 1.2))
                pool_d    = float(spatial_params.get('pool_depth_m',   0.3)) * 10  # scale to model units
                col_count = int(spatial_params.get('column_count',     8))
                col_h     = float(spatial_params.get('column_height_m', height * 0.75))
                col_r     = float(spatial_params.get('column_radius_m', radius * 0.06))
                # Wading pool basin
                pool_plane = rs.MovePlane(rs.WorldXYPlane(), [pt[0], pt[1], pt[2] - pool_d])
                pool_base  = rs.AddCylinder(pool_plane, pool_d, pool_w / 2.0)
                # Plinth
                plinth = rs.AddCylinder(base_plane, height * 0.04, radius * 1.05)
                # Columns
                for idx in range(col_count):
                    theta = idx * (2 * math.pi / col_count)
                    cx = pt[0] + (radius * 0.8) * math.cos(theta)
                    cy = pt[1] + (radius * 0.8) * math.sin(theta)
                    col = rs.AddCylinder(rs.MovePlane(rs.WorldXYPlane(), [cx, cy, pt[2]]), col_h, col_r)
                    geo_list.append(col)
                # Overhanging roof slab
                roof = rs.AddCylinder(rs.MovePlane(rs.WorldXYPlane(), [pt[0], pt[1], pt[2] + col_h]), height * 0.12, radius * 1.2)
                geo_list.extend([pool_base, plinth, roof])

            elif geometry_type == "shade_canopy":
                # Minimal shade canopy: thin perimeter ring + tensile surface approximated by a flat disc
                col_count = int(spatial_params.get('column_count', 6))
                col_h     = float(spatial_params.get('column_height_m', height * 0.9))
                col_r     = float(spatial_params.get('column_radius_m', radius * 0.05))
                for idx in range(col_count):
                    theta = idx * (2 * math.pi / col_count)
                    cx = pt[0] + (radius * 0.85) * math.cos(theta)
                    cy = pt[1] + (radius * 0.85) * math.sin(theta)
                    col = rs.AddCylinder(rs.MovePlane(rs.WorldXYPlane(), [cx, cy, pt[2]]), col_h, col_r)
                    geo_list.append(col)
                canopy = rs.AddCylinder(rs.MovePlane(rs.WorldXYPlane(), [pt[0], pt[1], pt[2] + col_h]), height * 0.06, radius * 1.1)
                geo_list.append(canopy)

            elif geometry_type == "water_garden":
                # Layered water garden: outer ring channel + inner raised planting mound + central jet pedestal
                outer_rim   = rs.AddCylinder(base_plane, height * 0.04, radius)
                inner_pool  = rs.AddCylinder(base_plane, height * 0.06, radius * 0.85)
                mound_plane = rs.MovePlane(rs.WorldXYPlane(), [pt[0], pt[1], pt[2] + height * 0.06])
                mound       = rs.AddSphere([pt[0], pt[1], pt[2] + height * 0.25], radius * 0.4)
                pedestal    = rs.AddCylinder(mound_plane, height * 0.3, radius * 0.12)
                geo_list.extend([outer_rim, inner_pool, mound, pedestal])

            elif geometry_type == "acoustic_screen":
                # Perforated acoustic screen wall: a row of thin vertical fins
                fin_count  = max(3, int(radius / 3))
                fin_width  = (radius * 2) / (fin_count * 1.5)
                fin_depth  = fin_width * 0.3
                for idx in range(fin_count):
                    fx = pt[0] - radius + idx * (radius * 2 / fin_count)
                    fin_pts = [
                        [fx,            pt[1],            pt[2]],
                        [fx + fin_width, pt[1],            pt[2]],
                        [fx + fin_width, pt[1] + fin_depth, pt[2]],
                        [fx,            pt[1] + fin_depth, pt[2]],
                        [fx,            pt[1],            pt[2] + height],
                        [fx + fin_width, pt[1],            pt[2] + height],
                        [fx + fin_width, pt[1] + fin_depth, pt[2] + height],
                        [fx,            pt[1] + fin_depth, pt[2] + height],
                    ]
                    fin = rs.AddBox(fin_pts)
                    geo_list.append(fin)

            elif geometry_type == "memory_tower":
                # Slender memory tower: base + tapered shaft + crown
                base = rs.AddCylinder(base_plane, height * 0.08, radius)
                shaft_plane = rs.MovePlane(rs.WorldXYPlane(), [pt[0], pt[1], pt[2] + height * 0.08])
                shaft = rs.AddCylinder(shaft_plane, height * 0.75, radius * 0.35)
                crown_plane = rs.MovePlane(rs.WorldXYPlane(), [pt[0], pt[1], pt[2] + height * 0.83])
                crown = rs.AddCylinder(crown_plane, height * 0.1, radius * 0.55)
                spire_plane = rs.MovePlane(rs.WorldXYPlane(), [pt[0], pt[1], pt[2] + height * 0.93])
                spire = rs.AddCylinder(spire_plane, height * 0.25, radius * 0.08)
                geo_list.extend([base, shaft, crown, spire])

            elif geometry_type == "landscape_mound":
                # Topographic mound: stacked diminishing spheroids approximating a landform
                for level in range(4):
                    frac  = 1.0 - level * 0.22
                    z_off = pt[2] + level * (height * 0.28)
                    sphere = rs.AddSphere([pt[0], pt[1], z_off], radius * frac)
                    geo_list.append(sphere)

            elif "tree" in name_lower or "garden" in name_lower or "park" in name_lower:
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