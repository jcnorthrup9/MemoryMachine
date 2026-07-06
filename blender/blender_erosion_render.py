"""
Render the eroded terrace (site_eroded.blend, produced by blender_erosion_pass.py)
for visual verification. Run headless:
  blender --background site_eroded.blend --python blender_erosion_render.py
"""
import bpy
import mathutils

SITE_W = 354.14
SITE_L = 602.4
VIEW_DIR = mathutils.Vector((1.0, -1.0, 1.0)).normalized()
OUT_PNG = r"D:\MemoryMachine\outputs\vector_export_test\erosion_test_render.png"

for name in list(bpy.data.objects.keys()):
    obj = bpy.data.objects.get(name)
    if obj and obj.type == 'CAMERA':
        bpy.data.objects.remove(obj, do_unlink=True)

center = mathutils.Vector((SITE_W / 2, SITE_L / 2, 0.0))
cam_data = bpy.data.cameras.new("RenderCam")
cam_data.type = 'ORTHO'
cam_data.clip_start = 0.1
cam_data.clip_end = 10000
cam_obj = bpy.data.objects.new("RenderCam", cam_data)
bpy.context.collection.objects.link(cam_obj)
cam_obj.location = center + VIEW_DIR * max(SITE_W, SITE_L) * 2
direction = center - cam_obj.location
cam_obj.rotation_euler = direction.to_track_quat('-Z', 'Y').to_euler()
bpy.context.scene.camera = cam_obj

# Size ortho_scale from the whole SITE's bounding box in camera space (not a
# guessed number) -- an isometric view's camera-space extent can be much
# larger than any single world dimension (see Line Art rehearsal notes).
bpy.context.view_layer.update()
cam_inv = cam_obj.matrix_world.inverted()
all_corners = []
for obj in bpy.context.scene.objects:
    if obj.type == 'MESH':
        all_corners.extend(obj.matrix_world @ mathutils.Vector(c) for c in obj.bound_box)
local = [cam_inv @ c for c in all_corners]
x_span = max(c.x for c in local) - min(c.x for c in local)
y_span = max(c.y for c in local) - min(c.y for c in local)
res_x, res_y = bpy.context.scene.render.resolution_x, bpy.context.scene.render.resolution_y
cam_data.ortho_scale = 1.2 * max(x_span, y_span * res_x / res_y)
print(f"camera-space extent x={x_span:.1f} y={y_span:.1f} -> ortho_scale={cam_data.ortho_scale:.1f}")

light = bpy.data.lights.new("Sun", type='SUN')
light.energy = 3.0
light_obj = bpy.data.objects.new("Sun", light)
bpy.context.collection.objects.link(light_obj)
light_obj.rotation_euler = (0.9, 0.3, 0.6)

bpy.context.scene.render.resolution_x = 3840
bpy.context.scene.render.resolution_y = 2160
bpy.context.scene.render.resolution_percentage = 100
bpy.context.scene.render.filepath = OUT_PNG
bpy.context.scene.render.image_settings.file_format = 'PNG'
bpy.context.scene.render.engine = 'BLENDER_EEVEE_NEXT' if 'BLENDER_EEVEE_NEXT' in [e.identifier for e in bpy.types.RenderSettings.bl_rna.properties['engine'].enum_items] else 'BLENDER_EEVEE'
print("using render engine:", bpy.context.scene.render.engine)
# Bump anti-aliasing samples -- default may be too low for a clean 4K still.
if hasattr(bpy.context.scene.eevee, "taa_render_samples"):
    bpy.context.scene.eevee.taa_render_samples = 64

bpy.ops.render.render(write_still=True)
print("rendered to", OUT_PNG)
