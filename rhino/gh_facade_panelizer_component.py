"""
GhPython Script component: PM_FacadePanelizer  --  FidelityGrid1
--------------------------------------------------------------------
Paste into a "Python 3 Script" component (Maths > Script > Python 3 Script,
guid 719467e6-7cf5-4848-99b0-c5dd57e5442c) on a Grasshopper canvas. This is
the committed source-of-record for the live component built and driven this
session via the Cordyceps MCP bridge (gh_canvas/gh_script/gh_wire) -- until
now it existed only inside the live .gh document. See
PershingMetabolizer_Prototype/FIDELITY_GRID_1.md for the full writeup
(algorithm walkthrough, verification numbers, known caveats) and
PershingMetabolizer_Prototype/2D_GRID_PARTI_LOGIC_SPEC.md sections 1-4 and 6
for the algorithm this implements (deliberately NOT section 5's line-warping
or section 7's Voronoi webbing -- those are FidelityGrid2's territory).

Component setup
----------------
Inputs (item access, Generic Data -- cast explicitly in code since GH
Python 3 Script components don't preserve strict type hints via configure()):
  Bake         : bool  -- Boolean Toggle. False = preview only (Panels/
                 Mullions/GridCrv/SeedPts/MarkedCrv outputs still populate
                 for inspection). True = also writes into the Rhino document.
  Refresh      : bool  -- Boolean Toggle. Currently unused by the script body
                 (the algorithm is fully deterministic, no RNG state to
                 reset) -- wired for future use, harmless if left unwired.
  SubDiv       : int   -- Number Slider, range 2-8, default 4. Behavior B's
                 recursive-subdivision factor for marked cells.
  FloorFt      : float -- Number Slider, range 6-27, default 13.5. Vertical
                 band height panels get divided into.
  PanelDepthFt : float -- Number Slider, range 0.1-2, default 0.25. Glass
                 panel extrusion depth.
  MullionFt    : float -- Number Slider, range 0.1-2, default 0.5. Mullion
                 strip width (also used as the panel-to-panel reveal gap).

Outputs:
  Panels     : Breps (glass panel solids)
  Mullions   : Breps (mullion strip solids)
  GridCrv    : Curves (site-level column grid + DTLA grid lines, combined,
               for preview)
  DtlaLines  : Curves (the 3 real DTLA grid lines ALONE, not combined with
               the column grid -- for components that need just the
               rotated secondary grid, e.g. PM_ElasticGrid's warped-line
               distortion)
  SeedPts    : Points (the real column x DTLA collision seeds)
  MarkedCrv  : Curves (outlines of the marked/subdivided cells)
  Log        : str summary -- wire to a Panel. Also printed to the
               component's built-in `out` stream.

Assumptions made explicit here because the prompt didn't pin them down:
  - "Top plane" / facade detection: a face counts as a facade if it's planar
    and its normal is within TOP_FACE_NORMAL_DOT... actually see
    VERT_FACE_NORMAL_DOT below -- a face is VERTICAL (a facade candidate) if
    abs(normal.Z) <= 0.1, not the inverse. Non-planar or near-horizontal
    faces (roofs, floors) are skipped entirely.
  - CORRECTED 2026-08: ORIGIN/COL_ANGLE_DEG/BOUNDARY_PTS now come directly
    from Rhino/scripts/grid_ortho.py + grid_dtla.py in the OneDrive SCI-Arc
    Thesis project -- confirmed to be the SAME site/column survey as this
    document's real_geometry.json (same folder tree, in fact: this .gh file
    lives alongside Rhino/scripts/ in .../2026_Summer/Thesis/Rhino/).
    Previously this component derived ORIGIN at runtime as "nearest real
    column_positions entry to secondary_entrance_anchor" and assumed
    COL_ANGLE_DEG=0.0 (claimed "measured empirically" -- that measurement
    was wrong, likely taken against placeholder/idealized test geometry
    rather than the real survey). The true Hill St/metro corner column is
    one of exactly 5 columns missing from this doc's OBJ-derived
    real_geometry.json extraction, so the old runtime heuristic silently
    fell back to a column one grid-row short. grid_ortho.py's later
    from-survey ORIGIN captures the real corner directly, and the real
    as-surveyed column grid does carry a 0.4deg drift (kept deliberately,
    not zeroed -- same reasoning as grid_ortho.py's own comment).
  - Grade clipping: a facade's vertical extent is clamped so no panel is
    generated below world Z=0. Buildings whose entire mass sits at or below
    grade (their roof is flush with or below Z=0) correctly get zero panels
    -- there is no facade above ground to panelize. Confirmed for
    Program::PracticeSpace and Program::ComputerTechSpace via bbox
    inspection; not a bug.
  - Buried-panel culling: a candidate panel is skipped if its cell center
    falls inside any OTHER building's closed Brep (relevant where massing
    footprints overlap in plan, e.g. the two CommunityCenter masses).
  - Materials are created here with real PhysicallyBased channel data (not
    just legacy DiffuseColor), assigned by LAYER (Layer.RenderMaterialIndex)
    rather than per-object. CRITICAL GOTCHA, discovered this session:
    materials created/assigned from *inside* this GhPython component set
    the data correctly (verifiable via Cordyceps' rhino_render
    material_list) but do NOT visibly render in Rhino's Rendered display
    mode -- some display-pipeline notification that Grasshopper's Python 3
    engine doesn't trigger, that Rhino's classic scripting engine does.
    The fix is a SEPARATE step: after baking, run
    rhino/apply_facade_materials.py via rhino/run_rhino_script.py (the
    win32com/_-ScriptEditor Run COM bridge), which re-applies the exact
    same materials through that working pathway. This must be re-run after
    every re-bake, since clear_previous_bake() regenerates objects with
    this component's own (invisible) material assignment.
  - All dimensional constants are in FEET (this document's real-world unit
    system, confirmed by the user) -- no unit-scale conversion helper is
    needed here, unlike the earlier meter-based canopy scripts.

When pasting into an actual Grasshopper Python 3 Script component, the
component requires '#! python 3' as the literal first line -- prepend it
(and drop this docstring, or keep it below the directive) since this file
leads with documentation instead for readability as a repo reference copy.
"""
import json
import math
import os
from bisect import bisect_right

import Rhino
import Rhino.Geometry as rg
import System.Drawing

GLASS_MATERIAL_NAME = "PM_Glass_Panel"
GLASS_MATERIAL_HEX = "#CFE6E4"
MULLION_MATERIAL_NAME = "PM_Mullion_Metal"
MULLION_MATERIAL_HEX = "#4A4A4A"

# ---------------------------------------------------------------- constants
CANDIDATE_JSON_PATHS = [
    os.path.join(os.getcwd(), "PershingMetabolizer_Prototype", "real_geometry.json"),
    r"C:\Users\jcnor\MemoryMachine\PershingMetabolizer_Prototype\real_geometry.json",
]
FALLBACK_SITE_SIZE = (354.22, 602.53)

# Real site frame -- source of truth: Rhino/scripts/grid_ortho.py +
# grid_dtla.py (see docstring note above for why this superseded the old
# runtime-derived ORIGIN/COL_ANGLE_DEG=0.0).
ORIGIN = (319.89, 596.22)
COL_ANGLE_DEG = 0.4
BOUNDARY_PTS = [
    (-12.98, -3.09), (337.01, -0.67), (332.87, 599.31), (-17.12, 596.90),
]

COL_SPACING = 27.0
DTLA_SPACING_U = 336.0
DTLA_SPACING_V = 600.0
DTLA_ANGLE_DEG = 36.0 + COL_ANGLE_DEG
BOUNDARY_OFFSET = 9.0
SEED_TOL = 0.05

VERT_FACE_NORMAL_DOT = 0.1
MIN_FACE_AREA_FT2 = 4.0
MIN_PANEL_FT = 1.0

TARGET_ROOT_LAYER = "Detailed_Facades"
PROGRAM_LAYERS = [
    "PracticeSpace", "ComputerTechSpace", "ArtsAndCraftsStudio",
    "WorkOutEquipment", "PicnicGrillSpace", "Greenspace",
    "Skatepark", "CommunityCenter",
]

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
        return FALLBACK_SITE_SIZE, "FALLBACK (real_geometry.json not found)"
    width = data["site"]["width_ft"]
    length = data["site"]["length_ft"]
    return (width, length), used_path


SITE_SIZE, SITE_DATA_SOURCE = load_site_data()


# --------------------------------------- portable grid algorithm (spec 1-4,6)
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


def subdivide_interval(v0, v1, n_sub):
    return [v0 + (v1 - v0) * i / n_sub for i in range(n_sub + 1)]


col_lines, col_to_local, col_to_world, (col_n_lo, col_n_hi, col_m_lo, col_m_hi) = build_grid_lines(
    ORIGIN, COL_SPACING, COL_SPACING, COL_ANGLE_DEG, BOUNDARY_PTS, BOUNDARY_OFFSET)
dtla_lines, _dtla_to_local, _dtla_to_world, _dtla_range = build_grid_lines(
    ORIGIN, DTLA_SPACING_U, DTLA_SPACING_V, DTLA_ANGLE_DEG, BOUNDARY_PTS, BOUNDARY_OFFSET)

Us = list(range(col_n_lo, col_n_hi + 1))
Vs = list(range(col_m_lo, col_m_hi + 1))

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

# Behavior B marking: a seed sits on exactly one COLUMN-grid line (that's how
# it was constructed -- col_line x dtla_line). It straddles the two cells
# adjacent to that line, at the cross-index given by the seed's own position.
MARKED = set()
for (sx, sy, axis, idx) in seeds:
    lu, lv = col_to_local(sx, sy)
    if axis == "V" and idx in Vs:
        a = max(0, min(bisect_right(Us, lu / COL_SPACING) - 1, len(Us) - 2))
        p = Vs.index(idx)
        if p > 0:
            MARKED.add((a, p - 1))
        if p < len(Vs) - 1:
            MARKED.add((a, p))
    elif axis == "U" and idx in Us:
        b = max(0, min(bisect_right(Vs, lv / COL_SPACING) - 1, len(Vs) - 2))
        p = Us.index(idx)
        if p > 0:
            MARKED.add((p - 1, b))
        if p < len(Us) - 1:
            MARKED.add((p, b))


def cell_local_bounds(a, b):
    return Us[a] * COL_SPACING, Us[a + 1] * COL_SPACING, Vs[b] * COL_SPACING, Vs[b + 1] * COL_SPACING


def is_marked_world(wx, wy):
    lu, lv = col_to_local(wx, wy)
    a = bisect_right(Us, lu / COL_SPACING) - 1
    b = bisect_right(Vs, lv / COL_SPACING) - 1
    if a < 0 or b < 0 or a > len(Us) - 2 or b > len(Vs) - 2:
        return False
    return (a, b) in MARKED


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
    z0 = max(min(zs), 0.0)  # GradeClip: never panel below grade
    return o, h_axis, min(hs), max(hs), z0, max(zs)


def facade_h_joints(o, h_axis, h0, h1):
    p0 = (o.X + h0 * h_axis.X, o.Y + h0 * h_axis.Y)
    p1 = (o.X + h1 * h_axis.X, o.Y + h1 * h_axis.Y)
    joints = set([round(h0, 6), round(h1, 6)])
    for (c_p1, c_p2, _c_axis, _c_idx) in col_lines:
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


def make_cell_boxes(o, h_axis, h0, h1, z0, z1, depth_ft, mullion_ft, sub,
                     skip_brep, all_breps, out_panels):
    w, hgt = h1 - h0, z1 - z0
    if w < MIN_PANEL_FT or hgt < MIN_PANEL_FT * 0.3:
        return False
    hmid, zmid = (h0 + h1) / 2.0, (z0 + z1) / 2.0
    wx, wy = o.X + hmid * h_axis.X, o.Y + hmid * h_axis.Y
    if is_buried(wx, wy, zmid, skip_brep, all_breps):
        return False
    marked = is_marked_world(wx, wy)
    v_axis = rg.Vector3d.ZAxis
    gap = mullion_ft / 2.0

    def emit(hh0, hh1, zz0, zz1):
        ww, hh = hh1 - hh0, zz1 - zz0
        if ww <= gap * 2 or hh <= gap * 2:
            return
        plane = rg.Plane(rg.Point3d(o.X + hh0 * h_axis.X, o.Y + hh0 * h_axis.Y, zz0), h_axis, v_axis)
        box = rg.Box(plane, rg.Interval(gap, ww - gap), rg.Interval(gap, hh - gap), rg.Interval(0, depth_ft))
        out_panels.append(box.ToBrep())

    if not marked:
        emit(h0, h1, z0, z1)
        return False

    h_j = subdivide_interval(h0, h1, sub)
    z_j = subdivide_interval(z0, z1, sub)
    for i in range(len(h_j) - 1):
        for j in range(len(z_j) - 1):
            emit(h_j[i], h_j[i + 1], z_j[j], z_j[j + 1])
    return True


def facade_mullions(o, h_axis, h_joints, z0, z1, mullion_ft, depth_ft, out_mullions):
    v_axis = rg.Vector3d.ZAxis
    half = mullion_ft / 2.0
    for h in h_joints:
        plane = rg.Plane(rg.Point3d(o.X + h * h_axis.X, o.Y + h * h_axis.Y, z0), h_axis, v_axis)
        box = rg.Box(plane, rg.Interval(-half, half), rg.Interval(0, z1 - z0), rg.Interval(0, depth_ft))
        out_mullions.append(box.ToBrep())


def facade_floor_mullions(o, h_axis, h0, h1, z_lines, mullion_ft, depth_ft, out_mullions):
    v_axis = rg.Vector3d.ZAxis
    half = mullion_ft / 2.0
    for z in z_lines:
        plane = rg.Plane(rg.Point3d(o.X + h0 * h_axis.X, o.Y + h0 * h_axis.Y, z - half), h_axis, v_axis)
        box = rg.Box(plane, rg.Interval(0, h1 - h0), rg.Interval(0, mullion_ft), rg.Interval(0, depth_ft))
        out_mullions.append(box.ToBrep())


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
    # Always rebuild rather than reuse-by-name: an earlier run of this script
    # (or an external tool) may have left a same-named material with no real
    # PBR data, and silently reusing that stale entry would defeat the fix
    # below. Delete-then-recreate keeps every bake pass self-consistent.
    for i in range(rhino_doc.Materials.Count - 1, -1, -1):
        if rhino_doc.Materials[i].Name == name:
            rhino_doc.Materials.Delete(rhino_doc.Materials[i])
    # Build a self-contained legacy Material with real PBR channel data --
    # Rhino 8's Rendered/Raytraced pipeline is PBR-driven, so a plain
    # DiffuseColor-only stub (no PhysicallyBased data) can render as flat
    # white/default even though the object technically "has" a material.
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
    return rhino_doc.Materials.Add(mat)


def clear_previous_bake():
    """Delete objects under TARGET_ROOT_LAYER (keeps the layer structure so
    ensure_layer_path's find-or-create stays idempotent across re-bakes)."""
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
    sub = max(2, int(round(float(SubDiv)))) if SubDiv is not None else 4
    floor_ft = float(FloorFt) if FloorFt is not None else 13.5
    panel_depth_ft = float(PanelDepthFt) if PanelDepthFt is not None else 0.25
    mullion_ft = float(MullionFt) if MullionFt is not None else 0.5
    do_bake = bool(Bake) if Bake is not None else False

    grid_crv = [rg.LineCurve(rg.Point3d(p1[0], p1[1], 0.0), rg.Point3d(p2[0], p2[1], 0.0))
                for (p1, p2, _a, _i) in col_lines + dtla_lines]
    dtla_crv = [rg.LineCurve(rg.Point3d(p1[0], p1[1], 0.0), rg.Point3d(p2[0], p2[1], 0.0))
                for (p1, p2, _a, _i) in dtla_lines]
    seed_pts = [rg.Point3d(sx, sy, 0.0) for (sx, sy, _a, _i) in seeds]
    marked_crv = []
    for a in range(len(Us) - 1):
        for b in range(len(Vs) - 1):
            if (a, b) in MARKED:
                u0, u1, v0, v1 = cell_local_bounds(a, b)
                pts = [rg.Point3d(col_to_world(u, v)[0], col_to_world(u, v)[1], 0.05)
                       for (u, v) in [(u0, v0), (u1, v0), (u1, v1), (u0, v1), (u0, v0)]]
                marked_crv.append(rg.PolylineCurve(pts))

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

    panels_by_bldg, mullions_by_bldg, marked_facade_cells = {}, {}, {}
    for name, breps in bldg_breps.items():
        panels, mullions_list, marked_count = [], [], 0
        for brep in breps:
            for face, plane in facade_faces(brep):
                o, h_axis, h0, h1, z0, z1 = face_frame(face, plane)
                if h1 - h0 < MIN_PANEL_FT or z1 - z0 < MIN_PANEL_FT * 0.3:
                    continue
                h_joints = facade_h_joints(o, h_axis, h0, h1)
                bands = z_bands(z0, z1, floor_ft)
                for i in range(len(h_joints) - 1):
                    for (zz0, zz1) in bands:
                        was_marked = make_cell_boxes(
                            o, h_axis, h_joints[i], h_joints[i + 1], zz0, zz1,
                            panel_depth_ft, mullion_ft, sub, brep, all_breps, panels)
                        if was_marked:
                            marked_count += 1
                facade_mullions(o, h_axis, h_joints, z0, z1, mullion_ft, panel_depth_ft, mullions_list)
                z_lines = [bands[0][0]] + [bb[1] for bb in bands] if bands else [z0, z1]
                facade_floor_mullions(o, h_axis, h0, h1, z_lines, mullion_ft, panel_depth_ft, mullions_list)
        panels_by_bldg[name] = panels
        mullions_by_bldg[name] = mullions_list
        marked_facade_cells[name] = marked_count

    all_panels = [p for v in panels_by_bldg.values() for p in v]
    all_mullions = [m for v in mullions_by_bldg.values() for m in v]

    log_lines = [
        "site_data_source={}".format(SITE_DATA_SOURCE),
        "col_lines={} dtla_lines={} seeds={} cells={} marked={}".format(
            len(col_lines), len(dtla_lines), len(seeds), (len(Us) - 1) * (len(Vs) - 1), len(MARKED)),
        "ORIGIN=({:.3f},{:.3f})  site={:.2f}x{:.2f}ft".format(ORIGIN[0], ORIGIN[1], SITE_SIZE[0], SITE_SIZE[1]),
    ]
    for name in PROGRAM_LAYERS:
        if name in panels_by_bldg:
            log_lines.append("{}: marked_facade_cells={} panels={} mullions={}".format(
                name, marked_facade_cells[name], len(panels_by_bldg[name]), len(mullions_by_bldg[name])))
    log_lines.append("TOTAL panels={} mullions={}".format(len(all_panels), len(all_mullions)))

    if do_bake:
        clear_previous_bake()
        glass_idx = find_or_make_material(GLASS_MATERIAL_NAME, GLASS_MATERIAL_HEX,
                                           metallic=0.0, roughness=0.05, transparency=0.8)
        mullion_idx = find_or_make_material(MULLION_MATERIAL_NAME, MULLION_MATERIAL_HEX,
                                             metallic=0.9, roughness=0.3, transparency=0.0)
        ensure_layer_path(TARGET_ROOT_LAYER + "::_Parti::ColumnGrid")
        ensure_layer_path(TARGET_ROOT_LAYER + "::_Parti::DtlaGrid")
        ensure_layer_path(TARGET_ROOT_LAYER + "::_Parti::Seeds")
        ensure_layer_path(TARGET_ROOT_LAYER + "::_Parti::MarkedCells")
        col_attr = attrs_for(TARGET_ROOT_LAYER + "::_Parti::ColumnGrid")
        for (p1, p2, _ax, _ix) in col_lines:
            rhino_doc.Objects.AddLine(rg.Point3d(p1[0], p1[1], 0.0), rg.Point3d(p2[0], p2[1], 0.0), col_attr)
        dtla_attr = attrs_for(TARGET_ROOT_LAYER + "::_Parti::DtlaGrid")
        for (p1, p2, _ax, _ix) in dtla_lines:
            rhino_doc.Objects.AddLine(rg.Point3d(p1[0], p1[1], 0.0), rg.Point3d(p2[0], p2[1], 0.0), dtla_attr)
        seed_attr = attrs_for(TARGET_ROOT_LAYER + "::_Parti::Seeds")
        for pt in seed_pts:
            rhino_doc.Objects.AddPoint(pt, seed_attr)
        marked_attr = attrs_for(TARGET_ROOT_LAYER + "::_Parti::MarkedCells")
        for crv in marked_crv:
            rhino_doc.Objects.AddCurve(crv, marked_attr)

        for name in PROGRAM_LAYERS:
            if name not in panels_by_bldg:
                continue
            panel_layer = "{}::{}::Panels".format(TARGET_ROOT_LAYER, name)
            mullion_layer = "{}::{}::Mullions".format(TARGET_ROOT_LAYER, name)
            ensure_layer_path(panel_layer)
            ensure_layer_path(mullion_layer)
            p_idx = rhino_doc.Layers.FindByFullPath(panel_layer, -1)
            m_idx = rhino_doc.Layers.FindByFullPath(mullion_layer, -1)
            rhino_doc.Layers[p_idx].RenderMaterialIndex = glass_idx
            rhino_doc.Layers[m_idx].RenderMaterialIndex = mullion_idx
            # Object attrs left at their default MaterialSource (MaterialFromLayer)
            # so every panel/mullion inherits its layer's material automatically --
            # no per-object material assignment needed for ~1800 objects.
            p_attr, m_attr = attrs_for(panel_layer), attrs_for(mullion_layer)
            for brep in panels_by_bldg[name]:
                rhino_doc.Objects.AddBrep(brep, p_attr)
            for brep in mullions_by_bldg[name]:
                rhino_doc.Objects.AddBrep(brep, m_attr)
        rhino_doc.Views.Redraw()
        log_lines.append("BAKED to {}::*".format(TARGET_ROOT_LAYER))

    return all_panels, all_mullions, grid_crv, dtla_crv, seed_pts, marked_crv, "\n".join(log_lines)


if rhino_doc is None:
    Panels, Mullions, GridCrv, DtlaLines, SeedPts, MarkedCrv, Log = [], [], [], [], [], [], "ERROR: no active Rhino document"
else:
    Panels, Mullions, GridCrv, DtlaLines, SeedPts, MarkedCrv, Log = run()
    print(Log)
