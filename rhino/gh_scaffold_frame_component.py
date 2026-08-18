"""
GhPython Script component: PM_ScaffoldFrame
--------------------------------------------------------------------
Paste into a "Python 3 Script" component (Maths > Script > Python 3 Script,
guid 719467e6-7cf5-4848-99b0-c5dd57e5442c) on the same Grasshopper canvas as
FidelityGrid1's PM_FacadePanelizer. See PershingMetabolizer_Prototype/
SCAFFOLD_FRAME.md for the full writeup.

Purpose: this REPLACES PM_GrowthScaffold (the agent-based voxel-growth
system, now disabled/preserved -- see
PershingMetabolizer_Prototype/GROWTH_SCAFFOLD.md) after direct user
feedback that its short zigzagging voxel steps read as diagonal, and that
its cross-building bridging left the buildings' own footprints entirely.
The brief, verbatim: "the growth should be contained within the footprint
of the buildings. they also don't need to be voxelized growths that go out
at an angle like that. they should be made of straight components,
orthogonal vertical and horizontal pieces. maybe the mullion and
fenestration script that you made first was closer to that logic."

So this is a direct 3D extension of FidelityGrid1's own proven logic
(PM_FacadePanelizer, rhino/gh_facade_panelizer_component.py) -- same site
data, same column-grid/DTLA-grid collision field, same facade-detection and
per-building framing -- reused near-verbatim, NOT a new simulation. There is
no agent, no voxel-collision set, no diagonal-reading zigzag: every member
is a single straight Box aligned to either the facade's own horizontal axis
or world Z, built with FidelityGrid1's own facade_mullions()/
facade_floor_mullions() box-primitive helpers. Because every face is
processed per-building from that building's own Brep, structure never
leaves that building's own footprint or bridges to another mass -- there is
no site-wide pooled target set like the old component had.

"Growth" here means: every facade always gets FidelityGrid1's baseline
mullion grid (real column-grid verticals + real floor-line horizontals,
spanning the whole facade) -- a plain orthogonal frame skeleton on every
building, everywhere. On top of that baseline, bays whose plan-footprint
falls in one of FidelityGrid1's own "marked" cells (the same column x DTLA
grid collision field that already drives FG1's dense panel subdivision)
get an EXTRA, denser sub-grid of members within that one bay only -- more
vertical posts, more horizontal rails, reading as a built-up, scaffolded
zone -- while unmarked bays stay a plain single rectangular frame. This
reuses the exact same "interesting zone" definition FG1 already
established and the user already accepted, rather than inventing a new
attractor/height-tier concept.

Component setup
----------------
Inputs (item access, Generic Data -- cast explicitly in code):
  Bake       : bool  -- Boolean Toggle. False = preview only.
  Refresh    : bool  -- unused (fully deterministic, no RNG); wired for
               future use.
  SubDiv     : int   -- Slider, 2-8, default 3. Extra vertical-post /
               horizontal-rail count within each MARKED bay only (see
               FidelityGrid1's SubDiv for the parent concept -- same
               subdivide_interval() helper, applied along a bay's own
               h-range and each floor band's own z-range instead of a 2D
               panel cell).
  FloorFt    : float -- Slider, 6-27, default 13.5. Real floor-line
               spacing for the baseline horizontal rails -- identical
               meaning to FG1's FloorFt.
  MemberFt   : float -- Slider, 0.25-2.0, default 0.75. Square member
               cross-section (both box half-width and depth-along-normal)
               -- deliberately a single fixed stock size for every member,
               same "uniform dimensional lumber" reasoning as the old
               GrowthScaffold's StickSizeFt, just applied to straight
               mullion-style boxes instead of short voxel-hop boxes.

Outputs:
  Members : Breps (every straight vertical/horizontal member, baseline +
            growth, all buildings)
  Log     : str summary -- wire to a Panel.

Assumptions made explicit here because the prompt didn't pin them down:
  - Reuses FG1's col_lines/dtla_lines/seeds/MARKED field VERBATIM, including
    FG1's corrected real ORIGIN/COL_ANGLE_DEG/BOUNDARY_PTS (see FG1's own
    docstring for the correction rationale -- traced to Rhino/scripts/
    grid_ortho.py + grid_dtla.py, confirmed same site/survey). Both
    components must keep using the exact same constants, since they both
    draw lines on the same facades and would visibly disagree otherwise.
  - Bay marking is evaluated ONCE per bay at its plan midpoint
    (is_marked_world(wx, wy) at h=hmid), constant across the bay's full
    z0..z1 height -- this mirrors FG1's own make_cell_boxes(), whose marked
    check also only depends on (wx, wy), never z, so re-deriving it per
    floor band would be redundant, not more accurate.
  - The baseline mullion grid (facade_mullions + facade_floor_mullions,
    called once per facade across its FULL h/z range) runs unconditionally,
    with no is_buried() culling -- this matches FG1's own Mullions output,
    which is likewise unculled (only individual PANELS are buried-culled in
    FG1, never the mullion grid itself). The growth layer's extra per-bay
    density IS buried-culled, mirroring FG1's make_cell_boxes() panel
    culling.
  - Buildings are processed one at a time, each from only its own Brep's
    faces -- there is no cross-building geometry query of any kind, which
    is what guarantees containment within each building's own footprint.
  - All dimensional constants are in FEET, matching every other script in
    this repo.

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

SCAFFOLD_MATERIAL_NAME = "PM_Scaffold_Timber"
SCAFFOLD_MATERIAL_HEX = "#B07C4A"

# ---------------------------------------------------------------- constants
CANDIDATE_JSON_PATHS = [
    os.path.join(os.getcwd(), "PershingMetabolizer_Prototype", "real_geometry.json"),
    r"C:\Users\jcnor\MemoryMachine\PershingMetabolizer_Prototype\real_geometry.json",
]
FALLBACK_SITE_SIZE = (354.22, 602.53)

# Real site frame -- source of truth: Rhino/scripts/grid_ortho.py +
# grid_dtla.py. Must match FG1's own constants exactly (see FG1's
# docstring for the correction rationale).
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

TARGET_ROOT_LAYER = "Detailed_ScaffoldFrame"
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


# --------------------------------------- portable grid algorithm (FG1 verbatim)
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
    z0 = max(min(zs), 0.0)
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


# ------------------------------------------------------- straight member primitives
def facade_mullions(o, h_axis, h_joints, z0, z1, member_ft, depth_ft, out_members):
    """One straight vertical Box per h in h_joints, full z0->z1 height."""
    v_axis = rg.Vector3d.ZAxis
    half = member_ft / 2.0
    for h in h_joints:
        plane = rg.Plane(rg.Point3d(o.X + h * h_axis.X, o.Y + h * h_axis.Y, z0), h_axis, v_axis)
        box = rg.Box(plane, rg.Interval(-half, half), rg.Interval(0, z1 - z0), rg.Interval(0, depth_ft))
        out_members.append(box.ToBrep())


def facade_floor_mullions(o, h_axis, h0, h1, z_lines, member_ft, depth_ft, out_members):
    """One straight horizontal Box per z in z_lines, spanning h0->h1."""
    v_axis = rg.Vector3d.ZAxis
    half = member_ft / 2.0
    for z in z_lines:
        plane = rg.Plane(rg.Point3d(o.X + h0 * h_axis.X, o.Y + h0 * h_axis.Y, z - half), h_axis, v_axis)
        box = rg.Box(plane, rg.Interval(0, h1 - h0), rg.Interval(0, member_ft), rg.Interval(0, depth_ft))
        out_members.append(box.ToBrep())


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
    sub = max(2, int(round(float(SubDiv)))) if SubDiv is not None else 3
    floor_ft = float(FloorFt) if FloorFt is not None else 13.5
    member_ft = float(MemberFt) if MemberFt is not None else 0.75
    do_bake = bool(Bake) if Bake is not None else False

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

    members_by_bldg = {}
    base_count, grown_count, marked_bays_count, total_bays_count = {}, {}, {}, {}

    for name, breps in bldg_breps.items():
        members = []
        base_n = grown_n = marked_bays = total_bays = 0
        for brep in breps:
            for face, plane in facade_faces(brep):
                o, h_axis, h0, h1, z0, z1 = face_frame(face, plane)
                if h1 - h0 < MIN_PANEL_FT or z1 - z0 < MIN_PANEL_FT * 0.3:
                    continue
                h_joints = facade_h_joints(o, h_axis, h0, h1)
                bands = z_bands(z0, z1, floor_ft)
                z_lines = [bands[0][0]] + [bb[1] for bb in bands] if bands else [z0, z1]

                # 1) Baseline frame: FG1's own mullion grid, unconditional, unculled.
                before = len(members)
                facade_mullions(o, h_axis, h_joints, z0, z1, member_ft, member_ft, members)
                facade_floor_mullions(o, h_axis, h0, h1, z_lines, member_ft, member_ft, members)
                base_n += len(members) - before

                # 2) Growth layer: extra density in MARKED bays only.
                for i in range(len(h_joints) - 1):
                    hb0, hb1 = h_joints[i], h_joints[i + 1]
                    total_bays += 1
                    hmid = (hb0 + hb1) / 2.0
                    wx, wy = o.X + hmid * h_axis.X, o.Y + hmid * h_axis.Y
                    if is_buried(wx, wy, (z0 + z1) / 2.0, brep, all_breps):
                        continue
                    if not is_marked_world(wx, wy):
                        continue
                    marked_bays += 1
                    before2 = len(members)
                    verts_h = subdivide_interval(hb0, hb1, sub)
                    facade_mullions(o, h_axis, verts_h, z0, z1, member_ft, member_ft, members)
                    for (bb0, bb1) in bands:
                        rails_z = subdivide_interval(bb0, bb1, sub)
                        facade_floor_mullions(o, h_axis, hb0, hb1, rails_z, member_ft, member_ft, members)
                    grown_n += len(members) - before2

        members_by_bldg[name] = members
        base_count[name] = base_n
        grown_count[name] = grown_n
        marked_bays_count[name] = marked_bays
        total_bays_count[name] = total_bays

    all_members = [m for v in members_by_bldg.values() for m in v]

    log_lines = [
        "site_data_source={}".format(SITE_DATA_SOURCE),
        "col_lines={} dtla_lines={} seeds={} marked_cells={}".format(
            len(col_lines), len(dtla_lines), len(seeds), len(MARKED)),
        "ORIGIN=({:.3f},{:.3f})  site={:.2f}x{:.2f}ft".format(ORIGIN[0], ORIGIN[1], SITE_SIZE[0], SITE_SIZE[1]),
        "sub={} floorFt={} memberFt={}".format(sub, floor_ft, member_ft),
    ]
    for name in PROGRAM_LAYERS:
        if name in members_by_bldg:
            log_lines.append(
                "{}: bays={} marked_bays={} base_members={} grown_members={} total={}".format(
                    name, total_bays_count[name], marked_bays_count[name],
                    base_count[name], grown_count[name], len(members_by_bldg[name])))
    log_lines.append("TOTAL members={}".format(len(all_members)))

    if do_bake:
        clear_previous_bake()
        scaffold_idx = find_or_make_material(SCAFFOLD_MATERIAL_NAME, SCAFFOLD_MATERIAL_HEX,
                                              metallic=0.0, roughness=0.75, transparency=0.0)
        for name in PROGRAM_LAYERS:
            if name not in members_by_bldg:
                continue
            member_layer = "{}::{}::Members".format(TARGET_ROOT_LAYER, name)
            ensure_layer_path(member_layer)
            m_idx = rhino_doc.Layers.FindByFullPath(member_layer, -1)
            rhino_doc.Layers[m_idx].RenderMaterialIndex = scaffold_idx
            m_attr = attrs_for(member_layer)
            for brep in members_by_bldg[name]:
                rhino_doc.Objects.AddBrep(brep, m_attr)
        rhino_doc.Views.Redraw()
        log_lines.append("BAKED to {}::*".format(TARGET_ROOT_LAYER))

    return all_members, "\n".join(log_lines)


if rhino_doc is None:
    Members, Log = [], "ERROR: no active Rhino document"
else:
    Members, Log = run()
    print(Log)
