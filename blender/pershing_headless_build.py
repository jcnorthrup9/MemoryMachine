"""
blender/pershing_headless_build.py
-----------------------------------
Headless Blender scene builder for the Pershing hybrid pipeline.

Ingests the SAME voxel/structural JSON payload the browser already gets
from POST /api/pershing/rebuild (logic/pershing_api.py) -- does NOT
re-run TerracingEngine, does NOT need bpy paint-canvas state. This is the
headless counterpart to blender_cockpit.py's rebuild_all() /
build_terrace_mesh() / build_structural_meshes(), stripped of the live-paint
UI (the browser's PaintOverlay.jsx already owns that job) and re-pointed at
CLI args instead of hardcoded D:\\MemoryMachine paths, so it stays portable
across the Syncthing-synced machines this repo lives on.

Deliberately does NOT re-import blender_cockpit.py's static-context import
or axo-view/mirror setup: that mirror is specific to the cockpit's own fixed
presentation camera. This export instead stays in the same raw real-feet,
Z-up convention the live JSON/Three.js viewport already uses (see
Viewport.jsx's toThree() and StaticContext.jsx's own transform) -- baking
in the axo mirror here would silently put this mesh in a different
coordinate convention than everything else the frontend loads. Static
context (columns/tunnel/entrance/ramps) is not re-embedded either -- the
frontend already renders that once, separately, from site_named.obj;
duplicating it here would double-render it.

Run headless:
    blender --background --python pershing_headless_build.py -- \
        --input <voxel/structural JSON> --output <obj path> \
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

TERRACE_OBJ_NAME = "cockpit_terrace"
STRUCTURAL_COLLECTION_NAME = "mm_structural_frame"

# Cross-section (plan) footprint in feet for each box-shaped
# StructuralElement.kind -- mirrors blender_cockpit.py's _PROTOTYPE_DIMS_FT
# exactly (see that file for the per-kind rationale). Cylinder/hex/disc
# kinds don't use this dict; their geometry comes from radius_ft (and, for
# two-point kinds, x2/y2/z2_ft) instead.
_PROTOTYPE_DIMS_FT = {
    "concrete_floor_block": (9.0, 9.0, 8.0 / 12.0),
    "concrete_retaining_block": (3.0, 3.0, 8.0 / 12.0),
    "steel_collar_sleeve": (2.0, 2.0, 1.0),
    "gusset_plate": (1.5, 0.1, 1.5),
    "steel_strap_band": (2.2, 0.15, 1.0),
    "footing_shoe": (1.3, 1.3, 1.0),
    "glulam_post": (1.0, 1.0, 1.0),
    "water_plane": (8.0, 8.0, 0.2),
    "water_cascade_block": (4.0, 1.5, 1.0),
    "misting_line": (0.15, 0.15, 1.0),
    "bench_assembly": (6.0, 2.0, 1.5),
    "restroom_pod": (10.0, 8.0, 8.0),
    "fountain": (4.0, 4.0, 3.0),
    # Unit footprint -- BuildingMassEngine passes real width/depth via
    # scale/scale_y rather than a fixed prototype size like every other
    # box kind here, since building footprints vary per instance.
    "building_mass": (1.0, 1.0, 1.0),
}
_VERTICAL_CYLINDER_KINDS = {"steel_bolt", "bolt_flange_plate", "tree_trunk"}
_HEX_KINDS = {"steel_turnbuckle", "tree_canopy"}
_ALL_STRUCT_KINDS = (
    tuple(_PROTOTYPE_DIMS_FT) + tuple(_VERTICAL_CYLINDER_KINDS) + tuple(_HEX_KINDS)
    + ("steel_strut", "steel_tie_rod", "knee_brace", "timber_beam")
)

_BOX_FACES = ((0, 1, 2, 3), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7))


def _add_box(bm, cx, cy, cz, sx, sy, sz):
    hx, hy, hz = sx / 2, sy / 2, sz / 2
    coords = (
        (cx - hx, cy - hy, cz - hz), (cx + hx, cy - hy, cz - hz),
        (cx + hx, cy + hy, cz - hz), (cx - hx, cy + hy, cz - hz),
        (cx - hx, cy - hy, cz + hz), (cx + hx, cy - hy, cz + hz),
        (cx + hx, cy + hy, cz + hz), (cx - hx, cy + hy, cz + hz),
    )
    verts = [bm.verts.new(c) for c in coords]
    for f in _BOX_FACES:
        bm.faces.new([verts[i] for i in f])


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


def build_terrace_mesh(mesh, voxel_ft, max_canyon_depth_ft, voxels):
    """Box-per-voxel port of blender_cockpit.py's build_terrace_mesh, taking
    plain scalars/dicts instead of a live TerracingEngine instance -- the
    JSON payload already carries everything this needs (z_ft/gx/gy per
    voxel, voxel_ft, max_canyon_depth_ft), so no engine object required."""
    bm = bmesh.new()
    floor_z = -(max_canyon_depth_ft + 10.0)
    for v in voxels:
        top = v["z_ft"]
        height = top - floor_z
        if height <= 0:
            continue
        cx = v["gx"] * voxel_ft + voxel_ft / 2
        cy = v["gy"] * voxel_ft + voxel_ft / 2
        cz = top - height / 2
        _add_box(bm, cx, cy, cz, voxel_ft, voxel_ft, height)
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
                _add_cylinder(bm, (spec["x_ft"], spec["y_ft"], spec["z_top_ft"]),
                               (spec["x2_ft"], spec["y2_ft"], spec["z2_ft"]), spec.get("radius_ft") or 0.2)
            elif kind in _HEX_KINDS:
                _add_hex_prism(bm, (spec["x_ft"], spec["y_ft"], spec["z_top_ft"]), spec.get("radius_ft") or 0.3,
                                spec["height_ft"], rotation_deg=spec.get("rotation_deg", 0.0))
            elif kind in _VERTICAL_CYLINDER_KINDS:
                p0 = (spec["x_ft"], spec["y_ft"], spec["z_top_ft"] - spec["height_ft"])
                p1 = (spec["x_ft"], spec["y_ft"], spec["z_top_ft"])
                _add_cylinder(bm, p0, p1, spec.get("radius_ft") or 0.2)
            else:
                base_sx, base_sy, _ = _PROTOTYPE_DIMS_FT.get(kind, (1.0, 1.0, 1.0))
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


def _export_lineart_svg(gp_obj, cam_obj, output_path, margin=1.05, stroke_width_ft=None):
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
    """
    cam_inv = cam_obj.matrix_world.inverted()
    gp_mw = gp_obj.matrix_world
    path_strs = []
    min_x = min_y = max_x = max_y = None
    for layer in gp_obj.data.layers:
        for frame in layer.frames:
            for stroke in frame.drawing.strokes:
                pts2d = []
                for pt in stroke.points:
                    world = gp_mw @ pt.position
                    local = cam_inv @ world
                    x, y = local.x, -local.y  # flip Y: camera-space up -> SVG down
                    pts2d.append((x, y))
                    min_x = x if min_x is None else min(min_x, x)
                    max_x = x if max_x is None else max(max_x, x)
                    min_y = y if min_y is None else min(min_y, y)
                    max_y = y if max_y is None else max(max_y, y)
                if len(pts2d) < 2:
                    continue
                d = "M" + " L".join(f"{px:.4f},{py:.4f}" for px, py in pts2d)
                if stroke.cyclic:
                    d += " Z"
                path_strs.append(d)

    if min_x is None:
        raise ValueError("Line Art bake produced zero strokes with >=2 points -- nothing to export")

    w = (max_x - min_x) * margin
    h = (max_y - min_y) * margin
    cx, cy = (min_x + max_x) / 2, (min_y + max_y) / 2
    vb_x, vb_y = cx - w / 2, cy - h / 2
    if stroke_width_ft is None:
        stroke_width_ft = max(w, h) / 1500.0

    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<svg xmlns="http://www.w3.org/2000/svg" version="1.1" '
        f'viewBox="{vb_x:.4f} {vb_y:.4f} {w:.4f} {h:.4f}" '
        f'width="{w:.4f}" height="{h:.4f}">',
        f'<g fill="none" stroke="black" stroke-width="{stroke_width_ft:.5f}" '
        f'stroke-linecap="round" stroke-linejoin="round">',
    ]
    lines.extend(f'<path d="{d}"/>' for d in path_strs)
    lines.append("</g></svg>")

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def build_line_art(output_path):
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

    SVG output is written by _export_lineart_svg() above, not Blender's own
    grease_pencil_export_svg operator -- see that function's docstring for
    why (a confirmed upstream Blender bug corrupts that operator's output
    for orthographic-camera Line Art).
    """
    mins, maxs = _scene_bounds_world()
    center = (mins + maxs) / 2.0
    site_span = max(maxs.x - mins.x, maxs.y - mins.y, maxs.z - mins.z, 1.0)

    cam_data = bpy.data.cameras.new("LineArtCam")
    cam_data.type = 'ORTHO'
    cam_data.clip_start = 0.1
    cam_data.clip_end = site_span * 10
    cam_obj = bpy.data.objects.new("LineArtCam", cam_data)
    bpy.context.collection.objects.link(cam_obj)
    cam_obj.location = center + AXO_VIEW_DIR * site_span * 2
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
    parser.add_argument("--input", required=True, help="Path to the rebuild JSON (voxels/structural/voxel_ft/max_canyon_depth_ft)")
    parser.add_argument("--output", required=True, help="Path to write the built OBJ to")
    parser.add_argument("--lineart-output", default=None, help="Optional path to also write a Grease Pencil Line Art SVG to")
    args = parser.parse_args(argv)

    with open(args.input) as f:
        payload = json.load(f)

    bpy.ops.wm.read_factory_settings(use_empty=True)

    terrace_mesh = bpy.data.meshes.new(TERRACE_OBJ_NAME)
    terrace_obj = bpy.data.objects.new(TERRACE_OBJ_NAME, terrace_mesh)
    bpy.context.collection.objects.link(terrace_obj)
    build_terrace_mesh(terrace_mesh, payload["voxel_ft"], payload["max_canyon_depth_ft"], payload["voxels"])

    struct_coll = bpy.data.collections.new(STRUCTURAL_COLLECTION_NAME)
    bpy.context.scene.collection.children.link(struct_coll)
    build_structural_meshes(struct_coll, payload["structural"])

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
        build_line_art(args.lineart_output)


if __name__ == "__main__":
    main()
