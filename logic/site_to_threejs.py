"""
site_to_threejs.py
------------------
Converts Pershing Square geometry from logic/site_reconstruction.py
(Rhino, feet, SW-corner origin) to Three.js geometry descriptors
(5-metre units, park-centre origin).

Coordinate system:
  Rhino  : origin at SW corner, X=East, Y=North, Z=Up, units=feet
  Three.js: X=East, Y=Up, Z=South (into screen), units = 5 real metres
  Scale  : 1 Three.js unit = 5 m = 16.4042 ft

Run standalone to regenerate data/pershing_site_context.json:
  python logic/site_to_threejs.py
"""
import os, csv, json, math

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TREE_CSV  = os.path.join(BASE_DIR, 'data', 'extracted_trees.csv')
OUT_JSON  = os.path.join(BASE_DIR, 'data', 'pershing_site_context.json')

# ── coordinate conversion ────────────────────────────────────────────────────
SCALE = 16.4042          # feet per Three.js unit  (1 unit = 5 m)
CX    = 165.0            # Rhino X of park centre  (330 / 2)
CY    = 275.0            # Rhino Y of park centre  (550 / 2)

def r2t(rx, ry, rz):
    """Rhino (ft, SW-origin) → Three.js (units, centre-origin)."""
    return (
        round((rx - CX) / SCALE, 3),
        round(rz         / SCALE, 3),
        round(-(ry - CY) / SCALE, 3),
    )

# ── geometry helpers ─────────────────────────────────────────────────────────
def box(x0, y0, z0, x1, y1, z1, color, opacity=0.85, label=""):
    """Axis-aligned box from min/max Rhino corners."""
    cx = (x0 + x1) / 2;  cy = (y0 + y1) / 2;  cz = (z0 + z1) / 2
    w  = abs(x1 - x0);   d  = abs(y1 - y0);    h  = abs(z1 - z0)
    tx, ty, tz = r2t(cx, cy, cz)
    return {
        "type":     "box",
        "args":     [round(w/SCALE, 3), round(h/SCALE, 3), round(d/SCALE, 3)],
        "position": [tx, ty, tz],
        "color":    color,
        "opacity":  opacity,
        "label":    label,
    }

def cyl(rx, ry, rz_base, height, radius, color, opacity=0.85, label="", segments=8):
    """Upright cylinder; rz_base is the bottom Z in Rhino coords."""
    tx, ty, tz = r2t(rx, ry, rz_base + height / 2)
    return {
        "type":     "cylinder",
        "args":     [round(radius/SCALE, 3), round(radius/SCALE, 3),
                     round(height/SCALE, 3), segments],
        "position": [tx, ty, tz],
        "color":    color,
        "opacity":  opacity,
        "label":    label,
    }

def sph(rx, ry, rz, radius, color, opacity=0.85, label=""):
    tx, ty, tz = r2t(rx, ry, rz)
    return {
        "type":     "sphere",
        "args":     [round(radius/SCALE, 3), 16, 16],
        "position": [tx, ty, tz],
        "color":    color,
        "opacity":  opacity,
        "label":    label,
    }

# ── layer colours ─────────────────────────────────────────────────────────────
C_HARD    = "#c8c8c8"
C_ICONIC  = "#800080"   # purple (default iconic)
C_YELLOW  = "#ffc800"
C_PINK    = "#ff69b4"
C_GARAGE  = "#3c3c3c"
C_RAMP    = "#646464"
C_LAND    = "#228b22"
C_WATER   = "#0096ff"
C_SIDE    = "#b4b4b4"
C_STREET  = "#323232"

# ── build geometry list ───────────────────────────────────────────────────────
def build():
    g = []

    # ── 0a. Surrounding sidewalk (15 ft wide) ─────────────────────────────
    g.append(box(-15,  -15, -1,    0,  565, 0, C_SIDE,   0.9, "sidewalk_west"))
    g.append(box(330,  -15, -1,  345,  565, 0, C_SIDE,   0.9, "sidewalk_east"))
    g.append(box(  0,  -15, -1,  330,    0, 0, C_SIDE,   0.9, "sidewalk_south"))
    g.append(box(  0,  550, -1,  330,  565, 0, C_SIDE,   0.9, "sidewalk_north"))

    # ── 0b. Surrounding streets (40 ft wide) ──────────────────────────────
    g.append(box(-55,  -55, -2,  -15,  605, -1, C_STREET, 0.95, "street_olive"))
    g.append(box(345,  -55, -2,  385,  605, -1, C_STREET, 0.95, "street_hill"))
    g.append(box(-15,  -55, -2,  345,  -15, -1, C_STREET, 0.95, "street_6th"))
    g.append(box(-15,  565, -2,  345,  605, -1, C_STREET, 0.95, "street_5th"))

    # ── 1. Plaza slab ────────────────────────────────────────────────────
    g.append(box(  0,    0, -10, 330,  550, 0, C_HARD,   0.9,  "plaza_slab"))

    # ── 1b. Underground parking garage ───────────────────────────────────
    g.append(box( 10,   10, -45, 320,  540, -10, C_GARAGE, 0.6, "parking_garage"))

    # ── 1c. Entrance ramps ────────────────────────────────────────────────
    # BooleanDifference carved these out of the plaza; here we represent
    # the ramp volumes explicitly as slightly lighter hardscape.
    g.append(box(  0,  150, -15,  25,  300, 0, C_RAMP,  0.8, "ramp_olive_st"))
    g.append(box(305,  250, -15, 330,  400, 0, C_RAMP,  0.8, "ramp_hill_st"))

    # ── 2. Legorreta campanile tower (approx — arch cutout omitted) ──────
    # Full tower: 20 × 20 ft plan, 120 ft tall, purple
    g.append(box(150, 250, 0, 170, 270, 120, C_ICONIC, 0.9, "campanile_tower"))
    # Approximate horizontal arch opening as a thin void slab visible from outside
    # (Three.js has no built-in CSG; we represent the aperture as a light-coloured
    # horizontal plane to suggest the through-opening at 90–110 ft elevation)
    g.append(box(152, 245, 90, 168, 275, 110, "#ffffff", 0.15, "campanile_aperture_hint"))

    # ── 3. Yellow aqueduct wall (arch cutouts approximated as lighter zones) ──
    g.append(box(160, 270, 0, 165, 400, 25, C_YELLOW, 0.9, "aqueduct_wall"))
    # Suggest the three arched openings as translucent cylinders punched through
    for y_arch in [290, 330, 370]:
        # Arch is a cylinder lying along X, centre at wall midplane x=162.5
        # In Three.js we approximate with a small box void hint
        g.append(box(158, y_arch - 8, 0, 167, y_arch + 8, 16, "#000010", 0.08,
                     "arch_void_hint"))

    # ── 4. Purple sphere + plinth ─────────────────────────────────────────
    g.append(box(146, 226, 0, 154, 234, 2, C_HARD,  0.85, "sphere_plinth"))
    g.append(sph(150, 230, 10, 8,       C_ICONIC, 0.9,  "iconic_sphere"))

    # ── 5. Water basin rim + water volume ─────────────────────────────────
    # Rim: outer 165–210 × 270–400 × 0–4 ft, inner void 167–208 × 272–398 × 1–5
    # Approximate as four thin rim slabs (N/S/E/W walls)
    rim_t = 2  # ft rim thickness
    g.append(box(165, 270, 0, 210,       270 + rim_t, 4, C_HARD, 0.85, "basin_rim_south"))
    g.append(box(165, 400 - rim_t, 0, 210, 400,       4, C_HARD, 0.85, "basin_rim_north"))
    g.append(box(165, 270, 0, 165 + rim_t, 400,       4, C_HARD, 0.85, "basin_rim_west"))
    g.append(box(210 - rim_t, 270, 0, 210, 400,       4, C_HARD, 0.85, "basin_rim_east"))
    # Water surface
    g.append(box(167, 272, 1, 208, 398, 3, C_WATER, 0.75, "water_basin"))

    # ── 5b. Yellow colonnade walkway ──────────────────────────────────────
    for x_col in range(20, 140, 15):   # [20, 35, 50, 65, 80, 95, 110, 125]
        g.append(cyl(x_col, 450, 0, 15, 1.5, C_YELLOW, 0.9, f"colonnade_col_{x_col}"))
    # Cap beam
    g.append(box(15, 448, 15, 145, 452, 17, C_YELLOW, 0.9, "colonnade_beam"))

    # ── 6. Stepped amphitheater ───────────────────────────────────────────
    for i in range(6):
        sx = 210 + i * 10
        sz = i * 2
        g.append(box(sx, 270, 0, sx + 10, 400, sz + 2,
                     C_HARD, 0.85, f"amph_step_{i}"))

    # ── 7. Trees from CSV ─────────────────────────────────────────────────
    if os.path.exists(TREE_CSV):
        with open(TREE_CSV, newline='') as f:
            reader = csv.DictReader(f)
            for row in reader:
                tx_r = float(row['X'])
                ty_r = float(row['Y'])
                tr   = float(row['Radius'])
                g.append(cyl(tx_r, ty_r, 0, 10, max(tr * 0.2, 0.5),
                             "#5a3e1b", 0.9, "tree_trunk"))
                g.append(sph(tx_r, ty_r, 10, tr,
                             C_LAND, 0.8, "tree_canopy"))

    # ── 8. Yellow transit pavilion (Olive St side) ────────────────────────
    g.append(box(10, 200, 0, 50, 240, 18, C_YELLOW, 0.9, "transit_pavilion"))

    # ── 9. View-framing walls (cutouts approximated) ──────────────────────
    # Pink wall (E–W, N edge of park)
    g.append(box(80, 480, 0, 130, 482, 20, C_PINK, 0.9, "pink_wall"))
    # Suggest the circular aperture as a translucent disc aligned with wall
    g.append(sph(105, 481, 10, 6, "#ffffff", 0.12, "pink_wall_aperture_hint"))

    # Purple wall (N–S, east zone)
    g.append(box(240, 420, 0, 242, 470, 20, C_ICONIC, 0.9, "purple_wall"))
    # Suggest the square cutout
    g.append(box(235, 440, 5, 245, 450, 15, "#000010", 0.08, "purple_wall_void_hint"))

    return g


# ── entrypoint ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    geometries = build()
    with open(OUT_JSON, 'w') as f:
        json.dump({"geometries": geometries}, f, indent=2)
    print(f"[OK] Wrote {len(geometries)} geometry descriptors to {OUT_JSON}")
