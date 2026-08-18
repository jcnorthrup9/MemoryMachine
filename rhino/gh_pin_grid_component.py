"""
GhPython Script component: PM_PinGrid
--------------------------------------------------------------------
Paste into a "Python 3 Script" component (Maths > Script > Python 3 Script,
guid 719467e6-7cf5-4848-99b0-c5dd57e5442c) on the same Grasshopper canvas as
FidelityGrid1's PM_FacadePanelizer (rhino/gh_facade_panelizer_component.py).
See PershingMetabolizer_Prototype/PIN_GRID.md for the full writeup.

REVISION 2 (this session, same day as REVISION 1): recalibrated after
direct user feedback on the first version. REVISION 1 generated two UNIFORM
grids of freestanding pins (a 9ft "coarse" grid subdividing the idealized
27ft column module, a 1.5ft "fine" grid), every pin's height driven by a
continuous density gradient -- every point got SOME pin, just varying in
height. The user's correction, verbatim: "the points at 27 feet can be the
columns on site, this operates as the scaffolding, then the other
implements such as mullions and open spaces are determined by the
algorithm." Clarified via follow-up: (1) the 27ft anchors should be the
REAL surveyed columns from real_geometry.json, not an idealized uniform
grid; (2) the fine layer should be BINARY zones with real open voids, not
a continuous gradient; (3) the fine elements should be straight mullion-BAR
members (thin strips, like FidelityGrid1's real mullions), not
free-standing pins.

This revision recombines THREE pieces of logic already proven elsewhere in
this session, rather than inventing a new algorithm:
  - Real column positions (real_geometry.json's column_positions -- 294
    actual surveyed points, irregularly spaced ~27ft apart with real gaps)
    become the "scaffolding" layer -- sparse, tall, literal structure.
  - FidelityGrid1's own MARKED cell field (col-grid x DTLA-grid collision,
    byte-for-byte the same `is_marked_world` logic FG1's panels and
    PM_ScaffoldFrame's growth bays already use) decides WHERE the fine
    layer appears at all -- marked cells get a mullion screen, unmarked
    cells are genuinely empty (open space), not a shorter pin.
  - FidelityGrid1's own facade_mullions/facade_floor_mullions box-building
    idiom (straight strips along grid lines) becomes the mullion form,
    applied in PLAN instead of on a facade.

Unlike FG1/FG2/ScaffoldFrame (which skin a building's own facade faces),
this system fills the PLAN INTERIOR of a footprint -- more like a
landscape/plaza treatment than a wall.

Component setup
----------------
Inputs (item access, Generic Data -- cast explicitly in code):
  Bake            : bool  -- Boolean Toggle. False = preview only.
  Refresh         : bool  -- unused (deterministic, no RNG); wired for
                    future use.
  ScaffoldHeightFt: float -- Number Slider, 0-60, default = real
                    column_height_ft from real_geometry.json (30.0) --
                    NOT density-driven. These represent literal real
                    structure, so they get the real structural height, not
                    an algorithmic field.
  ScaffoldStickFt : float -- Number Slider, 0.25-3, default 1.2. Real
                    column post square cross-section.
  MullionSubDiv   : int   -- Number Slider, 2-30, default 10. How many
                    fine grid lines subdivide a MARKED 27ft cell's own
                    local extent (~2.7ft spacing at default) -- same
                    subdivide_interval() idiom FG1 uses for its marked-cell
                    panel subdivision, applied to mullion-line spacing
                    instead.
  MullionHeightFt : float -- Number Slider, 0-30, default 8.0. Mullion
                    strip height (uniform within a marked cell -- these are
                    algorithmic infill, not real surveyed structure, so a
                    single tunable height is appropriate).
  MullionWidthFt  : float -- Number Slider, 0.05-2, default 0.35. Mullion
                    strip in-plan cross-section width (perpendicular to
                    each strip's own run direction). NOTE: unlike FG1's
                    facade mullions, there is no separate "depth away from
                    the glass plane" dimension here -- a plan-fill vertical
                    strip has no facade normal to project along, so a
                    single width parameter is the complete, correct
                    cross-section (a planned second "MullionDepthFt" was
                    dropped as not meaningful for this orientation).

Outputs:
  ScaffoldPosts  : Breps (real-column scaffolding posts)
  MullionMembers : Breps (mullion-strip screens, marked cells only)
  Log            : str summary -- wire to a Panel.

Assumptions made explicit here because the prompt didn't pin them down:
  - Footprint source, THIS PROTOTYPE ONLY: every closed planar curve found
    on FOOTPRINT_LAYER ("Default") in the active document. On the real
    Pershing document this should become each Program::* building's own
    plan footprint -- swapping FOOTPRINT_LAYER-gathering for that is the
    ONLY change needed to port this to real buildings; everything else
    (real-column filtering, MARKED-cell overlap, mullion emission) is
    already written generically against "a closed planar curve."
  - col_lines/dtla_lines/seeds/MARKED are computed with the same corrected
    real ORIGIN/COL_ANGLE_DEG/BOUNDARY_PTS as FG1 and PM_ScaffoldFrame (see
    FG1's docstring for the correction rationale -- traced to Rhino/scripts/
    grid_ortho.py + grid_dtla.py), so this component's marked-cell field
    agrees with FG1's own zones rather than introducing a second,
    disagreeing convention.
  - COLUMN_POSITIONS (real_geometry.json's raw column data) live in a
    different local frame than ORIGIN/BOUNDARY_PTS above -- translated by
    COLUMN_FRAME_TRANSLATE before use (see constants block).
  - Real columns are filtered into a footprint via Curve.Contains -- exact
    point-in-polygon, no snapping or nearest-match. A footprint with no
    real column inside it (quite possible for a single small test bay --
    real columns are ~27ft apart, so a lone bay may contain zero) will
    have an empty ScaffoldPosts output; the Log warns explicitly rather
    than silently baking nothing.
  - MARKED-cell overlap is tested at each cell's own local-grid MIDPOINT
    against the footprint curve (same "sample the cell center" idiom FG1's
    make_cell_boxes and PM_ScaffoldFrame's bay-marking already use) -- not
    a true polygon-clip, so a cell that's mostly outside the footprint but
    whose exact center happens to fall inside (or vice versa) is an
    acceptable approximation at this prototype stage, consistent with how
    the rest of this project already treats cell/footprint overlap.
  - No is_buried() culling yet (no "other building" concept for a lone
    test footprint) -- add it when porting to real multi-building
    footprints, mirroring FG1/PM_ScaffoldFrame's existing pattern.
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

SCAFFOLD_MATERIAL_NAME = "PM_Pin_Coarse"   # kept from REVISION 1 -- now means "scaffold"
SCAFFOLD_MATERIAL_HEX = "#5A5A5A"
MULLION_MATERIAL_NAME = "PM_Pin_Fine"      # kept from REVISION 1 -- now means "mullion"
MULLION_MATERIAL_HEX = "#2FA6A0"

# ---------------------------------------------------------------- constants
CANDIDATE_JSON_PATHS = [
    os.path.join(os.getcwd(), "PershingMetabolizer_Prototype", "real_geometry.json"),
    r"C:\Users\jcnor\MemoryMachine\PershingMetabolizer_Prototype\real_geometry.json",
]
FALLBACK_SITE_SIZE = (354.22, 602.53)
FALLBACK_COLUMN_HEIGHT_FT = 30.0

# Real site frame -- source of truth: Rhino/scripts/grid_ortho.py +
# grid_dtla.py. Must match FG1's own constants exactly (see FG1's
# docstring for the correction rationale).
ORIGIN = (319.89, 596.22)
COL_ANGLE_DEG = 0.4
BOUNDARY_PTS = [
    (-12.98, -3.09), (337.01, -0.67), (332.87, 599.31), (-17.12, 596.90),
]
# real_geometry.json's column_positions are in a different local frame
# (bottom-left column at approx (13.028, 3.124), not (0,0)-ish like
# grid_ortho.py's frame) -- translate into the same frame as ORIGIN/
# BOUNDARY_PTS above before use. Translation-only; a residual sub-degree
# rotation between the two frames is not corrected (known approximation).
COLUMN_FRAME_TRANSLATE = (-13.028, -3.124)

COL_SPACING = 27.0
DTLA_SPACING_U = 336.0
DTLA_SPACING_V = 600.0
DTLA_ANGLE_DEG = 36.0 + COL_ANGLE_DEG
BOUNDARY_OFFSET = 9.0
SEED_TOL = 0.05

FOOTPRINT_LAYER = "Default"
TARGET_ROOT_LAYER = "Detailed_PinGrid"
MIN_FOOTPRINT_FT2 = 4.0

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
        return (FALLBACK_SITE_SIZE, "FALLBACK (real_geometry.json not found)",
                [], FALLBACK_COLUMN_HEIGHT_FT)
    width = data["site"]["width_ft"]
    length = data["site"]["length_ft"]
    columns_raw = data["column_positions"]
    tx, tz = COLUMN_FRAME_TRANSLATE
    column_positions = [(c["x"] + tx, c["z"] + tz) for c in columns_raw]
    column_height_ft = data.get("column_height_ft", FALLBACK_COLUMN_HEIGHT_FT)
    return (width, length), used_path, column_positions, column_height_ft


SITE_SIZE, SITE_DATA_SOURCE, COLUMN_POSITIONS, COLUMN_HEIGHT_FT = load_site_data()


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

# Behavior B marking -- byte-for-byte FG1's MARKED field, so this component
# agrees with FG1's own already-accepted "structurally interesting zone"
# definition rather than inventing a second one.
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


# ---------------------------------------------------------- footprint geometry
def coerce_curve(geo):
    if isinstance(geo, rg.Curve):
        return geo
    return None


def gather_footprints():
    idx = rhino_doc.Layers.FindByFullPath(FOOTPRINT_LAYER, -1)
    if idx < 0:
        return []
    out = []
    for rh_obj in rhino_doc.Objects.FindByLayer(rhino_doc.Layers[idx]):
        crv = coerce_curve(rh_obj.Geometry)
        if crv is None or not crv.IsClosed or not crv.IsPlanar(TOL):
            continue
        amp = rg.AreaMassProperties.Compute(crv)
        if amp is None or amp.Area < MIN_FOOTPRINT_FT2:
            continue
        out.append(crv)
    return out


def point_in_curve(crv, x, y):
    containment = crv.Contains(rg.Point3d(x, y, 0.0), rg.Plane.WorldXY, TOL)
    return containment == rg.PointContainment.Inside or containment == rg.PointContainment.Coincident


def make_pin(px, py, height, stick_ft):
    if height <= 0.0:
        return None
    half = stick_ft / 2.0
    plane = rg.Plane(rg.Point3d(px, py, 0.0), rg.Vector3d.XAxis, rg.Vector3d.YAxis)
    box = rg.Box(plane, rg.Interval(-half, half), rg.Interval(-half, half), rg.Interval(0, height))
    return box.ToBrep()


def make_strip(x0, y0, x1, y1, height, width_ft):
    """One straight vertical strip Box running from (x0,y0) to (x1,y1) in
    plan, Z=0 to height, width_ft thick perpendicular to its own run
    direction -- the plan-fill analogue of FG1's facade_mullions box."""
    dx, dy = x1 - x0, y1 - y0
    length = math.hypot(dx, dy)
    if length < 1e-6 or height <= 0.0:
        return None
    dir_vec = rg.Vector3d(dx / length, dy / length, 0.0)
    normal_vec = rg.Vector3d(-dir_vec.Y, dir_vec.X, 0.0)
    plane = rg.Plane(rg.Point3d(x0, y0, 0.0), dir_vec, normal_vec)
    half = width_ft / 2.0
    box = rg.Box(plane, rg.Interval(0, length), rg.Interval(-half, half), rg.Interval(0, height))
    return box.ToBrep()


def scaffold_columns(crv, height, stick_ft):
    """Real surveyed columns (real_geometry.json) that fall inside crv --
    the sparse, literal-structure 'scaffolding' layer."""
    posts = []
    for (cx, cy) in COLUMN_POSITIONS:
        if not point_in_curve(crv, cx, cy):
            continue
        post = make_pin(cx, cy, height, stick_ft)
        if post is not None:
            posts.append(post)
    return posts


def mullion_cells(crv, sub, height, width_ft, cell_stats):
    """FG1's MARKED 27ft cells that overlap crv get a criss-cross mullion
    strip screen; unmarked overlapping cells get nothing -- a genuine open
    void, not a shorter pin."""
    bbox = crv.GetBoundingBox(True)
    corners_local = [
        col_to_local(bbox.Min.X, bbox.Min.Y), col_to_local(bbox.Max.X, bbox.Min.Y),
        col_to_local(bbox.Max.X, bbox.Max.Y), col_to_local(bbox.Min.X, bbox.Max.Y),
    ]
    lus = [c[0] for c in corners_local]
    lvs = [c[1] for c in corners_local]
    a_lo = max(0, bisect_right(Us, min(lus) / COL_SPACING) - 1)
    a_hi = min(len(Us) - 2, bisect_right(Us, max(lus) / COL_SPACING) - 1)
    b_lo = max(0, bisect_right(Vs, min(lvs) / COL_SPACING) - 1)
    b_hi = min(len(Vs) - 2, bisect_right(Vs, max(lvs) / COL_SPACING) - 1)

    members = []
    overlapping = marked_count = 0
    for a in range(a_lo, a_hi + 1):
        for b in range(b_lo, b_hi + 1):
            u0, u1, v0, v1 = cell_local_bounds(a, b)
            wx, wy = col_to_world((u0 + u1) / 2.0, (v0 + v1) / 2.0)
            if not point_in_curve(crv, wx, wy):
                continue
            overlapping += 1
            if (a, b) not in MARKED:
                continue
            marked_count += 1
            for u in subdivide_interval(u0, u1, sub):
                x0, y0 = col_to_world(u, v0)
                x1, y1 = col_to_world(u, v1)
                strip = make_strip(x0, y0, x1, y1, height, width_ft)
                if strip is not None:
                    members.append(strip)
            for v in subdivide_interval(v0, v1, sub):
                x0, y0 = col_to_world(u0, v)
                x1, y1 = col_to_world(u1, v)
                strip = make_strip(x0, y0, x1, y1, height, width_ft)
                if strip is not None:
                    members.append(strip)
    cell_stats.append((overlapping, marked_count))
    return members


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
    scaffold_height = float(ScaffoldHeightFt) if ScaffoldHeightFt is not None else COLUMN_HEIGHT_FT
    scaffold_stick = float(ScaffoldStickFt) if ScaffoldStickFt is not None else 1.2
    mullion_sub = max(2, int(round(float(MullionSubDiv)))) if MullionSubDiv is not None else 10
    mullion_height = float(MullionHeightFt) if MullionHeightFt is not None else 8.0
    mullion_width = float(MullionWidthFt) if MullionWidthFt is not None else 0.35
    do_bake = bool(Bake) if Bake is not None else False

    footprints = gather_footprints()

    all_scaffold, all_mullion = [], []
    scaffold_by_fp, mullion_by_fp = [], []
    column_counts = []
    cell_stats = []

    for crv in footprints:
        s_posts = scaffold_columns(crv, scaffold_height, scaffold_stick)
        m_members = mullion_cells(crv, mullion_sub, mullion_height, mullion_width, cell_stats)
        scaffold_by_fp.append(s_posts)
        mullion_by_fp.append(m_members)
        all_scaffold.extend(s_posts)
        all_mullion.extend(m_members)
        column_counts.append(len(s_posts))

    total_columns = sum(column_counts)
    total_overlap = sum(o for (o, m) in cell_stats)
    total_marked = sum(m for (o, m) in cell_stats)

    log_lines = [
        "site_data_source={}".format(SITE_DATA_SOURCE),
        "ORIGIN=({:.3f},{:.3f})  column_height_ft={}".format(ORIGIN[0], ORIGIN[1], COLUMN_HEIGHT_FT),
        "seeds={} footprints={} realColumnsInSite={}".format(len(seeds), len(footprints), len(COLUMN_POSITIONS)),
        "scaffoldHeight={} scaffoldStick={}".format(scaffold_height, scaffold_stick),
        "mullionSub={} mullionHeight={} mullionWidth={}".format(mullion_sub, mullion_height, mullion_width),
        "columnsInFootprints={}{}".format(
            total_columns,
            "  (WARNING: zero real columns fall inside any footprint -- scaffolding layer is empty)"
            if total_columns == 0 else ""),
        "cellsOverlapping={} cellsMarked={}{}".format(
            total_overlap, total_marked,
            "  (WARNING: zero marked cells -- footprint may be entirely open/void; try a larger footprint)"
            if total_marked == 0 else ""),
        "scaffoldPosts={} mullionMembers={}".format(len(all_scaffold), len(all_mullion)),
    ]

    if do_bake:
        clear_previous_bake()
        scaffold_idx = find_or_make_material(SCAFFOLD_MATERIAL_NAME, SCAFFOLD_MATERIAL_HEX,
                                              metallic=0.1, roughness=0.7, transparency=0.0)
        mullion_idx = find_or_make_material(MULLION_MATERIAL_NAME, MULLION_MATERIAL_HEX,
                                             metallic=0.2, roughness=0.4, transparency=0.0)
        for i, crv in enumerate(footprints):
            scaffold_layer = "{}::Footprint{}::Scaffold".format(TARGET_ROOT_LAYER, i)
            mullion_layer = "{}::Footprint{}::Mullion".format(TARGET_ROOT_LAYER, i)
            ensure_layer_path(scaffold_layer)
            ensure_layer_path(mullion_layer)
            s_idx = rhino_doc.Layers.FindByFullPath(scaffold_layer, -1)
            m_idx = rhino_doc.Layers.FindByFullPath(mullion_layer, -1)
            rhino_doc.Layers[s_idx].RenderMaterialIndex = scaffold_idx
            rhino_doc.Layers[m_idx].RenderMaterialIndex = mullion_idx
            s_attr, m_attr = attrs_for(scaffold_layer), attrs_for(mullion_layer)
            for brep in scaffold_by_fp[i]:
                rhino_doc.Objects.AddBrep(brep, s_attr)
            for brep in mullion_by_fp[i]:
                rhino_doc.Objects.AddBrep(brep, m_attr)
        rhino_doc.Views.Redraw()
        log_lines.append("BAKED to {}::*".format(TARGET_ROOT_LAYER))

    return all_scaffold, all_mullion, "\n".join(log_lines)


if rhino_doc is None:
    ScaffoldPosts, MullionMembers, Log = [], [], "ERROR: no active Rhino document"
else:
    ScaffoldPosts, MullionMembers, Log = run()
    print(Log)
