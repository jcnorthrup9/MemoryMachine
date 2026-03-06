# -*- coding: utf-8 -*-
import rhinoscriptsyntax as rs
import csv
import os

CSV_PATH = r"D:\MemoryMachine\data\1988_trailer_spatial.csv"
MODEL_DIR = r"D:\MemoryMachine\archive\assets\models"

def generate_3d_massing():
    rs.EnableRedraw(False)
    
    rs.AddLayer("00_SITE")
    rs.AddLayer("01_PROXY_MASSING")
    rs.AddLayer("02_IMPORTED_ASSETS")
    rs.AddLayer("03_LABELS")
    
    site_srf = rs.AddPlaneSurface(rs.WorldXYPlane(), 100, 60)
    rs.ObjectLayer(site_srf, "00_SITE")
    
    if not os.path.exists(CSV_PATH):
        rs.EnableRedraw(True)
        return

    try:
        with open(CSV_PATH, mode='r') as f:
            reader = csv.DictReader(f)
            x_pos, y_pos = 20, 10 
            
            for row in reader:
                element = row.get('Element')
                if not element: continue
                    
                obj_path = os.path.join(MODEL_DIR, element + ".obj")
                created_objs = []
                target_layer = ""
                
                if os.path.exists(obj_path):
                    rs.Command('_-Import "{}" _Enter'.format(obj_path))
                    last_objs = rs.LastCreatedObjects()
                    if last_objs:
                        rs.MoveObjects(last_objs, [x_pos, y_pos, 0])
                        created_objs.extend(last_objs)
                        target_layer = "02_IMPORTED_ASSETS"
                else:
                    proxy = None
                    if "trailer_mass" in element:
                        proxy = rs.AddBox([[20,10,0], [80,10,0], [80,34,0], [20,34,0], [20,10,10], [80,10,10], [80,34,10], [20,34,10]])
                    elif "tree" in element:
                        trunk = rs.AddCylinder(rs.WorldXYPlane(), 10, 1.5)
                        canopy = rs.AddSphere([0, 0, 10], 6)
                        proxy = [trunk, canopy]
                        rs.MoveObjects(proxy, [x_pos, y_pos + 30, 0])
                    elif "couch" in element:
                        proxy = rs.AddBox([[x_pos, y_pos, 0], [x_pos+7, y_pos, 0], [x_pos+7, y_pos+3, 0], [x_pos, y_pos+3, 0],
                                   [x_pos, y_pos, 3], [x_pos+7, y_pos, 3], [x_pos+7, y_pos+3, 3], [x_pos, y_pos+3, 3]])
                    elif "swingset" in element:
                        proxy = rs.AddBox([[x_pos, y_pos+20, 0], [x_pos+10, y_pos+20, 0], [x_pos+10, y_pos+25, 0], [x_pos, y_pos+25, 0],
                                   [x_pos, y_pos+20, 8], [x_pos+10, y_pos+20, 8], [x_pos+10, y_pos+25, 8], [x_pos, y_pos+25, 8]])
                    
                    if proxy:
                        if isinstance(proxy, list): created_objs.extend(proxy)
                        else: created_objs.append(proxy)
                        target_layer = "01_PROXY_MASSING"

                if created_objs:
                    for obj in created_objs:
                        rs.ObjectName(obj, element)
                        rs.ObjectLayer(obj, target_layer)
                    
                    bbox = rs.BoundingBox(created_objs)
                    if bbox:
                        top_center = (bbox[4] + bbox[5] + bbox[6] + bbox[7]) / 4
                        dot_pt = [top_center[0], top_center[1], top_center[2] + 2]
                        dot = rs.AddTextDot(element, dot_pt)
                        rs.ObjectLayer(dot, "03_LABELS")

                x_pos += 5 

    except Exception as e:
        print("❌ ERROR: " + str(e))

    rs.ZoomExtents()
    rs.EnableRedraw(True)

if __name__ == "__main__":
    generate_3d_massing()