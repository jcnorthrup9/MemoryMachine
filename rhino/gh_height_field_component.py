"""
GhPython Script component: PM_HeightField
--------------------------------------------------------------------
Paste into a "Python 3 Script" component (Maths > Script > Python 3 Script,
guid 719467e6-7cf5-4848-99b0-c5dd57e5442c) on the FidelityGrid1.gh canvas,
downstream of PM_FacadePanelizer (rhino/gh_facade_panelizer_component.py).
See PershingMetabolizer_Prototype/MASSING_FRAME.md for the full writeup.

Near-verbatim port of Rhino/scripts/canopy_height_field.py's pure
height_field()/smoothstep() functions (OneDrive SCI-Arc Thesis project) --
same math, same real MIN_H/MAX_H/RADIUS defaults, exposed here as a
reusable Grasshopper component instead of a one-off __main__ script.

Purpose: a smooth falloff from the real column x DTLA-grid collision seeds
(FG1's own SeedPts output) -- low near a seed (walkable clearance), opening
up to a maximum height/reach by RADIUS away. Originally built for the
canopy diagram layer; reused here (per explicit user direction, "extend
the existing seed/marked-cell logic into 3D") to drive branch length in
PM_MassingFrame_Lsystem, so the massing's member-length variation traces
back to the same real site datum as everything else in this project,
rather than an arbitrary/random length choice.

Component setup
----------------
Inputs:
  QueryPoints : Point3d list, list access. Positions to sample the field
                at (e.g. an L-system branch's start point).
  Seeds       : Point3d list, list access. Wire FG1's SeedPts output
                directly -- the real 55 column x DTLA-grid collision
                points.
  MinHeightFt : float, item access, default 9.0 (real value from
                canopy_height_field.py -- walkable clearance).
  MaxHeightFt : float, item access, default 24.0 (real value).
  RadiusFt    : float, item access, default 54.0 (real value -- 2 column
                bays).

Outputs:
  Heights : float list, parallel to QueryPoints.
  Log     : str summary -- wire to a Panel.

Assumptions:
  - Only X/Y are used for distance (matches the source script -- this is
    a 2D plan-distance falloff, not 3D).
  - If Seeds is empty, every height defaults to MinHeightFt and the Log
    warns explicitly, rather than dividing by zero or crashing.
  - All dimensional constants are in FEET, matching every other script in
    this repo.

When pasting into an actual Grasshopper Python 3 Script component, the
component requires '#! python 3' as the literal first line -- prepend it
(and drop this docstring, or keep it below the directive) since this file
leads with documentation instead for readability as a repo reference copy.
"""
import math

import Rhino.Geometry as rg


def smoothstep(t):
    t = max(0.0, min(1.0, t))
    return t * t * (3.0 - 2.0 * t)


def height_field(x, y, seeds_xy, min_h, max_h, radius):
    """seeds_xy: list of (x, y) tuples. Height is lowest near the nearest
    seed, opening up to max_h beyond radius."""
    d_min = min(math.hypot(x - sx, y - sy) for (sx, sy) in seeds_xy)
    t = smoothstep(d_min / radius)
    return min_h + (max_h - min_h) * t


def run():
    query_pts = list(QueryPoints) if QueryPoints else []
    seed_pts = list(Seeds) if Seeds else []
    min_h = float(MinHeightFt) if MinHeightFt is not None else 9.0
    max_h = float(MaxHeightFt) if MaxHeightFt is not None else 24.0
    radius = float(RadiusFt) if RadiusFt is not None else 54.0

    if not seed_pts:
        heights = [min_h for _ in query_pts]
        log = "WARNING: no Seeds wired -- every height defaulted to MinHeightFt={}".format(min_h)
        return heights, log

    seeds_xy = [(p.X, p.Y) for p in seed_pts]
    heights = [height_field(p.X, p.Y, seeds_xy, min_h, max_h, radius) for p in query_pts]

    log_lines = [
        "queryPoints={} seeds={}".format(len(query_pts), len(seed_pts)),
        "minHeightFt={} maxHeightFt={} radiusFt={}".format(min_h, max_h, radius),
    ]
    if heights:
        log_lines.append("heightRange=({:.2f}, {:.2f})".format(min(heights), max(heights)))
    return heights, "\n".join(log_lines)


Heights, Log = run()
print(Log)
