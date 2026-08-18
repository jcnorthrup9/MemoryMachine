"""
GhPython Script component: PM_CellOccupancy
--------------------------------------------------------------------
Paste into a "Python 3 Script" component (Maths > Script > Python 3 Script,
guid 719467e6-7cf5-4848-99b0-c5dd57e5442c) on the FidelityGrid1.gh canvas,
downstream of PM_FacadePanelizer (FG1)'s real SeedPts. See
PershingMetabolizer_Prototype/MASSING_FRAME.md for the full writeup.

Purpose: a voxel-cell "placement guide" -- decides WHERE the massing
frame (PM_MassingFrame_Lsystem) should grow, at a finer resolution than
the sparse 55 site-wide real seeds alone. This is the useful piece of a
field-interference spec the user shared for review (which proposed solid
stair-stepped voxel massing) -- per explicit user direction, kept as a
PLACEMENT GUIDE only (candidate root points), not solid built geometry;
the actual visible massing stays PM_MassingFrame_Lsystem's open
interlocking bar-frame output.

Directly addresses a real limitation found verifying PM_MassingFrame_
Lsystem: a small test massing footprint only contains 1-9 of the site's
55 real seeds (`rootsInMassing=1` in that component's own Log), giving a
sparse, barely-visible frame. This component generates denser candidate
root positions -- gated by real seed proximity, so they stay anchored to
the real site data, not an arbitrary uniform grid -- meant to be merged
with FG1's own SeedPts (via a native GH Merge component) before feeding
PM_MassingFrame_Lsystem.Seeds.

Component setup
----------------
Inputs:
  Seeds           : Point3d list, list access. Wire FG1's real SeedPts --
                    proximity to these decides which cells qualify.
  Massing         : Brep, item access, optional. Section-cut footprint
                    extraction reuses PM_GrowthColumns.footprint_from_
                    massing()'s exact pattern (general-purpose, not
                    bottom-face-only).
  CellSizeFt      : float, item access, default 9.0. Independent of the
                    27ft column-module MARKED-cell field FG1 already
                    uses -- a finer, separate resolution (per the
                    reviewed spec's own suggested 6-9ft).
  InfluenceRadiusFt : float, item access, default 54.0 (matches
                    PM_HeightField's own RadiusFt default -- same
                    real-scale intuition, 2 column bays).

Outputs:
  OccupiedCells : Points (qualifying cell centers -- candidate roots).
  Log           : str summary -- wire to a Panel.

Assumptions:
  - A cell "qualifies" if its center is inside the massing footprint AND
    within InfluenceRadiusFt of at least one real seed -- binary
    (in/out), not a continuous density field, matching this project's
    established "real open voids, not everywhere" convention (same
    reasoning PM_PinGrid's binary MARKED zones already established).
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


def footprint_from_massing(massing):
    """Verbatim pattern from PM_GrowthColumns -- general-purpose section-
    cut, not a bottom-face assumption."""
    bbox = massing.GetBoundingBox(True)
    cut_z = bbox.Min.Z + 0.05
    plane = rg.Plane(rg.Point3d(0.0, 0.0, cut_z), rg.Vector3d.ZAxis)
    ok, curves, _pts = rg.Intersect.Intersection.BrepPlane(massing, plane, TOL)
    if not ok or not curves:
        return []
    return [crv for crv in curves if crv.IsClosed and crv.IsPlanar(TOL)]


def point_in_curve(crv, x, y):
    containment = crv.Contains(rg.Point3d(x, y, 0.0), rg.Plane.WorldXY, TOL)
    return containment == rg.PointContainment.Inside or containment == rg.PointContainment.Coincident


def run():
    seed_pts = list(Seeds) if Seeds else []
    cell_size = float(CellSizeFt) if CellSizeFt is not None else 9.0
    influence_radius = float(InfluenceRadiusFt) if InfluenceRadiusFt is not None else 54.0

    if not seed_pts:
        return [], "WARNING: no Seeds wired -- nothing to test proximity against."
    if Massing is None:
        return [], "WARNING: no Massing wired -- nothing to grid."

    footprints = footprint_from_massing(Massing)
    if not footprints:
        return [], "WARNING: massing footprint extraction returned nothing."

    seeds_xy = [(p.X, p.Y) for p in seed_pts]

    occupied = []
    candidates = 0
    for crv in footprints:
        bbox = crv.GetBoundingBox(True)
        nx = max(1, int(math.ceil((bbox.Max.X - bbox.Min.X) / cell_size)))
        ny = max(1, int(math.ceil((bbox.Max.Y - bbox.Min.Y) / cell_size)))
        for i in range(nx):
            for j in range(ny):
                cx = bbox.Min.X + (i + 0.5) * cell_size
                cy = bbox.Min.Y + (j + 0.5) * cell_size
                if not point_in_curve(crv, cx, cy):
                    continue
                candidates += 1
                nearest_d = min(math.hypot(cx - sx, cy - sy) for (sx, sy) in seeds_xy)
                if nearest_d <= influence_radius:
                    occupied.append(rg.Point3d(cx, cy, 0.0))

    log_lines = [
        "seeds={} cellSizeFt={} influenceRadiusFt={}".format(len(seed_pts), cell_size, influence_radius),
        "candidateCells={} occupiedCells={}{}".format(
            candidates, len(occupied),
            "  (WARNING: zero cells within InfluenceRadiusFt of any seed)"
            if occupied == [] and candidates > 0 else ""),
    ]
    return occupied, "\n".join(log_lines)


OccupiedCells, Log = run()
print(Log)
