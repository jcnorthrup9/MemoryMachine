"""
GhPython Script component: PM_FacadeScreen  --  FidelityGrid2
--------------------------------------------------------------------
Paste into a "Python 3 Script" component (Maths > Script > Python 3 Script,
guid 719467e6-7cf5-4848-99b0-c5dd57e5442c) on the same Grasshopper canvas as
FidelityGrid1's PM_FacadePanelizer (rhino/gh_facade_panelizer_component.py).
See PershingMetabolizer_Prototype/FIDELITY_GRID_2.md for the full writeup.

Purpose: a second, more three-dimensional facade layer that compounds on
top of FidelityGrid1 rather than sitting beside it. It reuses FidelityGrid1's
own site-level column-grid x DTLA-grid collision seeds (2D_GRID_PARTI_LOGIC_
SPEC.md sections 1-4) as real architectural anchor points, then implements
section 5 ("warped grid lines") -- deliberately skipped by FidelityGrid1 --
to deflect a SECOND, independently-spaced/rotated grid's cell boundaries
away from those seeds, and drives a continuous overlap-DENSITY field (not
FidelityGrid1's binary marked/unmarked) that graduates each cell's standoff
projection distance from the glass plane. Cells above a density threshold
get a third "hybrid" material, echoing the violet "synthesized hybrid
substance" language from the Processing-sketch reference this was developed
against -- see FIDELITY_GRID_2.md for the full translation rationale (this
is a deliberate hybrid of that sketch's concepts with the spec's own
Behavior-B-sibling machinery, not a literal port of either).

Component setup
----------------
Inputs (item access, Generic Data -- cast explicitly in code):
  Bake             : bool  -- Boolean Toggle. False = preview only.
  Refresh          : bool  -- unused by the script body (deterministic, no
                     RNG); wired for future use.
  Grid2RotDeg      : float -- Number Slider, 0-45, default 20.0. Secondary
                     grid rotation off world XY (the Processing sketch's
                     rotationAngle=0.35rad ~= 20deg).
  Grid2SpacingFt   : float -- Number Slider, 9-54, default 27.0. Secondary
                     grid spacing (the sketch's equal gridA/gridB=27).
  Panel2ZFt        : float -- Number Slider, 4-27, default 13.5. Screen
                     lattice vertical module.
  WarpMaxRadiusFt  : float -- Number Slider, 0-120, default 54.0. Spec section
                     5's near-anchor falloff radius (2 column bays).
  WarpMaxForceFt   : float -- Number Slider, 0-30, default 9.0. Spec section
                     5's near-anchor max deflection distance.
  InfluenceRadiusFt: float -- Number Slider, 13.5-108, default 54.0. Density
                     kernel radius (how far a seed's "crowding" reaches).
  MinStandoffFt    : float -- Number Slider, 0.25-6, default 1.0. Screen
                     standoff (air gap) at zero density.
  MaxStandoffFt    : float -- Number Slider, 1-16, default 5.0. Standoff at
                     saturated density.
  Panel2ThickFt    : float -- Number Slider, 0.1-1.5, default 0.33. Screen
                     slab thickness.
  HybridThresh     : float -- Number Slider, 0-1, default 0.60. Normalized
                     density above which a cell becomes "hybrid" material.
  SwirlDeg         : float -- Number Slider, 0-90, default 0.0. Optional
                     tangential warp component (0 = pure radial repulsion).
  PanelTiltDeg     : float -- Number Slider, 0-90, default 0.0. Hinges each
                     cell at its own TOP edge and rotates the bottom edge
                     from flush-vertical (0=today's wall screen) toward
                     horizontal-and-outward (90=overhang/walkway cover).
                     Top-hinge (not bottom) is deliberate -- it leaves
                     clearance underneath for a walkway; bottom-hinge would
                     collapse the canopy to grade instead. Applies uniformly
                     to every cell (Screen and ScreenHybrid alike, every
                     floor band) -- dial it live to explore, rather than a
                     scripted "only near grade" zone rule. Horizontally
                     adjacent cells share the same hinge math and stay
                     seamed; vertically stacked bands genuinely separate as
                     tilt increases (each fans open from its own higher
                     hinge) -- a louvre/brise-soleil stack, not a bug.

Outputs:
  Screen       : Breps (plain screen slabs)
  ScreenHybrid : Breps (high-density "hybrid" slabs, third material)
  Standoffs    : Breps (cylindrical standoffs from the FG1 glass plane)
  WarpCrv      : Curves (flat, densified warped secondary-grid lines --
                 diagnostic only, not used to generate panel geometry)
  Log          : str summary -- wire to a Panel.

Assumptions made explicit here because the prompt didn't pin them down:
  - Seeds are RECOMPUTED here (col-grid x DTLA-grid collision, byte-for-byte
    the same algorithm as FidelityGrid1), not read from FidelityGrid1's
    baked geometry -- this keeps both layers independently toggleable and
    rebakeable with no fragile dependency on parsing baked Breps. The Log's
    `seeds=` count should always read 56; if it doesn't, ORIGIN/site data
    has drifted between the two components and they're no longer talking
    about the same site.
  - The warp (spec section 5's warp_point, promoted to 3D) is evaluated once
    at each cell's UNWARPED plan corner, not iteratively re-warped -- the
    lattice stays a single-valued function of its unwarped position, which
    avoids any self-intersection feedback risk.
  - Seed influence (both warp force and density) is computed in true 3D
    against each seed treated as sitting at grade (z=0), so influence fades
    with height above ground as well as plan distance -- a facade's upper
    floors are less affected by ground-level seed clustering than its base.
  - Cell boundaries are straight lines between the four already-warped
    corner nodes; the fine (3ft-step) polyline resampling from spec section
    5 is used ONLY for the flat WarpCrv diagnostic output, not to further
    subdivide panel edges. Documented simplification: at this module scale
    (spacing ~27ft vs. a 3ft resample step) the loss of intra-edge
    curvature is minor. A future refinement could densify actual panel
    edges the same way if the coarser look isn't fine enough.
  - Non-planar warped quads are built as bilinear ruled surfaces
    (Brep.CreateFromCornerPoints x6 + Join), not Brep.CreatePlanarBreps
    (silently returns nothing for non-planar input) or CreateOffsetBrep
    (invokes a slow, unreliable-on-twisted-input solver at this object
    count).
  - Hybrid-vs-plain classification is by a cell's mean corner density
    (average of its 4 corner dnorm values), not a per-corner or
    per-sub-sample test.
  - G1_PANEL_DEPTH_FT = 0.25 hardcodes FidelityGrid1's PanelDepthFt DEFAULT
    as the baseline glass-plane offset every standoff/screen depth is
    measured from. If FG1's slider is moved off its 0.25 default before
    FG2 is baked, update this constant to match, or the screen's baseline
    will be wrong relative to the actual glass plane.
  - Materials: same two-step workflow as FidelityGrid1 (see
    FIDELITY_GRID_1.md section 7 / FIDELITY_GRID_2.md) -- materials set
    from inside this component do not visibly render in Rhino's Rendered
    display mode. Bake here, then run the (extended)
    rhino/apply_facade_materials.py via rhino/run_rhino_script.py (the
    win32com COM bridge) to make PM_Hybrid_Overlap and the reused
    PM_Mullion_Metal actually visible.

When pasting into an actual Grasshopper Python 3 Script component, the
component requires '#! python 3' as the literal first line -- prepend it
(and drop this docstring, or keep it below the directive) since this file
leads with documentation instead for readability as a repo reference copy.
"""
import json
import math
import os

import Rhino
import Rhino.Geometry as rg
import System.Drawing

MULLION_MATERIAL_NAME = "PM_Mullion_Metal"
MULLION_MATERIAL_HEX = "#4A4A4A"
HYBRID_MATERIAL_NAME = "PM_Hybrid_Overlap"
HYBRID_MATERIAL_HEX = "#553C5F"

# ---------------------------------------------------------------- constants
CANDIDATE_JSON_PATHS = [
    os.path.join(os.getcwd(), "PershingMetabolizer_Prototype", "real_geometry.json"),
    r"C:\Users\jcnor\MemoryMachine\PershingMetabolizer_Prototype\real_geometry.json",
]
FALLBACK_SITE_SIZE = (354.22, 602.53)
FALLBACK_ORIGIN = (337.028, 570.21)

COL_SPACING = 27.0
COL_ANGLE_DEG = 0.0
DTLA_SPACING_U = 336.0
DTLA_SPACING_V = 600.0
DTLA_ANGLE_DEG = 36.0 + COL_ANGLE_DEG
BOUNDARY_OFFSET = 9.0
SEED_TOL = 0.05

VERT_FACE_NORMAL_DOT = 0.1
MIN_FACE_AREA_FT2 = 4.0
MIN_PANEL_FT = 1.0

TARGET_ROOT_LAYER = "Detailed_Screen"
PROGRAM_LAYERS = [
    "PracticeSpace", "ComputerTechSpace", "ArtsAndCraftsStudio",
    "WorkOutEquipment", "PicnicGrillSpace", "Greenspace",
    "Skatepark", "CommunityCenter",
]

# Spec section 5's example fade fractions (radius 32->18, force 16->6),
# applied as fractions of the user-supplied Warp*Ft sliders.
FAR_RADIUS_FRAC = 18.0 / 32.0
FAR_FORCE_FRAC = 6.0 / 16.0
DENSITY_NORM_K = 2.5           # ~2.5 coincident seeds' worth of density saturates dnorm=1
G1_PANEL_DEPTH_FT = 0.25       # mirrors FidelityGrid1's PanelDepthFt default -- keep in sync
STANDOFF_RADIUS_FT = 0.15
PANEL2_GAP_FT = 0.25
WARP_SAMPLE_FT = 3.0           # WarpCrv diagnostic resample step only

rhino_doc = Rhino.RhinoDoc.ActiveDoc
TOL = rhino_doc.ModelAbsoluteTolerance if rhino_doc else 0.01


# ------------------------------------------------------- site data loading
def load_site_data():
    data, used_path = None, None
    for path in CANDIDATE_JSON_PATHS:
        try:
            with open(path, "r") as f:
                data = json.load(f)
            used_path = path
            break
        except Exception:
            continue
    if data is None:
        return FALLBACK_SITE_SIZE, FALLBACK_ORIGIN, "FALLBACK (real_geometry.json not found)"
    width = data["site"]["width_ft"]
    length = data["site"]["length_ft"]
    anchor = data["secondary_entrance_anchor"]
    columns = data["column_positions"]
    ax, az = anchor["x"], anchor["z"]
    best, best_d = None, None
    for c in columns:
        d = math.hypot(c["x"] - ax, c["z"] - az)
        if best_d is None or d < best_d:
            best_d, best = d, (c["x"], c["z"])
    origin = best if best is not None else FALLBACK_ORIGIN
    return (width, length), origin, used_path


SITE_SIZE, ORIGIN, SITE_DATA_SOURCE = load_site_data()
BOUNDARY_PTS = [
    (0.0, 0.0), (SITE_SIZE[0], 0.0),
    (SITE_SIZE[0], SITE_SIZE[1]), (0.0, SITE_SIZE[1]),
]


# ------------------------------------------- portable grid algorithm (spec 1-4)
def build_grid_lines(origin, spacing_u, spacing_v, angle_deg, boundary_pts, offset):
    ox, oy = origin
    theta = math.radians(angle_deg)
    cos_t, sin_t = math.cos(theta), math.sin(theta)

    def to_local(x, y):
        dx, dy = x - ox, y - oy
        return (dx * cos_t + dy * sin_t, -dx * sin_t + dy * cos_t)

    def to_world(lu, lv):
        return (ox + lu * cos_t - lv * sin_t, oy + lu * sin_t + lv * cos_t)

    local_pts = [to_local(x, y) for x, y in boundary_pts]
    us = [p[0] for p in local_pts]
    vs = [p[1] for p in local_pts]
    min_u, max_u = min(us) - offset, max(us) + offset
    min_v, max_v = min(vs) - offset, max(vs) + offset

    lines = []
    n_lo, n_hi = int(math.ceil(min_u / spacing_u)), int(math.floor(max_u / spacing_u))
    for n in range(n_lo, n_hi + 1):
        u = n * spacing_u
        lines.append((to_world(u, min_v), to_world(u, max_v), "U", n))

    m_lo, m_hi = int(math.ceil(min_v / spacing_v)), int(math.floor(max_v / spacing_v))
    for m in range(m_lo, m_hi + 1):
        v = m * spacing_v
        lines.append((to_world(min_u, v), to_world(max_u, v), "V", m))

    return lines, to_local, to_world, (n_lo, n_hi, m_lo, m_hi)


def segment_intersection(p1, p2, p3, p4):
    x1, y1 = p1; x2, y2 = p2; x3, y3 = p3; x4, y4 = p4
    denom = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
    if abs(denom) < 1e-9:
        return None
    t = ((x1 - x3) * (y3 - y4) - (y1 - y3) * (x3 - x4)) / denom
    u = ((x1 - x3) * (y1 - y2) - (y1 - y3) * (x1 - x2)) / denom
    if 0 <= t <= 1 and 0 <= u <= 1:
        return (x1 + t * (x2 - x1), y1 + t * (y2 - y1))
    return None


col_lines, _col_to_local, _col_to_world, _col_range = build_grid_lines(
    ORIGIN, COL_SPACING, COL_SPACING, COL_ANGLE_DEG, BOUNDARY_PTS, BOUNDARY_OFFSET)
dtla_lines, _dtla_to_local, _dtla_to_world, _dtla_range = build_grid_lines(
    ORIGIN, DTLA_SPACING_U, DTLA_SPACING_V, DTLA_ANGLE_DEG, BOUNDARY_PTS, BOUNDARY_OFFSET)

_raw_seeds = []
for (c_p1, c_p2, c_axis, c_idx) in col_lines:
    for (d_p1, d_p2, _d_axis, _d_idx) in dtla_lines:
        ipt = segment_intersection(
            (c_p1[0], c_p1[1]), (c_p2[0], c_p2[1]),
            (d_p1[0], d_p1[1]), (d_p2[0], d_p2[1]))
        if ipt is not None:
            _raw_seeds.append((ipt[0], ipt[1], c_axis, c_idx))

seeds = []
for s in _raw_seeds:
    if not any(math.hypot(s[0] - t[0], s[1] - t[1]) < SEED_TOL for t in seeds):
        seeds.append(s)


# --------------------------------------------------- spec section 5: warp
def seed_fade_params(seed_list, origin, max_radius, max_force):
    """Per-seed max_radius/max_force fade linearly with the SEED's own
    distance from the anchor -- computed once, not per-sample."""
    d = [math.hypot(sx - origin[0], sy - origin[1]) for (sx, sy, _a, _i) in seed_list]
    dmax = max(d) if d else 1.0
    dmax = dmax or 1.0
    out = []
    for di in d:
        frac = di / dmax
        out.append((
            max_radius * (1.0 - (1.0 - FAR_RADIUS_FRAC) * frac),
            max_force * (1.0 - (1.0 - FAR_FORCE_FRAC) * frac),
        ))
    return out


def smoothstep(t):
    t = max(0.0, min(1.0, t))
    return t * t * (3.0 - 2.0 * t)


def warp_point(px, py, pz, seed_list, fades, swirl_rad):
    """Spec section 5's warp_point, promoted to 3D. Force accumulates over
    ALL seeds in range, not just the nearest."""
    x, y = px, py
    for (sx, sy, _a, _i), (r_max, f_max) in zip(seed_list, fades):
        dp = math.hypot(px - sx, py - sy)
        d = math.hypot(dp, pz)
        if d >= r_max or dp < 1e-9:
            continue
        force = f_max * (1.0 - d / r_max)
        ang = math.atan2(py - sy, px - sx) + swirl_rad * (1.0 - d / r_max)
        x += math.cos(ang) * force
        y += math.sin(ang) * force
    return x, y


def density_at(px, py, pz, seed_list, radius):
    """Continuous overlap-density: linear-falloff sum over all seeds."""
    total = 0.0
    for (sx, sy, _a, _i) in seed_list:
        dp = math.hypot(px - sx, py - sy)
        d = math.hypot(dp, pz)
        total += max(0.0, 1.0 - d / radius)
    return total


# ---------------------------------------------------------- facade geometry
def coerce_brep(geo):
    if isinstance(geo, rg.Brep):
        return geo
    if isinstance(geo, rg.Extrusion):
        return geo.ToBrep()
    return rg.Brep.TryConvertBrep(geo)


def facade_faces(brep):
    faces = []
    for face in brep.Faces:
        ok, plane = face.TryGetPlane(TOL)
        if not ok:
            continue
        n = plane.Normal
        if abs(n.Z) > VERT_FACE_NORMAL_DOT:
            continue
        amp = rg.AreaMassProperties.Compute(face)
        if amp is None or amp.Area < MIN_FACE_AREA_FT2:
            continue
        faces.append((face, plane))
    return faces


def face_frame(face, plane):
    o = plane.Origin
    normal = plane.Normal
    if normal.Z < 0:
        normal = -normal
    h_axis = rg.Vector3d.CrossProduct(rg.Vector3d.ZAxis, normal)
    h_axis.Unitize()
    bbox = face.GetBoundingBox(True)
    corners = [
        rg.Point3d(bbox.Min.X, bbox.Min.Y, bbox.Min.Z), rg.Point3d(bbox.Max.X, bbox.Min.Y, bbox.Min.Z),
        rg.Point3d(bbox.Min.X, bbox.Max.Y, bbox.Min.Z), rg.Point3d(bbox.Max.X, bbox.Max.Y, bbox.Min.Z),
        rg.Point3d(bbox.Min.X, bbox.Min.Y, bbox.Max.Z), rg.Point3d(bbox.Max.X, bbox.Min.Y, bbox.Max.Z),
        rg.Point3d(bbox.Min.X, bbox.Max.Y, bbox.Max.Z), rg.Point3d(bbox.Max.X, bbox.Max.Y, bbox.Max.Z),
    ]
    hs = [(c - o) * h_axis for c in corners]
    zs = [c.Z for c in corners]
    z0 = max(min(zs), 0.0)
    return o, h_axis, min(hs), max(hs), z0, max(zs)


def outward_normal(face, plane):
    n = plane.Normal
    if face.OrientationIsReversed:
        n = -n
    n.Unitize()
    return n


def joints_against_lines(o, h_axis, h0, h1, lines):
    """Same idiom as FidelityGrid1's facade_h_joints, parameterized by an
    arbitrary line set instead of the column grid."""
    p0 = (o.X + h0 * h_axis.X, o.Y + h0 * h_axis.Y)
    p1 = (o.X + h1 * h_axis.X, o.Y + h1 * h_axis.Y)
    joints = set([round(h0, 6), round(h1, 6)])
    for (c_p1, c_p2, _ax, _ix) in lines:
        ipt = segment_intersection(p0, p1, (c_p1[0], c_p1[1]), (c_p2[0], c_p2[1]))
        if ipt is not None:
            dh = (ipt[0] - o.X) * h_axis.X + (ipt[1] - o.Y) * h_axis.Y
            if h0 - 1e-6 <= dh <= h1 + 1e-6:
                joints.add(round(dh, 6))
    return sorted(joints)


def z_bands(z0, z1, floor_ft):
    bands = []
    z = math.floor(z0 / floor_ft) * floor_ft
    while z < z1 - 1e-6:
        z_next = z + floor_ft
        b0, b1 = max(z, z0), min(z_next, z1)
        if b1 - b0 > 1e-6:
            bands.append((b0, b1))
        z = z_next
    return bands


def is_buried(wx, wy, wz, skip_brep, all_breps):
    pt = rg.Point3d(wx, wy, wz)
    for other in all_breps:
        if other is skip_brep:
            continue
        try:
            if other.IsSolid and other.IsPointInside(pt, TOL, False):
                return True
        except Exception:
            continue
    return False


def screen_node(o, h_axis, n_axis, h, z, seed_list, fades, swirl_rad,
                 radius, min_so, max_so):
    px = o.X + h * h_axis.X
    py = o.Y + h * h_axis.Y
    wx, wy = warp_point(px, py, z, seed_list, fades, swirl_rad)
    dh = (wx - px) * h_axis.X + (wy - py) * h_axis.Y
    dn = (wx - px) * n_axis.X + (wy - py) * n_axis.Y
    dens = density_at(px, py, z, seed_list, radius)
    dnorm = min(1.0, dens / DENSITY_NORM_K)
    off = G1_PANEL_DEPTH_FT + min_so + (max_so - min_so) * smoothstep(dnorm) + max(0.0, dn)
    pt = rg.Point3d(px + dh * h_axis.X + off * n_axis.X,
                     py + dh * h_axis.Y + off * n_axis.Y, z)
    return pt, dnorm


def tilt_bottom_corner(P, hinge, h_axis, n_axis, tilt_rad):
    """Rotate a cell's bottom corner P about its TOP-row hinge point by
    tilt_rad, sweeping the vertical drop (hinge->P) toward the outward
    normal. At tilt_rad=0 this returns P unchanged (bit-identical to the
    flush-wall geometry). {h_axis, ZAxis, n_axis} is orthonormal (see
    face_frame's h_axis = ZAxis x normal), so this decomposition is exact."""
    if tilt_rad == 0.0:
        return P
    delta = P - hinge
    d_h = delta * h_axis
    p = -delta.Z
    q = delta * n_axis
    cos_t, sin_t = math.cos(tilt_rad), math.sin(tilt_rad)
    new_p = p * cos_t - q * sin_t
    new_q = p * sin_t + q * cos_t
    return hinge + d_h * h_axis + (-new_p) * rg.Vector3d.ZAxis + new_q * n_axis


def inset_quad(A, B, C, D, gap):
    cx = (A.X + B.X + C.X + D.X) / 4.0
    cy = (A.Y + B.Y + C.Y + D.Y) / 4.0
    cz = (A.Z + B.Z + C.Z + D.Z) / 4.0
    center = rg.Point3d(cx, cy, cz)

    def move(P):
        v = P - center
        length = v.Length
        if length < 1e-9:
            return P
        v.Unitize()
        shrink = min(gap, length * 0.45)
        return P - v * shrink

    return move(A), move(B), move(C), move(D)


def make_screen_slab(A, B, C, D, n_axis, thick, tol):
    """Warped quads are generally non-planar -- build bilinear ruled
    surfaces (never fails on non-planarity) rather than CreatePlanarBreps
    (returns nothing) or CreateOffsetBrep (slow, unreliable when twisted)."""
    off = n_axis * thick
    A2, B2, C2, D2 = A + off, B + off, C + off, D + off
    quads = [(A, B, C, D), (A2, B2, C2, D2),
             (A, B, B2, A2), (B, C, C2, B2),
             (C, D, D2, C2), (D, A, A2, D2)]
    faces = []
    for p0, p1, p2, p3 in quads:
        f = rg.Brep.CreateFromCornerPoints(p0, p1, p2, p3, tol)
        if f is not None:
            faces.append(f)
    if not faces:
        return None
    joined = rg.Brep.JoinBreps(faces, tol)
    return joined[0] if joined else None


def warp_crv_diagnostics(lines, seed_list, fades, swirl_rad, sample_ft):
    crvs = []
    for (p1, p2, _ax, _ix) in lines:
        length = math.hypot(p2[0] - p1[0], p2[1] - p1[1])
        n = max(2, int(math.ceil(length / sample_ft)) + 1)
        pts = []
        for k in range(n):
            t = k / float(n - 1)
            px = p1[0] + (p2[0] - p1[0]) * t
            py = p1[1] + (p2[1] - p1[1]) * t
            wx, wy = warp_point(px, py, 0.0, seed_list, fades, swirl_rad)
            pts.append(rg.Point3d(wx, wy, 0.02))
        if len(pts) >= 2:
            crvs.append(rg.PolylineCurve(pts))
    return crvs


def dnorm_color(dnorm):
    t = max(0.0, min(1.0, dnorm))
    r = max(0, min(255, int(60 + 195 * t)))
    g = max(0, min(255, int(60 + 40 * (1.0 - t))))
    b = max(0, min(255, int(60 + 195 * (1.0 - t))))
    return System.Drawing.Color.FromArgb(r, g, b)


# ---------------------------------------------------------------- layering
def ensure_layer_path(full_path):
    idx = rhino_doc.Layers.FindByFullPath(full_path, -1)
    if idx >= 0:
        return rhino_doc.Layers[idx].Id
    parent_id, built = None, ""
    for seg in full_path.split("::"):
        built = seg if not built else built + "::" + seg
        found = rhino_doc.Layers.FindByFullPath(built, -1)
        if found >= 0:
            parent_id = rhino_doc.Layers[found].Id
            continue
        new_layer = Rhino.DocObjects.Layer()
        new_layer.Name = seg
        if parent_id is not None:
            new_layer.ParentLayerId = parent_id
        new_idx = rhino_doc.Layers.Add(new_layer)
        if new_idx < 0:
            return None
        parent_id = rhino_doc.Layers[new_idx].Id
    return parent_id


def attrs_for(full_path):
    a = Rhino.DocObjects.ObjectAttributes()
    a.LayerIndex = rhino_doc.Layers.FindByFullPath(full_path, -1)
    return a


def find_or_make_material(name, color_hex, metallic=0.0, roughness=0.3, transparency=0.0):
    mat = Rhino.DocObjects.Material()
    mat.Name = name
    c = color_hex.lstrip("#")
    r, g, b = int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)
    color = System.Drawing.Color.FromArgb(r, g, b)
    mat.DiffuseColor = color
    mat.Transparency = transparency
    mat.Reflectivity = metallic
    try:
        pbr = mat.PhysicallyBased
        if pbr is None:
            mat.ToPhysicallyBased()
            pbr = mat.PhysicallyBased
        if pbr is not None:
            pbr.BaseColor = Rhino.Display.Color4f(color)
            pbr.Metallic = metallic
            pbr.Roughness = roughness
            pbr.Opacity = max(0.0, 1.0 - transparency)
    except Exception:
        pass
    existing_idx = -1
    for i in range(rhino_doc.Materials.Count):
        if rhino_doc.Materials[i].Name == name:
            existing_idx = i
            break
    if existing_idx >= 0:
        rhino_doc.Materials.Modify(mat, existing_idx, True)
        return existing_idx
    return rhino_doc.Materials.Add(mat)


def clear_previous_bake():
    idx = rhino_doc.Layers.FindByFullPath(TARGET_ROOT_LAYER, -1)
    if idx < 0:
        return
    keep_ids = set([rhino_doc.Layers[idx].Id])
    changed = True
    while changed:
        changed = False
        for i in range(rhino_doc.Layers.Count):
            lyr = rhino_doc.Layers[i]
            if lyr.ParentLayerId in keep_ids and lyr.Id not in keep_ids:
                keep_ids.add(lyr.Id)
                changed = True
    layer_indices = set(i for i in range(rhino_doc.Layers.Count) if rhino_doc.Layers[i].Id in keep_ids)
    to_remove = [o for o in rhino_doc.Objects if o.Attributes.LayerIndex in layer_indices]
    for o in to_remove:
        rhino_doc.Objects.Delete(o, True)


# ---------------------------------------------------------------------- run
def run():
    grid2_spacing = float(Grid2SpacingFt) if Grid2SpacingFt is not None else 27.0
    grid2_rot = float(Grid2RotDeg) if Grid2RotDeg is not None else 20.0
    panel_z_ft = float(Panel2ZFt) if Panel2ZFt is not None else 13.5
    warp_max_radius = float(WarpMaxRadiusFt) if WarpMaxRadiusFt is not None else 54.0
    warp_max_force = float(WarpMaxForceFt) if WarpMaxForceFt is not None else 9.0
    influence_radius = float(InfluenceRadiusFt) if InfluenceRadiusFt is not None else 54.0
    min_so = float(MinStandoffFt) if MinStandoffFt is not None else 1.0
    max_so = float(MaxStandoffFt) if MaxStandoffFt is not None else 5.0
    thick = float(Panel2ThickFt) if Panel2ThickFt is not None else 0.33
    hybrid_thresh = float(HybridThresh) if HybridThresh is not None else 0.60
    swirl_rad = math.radians(float(SwirlDeg)) if SwirlDeg is not None else 0.0
    tilt_rad = math.radians(float(PanelTiltDeg)) if PanelTiltDeg is not None else 0.0
    do_bake = bool(Bake) if Bake is not None else False
    gap = PANEL2_GAP_FT

    grid2_lines, _g2_to_local, _g2_to_world, _g2_range = build_grid_lines(
        ORIGIN, grid2_spacing, grid2_spacing, grid2_rot, BOUNDARY_PTS, BOUNDARY_OFFSET)

    fades = seed_fade_params(seeds, ORIGIN, warp_max_radius, warp_max_force)
    warp_crv = warp_crv_diagnostics(grid2_lines, seeds, fades, swirl_rad, WARP_SAMPLE_FT)

    bldg_breps = {}
    all_breps = []
    for name in PROGRAM_LAYERS:
        idx = rhino_doc.Layers.FindByFullPath("Program::" + name, -1)
        if idx < 0:
            continue
        breps = []
        for rh_obj in rhino_doc.Objects.FindByLayer(rhino_doc.Layers[idx]):
            b = coerce_brep(rh_obj.Geometry)
            if b is not None:
                breps.append(b)
                all_breps.append(b)
        bldg_breps[name] = breps

    screen_by_bldg, hybrid_by_bldg, standoff_by_bldg = {}, {}, {}
    density_pts = []
    all_dnorms = []

    for name, breps in bldg_breps.items():
        screen_list, hybrid_list, standoff_list = [], [], []
        for brep in breps:
            for face, plane in facade_faces(brep):
                o, h_axis, h0, h1, z0, z1 = face_frame(face, plane)
                if h1 - h0 < MIN_PANEL_FT or z1 - z0 < MIN_PANEL_FT * 0.3:
                    continue
                n_axis = outward_normal(face, plane)

                h_joints = joints_against_lines(o, h_axis, h0, h1, grid2_lines)
                if len(h_joints) < 2:
                    continue
                z_bnds = z_bands(z0, z1, panel_z_ft)
                if not z_bnds:
                    continue
                z_lines = [z_bnds[0][0]] + [b[1] for b in z_bnds]

                node_grid = {}
                for i, h in enumerate(h_joints):
                    for j, z in enumerate(z_lines):
                        pt, dnorm = screen_node(
                            o, h_axis, n_axis, h, z, seeds, fades, swirl_rad,
                            influence_radius, min_so, max_so)
                        node_grid[(i, j)] = (pt, dnorm)
                        all_dnorms.append(dnorm)
                        if (i + j) % 3 == 0:
                            density_pts.append((pt, dnorm))

                for i in range(len(h_joints) - 1):
                    for j in range(len(z_lines) - 1):
                        A, dA = node_grid[(i, j)]
                        B, dB = node_grid[(i + 1, j)]
                        C, dC = node_grid[(i + 1, j + 1)]
                        D, dD = node_grid[(i, j + 1)]
                        if A.DistanceTo(B) < MIN_PANEL_FT or A.DistanceTo(D) < MIN_PANEL_FT * 0.3:
                            continue
                        cell_dnorm = (dA + dB + dC + dD) / 4.0
                        hmid = (h_joints[i] + h_joints[i + 1]) / 2.0
                        zmid = (z_lines[j] + z_lines[j + 1]) / 2.0
                        wx = o.X + hmid * h_axis.X
                        wy = o.Y + hmid * h_axis.Y
                        if is_buried(wx, wy, zmid, brep, all_breps):
                            continue
                        A_t = tilt_bottom_corner(A, D, h_axis, n_axis, tilt_rad)
                        B_t = tilt_bottom_corner(B, C, h_axis, n_axis, tilt_rad)
                        Ai, Bi, Ci, Di = inset_quad(A_t, B_t, C, D, gap)
                        slab = make_screen_slab(Ai, Bi, Ci, Di, n_axis, thick, TOL)
                        if slab is None:
                            continue
                        if cell_dnorm >= hybrid_thresh:
                            hybrid_list.append(slab)
                        else:
                            screen_list.append(slab)

                        base_pt = rg.Point3d(wx + G1_PANEL_DEPTH_FT * n_axis.X,
                                              wy + G1_PANEL_DEPTH_FT * n_axis.Y, zmid)
                        center_node = rg.Point3d(
                            (Ai.X + Bi.X + Ci.X + Di.X) / 4.0,
                            (Ai.Y + Bi.Y + Ci.Y + Di.Y) / 4.0,
                            (Ai.Z + Bi.Z + Ci.Z + Di.Z) / 4.0)
                        standoff_len = base_pt.DistanceTo(center_node)
                        if standoff_len > 0.05:
                            axis = center_node - base_pt
                            axis.Unitize()
                            circle = rg.Circle(rg.Plane(base_pt, axis), STANDOFF_RADIUS_FT)
                            cyl = rg.Cylinder(circle, standoff_len)
                            standoff_list.append(cyl.ToBrep(True, True))

        screen_by_bldg[name] = screen_list
        hybrid_by_bldg[name] = hybrid_list
        standoff_by_bldg[name] = standoff_list

    all_screen = [p for v in screen_by_bldg.values() for p in v]
    all_hybrid = [p for v in hybrid_by_bldg.values() for p in v]
    all_standoffs = [p for v in standoff_by_bldg.values() for p in v]

    mean_dnorm = sum(all_dnorms) / len(all_dnorms) if all_dnorms else 0.0
    max_dnorm = max(all_dnorms) if all_dnorms else 0.0
    total_cells = len(all_screen) + len(all_hybrid)

    log_lines = [
        "site_data_source={}".format(SITE_DATA_SOURCE),
        "seeds={} grid2_lines={} cells={} hybrid={}".format(
            len(seeds), len(grid2_lines), total_cells, len(all_hybrid)),
        "mean_dnorm={:.3f} max_dnorm={:.3f}".format(mean_dnorm, max_dnorm),
        "ORIGIN=({:.3f},{:.3f})".format(ORIGIN[0], ORIGIN[1]),
    ]
    for name in PROGRAM_LAYERS:
        if name in screen_by_bldg:
            log_lines.append("{}: screen={} hybrid={} standoffs={}".format(
                name, len(screen_by_bldg[name]), len(hybrid_by_bldg[name]), len(standoff_by_bldg[name])))
    log_lines.append("TOTAL screen={} hybrid={} standoffs={}".format(
        len(all_screen), len(all_hybrid), len(all_standoffs)))

    if do_bake:
        clear_previous_bake()
        mullion_idx = find_or_make_material(MULLION_MATERIAL_NAME, MULLION_MATERIAL_HEX,
                                             metallic=0.9, roughness=0.3, transparency=0.0)
        hybrid_idx = find_or_make_material(HYBRID_MATERIAL_NAME, HYBRID_MATERIAL_HEX,
                                            metallic=0.2, roughness=0.55, transparency=0.0)

        ensure_layer_path(TARGET_ROOT_LAYER + "::_Parti::WarpedGrid")
        ensure_layer_path(TARGET_ROOT_LAYER + "::_Parti::DensityPts")
        warp_attr = attrs_for(TARGET_ROOT_LAYER + "::_Parti::WarpedGrid")
        for crv in warp_crv:
            rhino_doc.Objects.AddCurve(crv, warp_attr)
        dens_layer_idx = rhino_doc.Layers.FindByFullPath(TARGET_ROOT_LAYER + "::_Parti::DensityPts", -1)
        for pt, dnorm in density_pts:
            pattr = Rhino.DocObjects.ObjectAttributes()
            pattr.LayerIndex = dens_layer_idx
            pattr.ColorSource = Rhino.DocObjects.ObjectColorSource.ColorFromObject
            pattr.ObjectColor = dnorm_color(dnorm)
            rhino_doc.Objects.AddPoint(pt, pattr)

        for name in PROGRAM_LAYERS:
            if name not in screen_by_bldg:
                continue
            screen_layer = "{}::{}::Screen".format(TARGET_ROOT_LAYER, name)
            hybrid_layer = "{}::{}::ScreenHybrid".format(TARGET_ROOT_LAYER, name)
            standoff_layer = "{}::{}::Standoffs".format(TARGET_ROOT_LAYER, name)
            ensure_layer_path(screen_layer)
            ensure_layer_path(hybrid_layer)
            ensure_layer_path(standoff_layer)
            s_idx = rhino_doc.Layers.FindByFullPath(screen_layer, -1)
            h_idx = rhino_doc.Layers.FindByFullPath(hybrid_layer, -1)
            st_idx = rhino_doc.Layers.FindByFullPath(standoff_layer, -1)
            rhino_doc.Layers[s_idx].RenderMaterialIndex = mullion_idx
            rhino_doc.Layers[h_idx].RenderMaterialIndex = hybrid_idx
            rhino_doc.Layers[st_idx].RenderMaterialIndex = mullion_idx
            s_attr = attrs_for(screen_layer)
            h_attr = attrs_for(hybrid_layer)
            st_attr = attrs_for(standoff_layer)
            for brep in screen_by_bldg[name]:
                rhino_doc.Objects.AddBrep(brep, s_attr)
            for brep in hybrid_by_bldg[name]:
                rhino_doc.Objects.AddBrep(brep, h_attr)
            for brep in standoff_by_bldg[name]:
                rhino_doc.Objects.AddBrep(brep, st_attr)
        rhino_doc.Views.Redraw()
        log_lines.append("BAKED to {}::*".format(TARGET_ROOT_LAYER))

    return all_screen, all_hybrid, all_standoffs, warp_crv, "\n".join(log_lines)


if rhino_doc is None:
    Screen, ScreenHybrid, Standoffs, WarpCrv, Log = [], [], [], [], "ERROR: no active Rhino document"
else:
    Screen, ScreenHybrid, Standoffs, WarpCrv, Log = run()
    print(Log)
