"""
blender/pershing_headless_build.py
-----------------------------------
Headless Blender scene builder for the Pershing hybrid pipeline.

Ingests the SAME rebuild JSON payload the browser already gets from
POST /api/pershing/rebuild (logic/pershing_api.py) -- does NOT re-run
TerracingEngine, does NOT need bpy paint-canvas state. This is the
headless counterpart to blender_cockpit.py's rebuild_all() /
build_structural_meshes(), stripped of the live-paint UI (the browser's
PaintOverlay.jsx already owns that job) and re-pointed at CLI args instead
of hardcoded D:\\MemoryMachine paths, so it stays portable across the
Syncthing-synced machines this repo lives on.

Deliberately does NOT re-import blender_cockpit.py's static-context import
or axo-view/mirror setup: that mirror is specific to the cockpit's own fixed
presentation camera. This export instead stays in the same raw real-feet,
Z-up convention the live JSON/Three.js viewport already uses (see
Viewport.jsx's toThree() and StaticContext.jsx's own transform) -- baking
in the axo mirror here would silently put this mesh in a different
coordinate convention than everything else the frontend loads.

2026-07-13: real columns/slabs/ramps (real_columns, real_slabs, ramp_meshes
-- see build_real_context_meshes/build_ramp_meshes) ARE now included in the
primary --output OBJ, replacing what used to be a box-per-voxel terrace
mesh (never matched the actual parking structure slabs). This export is
consumed standalone (e.g. opened directly in Rhino), not alongside the
live web viewport, so the earlier "avoid double-rendering site_named.obj"
reasoning no longer applies to that geometry. The tunnel/secondary-entrance/
metro-connector static context is still NOT re-embedded here -- only real
columns/slabs/ramps, per what's actually been requested so far.

Run headless:
    blender --background --python pershing_headless_build.py -- \
        --input <rebuild JSON> --output <obj path> \
        [--lineart-output <svg path>]

The box/cylinder/hex-prism mesh-building math below is a straight port of
blender_cockpit.py's versions -- duplicated rather than imported, same
reasoning that script already established for its own AXO_VIEW_DIR/
_axo_basis constants: importing terracing_engine.py here would pull in
numpy plus require constructing a throwaway TerracingEngine instance just
to reuse two small helpers, when this script's input is already the fully
computed voxel/structural JSON, not raw site geometry.

--lineart-output is optional and additive to the OBJ export, not a
replacement -- when given, runs blender/blender_lineart_export.py's proven
Grease Pencil Line Art pipeline (2026-07-03 rehearsal: LINEART_OBJECT
preset, not a manually-built GP+modifier, which reliably bakes to zero
strokes; camera-space-projected ortho_scale, not world-space; frame_start/
frame_end pinned to 1) directly against the mesh this script just built in
memory -- no OBJ export+reimport round trip needed, unlike that rehearsal
script, which imports an already-exported OBJ from disk. Uses the
LINEART_SCENE preset instead of LINEART_OBJECT, since this script's scene
has many objects (the terrace plus one mesh per structural kind) that all
need to contribute strokes, not just one.
"""
import argparse
import json
import math
import os
import sys

import bmesh
import bpy
import mathutils

STRUCTURAL_COLLECTION_NAME = "mm_structural_frame"
CANOPY_OBJ_NAME = "mm_canopy"
CANOPY_COLLECTION_NAME = "mm_canopy_layer"
REAL_CONTEXT_COLLECTION_NAME = "mm_real_slabs_columns"
REAL_RAMPS_COLLECTION_NAME = "mm_real_ramps"

# Shared kind registry (2026-07-16 fix -- see the note this block used to
# carry, admitting this file's kind tables had ALREADY drifted once:
# circulation_network.py's footpath/ramp/escalator kinds were silently
# dropped from this script's OBJ export until manually patched, while
# blender_cockpit.py's equivalent tables derived dynamically from
# KIND_REGISTRY and never had that problem. Fixed properly this time by
# doing the same here, instead of hand-patching another entry (canopy_panel/
# canopy_column_trunk/canopy_column_branch) into a tuple that will just
# drift again next time a kind is added). Pure stdlib json.load(), no bpy/
# numpy cost -- this script already imports json at module scope, so this
# doesn't reintroduce the "importing terracing_engine.py pulls in numpy
# plus a throwaway TerracingEngine instance" cost the module docstring
# explains this file avoids elsewhere.
_KIND_REGISTRY_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "frontend", "src", "kindRegistry.json")
with open(_KIND_REGISTRY_PATH) as _f:
    _KIND_REGISTRY = json.load(_f)

# Cross-section (plan) footprint in feet for each box-shaped
# StructuralElement.kind -- mirrors blender_cockpit.py's _PROTOTYPE_DIMS_FT
# exactly. Cylinder/hex/panel kinds don't use this dict; their geometry
# comes from radius_ft/normal_x-y-z (and, for two-point kinds, x2/y2/z2_ft)
# instead.
_PROTOTYPE_DIMS_FT = {
    kind: tuple(entry["dims_ft"]) for kind, entry in _KIND_REGISTRY["kinds"].items() if entry["shape"] == "box"
}
_VERTICAL_CYLINDER_KINDS = {
    kind for kind, entry in _KIND_REGISTRY["kinds"].items() if entry["shape"] == "vertical_cylinder"
}
_HEX_KINDS = {kind for kind, entry in _KIND_REGISTRY["kinds"].items() if entry["shape"] == "hex"}
# 2026-07-16 Canopy Redesign -- flat individually-oriented panels
# (canopy_panel), needs a full per-instance basis from a normal vector
# (see _add_panel), not just a rotation_deg like the box path.
_PANEL_KINDS = {kind for kind, entry in _KIND_REGISTRY["kinds"].items() if entry["shape"] == "panel"}
# Circulation paths (2026-07-13) render as flat ribbons, not round tubes --
# see _add_ribbon below. Kept as a small explicit set rather than derived
# from KIND_REGISTRY's `shape` field (unlike everything else in this
# block): "two_point AND a walkable path" isn't a shape-level distinction
# the registry schema captures, and unlike _ALL_STRUCT_KINDS below, this
# set hasn't actually drifted -- it's reviewed alongside every new
# two-point kind addition, so hand-maintaining it is a deliberate choice,
# not a repeat of the bug this fix closes.
CIRCULATION_PATH_KINDS = {
    "footpath", "ramp", "escalator", "footpath_bridge", "ramp_bridge", "escalator_bridge",
}
PATH_HALF_THICKNESS_FT = 0.25  # slightly thickened, not a paper-thin plane -- see Viewport.jsx's twin constant
_ALL_STRUCT_KINDS = tuple(
    kind for kind, entry in _KIND_REGISTRY["kinds"].items() if entry["shape"] != "real"
)

_BOX_FACES = ((0, 1, 2, 3), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7))


def _add_rotated_box(bm, center, size, rot_mat3):
    hx, hy, hz = size[0] / 2, size[1] / 2, size[2] / 2
    local = (
        (-hx, -hy, -hz), (hx, -hy, -hz), (hx, hy, -hz), (-hx, hy, -hz),
        (-hx, -hy, hz), (hx, -hy, hz), (hx, hy, hz), (-hx, hy, hz),
    )
    verts = [bm.verts.new(rot_mat3 @ mathutils.Vector(c) + mathutils.Vector(center)) for c in local]
    for f in _BOX_FACES:
        bm.faces.new([verts[i] for i in f])


def _rotation_for(spec):
    # Only gusset_plate uses a rotated-box path (faced along the strut's
    # bearing angle, about Z) -- knee braces and tie-rods are true
    # two-point cylinders, so they don't need an angle guess here.
    if spec["kind"] == "gusset_plate":
        return mathutils.Matrix.Rotation(math.radians(spec.get("rotation_deg", 0.0)), 4, 'Z').to_3x3()
    return mathutils.Matrix.Identity(3)


def _add_cylinder(bm, p0, p1, radius, segments=8):
    p0 = mathutils.Vector(p0)
    p1 = mathutils.Vector(p1)
    axis = p1 - p0
    length = axis.length
    if length < 1e-6:
        return
    axis_n = axis / length
    ref = mathutils.Vector((0.0, 0.0, 1.0)) if abs(axis_n.z) < 0.9 else mathutils.Vector((1.0, 0.0, 0.0))
    u = ref.cross(axis_n).normalized()
    v = axis_n.cross(u).normalized()
    ring0, ring1 = [], []
    for i in range(segments):
        ang = 2 * math.pi * i / segments
        offset = (u * math.cos(ang) + v * math.sin(ang)) * radius
        ring0.append(bm.verts.new(p0 + offset))
        ring1.append(bm.verts.new(p1 + offset))
    for i in range(segments):
        j = (i + 1) % segments
        bm.faces.new((ring0[i], ring0[j], ring1[j], ring1[i]))
    bm.faces.new(ring0[::-1])
    bm.faces.new(ring1)


def _add_ribbon(bm, p0, p1, half_width, half_thickness):
    """Flat, slightly-thickened plank between two points -- same u/v basis
    _add_cylinder uses above (ref=(0,0,1) unless the segment is nearly
    vertical), but a 4-corner rectangle cross-section instead of a circular
    ring, so an inclined ramp's cross-section tilts naturally with grade
    instead of staying flat. Used for circulation_network.py's footpath/
    ramp/escalator kinds (2026-07-13, replacing round cylinders -- these
    are walkable path surfaces, not structural rods)."""
    p0 = mathutils.Vector(p0)
    p1 = mathutils.Vector(p1)
    axis = p1 - p0
    length = axis.length
    if length < 1e-6:
        return
    axis_n = axis / length
    ref = mathutils.Vector((0.0, 0.0, 1.0)) if abs(axis_n.z) < 0.9 else mathutils.Vector((1.0, 0.0, 0.0))
    u = ref.cross(axis_n).normalized()  # width axis
    v = axis_n.cross(u).normalized()    # thickness axis
    corners = (u * half_width + v * half_thickness, -u * half_width + v * half_thickness,
               -u * half_width - v * half_thickness, u * half_width - v * half_thickness)
    ring0 = [bm.verts.new(p0 + c) for c in corners]
    ring1 = [bm.verts.new(p1 + c) for c in corners]
    for i in range(4):
        j = (i + 1) % 4
        bm.faces.new((ring0[i], ring0[j], ring1[j], ring1[i]))
    bm.faces.new(ring0[::-1])
    bm.faces.new(ring1)


def _add_hex_prism(bm, center, radius, height, rotation_deg=0.0):
    cx, cy, cz = center
    top, bottom = cz + height / 2, cz - height / 2
    ring_top, ring_bottom = [], []
    for i in range(6):
        ang = math.radians(60 * i + rotation_deg)
        x, y = cx + radius * math.cos(ang), cy + radius * math.sin(ang)
        ring_top.append(bm.verts.new((x, y, top)))
        ring_bottom.append(bm.verts.new((x, y, bottom)))
    for i in range(6):
        j = (i + 1) % 6
        bm.faces.new((ring_bottom[i], ring_bottom[j], ring_top[j], ring_top[i]))
    bm.faces.new(ring_top)
    bm.faces.new(ring_bottom[::-1])


def _add_panel(bm, center, normal, width, depth, thickness):
    """Flat individually-oriented plate (canopy_panel) -- 2026-07-16 Canopy
    Redesign. Straight port of blender_cockpit.py's _add_panel (same u/v
    basis _add_cylinder/_add_ribbon above already use: ref=(0,0,1) unless
    the normal is nearly vertical, then fall back to (1,0,0); u = ref x n,
    v = n x u) -- same threshold, same cross-product order as
    Viewport.jsx's CanopyPanelInstances (which works in Three.js's Y-up
    frame post-toThreeDir(), this one works directly in Blender's native
    Z-up frame on the raw real-feet normal, so the reference axis is Z
    here vs Y there BY DESIGN, not a discrepancy). See that component's own
    comment for why this must be checked cross-tool if ever touched
    again -- this exact bug class (position/direction mirror mismatches)
    has shipped once already in this codebase."""
    center_v = mathutils.Vector(center)
    n = mathutils.Vector(normal).normalized()
    ref = mathutils.Vector((0.0, 0.0, 1.0)) if abs(n.z) < 0.9 else mathutils.Vector((1.0, 0.0, 0.0))
    u = ref.cross(n).normalized()
    v = n.cross(u).normalized()
    hw, hd, ht = width / 2, depth / 2, thickness / 2
    bottom, top = [], []
    for su, sv in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
        base = center_v + u * (su * hw) + v * (sv * hd)
        bottom.append(bm.verts.new(base - n * ht))
        top.append(bm.verts.new(base + n * ht))
    for i in range(4):
        j = (i + 1) % 4
        bm.faces.new((bottom[i], bottom[j], top[j], top[i]))
    bm.faces.new(bottom[::-1])
    bm.faces.new(top)


def build_canopy_mesh(mesh, height_matrix, voxel_ft, puncture_mask=None):
    """Continuous heightfield mesh (one bmesh vert per (gx, gy) grid point,
    one quad face per cell) -- NOT box-per-voxel like build_terrace_mesh
    above, a real continuous surface, same cx/cy centering convention as
    build_terrace_mesh. Cells where puncture_mask[gx][gy] is true skip their
    face entirely, leaving a real hole rather than a solid quad there."""
    bm = bmesh.new()
    nx = len(height_matrix)
    nz = len(height_matrix[0]) if nx else 0
    verts = [[None] * nz for _ in range(nx)]
    for gx in range(nx):
        for gy in range(nz):
            cx = gx * voxel_ft + voxel_ft / 2
            cy = gy * voxel_ft + voxel_ft / 2
            verts[gx][gy] = bm.verts.new((cx, cy, height_matrix[gx][gy]))
    for gx in range(nx - 1):
        for gy in range(nz - 1):
            if puncture_mask and puncture_mask[gx][gy]:
                continue
            bm.faces.new((verts[gx][gy], verts[gx + 1][gy], verts[gx + 1][gy + 1], verts[gx][gy + 1]))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(mesh)
    bm.free()


def _order_quad_corners_xy(corners):
    """Sort 4 [x,y,z] corners into a non-crossing loop by angle around
    their own centroid (plan XY only; Z tags along unchanged) -- same
    technique vector_export.py's _order_quad_corners uses (mirrors
    Viewport.jsx's orderQuadCorners), since Rhino's Brep.Vertices order
    for a planar face isn't guaranteed to trace a boundary loop."""
    cx = sum(c[0] for c in corners) / len(corners)
    cy = sum(c[1] for c in corners) / len(corners)
    return sorted(corners, key=lambda c: math.atan2(c[1] - cy, c[0] - cx))


def _add_slab_plate(bm, slab):
    """One real slab plate as a thin hexahedron -- top face at the slab's
    real top_corners_ft, bottom face offset straight down in Z by
    thickness_ft. Same simplification vector_export.py's
    _build_slab_plate_mesh and Viewport.jsx's RealSlabPlate both already
    use/document: at real ramp tilt angles here (~1.7deg), the difference
    vs. an oriented-normal offset is sub-1/8" over a 1ft-thick plate --
    not worth a full oriented extrusion for a line-art silhouette."""
    ordered = _order_quad_corners_xy(slab["top_corners_ft"])
    thickness = slab["thickness_ft"]
    top = [mathutils.Vector(c) for c in ordered]
    bottom = [mathutils.Vector((c[0], c[1], c[2] - thickness)) for c in ordered]
    verts = [bm.verts.new(v) for v in top + bottom]
    # top(0,1,2,3) / bottom(4,5,6,7) -- same corner-order convention as
    # vector_export.py's _SLAB_PLATE_INDICES.
    quads = (
        (0, 1, 2, 3), (4, 7, 6, 5),
        (0, 4, 5, 1), (1, 5, 6, 2), (2, 6, 7, 3), (3, 7, 4, 0),
    )
    for q in quads:
        bm.faces.new([verts[i] for i in q])


def build_real_context_meshes(coll, real_columns, real_slabs, obj_name="mm_real_context"):
    """
    Real column/slab geometry -- built as simple native Blender primitives
    directly from real_geometry position/dimension data (real_columns[].x/
    z/diameter_ft/top_ft/bottom_ft, real_slabs[].top_corners_ft/
    thickness_ft), NOT by importing the heavy Rhino column_prototype_mesh
    OBJ. That OBJ is 1984 faces (non-watertight) per column and, instanced
    across ~294 real columns, was confirmed 2026-07-11 to be the actual
    dominant cause of a 27+ GiB crash in vector_export.py's trimesh-based
    hidden-line-removal attempt (99.3% of that pipeline's combined mesh) --
    a 12-sided cylinder per column and a thin quad plate per slab give
    everything needed (real silhouette/crease edges, real footprint) at a
    fraction of the vertex count, sidestepping that problem entirely on the
    Blender side too rather than importing the same heavy geometry here.

    2026-07-13: now also called unconditionally from main()'s primary
    --output path (see REAL_CONTEXT_COLLECTION_NAME below) -- the user
    consumes this OBJ standalone in Rhino, not alongside the live web
    viewport's own separate site_named.obj render, so the earlier "never
    leak real context into --output" exclusion (still true for the
    tunnel/secondary-entrance/metro-connector static context, which this
    function still does NOT include) no longer applies to columns/slabs
    for that workflow. Still also called from the --lineart-output/
    --include-real-context path below under its own default "mm_real_context"
    name -- harmless if both run in the same invocation (Blender just
    auto-suffixes the second object), not deduplicated since that combo is
    a rare, explicit opt-in.
    """
    mesh = bpy.data.meshes.new(obj_name)
    obj = bpy.data.objects.new(obj_name, mesh)
    coll.objects.link(obj)

    bm = bmesh.new()
    for col in real_columns:
        radius = col["diameter_ft"] / 2
        p0 = (col["x"], col["z"], col["bottom_ft"])
        p1 = (col["x"], col["z"], col["top_ft"])
        _add_cylinder(bm, p0, p1, radius, segments=12)
    for slab in real_slabs:
        _add_slab_plate(bm, slab)

    if bm.verts:
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(mesh)
    bm.free()


def build_ramp_meshes(coll, ramp_meshes):
    """Real spiral-core parking ramp geometry (2026-07-13) -- unlike columns/
    slabs above, this is already pre-tessellated real mesh data straight
    from Rhino (real_geometry.json's ramp_meshes: per-cluster list of
    per-level {vertices: flat [x,y,z,...], faces: flat [i0,i1,i2,...]}), so
    no primitive simplification is needed -- just build the real faces
    directly. One object per cluster (all of that cluster's levels
    concatenated), named mm_real_ramp_<cluster>."""
    for cluster_name, levels in ramp_meshes.items():
        obj_name = f"mm_real_ramp_{cluster_name}"
        mesh = bpy.data.meshes.new(obj_name)
        obj = bpy.data.objects.new(obj_name, mesh)
        coll.objects.link(obj)

        bm = bmesh.new()
        for level in levels:
            verts = level["vertices"]
            level_verts = [bm.verts.new((verts[i], verts[i + 1], verts[i + 2]))
                            for i in range(0, len(verts), 3)]
            faces = level["faces"]
            for i in range(0, len(faces), 3):
                bm.faces.new((level_verts[faces[i]], level_verts[faces[i + 1]], level_verts[faces[i + 2]]))
        if bm.verts:
            bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
        bm.to_mesh(mesh)
        bm.free()


def build_structural_meshes(coll, specs):
    """One mesh/object per StructuralElement kind, every instance of that
    kind concatenated into it -- same box/cylinder/hex-prism dispatch as
    blender_cockpit.py's version, reading dict keys (JSON) instead of
    dataclass attributes."""
    by_kind = {}
    for spec in specs:
        by_kind.setdefault(spec["kind"], []).append(spec)

    for kind in _ALL_STRUCT_KINDS:
        kind_specs = by_kind.get(kind, [])
        if not kind_specs:
            continue
        obj_name = f"mm_struct_{kind}"
        mesh = bpy.data.meshes.new(obj_name)
        obj = bpy.data.objects.new(obj_name, mesh)
        coll.objects.link(obj)

        bm = bmesh.new()
        for spec in kind_specs:
            if spec.get("x2_ft") is not None:
                p0 = (spec["x_ft"], spec["y_ft"], spec["z_top_ft"])
                p1 = (spec["x2_ft"], spec["y2_ft"], spec["z2_ft"])
                if kind in CIRCULATION_PATH_KINDS:
                    _add_ribbon(bm, p0, p1, spec.get("radius_ft") or 0.2, PATH_HALF_THICKNESS_FT)
                else:
                    _add_cylinder(bm, p0, p1, spec.get("radius_ft") or 0.2)
            elif kind in _HEX_KINDS:
                _add_hex_prism(bm, (spec["x_ft"], spec["y_ft"], spec["z_top_ft"]), spec.get("radius_ft") or 0.3,
                                spec["height_ft"], rotation_deg=spec.get("rotation_deg", 0.0))
            elif kind in _PANEL_KINDS:
                normal = (spec.get("normal_x") or 0.0, spec.get("normal_y") or 0.0, spec.get("normal_z") or 1.0)
                scale = spec.get("scale", 1.0)
                scale_y = spec.get("scale_y") or scale
                _add_panel(bm, (spec["x_ft"], spec["y_ft"], spec["z_top_ft"]), normal,
                           scale, scale_y, spec["height_ft"])
            elif kind in _VERTICAL_CYLINDER_KINDS:
                p0 = (spec["x_ft"], spec["y_ft"], spec["z_top_ft"] - spec["height_ft"])
                p1 = (spec["x_ft"], spec["y_ft"], spec["z_top_ft"])
                _add_cylinder(bm, p0, p1, spec.get("radius_ft") or 0.2)
            else:
                base_sx, base_sy = _PROTOTYPE_DIMS_FT.get(kind, (1.0, 1.0))
                scale = spec.get("scale", 1.0)
                # scale_y is only set for kinds needing an independent width
                # vs. depth (currently just building_mass) -- None
                # everywhere else, falling back to the original uniform
                # `scale` behavior.
                scale_y = spec.get("scale_y") or scale
                size = (base_sx * scale, base_sy * scale_y, spec["height_ft"])
                center = (spec["x_ft"], spec["y_ft"], spec["z_top_ft"] - spec["height_ft"] / 2)
                _add_rotated_box(bm, center, size, _rotation_for(spec))
        if bm.verts:
            bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
        bm.to_mesh(mesh)
        bm.free()


AXO_VIEW_DIR = mathutils.Vector((1.0, -1.0, 1.0)).normalized()


def _scene_bounds_world():
    """Combined world-space bounding box across every MESH object currently
    in the scene -- used to frame the Line Art camera, in place of
    blender_lineart_export.py's hardcoded SITE_W/SITE_L (this script has no
    separate site-dimension input; the built mesh's own extent is the real,
    self-contained source of truth, and this also correctly includes the
    structural framing's own footprint, not just the terrace)."""
    mins = [None, None, None]
    maxs = [None, None, None]
    for obj in bpy.context.scene.objects:
        if obj.type != 'MESH':
            continue
        for corner in obj.bound_box:
            world_co = obj.matrix_world @ mathutils.Vector(corner)
            for i in range(3):
                if mins[i] is None or world_co[i] < mins[i]:
                    mins[i] = world_co[i]
                if maxs[i] is None or world_co[i] > maxs[i]:
                    maxs[i] = world_co[i]
    return mathutils.Vector(mins), mathutils.Vector(maxs)


def _export_lineart_svg(gp_obj, cam_obj, output_path, margin=1.05, stroke_width_ft=None,
                         depth_band_labels=("near", "mid", "far")):
    """
    Writes the SVG ourselves from the baked GP stroke points instead of
    calling bpy.ops.wm.grease_pencil_export_svg -- that operator is
    confirmed broken in Blender 4.3+/5.0 for exactly this ortho-camera
    Line Art case (upstream bug #136312: exported width/height/viewBox
    doesn't match Output > Resolution; T86942: orthographic-camera line
    art export issues). Verified empirically 2026-07-08: the built-in
    exporter's declared viewBox and even its raw path coordinates carry a
    severe, non-uniform X/Y scale corruption (aspect ratios of 11:1 up to
    99:1 observed against a scene whose true camera-space aspect is
    ~1.7:1, confirmed via _scene_bounds_world()'s projected corners), and
    a naive post-hoc aspect-correction rescale still left long garbage
    "ray" strokes because the corruption isn't a single uniform affine
    error. Projecting each stroke's own points through the same cam_inv
    transform already trusted for ortho_scale sidesteps the exporter
    entirely and reproduces a correct, sane result (verified via a
    from-scratch Playwright render).

    Depth-band layering (2026-07-11): each stroke's average camera-space Z
    -- already computed here as part of the same cam_inv projection this
    function needs anyway, no extra pass required -- buckets it into one of
    len(depth_band_labels) evenly-spaced bands across the scene's actual
    depth range, each becoming its own SVG <g id="..."> group. Illustrator
    reads SVG groups as layers on import, giving a near/mid/far foreground/
    midground/background split (hand-drafting convention) instead of one
    flat pile of strokes. A perfectly flat scene from this exact angle
    (min depth == max depth, e.g. a true top-down plan view of an
    unexcavated terrace) puts everything in one band -- correct, not a bug.
    Blender cameras look down local -Z, so LESS-negative/more-positive
    camera-space Z is closer to the camera -- "near" is the band nearest
    max_z, "far" the band nearest min_z.
    """
    cam_inv = cam_obj.matrix_world.inverted()
    gp_mw = gp_obj.matrix_world
    stroke_entries = []  # (path_d, avg_z)
    min_x = min_y = max_x = max_y = None
    min_z = max_z = None
    for layer in gp_obj.data.layers:
        for frame in layer.frames:
            for stroke in frame.drawing.strokes:
                pts2d = []
                zs = []
                for pt in stroke.points:
                    world = gp_mw @ pt.position
                    local = cam_inv @ world
                    x, y = local.x, -local.y  # flip Y: camera-space up -> SVG down
                    pts2d.append((x, y))
                    zs.append(local.z)
                    min_x = x if min_x is None else min(min_x, x)
                    max_x = x if max_x is None else max(max_x, x)
                    min_y = y if min_y is None else min(min_y, y)
                    max_y = y if max_y is None else max(max_y, y)
                if len(pts2d) < 2:
                    continue
                avg_z = sum(zs) / len(zs)
                min_z = avg_z if min_z is None else min(min_z, avg_z)
                max_z = avg_z if max_z is None else max(max_z, avg_z)
                d = "M" + " L".join(f"{px:.4f},{py:.4f}" for px, py in pts2d)
                if stroke.cyclic:
                    d += " Z"
                stroke_entries.append((d, avg_z))

    if min_x is None:
        raise ValueError("Line Art bake produced zero strokes with >=2 points -- nothing to export")

    w = (max_x - min_x) * margin
    h = (max_y - min_y) * margin
    cx, cy = (min_x + max_x) / 2, (min_y + max_y) / 2
    vb_x, vb_y = cx - w / 2, cy - h / 2
    if stroke_width_ft is None:
        stroke_width_ft = max(w, h) / 1500.0

    n_bands = len(depth_band_labels)
    z_range = max_z - min_z
    banded = {label: [] for label in depth_band_labels}
    for d, avg_z in stroke_entries:
        if z_range < 1e-9:
            band_idx = 0
        else:
            frac = (max_z - avg_z) / z_range  # 0 at max_z (nearest) -> 1 at min_z (farthest)
            band_idx = min(n_bands - 1, int(frac * n_bands))
        banded[depth_band_labels[band_idx]].append(d)

    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<svg xmlns="http://www.w3.org/2000/svg" version="1.1" '
        f'viewBox="{vb_x:.4f} {vb_y:.4f} {w:.4f} {h:.4f}" '
        f'width="{w:.4f}" height="{h:.4f}">',
    ]
    for label in depth_band_labels:
        ds = banded[label]
        if not ds:
            continue
        lines.append(f'<g id="{label}" fill="none" stroke="black" stroke-width="{stroke_width_ft:.5f}" '
                      f'stroke-linecap="round" stroke-linejoin="round">')
        lines.extend(f'<path d="{d}"/>' for d in ds)
        lines.append("</g>")
    lines.append("</svg>")

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def build_line_art(output_path, view_dir=None):
    """
    Grease Pencil Line Art export against whatever mesh objects are
    currently in the scene -- port of blender/blender_lineart_export.py's
    proven pipeline (see that module's docstring for the two real bugs its
    approach fixes: manual GP+modifier baking to zero strokes, and
    world-space instead of camera-space ortho_scale), adapted to operate
    on an in-memory-built scene instead of importing an OBJ from disk, and
    to use LINEART_SCENE (every mesh contributes) instead of LINEART_OBJECT
    (a single source mesh) since this scene has many structural-kind
    objects alongside the terrace.

    `view_dir`: camera direction (any 3-tuple/Vector, normalized here) --
    defaults to the same fixed isometric AXO_VIEW_DIR vector_export.py
    also uses (2026-07-11: parameterized so a live browser camera angle
    can drive this instead of always the one hardcoded direction; the
    framing math below was already direction-agnostic, deriving ortho_scale
    from the scene bounds projected into camera space rather than any
    fixed world-space assumption).

    SVG output is written by _export_lineart_svg() above, not Blender's own
    grease_pencil_export_svg operator -- see that function's docstring for
    why (a confirmed upstream Blender bug corrupts that operator's output
    for orthographic-camera Line Art).
    """
    view_dir = mathutils.Vector(view_dir).normalized() if view_dir else AXO_VIEW_DIR

    mins, maxs = _scene_bounds_world()
    center = (mins + maxs) / 2.0
    site_span = max(maxs.x - mins.x, maxs.y - mins.y, maxs.z - mins.z, 1.0)

    cam_data = bpy.data.cameras.new("LineArtCam")
    cam_data.type = 'ORTHO'
    cam_data.clip_start = 0.1
    cam_data.clip_end = site_span * 10
    cam_obj = bpy.data.objects.new("LineArtCam", cam_data)
    bpy.context.collection.objects.link(cam_obj)
    cam_obj.location = center + view_dir * site_span * 2
    direction = center - cam_obj.location
    cam_obj.rotation_euler = direction.to_track_quat('-Z', 'Y').to_euler()
    bpy.context.scene.camera = cam_obj

    # ortho_scale from the SCENE bbox projected into camera space, not
    # world-space dimensions -- an isometric-ish view's camera-space extent
    # can be much larger than any single world-space dimension (confirmed
    # empirically in blender_lineart_export.py's own rehearsal).
    bpy.context.view_layer.update()
    cam_inv = cam_obj.matrix_world.inverted()
    corners = [
        mathutils.Vector((x, y, z))
        for x in (mins.x, maxs.x) for y in (mins.y, maxs.y) for z in (mins.z, maxs.z)
    ]
    local = [cam_inv @ c for c in corners]
    x_span = max(c.x for c in local) - min(c.x for c in local)
    y_span = max(c.y for c in local) - min(c.y for c in local)
    res_x, res_y = bpy.context.scene.render.resolution_x, bpy.context.scene.render.resolution_y
    margin = 1.2
    cam_data.ortho_scale = margin * max(x_span, y_span * res_x / res_y)

    bpy.ops.object.select_all(action='DESELECT')
    bpy.ops.object.grease_pencil_add(type='LINEART_SCENE', location=(0, 0, 0))
    gp_obj = bpy.context.object
    gp_obj.name = "SiteLineArt"
    mod = gp_obj.modifiers["Lineart"]
    mod.source_camera = cam_obj
    mod.crease_threshold = math.radians(25)

    bpy.context.scene.frame_start = 1
    bpy.context.scene.frame_end = 1
    bpy.context.scene.frame_set(1)

    bpy.ops.object.select_all(action='DESELECT')
    gp_obj.select_set(True)
    bpy.context.view_layer.objects.active = gp_obj
    bpy.ops.object.lineart_bake_strokes()

    _export_lineart_svg(gp_obj, cam_obj, output_path)
    print(f"LINEART_DONE:{output_path}")


def main():
    argv = sys.argv
    argv = argv[argv.index("--") + 1:] if "--" in argv else []

    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, help="Path to the rebuild JSON (real_columns/real_slabs/ramp_meshes/structural/voxel_ft)")
    parser.add_argument("--output", required=True, help="Path to write the built OBJ to")
    parser.add_argument("--lineart-output", default=None, help="Optional path to also write a Grease Pencil Line Art SVG to")
    parser.add_argument("--view-dir", default=None,
                         help="Comma-separated x,y,z camera direction for Line Art (Z-up site-local frame, "
                              "same convention as vector_export.py's AXO_VIEW_DIR) -- default: that same "
                              "fixed isometric direction")
    parser.add_argument("--include-real-context", action="store_true",
                         help="Also line-art the real columns/slabs (payload's real_columns/real_slabs, if "
                              "present) as lightweight native primitives -- vector-export use only, NOT "
                              "included in --output's OBJ (which deliberately excludes static context to "
                              "avoid double-rendering the live viewport's own separate real-context display)")
    args = parser.parse_args(argv)

    with open(args.input) as f:
        payload = json.load(f)

    bpy.ops.wm.read_factory_settings(use_empty=True)

    # 2026-07-13: real slab/column/ramp geometry replaces the old box-per-
    # voxel terrace mesh here -- the voxel boxes never matched the actual
    # parking structure slabs as they exist in the Rhino file, and this OBJ
    # is now consumed standalone in Rhino (not alongside the live web
    # viewport, which is the only reason real context used to be excluded
    # from this export -- see build_real_context_meshes's docstring).
    real_coll = bpy.data.collections.new(REAL_CONTEXT_COLLECTION_NAME)
    bpy.context.scene.collection.children.link(real_coll)
    build_real_context_meshes(
        real_coll, payload.get("real_columns", []), payload.get("real_slabs", []),
        obj_name=REAL_CONTEXT_COLLECTION_NAME)

    if payload.get("ramp_meshes"):
        ramp_coll = bpy.data.collections.new(REAL_RAMPS_COLLECTION_NAME)
        bpy.context.scene.collection.children.link(ramp_coll)
        build_ramp_meshes(ramp_coll, payload["ramp_meshes"])

    struct_coll = bpy.data.collections.new(STRUCTURAL_COLLECTION_NAME)
    bpy.context.scene.collection.children.link(struct_coll)
    build_structural_meshes(struct_coll, payload["structural"])

    if "canopy_height_matrix" in payload:
        # 2026-07-16: this key no longer appears in real payloads --
        # rebuild() stopped computing canopy entirely (see logic/
        # pershing_api.py), and App.jsx's dataForBlenderExport() merges the
        # new canopy_panel/canopy_column_trunk/canopy_column_branch specs
        # straight into payload["structural"] instead (handled generically
        # by build_structural_meshes above via _PANEL_KINDS/_add_panel, no
        # special-casing needed there). This branch is effectively dead on
        # any current payload; left in place only in case an old saved
        # payload (from before this date) is ever replayed through this
        # script. Own named collection (2026-07-13), matching
        # STRUCTURAL_COLLECTION_NAME/REAL_CONTEXT_COLLECTION_NAME/
        # REAL_RAMPS_COLLECTION_NAME above -- consistent per-layer
        # organization for anyone opening the intermediate scene in
        # Blender itself (the exported OBJ's own per-object "o" naming is
        # what actually matters for isolating layers in Rhino --
        # collections don't carry through OBJ export).
        canopy_coll = bpy.data.collections.new(CANOPY_COLLECTION_NAME)
        bpy.context.scene.collection.children.link(canopy_coll)
        canopy_mesh = bpy.data.meshes.new(CANOPY_OBJ_NAME)
        canopy_obj = bpy.data.objects.new(CANOPY_OBJ_NAME, canopy_mesh)
        canopy_coll.objects.link(canopy_obj)
        build_canopy_mesh(canopy_mesh, payload["canopy_height_matrix"], payload["voxel_ft"],
                           payload.get("canopy_puncture_mask"))

    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    bpy.ops.object.select_all(action='SELECT')
    # up_axis='Z', forward_axis='Y' -- same convention this project's other
    # OBJ import/export calls already use (see blender_cockpit.py's
    # import_static_context docstring): keeps the exported vertex data as
    # literal real-feet, Z-up, matching what the live JSON/Three.js
    # viewport already assumes, with no axis remap either direction.
    bpy.ops.wm.obj_export(filepath=args.output, up_axis='Z', forward_axis='Y', export_selected_objects=True)
    print(f"HEADLESS_BUILD_DONE:{args.output}")

    if args.lineart_output:
        if args.include_real_context:
            # 2026-07-13: real columns/slabs are now ALSO already in the
            # scene unconditionally (see REAL_CONTEXT_COLLECTION_NAME
            # above) -- this duplicates them into a second object under the
            # historical "mm_real_context" name. Harmless (Line Art bakes
            # off the whole scene either way, and OBJ export already
            # finished above) but redundant whenever both this flag and the
            # primary export run together; left as-is rather than touching
            # this flag's own opt-in contract for --lineart-output-only
            # callers.
            lineart_real_coll = bpy.data.collections.new("mm_real_context")
            bpy.context.scene.collection.children.link(lineart_real_coll)
            build_real_context_meshes(
                lineart_real_coll, payload.get("real_columns", []), payload.get("real_slabs", []))
        view_dir = tuple(float(v) for v in args.view_dir.split(",")) if args.view_dir else None
        build_line_art(args.lineart_output, view_dir=view_dir)


if __name__ == "__main__":
    main()
