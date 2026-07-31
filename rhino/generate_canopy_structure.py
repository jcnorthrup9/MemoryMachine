"""
generate_canopy_structure.py
------------------------------
Run inside Rhino 8 via:  Tools > Python Script > Run...

Procedurally generates a supporting structure (columns, primary beams,
secondary purlins) against the top face of every object on the
mm_struct_canopy_panels layer, using a 1.5m x 1.5m grid rotated 45deg in
the plane of each object's topmost, mostly-upward-facing planar face.

Assumptions made explicit here because the prompt didn't pin them down:
  - "Top plane" = the Brep face with the highest elevation whose planar
    normal points mostly upward (dot with world Z > TOP_FACE_NORMAL_DOT).
    If an object has no such planar face (e.g. a curved/domed canopy
    shell), we fall back to a flat plane at the object's bounding-box top,
    spanning its XY footprint, so geometry still gets generated -- just
    against an approximation of the real top surface.
  - The grid's un-rotated axes come from the face's own planar
    parameterization (TryGetPlane); only the 45deg rotation relative to
    that is authoritative here, since the prompt didn't specify a
    reference direction to rotate from.
  - Grid points outside the face's outer boundary (or inside a hole) are
    skipped -- containment is checked per point via IsPointOnFace rather
    than assuming a rectangular face.
  - Beams/purlins are centered ON their grid point and extend
    symmetrically along their axis; the prompt didn't say "from" vs
    "centered at" the point, and centered keeps the grid visually
    balanced.
  - Beams sit directly on the top face (z -> z+0.4m). Purlins sit at
    z+0.4m -> z+0.6m as the prompt states literally ("secondary purlins
    ... at Z + 0.4m"), which also happens to put them on top of the beams.
  - Columns assume the top-plane point is above world Z=0 (ground) and are
    skipped with a warning otherwise, rather than generating an inverted
    or zero-height cylinder.
  - All dimensional constants below are in METERS and converted to the
    active document's unit system via UNIT_SCALE -- never hardcode raw
    numbers straight into doc units, since this project is worked from
    more than one machine/template with different unit setups.
"""

import math
import random

import rhinoscriptsyntax as rs
import scriptcontext as sc
import Rhino
from Rhino.Geometry import (
    Box,
    Circle,
    Cylinder,
    Interval,
    Plane,
    Point3d,
    Vector3d,
)

SOURCE_LAYER = "mm_struct_canopy_panels"
TARGET_ROOT_LAYER = "Detailed_Canopy"
COLUMN_LAYER = TARGET_ROOT_LAYER + "::Columns"
BEAM_LAYER = TARGET_ROOT_LAYER + "::Beams"
PURLIN_LAYER = TARGET_ROOT_LAYER + "::Purlins"

GRID_SPACING_M = 1.5
GRID_ROTATION_DEG = 45.0
GENERATE_PROBABILITY = 0.70
COLUMN_PROBABILITY = 0.30
BEAM_PROBABILITY = 0.35
# purlin gets the remainder (0.35)

COLUMN_RADIUS_M = 0.2
BEAM_WIDTH_M = 0.15
BEAM_HEIGHT_M = 0.4
PURLIN_WIDTH_M = 0.1
PURLIN_HEIGHT_M = 0.2
PURLIN_Z_OFFSET_M = 0.4
SPAN_MIN_UNITS = 2
SPAN_MAX_UNITS = 6

TOP_FACE_NORMAL_DOT = 0.9  # how "upward" a face normal must be to count as a top face

UNIT_SCALE = Rhino.RhinoMath.UnitScale(Rhino.UnitSystem.Meters, sc.doc.ModelUnitSystem)


def m(value):
    """Convert a value expressed in meters to the document's unit system."""
    return value * UNIT_SCALE


def _ensure_layer_path(full_path):
    """Create every missing layer along a '::' path and return the leaf's Id."""
    idx = sc.doc.Layers.FindByFullPath(full_path, -1)
    if idx >= 0:
        return sc.doc.Layers[idx].Id

    parent_id = None
    built = ""
    for seg in full_path.split("::"):
        built = seg if not built else built + "::" + seg
        found = sc.doc.Layers.FindByFullPath(built, -1)
        if found >= 0:
            parent_id = sc.doc.Layers[found].Id
            continue
        new_layer = Rhino.DocObjects.Layer()
        new_layer.Name = seg
        if parent_id is not None:
            new_layer.ParentLayerId = parent_id
        new_idx = sc.doc.Layers.Add(new_layer)
        if new_idx < 0:
            print("  [WARN] Could not create layer segment: {}".format(seg))
            return None
        parent_id = sc.doc.Layers[new_idx].Id
    return parent_id


def _attrs_for_layer(layer_path):
    attrs = Rhino.DocObjects.ObjectAttributes()
    attrs.LayerIndex = sc.doc.Layers.FindByFullPath(layer_path, -1)
    return attrs


def _find_top_face(brep):
    best_face = None
    best_z = None
    for face in brep.Faces:
        rc, plane = face.TryGetPlane(sc.doc.ModelAbsoluteTolerance)
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
    """Flat bbox-top fallback for objects with no upward planar face."""
    bbox = brep.GetBoundingBox(True)
    plane = Plane(Point3d(bbox.Min.X, bbox.Min.Y, bbox.Max.Z), Vector3d.ZAxis)
    surface = Rhino.Geometry.PlaneSurface(
        plane,
        Interval(0, bbox.Max.X - bbox.Min.X),
        Interval(0, bbox.Max.Y - bbox.Min.Y),
    )
    synth_brep = surface.ToBrep()
    return synth_brep.Faces[0], synth_brep


def _grid_points(face):
    """Return (points, primary_axis, secondary_axis) for a 45deg-rotated
    GRID_SPACING_M grid clipped to the face's outer boundary (and holes)."""
    rc, plane = face.TryGetPlane(sc.doc.ModelAbsoluteTolerance)
    if not rc:
        return [], None, None
    if plane.Normal.Z < 0:
        plane.Flip()

    grid_plane = Plane(plane.Origin, plane.XAxis, plane.YAxis)
    grid_plane.Rotate(math.radians(GRID_ROTATION_DEG), grid_plane.Normal)

    bbox = face.GetBoundingBox(True)
    corners = [
        Point3d(bbox.Min.X, bbox.Min.Y, bbox.Min.Z),
        Point3d(bbox.Max.X, bbox.Min.Y, bbox.Min.Z),
        Point3d(bbox.Min.X, bbox.Max.Y, bbox.Min.Z),
        Point3d(bbox.Max.X, bbox.Max.Y, bbox.Min.Z),
        Point3d(bbox.Min.X, bbox.Min.Y, bbox.Max.Z),
        Point3d(bbox.Max.X, bbox.Min.Y, bbox.Max.Z),
        Point3d(bbox.Min.X, bbox.Max.Y, bbox.Max.Z),
        Point3d(bbox.Max.X, bbox.Max.Y, bbox.Max.Z),
    ]
    us, vs = [], []
    for c in corners:
        rc2, u, v = grid_plane.ClosestParameter(c)
        us.append(u)
        vs.append(v)

    step = m(GRID_SPACING_M)
    points = []
    u = min(us)
    while u <= max(us):
        v = min(vs)
        while v <= max(vs):
            candidate = grid_plane.PointAt(u, v)
            rc3, fu, fv = face.ClosestPoint(candidate)
            if rc3:
                relation = face.IsPointOnFace(fu, fv)
                if relation != Rhino.Geometry.PointFaceRelation.Exterior:
                    points.append(face.PointAt(fu, fv))
            v += step
        u += step

    return points, grid_plane.XAxis, grid_plane.YAxis


def _make_column(pt):
    if pt.Z <= sc.doc.ModelAbsoluteTolerance:
        return None
    base_plane = Plane(Point3d(pt.X, pt.Y, 0.0), Vector3d.ZAxis)
    circle = Circle(base_plane, m(COLUMN_RADIUS_M))
    cylinder = Cylinder(circle, pt.Z)
    return cylinder.ToBrep(True, True)


def _make_member(pt, run_axis, cross_axis, width_m, height_m, z_offset_m):
    """Box centered on pt, extending along run_axis, width_m across
    cross_axis, from z_offset_m to z_offset_m + height_m above pt."""
    length = m(random.randint(SPAN_MIN_UNITS, SPAN_MAX_UNITS) * GRID_SPACING_M)

    plane = Plane(pt, run_axis, cross_axis)
    if plane.ZAxis * Vector3d.ZAxis < 0:
        # Keep the box's local Z pointing world-up regardless of which
        # axis (primary/secondary) was passed as run vs. cross -- the
        # width interval is symmetric so flipping cross_axis is harmless.
        plane = Plane(pt, run_axis, -cross_axis)

    box = Box(
        plane,
        Interval(-length / 2.0, length / 2.0),
        Interval(-m(width_m) / 2.0, m(width_m) / 2.0),
        Interval(m(z_offset_m), m(z_offset_m) + m(height_m)),
    )
    return box.ToBrep()


def main():
    print("=" * 60)
    print("generate_canopy_structure — starting")
    print("=" * 60)

    if not rs.IsLayer(SOURCE_LAYER):
        print("[ERROR] Layer '{}' does not exist in this document.".format(SOURCE_LAYER))
        return

    source_ids = rs.ObjectsByLayer(SOURCE_LAYER)
    if not source_ids:
        print("[INFO] No objects found on layer '{}'.".format(SOURCE_LAYER))
        return

    for layer_path in (COLUMN_LAYER, BEAM_LAYER, PURLIN_LAYER):
        if _ensure_layer_path(layer_path) is None:
            print("[ERROR] Could not set up '{}' -- aborting.".format(layer_path))
            return

    attrs = {
        "column": _attrs_for_layer(COLUMN_LAYER),
        "beam": _attrs_for_layer(BEAM_LAYER),
        "purlin": _attrs_for_layer(PURLIN_LAYER),
    }

    counts = {"columns": 0, "beams": 0, "purlins": 0, "skipped_points": 0, "grid_points": 0}
    objects_processed = 0
    objects_skipped = 0

    for obj_id in source_ids:
        brep = rs.coercebrep(obj_id)
        if brep is None:
            print("  [WARN] Object {} is not a Brep/Extrusion -- skipped.".format(obj_id))
            objects_skipped += 1
            continue

        face = _find_top_face(brep)
        if face is None:
            print("  [INFO] Object {}: no upward planar face found, using bbox-top fallback.".format(obj_id))
            face, _keep_alive = _synthetic_top_face(brep)

        points, primary_axis, secondary_axis = _grid_points(face)
        if not points:
            print("  [WARN] Object {}: grid produced no points inside the top face.".format(obj_id))
            objects_skipped += 1
            continue

        counts["grid_points"] += len(points)

        for pt in points:
            if random.random() >= GENERATE_PROBABILITY:
                counts["skipped_points"] += 1
                continue

            roll = random.random()
            if roll < COLUMN_PROBABILITY:
                geo_brep = _make_column(pt)
                if geo_brep is None:
                    counts["skipped_points"] += 1
                    continue
                sc.doc.Objects.AddBrep(geo_brep, attrs["column"])
                counts["columns"] += 1
            elif roll < COLUMN_PROBABILITY + BEAM_PROBABILITY:
                geo_brep = _make_member(
                    pt, primary_axis, secondary_axis, BEAM_WIDTH_M, BEAM_HEIGHT_M, 0.0
                )
                sc.doc.Objects.AddBrep(geo_brep, attrs["beam"])
                counts["beams"] += 1
            else:
                geo_brep = _make_member(
                    pt, secondary_axis, primary_axis, PURLIN_WIDTH_M, PURLIN_HEIGHT_M,
                    PURLIN_Z_OFFSET_M,
                )
                sc.doc.Objects.AddBrep(geo_brep, attrs["purlin"])
                counts["purlins"] += 1

        objects_processed += 1

    sc.doc.Views.Redraw()

    print("\nObjects processed: {}   skipped: {}".format(objects_processed, objects_skipped))
    print("Grid points evaluated: {}   (no-geometry rolls: {})".format(
        counts["grid_points"], counts["skipped_points"]))
    print("Baked -> {}: {} column(s)".format(COLUMN_LAYER, counts["columns"]))
    print("Baked -> {}: {} beam(s)".format(BEAM_LAYER, counts["beams"]))
    print("Baked -> {}: {} purlin(s)".format(PURLIN_LAYER, counts["purlins"]))
    print("\n" + "=" * 60)
    print("DONE")
    print("=" * 60)


main()
