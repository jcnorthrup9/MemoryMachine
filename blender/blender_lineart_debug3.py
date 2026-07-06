import bpy
import math

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.mesh.primitive_cube_add(size=2, location=(0, 0, 0))
cube = bpy.context.object
print("cube created:", cube.name)

cam_data = bpy.data.cameras.new("Cam")
cam_data.type = 'ORTHO'
cam_data.ortho_scale = 6
cam = bpy.data.objects.new("Cam", cam_data)
bpy.context.collection.objects.link(cam)
cam.location = (5, 5, 5)
import mathutils
direction = mathutils.Vector((0, 0, 0)) - cam.location
cam.rotation_euler = direction.to_track_quat('-Z', 'Y').to_euler()
bpy.context.scene.camera = cam

bpy.ops.object.grease_pencil_add(type='EMPTY', location=(0, 0, 0))
gp = bpy.context.object
mod = gp.modifiers.new(name="LA", type='LINEART')
mod.source_type = 'OBJECT'
mod.source_object = cube
mod.use_contour = True
mod.source_camera = cam
mod.target_layer = gp.data.layers[0].name
print("target_layer set to:", repr(mod.target_layer))
gp.modifiers.active = mod

bpy.context.scene.frame_set(1)
bpy.context.view_layer.update()
bpy.ops.object.select_all(action='DESELECT')
gp.select_set(True)
bpy.context.view_layer.objects.active = gp

print("trying a render pass first, to populate any Line Art cache...")
bpy.context.scene.render.resolution_x = 64
bpy.context.scene.render.resolution_y = 64
try:
    bpy.ops.render.render(write_still=False)
    print("render finished")
except Exception as e:
    print("render FAILED:", e)

result = bpy.ops.object.lineart_bake_strokes()
print("lineart_bake_strokes result:", result)

for layer in gp.data.layers:
    for frame in layer.frames:
        d = frame.drawing
        print("layer", layer.name, "frame", frame.frame_number, "strokes:", len(d.strokes) if d else None)
        if d and len(d.strokes):
            for s in list(d.strokes)[:3]:
                print("  stroke points:", len(s.points))
