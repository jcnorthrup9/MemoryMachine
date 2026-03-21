# -*- coding: utf-8 -*-
import rhinoscriptsyntax as rs
import random

def generate_nakagin_tower():
    # Turn off redraw during generation for speed
    rs.EnableRedraw(False)
    
    # --- HARD DATA & PARAMETERS ---
    capsule_w = 2.5
    capsule_l = 4.0
    capsule_h = 2.5
    window_dia = 1.3
    
    core_w = 4.0
    floor_h = 3.0 # Approximate floor-to-floor height
    
    # Core A (11 stories), Core B (13 stories)
    # Total 140 capsules roughly split between them
    cores = [
        {"name": "Core A", "pos": (0, 0, 0), "floors": 11, "capsules": 60},
        {"name": "Core B", "pos": (9, 0, 0), "floors": 13, "capsules": 80}
    ]
    
    # --- 1. GENERATE THE CENTRAL CORES ---
    for c in cores:
        pt0 = (c["pos"][0] - core_w/2.0, c["pos"][1] - core_w/2.0, 0)
        pt1 = (c["pos"][0] + core_w/2.0, c["pos"][1] + core_w/2.0, c["floors"] * floor_h + 3)
        
        # 8 corners for the core bounding box
        core_box = rs.AddBox([
            (pt0[0], pt0[1], pt0[2]), (pt1[0], pt0[1], pt0[2]), 
            (pt1[0], pt1[1], pt0[2]), (pt0[0], pt1[1], pt0[2]),
            (pt0[0], pt0[1], pt1[2]), (pt1[0], pt0[1], pt1[2]), 
            (pt1[0], pt1[1], pt1[2]), (pt0[0], pt1[1], pt1[2])
        ])
        # Dark concrete color for the core
        rs.ObjectColor(core_box, (80, 80, 80)) 
        
    # --- 2. CAPSULE DISTRIBUTION LOGIC ---
    # Directions: North, East, South, West (dx, dy, rotation_degrees)
    directions = [
        (0, 1, 0),    
        (1, 0, -90),  
        (0, -1, 180), 
        (-1, 0, 90)   
    ]
    
    capsules_created = 0
    
    for c in cores:
        # Generate potential "slots" on the faces of the core
        available_slots = []
        
        # Start from floor 2 to leave ground clearance
        for f in range(2, c["floors"]):
            for d in directions:
                # Add 2 lateral attachment points per face to allow staggering
                available_slots.append((f, d, -0.6))
                available_slots.append((f, d, 0.6))
                
        # Shuffle slots so the placement looks organic and random
        random.shuffle(available_slots)
        
        # Attach capsules until we hit the capacity for this core
        for i in range(min(c["capsules"], len(available_slots))):
            slot = available_slots[i]
            floor = slot[0]
            d = slot[1]
            lateral_offset = slot[2]
            
            # Base anchor position on the core face
            cx = c["pos"][0] + (d[0] * core_w/2.0)
            cy = c["pos"][1] + (d[1] * core_w/2.0)
            cz = floor * floor_h
            
            # Add vertical height staggering
            cz += random.choice([0, 0.4, 0.8])
            
            # Add lateral staggering
            if d[1] != 0: # Pointing North/South
                cx += lateral_offset * capsule_w
            else:         # Pointing East/West
                cy += lateral_offset * capsule_w
            
            # --- 3. GENERATE THE CAPSULE GEOMETRY ---
            # Create at origin extending outwards in Y, then rotate/move
            pt0 = (-capsule_w/2.0, 0, 0)
            pt1 = (capsule_w/2.0, capsule_l, capsule_h)
            
            capsule_box = rs.AddBox([
                (pt0[0], pt0[1], pt0[2]), (pt1[0], pt0[1], pt0[2]), 
                (pt1[0], pt1[1], pt0[2]), (pt0[0], pt1[1], pt0[2]),
                (pt0[0], pt0[1], pt1[2]), (pt1[0], pt0[1], pt1[2]), 
                (pt1[0], pt1[1], pt1[2]), (pt0[0], pt1[1], pt1[2])
            ])
            
            # Draw the iconic 1.3m circular window on the outer face
            window_center = (0, capsule_l, capsule_h/2.0)
            window_plane = rs.PlaneFromNormal(window_center, (0, 1, 0))
            window = rs.AddCircle(window_plane, window_dia / 2.0)
            
            capsule_group = [capsule_box, window]
            
            # Apply rotation based on the face direction
            if d[2] != 0:
                capsule_group = rs.RotateObjects(capsule_group, (0,0,0), d[2], (0,0,1))
                
            # Move to the calculated attachment point
            capsule_group = rs.MoveObjects(capsule_group, (cx, cy, cz))
            
            # Light grey steel color for the capsule
            rs.ObjectColor(capsule_box, (200, 200, 200))
            
            capsules_created += 1

    rs.EnableRedraw(True)
    print("Success: Generated two cores and {} capsules.".format(capsules_created))

if __name__ == "__main__":
    generate_nakagin_tower()
