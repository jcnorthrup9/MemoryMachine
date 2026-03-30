import os
import sys
import json
import math
import argparse
try:
    import cv2
    import numpy as np
except ImportError:
    pass

try:
    from dotenv import load_dotenv
    from google import genai
    from google.genai import types
except ImportError as e:
    print(f"❌ Missing dependency: {e}. Please run: pip install python-dotenv google-genai")
    sys.exit(1)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(BASE_DIR)

from logic.precedent_scraper import SITES

def trace_plaza_boundary(site_id, custom_img=None, custom_lat=None, custom_zoom=18.0):
    load_dotenv(os.path.join(BASE_DIR, '.env'))
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("❌ Error: GEMINI_API_KEY missing.")
        return
        
    client = genai.Client(api_key=api_key)
    
    if custom_img and custom_lat is not None:
        img_path = custom_img
        lat = custom_lat
        zoom = custom_zoom
        site_name = site_id
    else:
        site_data = next((s for s in SITES if s['name'].lower() == site_id.lower() or s['id'] == site_id.lower().replace(' ', '_')), None)
        if not site_data:
            print(f"❌ Error: Site '{site_id}' not found in registry.")
            return
        img_path = os.path.join(BASE_DIR, 'assets', 'precedents', f"{site_data['id']}_satellite.jpg")
        lat = site_data['lat']
        zoom = site_data.get('zoom', 18.0)
        site_name = site_data['name']

    if not os.path.exists(img_path):
        print(f"❌ Error: Satellite image not found at {img_path}")
        return
        
    print(f"👁️  Sending {site_name} satellite image to Gemini Vision for boundary tracing...")
    
    with open(img_path, "rb") as f:
        img_bytes = f.read()
        
    # --- Generate Canny Edge Map via OpenCV ---
    print("🧠 Processing image through Canny Edge Detection...")
    img_cv = cv2.imread(img_path)
    gray = cv2.cvtColor(img_cv, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    edges = cv2.Canny(blurred, 50, 150)
    kernel = np.ones((2,2), np.uint8)
    edges_thick = cv2.dilate(edges, kernel, iterations=1) # Thicken lines for the AI
    _, edge_buffer = cv2.imencode('.jpg', edges_thick)
    edge_bytes = edge_buffer.tobytes()
    
    prompt = """
    You are an expert architectural diagrammer analyzing a satellite image of a public space.
    Your task is to generate a full spatial diagram matching an abstract, analytical style (similar to your analysis of Parc de la Villette and Schouwburgplein).
    
    You have been provided with TWO images: 
    1. The raw satellite view.
    2. A Canny Edge map. Use the high-contrast lines in the edge map to accurately lock your coordinates to the true physical boundaries, paths, and hardscape edges.
    
    Extract the following spatial elements as series of (x, y) coordinates.
    The coordinates MUST be normalized between 0.0 and 1.0, where:
    [0.0, 0.0] is the Top-Left corner of the image.
    [1.0, 1.0] is the Bottom-Right corner of the image.
    
    Return ONLY a valid JSON object with NO markdown formatting, containing these keys:
    1. "plaza_boundary": A single array of points for the main hardscape/plaza perimeter.
    2. "vegetation_zones": An array of multiple point arrays representing distinct green spaces/parks.
    3. "paths": An array of multiple point arrays representing major pedestrian axes or circulation routes.
    
    Example format:
    {
      "plaza_boundary": [[0.5, 0.2], [0.6, 0.3], [0.55, 0.8]],
      "vegetation_zones": [ [[0.1, 0.1], [0.2, 0.1], [0.15, 0.2]] ],
      "paths": [ [[0.0, 0.5], [1.0, 0.5]] ]
    }
    """
    
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=[
            prompt,
            types.Part.from_bytes(data=img_bytes, mime_type="image/jpeg"),
            types.Part.from_bytes(data=edge_bytes, mime_type="image/jpeg")
        ]
    )
    
    try:
        clean_json = response.text.strip().replace("```json", "").replace("```", "")
        data = json.loads(clean_json)
        print(f"✅ Gemini successfully extracted diagrammatic geometry.")
    except Exception as e:
        print(f"❌ Failed to parse Gemini response: {e}\nResponse:\n{response.text}")
        return
        
    # --- Convert UV to Rhino Coordinates ---
    m_per_px = 156543.03392 * math.cos(math.radians(lat)) / (2 ** zoom)
    img_width_m = 1100 * m_per_px
    img_height_m = 660 * m_per_px
    
    def convert_uvs(uv_points):
        rhino_pts = []
        for u, v in uv_points:
            x = u * img_width_m
            y = (1.0 - v) * img_height_m
            rhino_pts.append((x, y, 0.0))
        return rhino_pts
        
    # Generate python script for Claude
    safe_name = site_name.lower().replace(' ', '_').replace(',', '').replace('.', '')
    out_dir = os.path.join(BASE_DIR, 'data', 'orchestrator_scripts')
    out_path = os.path.join(out_dir, f"draw_diagram_{safe_name}.py")
    
    script_lines = [
        "import rhinoscriptsyntax as rs",
        "",
        f"def draw_diagram_{safe_name}(offset_x=0, offset_y=0, layer_plaza='Diagram::01_Plaza', layer_veg='Diagram::02_Vegetation', layer_paths='Diagram::03_Paths'):",
        "    rs.EnableRedraw(False)",
        "    original_layer = rs.CurrentLayer()",
        ""
    ]
    
    def add_poly_code(pts_array, layer_var, close=True):
        if not pts_array: return
        script_lines.append(f"    if not rs.IsLayer({layer_var}): rs.AddLayer({layer_var})")
        script_lines.append(f"    rs.CurrentLayer({layer_var})")
        pt_str = ", ".join([f"({x:.2f} + offset_x, {y:.2f} + offset_y, {z:.2f})" for x, y, z in convert_uvs(pts_array)])
        script_lines.append(f"    pts = [{pt_str}]")
        script_lines.append("    if len(pts) > 1:")
        if close:
            script_lines.append("        if len(pts) > 2: pts.append(pts[0])")
        script_lines.append("        rs.AddPolyline(pts)")
        script_lines.append("")

    # Draw Plaza
    plaza = data.get("plaza_boundary", [])
    if plaza:
        add_poly_code(plaza, "layer_plaza", close=True)
        
    # Draw Vegetation
    veg_zones = data.get("vegetation_zones", [])
    for veg in veg_zones:
        add_poly_code(veg, "layer_veg", close=True)
        
    # Draw Paths
    paths = data.get("paths", [])
    for path in paths:
        add_poly_code(path, "layer_paths", close=False)
    
    script_lines.extend([
        "    rs.CurrentLayer(original_layer)",
        "    rs.EnableRedraw(True)",
        f"    print('AI Vision Diagram drawn for {site_name}.')"
    ])
    
    with open(out_path, 'w', encoding='utf-8') as f:
        f.write("\n".join(script_lines))
        
    print(f"📝 Rhino script generated: {out_path}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--site", type=str, required=True, help="Site name (e.g., 'Piazza del Campo')")
    parser.add_argument("--image", type=str, help="Direct path to image", default=None)
    parser.add_argument("--lat", type=float, help="Latitude for scale", default=None)
    parser.add_argument("--zoom", type=float, help="Zoom level", default=18.0)
    args = parser.parse_args()
    trace_plaza_boundary(args.site, args.image, args.lat, args.zoom)