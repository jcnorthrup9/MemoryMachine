import rhinoscriptsyntax as rs
import json
import os

try:
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    JSON_PATH = os.path.join(BASE_DIR, 'data', 'pershing_osm.json')
except NameError:
    JSON_PATH = r"c:\Users\john\MemoryMachine\data\pershing_osm.json"

# Center coordinate of Pershing Square to anchor our Rhino origin (0,0)
CENTER_LAT = 34.0483
CENTER_LON = -118.2525

def latlon_to_xy(lat, lon):
    # Simple Equirectangular projection from GPS to Feet
    lat_diff = lat - CENTER_LAT
    lon_diff = lon - CENTER_LON
    
    # 1 deg lat = ~365,223 ft | 1 deg lon at 34 N = ~302,762 ft
    y = lat_diff * 365223
    x = lon_diff * 302762
    return [x, y, 0]

def build_city_context():
    if not os.path.exists(JSON_PATH):
        print("OSM Data not found. Run osm_scraper.py first.")
        return
        
    rs.EnableRedraw(False)
    rs.AddLayer("00_SITE::OSM_CONTEXT", (180, 180, 180))
    
    with open(JSON_PATH, 'r') as f:
        data = json.load(f)
        
    nodes = {}
    ways = []
    
    # Sort the raw GIS data into Points (nodes) and Footprints (ways)
    for el in data.get('elements', []):
        if el['type'] == 'node':
            nodes[el['id']] = (el['lat'], el['lon'])
        elif el['type'] == 'way':
            ways.append(el)
            
    for way in ways:
        pts = [latlon_to_xy(nodes[n][0], nodes[n][1]) for n in way['nodes'] if n in nodes]
                
        if len(pts) > 2:
            # Close the polyline
            if pts[0] != pts[-1]: pts.append(pts[0])
            
            # Calculate Extrusion Height (Fallback to 40ft if unknown)
            tags = way.get('tags', {})
            height = float(tags.get('building:levels', 3)) * 14.0 # Estimate 14ft per story
            
            crv = rs.AddPolyline(pts)
            if crv and rs.IsCurveClosed(crv):
                mass = rs.ExtrudeCurveStraight(crv, [0,0,0], [0,0,height])
                rs.CapPlanarHoles(mass)
                rs.ObjectLayer(mass, "00_SITE::OSM_CONTEXT")
            if crv: rs.DeleteObject(crv)
                
    rs.EnableRedraw(True)
    print("✅ OpenStreetMap context generation complete.")

if __name__ == "__main__":
    build_city_context()