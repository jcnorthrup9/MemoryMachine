import os
import sys


def _process_asset(rs, file_path, config):
    """Imports, scales, places, and annotates a single asset based on its configuration."""
    print(f"Processing asset with config: {config.get('layer', 'default')}")
    
    # 1. Import the object
    rs.UnselectAllObjects()
    rs.Command(f'_-Import "{file_path}" _Enter', False)
    imported_objs = rs.SelectedObjects()

    if not imported_objs:
        print(f"Warning: Import failed or produced no objects for {os.path.basename(file_path)}")
        return

    # 2. Set Layer
    layer = config.get("layer", "MEM_IMPORTED_ASSETS")
    if not rs.IsLayer(layer):
        rs.AddLayer(layer, config.get("color", (128, 128, 128)))
    rs.ObjectLayer(imported_objs, layer)

    # 3. Group and Scale
    group_name = rs.AddGroup()
    rs.AddObjectsToGroup(imported_objs, group_name)
    
    bbox = rs.BoundingBox(imported_objs)
    if not bbox: return

    # Scale to a specific height
    target_height = config.get("scale_to_height")
    if target_height:
        current_height = bbox[4][2] - bbox[0][2]
        if current_height > 0.01:
            scale_factor = target_height / current_height
            rs.ScaleObjects(imported_objs, bbox[0], [scale_factor, scale_factor, scale_factor])
            bbox = rs.BoundingBox(imported_objs) # Recalculate bbox after scaling

    # 4. Place and Rotate
    target_loc = config.get("location")
    if target_loc:
        current_base = bbox[0]
        translation = rs.VectorCreate(target_loc, current_base)
        rs.MoveObjects(imported_objs, translation)
        print(f"Placed {os.path.basename(file_path)} at {target_loc}")

    rotation = config.get("rotation_z")
    if rotation:
        rs.RotateObjects(imported_objs, target_loc, rotation)

    # 5. Add Sensory Annotation
    sensory_dot = config.get("sensory_dot")
    if sensory_dot:
        rs.AddTextDot(sensory_dot["text"], sensory_dot["location"])

def import_assets():
    # Import inside function so script can be loaded by CPython for COM dispatch
    try:
        import rhinoscriptsyntax as rs
    except ImportError:
        return

    # --- CONFIGURATION ---
    # Derive paths relative to this script file for portability
    PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    ASSET_FOLDER = os.path.join(PROJECT_ROOT, "archive", "assets", "models")

    ASSET_CONFIG = {
        "SwingSet": {
            "filename_pattern": "10549_ChildrenSwingSet",
            "layer": "swing_set",
            "color": (0, 255, 255),
            "scale_to_height": 6.0,
            "location": [50, 20, 0],
            "rotation_z": 15,
            "sensory_dot": {
                "text": "Patches of dirt underneath",
                "location": [50, 20, 7]
            }
        },
        # Future assets can be added here.
        # "ToyCar": { ... }
    }

    if not os.path.exists(ASSET_FOLDER):
        print(f"Error: Folder not found: {ASSET_FOLDER}")
        return

    found_files = [f for f in os.listdir(ASSET_FOLDER) if f.lower().endswith(".obj")]
    if not found_files:
        print("No .obj files found in assets folder.")
        return

    rs.EnableRedraw(False)

    for filename in found_files:
        for asset_name, config in ASSET_CONFIG.items():
            if config["filename_pattern"] in filename:
                file_path = os.path.join(ASSET_FOLDER, filename)
                _process_asset(rs, file_path, config)
                break  # Found config for this file, move to next file

    rs.EnableRedraw(True)
    print("Asset Import Complete.")

if __name__ == "__main__":
    try:
        import rhinoscriptsyntax
        import_assets()
    except ImportError:
        # Running from standard Python (CLI) -> Dispatch to Rhino
        print("Standard Python detected. Dispatching to Rhino via COM...")
        try:
            import win32com.client
            # Try Rhino 8 Interface first, then fallback
            try:
                rhino = win32com.client.dynamic.Dispatch("Rhino.Interface.8")
            except:
                rhino = win32com.client.dynamic.Dispatch("Rhino.Application")
            
            # Get RhinoScript object for RunScript command
            try:
                rs_app = rhino.GetScriptObject()
            except:
                rs_app = rhino

            script_path = os.path.abspath(__file__)
            # Use ScriptEditor to run the file inside Rhino
            cmd = f'_-ScriptEditor Run "{script_path}"'
            
            # Execute
            if hasattr(rs_app, "RunScript"):
                rs_app.RunScript(cmd, 1)
            else:
                rhino.RunScript(cmd, 1)
            print("✅ Command sent to Rhino.")
            
        except Exception as e:
            print(f"❌ Error: {e}")
            print("Ensure Rhino is running and 'pip install pywin32' is executed in this venv.")