"""
GhPython Script component: PM_PedestalUndercroft
--------------------------------------------------------------------
Paste into a "Python 3 Script" component (Maths > Script > Python 3 Script,
guid 719467e6-7cf5-4848-99b0-c5dd57e5442c) on the FidelityGrid1.gh canvas.
See PershingMetabolizer_Prototype/MASSING_FRAME.md for the full writeup.

Purpose: bring the physical pedestal already built and fabricated for this
project (photographed in modelGRIDinspo.png -- legs of real lumber hanging
below a site model, floating at heights driven by distance from a real
site datum, with a convex-hull "forced-touch" trick guaranteeing physical
stability) into the DIGITAL massing itself, per explicit user direction
("bring it into the digital massing" -- an undercroft/legs as part of the
building's own geometry, not just a fabrication detail).

Ported from Rhino/scripts/pedestal_leg_distribution.py's pure functions
(hull_2d, compute_forced_touch_set) -- same math, adapted to REAL FEET
(the source script's own __main__ works in inches, for the ~1:192
physical model; the pure math itself is unit-agnostic, so this component
just feeds it feet-scaled values) and driven by the site's own real
ORIGIN as the float-distance anchor (matching the real project's own
datum choice, not a new one).

Algorithm:
  1. Candidate leg positions = the massing footprint's real seeds (or
     L-system root positions) -- same candidate-gathering spirit as the
     source script's "55 posts + building-leg candidates" combined list,
     simplified here to just the seed positions since this component
     doesn't yet distinguish a separate "building leg" population.
  2. hull_2d() finds the 2D convex hull of those XY positions -- those
     legs are FORCED to touch a floor plane exactly (bottom_z = FloorZ).
     A volume-weighted center of mass is mathematically guaranteed to lie
     within the convex hull of the points it's averaged from, so forcing
     exactly the hull-perimeter legs to touch guarantees stability BY
     CONSTRUCTION, independent of how dramatic the interior float is --
     this is the source script's own key insight, reused verbatim rather
     than re-derived.
  3. Every INTERIOR leg (not on the hull) floats: bottom_z = FloorZ +
     MaxFloatFt * t, where t = normalized distance from ORIGIN (0 at
     ORIGIN, 1 at the farthest candidate) -- same distance-from-anchor
     principle as the source script's floating-leg rule.
  4. Each leg is a simple vertical box from its computed bottom_z up to
     the massing's own underside at that XY position (real ground/massing
     sampling, matching the source script's ground_z_at() ray-cast
     pattern, simplified here to a flat "massing bottom" since this
     prototype's test massing is a simple prismatic volume).

Component setup
----------------
Inputs:
  Seeds       : Point3d list, list access. Candidate leg XY positions --
                wire FG1's SeedPts (or PM_MassingFrame_Lsystem root
                positions once that's exposed separately).
  Massing     : Brep, item access, optional. Used to find each leg's top
                (the massing's own underside at that XY) and to filter
                seeds to those under the footprint.
  FloorZ      : float, item access, default 0.0. The floor plane forced-
                touch legs land on exactly.
  MaxFloatFt  : float, item access, default 6.0. Maximum float distance
                for interior (non-hull) legs -- real feet, not the source
                script's inches-scale physical-model value.
  LegWidthFt  : float, item access, default 0.75. Square leg cross-
                section (matches this project's other structural
                members).

Outputs:
  Legs : Breps (one vertical box per candidate position)
  Log  : str summary -- wire to a Panel.

Assumptions:
  - "Massing's underside at that XY" is approximated as the massing's own
    bounding-box Min.Z (flat), not a true per-point ray-cast against the
    actual solid -- correct for this prototype's simple prismatic test
    massing; a real ray-cast (Intersection.MeshRay / a Brep-ray
    equivalent) would be needed for a massing with a non-flat underside,
    mirroring the source script's own ground_z_at() pattern.
  - hull_2d() and compute_forced_touch_set() are near-verbatim ports of
    the source script's own functions (same monotone-chain algorithm),
    not reimplemented from scratch.
  - All dimensional constants are in FEET, matching every other script in
    this repo -- NOT the source script's inches (that was for the
    ~1:192 physical model; this is digital, full-scale).

When pasting into an actual Grasshopper Python 3 Script component, the
component requires '#! python 3' as the literal first line -- prepend it
(and drop this docstring, or keep it below the directive) since this file
leads with documentation instead for readability as a repo reference copy.
"""
import math

import Rhino
import Rhino.Geometry as rg

# Same real site datum used everywhere else in this pipeline (see FG1's
# docstring for the correction rationale).
ORIGIN = (319.89, 596.22)


def hull_2d(points):
    """Standard monotone-chain convex hull -- verbatim port of
    pedestal_leg_distribution.py's hull_2d(). points: iterable of
    (x, y) tuples."""
    pts = sorted(set(points))
    if len(pts) < 3:
        return pts

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower = []
    for p in pts:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    upper = []
    for p in reversed(pts):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    return lower[:-1] + upper[:-1]


def compute_forced_touch_set(all_candidate_xy):
    """Verbatim port -- returns the set of (x, y) positions on the 2D
    convex hull, forced to touch FloorZ exactly (stability guaranteed by
    construction, see module docstring)."""
    return set(hull_2d(all_candidate_xy))


def make_leg(px, py, bottom_z, top_z, width_ft):
    if top_z <= bottom_z:
        return None
    half = width_ft / 2.0
    plane = rg.Plane(rg.Point3d(px, py, 0.0), rg.Vector3d.XAxis, rg.Vector3d.YAxis)
    box = rg.Box(plane, rg.Interval(-half, half), rg.Interval(-half, half), rg.Interval(bottom_z, top_z))
    return box.ToBrep()


def run():
    seeds = list(Seeds) if Seeds else []
    floor_z = float(FloorZ) if FloorZ is not None else 0.0
    max_float = float(MaxFloatFt) if MaxFloatFt is not None else 6.0
    leg_width = float(LegWidthFt) if LegWidthFt is not None else 0.75

    if not seeds:
        return [], "WARNING: no Seeds wired -- nothing to build."

    top_z = floor_z + 0.1
    if Massing is not None:
        bbox = Massing.GetBoundingBox(True)
        top_z = bbox.Min.Z
        seeds = [p for p in seeds if Massing.IsPointInside(
            rg.Point3d(p.X, p.Y, top_z + 0.05), 0.01, False)]

    if not seeds:
        return [], "WARNING: zero seeds fall under the massing footprint -- nothing built."

    candidate_xy = [(p.X, p.Y) for p in seeds]
    forced_set = compute_forced_touch_set(candidate_xy)

    max_dist = max(math.hypot(x - ORIGIN[0], y - ORIGIN[1]) for (x, y) in candidate_xy)
    max_dist = max(max_dist, 1e-6)

    legs = []
    forced_count = 0
    for (x, y) in candidate_xy:
        forced = (x, y) in forced_set
        if forced:
            forced_count += 1
            bottom_z = floor_z
        else:
            t = math.hypot(x - ORIGIN[0], y - ORIGIN[1]) / max_dist
            bottom_z = floor_z + max_float * t
            if bottom_z >= top_z:
                bottom_z = top_z - 0.1
        leg = make_leg(x, y, bottom_z, top_z, leg_width)
        if leg is not None:
            legs.append(leg)

    log_lines = [
        "candidateLegs={} forcedTouchHullLegs={}".format(len(candidate_xy), forced_count),
        "floorZ={} maxFloatFt={} legWidthFt={} topZ={:.3f}".format(floor_z, max_float, leg_width, top_z),
        "legsBuilt={}".format(len(legs)),
    ]

    return legs, "\n".join(log_lines)


Legs, Log = run()
print(Log)
