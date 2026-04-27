import xml.etree.ElementTree as ET
import re

def _get_float(val, default=0.0):
    if not val: return default
    try:
        return float(re.sub(r'[^\d.-]', '', str(val)))
    except ValueError:
        return default

def parse_svg_to_json(svg_path, scale_factor=1.0, center=True, rotate_90=True):
    """
    Reads an SVG and extracts paths into discrete 3D coordinate arrays for Blender.
    Requires: pip install svg.path
    """
    try:
        from svg.path import parse_path
    except ImportError:
        raise ImportError("The 'svg.path' library is missing. Please run: pip install svg.path")
        
    tree = ET.parse(svg_path)
    root = tree.getroot()
    
    polygons = []
    all_pts = []
    
    # Iterate over all elements to catch shapes as well as paths
    for idx, elem in enumerate(root.iter()):
        tag = elem.tag.split('}')[-1].lower()
        
        # Safeguard: Skip pattern definitions and explicitly named hatch layers
        if tag == 'pattern':
            continue
        elem_id = elem.attrib.get('id', '').lower()
        elem_class = elem.attrib.get('class', '').lower()
        if 'hatch' in elem_id or 'hatch' in elem_class:
            continue
            
        d = ""
        
        if tag == 'path':
            d = elem.attrib.get('d', '')
        elif tag == 'rect':
            x = _get_float(elem.attrib.get('x', 0))
            y = _get_float(elem.attrib.get('y', 0))
            w = _get_float(elem.attrib.get('width', 0))
            h = _get_float(elem.attrib.get('height', 0))
            d = f"M {x} {y} L {x+w} {y} L {x+w} {y+h} L {x} {y+h} Z"
        elif tag == 'circle':
            cx = _get_float(elem.attrib.get('cx', 0))
            cy = _get_float(elem.attrib.get('cy', 0))
            r = _get_float(elem.attrib.get('r', 0))
            d = f"M {cx-r},{cy} A {r},{r} 0 1,0 {cx+r},{cy} A {r},{r} 0 1,0 {cx-r},{cy}"
        elif tag == 'ellipse':
            cx = _get_float(elem.attrib.get('cx', 0))
            cy = _get_float(elem.attrib.get('cy', 0))
            rx = _get_float(elem.attrib.get('rx', 0))
            ry = _get_float(elem.attrib.get('ry', 0))
            d = f"M {cx-rx},{cy} A {rx},{ry} 0 1,0 {cx+rx},{cy} A {rx},{ry} 0 1,0 {cx-rx},{cy}"
        elif tag in ['polygon', 'polyline']:
            pts_str = elem.attrib.get('points', '').replace(',', ' ').split()
            if len(pts_str) >= 2:
                d = f"M {pts_str[0]} {pts_str[1]} "
                for i in range(2, len(pts_str), 2):
                    if i+1 < len(pts_str):
                        d += f"L {pts_str[i]} {pts_str[i+1]} "
                if tag == 'polygon':
                    d += "Z"
        elif tag == 'line':
            x1 = _get_float(elem.attrib.get('x1', 0))
            y1 = _get_float(elem.attrib.get('y1', 0))
            x2 = _get_float(elem.attrib.get('x2', 0))
            y2 = _get_float(elem.attrib.get('y2', 0))
            d = f"M {x1} {y1} L {x2} {y2}"

        if not d:
            continue
            
        try:
            parsed_path = parse_path(d)
        except Exception as e:
            print(f"Skipping {tag} due to svg.path error: {e}")
            continue
            
        pts = []
        
        # Discretize the curve into straight segments (e.g., 10 points per segment)
        for sub in parsed_path:
            for i in range(11):
                try:
                    pos = sub.point(i / 10.0)
                except Exception:
                    continue
                
                raw_x = pos.real
                raw_y = -pos.imag # Invert Y for Blender
                
                if rotate_90:
                    # 90-degree rotation (Swap X and Y)
                    x = -raw_y * scale_factor
                    y = raw_x * scale_factor
                else:
                    x = raw_x * scale_factor
                    y = raw_y * scale_factor
                
                point = [round(x, 4), round(y, 4), 0.0]
                if not pts or pts[-1] != point:  # Prevent duplicate consecutive points
                    pts.append(point)
                    all_pts.append(point)
                    
        # Extract Color (from fill attribute or inline style)
        fill_color = elem.attrib.get('fill', '#CCCCCC') # Default to gray if none found
        style_attr = elem.attrib.get('style', '')
        if 'fill:' in style_attr:
            match = re.search(r'fill:\s*(#[0-9a-fA-F]+)', style_attr)
            if match:
                fill_color = match.group(1)

        layer_id = elem.attrib.get('id', f'layer_{idx}')
        if pts:
            polygons.append({
                "layer_name": layer_id,
                "color": fill_color,
                "coordinates": pts
            })
        
    # Center the entire geometry around (0,0,0)
    if center and all_pts:
        cx = (min(p[0] for p in all_pts) + max(p[0] for p in all_pts)) / 2.0
        cy = (min(p[1] for p in all_pts) + max(p[1] for p in all_pts)) / 2.0
        for poly in polygons:
            for pt in poly["coordinates"]:
                pt[0] = round(pt[0] - cx, 4)
                pt[1] = round(pt[1] - cy, 4)
                
    return polygons