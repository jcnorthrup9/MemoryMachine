import rhinoscriptsyntax as rs

def build_pershing_base():
    # Primary Plaza Deck (The Lid)
    plaza_id = rs.AddPlaneSurface(rs.WorldXYPlane(), 110, 150)
    
    # Subterranean Void (Parking Garage approximation)
    rs.MoveObject(rs.CopyObject(plaza_id), [0,0,-12])
    
    # Ramps and Stairs Logic
    # (Simplified: creating the perimeter "walls" that define the current sunken nature)
    rs.AddBox([[0,0,0], [110,0,0], [110,5,3], [0,5,3]]) 
    print("Base Site Constraints Generated.")

# build_pershing_base()