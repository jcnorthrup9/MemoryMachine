"""
GhPython Script component: PM_GrowthColumns
--------------------------------------------------------------------
Paste into a "Python 3 Script" component (Maths > Script > Python 3 Script,
guid 719467e6-7cf5-4848-99b0-c5dd57e5442c) on the FidelityGrid1.gh canvas,
alongside PM_PinGrid (rhino/gh_pin_grid_component.py). See
PershingMetabolizer_Prototype/GROWTH_COLUMNS.md for the full writeup.

Purpose: generates correctly-scaled SAMPLE POINTS on the site's real
column module -- a 27ft "major" grid and a 9ft "mullion" grid nested
inside it -- for PM_GrowthAgents (rhino/gh_growth_agents_component.py) to
grow. This component does NOT build any geometry itself and does NOT run
the growth algorithm -- it is a pure point generator for BOTH grids.

Originally major-grid points were built here directly as fixed straight
pins (literal, ungrown structure), while only mullion points were routed
through the growth script -- the design rationale at the time being
"27ft points are the real columns / scaffolding, mullions are what the
algorithm determines." Per explicit user direction ("they both should
have this logic"), that asymmetry is gone: BOTH grids are now just point
output from this component, and BOTH get grown by two separate instances
of PM_GrowthAgents downstream (one per grid, with different
RigidityBias/MaxGens/Speed so major-grid growth stays close to vertical
and reads as structural, while mullion growth branches more freely -- see
PM_GrowthAgents' own docstring). A useful side effect: massing-top falloff
for major columns is now handled by the same volumetric containment
mechanism as mullions, rather than a separate flat-height-cap special
case.

Two nested grids, same origin/angle:
  - MAJOR grid, 27ft spacing -- matching the site's own real column pitch
    (real_slabs_columns.json confirms actual surveyed columns sit on a
    true 27ft pitch). For THIS prototype the major positions are an
    idealized uniform grid over the test closed polysurface, per the
    user's explicit answer ("for the test it is just a 27x27 foot grid")
    -- but position sourcing goes through one function,
    major_column_points(), so swapping to real COLUMN_POSITIONS later
    (already loaded above as COLUMN_POSITIONS) is a one-function change.
  - MULLION grid, MullionSpacingFt (default 9.0) spacing -- the finer
    points nested inside each major bay, deduped against the major grid by
    local-coordinate coincidence (not O(n*m) distance scanning -- both
    grids share angle=0 and ORIGIN, so a point's local u/v modulo
    COL_SPACING tells us directly whether it coincides with a major point).

The actual scale fix (from this component's original design) is the UV
mapping: MullionUV normalizes each mullion point's position against the
FOOTPRINT's own bounding box (0-1), not whatever small domain (e.g. a
voxel module's own bounding box) an image-sampler script might otherwise
sample against. Wire MullionPoints/MullionUV into an Image Sampler once a
real plan drawing is available.

Component setup
----------------
Inputs (item access, Generic Data -- cast explicitly in code):
  Massing          : Brep -- optional, item access. The building massing
                     volume (a closed solid). If wired, its footprint is
                     extracted via a horizontal section-cut just above its
                     base (general-purpose -- works for sloped grade or
                     multi-face bases, not just a single flat bottom face)
                     and takes priority over Crv. Wire this SAME Brep into
                     both PM_GrowthAgents instances' own Massing input too
                     -- that's what makes both grids fall off flush at the
                     massing's top surface (hard clip, via containment).
  Crv              : Curve -- optional, item access. Used only if Massing
                     is not wired. If wired (this document's own
                     convention -- a single Curve param feeding the whole
                     pipeline), sample that curve directly. If neither is
                     wired, falls back to PM_PinGrid's layer-scan
                     convention (FOOTPRINT_LAYER) for the eventual
                     FidelityGrid1 port.
  Bake             : bool  -- Boolean Toggle. False = preview only. Bakes
                     raw points only (verification aid) -- this component
                     builds no grown/final geometry, so there is nothing
                     else to bake here; the actual visible structure comes
                     from PM_GrowthAgents' output downstream.
  MullionSpacingFt : float -- Number Slider, 2-27, default 9.0. Fine-grid
                     spacing nested inside each 27ft major bay. Does not
                     need to evenly divide 27 -- dedup against the major
                     grid is coincidence-based, not index arithmetic.

Outputs:
  MajorPoints  : Points (27ft-grid candidate points, footprint-filtered
                 -- NOT gated by any image value, not built into geometry
                 here; wire into a PM_GrowthAgents instance)
  MullionPoints: Points (9ft-nested candidate points, footprint-filtered,
                 major-grid-deduped -- same, wire into a second
                 PM_GrowthAgents instance)
  MullionUV    : Points packed as (u, v, 0) -- each mullion point's
                 position normalized 0-1 against its own footprint's
                 bounding box. Feed into an Image Sampler once a real plan
                 drawing is ready.
  Log          : str summary -- wire to a Panel.

Assumptions made explicit here because the prompt didn't pin them all down:
  - Footprint source, THIS PROTOTYPE ONLY: if neither Massing nor Crv is
    wired, every closed planar curve found on FOOTPRINT_LAYER ("Default")
    in the active document -- same convention as PM_PinGrid, same porting
    note applies (swap gather_footprints() for real Program::* footprints
    later).
  - This component only extracts the massing's FOOTPRINT (for point
    generation in plan) and never touches height/Z -- that's entirely
    PM_GrowthAgents' concern (containment against the massing's actual
    volume), keeping this component a pure "where do plan-level points
    go" concern.
  - MAJOR_POINTS_ALL are computed once, globally, from the site's own
    SITE_SIZE/ORIGIN (matching PM_PinGrid's col_lines convention), then
    filtered per footprint -- so multiple footprints sharing a site agree
    on the same major-grid phase.
  - No is_buried() culling yet (mirrors PM_PinGrid's same open caveat).
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

import Rhino
import Rhino.Geometry as rg

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
# real_geometry.json's column_positions are in a different local frame --
# translate into the same frame as ORIGIN/BOUNDARY_PTS above before use.
COLUMN_FRAME_TRANSLATE = (-13.028, -3.124)

COL_SPACING = 27.0
BOUNDARY_OFFSET = 9.0
SEED_TOL = 0.05

FOOTPRINT_LAYER = "Default"
TARGET_ROOT_LAYER = "Detailed_GrowthColumns"
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


# --------------------------------------------------------- point-grid helper
def build_point_grid(origin, spacing_u, spacing_v, angle_deg, boundary_pts, offset):
    """Unlike PM_PinGrid's build_grid_lines (which returns LINES, needed
    there to intersect two differently-angled grids), this returns POINTS
    directly -- simpler, since MAJOR and MULLION here share the same
    angle/origin and never need to be intersected against each other, only
    deduped."""
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

    n_lo, n_hi = int(math.ceil(min_u / spacing_u)), int(math.floor(max_u / spacing_u))
    m_lo, m_hi = int(math.ceil(min_v / spacing_v)), int(math.floor(max_v / spacing_v))

    points = []
    for n in range(n_lo, n_hi + 1):
        for m in range(m_lo, m_hi + 1):
            points.append(to_world(n * spacing_u, m * spacing_v))
    return points, to_local, to_world


MAJOR_POINTS_ALL, major_to_local, major_to_world = build_point_grid(
    ORIGIN, COL_SPACING, COL_SPACING, COL_ANGLE_DEG, BOUNDARY_PTS, BOUNDARY_OFFSET)


def is_on_major_grid(x, y):
    """True if (x,y) coincides with a major 27ft grid point -- checked via
    local-coordinate modulo, not O(n*m) distance scanning against
    MAJOR_POINTS_ALL, since both grids share angle=0 and ORIGIN."""
    lu, lv = major_to_local(x, y)
    tol_local = SEED_TOL
    ru = lu - COL_SPACING * round(lu / COL_SPACING)
    rv = lv - COL_SPACING * round(lv / COL_SPACING)
    return abs(ru) < tol_local and abs(rv) < tol_local


# ---------------------------------------------------------- footprint geometry
def coerce_curve(geo):
    if isinstance(geo, rg.Curve):
        return geo
    return None


def footprint_from_massing(massing):
    """General-purpose footprint extraction: slice the massing SOLID with a
    horizontal plane just above its own base (Intersection.BrepPlane),
    rather than assuming it has one single flat bottom face. Works
    identically to bottom-face extraction for a plain extruded box (this
    prototype's test massing), but also handles massings on sloped grade
    or assembled from several stacked/offset volumes, which real massing
    studies commonly are -- no special-casing needed later."""
    bbox = massing.GetBoundingBox(True)
    cut_z = bbox.Min.Z + 0.05
    plane = rg.Plane(rg.Point3d(0.0, 0.0, cut_z), rg.Vector3d.ZAxis)
    ok, curves, _pts = rg.Intersect.Intersection.BrepPlane(massing, plane, TOL)
    if not ok or not curves:
        return []
    return [crv for crv in curves if crv.IsClosed and crv.IsPlanar(TOL)]


def gather_footprints(crv_input=None, massing_input=None):
    """Priority: Massing (a 3D solid -- section-cut for its footprint,
    general-purpose so it also works for non-prismatic real massings) >
    Crv (this document's own convention -- a single Curve param feeding
    the whole pipeline) > PM_PinGrid's layer-scan convention (for the
    eventual FidelityGrid1 port, where footprints come from a document
    layer instead of a single wired parameter)."""
    if massing_input is not None:
        return footprint_from_massing(massing_input)
    if crv_input is not None:
        crv = coerce_curve(crv_input)
        if crv is not None and crv.IsClosed and crv.IsPlanar(TOL):
            return [crv]
        return []
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


def major_column_points(crv):
    """Literal 27ft-grid candidate positions inside crv. Idealized grid
    for this prototype (per user: 'for the test it is just a 27x27 foot
    grid'); swap the source list here for real COLUMN_POSITIONS (already
    loaded above) when porting to the real site model -- the filtering and
    everything downstream is unchanged."""
    return [(x, y) for (x, y) in MAJOR_POINTS_ALL if point_in_curve(crv, x, y)]


def mullion_points(crv, spacing_ft):
    """Fine-grid candidate points inside crv, nested within the major bays,
    deduped against major_column_points."""
    candidates, _, _ = build_point_grid(
        ORIGIN, spacing_ft, spacing_ft, COL_ANGLE_DEG, BOUNDARY_PTS, BOUNDARY_OFFSET)
    out = []
    for (x, y) in candidates:
        if not point_in_curve(crv, x, y):
            continue
        if is_on_major_grid(x, y):
            continue
        out.append((x, y))
    return out


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
    mullion_spacing = float(MullionSpacingFt) if MullionSpacingFt is not None else 9.0
    do_bake = bool(Bake) if Bake is not None else False

    footprints = gather_footprints(Crv, Massing)

    all_major_pts_geo, all_mullion_pts_geo, all_mullion_uv_geo = [], [], []
    major_pts_by_fp, mullion_pts_by_fp = [], []
    major_counts, mullion_counts = [], []

    for crv in footprints:
        bbox = crv.GetBoundingBox(True)
        bw = max(bbox.Max.X - bbox.Min.X, 1e-6)
        bh = max(bbox.Max.Y - bbox.Min.Y, 1e-6)

        m_pts = major_column_points(crv)
        major_counts.append(len(m_pts))
        fp_major_geo = [rg.Point3d(mx, my, 0.0) for (mx, my) in m_pts]
        major_pts_by_fp.append(fp_major_geo)
        all_major_pts_geo.extend(fp_major_geo)

        mu_pts = mullion_points(crv, mullion_spacing)
        mullion_counts.append(len(mu_pts))
        fp_mullion_geo = []
        for (px, py) in mu_pts:
            u = (px - bbox.Min.X) / bw
            v = (py - bbox.Min.Y) / bh
            pt = rg.Point3d(px, py, 0.0)
            uv = rg.Point3d(u, v, 0.0)
            fp_mullion_geo.append(pt)
            all_mullion_pts_geo.append(pt)
            all_mullion_uv_geo.append(uv)
        mullion_pts_by_fp.append(fp_mullion_geo)

    total_major = sum(major_counts)
    total_mullion = sum(mullion_counts)

    log_lines = [
        "site_data_source={}".format(SITE_DATA_SOURCE),
        "ORIGIN=({:.3f},{:.3f})".format(ORIGIN[0], ORIGIN[1]),
        "footprints={}".format(len(footprints)),
        "mullionSpacing={}".format(mullion_spacing),
        "majorPoints={}{}".format(
            total_major,
            "  (WARNING: zero major-grid points fall inside any footprint)"
            if total_major == 0 else ""),
        "mullionCandidates={}{}".format(
            total_mullion,
            "  (WARNING: zero mullion points -- footprint may be smaller than MullionSpacingFt,"
            " or entirely coincides with the major grid)"
            if total_mullion == 0 else ""),
        "NOTE: wire MajorPoints and MullionPoints into two separate PM_GrowthAgents"
        " instances (different RigidityBias/MaxGens/Speed) -- this component only"
        " generates points, it builds no geometry itself.",
    ]

    if do_bake:
        clear_previous_bake()
        for i, crv in enumerate(footprints):
            major_layer = "{}::Footprint{}::MajorPoints".format(TARGET_ROOT_LAYER, i)
            mullion_layer = "{}::Footprint{}::MullionPoints".format(TARGET_ROOT_LAYER, i)
            ensure_layer_path(major_layer)
            ensure_layer_path(mullion_layer)
            major_attr, mullion_attr = attrs_for(major_layer), attrs_for(mullion_layer)
            for pt in major_pts_by_fp[i]:
                rhino_doc.Objects.AddPoint(pt, major_attr)
            for pt in mullion_pts_by_fp[i]:
                rhino_doc.Objects.AddPoint(pt, mullion_attr)
        rhino_doc.Views.Redraw()
        log_lines.append("BAKED to {}::*  (raw points only, verification aid --"
                          " no grown geometry here)".format(TARGET_ROOT_LAYER))

    return all_major_pts_geo, all_mullion_pts_geo, all_mullion_uv_geo, "\n".join(log_lines)


if rhino_doc is None:
    MajorPoints, MullionPoints, MullionUV, Log = [], [], [], "ERROR: no active Rhino document"
else:
    MajorPoints, MullionPoints, MullionUV, Log = run()
    print(Log)
