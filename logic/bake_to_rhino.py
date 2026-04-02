"""
bake_to_rhino.py
----------------
Reads data/current_intervention.json and bakes the Three.js geometry
descriptors into the live Rhino 8 session as native Rhino geometry on
the layer MEM_GENERATED.

Coordinate mapping
------------------
Three.js is Y-up; Rhino is Z-up.
  Three.js X  →  Rhino X
  Three.js Y  →  Rhino Z  (vertical / up)
  Three.js Z  →  Rhino -Y (Three.js Z+ is south; Rhino Y+ is north)
Scale: 1 Three.js unit = 5 real metres (per site_to_threejs.py convention).

Geometry argument mapping
-------------------------
Three.js BoxGeometry       args=[width, height, depth], position=center
Three.js CylinderGeometry  args=[radiusTop, radiusBottom, height], position=center
Three.js SphereGeometry    args=[radius], position=center

Rhino rs.AddBox(8_corners)          – corners built from center + half-extents
Rhino rs.AddCylinder(plane, h, r)   – plane at base of cylinder, axis = Z
Rhino rs.AddSphere(center, radius)
"""

try:
    import rhinoscriptsyntax as rs
    import Rhino.Geometry as rg
    INSIDE_RHINO = True
except ImportError:
    rs = None
    rg = None
    INSIDE_RHINO = False

import os
import json

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
BASE_DIR  = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_FILE = os.path.join(BASE_DIR, 'data', 'current_intervention.json')

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
LAYER_NAME = 'MEM_GENERATED'
SCALE      = 5.0   # 1 Three.js unit → 5 real metres in Rhino model


# ---------------------------------------------------------------------------
# Coordinate helpers
# ---------------------------------------------------------------------------
def to_rhino_pt(tx, ty, tz):
    """Convert a Three.js (Y-up) point to a Rhino Point3d (Z-up), scaled."""
    return rg.Point3d(tx * SCALE, -tz * SCALE, ty * SCALE)


# ---------------------------------------------------------------------------
# Layer management
# ---------------------------------------------------------------------------
def ensure_layer():
    if not rs.IsLayer(LAYER_NAME):
        rs.AddLayer(LAYER_NAME, color=(0, 255, 136))
    rs.CurrentLayer(LAYER_NAME)


# ---------------------------------------------------------------------------
# Geometry bakers
# ---------------------------------------------------------------------------
def bake_box(geo):
    """
    Three.js BoxGeometry: args=[width, height, depth], position=center.
    Converts to a Rhino Box defined by 8 corners on the MEM_GENERATED layer.
    """
    w, h, d = [a * SCALE for a in geo['args']]
    pos = geo.get('position', [0, 0, 0])

    # Centre in Rhino space
    cx = pos[0] * SCALE
    cy = -pos[2] * SCALE          # Three.js Z → Rhino -Y
    cz = pos[1] * SCALE           # Three.js Y → Rhino Z

    hw, hh, hd = w / 2, h / 2, d / 2

    # 8 corners: bottom face then top face (matching rs.AddBox winding)
    corners = [
        [cx - hw, cy - hd, cz - hh],
        [cx + hw, cy - hd, cz - hh],
        [cx + hw, cy + hd, cz - hh],
        [cx - hw, cy + hd, cz - hh],
        [cx - hw, cy - hd, cz + hh],
        [cx + hw, cy - hd, cz + hh],
        [cx + hw, cy + hd, cz + hh],
        [cx - hw, cy + hd, cz + hh],
    ]
    return rs.AddBox(corners)


def bake_cylinder(geo):
    """
    Three.js CylinderGeometry: args=[radiusTop, radiusBottom, height], position=center.
    Rhino rs.AddCylinder(base_plane, height, radius, cap=True).
    radiusTop and radiusBottom are averaged (Rhino cylinders are uniform radius).
    The base plane is placed at the bottom of the cylinder.
    """
    r_top, r_bot, h_3js = geo['args']
    radius  = ((r_top + r_bot) / 2.0) * SCALE
    height  = h_3js * SCALE
    pos     = geo.get('position', [0, 0, 0])

    # Bottom of cylinder in Rhino space (center.y - h/2 in Three.js Y)
    base_x = pos[0] * SCALE
    base_y = -pos[2] * SCALE
    base_z = (pos[1] - h_3js / 2.0) * SCALE

    base_plane = rs.PlaneFromNormal([base_x, base_y, base_z], [0, 0, 1])
    return rs.AddCylinder(base_plane, height, radius, cap=True)


def bake_sphere(geo):
    """
    Three.js SphereGeometry: args=[radius], position=center.
    Rhino rs.AddSphere(center, radius).
    """
    radius = geo['args'][0] * SCALE
    pos    = geo.get('position', [0, 0, 0])
    center = [pos[0] * SCALE, -pos[2] * SCALE, pos[1] * SCALE]
    return rs.AddSphere(center, radius)


# ---------------------------------------------------------------------------
# Main bake function
# ---------------------------------------------------------------------------
def bake_geometries():
    if not os.path.exists(DATA_FILE):
        print(f"❌ Data file not found: {DATA_FILE}")
        return

    with open(DATA_FILE, encoding='utf-8') as f:
        geometries = json.load(f)

    if not geometries:
        print("⚠️  No geometries found in data file.")
        return

    print(f"[bake_to_rhino] Baking {len(geometries)} geometries onto layer '{LAYER_NAME}'...")

    rs.EnableRedraw(False)
    ensure_layer()

    count = 0
    for geo in geometries:
        geo_type = geo.get('type', '')
        try:
            if geo_type == 'box':
                obj = bake_box(geo)
            elif geo_type == 'cylinder':
                obj = bake_cylinder(geo)
            elif geo_type == 'sphere':
                obj = bake_sphere(geo)
            else:
                print(f"  [skip] Unknown geometry type: {geo_type}")
                continue

            if obj:
                count += 1
        except Exception as e:
            print(f"  [warn] Failed to bake {geo_type}: {e}")

    rs.EnableRedraw(True)
    rs.ZoomExtents()
    print(f"✅ Bake complete — {count} objects added to layer '{LAYER_NAME}'.")


# ---------------------------------------------------------------------------
# Entry point — COM dispatch fallback for standard Python invocation
# ---------------------------------------------------------------------------
if __name__ == '__main__':
    if INSIDE_RHINO:
        bake_geometries()
    else:
        print("Standard Python detected. Dispatching to Rhino via COM...")
        try:
            import win32com.client
            try:
                rhino = win32com.client.dynamic.Dispatch("Rhino.Interface.8")
            except Exception:
                rhino = win32com.client.dynamic.Dispatch("Rhino.Application")

            try:
                rs_app = rhino.GetScriptObject()
            except Exception:
                rs_app = rhino

            script_path = os.path.abspath(__file__)
            cmd = f'_-ScriptEditor Run "{script_path}"'

            if hasattr(rs_app, "RunScript"):
                rs_app.RunScript(cmd, 1)
            else:
                rhino.RunScript(cmd, 1)
            print("✅ Command sent to Rhino.")
        except Exception as e:
            print(f"❌ Error: {e}")
            print("Ensure Rhino 8 is running and 'pip install pywin32' has been run in this venv.")
