"""
GhPython Script component: PM_GrowthScaffold
--------------------------------------------------------------------
Paste into a "Python 3 Script" component (Maths > Script > Python 3 Script,
guid 719467e6-7cf5-4848-99b0-c5dd57e5442c) on the same Grasshopper canvas as
FidelityGrid1's PM_FacadePanelizer. See PershingMetabolizer_Prototype/
GROWTH_SCAFFOLD.md for the full writeup.

Purpose: an agent-based, grid-snapped, attractor-seeking growth system
ported from an external Processing/three.js sketch (`app_tk4.js`'s
Agent.update(), documented in this repo's
HANDOFF_08012026_PROCESSING_GROWTH_ALGO_FOR_MASSING.md) -- NOT a facade
panelizer. Agents spawn at every point where a building's plan footprint
edge crosses the site's real 27ft column grid, and grow toward a pooled,
site-wide set of the SAME points (lofted to two roof-height tiers), taking
fixed-length orthogonal steps and dodging around each other via a shared
occupied-voxel set. The result is a dense interlocking lattice of uniform
box "sticks" -- like architectural scaffolding -- that bridges BETWEEN
separate building masses rather than staying confined to one facade. This
supersedes FidelityGrid2 (PM_FacadeScreen, now disabled/preserved) as this
project's second compounding-grid layer.

Component setup
----------------
Inputs (item access, Generic Data -- cast explicitly in code):
  Bake               : bool  -- Boolean Toggle. False = preview only.
  Refresh            : bool  -- unused (fully deterministic, no RNG);
                        wired for future use.
  TLengthFt          : float -- Slider, 0.75-6.0, default 1.5. Fixed
                        step length AND voxel size -- this is the "small
                        patterning grid" scaled down from the 27ft "large
                        organizer" grid. 1.5ft divides evenly into both
                        27ft (18 steps/bay) and the 30/15ft attractor
                        height tiers (20/10 steps), so agents can arrive
                        exactly on a voxel plane instead of asymptotically.
  StickSizeFt        : float -- Slider, 0.25-3.0, default 0.5. FIXED
                        constant cross-section for every member (the
                        user's explicit decision -- this algorithm's
                        origin was fabricating real lumber at uniform
                        stock size, and it produces that by construction:
                        every step is the same length AND thickness).
  Dna0               : float -- Slider, 1.0-4.0, default 2.0. Attractor-
                        affinity multiplier. NOTE: with only one steering
                        term (no swarm-cohesion counter-force, unlike the
                        Processing original), this value is mathematically
                        inert -- force_ortho() discards magnitude and
                        keeps only sign. Kept for parity / future use if a
                        second steering term is ever added.
  MaxLifespan        : int   -- Slider, 10-500, default 120. Per-agent
                        step/age cap. The source's default (28) was tuned
                        for tLength=48 in pixel space and does not port --
                        at this project's scale, one vertical climb (~20
                        steps) plus one bay of horizontal reach (~18
                        steps) alone is ~38 steps; 120 gives real margin.
                        The Log prints the minimum this should be for the
                        current TLengthFt/AttractorZFt -- raise it if the
                        printed requirement exceeds this slider's value.
  MaxAttractorDistFt : float -- Slider, 27-600, default 135 (5 bays). An
                        agent with no attractor in range dies immediately
                        (cause="no_target") rather than falling back to
                        some default target -- there is no image "ceiling"
                        concept to fall back to here.
  AttractorZFt       : float -- Slider, 0-60, default 30.0. Upper
                        attractor height tier, matches real_geometry.json's
                        column_height_ft.
  AttractorZSplit    : float -- Slider, 0-1, default 0.5. Lower tier =
                        AttractorZFt * AttractorZSplit (15ft at default).
                        Tier assignment is deterministic (checkerboard by
                        bay index, no RNG) so the scaffold's canopy height
                        varies like the reference image instead of
                        terminating on one flat plane. 1.0 collapses to a
                        single height.
  MaxAgents          : int   -- Slider, 0-400, default 0. 0 = spawn one
                        agent per unique footprint-edge/grid intersection
                        (all of them); >0 caps to the first N spawn points
                        in a fixed, deterministic order (no random sample).
  SnapGridPhase      : bool  -- Boolean Toggle, default True. See
                        "Assumptions" below -- ORIGIN and the building
                        massing module are NOT in phase; this corrects it.

Outputs:
  Members     : Breps (the grown stick/box segments)
  PathCrv     : Curves (one polyline per agent's committed history, for
                inspecting individual growth paths)
  AttractorPts: Points (the pooled, height-lofted target set)
  SpawnPts    : Points (the grade-level footprint/grid intersections)
  DeadEndPts  : Points (where an agent terminated with cause="cornered" --
                these are EXPECTED, not a bug; they're the cantilevered
                tips visible in the reference image)
  Log         : str summary -- wire to a Panel.

Assumptions made explicit here because the prompt didn't pin them down:
  - GRID PHASE MISMATCH, discovered and corrected this session: the site's
    real column-survey ORIGIN=(337.028, 570.21) is NOT in phase with the
    building massing module -- 337.028 mod 27 = 13.028, 570.21 mod 27 =
    3.21. FidelityGrid1's col_lines (anchored at raw ORIGIN) do NOT pass
    through any building footprint corner, even though every footprint IS
    bay-snapped to exact multiples of 27 from world (0,0). For THIS
    component only (not FG1, which has no reason to change), when
    SnapGridPhase is True the grid is rebuilt from a phase-corrected
    anchor: GROWTH_ORIGIN = (round(ORIGIN.X/27)*27, round(ORIGIN.Y/27)*27)
    = (324.0, 567.0) -- independently confirmed correct, since that exact
    point is CommunityCenter's own far corner. SnapGridPhase=False uses
    raw ORIGIN instead, for comparison (expect ~zero footprint-corner
    hits in that mode).
  - Attractors are seeded ABOVE grade only; spawns are AT grade only. If
    both existed at the same (x,y), the Z=0 copy would always be nearer
    and nothing would ever climb -- so the two sets are deliberately
    disjoint in Z, and an agent's own directly-overhead attractor is
    excluded from its target search (else every agent just grows a
    trivial straight column and nothing bridges between buildings).
  - Buildings here are simple axis-aligned boxes in plan (confirmed via
    bbox inspection), so a "footprint edge" is just one of a building's 4
    bounding-box rectangle edges -- no face-extraction needed.
  - Attractors/spawns are POOLED from ALL buildings into one site-wide
    list (the user's explicit choice) -- an agent spawned at one
    building's footprint can and should be able to target a point on a
    DIFFERENT building, which is what produces cross-building bridging
    rather than 8 independent per-building clusters.
  - The driver runs agents ROUND-ROBIN (one step each per tick, repeated),
    matching the source's per-frame loop -- not agent-by-agent to
    completion, which would let early agents claim voxels before later
    ones even start and bias the lattice.
  - in_bounds() re-checks the SITE boundary (expanded by BOUNDARY_OFFSET)
    and a Z ceiling (1.5x AttractorZFt) on every candidate step -- without
    this, ungrounded agents can wander off-site indefinitely before aging
    out.
  - Materials: same two-step workflow as FidelityGrid1/2 -- materials set
    from inside this component do not visibly render in Rhino's Rendered
    display mode. Bake here, then run the (extended)
    rhino/apply_facade_materials.py via rhino/run_rhino_script.py (the
    win32com COM bridge) to make PM_Scaffold_Timber actually visible.
  - This document's Materials table has 13,000+ pre-existing entries;
    find_or_make_material() below updates a same-named entry IN PLACE via
    Materials.Modify() rather than deleting and recreating it --
    Materials.Delete() on an in-use entry was observed to fail/halt
    script execution earlier this session.
  - All dimensional constants are in FEET.

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

SCAFFOLD_MATERIAL_NAME = "PM_Scaffold_Timber"
SCAFFOLD_MATERIAL_HEX = "#B07C4A"

# ---------------------------------------------------------------- constants
CANDIDATE_JSON_PATHS = [
    os.path.join(os.getcwd(), "PershingMetabolizer_Prototype", "real_geometry.json"),
    r"C:\Users\jcnor\MemoryMachine\PershingMetabolizer_Prototype\real_geometry.json",
]
FALLBACK_SITE_SIZE = (354.22, 602.53)
FALLBACK_ORIGIN = (337.028, 570.21)

COL_SPACING = 27.0
BOUNDARY_OFFSET = 9.0
SEED_TOL = 0.05

TARGET_ROOT_LAYER = "Detailed_Scaffold"
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


# --------------------------------------- portable grid algorithm (spec 1-4)
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


def coerce_brep(geo):
    if isinstance(geo, rg.Brep):
        return geo
    if isinstance(geo, rg.Extrusion):
        return geo.ToBrep()
    return rg.Brep.TryConvertBrep(geo)


# ------------------------------------------------------- attractor/spawn build
def footprint_edges(brep):
    """Buildings here are simple axis-aligned boxes in plan -- a footprint
    edge is just one of the bbox rectangle's 4 sides, CCW."""
    bbox = brep.GetBoundingBox(True)
    x0, x1 = bbox.Min.X, bbox.Max.X
    y0, y1 = bbox.Min.Y, bbox.Max.Y
    corners = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
    return [(corners[i], corners[(i + 1) % 4]) for i in range(4)]


def build_attractors(col_lines, bldg_breps, attr_z, z_split, col_spacing):
    raw_pts = []
    for name, breps in bldg_breps.items():
        for brep in breps:
            for (p1, p2) in footprint_edges(brep):
                for (c_p1, c_p2, _ax, _ix) in col_lines:
                    ipt = segment_intersection(p1, p2, (c_p1[0], c_p1[1]), (c_p2[0], c_p2[1]))
                    if ipt is not None:
                        raw_pts.append(ipt)

    unique_pts = []
    for p in raw_pts:
        if not any(math.hypot(p[0] - q[0], p[1] - q[1]) < SEED_TOL for q in unique_pts):
            unique_pts.append(p)

    spawn_pts = [rg.Point3d(x, y, 0.0) for (x, y) in unique_pts]
    attractors = []
    for (x, y) in unique_pts:
        nu = int(round(x / col_spacing))
        nv = int(round(y / col_spacing))
        z = attr_z if ((nu + nv) % 2 == 0) else attr_z * z_split
        attractors.append(rg.Point3d(x, y, z))
    return spawn_pts, attractors, len(raw_pts)


# --------------------------------------------------------- growth algorithm
def sign(v):
    return 1.0 if v >= 0 else -1.0


def force_ortho(v):
    """The core 'grid logic': zero every axis but the largest-magnitude
    one, then normalize -- always a unit vector along +/-X, +/-Y, +/-Z."""
    ax, ay, az = abs(v.X), abs(v.Y), abs(v.Z)
    if ax >= ay and ax >= az:
        return rg.Vector3d(sign(v.X), 0.0, 0.0)
    elif ay >= az:
        return rg.Vector3d(0.0, sign(v.Y), 0.0)
    else:
        return rg.Vector3d(0.0, 0.0, sign(v.Z))


def gkey(pt, t):
    return (int(round(pt.X / t)), int(round(pt.Y / t)), int(round(pt.Z / t)))


def in_bounds(pt, z_ceiling):
    if pt.Z < -1e-6 or pt.Z > z_ceiling:
        return False
    xs = [p[0] for p in BOUNDARY_PTS]
    ys = [p[1] for p in BOUNDARY_PTS]
    return (min(xs) - BOUNDARY_OFFSET <= pt.X <= max(xs) + BOUNDARY_OFFSET and
            min(ys) - BOUNDARY_OFFSET <= pt.Y <= max(ys) + BOUNDARY_OFFSET)


def step_agent(a, attractors, occupied, t, dna0, max_dist, max_life, z_ceiling):
    if a["target"] is None:
        best, best_d = None, None
        for att in attractors:
            dp = math.hypot(att.X - a["spawn"][0], att.Y - a["spawn"][1])
            if dp < SEED_TOL:
                continue  # exclude the attractor directly above this agent's own spawn
            d = a["pos"].DistanceTo(att)
            if d <= max_dist and (best_d is None or d < best_d):
                best, best_d = att, d
        if best is None:
            a["dead"], a["cause"] = True, "no_target"
            return
        a["target"] = best

    a["age"] += 1
    if a["age"] > max_life:
        a["dead"], a["cause"] = True, "aged"
        return

    acc = a["target"] - a["pos"]
    acc.Unitize()
    acc *= dna0
    d0 = force_ortho(acc)

    if abs(d0.X) > 1e-6:
        dodge = rg.Vector3d(0.0, 0.0, sign(acc.X))
    elif abs(d0.Z) > 1e-6:
        dodge = rg.Vector3d(sign(acc.X), 0.0, 0.0)
    else:
        dodge = rg.Vector3d(sign(acc.X), 0.0, 0.0)
    vertical = rg.Vector3d(0.0, 0.0, 1.0)

    for cand in (d0, dodge, vertical):
        nxt = a["pos"] + cand * t
        if in_bounds(nxt, z_ceiling) and gkey(nxt, t) not in occupied:
            a["segments"].append((a["pos"], nxt, cand))
            occupied.add(gkey(nxt, t))
            a["pos"] = nxt
            a["hist"].append(nxt)
            if a["pos"].DistanceTo(a["target"]) <= t:
                a["dead"], a["cause"] = True, "arrived"
            return

    a["dead"], a["cause"] = True, "cornered"


def make_stick(p0, p1, axis_vec, size):
    h = size / 2.0
    perp = rg.Vector3d.XAxis if abs(axis_vec.Z) > 0.5 else rg.Vector3d.ZAxis
    length = p0.DistanceTo(p1)
    plane = rg.Plane(p0, axis_vec, perp)
    box = rg.Box(plane, rg.Interval(0, length), rg.Interval(-h, h), rg.Interval(-h, h))
    return box.ToBrep()


def axis_label(v):
    if abs(v.X) > 0.5:
        return "X"
    if abs(v.Y) > 0.5:
        return "Y"
    return "Z"


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
    pbr = mat.PhysicallyBased
    if pbr is None:
        mat.ToPhysicallyBased()
        pbr = mat.PhysicallyBased
    if pbr is not None:
        pbr.BaseColor = Rhino.Display.Color4f(color)
        pbr.Metallic = metallic
        pbr.Roughness = roughness
        pbr.Opacity = max(0.0, 1.0 - transparency)

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
    t_len = float(TLengthFt) if TLengthFt is not None else 1.5
    stick_size = float(StickSizeFt) if StickSizeFt is not None else 0.5
    dna0 = float(Dna0) if Dna0 is not None else 2.0
    max_life = int(round(float(MaxLifespan))) if MaxLifespan is not None else 120
    max_dist = float(MaxAttractorDistFt) if MaxAttractorDistFt is not None else 135.0
    attr_z = float(AttractorZFt) if AttractorZFt is not None else 30.0
    z_split = float(AttractorZSplit) if AttractorZSplit is not None else 0.5
    max_agents = int(round(float(MaxAgents))) if MaxAgents is not None else 0
    snap_phase = bool(SnapGridPhase) if SnapGridPhase is not None else True
    do_bake = bool(Bake) if Bake is not None else False
    z_ceiling = attr_z * 1.5

    if snap_phase:
        grid_origin = (round(ORIGIN[0] / COL_SPACING) * COL_SPACING,
                       round(ORIGIN[1] / COL_SPACING) * COL_SPACING)
        phase_label = "SNAPPED"
    else:
        grid_origin = ORIGIN
        phase_label = "RAW"

    col_lines, _to_local, _to_world, _range = build_grid_lines(
        grid_origin, COL_SPACING, COL_SPACING, 0.0, BOUNDARY_PTS, BOUNDARY_OFFSET)

    bldg_breps = {}
    for name in PROGRAM_LAYERS:
        idx = rhino_doc.Layers.FindByFullPath("Program::" + name, -1)
        if idx < 0:
            continue
        breps = []
        for rh_obj in rhino_doc.Objects.FindByLayer(rhino_doc.Layers[idx]):
            b = coerce_brep(rh_obj.Geometry)
            if b is not None:
                breps.append(b)
        bldg_breps[name] = breps

    spawn_pts, attractors, raw_hits = build_attractors(col_lines, bldg_breps, attr_z, z_split, COL_SPACING)

    spawn_subset = spawn_pts if max_agents <= 0 else spawn_pts[:max_agents]
    agents = [{
        "pos": p, "target": None, "spawn": (p.X, p.Y), "age": 0,
        "hist": [p], "dead": False, "cause": "", "segments": [],
    } for p in spawn_subset]

    occupied = set()
    for a in agents:
        occupied.add(gkey(a["pos"], t_len))

    steps_run = 0
    for _ in range(max_life + 1):
        live = [a for a in agents if not a["dead"]]
        if not live:
            break
        for a in live:
            step_agent(a, attractors, occupied, t_len, dna0, max_dist, max_life, z_ceiling)
        steps_run += 1

    members, path_crv, dead_end_pts = [], [], []
    causes = {"arrived": 0, "cornered": 0, "aged": 0, "no_target": 0}
    axis_counts = {"X": 0, "Y": 0, "Z": 0}
    for a in agents:
        causes[a["cause"]] = causes.get(a["cause"], 0) + 1
        if a["cause"] == "cornered":
            dead_end_pts.append(a["pos"])
        if len(a["hist"]) >= 2:
            path_crv.append(rg.PolylineCurve(a["hist"]))
        for (p0, p1, axis_vec) in a["segments"]:
            members.append(make_stick(p0, p1, axis_vec, stick_size))
            axis_counts[axis_label(axis_vec)] += 1

    log_lines = [
        "site_data_source={}".format(SITE_DATA_SOURCE),
        "grid_phase={} origin=({:.3f},{:.3f})  [raw ORIGIN=({:.3f},{:.3f})]".format(
            phase_label, grid_origin[0], grid_origin[1], ORIGIN[0], ORIGIN[1]),
        "col_lines={}  breps={}  raw_edge_hits={}  attractors={}  spawns={}".format(
            len(col_lines), sum(len(v) for v in bldg_breps.values()), raw_hits, len(attractors), len(spawn_pts)),
        "tLength={:.2f}ft stick={:.2f}ft  attr_z={:.1f}/{:.1f}  maxLife={} (need>={})  maxAttrDist={:.0f}ft".format(
            t_len, stick_size, attr_z, attr_z * z_split, max_life,
            int(math.ceil(1.3 * (max_dist + attr_z) / t_len)), max_dist),
        "agents={}  steps_run={}".format(len(agents), steps_run),
        "terminations: arrived={} cornered={} aged={} no_target={}".format(
            causes.get("arrived", 0), causes.get("cornered", 0), causes.get("aged", 0), causes.get("no_target", 0)),
        "segments={}  axis X={} Y={} Z={}  occupied_voxels={}".format(
            len(members), axis_counts["X"], axis_counts["Y"], axis_counts["Z"], len(occupied)),
    ]

    if do_bake:
        clear_previous_bake()
        scaffold_idx = find_or_make_material(SCAFFOLD_MATERIAL_NAME, SCAFFOLD_MATERIAL_HEX,
                                              metallic=0.0, roughness=0.75, transparency=0.0)

        for ax in ("X", "Y", "Z"):
            ensure_layer_path("{}::Members::{}".format(TARGET_ROOT_LAYER, ax))
            idx = rhino_doc.Layers.FindByFullPath("{}::Members::{}".format(TARGET_ROOT_LAYER, ax), -1)
            rhino_doc.Layers[idx].RenderMaterialIndex = scaffold_idx

        member_attrs = {ax: attrs_for("{}::Members::{}".format(TARGET_ROOT_LAYER, ax)) for ax in ("X", "Y", "Z")}
        for a in agents:
            for (p0, p1, axis_vec) in a["segments"]:
                brep = make_stick(p0, p1, axis_vec, stick_size)
                rhino_doc.Objects.AddBrep(brep, member_attrs[axis_label(axis_vec)])

        ensure_layer_path(TARGET_ROOT_LAYER + "::_Parti::Attractors")
        ensure_layer_path(TARGET_ROOT_LAYER + "::_Parti::Spawns")
        ensure_layer_path(TARGET_ROOT_LAYER + "::_Parti::DeadEnds")
        ensure_layer_path(TARGET_ROOT_LAYER + "::_Parti::Paths")
        attr_attr = attrs_for(TARGET_ROOT_LAYER + "::_Parti::Attractors")
        for pt in attractors:
            rhino_doc.Objects.AddPoint(pt, attr_attr)
        spawn_attr = attrs_for(TARGET_ROOT_LAYER + "::_Parti::Spawns")
        for pt in spawn_pts:
            rhino_doc.Objects.AddPoint(pt, spawn_attr)
        dead_attr = attrs_for(TARGET_ROOT_LAYER + "::_Parti::DeadEnds")
        for pt in dead_end_pts:
            rhino_doc.Objects.AddPoint(pt, dead_attr)
        path_attr = attrs_for(TARGET_ROOT_LAYER + "::_Parti::Paths")
        for crv in path_crv:
            rhino_doc.Objects.AddCurve(crv, path_attr)

        rhino_doc.Views.Redraw()
        log_lines.append("BAKED to {}::*".format(TARGET_ROOT_LAYER))

    return members, path_crv, attractors, spawn_pts, dead_end_pts, "\n".join(log_lines)


if rhino_doc is None:
    Members, PathCrv, AttractorPts, SpawnPts, DeadEndPts, Log = [], [], [], [], [], "ERROR: no active Rhino document"
else:
    Members, PathCrv, AttractorPts, SpawnPts, DeadEndPts, Log = run()
    print(Log)
