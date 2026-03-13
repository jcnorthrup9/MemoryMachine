import rhinoscriptsyntax as rs
import Rhino
import scriptcontext as sc
import System.Drawing
import random
import math

# --- CONFIGURATION ---
ROOT_LAYER = "TRAILER_88"
LAYERS = {
    "GEOMETRY": {"name": "GEOMETRY", "color": System.Drawing.Color.FromArgb(0, 255, 0)},     # Neon Green
    "ANOMALIES": {"name": "ANOMALIES", "color": System.Drawing.Color.FromArgb(255, 0, 255)}, # Magenta/Glitch
    "ENV": {"name": "ENVIRONMENT", "color": System.Drawing.Color.FromArgb(100, 100, 100)},   # Dark Grey
    "GRID": {"name": "ENVIRONMENT::SITE_GRID", "color": System.Drawing.Color.FromArgb(40, 40, 40)},
    "BOUND": {"name": "ENVIRONMENT::SITE_BOUNDARY", "color": System.Drawing.Color.White}
}

def setup_layers():
    """Creates the layer hierarchy with specific colors."""
    rs.EnableRedraw(False)
    if not rs.IsLayer(ROOT_LAYER):
        rs.AddLayer(ROOT_LAYER)
    
    for key, data in LAYERS.items():
        full_name = f"{ROOT_LAYER}::{data['name']}" if "::" not in data['name'] else f"{ROOT_LAYER}::{data['name']}"
        # Handle nested manually if needed, but Rhino handles '::' usually. 
        # To be safe with parent checking:
        parts = data['name'].split("::")
        current_parent = ROOT_LAYER
        
        for part in parts:
            layer_path = f"{current_parent}::{part}"
            if not rs.IsLayer(layer_path):
                rs.AddLayer(layer_path, parent=current_parent)
            current_parent = layer_path
            
            # Set color for the specific leaf layer
            if part == parts[-1]:
                rs.LayerColor(layer_path, data['color'])

    rs.CurrentLayer(f"{ROOT_LAYER}::GEOMETRY")
    rs.EnableRedraw(True)

def create_site_foundation():
    """Generates the 100x100 grid and boundary."""
    print("Building Site Foundation...")
    layer_grid = f"{ROOT_LAYER}::ENVIRONMENT::SITE_GRID"
    layer_bound = f"{ROOT_LAYER}::ENVIRONMENT::SITE_BOUNDARY"
    
    # 1. Boundary (100x100 centered at origin)
    # -50 to 50
    corners = [
        [-50, -50, 0], [50, -50, 0], [50, 50, 0], [-50, 50, 0], [-50, -50, 0]
    ]
    bound_crv = rs.AddPolyline(corners)
    rs.ObjectLayer(bound_crv, layer_bound)
    
    # 2. Grid (1ft intervals)
    rs.CurrentLayer(layer_grid)
    grid_lines = []
    for i in range(-50, 51):
        # X-direction lines
        l1 = rs.AddLine([i, -50, 0], [i, 50, 0])
        # Y-direction lines
        l2 = rs.AddLine([-50, i, 0], [50, i, 0])
        grid_lines.extend([l1, l2])
    
    # Group grid for cleanliness
    group_name = rs.AddGroup("SITE_GRID_GROUP")
    rs.AddObjectsToGroup(grid_lines, group_name)

def create_glitched_trailer():
    """Creates the trailer mesh and applies random vertex displacement."""
    print("Constructing Trailer Entity...")
    layer_geo = f"{ROOT_LAYER}::GEOMETRY"
    rs.CurrentLayer(layer_geo)
    
    # Dimensions: 32' x 8' x 10'
    # Base Plane centered locally first, then moved
    # Create a Mesh Box directly for easier vertex manipulation
    # Parameters: Box(Plane, x_interval, y_interval, z_interval)
    # We construct it using Rhino.Geometry for finer control
    
    origin = Rhino.Geometry.Point3d(0,0,0)
    x_vec = Rhino.Geometry.Vector3d(1,0,0)
    y_vec = Rhino.Geometry.Vector3d(0,1,0)
    plane = Rhino.Geometry.Plane(origin, x_vec, y_vec)
    
    box = Rhino.Geometry.Mesh.CreateFromBox(
        Rhino.Geometry.BoundingBox(
            Rhino.Geometry.Point3d(0, 0, 0), 
            Rhino.Geometry.Point3d(32, 8, 10)
        ),
        10, 4, 4 # Counts for faces (X, Y, Z) - more faces = more glitch potential
    )
    
    # Apply Glitch (Randomize 5% of vertices)
    vertices = box.Vertices
    for i in range(vertices.Count):
        if random.random() < 0.05: # 5% chance
            # Shift by 0.5 units in a random direction
            shift = Rhino.Geometry.Vector3d(
                random.uniform(-0.5, 0.5),
                random.uniform(-0.5, 0.5),
                random.uniform(-0.5, 0.5)
            )
            vertices[i] = vertices[i] + shift
            
    # Transform: Move to (15, 10, 0) and Rotate 15 degrees
    xform_move = Rhino.Geometry.Transform.Translation(15, 10, 0)
    xform_rot = Rhino.Geometry.Transform.Rotation(math.radians(15), Rhino.Geometry.Point3d(15, 10, 0))
    
    box.Transform(xform_move)
    box.Transform(xform_rot)
    
    # Add to document
    sc.doc.Objects.AddMesh(box)
    sc.doc.Views.Redraw()

def create_narrative_objects():
    """Adds fence, pole, and anomalies."""
    print("Inserting Narrative Artifacts...")
    layer_env = f"{ROOT_LAYER}::ENVIRONMENT"
    layer_anom = f"{ROOT_LAYER}::ANOMALIES"
    
    # 1. Perimeter Fence Posts (Every 10 feet along boundary)
    rs.CurrentLayer(layer_env)
    for x in [-50, 50]:
        for y in range(-50, 51, 10):
            rs.AddLine([x, y, 0], [x, y, 6]) # 6ft posts
    for y in [-50, 50]:
        for x in range(-40, 41, 10): # Avoid duplicates at corners roughly
            rs.AddLine([x, y, 0], [x, y, 6])
            
    # 2. Utility Pole (Cylinder)
    # Arbitrary location based on typical lot layouts (Corner offset)
    pole_pt = [45, 45, 0]
    rs.AddCylinder(rs.WorldXYPlane(), 20, 0.8, cap=True) 
    rs.MoveObject(rs.LastCreatedObjects()[0], pole_pt)
    
    # 3. Anomalous Markers (Spheres)
    rs.CurrentLayer(layer_anom)
    
    # Narrative coordinates derived from lore (The Tree, The Potato, The Winch)
    # Relative to the trailer's transformed position approx.
    events = [
        {"name": "EVENT_01_ROOT_SYSTEM", "pt": [12, 18, 0]},
        {"name": "EVENT_02_POTATO_JAR", "pt": [18, 12, 4]}, # Inside trailer area
        {"name": "EVENT_03_BLUE_TRUCK", "pt": [10, 8, 0]}
    ]
    
    for evt in events:
        sphere = rs.AddSphere(evt["pt"], 0.5)
        rs.ObjectName(sphere, evt["name"])
        rs.AddTextDot(evt["name"], evt["pt"])

def main():
    rs.EnableRedraw(False)
    setup_layers()
    create_site_foundation()
    create_glitched_trailer()
    create_narrative_objects()
    rs.EnableRedraw(True)
    print("✅ TRAILER 88 RECONSTRUCTION COMPLETE.")

if __name__ == "__main__":
    main()