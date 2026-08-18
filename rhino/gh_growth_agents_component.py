"""
GhPython Script component: PM_GrowthAgents
--------------------------------------------------------------------
Paste into a "Python 3 Script" component (Maths > Script > Python 3 Script,
guid 719467e6-7cf5-4848-99b0-c5dd57e5442c) on the FidelityGrid1.gh canvas,
downstream of PM_GrowthColumns (rhino/gh_growth_columns_component.py). See
PershingMetabolizer_Prototype/GROWTH_COLUMNS.md for the full writeup.

Purpose: grows orthogonal stick structures upward from a set of seed
points, contained within a massing volume. This is a clean, repo-tracked
port of the agent-based growth algorithm prototyped and verified live in
the user's own "ImageSamplerToColumns.gh" pipeline this session (cohesion
+ decaying upward gravity + axis-snapped orthogonal movement).

USED TWICE in the FidelityGrid1.gh pipeline -- once for major-grid
("column") points, once for mullion points, as two separate component
instances with different RigidityBias/MaxGens/Speed settings and
different downstream module cross-sections. Originally major points were
built as fixed straight pins by PM_GrowthColumns itself while only
mullions ran through this growth script; per explicit user direction
("they both should have this logic") PM_GrowthColumns now just emits raw
points for BOTH grids, and this component handles all growth+containment
for both -- a nice side effect is that the massing-top falloff for major
columns is now handled by the same containment mechanism as mullions,
replacing the flat-height-cap special case that existed before this.

Algorithm (unchanged from the verified original, credit due -- this is
the user's own agent design, not a new invention):
  - Each seed point becomes an agent.
  - Each generation, an agent's acceleration is: a decaying upward
    "gravity" (strong early, fading to zero by MaxGens) plus a "cohesion"
    force pulling it toward every other agent, weighted by inverse
    squared distance. Combined and unitized.
  - NEW (this port): RigidityBias blends that combined vector toward pure
    UP_VEC before axis-snapping -- 0.0 leaves it unchanged (free-branching,
    the original mullion behavior), closer to 1.0 makes the agent's
    accumulated direction increasingly dominated by "straight up" before
    force_ortho picks an axis, so it stays close to its own grid line and
    reads as structural rather than organic. This is the mechanism behind
    "columns grow more rigidly, mullions wander more freely."
  - The (possibly rigidity-biased) vector is snapped to whichever single
    axis (X, Y, or Z) it's most aligned with (force_ortho -- orthogonal,
    architectural character, not a diagonal/organic blob), then scaled by
    Speed.
  - Containment: if a Massing Brep is wired, an agent that would step
    outside the massing's actual solid volume freezes permanently instead
    of moving -- growth stays inside the real 3D envelope (including any
    setbacks/terracing a real massing has), not just a flat plan
    footprint or a single global height cap. Without a Massing wired,
    agents grow unconstrained (useful for pure algorithm testing).
  - Brep.IsPointInside() is only reliable on a CLOSED, manifold solid.
    prepare_massing() checks IsSolid/IsValid first and, if the wired Brep
    isn't already closed, attempts Brep.CapPlanarHoles() before use --
    reported in the Log either way. If it still can't be closed,
    containment falls back to a flat Z-height cap at the massing's own
    bounding-box top, rather than skipping containment entirely.

Component setup
----------------
Inputs:
  Points        : Point3d list, list access. Seed points -- wire either
                  PM_GrowthColumns' MajorPoints or MullionPoints (use two
                  separate instances of this component, one per grid).
  Massing       : Brep, item access, optional. Same Brep wired into
                  PM_GrowthColumns' own Massing input.
  MaxGens       : int, item access, default 12.
  Speed         : float, item access, default 2.5 (ft per generation step).
  RigidityBias  : float, item access, 0.0-1.0, default 0.0. 0.0 = original
                  free-branching behavior (appropriate for mullions).
                  Values closer to 1.0 keep growth closer to vertical/on
                  its own seed line (appropriate for major columns, which
                  should read as structural, not organic).

Outputs:
  GrowthPts : Point3d list -- every agent's full trail (seed position plus
              one point per generation it was still alive), ready to feed
              a native "Center Box" + "Move" pair to visualize the actual
              grown structure. Use a thicker Center Box for the major-grid
              instance, thinner for the mullion instance.
  Log       : str summary -- wire to a Panel.

On the image-sampling gate: PM_GrowthColumns already outputs MullionUV
(each seed point's position normalized 0-1 against its footprint's
bounding box) for exactly this purpose, correctly scaled from day one.
Bypassed here per the user's explicit decision, since the image currently
wired in the old pipeline is a random placeholder, not a real plan
drawing. When a real plan image (white background, black wall poche) is
ready, insert a native Image Sampler + Smaller Than + Dispatch between
PM_GrowthColumns.MullionPoints/MullionUV and the mullion instance's Points
input -- no changes needed here.

Assumptions:
  - Bounding-box-based containment tolerance uses the active document's
    ModelAbsoluteTolerance, matching every other script in this repo.
  - All dimensional constants are in FEET.

When pasting into an actual Grasshopper Python 3 Script component, the
component requires '#! python 3' as the literal first line -- prepend it
(and drop this docstring, or keep it below the directive) since this file
leads with documentation instead for readability as a repo reference copy.
"""
import Rhino
import Rhino.Geometry as rg

rhino_doc = Rhino.RhinoDoc.ActiveDoc
TOL = rhino_doc.ModelAbsoluteTolerance if rhino_doc else 0.01

UP_VEC = rg.Vector3d(0, 0, 1)


def force_ortho(vec):
    """Snap a vector to whichever single axis it's most aligned with, then
    re-unitize -- gives growth its orthogonal, architectural character
    rather than an organic/diagonal blob."""
    if abs(vec.X) > abs(vec.Y) and abs(vec.X) > abs(vec.Z):
        vec.Y = 0
        vec.Z = 0
    elif abs(vec.Y) > abs(vec.Z):
        vec.X = 0
        vec.Z = 0
    else:
        vec.X = 0
        vec.Y = 0
    if vec.X != 0 or vec.Y != 0 or vec.Z != 0:
        vec.Unitize()
    return vec


def prepare_massing(massing):
    """Returns (brep_or_None, z_cap_or_None, log_line). See module
    docstring for why this exists -- IsPointInside needs a closed solid,
    and this makes that explicit rather than trusting an unreliable
    result."""
    if massing is None:
        return None, None, "massing=not wired (unconstrained growth)"
    bbox = massing.GetBoundingBox(True)
    z_cap = bbox.Max.Z
    if massing.IsSolid and massing.IsValid:
        return massing, z_cap, "massing=wired, closed solid (containment active)"
    capped = massing.CapPlanarHoles(TOL)
    if capped and massing.IsSolid and massing.IsValid:
        return massing, z_cap, "massing=wired, capped open Brep into a closed solid (containment active)"
    return None, z_cap, ("massing=wired but NOT a closed solid and could not be capped -- "
                          "falling back to a flat Z-height cap at {:.2f}ft (containment approximate)"
                          .format(z_cap))


class Agent(object):
    def __init__(self, pos):
        self.pos = rg.Point3d(pos)
        self.alive = True

    def cohesion(self, agents):
        total = rg.Vector3d(0, 0, 0)
        for other in agents:
            d2 = rg.Point3d(other.pos).DistanceToSquared(self.pos)
            if d2 > 0:
                v = rg.Point3d(other.pos) - self.pos
                v.Unitize()
                v = v * (1.0 / d2)
                total = total + v
        total.Unitize()
        return total

    def update(self, gen, max_gens, speed, agents, massing, z_cap, rigidity):
        if not self.alive:
            return
        gravity = UP_VEC * (1.0 - (gen / float(max_gens)))
        acc = gravity + self.cohesion(agents)
        acc.Unitize()
        if rigidity > 0.0:
            acc = acc * (1.0 - rigidity) + UP_VEC * rigidity
            acc.Unitize()
        acc = force_ortho(acc)
        acc = acc * speed
        new_pos = self.pos + acc
        if massing is not None:
            if not massing.IsPointInside(new_pos, TOL, False):
                self.alive = False
                return
        elif z_cap is not None and new_pos.Z > z_cap:
            self.alive = False
            return
        self.pos = new_pos


def grow(points, massing, z_cap, max_gens, speed, rigidity):
    agents = [Agent(p) for p in points]
    out_pts = [rg.Point3d(a.pos) for a in agents]
    for g in range(max_gens):
        for a in agents:
            if not a.alive:
                continue
            a.update(g, max_gens, speed, agents, massing, z_cap, rigidity)
            if a.alive:
                out_pts.append(rg.Point3d(a.pos))
    frozen = sum(1 for a in agents if not a.alive)
    return out_pts, frozen


def run():
    pts = list(Points) if Points else []
    max_gens = max(1, int(MaxGens)) if MaxGens is not None else 12
    speed = float(Speed) if Speed is not None else 2.5
    rigidity = min(1.0, max(0.0, float(RigidityBias))) if RigidityBias is not None else 0.0

    if not pts:
        return [], "WARNING: no seed Points wired -- nothing to grow."

    massing, z_cap, massing_log = prepare_massing(Massing)
    out_pts, frozen = grow(pts, massing, z_cap, max_gens, speed, rigidity)

    log_lines = [
        "seeds={} maxGens={} speed={} rigidityBias={}".format(len(pts), max_gens, speed, rigidity),
        massing_log,
        "frozenByContainment={}/{}".format(frozen, len(pts)) if (massing is not None or z_cap is not None) else "",
        "growthPts={}".format(len(out_pts)),
    ]
    return out_pts, "\n".join(l for l in log_lines if l)


GrowthPts, Log = run()
print(Log)
