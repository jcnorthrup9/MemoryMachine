"""
Memory Machine -- Blender live-cockpit proof-of-concept.

Smallest possible test of the "Blender becomes the live control cockpit"
architecture decision (2026-07-04, see PIPELINE_STATUS_AND_NEXT_STEPS.md):
imports terracing_engine.py directly into Blender's own Python, builds the
terrace mesh once from the real (already-verified) Pershing data + the one
real sketch on hand, and exposes a single Scene property (sketch_alpha) that
reruns the real engine and rebuilds the mesh in-viewport when moved.

Deliberately does NOT import vector_export.py -- that module needs trimesh
(and, for HLR, embreex), which are a much heavier ask for Blender's bundled
Python than this POC needs. The terrace box mesh is built directly with
bmesh here (a port of vector_export.build_terraced_solid's box-per-voxel
logic, minus the trimesh dependency). Static context (columns/tunnel/
entrance/ramps) is instead imported once from the already-exported
site_named.obj, for visual reference only -- it does not rebuild.

sketch_weights are precomputed by precompute_sketch_cache.py (run in the
normal project venv, which has PIL/svgpathtools) and loaded here as a plain
JSON nested list -- no numpy/PIL needed inside Blender at all. That JSON
cache is only the STARTING baseline; live painting (see setup_paint_canvas
below) overwrites it via bake_paint_canvas whenever the user paints and hits
"Bake Painted Sketch".

Run via BlenderMCP's execute_blender_code, or headless:
    blender --background --python blender_cockpit.py
(headless won't show the live slider UI, but will still build the mesh once
and print rebuild timing -- useful to sanity-check performance in isolation.)
"""
import json
import math
import os
import sys
import time

import bmesh
import bpy
import mathutils
import numpy as np

REPO_ROOT = r"D:\MemoryMachine"
REAL_GEOMETRY_PATH = os.path.join(REPO_ROOT, "PershingMetabolizer_Prototype", "real_geometry.json")
SKETCH_CACHE_PATH = os.path.join(REPO_ROOT, "outputs", "cockpit", "sketch_weights_cache.json")
CONTEXT_OBJ_PATH = os.path.join(REPO_ROOT, "outputs", "vector_export_test", "site_named.obj")

# Same axonometric convention as vector_export.py's AXO_VIEW_DIR / _axo_basis /
# mirror_mesh_y -- numerically verified 2026-07-05 (entrance projects to the
# largest +u of any reference point, 5TH ST near-topmost +v) to put Hill St /
# the Metro entrance on the right. Duplicated here in plain numpy rather than
# imported from vector_export.py, which pulls in trimesh -- too heavy an
# import just to reuse two small constants/functions in Blender's Python.
AXO_VIEW_DIR = np.array([1.0, -1.0, 1.0])
AXO_VIEW_DIR /= np.linalg.norm(AXO_VIEW_DIR)


def _axo_basis(view_dir):
    world_up = np.array([0.0, 0.0, 1.0])
    u = np.cross(world_up, view_dir)
    u /= np.linalg.norm(u)
    v = np.cross(view_dir, u)
    v /= np.linalg.norm(v)
    return u, v

if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from terracing_engine import (  # noqa: E402
    TerracingEngine, StructuralFramingEngine, TypologyAssetEngine, STRUCTURAL_BAY_FT, KIND_REGISTRY)
# amenity_deficit.py only needs the stdlib csv module -- unlike
# sketch_weight_mapper.py (PIL/svgpathtools), safe to import directly in
# Blender's bundled Python, no precompute-cache step needed.
from amenity_deficit import load_deficit_hotspots_from_csv, find_latest_csv  # noqa: E402
# sketch_weight_mapper.py's find_latest_sketch is pure os.listdir/getmtime --
# safe to import at module level even though the rest of that module needs
# PIL/svgpathtools (those imports are local to the functions that need them,
# not at module scope, so importing the module itself doesn't require them).
from sketch_weight_mapper import find_latest_sketch  # noqa: E402

with open(REAL_GEOMETRY_PATH) as f:
    REAL_GEOMETRY = json.load(f)
with open(SKETCH_CACHE_PATH) as f:
    _cache = json.load(f)
SKETCH_WEIGHTS = _cache["weights"]
# May be absent in an older cache file (predates the hardscape toggle) --
# default to an all-False grid rather than erroring, same shape as weights.
HARDSCAPE_MASK = _cache.get("hardscape_mask") or [[False] * len(SKETCH_WEIGHTS[0]) for _ in SKETCH_WEIGHTS]

# Programmatic Typology Mixing Engine inputs (New Feature Directives section
# 4) -- Water/Shade, Greenscape, Amenity/Resting. Bootstrap empty (same
# pattern HARDSCAPE_MASK used before real hardscape sketch data existed);
# setup_paint_canvas/bake_paint_canvas below populate these live once the
# designer paints the corresponding category and hits Bake.
def _empty_mask():
    return [[False] * len(SKETCH_WEIGHTS[0]) for _ in SKETCH_WEIGHTS]

WATER_SHADE_MASK = _empty_mask()
GREENSCAPE_MASK = _empty_mask()
AMENITY_RESTING_MASK = _empty_mask()

AMENITY_CSV_PATH = find_latest_csv()
SKETCH_IMAGE_PATH = find_latest_sketch()

# Slider bound for mm_canyon_width -- how many 27ft bays span the site's
# short axis, derived from the same real site dims StructuralFramingEngine
# uses, so the N-panel can never ask for a canyon wider than the real site.
NX_BAYS = max(1, round(REAL_GEOMETRY["site"]["width_ft"] / STRUCTURAL_BAY_FT))

TERRACE_OBJ_NAME = "cockpit_terrace"
STRUCTURAL_COLLECTION_NAME = "mm_structural_frame"

# Cross-section (plan) footprint in feet for each box-shaped
# StructuralElement.kind -- height comes from the spec itself
# (spec.height_ft), not from here. Cylinder/hex/disc kinds (struts,
# tie-rods, knee braces, bolts, turnbuckles, bolt-flange plates) don't use
# this dict -- their geometry comes from spec.radius_ft (and, for two-point
# kinds, spec.x2/y2/z2_ft) instead; see build_structural_meshes.
#
# At dense Shoring Density in WOOD mode a single rebuild can mean tens of
# thousands of instances; one bpy.data.objects.new() per instance was
# measured at 15+ seconds/rebuild (object/depsgraph overhead, not mesh
# memory) -- violates the "hyper-responsive slider drag" requirement. Fixed
# by reusing the same technique build_terrace_mesh already uses for voxels:
# concatenate every instance of a kind into ONE bmesh/object per kind, same
# pattern, same speed.
#
# Derived from KIND_REGISTRY (2026-07-10 consolidation pass -- terracing_
# engine.py's shared import of frontend/src/kindRegistry.json), replacing a
# hand-maintained copy that had independently drifted from Viewport.jsx's:
# it never picked up circulation_network.py's footpath/ramp/escalator kinds
# or the typology tree_trunk/tree_canopy/building_mass kinds, which meant
# build_structural_meshes (below, iterates _ALL_STRUCT_KINDS rather than
# whatever's actually in a given rebuild's specs) silently dropped those
# kinds' meshes in this Blender-side tool even though the live web app
# rendered them fine. Deriving from the shared registry fixes that gap.
_PROTOTYPE_DIMS_FT = {
    kind: tuple(entry["dims_ft"]) for kind, entry in KIND_REGISTRY["kinds"].items() if entry["shape"] == "box"
}
# Two-point kinds are detected at runtime (spec.x2_ft is not None); these
# sets are only for the remaining single-point non-box kinds.
_VERTICAL_CYLINDER_KINDS = {
    kind for kind, entry in KIND_REGISTRY["kinds"].items() if entry["shape"] == "vertical_cylinder"
}
_HEX_KINDS = {kind for kind, entry in KIND_REGISTRY["kinds"].items() if entry["shape"] == "hex"}
# Every kind that can ever appear -- iterated even when a given rebuild
# produces zero of a kind, so switching STEEL <-> WOOD (or dropping a
# connection condition) correctly empties that kind's mesh instead of
# leaving stale geometry from the last rebuild.
_ALL_STRUCT_KINDS = tuple(
    kind for kind, entry in KIND_REGISTRY["kinds"].items() if entry["shape"] != "real"
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
    # Only gusset_plate still uses a rotated-box path (faced along the
    # strut's bearing angle, about Z) -- knee braces and tie-rods are true
    # two-point cylinders now, so they no longer need an angle guess here.
    if spec.kind == "gusset_plate":
        return mathutils.Matrix.Rotation(math.radians(spec.rotation_deg), 4, 'Z').to_3x3()
    return mathutils.Matrix.Identity(3)


def _add_cylinder(bm, p0, p1, radius, segments=8):
    """Real capped cylinder between two 3D points -- used for pipe struts,
    tie-rods, knee braces (all two-point) and, with p0==p1's xy and a
    vertical p0->p1, bolts/bolt-flange plates (single-point, "vertical
    cylinder" case) so none of these connections are a rotated-box guess at
    the true diagonal."""
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
    """Elongated hexagonal prism -- the structural turnbuckle at the dead
    center of each STEEL X-brace."""
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


def build_structural_meshes(coll, specs):
    """One mesh/object per StructuralElement kind, every instance of that
    kind concatenated into it -- boxes, cylinders, or a hex prism depending
    on kind, but always merged into a single mesh, never one Blender object
    per instance (object/depsgraph overhead doesn't scale -- see
    _PROTOTYPE_DIMS_FT comment above)."""
    by_kind = {}
    for spec in specs:
        by_kind.setdefault(spec.kind, []).append(spec)

    for kind in _ALL_STRUCT_KINDS:
        obj_name = f"mm_struct_{kind}"
        obj = bpy.data.objects.get(obj_name)
        if obj is None:
            mesh = bpy.data.meshes.new(obj_name)
            obj = bpy.data.objects.new(obj_name, mesh)
            coll.objects.link(obj)
        else:
            mesh = obj.data
            mesh.clear_geometry()

        bm = bmesh.new()
        for spec in by_kind.get(kind, []):
            if spec.x2_ft is not None:
                _add_cylinder(bm, (spec.x_ft, spec.y_ft, spec.z_top_ft),
                               (spec.x2_ft, spec.y2_ft, spec.z2_ft), spec.radius_ft or 0.2)
            elif kind in _HEX_KINDS:
                _add_hex_prism(bm, (spec.x_ft, spec.y_ft, spec.z_top_ft), spec.radius_ft or 0.3,
                                spec.height_ft, rotation_deg=spec.rotation_deg)
            elif kind in _VERTICAL_CYLINDER_KINDS:
                p0 = (spec.x_ft, spec.y_ft, spec.z_top_ft - spec.height_ft)
                p1 = (spec.x_ft, spec.y_ft, spec.z_top_ft)
                _add_cylinder(bm, p0, p1, spec.radius_ft or 0.2)
            else:
                base_sx, base_sy = _PROTOTYPE_DIMS_FT.get(kind, (1.0, 1.0))
                size = (base_sx * spec.scale, base_sy * spec.scale, spec.height_ft)
                center = (spec.x_ft, spec.y_ft, spec.z_top_ft - spec.height_ft / 2)
                _add_rotated_box(bm, center, size, _rotation_for(spec))
        if bm.verts:
            bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
        bm.to_mesh(mesh)
        bm.free()


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


def build_terrace_mesh(mesh, engine, voxels):
    """
    Port of vector_export.build_terraced_solid to bmesh, box-per-voxel, no
    trimesh/CSG needed -- boxes aren't unioned into one watertight solid,
    just concatenated into one mesh, same as trimesh.util.concatenate does
    for the "clean" export pass.
    """
    bm = bmesh.new()
    vf = engine.voxel_ft
    floor_z = -(engine.max_canyon_depth_ft + 10.0)

    for v in voxels:
        top = v.z_ft
        height = top - floor_z
        if height <= 0:
            continue
        cx = v.gx * vf + vf / 2
        cy = v.gy * vf + vf / 2
        cz = top - height / 2
        _add_box(bm, cx, cy, cz, vf, vf, height)

    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(mesh)
    bm.free()


def rebuild_all(scene):
    """
    One canyon, one rebuild. Canyon Width/Depth are not a second excavation
    -- they parameterize the same TerracingEngine run that Sketch Alpha /
    Hardscape / Amenity already drive (transit_falloff_ft and
    max_canyon_depth_ft respectively, see below), so every slider has to
    trigger this single pass: the terrace mesh, the slab-harvest tonnage,
    and the structural framing all read the one real voxel field.
    """
    t0 = time.time()
    hardscape_regions = [{"mask": HARDSCAPE_MASK}] if scene.mm_hardscape_enabled else None

    deficit_hotspots = None  # None -> TerracingEngine falls back to its own DEFAULT_DEFICIT_HOTSPOTS
    if scene.mm_use_real_amenity_data and AMENITY_CSV_PATH:
        deficit_hotspots = load_deficit_hotspots_from_csv(
            AMENITY_CSV_PATH, REAL_GEOMETRY["site"]["width_ft"], REAL_GEOMETRY["site"]["length_ft"])

    # Canyon Width (bays) -> transit_falloff_ft: bays convert straight to
    # feet, the entrance attractor's real spatial reach -- wider slider,
    # farther the attractor's influence spreads, wider the real excavated
    # footprint. Canyon Depth (levels) -> max_canyon_depth_ft, still hard-
    # capped at the real column height so no voxel ever floats past its
    # real unbraced length regardless of slider position.
    transit_falloff_ft = scene.mm_canyon_width * STRUCTURAL_BAY_FT
    max_canyon_depth_ft = min(scene.mm_canyon_depth * 9.0, REAL_GEOMETRY.get("column_height_ft", 30.0))

    engine = TerracingEngine(REAL_GEOMETRY, sketch_weights=SKETCH_WEIGHTS, sketch_alpha=scene.mm_sketch_alpha,
                              hardscape_regions=hardscape_regions, deficit_hotspots=deficit_hotspots,
                              transit_falloff_ft=transit_falloff_ft, max_canyon_depth_ft=max_canyon_depth_ft,
                              water_shade_regions=[{"mask": WATER_SHADE_MASK}],
                              greenscape_regions=[{"mask": GREENSCAPE_MASK}],
                              amenity_resting_regions=[{"mask": AMENITY_RESTING_MASK}])
    voxels = engine.run(phase=3)

    obj = bpy.data.objects.get(TERRACE_OBJ_NAME)
    if obj is None:
        mesh = bpy.data.meshes.new(TERRACE_OBJ_NAME)
        obj = bpy.data.objects.new(TERRACE_OBJ_NAME, mesh)
        bpy.context.collection.objects.link(obj)
    else:
        mesh = obj.data
        mesh.clear_geometry()

    build_terrace_mesh(mesh, engine, voxels)
    mesh.update()

    structural = StructuralFramingEngine(
        REAL_GEOMETRY, engine, material_mode=scene.mm_material_mode, shoring_density=scene.mm_shoring_density)
    result = structural.run()

    coll = bpy.data.collections.get(STRUCTURAL_COLLECTION_NAME)
    if coll is None:
        coll = bpy.data.collections.new(STRUCTURAL_COLLECTION_NAME)
        bpy.context.scene.collection.children.link(coll)

    typology = TypologyAssetEngine(REAL_GEOMETRY, engine)
    all_specs = result["harvested_blocks"] + result["structural"] + typology.run()
    build_structural_meshes(coll, all_specs)

    scene.mm_slab_harvest_label = f"Slab Material Harvested: {result['slab_harvest_tons']:.0f} Tons"
    hardscape_note = "on" if scene.mm_hardscape_enabled else "off"
    print(f"[cockpit] alpha={scene.mm_sketch_alpha:.2f}  hardscape={hardscape_note}  "
          f"faces={len(mesh.polygons)}  structural={len(all_specs)}  "
          f"{scene.mm_slab_harvest_label}  {time.time() - t0:.2f}s")


PAINT_CANVAS_OBJ_NAME = "mm_paint_canvas"
PAINT_CAM_NAME = "mm_paint_cam"
# key, panel label, brush/overlay tint RGB, continuous (True = weight like
# Canyon's additive sketch_weight, painted alpha used directly, no distance-
# falloff math needed -- the brush's own soft edge gives the falloff for
# free; False = boolean zone, thresholded at PAINT_ZONE_THRESHOLD). Per
# sketch_weight_mapper.py's own established distinction, a zone mark is a
# filled-region claim ("everything inside this claim"), not a line to
# measure distance from -- real brush painting satisfies that directly, no
# flood-fill trick needed, unlike the old scanned-photo pipeline.
PAINT_CATEGORIES = (
    ("canyon", "Canyon", (0.0, 0.0, 0.0), True),
    ("hardscape", "Hardscape", (0.15, 0.35, 1.0), False),
    ("water_shade", "Water/Shade", (0.15, 0.85, 0.95), False),
    ("greenscape", "Greenscape", (0.2, 0.75, 0.25), False),
    ("amenity_resting", "Amenity/Resting", (1.0, 0.55, 0.1), False),
)
PAINT_ZONE_THRESHOLD = 0.3
PAINT_PX_PER_CELL = 8
_probe_engine = TerracingEngine(REAL_GEOMETRY)  # cheap -- only used for nx/nz/voxel_ft below
PAINT_GRID_NX, PAINT_GRID_NZ = _probe_engine.nx, _probe_engine.nz
PAINT_VOXEL_FT = _probe_engine.voxel_ft
PAINT_IMG_W = PAINT_GRID_NX * PAINT_PX_PER_CELL
PAINT_IMG_H = PAINT_GRID_NZ * PAINT_PX_PER_CELL


def _mask_image_name(key):
    return f"mm_paint_{key}"


def setup_paint_canvas():
    """
    One-time creation of the live 2D sketch-painting interface: a flat plane
    showing the real uploaded hand-drawn sketch (data/sketches/...) as a
    background, UV-registered to real site feet using the SAME flip_x=True/
    flip_y=True convention already calibrated in sketch_weight_mapper.py
    (HILL-left/OLIVE-right/6th-top/5th-bottom on the raw photo -> real site
    feet -- derivation verified 2026-07-05 against a rendered screenshot
    before trusting it, see conversation), plus one paintable mask Image per
    PAINT_CATEGORIES entry. Painting uses Blender's own Image Paint system
    directly (tool_settings.image_paint.canvas, mode='IMAGE') -- real
    per-pixel alpha, no material-slot switching needed, no PIL round-trip. A
    shader Mix-RGB chain composites all 5 masks tinted over the sketch so
    painting reads as literal semi-opaque color washes on the drawing.
    Idempotent, same pattern as import_static_context.
    """
    if bpy.data.objects.get(PAINT_CANVAS_OBJ_NAME) is not None:
        print("[cockpit] paint canvas already set up, skipping re-creation")
        return
    if SKETCH_IMAGE_PATH is None:
        print("[cockpit] no sketch image found in data/sketches, skipping paint canvas setup")
        return

    W = REAL_GEOMETRY["site"]["width_ft"]
    L = REAL_GEOMETRY["site"]["length_ft"]

    mesh = bpy.data.meshes.new(PAINT_CANVAS_OBJ_NAME)
    bm = bmesh.new()
    verts = [bm.verts.new(c) for c in ((0.0, 0.0, 0.0), (W, 0.0, 0.0), (W, L, 0.0), (0.0, L, 0.0))]
    bm.faces.new(verts)
    bm.to_mesh(mesh)
    bm.free()
    canvas_obj = bpy.data.objects.new(PAINT_CANVAS_OBJ_NAME, mesh)
    bpy.context.collection.objects.link(canvas_obj)

    mesh.uv_layers.new(name="UVMap")
    uv = mesh.uv_layers.active.data
    # real(0,0)->uv(1,0); real(W,0)->uv(0,0); real(W,L)->uv(0,1); real(0,L)->uv(1,1)
    # -- matches load_image_sketch's real_x=(1-fx)*W, real_y=(1-fy)*L exactly
    # once Blender's own bottom-up image.pixels row order is accounted for.
    for i, co in enumerate(((1.0, 0.0), (0.0, 0.0), (0.0, 1.0), (1.0, 1.0))):
        uv[i].uv = co

    sketch_img = bpy.data.images.load(SKETCH_IMAGE_PATH, check_existing=True)

    mat = bpy.data.materials.new("mm_paint_canvas_mat")
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()

    out = nt.nodes.new("ShaderNodeOutputMaterial")
    emit = nt.nodes.new("ShaderNodeEmission")
    nt.links.new(emit.outputs["Emission"], out.inputs["Surface"])

    uv_node = nt.nodes.new("ShaderNodeUVMap")
    uv_node.uv_map = "UVMap"

    sketch_tex = nt.nodes.new("ShaderNodeTexImage")
    sketch_tex.image = sketch_img
    nt.links.new(uv_node.outputs["UV"], sketch_tex.inputs["Vector"])

    prev_color = sketch_tex.outputs["Color"]
    for key, label, tint, continuous in PAINT_CATEGORIES:
        img = bpy.data.images.new(_mask_image_name(key), width=PAINT_IMG_W, height=PAINT_IMG_H, alpha=True)
        px = list(img.pixels)
        for i in range(3, len(px), 4):
            px[i] = 0.0  # fully transparent -- "nothing painted here yet"
        img.pixels = px

        mask_tex = nt.nodes.new("ShaderNodeTexImage")
        mask_tex.image = img
        nt.links.new(uv_node.outputs["UV"], mask_tex.inputs["Vector"])

        mix = nt.nodes.new("ShaderNodeMixRGB")
        mix.inputs["Color2"].default_value = (*tint, 1.0)
        nt.links.new(mask_tex.outputs["Alpha"], mix.inputs["Fac"])
        nt.links.new(prev_color, mix.inputs["Color1"])
        prev_color = mix.outputs["Color"]

    nt.links.new(prev_color, emit.inputs["Color"])
    canvas_obj.data.materials.append(mat)
    canvas_obj.hide_set(True)

    cam_data = bpy.data.cameras.new(PAINT_CAM_NAME)
    cam_data.type = 'ORTHO'
    cam_data.ortho_scale = max(W, L) * 1.05
    cam_obj = bpy.data.objects.new(PAINT_CAM_NAME, cam_data)
    bpy.context.collection.objects.link(cam_obj)
    cam_obj.location = (W / 2, L / 2, 500.0)
    cam_obj.rotation_euler = (0.0, 0.0, 0.0)
    cam_obj.hide_set(True)

    print(f"[cockpit] paint canvas created: {os.path.basename(SKETCH_IMAGE_PATH)}, "
          f"{len(PAINT_CATEGORIES)} paintable categories at {PAINT_IMG_W}x{PAINT_IMG_H}")


def _set_paint_view(active):
    """Toggle between the normal 3D axo view (active=False) and the paint
    canvas's dedicated top-down view (active=True) -- hides whichever set of
    objects would otherwise clutter/occlude the other, since the canvas
    plane and the real terrace both sit in the same real-feet footprint."""
    canvas_obj = bpy.data.objects.get(PAINT_CANVAS_OBJ_NAME)
    paint_cam = bpy.data.objects.get(PAINT_CAM_NAME)
    axo_cam = bpy.data.objects.get(AXO_CAM_NAME)
    if canvas_obj is None or paint_cam is None:
        return
    canvas_obj.hide_set(not active)
    for name in (TERRACE_OBJ_NAME, "columns", "tunnel", "secondary_entrance", "metro_connector", "ramps"):
        obj = bpy.data.objects.get(name)
        if obj is not None:
            obj.hide_set(active)
    coll = bpy.data.collections.get(STRUCTURAL_COLLECTION_NAME)
    if coll is not None:
        coll.hide_viewport = active

    bpy.context.scene.camera = paint_cam if active else axo_cam
    for area in bpy.context.window_manager.windows[0].screen.areas:
        if area.type == 'VIEW_3D':
            r3d = area.spaces.active.region_3d
            r3d.view_perspective = 'CAMERA'
            r3d.view_camera_zoom = 0
            r3d.view_camera_offset = (0.0, 0.0)
            break


def _enter_paint_mode(category_key):
    canvas_obj = bpy.data.objects.get(PAINT_CANVAS_OBJ_NAME)
    img = bpy.data.images.get(_mask_image_name(category_key))
    if canvas_obj is None or img is None:
        return
    _set_paint_view(True)

    ip = bpy.context.scene.tool_settings.image_paint
    ip.mode = 'IMAGE'
    ip.canvas = img
    tint = next(t for k, l, t, c in PAINT_CATEGORIES if k == category_key)
    if ip.brush is not None:
        ip.brush.color = tint

    if bpy.context.object is not None and bpy.context.object.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    for o in bpy.context.selected_objects:
        o.select_set(False)
    canvas_obj.select_set(True)
    bpy.context.view_layer.objects.active = canvas_obj
    bpy.ops.object.mode_set(mode='TEXTURE_PAINT')


class MM_OT_paint_category(bpy.types.Operator):
    bl_idname = "mm.paint_category"
    bl_label = "Paint"
    bl_description = "Enter Texture Paint mode on this category's mask layer, over the real sketch"
    category: bpy.props.StringProperty()

    def execute(self, context):
        _enter_paint_mode(self.category)
        return {'FINISHED'}


def _sample_mask_grid(img, continuous):
    """
    Average each mask image's alpha channel into an (nx, nz) grid, in the
    same real-feet cell indexing TerracingEngine uses (cell (gx, gy) center
    at ((gx+0.5)*voxel_ft, (gy+0.5)*voxel_ft)). Inverts setup_paint_canvas's
    UV placement exactly: real_x=(1-u)*W -> pixel col = u*w = (1-real_x/W)*w;
    real_y=v*L -> Blender's own bottom-up pixel row = v*h = (real_y/L)*h.
    `continuous`: True returns the averaged alpha directly (0..1 weight,
    e.g. Canyon); False thresholds at PAINT_ZONE_THRESHOLD (boolean zone).
    """
    w, h = img.size
    px = img.pixels[:]
    W = REAL_GEOMETRY["site"]["width_ft"]
    L = REAL_GEOMETRY["site"]["length_ft"]
    nx, nz = PAINT_GRID_NX, PAINT_GRID_NZ

    result = [[(0.0 if continuous else False)] * nz for _ in range(nx)]
    for gx in range(nx):
        real_x0, real_x1 = gx * PAINT_VOXEL_FT, (gx + 1) * PAINT_VOXEL_FT
        col0 = max(0, int((1 - real_x1 / W) * w))
        col1 = min(w, max(col0 + 1, int((1 - real_x0 / W) * w)))
        for gy in range(nz):
            real_y0, real_y1 = gy * PAINT_VOXEL_FT, (gy + 1) * PAINT_VOXEL_FT
            row0 = max(0, int((real_y0 / L) * h))
            row1 = min(h, max(row0 + 1, int((real_y1 / L) * h)))

            total, count = 0.0, 0
            for row in range(row0, row1):
                base = row * w * 4
                for col in range(col0, col1):
                    total += px[base + col * 4 + 3]
                    count += 1
            avg = total / count if count else 0.0
            result[gx][gy] = avg if continuous else avg > PAINT_ZONE_THRESHOLD
    return result


def bake_paint_canvas(scene):
    """
    Sample all 5 painted mask images into SKETCH_WEIGHTS/HARDSCAPE_MASK/
    WATER_SHADE_MASK/GREENSCAPE_MASK/AMENITY_RESTING_MASK, then trigger the
    one real rebuild. No falloff math needed -- the painted alpha itself
    already IS the continuous weight (Canyon) or the filled-region claim
    (everything else), since brush painting fills its own interior directly.
    """
    global SKETCH_WEIGHTS, HARDSCAPE_MASK, WATER_SHADE_MASK, GREENSCAPE_MASK, AMENITY_RESTING_MASK
    painted_counts = {}
    for key, label, tint, continuous in PAINT_CATEGORIES:
        img = bpy.data.images.get(_mask_image_name(key))
        if img is None:
            continue
        grid = _sample_mask_grid(img, continuous)
        if key == "canyon":
            SKETCH_WEIGHTS = grid
        elif key == "hardscape":
            HARDSCAPE_MASK = grid
        elif key == "water_shade":
            WATER_SHADE_MASK = grid
        elif key == "greenscape":
            GREENSCAPE_MASK = grid
        elif key == "amenity_resting":
            AMENITY_RESTING_MASK = grid
        painted_counts[key] = sum(1 for row in grid for v in row if (v > 0.01 if continuous else v))

    _set_paint_view(False)
    if bpy.context.object is not None and bpy.context.object.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    rebuild_all(scene)
    print(f"[cockpit] baked painted sketch: {painted_counts}")


class MM_OT_bake_paint(bpy.types.Operator):
    bl_idname = "mm.bake_paint"
    bl_label = "Bake Painted Sketch"
    bl_description = "Sample the painted mask layers into the live weight/mask grids, rebuild, and return to the 3D view"

    def execute(self, context):
        bake_paint_canvas(context.scene)
        return {'FINISHED'}


def _on_alpha_update(self, context):
    rebuild_all(context.scene)


def _on_hardscape_update(self, context):
    rebuild_all(context.scene)


def _on_amenity_update(self, context):
    rebuild_all(context.scene)


def _on_structural_update(self, context):
    rebuild_all(context.scene)


def import_static_context():
    """One-time import of real existing structure (columns/tunnel/entrance/
    ramps) for visual reference -- does not participate in the live rebuild.
    Skips its own 'terrace' object; the cockpit builds that one live."""
    if bpy.data.objects.get("columns") is not None:
        print("[cockpit] static context already imported, skipping re-import")
        return
    if not os.path.exists(CONTEXT_OBJ_PATH):
        print(f"[cockpit] no context OBJ at {CONTEXT_OBJ_PATH}, skipping (terrace-only)")
        return
    before = set(bpy.data.objects.keys())
    bpy.ops.wm.obj_import(filepath=CONTEXT_OBJ_PATH, up_axis='Z', forward_axis='Y')
    imported_names = [n for n in bpy.data.objects.keys() if n not in before]
    kept = []
    for name in imported_names:
        if name.startswith("terrace"):
            bpy.data.objects.remove(bpy.data.objects[name], do_unlink=True)
        else:
            kept.append(name)
    print(f"[cockpit] imported static context: {kept}")


AXO_CAM_NAME = "mm_axo_cam"


def setup_axo_view(real_geometry):
    """
    Orient the scene to this project's already-validated axonometric
    convention instead of Blender's arbitrary default/auto-frame view --
    without this, "left/right" in a screenshot is just whatever angle
    view_selected() happened to land on, not a meaningful check of site
    orientation (see 2026-07-05 conversation: entrance appeared to be on the
    "wrong" side purely because of this, not a real coordinate bug).

    Mirrors every object's Y the same way vector_export.mirror_mesh_y does
    (y -> site_length_ft - y) via the object's matrix_world (mesh data left
    untouched, so this stays correct across live terrace rebuilds), then
    places an orthographic camera along AXO_VIEW_DIR with up/right = the
    same (u, v) basis vector_export.axonometric_projection uses -- so
    on-screen layout matches the already-verified DXF/SVG axo export.
    """
    L = real_geometry["site"]["length_ft"]
    W = real_geometry["site"]["width_ft"]
    u, v = _axo_basis(AXO_VIEW_DIR)

    mirror = mathutils.Matrix(((1, 0, 0, 0), (0, -1, 0, L), (0, 0, 1, 0), (0, 0, 0, 1)))
    for name in (TERRACE_OBJ_NAME, "columns", "tunnel", "secondary_entrance", "metro_connector", "ramps"):
        obj = bpy.data.objects.get(name)
        if obj is not None:
            obj.matrix_world = mirror

    cam_obj = bpy.data.objects.get(AXO_CAM_NAME)
    if cam_obj is None:
        cam_data = bpy.data.cameras.new(AXO_CAM_NAME)
        cam_data.type = 'ORTHO'
        cam_data.ortho_scale = max(W, L) * 1.4
        cam_obj = bpy.data.objects.new(AXO_CAM_NAME, cam_data)
        bpy.context.collection.objects.link(cam_obj)

    center = mathutils.Vector((W / 2, L / 2, -35.0))
    rot = mathutils.Matrix((tuple(u), tuple(v), tuple(AXO_VIEW_DIR))).transposed().to_3x3()
    cam_obj.matrix_world = rot.to_4x4()
    cam_obj.location = center + mathutils.Vector(AXO_VIEW_DIR) * 800.0
    bpy.context.scene.camera = cam_obj

    for area in bpy.context.window_manager.windows[0].screen.areas:
        if area.type == 'VIEW_3D':
            area.spaces.active.region_3d.view_perspective = 'CAMERA'
            break
    print("[cockpit] axo view set up (entrance/Hill St should read on the right, 5th St near top)")


class MM_PT_cockpit(bpy.types.Panel):
    bl_label = "Memory Machine Cockpit"
    bl_idname = "MM_PT_cockpit"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Cockpit"

    def draw(self, context):
        self.layout.prop(context.scene, "mm_sketch_alpha", slider=True)
        self.layout.prop(context.scene, "mm_hardscape_enabled")
        hardscape_count = sum(1 for row in HARDSCAPE_MASK for v in row if v)
        self.layout.label(text=f"{hardscape_count} hardscape cells cached")
        row = self.layout.row()
        row.enabled = AMENITY_CSV_PATH is not None
        row.prop(context.scene, "mm_use_real_amenity_data")
        self.layout.label(text=(f"csv: {os.path.basename(AMENITY_CSV_PATH)}" if AMENITY_CSV_PATH
                                 else "no amenity CSV found -- using placeholder"))

        box = self.layout.box()
        box.label(text="Structural Framing Engine")
        box.prop(context.scene, "mm_canyon_width", slider=True)
        box.prop(context.scene, "mm_canyon_depth", slider=True)
        box.prop(context.scene, "mm_material_mode")
        box.prop(context.scene, "mm_shoring_density", slider=True)
        box.label(text=context.scene.mm_slab_harvest_label)

        box2 = self.layout.box()
        box2.label(text="Live Sketch (Paint on Photo)")
        if SKETCH_IMAGE_PATH is None:
            box2.label(text="no sketch image found in data/sketches")
        else:
            for key, label, tint, continuous in PAINT_CATEGORIES:
                op = box2.operator("mm.paint_category", text=f"Paint {label}", icon='BRUSH_DATA')
                op.category = key
            box2.operator("mm.bake_paint", icon='FILE_REFRESH')


def register():
    bpy.types.Scene.mm_sketch_alpha = bpy.props.FloatProperty(
        name="Sketch Alpha",
        description="Designer-sketch agency weight (see terracing_engine.py _effective_influence)",
        default=0.75, min=0.0, max=1.0,
        update=_on_alpha_update,
    )
    bpy.types.Scene.mm_hardscape_enabled = bpy.props.BoolProperty(
        name="Protect Hardscape",
        description="Veto excavation in designer-marked hardscape regions (see terracing_engine.py hardscape_regions)",
        default=True,
        update=_on_hardscape_update,
    )
    bpy.types.Scene.mm_use_real_amenity_data = bpy.props.BoolProperty(
        name="Use Real Amenity Data",
        description="Load deficit hotspots from the latest CSV in data/amenity_survey instead of the 2-point placeholder",
        default=AMENITY_CSV_PATH is not None,
        update=_on_amenity_update,
    )
    bpy.types.Scene.mm_canyon_width = bpy.props.IntProperty(
        name="Canyon Width (bays)",
        description="Lateral excavation footprint across the 27ft column grid, in whole bays",
        default=min(3, NX_BAYS), min=1, max=NX_BAYS,
        update=_on_structural_update,
    )
    bpy.types.Scene.mm_canyon_depth = bpy.props.IntProperty(
        name="Canyon Depth (levels)",
        description="Number of subterranean parking levels pierced",
        default=1, min=1, max=4,
        update=_on_structural_update,
    )
    bpy.types.Scene.mm_material_mode = bpy.props.EnumProperty(
        name="Material Mode",
        description="Structural system driving the canyon's framing logic",
        items=[
            ('STEEL', "Steel", "27ft column vectors, collars, and tension tie-rods"),
            ('WOOD', "Wood", "9ft heavy-timber sub-grid with glulam posts and knee braces"),
        ],
        default='STEEL',
        update=_on_structural_update,
    )
    bpy.types.Scene.mm_shoring_density = bpy.props.FloatProperty(
        name="Shoring Density",
        description="Safety factor multiplier driving structural element frequency/packing",
        default=1.0, min=0.5, max=2.0,
        update=_on_structural_update,
    )
    bpy.types.Scene.mm_slab_harvest_label = bpy.props.StringProperty(
        name="Slab Harvest Readout",
        default="Slab Material Harvested: 0 Tons",
    )
    for cls in (MM_PT_cockpit, MM_OT_paint_category, MM_OT_bake_paint):
        if cls.__name__ in dir(bpy.types):
            bpy.utils.unregister_class(getattr(bpy.types, cls.__name__))
        bpy.utils.register_class(cls)


def unregister():
    for cls in (MM_PT_cockpit, MM_OT_paint_category, MM_OT_bake_paint):
        bpy.utils.unregister_class(cls)
    del bpy.types.Scene.mm_sketch_alpha
    del bpy.types.Scene.mm_hardscape_enabled
    del bpy.types.Scene.mm_use_real_amenity_data
    del bpy.types.Scene.mm_canyon_width
    del bpy.types.Scene.mm_canyon_depth
    del bpy.types.Scene.mm_material_mode
    del bpy.types.Scene.mm_shoring_density
    del bpy.types.Scene.mm_slab_harvest_label


register()
import_static_context()
setup_paint_canvas()
rebuild_all(bpy.context.scene)
setup_axo_view(REAL_GEOMETRY)
