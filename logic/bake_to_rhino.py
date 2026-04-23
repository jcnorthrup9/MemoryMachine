import os
import json
import math
import rhinoscriptsyntax as rs
import System.Drawing

def hex_to_rgb(hex_str):
    hex_str = hex_str.lstrip('#')
    if len(hex_str) == 6:
        return tuple(int(hex_str[i:i+2], 16) for i in (0, 2, 4))
    return (150, 150, 150)

def bake():
    # Get the project root directory dynamically
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    json_path = os.path.join(base_dir, 'data', 'current_intervention.json')
    
    if not os.path.exists(json_path):
        print("No intervention data found. Hit 'GEN' in the UI first!")
        return
        
    with open(json_path, 'r') as f:
        data = json.load(f)
        
    geometries = data.get("geometries", [])
    
    rs.EnableRedraw(False)
    layer_name = "MemoryMachine_Interventions"
    
    # Load the base site model if it's not already in the scene
    base_layer = "MemoryMachine_Context"
    if not rs.IsLayer(base_layer):
        rs.AddLayer(base_layer, color=System.Drawing.Color.DarkGray)
        rs.CurrentLayer(base_layer)
        obj_path = os.path.join(base_dir, 'models', 'PershingSquareCurrent.obj')
        if os.path.exists(obj_path):
            rs.Command(f'_-Import "{obj_path}" _Enter', False)
            # Lock the context layer so it doesn't get accidentally selected
            rs.LayerLocked(base_layer, True)

    # Clear previous generations so they don't pile up
    if rs.IsLayer(layer_name):
        objs = rs.ObjectsByLayer(layer_name)
        if objs: rs.DeleteObjects(objs)
    else:
        rs.AddLayer(layer_name)
        
    rs.CurrentLayer(layer_name)
    
    for i, geo in enumerate(geometries):
        g_type = geo.get("type", "box")
        args = geo.get("args", [])
        pos = geo.get("position", [0, 0, 0])
        rot = geo.get("rotation", [0, 0, 0])
        color_hex = geo.get("color", "#888888")
        
        # Map Three.js (X, Y_up, Z_depth) to Rhino (X, -Y_depth, Z_up)
        rx = pos[0]
        ry = -pos[2]
        rz = pos[1]
        center = [rx, ry, rz]
        
        rgb = hex_to_rgb(color_hex)
        
        # Create a colored sublayer for this specific object
        sublayer = f"{layer_name}::{g_type.upper()}_{i}"
        if not rs.IsLayer(sublayer):
            rs.AddLayer(sublayer, color=System.Drawing.Color.FromArgb(*rgb), parent=layer_name)
        rs.CurrentLayer(sublayer)
        
        obj_id = None
        if g_type == 'box' and len(args) >= 3:
            w, h, d = args[0], args[1], args[2]
            dx, dy, dz = w/2.0, d/2.0, h/2.0
            
            # Calculate the 8 corners of the box from the centroid
            p0 = [rx - dx, ry - dy, rz - dz]
            p1 = [rx + dx, ry - dy, rz - dz]
            p2 = [rx + dx, ry + dy, rz - dz]
            p3 = [rx - dx, ry + dy, rz - dz]
            p4 = [rx - dx, ry - dy, rz + dz]
            p5 = [rx + dx, ry - dy, rz + dz]
            p6 = [rx + dx, ry + dy, rz + dz]
            p7 = [rx - dx, ry + dy, rz + dz]
            
            obj_id = rs.AddBox([p0, p1, p2, p3, p4, p5, p6, p7])
            
        elif g_type == 'cylinder' and len(args) >= 3:
            rt, rb, h = args[0], args[1], args[2]
            radius = max(rt, rb)
            base_pt = [rx, ry, rz - (h/2.0)]
            base_plane = rs.MovePlane(rs.WorldXYPlane(), base_pt)
            obj_id = rs.AddCylinder(base_plane, h, radius)
            if obj_id: rs.CapPlanarHoles(obj_id)
            
        elif g_type == 'sphere' and len(args) >= 1:
            radius = args[0]
            obj_id = rs.AddSphere(center, radius)
            
        # Apply rotation around Z-axis (mapped from Three.js Y-axis yaw)
        if obj_id and len(rot) >= 3 and rot[1] != 0:
            rs.RotateObject(obj_id, center, math.degrees(rot[1]), [0, 0, 1])
            
    rs.CurrentLayer("Default")
    rs.EnableRedraw(True)
    print(f"Successfully baked {len(geometries)} geometric interventions to Rhino!")

if __name__ == "__main__":
    bake()