import rhinoscriptsyntax as rs

def draw_diagram_schouwburgplein(offset_x=0, offset_y=0):
    rs.EnableRedraw(False)
    original_layer = rs.CurrentLayer()

    if not rs.IsLayer('Diagram::01_Plaza'): rs.AddLayer('Diagram::01_Plaza')
    rs.CurrentLayer('Diagram::01_Plaza')
    pts = [(36.38 + offset_x, 0.00 + offset_y, 0.00), (36.95 + offset_x, 30.77 + offset_y, 0.00), (52.42 + offset_x, 41.94 + offset_y, 0.00), (70.76 + offset_x, 55.00 + offset_y, 0.00), (79.06 + offset_x, 62.91 + offset_y, 0.00), (95.10 + offset_x, 69.44 + offset_y, 0.00), (113.72 + offset_x, 76.14 + offset_y, 0.00), (139.79 + offset_x, 78.55 + offset_y, 0.00), (152.40 + offset_x, 78.55 + offset_y, 0.00), (165.57 + offset_x, 76.83 + offset_y, 0.00), (183.91 + offset_x, 72.70 + offset_y, 0.00), (205.39 + offset_x, 66.34 + offset_y, 0.00), (220.86 + offset_x, 60.84 + offset_y, 0.00), (232.61 + offset_x, 50.02 + offset_y, 0.00), (238.91 + offset_x, 39.02 + offset_y, 0.00), (243.20 + offset_x, 28.02 + offset_y, 0.00), (241.77 + offset_x, 16.84 + offset_y, 0.00), (225.44 + offset_x, 10.14 + offset_y, 0.00), (203.39 + offset_x, 3.78 + offset_y, 0.00), (178.75 + offset_x, 1.89 + offset_y, 0.00), (148.39 + offset_x, 3.44 + offset_y, 0.00), (116.59 + offset_x, 3.78 + offset_y, 0.00), (84.51 + offset_x, 2.06 + offset_y, 0.00), (59.30 + offset_x, 0.34 + offset_y, 0.00), (36.38 + offset_x, 0.00 + offset_y, 0.00)]
    if len(pts) > 1:
        if len(pts) > 2: pts.append(pts[0])
        rs.AddPolyline(pts)

    if not rs.IsLayer('Diagram::02_Vegetation'): rs.AddLayer('Diagram::02_Vegetation')
    rs.CurrentLayer('Diagram::02_Vegetation')
    pts = [(23.78 + offset_x, 68.58 + offset_y, 0.00), (18.62 + offset_x, 66.17 + offset_y, 0.00), (18.33 + offset_x, 58.95 + offset_y, 0.00), (19.77 + offset_x, 50.70 + offset_y, 0.00), (21.77 + offset_x, 41.42 + offset_y, 0.00), (24.64 + offset_x, 32.83 + offset_y, 0.00), (27.50 + offset_x, 23.38 + offset_y, 0.00), (29.79 + offset_x, 13.58 + offset_y, 0.00), (31.80 + offset_x, 5.16 + offset_y, 0.00), (33.80 + offset_x, 2.06 + offset_y, 0.00), (38.67 + offset_x, 2.06 + offset_y, 0.00), (34.95 + offset_x, 11.69 + offset_y, 0.00), (31.80 + offset_x, 21.14 + offset_y, 0.00), (28.93 + offset_x, 31.80 + offset_y, 0.00), (25.78 + offset_x, 44.52 + offset_y, 0.00), (23.78 + offset_x, 57.23 + offset_y, 0.00), (23.78 + offset_x, 68.58 + offset_y, 0.00)]
    if len(pts) > 1:
        if len(pts) > 2: pts.append(pts[0])
        rs.AddPolyline(pts)

    if not rs.IsLayer('Diagram::02_Vegetation'): rs.AddLayer('Diagram::02_Vegetation')
    rs.CurrentLayer('Diagram::02_Vegetation')
    pts = [(92.81 + offset_x, 19.08 + offset_y, 0.00), (94.25 + offset_x, 44.52 + offset_y, 0.00), (134.35 + offset_x, 48.81 + offset_y, 0.00), (137.79 + offset_x, 22.86 + offset_y, 0.00), (92.81 + offset_x, 19.08 + offset_y, 0.00)]
    if len(pts) > 1:
        if len(pts) > 2: pts.append(pts[0])
        rs.AddPolyline(pts)

    if not rs.IsLayer('Diagram::02_Vegetation'): rs.AddLayer('Diagram::02_Vegetation')
    rs.CurrentLayer('Diagram::02_Vegetation')
    pts = [(154.12 + offset_x, 83.36 + offset_y, 0.00), (156.69 + offset_x, 88.00 + offset_y, 0.00), (167.87 + offset_x, 86.97 + offset_y, 0.00), (165.57 + offset_x, 82.67 + offset_y, 0.00), (154.12 + offset_x, 83.36 + offset_y, 0.00)]
    if len(pts) > 1:
        if len(pts) > 2: pts.append(pts[0])
        rs.AddPolyline(pts)

    if not rs.IsLayer('Diagram::02_Vegetation'): rs.AddLayer('Diagram::02_Vegetation')
    rs.CurrentLayer('Diagram::02_Vegetation')
    pts = [(190.50 + offset_x, 81.30 + offset_y, 0.00), (192.50 + offset_x, 88.52 + offset_y, 0.00), (202.24 + offset_x, 86.97 + offset_y, 0.00), (200.24 + offset_x, 80.61 + offset_y, 0.00), (190.50 + offset_x, 81.30 + offset_y, 0.00)]
    if len(pts) > 1:
        if len(pts) > 2: pts.append(pts[0])
        rs.AddPolyline(pts)

    if not rs.IsLayer('Diagram::02_Vegetation'): rs.AddLayer('Diagram::02_Vegetation')
    rs.CurrentLayer('Diagram::02_Vegetation')
    pts = [(30.94 + offset_x, 74.77 + offset_y, 0.00), (33.80 + offset_x, 82.67 + offset_y, 0.00), (52.71 + offset_x, 84.91 + offset_y, 0.00), (53.85 + offset_x, 78.55 + offset_y, 0.00), (30.94 + offset_x, 74.77 + offset_y, 0.00)]
    if len(pts) > 1:
        if len(pts) > 2: pts.append(pts[0])
        rs.AddPolyline(pts)

    if not rs.IsLayer('Diagram::03_Paths'): rs.AddLayer('Diagram::03_Paths')
    rs.CurrentLayer('Diagram::03_Paths')
    pts = [(57.58 + offset_x, 76.31 + offset_y, 0.00), (69.61 + offset_x, 78.55 + offset_y, 0.00), (89.66 + offset_x, 80.61 + offset_y, 0.00), (109.43 + offset_x, 80.61 + offset_y, 0.00), (129.19 + offset_x, 80.61 + offset_y, 0.00), (149.25 + offset_x, 78.55 + offset_y, 0.00), (169.01 + offset_x, 74.25 + offset_y, 0.00), (189.06 + offset_x, 69.95 + offset_y, 0.00), (208.83 + offset_x, 63.59 + offset_y, 0.00)]
    if len(pts) > 1:
        rs.AddPolyline(pts)

    if not rs.IsLayer('Diagram::03_Paths'): rs.AddLayer('Diagram::03_Paths')
    rs.CurrentLayer('Diagram::03_Paths')
    pts = [(38.67 + offset_x, 68.92 + offset_y, 0.00), (40.68 + offset_x, 55.17 + offset_y, 0.00), (42.68 + offset_x, 40.39 + offset_y, 0.00), (44.69 + offset_x, 23.38 + offset_y, 0.00), (45.83 + offset_x, 12.72 + offset_y, 0.00)]
    if len(pts) > 1:
        rs.AddPolyline(pts)

    if not rs.IsLayer('Diagram::03_Paths'): rs.AddLayer('Diagram::03_Paths')
    rs.CurrentLayer('Diagram::03_Paths')
    pts = [(236.62 + offset_x, 54.14 + offset_y, 0.00), (230.89 + offset_x, 57.23 + offset_y, 0.00), (222.87 + offset_x, 60.50 + offset_y, 0.00), (214.84 + offset_x, 63.59 + offset_y, 0.00)]
    if len(pts) > 1:
        rs.AddPolyline(pts)

    if not rs.IsLayer('Diagram::03_Paths'): rs.AddLayer('Diagram::03_Paths')
    rs.CurrentLayer('Diagram::03_Paths')
    pts = [(238.62 + offset_x, 12.72 + offset_y, 0.00), (198.80 + offset_x, 8.42 + offset_y, 0.00), (159.27 + offset_x, 6.36 + offset_y, 0.00), (119.45 + offset_x, 6.36 + offset_y, 0.00), (79.64 + offset_x, 8.42 + offset_y, 0.00), (39.82 + offset_x, 10.66 + offset_y, 0.00)]
    if len(pts) > 1:
        rs.AddPolyline(pts)

    rs.CurrentLayer(original_layer)
    rs.EnableRedraw(True)
    print('AI Vision Diagram drawn for Schouwburgplein.')