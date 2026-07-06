"""
Blender bridge + Grease Pencil Line Art rehearsal (Section 4/6 crossover).

Run headless: blender --background --python blender_lineart_export.py

Imports the clean combined mesh (see vector_export.py's build_combined_mesh,
exported to OBJ separately), sets up an orthographic camera matching
vector_export.py's AXO_VIEW_DIR (isometric), and runs a real Grease Pencil
Line Art pass (silhouette + crease edges, Blender's own hidden-line-aware
algorithm -- not the Python ray-cast HLR in vector_export.py) against it,
exporting the result to SVG. This is a cross-check of the OBJ import bridge
(axis convention especially -- verified separately, see session notes) and
a rehearsal for later swapping in the eroded/weathered mesh (Section 4).

IMPORTANT gotchas found the hard way (2026-07-03), all fixed below:
  - wm.obj_import defaults to up_axis='Y' (classic OBJ convention), which
    would silently rotate this Z-up-exported mesh wrong. Must pass
    up_axis='Z', forward_axis='Y' -- verified against the known site
    bounding box.
  - Manually building a Grease Pencil object (grease_pencil_add(type='EMPTY')
    + modifiers.new(type='LINEART')) reliably bakes to ZERO strokes, even
    with a perfectly-framed camera and a trivial test cube -- this is NOT a
    GPU/headless limitation (confirmed baking still fails in a live GUI
    session with real GPU access). The fix is to use one of the dedicated
    presets (grease_pencil_add(type='LINEART_OBJECT'/'LINEART_SCENE'/
    'LINEART_COLLECTION')), which auto-configures something the manual path
    misses and actually bakes real strokes.
  - ortho_scale must be sized from the mesh's bounding box PROJECTED INTO
    CAMERA SPACE (via the camera's inverse world matrix), not from the
    world-space site dimensions -- an isometric view's camera-space extent
    can be much larger than either world dimension alone (measured ~1028 x
    700 for this site from this angle, vs. 602 world-space max).
  - Line Art bakes one frame per scene frame_start..frame_end -- pin both
    to 1 for a static architectural drawing, or it bakes (and exports) 250
    redundant duplicate frames by default.
  - The exported SVG's strokes are `fill="#000000" stroke="none"` (correct:
    Grease Pencil strokes have real width, so the exporter represents each
    as a filled ribbon polygon, not an infinitely-thin stroked line). This
    is NOT a bug -- but it means the SVG has no background rect, so it can
    render as invisible "black on the browser's default background" until
    you add a white background rect, and it means downstream tooling must
    treat these as filled shapes, not strokes.
"""
import bpy
import math
import mathutils

OBJ_PATH = r"D:\MemoryMachine\outputs\vector_export_test\combined_clean.obj"
OUT_SVG = r"D:\MemoryMachine\outputs\vector_export_test\axo_blender_lineart.svg"

# Site dims, matching vector_export.py / terracing_engine.py (real, verified).
SITE_W = 354.14
SITE_L = 602.4
# Matches vector_export.py's AXO_VIEW_DIR, confirmed correct by the user.
VIEW_DIR = mathutils.Vector((1.0, -1.0, 1.0)).normalized()

bpy.ops.wm.read_factory_settings(use_empty=True)

bpy.ops.wm.obj_import(filepath=OBJ_PATH, up_axis='Z', forward_axis='Y')
mesh_objs = [o for o in bpy.context.scene.objects if o.type == 'MESH']
print(f"imported {len(mesh_objs)} mesh object(s)")
mesh_obj = mesh_objs[0]

# --- Camera: orthographic, isometric ---
center = mathutils.Vector((SITE_W / 2, SITE_L / 2, 0.0))
cam_data = bpy.data.cameras.new("AxoCam")
cam_data.type = 'ORTHO'
cam_data.clip_start = 0.1
cam_data.clip_end = max(SITE_W, SITE_L) * 10
cam_obj = bpy.data.objects.new("AxoCam", cam_data)
bpy.context.collection.objects.link(cam_obj)
cam_obj.location = center + VIEW_DIR * max(SITE_W, SITE_L) * 2
direction = center - cam_obj.location
cam_obj.rotation_euler = direction.to_track_quat('-Z', 'Y').to_euler()
bpy.context.scene.camera = cam_obj

# Size ortho_scale from the mesh's bounding box in CAMERA space (not world
# space -- see module docstring), with a margin, respecting render aspect.
bpy.context.view_layer.update()
cam_inv = cam_obj.matrix_world.inverted()
corners = [mesh_obj.matrix_world @ mathutils.Vector(c) for c in mesh_obj.bound_box]
local = [cam_inv @ c for c in corners]
x_span = max(c.x for c in local) - min(c.x for c in local)
y_span = max(c.y for c in local) - min(c.y for c in local)
res_x, res_y = bpy.context.scene.render.resolution_x, bpy.context.scene.render.resolution_y
margin = 1.2
cam_data.ortho_scale = margin * max(x_span, y_span * res_x / res_y)
print(f"camera-space extent x={x_span:.1f} y={y_span:.1f} -> ortho_scale={cam_data.ortho_scale:.1f}")

# --- Grease Pencil + Line Art: MUST use a LINEART_* preset, not a manual
# EMPTY + modifiers.new(type='LINEART') -- see module docstring. ---
bpy.context.view_layer.objects.active = mesh_obj
bpy.ops.object.select_all(action='DESELECT')
mesh_obj.select_set(True)
bpy.ops.object.grease_pencil_add(type='LINEART_OBJECT', location=(0, 0, 0))
gp_obj = bpy.context.object
gp_obj.name = "SiteLineArt"
mod = gp_obj.modifiers["Lineart"]
mod.source_camera = cam_obj
mod.crease_threshold = math.radians(25)  # match vector_export.py's crease_angle_deg default

bpy.context.scene.frame_start = 1
bpy.context.scene.frame_end = 1
bpy.context.scene.frame_set(1)

bpy.ops.object.select_all(action='DESELECT')
gp_obj.select_set(True)
bpy.context.view_layer.objects.active = gp_obj
bpy.ops.object.lineart_bake_strokes()

total_strokes = sum(
    len(frame.drawing.strokes) if frame.drawing else 0
    for layer in gp_obj.data.layers for frame in layer.frames
)
print(f"baked {total_strokes} strokes")

bpy.ops.wm.grease_pencil_export_svg(
    filepath=OUT_SVG,
    use_fill=False,
    selected_object_type='ACTIVE',
    frame_mode='ACTIVE',
    use_clip_camera=True,
)
print(f"exported {OUT_SVG}")
