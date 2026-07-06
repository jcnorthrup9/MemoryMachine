import rhinoscriptsyntax as rs
import os
import sys

def create_detailed_interior():
    # Setup Layer
    layer = "MEM_INTERIOR_DETAILED"
    if not rs.IsLayer(layer):
        rs.AddLayer(layer, (210, 105, 30)) # Burnt Orange
    rs.CurrentLayer(layer)
    rs.EnableRedraw(False)

    # ---------------------------------------------------------
    # 1. THE VELVET COUCH (Procedural Generation)
    # ---------------------------------------------------------
    # Location: Against the wall at X=52, Y=53.33 (North-East corner of living room)
    # Facing South (-Y)
    origin = [52, 50.5, 0] 
    width = 7.0
    depth = 2.8
    seat_h = 1.5
    back_h = 3.0
    
    # Legs (Teak wood style)
    leg_radius = 0.15
    leg_h = 0.5
    legs = [
        [origin[0] + 0.5, origin[1] + 0.5, 0],
        [origin[0] + width - 0.5, origin[1] + 0.5, 0],
        [origin[0] + 0.5, origin[1] + depth - 0.5, 0],
        [origin[0] + width - 0.5, origin[1] + depth - 0.5, 0]
    ]
    for pt in legs:
        rs.AddCylinder(pt, leg_h, leg_radius)

    # Main Base
    base_geo = rs.AddBox([
        (origin[0], origin[1], leg_h), (origin[0]+width, origin[1], leg_h),
        (origin[0]+width, origin[1]+depth, leg_h), (origin[0], origin[1]+depth, leg_h),
        (origin[0], origin[1], seat_h), (origin[0]+width, origin[1], seat_h),
        (origin[0]+width, origin[1]+depth, seat_h), (origin[0], origin[1]+depth, seat_h)
    ])

    # Backrest (Angled slightly)
    back_thickness = 0.8
    rs.AddBox([
        (origin[0], origin[1]+depth-back_thickness, seat_h), 
        (origin[0]+width, origin[1]+depth-back_thickness, seat_h),
        (origin[0]+width, origin[1]+depth, seat_h), 
        (origin[0], origin[1]+depth, seat_h),
        (origin[0], origin[1]+depth-back_thickness, back_h), 
        (origin[0]+width, origin[1]+depth-back_thickness, back_h),
        (origin[0]+width, origin[1]+depth, back_h), 
        (origin[0], origin[1]+depth, back_h)
    ])

    # Armrests (Cylindrical/Rolled style)
    arm_w = 0.6
    arm_h = 2.2
    # Left Arm
    rs.AddBox([
        (origin[0], origin[1], seat_h), (origin[0]+arm_w, origin[1], seat_h),
        (origin[0]+arm_w, origin[1]+depth-back_thickness, seat_h), (origin[0], origin[1]+depth-back_thickness, seat_h),
        (origin[0], origin[1], arm_h), (origin[0]+arm_w, origin[1], arm_h),
        (origin[0]+arm_w, origin[1]+depth-back_thickness, arm_h), (origin[0], origin[1]+depth-back_thickness, arm_h)
    ])
    # Right Arm
    rs.AddBox([
        (origin[0]+width-arm_w, origin[1], seat_h), (origin[0]+width, origin[1], seat_h),
        (origin[0]+width, origin[1]+depth-back_thickness, seat_h), (origin[0]+width-arm_w, origin[1]+depth-back_thickness, seat_h),
        (origin[0]+width-arm_w, origin[1], arm_h), (origin[0]+width, origin[1], arm_h),
        (origin[0]+width, origin[1]+depth-back_thickness, arm_h), (origin[0]+width-arm_w, origin[1]+depth-back_thickness, arm_h)
    ])

    # Cushions (3 individual seat cushions)
    cushion_w = (width - (2*arm_w)) / 3
    for i in range(3):
        x_pos = origin[0] + arm_w + (i * cushion_w) + 0.05
        rs.AddBox([
            (x_pos, origin[1], seat_h), (x_pos + cushion_w - 0.1, origin[1], seat_h),
            (x_pos + cushion_w - 0.1, origin[1]+depth-back_thickness, seat_h), (x_pos, origin[1]+depth-back_thickness, seat_h),
            (x_pos, origin[1], seat_h+0.3), (x_pos + cushion_w - 0.1, origin[1], seat_h+0.3),
            (x_pos + cushion_w - 0.1, origin[1]+depth-back_thickness, seat_h+0.3), (x_pos, origin[1]+depth-back_thickness, seat_h+0.3)
        ])

    # ---------------------------------------------------------
    # 2. MILK CRATE & TV
    # ---------------------------------------------------------
    # Crate (Grid pattern simulated by wireframe box for now, or simple box with holes)
    crate_origin = [54, 41, 0]
    rs.AddBox([
        (54, 41, 0), (55.1, 41, 0), (55.1, 42.1, 0), (54, 42.1, 0),
        (54, 41, 1.0), (55.1, 41, 1.0), (55.1, 42.1, 1.0), (54, 42.1, 1.0)
    ])
    
    rs.EnableRedraw(True)
    print("Detailed interior generated.")

if __name__ == "__main__":
    create_detailed_interior()
