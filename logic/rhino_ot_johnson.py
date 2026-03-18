# -*- coding: utf-8 -*-
import rhinoscriptsyntax as rs
import csv
import os
import random

CSV_PATH = r"C:\Users\jcnor\MemoryMachine\data\ot_johnson_massing.csv"

def build_ot_johnson_space():
    rs.EnableRedraw(False)
    
    if not os.path.exists(CSV_PATH):
        print("CSV not found. Run ot_johnson_mapper.py first.")
        rs.EnableRedraw(True)
        return
        
    # Create base foundation and context layers
    rs.AddLayer("00_SITE")
    rs.AddLayer("00_SITE::CONTEXT")
    
    rs.AddLayer("06_LABELS")
    
    def create_box(name, x, y, z, dx, dy, dz, layer, color):
        """Helper function to quickly generate and label massing blocks"""
        pts = [
            [x, y, z], [x+dx, y, z], [x+dx, y+dy, z], [x, y+dy, z],
            [x, y, z+dz], [x+dx, y, z+dz], [x+dx, y+dy, z+dz], [x, y+dy, z+dz]
        ]
        box = rs.AddBox(pts)
        
        if color:
            # Create a material sub-layer to apply the render color safely
            sub_layer = layer + "::" + name.split(" ")[0]
            if not rs.IsLayer(layer): rs.AddLayer(layer)
            if not rs.IsLayer(sub_layer):
                rs.AddLayer(sub_layer, color)
                mat_idx = rs.AddMaterialToLayer(sub_layer)
                rs.MaterialColor(mat_idx, color)
            rs.ObjectLayer(box, sub_layer)
        else:
            if not rs.IsLayer(layer): rs.AddLayer(layer)
            rs.ObjectLayer(box, layer)
            
        dot = rs.AddTextDot(name, [x + (dx/2), y + (dy/2), z + dz + 2])
        rs.ObjectLayer(dot, "06_LABELS")
        return box
        
    def create_label(name, x, y, z):
        dot = rs.AddTextDot(name, [x, y, z])
        rs.ObjectLayer(dot, "06_LABELS")

    dims = {}
    with open(CSV_PATH, mode='r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            color_val = None
            if 'ColorR' in row and row['ColorR']:
                color_val = (int(row['ColorR']), int(row['ColorG']), int(row['ColorB']))
                
            dims[row['Element'].lower()] = {
                'dx': float(row['DimX']), 'dy': float(row['DimY']), 
                'dz': float(row['DimZ']), 'layer': row['Layer'],
                'color': color_val
            }

    # Safe getters for materials
    brick = dims.get('brick', {'layer': '05_FINISHES', 'color': (178,34,34)})
    stone = dims.get('facade', {'layer': '04_ENCLOSURE', 'color': (180,150,120)})
    glass = dims.get('window', {'layer': '04_ENCLOSURE', 'color': (173, 216, 230)})
    iron = dims.get('iron', {'layer': '04_ENCLOSURE', 'color': (50, 50, 50)})
    office = dims.get('office', {'layer': '01_INTERIOR', 'color': (255, 250, 240)})
    corridor = dims.get('corridor', {'layer': '01_INTERIOR', 'color': (220, 220, 220)})

    # 0. URBAN CONTEXT
    # Sidewalks
    create_box("Sidewalk - Broadway", -60, -15, -1, 175, 15, 1, "00_SITE", (200, 200, 200))
    create_box("Sidewalk - 4th St", 100, -15, -1, 15, 155, 1, "00_SITE", (200, 200, 200))
    
    # Streets
    create_box("Street - Broadway", -60, -45, -2, 265, 30, 1, "00_SITE", (100, 100, 100))
    create_box("Street - 4th St", 115, -45, -2, 30, 185, 1, "00_SITE", (100, 100, 100))
    
    # Adjacent Proxy Buildings
    create_box("Context Mass West", -60, 0, 0, 60, 80, 65, "00_SITE::CONTEXT", (180, 180, 180))
    create_box("Context Mass North", 0, 80, 0, 100, 60, 75, "00_SITE::CONTEXT", (180, 180, 180))
    create_box("Context Mass Across Bway", -60, -105, 0, 205, 60, 55, "00_SITE::CONTEXT", (180, 180, 180))
    create_box("Context Mass Across 4th", 145, -105, 0, 60, 245, 90, "00_SITE::CONTEXT", (180, 180, 180))
    
    # Base Plot
    create_box("Plot Foundation", 0, 0, -1, 100, 80, 1, "00_SITE", (150, 150, 150))

    # 1. GROUND FLOOR: Storefronts & Lobby
    create_box("Grand Marble Lobby", 40, 0, 0, 20, 40, 15, dims.get('lobby', {}).get('layer', '01_INTERIOR'), dims.get('lobby', {}).get('color', (240, 235, 225)))
    create_label("Lobby Entrance", 50, 5, 16)
    
    for x_pos in [0, 20, 60, 80]:
        create_box("Storefront Base", x_pos, 0, 0, 20, 2, 2, stone['layer'], stone['color'])
        create_box("Storefront Glass", x_pos+1, 1, 2, 18, 1, 13, glass['layer'], glass['color'])
        create_box("Cast Iron Column", x_pos, 0, 0, 1, 2, 15, iron['layer'], iron['color'])
        create_box("Cast Iron Column", x_pos+19, 0, 0, 1, 2, 15, iron['layer'], iron['color'])
        
    for y_pos in [0, 20, 40, 60]:
        create_box("Side Storefront Base", 98, y_pos, 0, 2, 20, 2, stone['layer'], stone['color'])
        create_box("Side Storefront Glass", 99, y_pos+1, 2, 1, 18, 13, glass['layer'], glass['color'])
        create_box("Side Cast Iron Column", 98, y_pos, 0, 2, 1, 15, iron['layer'], iron['color'])
        create_box("Side Cast Iron Column", 98, y_pos+19, 0, 2, 1, 15, iron['layer'], iron['color'])
    
    # 2. UPPER FLOORS: Romanesque Facade with Stepped Arches
    for floor in range(1, 7):
        z_base = 15 + (floor - 1) * 12
        
        # Floor slab & Interiors
        create_box("Floor Slab", 0, 0, z_base-1, 100, 80, 1, "02_STRUCTURE", (100, 100, 100))
        create_box("Central Corridor", 10, 35, z_base, 80, 10, 11, corridor['layer'], corridor['color'])
        create_box("Office Block Front", 10, 5, z_base, 80, 30, 11, office['layer'], office['color'])
        create_box("Office Block Rear", 10, 45, z_base, 80, 30, 11, office['layer'], office['color'])
        
        # Facade detailing
        for x_pos in range(0, 100, 20):
            create_box("Brick Pier", x_pos, -2, z_base, 4, 2, 12, brick['layer'], brick['color'])
            create_box("Stone Spandrel", x_pos+4, -2, z_base, 16, 2, 3, stone['layer'], stone['color'])
            
            if floor < 6:
                # Rectangular windows for mid floors
                create_box("Office Window", x_pos+5, -1, z_base+3, 14, 1, 8, glass['layer'], glass['color'])
            else:
                # Top floor: Romanesque Stepped Arches
                create_box("Arch Window", x_pos+5, -1, z_base+3, 14, 1, 6, glass['layer'], glass['color'])
                # Voxel Stepped Arch in Brick
                create_box("Arch Step 1", x_pos+4, -2, z_base+9, 16, 2, 1, brick['layer'], brick['color'])
                create_box("Arch Step 2", x_pos+5, -2, z_base+10, 14, 2, 1, brick['layer'], brick['color'])
                create_box("Arch Step 3", x_pos+7, -2, z_base+11, 10, 2, 1, brick['layer'], brick['color'])
                create_box("Arch Cap", x_pos+9, -2, z_base+12, 6, 2, 1, stone['layer'], stone['color']) # Keystone

        # Facade detailing - 4th Street (Side)
        for y_pos in range(0, 80, 20):
            create_box("Side Brick Pier", 100, y_pos, z_base, 2, 4, 12, brick['layer'], brick['color'])
            create_box("Side Stone Spandrel", 100, y_pos+4, z_base, 2, 16, 3, stone['layer'], stone['color'])
            
            if floor < 6:
                create_box("Side Office Window", 100, y_pos+5, z_base+3, 1, 14, 8, glass['layer'], glass['color'])
            else:
                create_box("Side Arch Window", 100, y_pos+5, z_base+3, 1, 14, 6, glass['layer'], glass['color'])
                create_box("Side Arch Step 1", 100, y_pos+4, z_base+9, 2, 16, 1, brick['layer'], brick['color'])
                create_box("Side Arch Step 2", 100, y_pos+5, z_base+10, 2, 14, 1, brick['layer'], brick['color'])
                create_box("Side Arch Step 3", 100, y_pos+7, z_base+11, 2, 10, 1, brick['layer'], brick['color'])
                create_box("Side Arch Cap", 100, y_pos+9, z_base+12, 2, 6, 1, stone['layer'], stone['color'])
                
        # Corner anchor block connecting the two facades
        create_box("Corner Brick Pier", 100, -2, z_base, 2, 2, 12, brick['layer'], brick['color'])

    # 3. CORNICE, ROOF & PARTY WALLS
    create_box("Front Romanesque Cornice", -2, -4, 87, 104, 4, 3, dims.get('cornice', {}).get('layer', '04_ENCLOSURE'), dims.get('cornice', {}).get('color', (150, 140, 130)))
    create_box("Side Romanesque Cornice", 102, -4, 87, 4, 84, 3, dims.get('cornice', {}).get('layer', '04_ENCLOSURE'), dims.get('cornice', {}).get('color', (150, 140, 130)))
    create_box("Roof Mass", 0, 0, 87, 100, 80, 2, "02_STRUCTURE", (80, 80, 80))
    
    # Historical Context: adjacent shared walls
    create_box("Rear Party Wall", -2, 80, 0, 104, 2, 87, brick['layer'], brick['color'])
    create_box("West Party Wall", -2, 0, 0, 2, 80, 87, brick['layer'], brick['color'])
    
    # 4. VERTICAL CIRCULATION
    if 'elevator' in dims: 
        create_box("Elevator Core", 45, 35, 0, dims['elevator']['dx'], dims['elevator']['dy'], 87, dims['elevator']['layer'], dims['elevator']['color'])
        create_label("Historic Elevator Core", 45 + dims['elevator']['dx']/2, 35 + dims['elevator']['dy']/2, 89)
    if 'staircase' in dims: 
        create_box("Grand Staircase", 30, 35, 0, dims['staircase']['dx'], dims['staircase']['dy'], 87, dims['staircase']['layer'], dims['staircase']['color'])

    rs.ZoomExtents()
    rs.EnableRedraw(True)

if __name__ == "__main__":
    build_ot_johnson_space()