# -*- coding: utf-8 -*-
import rhinoscriptsyntax as rs
import csv
import os
import random

CSV_PATH = r"D:\MemoryMachine\data\bottega_massing.csv"

def build_bottega_space():
    rs.EnableRedraw(False)
    
    if not os.path.exists(CSV_PATH):
        print("CSV not found. Run spatial_mapper.py first.")
        rs.EnableRedraw(True)
        return
        
    # Create base foundation
    rs.AddLayer("00_SITE")
    # Expanded the site to a 100x150 rectangle to fit a large restaurant layout
    site_srf = rs.AddPlaneSurface(rs.WorldXYPlane(), 100, 150)
    rs.ObjectLayer(site_srf, "00_SITE")
    
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

    dims = {}
    with open(CSV_PATH, mode='r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            color_val = None
            if 'ColorR' in row and row['ColorR']:
                color_val = (int(row['ColorR']), int(row['ColorG']), int(row['ColorB']))
                
            # Store dimensions in a dictionary so we can call them by name
            dims[row['Element'].lower()] = {
                'dx': float(row['DimX']), 'dy': float(row['DimY']), 
                'dz': float(row['DimZ']), 'layer': row['Layer'],
                'color': color_val
            }

    # --- 1. FRONT RIGHT: Patisserie & Macaron Displays ---
    if 'display' in dims:
        d = dims['display']
        create_box("Patisserie Display 1", 65, 10, 0, d['dx'], d['dy'], d['dz'], d['layer'], d['color'])
        create_box("Patisserie Display 2", 65, 20, 0, d['dx'], d['dy'], d['dz'], d['layer'], d['color'])

    # --- 2. FRONT LEFT: Full Bar Area ---
    if 'bar' in dims:
        d = dims['bar']
        # Rotated to run long-ways down the left wall
        create_box("Cocktail Bar", 10, 10, 0, d['dy'], d['dx'], d['dz'], d['layer'], d['color']) 

    # --- 3. MIDDLE: Expansive Dining Seating ---
    if 'seating' in dims:
        d = dims['seating']
        # Distribute a grid of tables with slight organic randomization
        for i in range(4):
            for j in range(5):
                x_pos = 25 + (i * 15)
                y_pos = 45 + (j * 15)
                create_box("Dining Table", x_pos + random.uniform(-2, 2), y_pos + random.uniform(-2, 2), 0, d['dx'], d['dy'], d['dz'], d['layer'], d['color'])

    # --- 4. BACK: Open Kitchen & Wood-Fired Pizza Oven ---
    if 'kitchen' in dims:
        d = dims['kitchen']
        create_box("Open Kitchen", 25, 125, 0, d['dx'], d['dy'], d['dz'], d['layer'], d['color'])
    if 'oven' in dims:
        d = dims['oven']
        create_box("Wood-Fired Pizza Oven", 60, 125, 0, d['dx'], d['dy'], d['dz'], d['layer'], d['color'])
    elif 'kitchen' in dims: # Fallback if oven wasn't explicitly found
        create_box("Wood-Fired Pizza Oven", 60, 125, 0, 10, 10, 8, dims['kitchen']['layer'], dims['kitchen']['color'])

    # --- 5. BACK CORNER: Fancy Restrooms ---
    if 'bathroom' in dims:
        d = dims['bathroom']
        create_box("Marble Restrooms", 5, 135, 0, d['dx'], d['dy'], d['dz'], d['layer'], d['color'])

    # --- 6. ARCHITECTURAL SHELL ---
    if 'marble' in dims: create_box("Marble Floor", 0, 0, -1, 100, 150, 1, dims['marble']['layer'], dims['marble']['color'])
    if 'window' in dims: create_box("Glass Facade", 0, -1, 0, 100, 1, 15, dims['window']['layer'], dims['window']['color'])
    if 'ceiling' in dims: create_box("High Ceiling (Echo Chamber)", 0, 0, 20, 100, 150, 2, dims['ceiling']['layer'], dims['ceiling']['color'])
            
    # --- 7. DECORATIVE & SPECIFIC FIXTURES ---
    if 'patisserie' in dims:
        d = dims['patisserie']
        create_box("Patisserie Counter", 65, 30, 0, d['dx'], d['dy'], d['dz'], d['layer'], d['color'])
        
    if 'flower' in dims:
        d = dims['flower']
        create_box("Entrance Flowers (L)", 40, 5, 0, d['dx'], d['dy'], d['dz'], d['layer'], d['color'])
        create_box("Entrance Flowers (R)", 55, 5, 0, d['dx'], d['dy'], d['dz'], d['layer'], d['color'])
        
    if 'wall' in dims:
        d = dims['wall']
        create_box("White Wall (West)", 0, 0, 0, d['dx'], 150, d['dz'], d['layer'], d['color'])
        create_box("White Wall (East)", 100-d['dx'], 0, 0, d['dx'], 150, d['dz'], d['layer'], d['color'])

    if 'door' in dims:
        d = dims['door']
        # Placing main wooden doors at the entryway
        create_box(">> MAIN ENTRANCE <<", 46, -1, 0, d['dx'], d['dy'], d['dz'], d['layer'], d['color'])
        create_box("Secondary Door", 54, -1, 0, d['dx'], d['dy'], d['dz'], d['layer'], d['color'])
    else:
        # Fallback to ensure the entrance is always explicitly marked
        create_box(">> MAIN ENTRANCE <<", 46, -1, 0, 8, 1, 10, "04_ENCLOSURE", (139, 69, 19))
        
    if 'beam' in dims:
        d = dims['beam']
        # Placing exposed structural beams across the high ceiling
        for i in range(5):
            create_box("Exposed Beam {}".format(i+1), 20 + (i*15), 0, 19, d['dx'], 150, d['dz'], d['layer'], d['color'])

    rs.ZoomExtents()
    rs.EnableRedraw(True)

if __name__ == "__main__":
    build_bottega_space()