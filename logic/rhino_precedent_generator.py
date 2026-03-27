try:
    import rhinoscriptsyntax as rs
except ImportError:
    rs = None

import os
import random

def create_kinetic_mast(origin):
    """Generates a simplified kinetic mast like at Schouwburgplein."""
    rs.EnableRedraw(False)
    mast_height = 30
    arm_length = 15
    
    # Mast
    mast = rs.AddCylinder(origin, mast_height, 0.5)
    
    # Articulated Arm
    arm_origin = rs.PointAdd(origin, (0, 0, mast_height))
    arm_end = rs.PointAdd(arm_origin, (arm_length, 0, 0))
    arm = rs.AddLine(arm_origin, arm_end)
    rs.RotateObject(arm, arm_origin, random.uniform(0, 360))
    
    light = rs.AddSphere(rs.CurveEndPoint(arm), 0.8)
    
    group = rs.AddGroup()
    rs.AddObjectsToGroup([mast, arm, light], group)
    print("Generated: Kinetic Mast")
    return group

def create_wadable_pool(origin):
    """Generates a simplified pink wading pool like at Grand Park."""
    pool_width = 25
    pool_length = 40
    
    curve = rs.AddRectangle(rs.PlaneFromPoints(origin, rs.PointAdd(origin, (pool_width, 0, 0)), rs.PointAdd(origin, (0, pool_length, 0))), pool_width, pool_length)
    surface = rs.AddPlanarSrf(curve)
    rs.DeleteObject(curve)
    
    if surface:
        rs.ObjectColor(surface, (255, 105, 180)) # Hot Pink
        print("Generated: Wadable Pool")
        return surface
    return None

def create_art_wall(origin):
    """Generates a textured boundary wall like at Tanner Springs."""
    points = [origin]
    for i in range(1, 10):
        pt = rs.PointAdd(origin, (i * 5, random.uniform(-5, 5), 0))
        points.append(pt)
    
    curve = rs.AddCurve(points)
    wall = rs.ExtrudeCurveStraight(curve, (0,0,0), (0,0,8))
    rs.DeleteObject(curve)
    print("Generated: Art Wall")
    return wall

def create_supertree(origin):
    """Generates a simplified Supertree structure."""
    trunk_height = 45
    trunk_radius = 2.5
    canopy_radius = 12
    
    trunk = rs.AddCylinder(origin, trunk_height, trunk_radius)
    canopy_center = rs.PointAdd(origin, (0, 0, trunk_height))
    canopy = rs.AddCylinder(canopy_center, 2, canopy_radius)
    
    group = rs.AddGroup()
    rs.AddObjectsToGroup([trunk, canopy], group)
    print("Generated: Supertree")
    return group

def create_graphic_plaza(origin):
    """Generates a plaza with graphic stripes like at Superkilen."""
    plane = rs.AddPlaneSurface(rs.WorldXYPlane(), 50, 50)
    rs.MoveObject(plane, origin)
    
    # Add stripes as simple lines for concept
    for i in range(0, 51, 2):
        start = rs.PointAdd(origin, (i, 0, 0.1))
        end = rs.PointAdd(origin, (i, 50, 0.1))
        rs.AddLine(start, end)
        
    print("Generated: Graphic Plaza")
    return plane

def generate_all_precedents():
    """Main function to generate and arrange all precedent objects."""
    rs.DeleteObjects(rs.AllObjects())
    spacing = 60
    
    create_kinetic_mast([0, spacing * 0, 0])
    create_wadable_pool([spacing * 1, 0, 0])
    create_art_wall([spacing * 2, 0, 0])
    create_supertree([spacing * 3, 0, 0])
    create_graphic_plaza([spacing * 4, 0, 0])
    
    rs.ZoomExtents()
    rs.EnableRedraw(True)
    print("--- Precedent Generation Complete ---")

if __name__ == "__main__":
    if rs is not None:
        generate_all_precedents()
    else:
        print("Standard Python detected. Dispatching to Rhino via COM...")
        try:
            import win32com.client
            try:
                rhino = win32com.client.dynamic.Dispatch("Rhino.Interface.8")
            except:
                rhino = win32com.client.dynamic.Dispatch("Rhino.Application")
            
            try:
                rs_app = rhino.GetScriptObject()
            except:
                rs_app = rhino

            script_path = os.path.abspath(__file__)
            cmd = f'_-ScriptEditor Run "{script_path}"'
            
            if hasattr(rs_app, "RunScript"):
                rs_app.RunScript(cmd, 1)
            else:
                rhino.RunScript(cmd, 1)
            print("✅ Command sent to Rhino.")
        except Exception as e:
            print(f"❌ Error: {e}")
            print("Ensure Rhino is running and 'pip install pywin32' is executed in this venv.")