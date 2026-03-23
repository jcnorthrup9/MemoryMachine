# -*- coding: utf-8 -*-
import rhinoscriptsyntax as rs
import csv
import os
import random

def build_universal_space():
    rs.EnableRedraw(False)
    
    data_folder = r"c:\Users\john\MemoryMachine\data"
    # Prompt you to pick ANY generated CSV file
    csv_path = rs.OpenFileName("Select Massing CSV Blueprint", "CSV Files (*.csv)|*.csv||", data_folder)
    if not csv_path or not os.path.exists(csv_path):
        print("No CSV selected or found.")
        rs.EnableRedraw(True)
        return
        
    rs.AddLayer("00_SITE")
    site_srf = rs.AddPlaneSurface(rs.WorldXYPlane(), 200, 200)
    rs.ObjectLayer(site_srf, "00_SITE")
    rs.AddLayer("06_LABELS")
    
    x_offset, y_offset = 0, 0
    
    with open(csv_path, mode='r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            element = row['Element'].lower()
            instances = int(row['Instances'])
            dx, dy, dz = float(row['DimX']), float(row['DimY']), float(row['DimZ'])
            layer = row['Layer']
            
            color = None
            if row.get('ColorR') and row['ColorR'].strip():
                color = (int(row['ColorR']), int(row['ColorG']), int(row['ColorB']))
                
            for i in range(instances):
                # Introduce slight organic scattering for plural elements (e.g., forests)
                scatter_x = x_offset + random.uniform(-3, 3) if instances > 1 else x_offset
                scatter_y = y_offset + random.uniform(-3, 3) if instances > 1 else y_offset
                
                geo = []
                base_plane = rs.MovePlane(rs.WorldXYPlane(), [scatter_x + dx/2, scatter_y + dy/2, 0])
                
                # Procedural Geometry based on Element Name
                if "tree" in element:
                    trunk = rs.AddCylinder(base_plane, dz * 0.4, dx * 0.1)
                    canopy = rs.AddSphere([scatter_x + dx/2, scatter_y + dy/2, dz * 0.6], dx/2)
                    geo.extend([trunk, canopy])
                elif "water" in element or "grass" in element:
                    geo.append(rs.AddCylinder(base_plane, dz, dx/2))
                elif "canopy" in element or "pavilion" in element:
                    col1 = rs.AddCylinder(rs.MovePlane(rs.WorldXYPlane(), [scatter_x+1, scatter_y+1, 0]), dz, 0.5)
                    col2 = rs.AddCylinder(rs.MovePlane(rs.WorldXYPlane(), [scatter_x+dx-1, scatter_y+1, 0]), dz, 0.5)
                    col3 = rs.AddCylinder(rs.MovePlane(rs.WorldXYPlane(), [scatter_x+1, scatter_y+dy-1, 0]), dz, 0.5)
                    col4 = rs.AddCylinder(rs.MovePlane(rs.WorldXYPlane(), [scatter_x+dx-1, scatter_y+dy-1, 0]), dz, 0.5)
                    roof = rs.AddBox([ [scatter_x, scatter_y, dz], [scatter_x+dx, scatter_y, dz], [scatter_x+dx, scatter_y+dy, dz], [scatter_x, scatter_y+dy, dz],
                                       [scatter_x, scatter_y, dz+1], [scatter_x+dx, scatter_y, dz+1], [scatter_x+dx, scatter_y+dy, dz+1], [scatter_x, scatter_y+dy, dz+1] ])
                    geo.extend([col1, col2, col3, col4, roof])
                else:
                    # Default to Box Massing
                    pts = [ [scatter_x, scatter_y, 0], [scatter_x+dx, scatter_y, 0], [scatter_x+dx, scatter_y+dy, 0], [scatter_x, scatter_y+dy, 0],
                            [scatter_x, scatter_y, dz], [scatter_x+dx, scatter_y, dz], [scatter_x+dx, scatter_y+dy, dz], [scatter_x, scatter_y+dy, dz] ]
                    geo.append(rs.AddBox(pts))
                
                # Assign to highly organized layers
                sub_layer = layer + "::" + element.capitalize()
                if not rs.IsLayer(layer): rs.AddLayer(layer)
                if not rs.IsLayer(sub_layer): rs.AddLayer(sub_layer, color if color else (150,150,150))
                rs.ObjectLayer(geo, sub_layer)
                    
                dot = rs.AddTextDot("{} {}".format(element.capitalize(), i+1), [scatter_x + (dx/2), scatter_y + (dy/2), dz + 2])
                rs.ObjectLayer(dot, "06_LABELS")
                
                # Shift position to create a neat layout
                x_offset += dx + 10
                if x_offset > 180:
                    x_offset = 0
                    y_offset += dy + 20

    rs.ZoomExtents()
    rs.EnableRedraw(True)

if __name__ == "__main__":
    build_universal_space()