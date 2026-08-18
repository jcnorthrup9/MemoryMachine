"""
GhPython Script component: PM_MassingFrame_Lsystem
--------------------------------------------------------------------
Paste into a "Python 3 Script" component (Maths > Script > Python 3 Script,
guid 719467e6-7cf5-4848-99b0-c5dd57e5442c) on the FidelityGrid1.gh canvas,
downstream of PM_FacadePanelizer's SeedPts and PM_HeightField. See
PershingMetabolizer_Prototype/MASSING_FRAME.md for the full writeup.

Purpose: the massing form language the user wants (per "shared image (1)
.png", captioned "Media as spatial organization" -- their instructor's
reference) is a dense, strictly orthogonal, INTERLOCKING frame of members
at clearly varying length, crossing at multiple heights -- not the sparse
independent vertical sticks PM_GrowthAgents' cohesion/gravity simulation
produced, and explicitly NOT a Voronoi/cellular pattern ("that's a pretty
basic and overused pattern" -- also the wrong topology, Voronoi cells read
organic, not orthogonal-interlocking).

Algorithm: an orthogonal L-system (Lindenmayer system) -- recursive,
axis-constrained branching from real seed points, branch length driven by
PM_HeightField's real height-field falloff. Chosen over Voronoi/DLA per
explicit user selection: a real generative-design lineage, naturally
produces varying member lengths crossing at multiple heights, and is a
genuine 3D extension of FG1's own already-validated recursive marked-cell
subdivision ("Behavior B") -- not a bolt-on unrelated pattern.

Each real seed (FG1's SeedPts, filtered to fall inside the massing
footprint) becomes a branching root. At each node, up to 5 of the 6 signed
orthogonal directions (excluding only the reverse of the one just arrived
from) independently roll against BranchProb to spawn child branches --
deterministic, keyed by node position + depth (a simple
integer-hash PRNG, same reproducibility principle as the OneDrive
project's mulberry32-keyed jitter: no unseeded Random(), so the SAME seed
positions always produce the SAME frame). Each branch's length comes from
PM_HeightField.height_field() at its start point, scaled down by recursion
depth (branches shorten as they go, giving the varying-length read).
Recursion stops at MaxDepth or when a branch would exit the massing's
actual volume (reusing PM_GrowthAgents' own IsPointInside containment
pattern).

Component setup
----------------
Inputs:
  Seeds        : Point3d list, list access. Wire FG1's SeedPts -- used
                 both as branching roots AND as the height-field's own
                 seed set (height_field() is called directly here, inline
                 -- see below -- rather than through a separate
                 PM_HeightField component pass, since branch start points
                 are generated live during recursion and can't be
                 pre-computed ahead of time).
  Massing      : Brep, item access, optional. Containment volume -- same
                 Brep wired everywhere else in this pipeline.
  HeightSeeds  : Point3d list, list access, optional. Only wire this if
                 the height field should use a DIFFERENT seed set than
                 the branching roots (uncommon) -- defaults to Seeds when
                 left unwired.
  MinHeightFt  : float, item access, default 9.0.
  MaxHeightFt  : float, item access, default 24.0.
  RadiusFt     : float, item access, default 54.0.
  MaxDepth     : int, item access, default 4. Recursion depth limit.
  BranchProb   : float, item access, 0.0-1.0, default 0.6. Probability
                 each of the (up to 5) candidate directions actually
                 spawns a branch (not all 5 every time -- keeps the frame
                 from being a uniform lattice).
  MemberFt     : float, item access, default 0.75. Member cross-section
                 (matches this project's other structural members).

Outputs:
  Members  : Breps (straight box per branch segment)
  Log      : str summary -- wire to a Panel.

Assumptions:
  - Deterministic PRNG: a simple integer hash of (round(x*1000),
    round(y*1000), round(z*1000), depth, direction_index) mapped to
    [0,1) -- not cryptographically random, but reproducible and
    dependency-free (no extra imports needed).
  - Direction exclusion: at the root (no arrival direction), all 6 signed
    axis directions are candidates; after that, only the reverse of the
    arrival direction is excluded (no immediate backtrack -- continuing
    straight is a valid, even desirable, candidate), leaving 5 candidates.
    Each of those 5 independently rolls against BranchProb, so a node
    typically spawns somewhere between 0 and 5 children, not a hard cap.
  - Brep.IsPointInside() containment mirrors PM_GrowthAgents'
    prepare_massing() pattern exactly (closed-solid check, CapPlanarHoles
    fallback, flat Z-cap if still open) -- see that component's docstring
    for the full rationale.
  - All dimensional constants are in FEET, matching every other script in
    this repo.

When pasting into an actual Grasshopper Python 3 Script component, the
component requires '#! python 3' as the literal first line -- prepend it
(and drop this docstring, or keep it below the directive) since this file
leads with documentation instead for readability as a repo reference copy.
"""
import math

import Rhino
import Rhino.Geometry as rg

rhino_doc = Rhino.RhinoDoc.ActiveDoc
TOL = rhino_doc.ModelAbsoluteTolerance if rhino_doc else 0.01

DIRECTIONS = [
    (1, 0, 0), (-1, 0, 0),
    (0, 1, 0), (0, -1, 0),
    (0, 0, 1), (0, 0, -1),
]


def _hash01(*vals):
    """Deterministic pseudo-random float in [0,1) from integer inputs --
    no Random() state, so identical inputs always produce identical
    output (reproducibility, same principle as the OneDrive project's
    mulberry32-keyed jitter)."""
    h = 2166136261
    for v in vals:
        h = (h ^ (v & 0xFFFFFFFF)) * 16777619
        h &= 0xFFFFFFFF
    return (h % 1000000) / 1000000.0


def smoothstep(t):
    t = max(0.0, min(1.0, t))
    return t * t * (3.0 - 2.0 * t)


def height_field(x, y, seeds_xy, min_h, max_h, radius):
    if not seeds_xy:
        return min_h
    d_min = min(math.hypot(x - sx, y - sy) for (sx, sy) in seeds_xy)
    t = smoothstep(d_min / radius)
    return min_h + (max_h - min_h) * t


def prepare_massing(massing):
    """Verbatim pattern from PM_GrowthAgents -- see that component's
    docstring for the full rationale."""
    if massing is None:
        return None, None
    bbox = massing.GetBoundingBox(True)
    z_cap = bbox.Max.Z
    if massing.IsSolid and massing.IsValid:
        return massing, z_cap
    capped = massing.CapPlanarHoles(TOL)
    if capped and massing.IsSolid and massing.IsValid:
        return massing, z_cap
    return None, z_cap


def make_member(p0, p1, member_ft):
    dx, dy, dz = p1.X - p0.X, p1.Y - p0.Y, p1.Z - p0.Z
    length = math.sqrt(dx * dx + dy * dy + dz * dz)
    if length < 1e-6:
        return None
    dir_vec = rg.Vector3d(dx / length, dy / length, dz / length)
    # Pick a normal not parallel to dir_vec for a stable plane.
    ref = rg.Vector3d.ZAxis if abs(dir_vec.Z) < 0.9 else rg.Vector3d.XAxis
    normal_vec = rg.Vector3d.CrossProduct(dir_vec, ref)
    normal_vec.Unitize()
    plane = rg.Plane(p0, dir_vec, normal_vec)
    half = member_ft / 2.0
    box = rg.Box(plane, rg.Interval(0, length), rg.Interval(-half, half), rg.Interval(-half, half))
    return box.ToBrep()


def branch(pos, arrived_dir_idx, depth, max_depth, branch_prob, seeds_xy,
           min_h, max_h, radius, massing, z_cap, member_ft, out_members, stats):
    if depth >= max_depth:
        return
    candidates = [i for i in range(6) if arrived_dir_idx is None or DIRECTIONS[i] != tuple(
        -d for d in DIRECTIONS[arrived_dir_idx])]
    for di in candidates:
        roll = _hash01(int(round(pos.X * 1000)), int(round(pos.Y * 1000)),
                        int(round(pos.Z * 1000)), depth, di)
        if roll > branch_prob:
            continue
        h = height_field(pos.X, pos.Y, seeds_xy, min_h, max_h, radius)
        length = max(1.0, h * (1.0 - depth / float(max_depth + 1)))
        dx, dy, dz = DIRECTIONS[di]
        new_pos = rg.Point3d(pos.X + dx * length, pos.Y + dy * length, pos.Z + dz * length)

        if massing is not None:
            if not massing.IsPointInside(new_pos, TOL, False):
                continue
        elif z_cap is not None and new_pos.Z > z_cap:
            continue
        if new_pos.Z < -1e-6:
            continue

        member = make_member(pos, new_pos, member_ft)
        if member is not None:
            out_members.append(member)
            stats["members"] += 1
        stats["maxDepthReached"] = max(stats["maxDepthReached"], depth + 1)
        branch(new_pos, di, depth + 1, max_depth, branch_prob, seeds_xy,
               min_h, max_h, radius, massing, z_cap, member_ft, out_members, stats)


def run():
    seeds = list(Seeds) if Seeds else []
    height_seeds = list(HeightSeeds) if HeightSeeds else seeds
    max_depth = max(1, int(MaxDepth)) if MaxDepth is not None else 4
    branch_prob = min(1.0, max(0.0, float(BranchProb))) if BranchProb is not None else 0.6
    min_h = float(MinHeightFt) if MinHeightFt is not None else 9.0
    max_h = float(MaxHeightFt) if MaxHeightFt is not None else 24.0
    radius = float(RadiusFt) if RadiusFt is not None else 54.0
    member_ft = float(MemberFt) if MemberFt is not None else 0.75

    if not seeds:
        return [], "WARNING: no Seeds wired -- nothing to branch from."

    massing, z_cap = prepare_massing(Massing)

    roots = seeds
    if massing is not None:
        roots = [p for p in seeds if massing.IsPointInside(
            rg.Point3d(p.X, p.Y, (massing.GetBoundingBox(True).Min.Z + 0.05)), TOL, False)]

    seeds_xy = [(p.X, p.Y) for p in height_seeds]

    out_members = []
    stats = {"members": 0, "maxDepthReached": 0}
    for root in roots:
        branch(root, None, 0, max_depth, branch_prob, seeds_xy,
               min_h, max_h, radius, massing, z_cap, member_ft, out_members, stats)

    log_lines = [
        "seeds={} rootsInMassing={}".format(len(seeds), len(roots)),
        "maxDepth={} branchProb={} memberFt={}".format(max_depth, branch_prob, member_ft),
        "minHeightFt={} maxHeightFt={} radiusFt={}".format(min_h, max_h, radius),
        "members={} maxDepthReached={}".format(stats["members"], stats["maxDepthReached"]),
    ]
    if not roots:
        log_lines.append("WARNING: zero seeds fall inside the massing footprint -- nothing grown.")

    return out_members, "\n".join(log_lines)


Members, Log = run()
print(Log)
