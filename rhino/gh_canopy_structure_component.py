"""
GhPython Script component: canopy_structure_generator
-------------------------------------------------------
Paste this into a GhPython Script component (Maths > Script > GhPython
Script) on a new Grasshopper canvas. It reproduces the standalone
rhino/generate_canopy_structure.py logic but as a live, parametric
component: preview columns/beams/purlins update as you drag sliders, and
nothing touches the Rhino document until you flip Bake to True.

Component setup
----------------
Inputs (right-click each input on the component to set name + type hint):
  Geo         : Brep, list access  -- Breps from the mm_struct_canopy_panels
                layer. Easiest source: a native "Geometry Pipeline" param
                (Params > Util > Geometry Pipeline, built into GH1, no
                plugin needed) filtered to layer "mm_struct_canopy_panels",
                fed into this input. Or just reference objects manually.
  GridSpacing : float, item access -- Number slider, default 1.5 (meters)
  GridRotDeg  : float, item access -- Number slider, default 45.0
  GenProb     : float, item access -- Number slider 0-1, default 0.70
  ColProb     : float, item access -- Number slider 0-1, default 0.30
  BeamProb    : float, item access -- Number slider 0-1, default 0.35
                (purlin gets whatever's left: 1 - ColProb - BeamProb)
  Seed        : int,   item access -- Integer slider/panel. Re-solving with
                the same seed reproduces the same layout -- without this,
                GH would reshuffle the random layout on every recompute,
                which makes it impossible to evaluate a specific result.
  Bake        : bool,  item access -- Boolean Toggle. False = preview only.
                Flip to True once you like a seed/parameter combo to write
                the geometry into Rhino's Detailed_Canopy layer structure.

Outputs (name the component's output params to match these exactly):
  Columns : Breps (cylinders) -- wire to a Custom Preview / native display
  Beams   : Breps (primary members)
  Purlins : Breps (secondary members)
  Log     : str summary -- wire to a Panel

Same assumptions as the standalone script apply here (top-face detection,
bbox-top fallback for non-planar tops, centered symmetric spans, purlins at
Z+0.4m, columns skipped if the grid point isn't above ground) -- see
rhino/generate_canopy_structure.py's docstring for the full rationale.
"""

import math
import random

import Rhino
import scriptcontext as sc
from Rhino.Geometry import (
    Box, Circle, Cylinder, Interval, Plane, PlaneSurface, Point3d,
    PointFaceRelation, Vector3d,
)

# ---- defaults for any un-wired optional inputs ----
if GridSpacing is None: GridSpacing = 1.5
if GridRotDeg is None: GridRotDeg = 45.0
if GenProb is None: GenProb = 0.70
if ColProb is None: ColProb = 0.30
if BeamProb is None: BeamProb = 0.35
if Seed is None: Seed = 0
if Bake is None: Bake = False

COLUMN_RADIUS_M = 0.2
BEAM_WIDTH_M = 0.15
BEAM_HEIGHT_M = 0.4
PURLIN_WIDTH_M = 0.1
PURLIN_HEIGHT_M = 0.2
PURLIN_Z_OFFSET_M = 0.4
SPAN_MIN_UNITS = 2
SPAN_MAX_UNITS = 6
TOP_FACE_NORMAL_DOT = 0.9

TARGET_ROOT_LAYER = "Detailed_Canopy"
COLUMN_LAYER = TARGET_ROOT_LAYER + "::Columns"
BEAM_LAYER = TARGET_ROOT_LAYER + "::Beams"
PURLIN_LAYER = TARGET_ROOT_LAYER + "::Purlins"

rhino_doc = Rhino.RhinoDoc.ActiveDoc
UNIT_SCALE = Rhino.RhinoMath.UnitScale(Rhino.UnitSystem.Meters, rhino_doc.ModelUnitSystem)
TOL = rhino_doc.ModelAbsoluteTolerance


def m(value):
    return value * UNIT_SCALE


def _find_top_face(brep):
    best_face = None
    best_z = None
    for face in brep.Faces:
        rc, plane = face.TryGetPlane(TOL)
        if not rc:
            continue
        if plane.Normal.Z < 0:
            plane.Flip()
        if plane.Normal * Vector3d.ZAxis < TOP_FACE_NORMAL_DOT:
            continue
        z = face.GetBoundingBox(True).Max.Z
        if best_z is None or z > best_z:
            best_z = z
            best_face = face
    return best_face


def _synthetic_top_face(brep):
    bbox = brep.GetBoundingBox(True)
    plane = Plane(Point3d(bbox.Min.X, bbox.Min.Y, bbox.Max.Z), Vector3d.ZAxis)
    surface = PlaneSurface(
        plane,
        Interval(0, bbox.Max.X - bbox.Min.X),
        Interval(0, bbox.Max.Y - bbox.Min.Y),
    )
    synth_brep = surface.ToBrep()
    return synth_brep.Faces[0], synth_brep


def _grid_points(face, spacing_m, rotation_deg):
    rc, plane = face.TryGetPlane(TOL)
    if not rc:
        return [], None, None
    if plane.Normal.Z < 0:
        plane.Flip()

    grid_plane = Plane(plane.Origin, plane.XAxis, plane.YAxis)
    grid_plane.Rotate(math.radians(rotation_deg), grid_plane.Normal)

    bbox = face.GetBoundingBox(True)
    corners = [
        Point3d(bbox.Min.X, bbox.Min.Y, bbox.Min.Z), Point3d(bbox.Max.X, bbox.Min.Y, bbox.Min.Z),
        Point3d(bbox.Min.X, bbox.Max.Y, bbox.Min.Z), Point3d(bbox.Max.X, bbox.Max.Y, bbox.Min.Z),
        Point3d(bbox.Min.X, bbox.Min.Y, bbox.Max.Z), Point3d(bbox.Max.X, bbox.Min.Y, bbox.Max.Z),
        Point3d(bbox.Min.X, bbox.Max.Y, bbox.Max.Z), Point3d(bbox.Max.X, bbox.Max.Y, bbox.Max.Z),
    ]
    us, vs = [], []
    for c in corners:
        rc2, u, v = grid_plane.ClosestParameter(c)
        us.append(u)
        vs.append(v)

    step = m(spacing_m)
    points = []
    u = min(us)
    while u <= max(us):
        v = min(vs)
        while v <= max(vs):
            candidate = grid_plane.PointAt(u, v)
            rc3, fu, fv = face.ClosestPoint(candidate)
            if rc3 and face.IsPointOnFace(fu, fv) != PointFaceRelation.Exterior:
                points.append(face.PointAt(fu, fv))
            v += step
        u += step
    return points, grid_plane.XAxis, grid_plane.YAxis


def _make_column(pt):
    if pt.Z <= TOL:
        return None
    base_plane = Plane(Point3d(pt.X, pt.Y, 0.0), Vector3d.ZAxis)
    circle = Circle(base_plane, m(COLUMN_RADIUS_M))
    return Cylinder(circle, pt.Z).ToBrep(True, True)


def _make_member(pt, run_axis, cross_axis, width_m, height_m, z_offset_m):
    length = m(random.randint(SPAN_MIN_UNITS, SPAN_MAX_UNITS) * GridSpacing)
    plane = Plane(pt, run_axis, cross_axis)
    if plane.ZAxis * Vector3d.ZAxis < 0:
        plane = Plane(pt, run_axis, -cross_axis)
    box = Box(
        plane,
        Interval(-length / 2.0, length / 2.0),
        Interval(-m(width_m) / 2.0, m(width_m) / 2.0),
        Interval(m(z_offset_m), m(z_offset_m) + m(height_m)),
    )
    return box.ToBrep()


def _ensure_layer_path(full_path):
    idx = rhino_doc.Layers.FindByFullPath(full_path, -1)
    if idx >= 0:
        return rhino_doc.Layers[idx].Id
    parent_id = None
    built = ""
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


random.seed(Seed)

col_breps, beam_breps, purlin_breps = [], [], []
grid_point_count = 0
skipped_objects = 0

geo_list = Geo if isinstance(Geo, list) else [Geo]

for g in geo_list:
    if g is None:
        continue
    brep = g if isinstance(g, Rhino.Geometry.Brep) else Rhino.Geometry.Brep.TryConvertBrep(g)
    if brep is None:
        skipped_objects += 1
        continue

    face = _find_top_face(brep)
    keep_alive = None
    if face is None:
        face, keep_alive = _synthetic_top_face(brep)

    points, primary_axis, secondary_axis = _grid_points(face, GridSpacing, GridRotDeg)
    if not points:
        skipped_objects += 1
        continue
    grid_point_count += len(points)

    for pt in points:
        if random.random() >= GenProb:
            continue
        roll = random.random()
        if roll < ColProb:
            b = _make_column(pt)
            if b:
                col_breps.append(b)
        elif roll < ColProb + BeamProb:
            beam_breps.append(
                _make_member(pt, primary_axis, secondary_axis, BEAM_WIDTH_M, BEAM_HEIGHT_M, 0.0)
            )
        else:
            purlin_breps.append(
                _make_member(pt, secondary_axis, primary_axis, PURLIN_WIDTH_M, PURLIN_HEIGHT_M,
                              PURLIN_Z_OFFSET_M)
            )

Columns = col_breps
Beams = beam_breps
Purlins = purlin_breps

Log = (
    "Objects skipped: {}\n"
    "Grid points evaluated: {}\n"
    "Columns: {}   Beams: {}   Purlins: {}\n"
    "Seed: {}"
).format(skipped_objects, grid_point_count, len(col_breps), len(beam_breps), len(purlin_breps), Seed)

if Bake:
    # scriptcontext.doc defaults to the GH document inside GhPython, not the
    # Rhino document -- swap it for the bake only, then restore it, or
    # AddBrep/layer calls silently miss the real Rhino document.
    prior_doc = sc.doc
    sc.doc = rhino_doc
    try:
        for path in (COLUMN_LAYER, BEAM_LAYER, PURLIN_LAYER):
            _ensure_layer_path(path)

        col_attr = Rhino.DocObjects.ObjectAttributes()
        col_attr.LayerIndex = rhino_doc.Layers.FindByFullPath(COLUMN_LAYER, -1)
        beam_attr = Rhino.DocObjects.ObjectAttributes()
        beam_attr.LayerIndex = rhino_doc.Layers.FindByFullPath(BEAM_LAYER, -1)
        purlin_attr = Rhino.DocObjects.ObjectAttributes()
        purlin_attr.LayerIndex = rhino_doc.Layers.FindByFullPath(PURLIN_LAYER, -1)

        for b in col_breps:
            rhino_doc.Objects.AddBrep(b, col_attr)
        for b in beam_breps:
            rhino_doc.Objects.AddBrep(b, beam_attr)
        for b in purlin_breps:
            rhino_doc.Objects.AddBrep(b, purlin_attr)

        rhino_doc.Views.Redraw()
        Log += "\nBAKED to {}::[Columns|Beams|Purlins]".format(TARGET_ROOT_LAYER)
    finally:
        sc.doc = prior_doc
