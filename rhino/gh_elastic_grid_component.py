"""
GhPython Script component: PM_ElasticGrid
--------------------------------------------------------------------
Paste into a "Python 3 Script" component (Maths > Script > Python 3 Script,
guid 719467e6-7cf5-4848-99b0-c5dd57e5442c) on the FidelityGrid1.gh canvas,
downstream of PM_FacadePanelizer (FG1)'s real dtla_lines/seeds. See
PershingMetabolizer_Prototype/MASSING_FRAME.md for the full writeup.

Purpose: port `GRID_LOGIC_AND_MODEL_ALGORITHMS.md` section 1.6's
"threshold markers + warped DTLA lines" step -- documented as real,
already part of this site's 2D parti diagram, but never saved as its own
script (same gap as Behavior A/B) and never ported into Grasshopper. Also
independently proposed (in different terms -- "elastic Grid B buckling")
by a field-interference spec the user shared for review; recognized as
the same real, already-designed idea rather than built as a new
speculative algorithm.

Per section 1.6: the DTLA grid lines are resampled at ~3ft steps; each
sample point is pushed away from every real seed within a radius, force
ACCUMULATING across all seeds in range (not just the nearest one). Both
the radius and the force magnitude fade with THAT SEED'S OWN distance
from the site's real datum (ORIGIN) -- closer to the datum, stronger
repulsion. Calibrated (per the doc) so max deviation from straight lands
around 7-9ft. No exact formula/constants were saved anywhere, so this is
a faithful reconstruction of the documented EFFECT (accumulated radial
push, distance-from-ORIGIN-modulated strength, smoothstep falloff -- the
same falloff shape already established by PM_HeightField/
canopy_height_field.py, not the linear falloff a from-scratch spec might
guess at), with tunable sliders verified against the ~7-9ft target rather
than trusted as an exact port.

Component setup
----------------
Inputs:
  DtlaLines    : Curve list, list access. Wire FG1's dtla_lines-equivalent
                 (the 3 real DTLA grid lines) -- reuse, don't regenerate;
                 FG1 doesn't currently expose these as a GH output, so
                 for now wire line curves built from the same real
                 ORIGIN/DTLA_SPACING/DTLA_ANGLE constants (see FG1's own
                 docstring) -- e.g. via a small helper upstream, or by
                 extracting FG1's baked ColumnGrid/DtlaGrid layer curves.
  Seeds        : Point3d list, list access. Wire FG1's real SeedPts.
  SampleStepFt : float, item access, default 3.0 (the real spec's value).
  MaxRadiusFt  : float, item access, default 35.0. Repulsion radius at a
                 seed sitting exactly at ORIGIN (fades to 0 at the site's
                 far extent) -- calibrated live against FG1's real 55
                 seeds/3 DTLA lines: default 60.0 overshot to
                 maxDisplacementFt=15.22 (force accumulates across every
                 seed in range, so overlap compounds fast); 35.0
                 brought it into range.
  MaxForceFt   : float, item access, default 5.0. Maximum push distance
                 at a seed sitting exactly at ORIGIN -- same calibration
                 pass landed maxDisplacementFt=8.26 against this
                 component's own real DtlaLines/Seeds, inside the
                 ~7-9ft target (default 9.0 combined with the old
                 MaxRadiusFt=60.0 was the overshoot culprit above).

Outputs:
  DistortedLines : Curves (one NurbsCurve per input DTLA line).
  Log            : str summary -- wire to a Panel.

Assumptions:
  - "Distance from ORIGIN" normalizes against the farthest seed's own
    distance from ORIGIN (not a hardcoded site-extent constant), so the
    falloff always spans the actual seed population regardless of test
    footprint size.
  - Accumulated push is a straight vector sum across all in-range seeds
    (matches the doc's "force accumulating across all seeds in range, not
    just nearest"), not a max/nearest-only approach.
  - All dimensional constants are in FEET, matching every other script in
    this repo.

When pasting into an actual Grasshopper Python 3 Script component, the
component requires '#! python 3' as the literal first line -- prepend it
(and drop this docstring, or keep it below the directive) since this file
leads with documentation instead for readability as a repo reference copy.
"""
import math

import Rhino.Geometry as rg

ORIGIN = (319.89, 596.22)


def smoothstep(t):
    t = max(0.0, min(1.0, t))
    return t * t * (3.0 - 2.0 * t)


def seed_strength(seed_xy, max_dist_from_origin, max_radius_ft, max_force_ft):
    """Radius/force at this seed, scaled by how close the seed itself is
    to ORIGIN -- full strength at ORIGIN, fading to zero at the farthest
    seed's own distance."""
    d = math.hypot(seed_xy[0] - ORIGIN[0], seed_xy[1] - ORIGIN[1])
    t = 1.0 - smoothstep(d / max_dist_from_origin) if max_dist_from_origin > 1e-6 else 1.0
    return max_radius_ft * t, max_force_ft * t


def distort_curve(crv, scaled_seeds, sample_step):
    """scaled_seeds: list of (sx, sy, radius_ft, force_ft) -- per-seed
    strength precomputed once (it doesn't depend on the sample point),
    not recomputed for every point on every curve."""
    length = crv.GetLength()
    if length < 1e-6:
        return crv, 0, 0.0
    n = max(2, int(round(length / sample_step)))
    params = crv.DivideByCount(n, True)
    if not params:
        params = [crv.Domain.Mid]
    new_pts = []
    max_disp = 0.0
    for t in params:
        pt = crv.PointAt(t)
        total = rg.Vector3d(0, 0, 0)
        for (sx, sy, radius_ft, force_ft) in scaled_seeds:
            if radius_ft < 1e-6:
                continue
            d = math.hypot(pt.X - sx, pt.Y - sy)
            if d < 1e-6 or d >= radius_ft:
                continue
            falloff = 1.0 - smoothstep(d / radius_ft)
            mag = falloff * force_ft
            vx, vy = (pt.X - sx) / d, (pt.Y - sy) / d
            total += rg.Vector3d(vx * mag, vy * mag, 0.0)
        new_pt = pt + total
        max_disp = max(max_disp, total.Length)
        new_pts.append(new_pt)
    if len(new_pts) < 2:
        return crv, len(new_pts), max_disp
    curve = rg.Curve.CreateInterpolatedCurve(new_pts, 3)
    return (curve if curve is not None else crv), len(new_pts), max_disp


def run():
    lines = list(DtlaLines) if DtlaLines else []
    seed_pts = list(Seeds) if Seeds else []
    sample_step = float(SampleStepFt) if SampleStepFt is not None else 3.0
    max_radius = float(MaxRadiusFt) if MaxRadiusFt is not None else 35.0
    max_force = float(MaxForceFt) if MaxForceFt is not None else 5.0

    if not lines:
        return [], "WARNING: no DtlaLines wired -- nothing to distort."
    if not seed_pts:
        return lines, "WARNING: no Seeds wired -- returning input lines unchanged."

    seeds_xy = [(p.X, p.Y) for p in seed_pts]
    max_dist_from_origin = max(math.hypot(sx - ORIGIN[0], sy - ORIGIN[1]) for (sx, sy) in seeds_xy)
    max_dist_from_origin = max(max_dist_from_origin, 1e-6)

    scaled_seeds = []
    for (sx, sy) in seeds_xy:
        radius_ft, force_ft = seed_strength((sx, sy), max_dist_from_origin, max_radius, max_force)
        scaled_seeds.append((sx, sy, radius_ft, force_ft))

    out_curves = []
    total_samples = 0
    overall_max_disp = 0.0
    for crv in lines:
        distorted, n_samples, max_disp = distort_curve(crv, scaled_seeds, sample_step)
        out_curves.append(distorted)
        total_samples += n_samples
        overall_max_disp = max(overall_max_disp, max_disp)

    log_lines = [
        "lines={} seeds={} sampleStepFt={}".format(len(lines), len(seed_pts), sample_step),
        "maxRadiusFt={} maxForceFt={}".format(max_radius, max_force),
        "totalSamples={} maxDisplacementFt={:.2f}  (target ~7-9ft per GRID_LOGIC doc)".format(
            total_samples, overall_max_disp),
    ]
    return out_curves, "\n".join(log_lines)


DistortedLines, Log = run()
print(Log)
