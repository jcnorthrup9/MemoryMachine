import bpy
import json
import os

# --- DIRECTORY SETUP ---
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JSON_PATH = os.path.join(BASE_DIR, "data", "current_intervention.json")

COMFY_OUTPUT_DIR = r"D:\ComfyUI_windows_portable\ComfyUI\output"
if not os.path.exists(COMFY_OUTPUT_DIR):
    COMFY_OUTPUT_DIR = r"C:\ComfyUI_windows_portable\ComfyUI\output"

def clear_scene():
    """Clears all default objects in the current Blender scene."""
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete()

def get_recent_glbs():
    """Fetches and sorts the recently generated ComfyUI 3D models."""
    mesh_dir = os.path.join(COMFY_OUTPUT_DIR, "mesh")
    if not os.path.exists(mesh_dir):
        return []
    
    files = [os.path.join(mesh_dir, f) for f in os.listdir(mesh_dir) if f.lower().endswith('.glb')]
    files.sort(key=os.path.getmtime, reverse=True)
    return files

def load_intervention():
    if not os.path.exists(JSON_PATH):
        print(f"❌ JSON not found: {JSON_PATH}")
        return

    with open(JSON_PATH, 'r') as f:
        data = json.load(f)

    spatial_seed = data.get("spatial_seed", [])
    recent_glbs = get_recent_glbs()
    
    if not recent_glbs:
        print("⚠️ No GLB files found in ComfyUI output directory.")
        return

    glb_idx = 0

    for item in spatial_seed:
        layer_id = item.get("layerId", "")
        
        # Skip Base Boundary and Hardscape elements per logic
        if layer_id == "BOUNDARY" or "HARDSCAPE" in layer_id:
            continue

        # Cycle through available GLB assets
        glb_path = recent_glbs[glb_idx % len(recent_glbs)]
        glb_idx += 1

        # Get spatial constraints (mapped directly from the SVG coordinates)
        target_w = item.get("target_width", 20)
        target_h = item.get("target_height", 20) 
        
        # In 2D SVG space, Y is depth. In Blender, XY is the ground plane.
        target_loc_x = item.get("transform", {}).get("x", 0)
        target_loc_y = item.get("transform", {}).get("y", 0)

        # Import the GLB
        bpy.ops.import_scene.gltf(filepath=glb_path)
        imported_objs = bpy.context.selected_objects

        if not imported_objs:
            continue

        root_objs = [obj for obj in imported_objs if obj.parent not in imported_objs]
        meshes = [obj for obj in imported_objs if obj.type == 'MESH']
        
        if not meshes:
            continue

        # Step 1: Calculate the exact bounding box in world space
        min_x = min_y = min_z = float('inf')
        max_x = max_y = max_z = float('-inf')

        for mesh in meshes:
            for v in mesh.bound_box:
                world_v = mesh.matrix_world @ bpy.mathutils.Vector(v)
                min_x = min(min_x, world_v.x)
                max_x = max(max_x, world_v.x)
                min_y = min(min_y, world_v.y)
                max_y = max(max_y, world_v.y)
                min_z = min(min_z, world_v.z)
                max_z = max(max_z, world_v.z)

        size_x = max_x - min_x
        size_y = max_y - min_y
        size_z = max_z - min_z

        # Step 2: Scale proportionally to match the SVG footprint exactly
        scale_x = target_w / size_x if size_x > 0.001 else 1.0
        scale_y = target_h / size_y if size_y > 0.001 else 1.0

        for root in root_objs:
            root.scale[0] *= scale_x
            root.scale[1] *= scale_y
            root.scale[2] *= (scale_x + scale_y) / 2.0  # Average scale for height

        bpy.context.view_layer.update()

        # Step 3: Recalculate Center and Move to precise SVG coordinates
        min_x = min_y = min_z = float('inf')
        max_x = max_y = max_z = float('-inf')
        for mesh in meshes:
            for v in mesh.bound_box:
                world_v = mesh.matrix_world @ bpy.mathutils.Vector(v)
                min_x = min(min_x, world_v.x)
                max_x = max(max_x, world_v.x)
                min_y = min(min_y, world_v.y)
                max_y = max(max_y, world_v.y)
                min_z = min(min_z, world_v.z)
                max_z = max(max_z, world_v.z)
                
        center_x = (min_x + max_x) / 2.0
        center_y = (min_y + max_y) / 2.0
        center_z = min_z  # Snaps the bottom of the object precisely to the ground plane

        offset_x = target_loc_x - center_x
        offset_y = target_loc_y - center_y
        offset_z = 0 - center_z

        for root in root_objs:
            root.location.x += offset_x
            root.location.y += offset_y
            root.location.z += offset_z

        bpy.context.view_layer.update()

if __name__ == "__main__":
    clear_scene()
    load_intervention()
    
    # Save the resulting Masterplan as a standard Blender file
    save_path = os.path.join(BASE_DIR, "archive", "blender", "MemoryMachine_Masterplan.blend")
    os.makedirs(os.path.dirname(save_path), exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=save_path)
    
    print(f"\n🎉 SUCCESS: Blender Intervention Baked Successfully to: {save_path}!")
    # We deliberately don't quit here, allowing the UI to stay open so you can view it!