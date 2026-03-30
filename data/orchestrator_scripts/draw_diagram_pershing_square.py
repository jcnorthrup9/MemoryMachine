import rhinoscriptsyntax as rs

def draw_diagram_pershing_square(offset_x=0, offset_y=0, layer_plaza='Diagram::01_Plaza', layer_veg='Diagram::02_Vegetation', layer_paths='Diagram::03_Paths'):
    rs.EnableRedraw(False)
    original_layer = rs.CurrentLayer()

    if not rs.IsLayer(layer_plaza): rs.AddLayer(layer_plaza)
    rs.CurrentLayer(layer_plaza)
    pts = [(181.25 + offset_x, 228.34 + offset_y, 0.00), (372.06 + offset_x, 205.06 + offset_y, 0.00), (331.13 + offset_x, 78.13 + offset_y, 0.00), (132.88 + offset_x, 104.60 + offset_y, 0.00), (181.25 + offset_x, 228.34 + offset_y, 0.00)]
    if len(pts) > 1:
        if len(pts) > 2: pts.append(pts[0])
        rs.AddPolyline(pts)

    if not rs.IsLayer(layer_veg): rs.AddLayer(layer_veg)
    rs.CurrentLayer(layer_veg)
    pts = [(193.47 + offset_x, 227.38 + offset_y, 0.00), (262.04 + offset_x, 217.81 + offset_y, 0.00), (255.13 + offset_x, 200.27 + offset_y, 0.00), (186.56 + offset_x, 209.84 + offset_y, 0.00), (193.47 + offset_x, 227.38 + offset_y, 0.00)]
    if len(pts) > 1:
        if len(pts) > 2: pts.append(pts[0])
        rs.AddPolyline(pts)

    if not rs.IsLayer(layer_veg): rs.AddLayer(layer_veg)
    rs.CurrentLayer(layer_veg)
    pts = [(188.16 + offset_x, 198.68 + offset_y, 0.00), (248.22 + offset_x, 189.43 + offset_y, 0.00), (241.31 + offset_x, 173.80 + offset_y, 0.00), (181.25 + offset_x, 182.73 + offset_y, 0.00), (188.16 + offset_x, 198.68 + offset_y, 0.00)]
    if len(pts) > 1:
        if len(pts) > 2: pts.append(pts[0])
        rs.AddPolyline(pts)

    if not rs.IsLayer(layer_veg): rs.AddLayer(layer_veg)
    rs.CurrentLayer(layer_veg)
    pts = [(250.87 + offset_x, 172.21 + offset_y, 0.00), (314.12 + offset_x, 161.05 + offset_y, 0.00), (307.75 + offset_x, 143.51 + offset_y, 0.00), (243.96 + offset_x, 154.03 + offset_y, 0.00), (250.87 + offset_x, 172.21 + offset_y, 0.00)]
    if len(pts) > 1:
        if len(pts) > 2: pts.append(pts[0])
        rs.AddPolyline(pts)

    if not rs.IsLayer(layer_veg): rs.AddLayer(layer_veg)
    rs.CurrentLayer(layer_veg)
    pts = [(246.62 + offset_x, 136.17 + offset_y, 0.00), (294.46 + offset_x, 128.20 + offset_y, 0.00), (288.45 + offset_x, 116.08 + offset_y, 0.00), (240.78 + offset_x, 124.37 + offset_y, 0.00), (246.62 + offset_x, 136.17 + offset_y, 0.00)]
    if len(pts) > 1:
        if len(pts) > 2: pts.append(pts[0])
        rs.AddPolyline(pts)

    if not rs.IsLayer(layer_veg): rs.AddLayer(layer_veg)
    rs.CurrentLayer(layer_veg)
    pts = [(276.39 + offset_x, 110.66 + offset_y, 0.00), (302.96 + offset_x, 106.52 + offset_y, 0.00), (296.58 + offset_x, 95.39 + offset_y, 0.00), (270.01 + offset_x, 99.18 + offset_y, 0.00), (276.39 + offset_x, 110.66 + offset_y, 0.00)]
    if len(pts) > 1:
        if len(pts) > 2: pts.append(pts[0])
        rs.AddPolyline(pts)

    if not rs.IsLayer(layer_veg): rs.AddLayer(layer_veg)
    rs.CurrentLayer(layer_veg)
    pts = [(330.07 + offset_x, 199.64 + offset_y, 0.00), (356.11 + offset_x, 196.06 + offset_y, 0.00), (349.74 + offset_x, 184.01 + offset_y, 0.00), (323.69 + offset_x, 187.84 + offset_y, 0.00), (330.07 + offset_x, 199.64 + offset_y, 0.00)]
    if len(pts) > 1:
        if len(pts) > 2: pts.append(pts[0])
        rs.AddPolyline(pts)

    if not rs.IsLayer(layer_veg): rs.AddLayer(layer_veg)
    rs.CurrentLayer(layer_veg)
    pts = [(153.61 + offset_x, 97.27 + offset_y, 0.00), (213.14 + offset_x, 88.98 + offset_y, 0.00), (204.66 + offset_x, 74.94 + offset_y, 0.00), (144.57 + offset_x, 83.23 + offset_y, 0.00), (153.61 + offset_x, 97.27 + offset_y, 0.00)]
    if len(pts) > 1:
        if len(pts) > 2: pts.append(pts[0])
        rs.AddPolyline(pts)

    if not rs.IsLayer(layer_veg): rs.AddLayer(layer_veg)
    rs.CurrentLayer(layer_veg)
    pts = [(260.44 + offset_x, 216.54 + offset_y, 0.00), (281.70 + offset_x, 213.35 + offset_y, 0.00), (276.39 + offset_x, 205.38 + offset_y, 0.00), (255.13 + offset_x, 208.57 + offset_y, 0.00), (260.44 + offset_x, 216.54 + offset_y, 0.00)]
    if len(pts) > 1:
        if len(pts) > 2: pts.append(pts[0])
        rs.AddPolyline(pts)

    if not rs.IsLayer(layer_veg): rs.AddLayer(layer_veg)
    rs.CurrentLayer(layer_veg)
    pts = [(313.59 + offset_x, 141.59 + offset_y, 0.00), (329.54 + offset_x, 138.41 + offset_y, 0.00), (324.22 + offset_x, 132.03 + offset_y, 0.00), (308.28 + offset_x, 135.22 + offset_y, 0.00), (313.59 + offset_x, 141.59 + offset_y, 0.00)]
    if len(pts) > 1:
        if len(pts) > 2: pts.append(pts[0])
        rs.AddPolyline(pts)

    if not rs.IsLayer(layer_veg): rs.AddLayer(layer_veg)
    rs.CurrentLayer(layer_veg)
    pts = [(302.96 + offset_x, 96.95 + offset_y, 0.00), (318.91 + offset_x, 93.76 + offset_y, 0.00), (313.59 + offset_x, 87.38 + offset_y, 0.00), (297.65 + offset_x, 90.57 + offset_y, 0.00), (302.96 + offset_x, 96.95 + offset_y, 0.00)]
    if len(pts) > 1:
        if len(pts) > 2: pts.append(pts[0])
        rs.AddPolyline(pts)

    if not rs.IsLayer(layer_paths): rs.AddLayer(layer_paths)
    rs.CurrentLayer(layer_paths)
    pts = [(184.97 + offset_x, 227.06 + offset_y, 0.00), (211.01 + offset_x, 211.75 + offset_y, 0.00), (227.49 + offset_x, 202.19 + offset_y, 0.00), (247.15 + offset_x, 190.39 + offset_y, 0.00), (241.84 + offset_x, 154.35 + offset_y, 0.00), (239.18 + offset_x, 128.84 + offset_y, 0.00), (212.61 + offset_x, 103.33 + offset_y, 0.00), (159.45 + offset_x, 81.00 + offset_y, 0.00)]
    if len(pts) > 1:
        rs.AddPolyline(pts)

    if not rs.IsLayer(layer_paths): rs.AddLayer(layer_paths)
    rs.CurrentLayer(layer_paths)
    pts = [(366.74 + offset_x, 203.78 + offset_y, 0.00), (324.22 + offset_x, 186.24 + offset_y, 0.00), (302.96 + offset_x, 167.11 + offset_y, 0.00), (239.18 + offset_x, 128.84 + offset_y, 0.00), (212.61 + offset_x, 112.89 + offset_y, 0.00), (186.03 + offset_x, 96.95 + offset_y, 0.00), (154.14 + offset_x, 77.81 + offset_y, 0.00)]
    if len(pts) > 1:
        rs.AddPolyline(pts)

    if not rs.IsLayer(layer_paths): rs.AddLayer(layer_paths)
    rs.CurrentLayer(layer_paths)
    pts = [(191.34 + offset_x, 192.62 + offset_y, 0.00), (212.61 + offset_x, 187.84 + offset_y, 0.00), (239.18 + offset_x, 183.05 + offset_y, 0.00), (265.76 + offset_x, 178.27 + offset_y, 0.00), (292.33 + offset_x, 173.49 + offset_y, 0.00), (318.91 + offset_x, 168.70 + offset_y, 0.00), (345.48 + offset_x, 163.92 + offset_y, 0.00)]
    if len(pts) > 1:
        rs.AddPolyline(pts)

    if not rs.IsLayer(layer_paths): rs.AddLayer(layer_paths)
    rs.CurrentLayer(layer_paths)
    pts = [(159.45 + offset_x, 122.46 + offset_y, 0.00), (186.03 + offset_x, 117.68 + offset_y, 0.00), (212.61 + offset_x, 112.89 + offset_y, 0.00), (239.18 + offset_x, 108.11 + offset_y, 0.00), (265.76 + offset_x, 103.33 + offset_y, 0.00), (292.33 + offset_x, 98.54 + offset_y, 0.00), (318.91 + offset_x, 93.76 + offset_y, 0.00)]
    if len(pts) > 1:
        rs.AddPolyline(pts)

    rs.CurrentLayer(original_layer)
    rs.EnableRedraw(True)
    print('AI Vision Diagram drawn for Pershing Square.')