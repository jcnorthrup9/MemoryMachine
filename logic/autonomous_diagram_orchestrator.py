import os
import sys
import math
import argparse
import re
import osmnx as ox

# Add parent directory to path so we can import SOURCE_INFO from app.py
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(BASE_DIR)

from app import SOURCE_INFO
from logic.precedent_scraper import SITES

OUTPUT_DIR = os.path.join(BASE_DIR, 'data', 'orchestrator_scripts')
os.makedirs(OUTPUT_DIR, exist_ok=True)

def latlon_to_meters(lat, lon, center_lat, center_lon):
    """Convert lat/lon to local Cartesian coordinates in meters relative to a center point."""
    m_per_deg_lat = 111320.0
    m_per_deg_lon = 111320.0 * math.cos(math.radians(center_lat))
    
    x = (lon - center_lon) * m_per_deg_lon
    y = (lat - center_lat) * m_per_deg_lat
    return x, y

def fetch_site_footprints(site_id, site_info, radius=300):
    """Fetches building footprints from OpenStreetMap within a given radius (meters)."""
    coords = site_info.get("coordinates")
    if not coords:
        print(f"[ERROR] No coordinates found for {site_id}")
        return []
        
    center_lat = coords["lat"]
    center_lon = coords["lon"]
    
    print(f"🌍 Fetching OpenStreetMap building footprints for {site_id}...")
    tags = {'building': True}
    try:
        gdf = ox.features_from_point((center_lat, center_lon), tags=tags, dist=radius)
    except Exception as e:
        print(f"[ERROR] Failed to fetch OSM data: {e}")
        return []
        
    footprints = []
    for geom in gdf.geometry:
        if geom.geom_type == 'Polygon':
            polygons = [geom]
        elif geom.geom_type == 'MultiPolygon':
            polygons = list(geom.geoms)
        else:
            continue
            
        for poly in polygons:
            local_pts = []
            for lon, lat in poly.exterior.coords:
                x, y = latlon_to_meters(lat, lon, center_lat, center_lon)
                local_pts.append((x, y, 0))
            if local_pts:
                footprints.append(local_pts)
                
    print(f"✅ Extracted {len(footprints)} building footprints.")
    return footprints

def generate_rhino_script(site_id, footprints, img_path="", img_width=0, img_height=0):
    """Generates a flexible rhinoscriptsyntax function to draw the site at a given location."""
    safe_name = site_id.lower().replace(' ', '_').replace(',', '')
    script_lines = [
        "import rhinoscriptsyntax as rs",
        "import os",
        "",
        f"def draw_{safe_name}(offset_x=0, offset_y=0, footprint_layer='Default', image_layer='Default'):",
        "    rs.EnableRedraw(False)",
        "    original_layer = rs.CurrentLayer()",
        ""
    ]
    
    # 1. Add Picture Frame Underlay
    if img_path and img_width > 0:
        script_lines.extend([
            f"    if rs.IsLayer(image_layer): rs.CurrentLayer(image_layer)",
            f"    img_path = r'{img_path}'",
            f"    if os.path.exists(img_path):",
            f"        plane = rs.MovePlane(rs.WorldXYPlane(), [offset_x - {img_width/2}, offset_y - {img_height/2}, -1])",
            f"        try:",
            f"            rs.AddPictureFrame(plane, img_path, {img_width}, {img_height})",
            f"        except Exception as e:",
            f"            print('Could not add picture frame:', e)",
            ""
        ])
    
    # 2. Add OSM Footprints
    script_lines.extend([
        f"    if rs.IsLayer(footprint_layer): rs.CurrentLayer(footprint_layer)",
    ])
    
    for i, pts in enumerate(footprints):
        pt_str = ", ".join([f"({x:.2f} + offset_x, {y:.2f} + offset_y, {z:.2f})" for x, y, z in pts])
        script_lines.append(f"    pts_{i} = [{pt_str}]")
        script_lines.append(f"    if len(pts_{i}) > 2:")
        script_lines.append(f"        rs.AddPolyline(pts_{i})")
    
    script_lines.extend([
        "",
        "    rs.CurrentLayer(original_layer)",
        "    rs.EnableRedraw(True)",
        f"    print('OSM Context and Image drawing complete for {site_id}.')"
    ])
    
    out_path = os.path.join(OUTPUT_DIR, f"draw_{safe_name}.py")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(script_lines))
        
    print(f"📝 Rhino script generated: {out_path}\n")
    return out_path

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fetch OSM data and generate Rhino drawing script.")
    parser.add_argument("--site", type=str, help="Target site name (e.g., 'Piazza del Campo'). Leave blank for all.", default=None)
    parser.add_argument("--lat", type=float, help="Latitude (for autonomous mode)", default=None)
    parser.add_argument("--lon", type=float, help="Longitude (for autonomous mode)", default=None)
    parser.add_argument("--zoom", type=float, help="Zoom level for image scale", default=18.0)
    parser.add_argument("--image", type=str, help="Path to satellite image", default=None)
    args = parser.parse_args()
    
    if args.lat is not None and args.lon is not None and args.site:
        print(f"🚀 Running in Autonomous Mode for {args.site}")
        info = {"coordinates": {"lat": args.lat, "lon": args.lon}}
        fps = fetch_site_footprints(args.site, info)
        
        img_width = img_height = 0
        img_path = args.image if args.image and os.path.exists(args.image) else ""
        if img_path:
            m_per_px = 156543.03392 * math.cos(math.radians(args.lat)) / (2 ** args.zoom)
            img_width = 1100 * m_per_px
            img_height = 660 * m_per_px
            
        generate_rhino_script(args.site, fps, img_path, img_width, img_height)
        
    else:
        targets = {args.site: SOURCE_INFO[args.site]} if args.site and args.site in SOURCE_INFO else SOURCE_INFO
        site_keys = list(SOURCE_INFO.keys())
        
        for name, info in targets.items():
            if "coordinates" in info:
                fps = fetch_site_footprints(name, info)
                
                # 3. Find Image path and calculate exact scale
                site_data = next((s for s in SITES if s['name'] == name), None)
                img_path = ""
                img_width = img_height = 0
                
                if site_data:
                    img_path = os.path.join(BASE_DIR, 'assets', 'precedents', f"{site_data['id']}_satellite.jpg").replace("\\", "/")
                    zoom = site_data.get('zoom', 18.0)
                    center_lat = info["coordinates"]["lat"]
                    
                    m_per_px = 156543.03392 * math.cos(math.radians(center_lat)) / (2 ** zoom)
                    img_width = 1100 * m_per_px
                    img_height = 660 * m_per_px
                
                if fps or img_path:
                    generate_rhino_script(name, fps, img_path, img_width, img_height)