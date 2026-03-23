import rhinoscriptsyntax as rs
import os
import csv

try:
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    TREE_CSV = os.path.join(BASE_DIR, 'data', 'extracted_trees.csv')
except NameError:
    TREE_CSV = r"c:\Users\john\MemoryMachine\data\extracted_trees.csv"

def reconstruct_pershing_square_base():
    rs.EnableRedraw(False)
    
    # Create Context Layers
    rs.AddLayer("00_SITE::HARDSCAPE", (200, 200, 200))
    rs.AddLayer("00_SITE::ICONIC_GEO", (128, 0, 128))
    rs.AddLayer("00_SITE::SUBTERRANEAN_GARAGE", (60, 60, 60))
    rs.AddLayer("00_SITE::RAMPS", (100, 100, 100))
    rs.AddLayer("00_SITE::LANDSCAPE", (34, 139, 34))
    rs.AddLayer("00_SITE::WATER", (0, 150, 255))
    rs.AddLayer("06_LABELS", (255, 255, 255))
    
    # 1. Base plaza bounding (approx 330ft x 550ft block)
    plaza = rs.AddBox([[0,0,0], [330,0,0], [330,550,0], [0,550,0], [0,0,-10], [330,0,-10], [330,550,-10], [0,550,-10]])
    
    # 1b. The 3-Story Underground Parking Garage
    garage = rs.AddBox([[10, 10, -10], [320, 10, -10], [320, 540, -10], [10, 540, -10], [10, 10, -45], [320, 10, -45], [320, 540, -45], [10, 540, -45]])
    rs.ObjectLayer(garage, "00_SITE::SUBTERRANEAN_GARAGE")
    
    # 1c. The Entrance Ramps (Olive St & Hill St)
    ramp_west = rs.AddBox([[0, 150, 0], [25, 150, 0], [25, 300, 0], [0, 300, 0], [0, 150, -15], [25, 150, -15], [25, 300, -15], [0, 300, -15]])
    rs.ObjectLayer(ramp_west, "00_SITE::RAMPS")
    ramp_east = rs.AddBox([[305, 250, 0], [330, 250, 0], [330, 400, 0], [305, 400, 0], [305, 250, -15], [330, 250, -15], [330, 400, -15], [305, 400, -15]])
    rs.ObjectLayer(ramp_east, "00_SITE::RAMPS")
    
    # Carve the ramps out of the main plaza using Boolean Difference
    carved_plaza = rs.BooleanDifference(plaza, [ramp_west, ramp_east], delete_input=False)
    if carved_plaza:
        rs.DeleteObject(plaza)
        rs.ObjectLayer(carved_plaza, "00_SITE::HARDSCAPE")
    else:
        rs.ObjectLayer(plaza, "00_SITE::HARDSCAPE")
    
    # 2. Legorreta's Purple Campanile Tower (High-Fidelity with Cutout)
    campanile_base = rs.AddBox([[150, 250, 0], [170, 250, 0], [170, 270, 0], [150, 270, 0], [150, 250, 120], [170, 250, 120], [170, 270, 120], [150, 270, 120]])
    campanile_cutout = rs.AddBox([[152, 245, 90], [168, 245, 90], [168, 275, 90], [152, 275, 90], [152, 245, 110], [168, 245, 110], [168, 275, 110], [152, 275, 110]])
    campanile = rs.BooleanDifference(campanile_base, campanile_cutout, delete_input=False)
    if campanile:
        rs.DeleteObject(campanile_base)
        rs.DeleteObject(campanile_cutout)
        rs.ObjectLayer(campanile, "00_SITE::ICONIC_GEO")
        rs.ObjectColor(campanile, (128, 0, 128))
    else:
        rs.DeleteObject(campanile_cutout)
        rs.ObjectLayer(campanile_base, "00_SITE::ICONIC_GEO")
    
    # 3. Yellow Aqueduct Wall (High-Fidelity with Arches)
    wall_base = rs.AddBox([[160, 270, 0], [165, 270, 0], [165, 400, 0], [160, 400, 0], [160, 270, 25], [165, 270, 25], [165, 400, 25], [160, 400, 25]])
    arch_cutouts = []
    for y_pos in [290, 330, 370]:
        # Create cylinder along X axis to cut through the wall
        plane = rs.MovePlane(rs.WorldYZPlane(), [155, y_pos, 0])
        arch_cutouts.append(rs.AddCylinder(plane, 20, 8))
        
    wall = rs.BooleanDifference(wall_base, arch_cutouts, delete_input=False)
    if wall:
        rs.DeleteObject(wall_base)
        rs.DeleteObjects(arch_cutouts)
        rs.ObjectLayer(wall, "00_SITE::ICONIC_GEO")
        rs.ObjectColor(wall, (255, 200, 0))
    else:
        rs.DeleteObjects(arch_cutouts)
        rs.ObjectLayer(wall_base, "00_SITE::ICONIC_GEO")
    
    # 4. The Iconic Purple Sphere (Now with a concrete plinth)
    plinth = rs.AddBox([[146, 226, 0], [154, 226, 0], [154, 234, 0], [146, 234, 0], [146, 226, 2], [154, 226, 2], [154, 234, 2], [146, 234, 2]])
    rs.ObjectLayer(plinth, "00_SITE::HARDSCAPE")
    sphere = rs.AddSphere([150, 230, 10], 8)
    rs.ObjectLayer(sphere, "00_SITE::ICONIC_GEO")
    rs.ObjectColor(sphere, (128, 0, 128))

    # 5. Geometric Water Basin (High-Fidelity Recessed Rim)
    basin_base = rs.AddBox([[165, 270, 0], [210, 270, 0], [210, 400, 0], [165, 400, 0], [165, 270, 4], [210, 270, 4], [210, 400, 4], [165, 400, 4]])
    basin_void = rs.AddBox([[167, 272, 1], [208, 272, 1], [208, 398, 1], [167, 398, 1], [167, 272, 5], [208, 272, 5], [208, 398, 5], [167, 398, 5]])
    basin_rim = rs.BooleanDifference(basin_base, basin_void, delete_input=False)
    if basin_rim: 
        rs.DeleteObject(basin_base)
        rs.DeleteObject(basin_void)
        rs.ObjectLayer(basin_rim, "00_SITE::HARDSCAPE")
    else:
        rs.DeleteObject(basin_void)
        
    water_vol = rs.AddBox([[167, 272, 1], [208, 272, 1], [208, 398, 1], [167, 398, 1], [167, 272, 3], [208, 272, 3], [208, 398, 3], [167, 398, 3]])
    rs.ObjectLayer(water_vol, "00_SITE::WATER")

    # 5b. Yellow Colonnade Walkway
    colonnade_grp = []
    for x_pos in range(20, 140, 15):
        colonnade_grp.append(rs.AddCylinder(rs.MovePlane(rs.WorldXYPlane(), [x_pos, 450, 0]), 15, 1.5))
    colonnade_grp.append(rs.AddBox([[15, 448, 15], [145, 448, 15], [145, 452, 15], [15, 452, 15], [15, 448, 17], [145, 448, 17], [145, 452, 17], [15, 452, 17]]))
    
    rs.ObjectLayer(colonnade_grp, "00_SITE::ICONIC_GEO")
    for obj in colonnade_grp: rs.ObjectColor(obj, (255, 200, 0))

    # 6. Stepped Amphitheater / Seating
    for i in range(6):
        step_x = 210 + (i * 10)
        step_z = i * 2
        step = rs.AddBox([[step_x, 270, 0], [step_x+10, 270, 0], [step_x+10, 400, 0], [step_x, 400, 0], [step_x, 270, step_z+2], [step_x+10, 270, step_z+2], [step_x+10, 400, step_z+2], [step_x, 400, step_z+2]])
        rs.ObjectLayer(step, "00_SITE::HARDSCAPE")

    # 7. CV-Generated Landscape (from OpenCV extraction)
    if os.path.exists(TREE_CSV):
        trees = []
        with open(TREE_CSV, 'r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                tx, ty, tr = float(row['X']), float(row['Y']), float(row['Radius'])
                trunk = rs.AddCylinder(rs.MovePlane(rs.WorldXYPlane(), [tx, ty, 0]), 10, tr*0.2)
                canopy = rs.AddSphere([tx, ty, 10], tr)
                trees.extend([trunk, canopy])
        if trees:
            rs.ObjectLayer(trees, "00_SITE::LANDSCAPE")

    # 8. Yellow Transit Pavilion (Olive St side)
    pavilion = rs.AddBox([[10, 200, 0], [50, 200, 0], [50, 240, 0], [10, 240, 0], [10, 200, 18], [50, 200, 18], [50, 240, 18], [10, 240, 18]])
    rs.ObjectLayer(pavilion, "00_SITE::ICONIC_GEO")
    rs.ObjectColor(pavilion, (255, 200, 0))

    # 9. Geometric View-Framing Walls (Pink/Purple with cutouts)
    pink_wall_base = rs.AddBox([[80, 480, 0], [130, 480, 0], [130, 482, 0], [80, 482, 0], [80, 480, 20], [130, 480, 20], [130, 482, 20], [80, 482, 20]])
    circle_cutout_plane = rs.MovePlane(rs.WorldZXPlane(), [105, 475, 10])
    circle_cutout = rs.AddCylinder(circle_cutout_plane, 10, 6)
    pink_wall = rs.BooleanDifference(pink_wall_base, circle_cutout, delete_input=False)
    if pink_wall:
        rs.DeleteObject(pink_wall_base)
        rs.DeleteObject(circle_cutout)
        rs.ObjectLayer(pink_wall, "00_SITE::ICONIC_GEO")
        rs.ObjectColor(pink_wall, (255, 105, 180)) # Pink
    else:
        rs.DeleteObject(circle_cutout)
        rs.ObjectLayer(pink_wall_base, "00_SITE::ICONIC_GEO")
        
    purple_wall_base = rs.AddBox([[240, 420, 0], [242, 420, 0], [242, 470, 0], [240, 470, 0], [240, 420, 20], [242, 420, 20], [242, 470, 20], [240, 470, 20]])
    square_cutout = rs.AddBox([[235, 440, 5], [245, 440, 5], [245, 450, 5], [235, 450, 5], [235, 440, 15], [245, 440, 15], [245, 450, 15], [235, 450, 15]])
    purple_wall = rs.BooleanDifference(purple_wall_base, square_cutout, delete_input=False)
    if purple_wall:
        rs.DeleteObject(purple_wall_base)
        rs.DeleteObject(square_cutout)
        rs.ObjectLayer(purple_wall, "00_SITE::ICONIC_GEO")
        rs.ObjectColor(purple_wall, (128, 0, 128)) # Purple
    else:
        rs.DeleteObject(square_cutout)
        rs.ObjectLayer(purple_wall_base, "00_SITE::ICONIC_GEO")

    title_dot = rs.AddTextDot("Pershing Square Current Conditions", [160, 275, 125])
    rs.ObjectLayer(title_dot, "06_LABELS")
    
    rs.ZoomExtents()
    rs.EnableRedraw(True)
    print("✅ Base conditions for Pershing Square reconstructed. Ready for intervention.")
    
    # Take an automatic high-res screenshot of the viewport
    archive_dir = os.path.join(BASE_DIR, 'archive', 'render_output')
    if not os.path.exists(archive_dir):
        os.makedirs(archive_dir)
    capture_path = os.path.join(archive_dir, 'pershing_site_capture.png')
    
    # Use Rhino's command line to silently capture the view
    rs.Command('_-ViewCaptureToFile "{}" _Width=1920 _Height=1080 _TransparentBackground=_No _Enter'.format(capture_path))
    print("📸 Saved Rhino viewport capture to: {}".format(capture_path))

if __name__ == "__main__":
    reconstruct_pershing_square_base()