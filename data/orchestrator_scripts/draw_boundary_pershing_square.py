import rhinoscriptsyntax as rs

def draw_boundary_pershing_square(offset_x=0, offset_y=0, layer='Default'):
    rs.EnableRedraw(False)
    original_layer = rs.CurrentLayer()
    if rs.IsLayer(layer): rs.CurrentLayer(layer)

    pts = [(-141.51 + offset_x, 78.37 + offset_y, 0.00), (-136.07 + offset_x, 88.17 + offset_y, 0.00), (-119.74 + offset_x, 88.17 + offset_y, 0.00), (-97.97 + offset_x, 88.17 + offset_y, 0.00), (-76.20 + offset_x, 88.17 + offset_y, 0.00), (-54.43 + offset_x, 88.17 + offset_y, 0.00), (-27.21 + offset_x, 88.17 + offset_y, 0.00), (0.00 + offset_x, 88.17 + offset_y, 0.00), (27.21 + offset_x, 88.17 + offset_y, 0.00), (43.54 + offset_x, 84.91 + offset_y, 0.00), (54.43 + offset_x, 78.37 + offset_y, 0.00), (59.87 + offset_x, 65.31 + offset_y, 0.00), (59.87 + offset_x, 48.98 + offset_y, 0.00), (59.87 + offset_x, 32.66 + offset_y, 0.00), (59.87 + offset_x, 16.33 + offset_y, 0.00), (54.43 + offset_x, 0.00 + offset_y, 0.00), (48.98 + offset_x, -16.33 + offset_y, 0.00), (48.98 + offset_x, -29.39 + offset_y, 0.00), (54.43 + offset_x, -39.19 + offset_y, 0.00), (38.10 + offset_x, -42.45 + offset_y, 0.00), (10.89 + offset_x, -42.45 + offset_y, 0.00), (-16.33 + offset_x, -42.45 + offset_y, 0.00), (-43.54 + offset_x, -42.45 + offset_y, 0.00), (-70.75 + offset_x, -42.45 + offset_y, 0.00), (-97.97 + offset_x, -42.45 + offset_y, 0.00), (-119.74 + offset_x, -39.19 + offset_y, 0.00), (-130.62 + offset_x, -29.39 + offset_y, 0.00), (-136.07 + offset_x, -16.33 + offset_y, 0.00), (-141.51 + offset_x, 0.00 + offset_y, 0.00), (-141.51 + offset_x, 16.33 + offset_y, 0.00), (-136.07 + offset_x, 32.66 + offset_y, 0.00), (-136.07 + offset_x, 48.98 + offset_y, 0.00), (-136.07 + offset_x, 65.31 + offset_y, 0.00), (-141.51 + offset_x, 75.11 + offset_y, 0.00), (-141.51 + offset_x, 78.37 + offset_y, 0.00)]
    if len(pts) > 2:
        pts.append(pts[0]) # Close the curve
        rs.AddPolyline(pts)

    rs.CurrentLayer(original_layer)
    rs.EnableRedraw(True)
    print('AI Vision Boundary drawn for Pershing Square.')