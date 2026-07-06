import bpy
import math
import mathutils

OBJ_PATH = r"D:\MemoryMachine\outputs\vector_export_test\combined_clean.obj"
SITE_W = 354.14
SITE_L = 602.4

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.wm.obj_import(filepath=OBJ_PATH, up_axis='Z', forward_axis='Y')
mesh_objs = [o for o in bpy.context.scene.objects if o.type == 'MESH']
print("imported mesh objects:", len(mesh_objs), [o.name for o in mesh_objs])
for o in mesh_objs:
    print("  ", o.name, "verts:", len(o.data.vertices), "polys:", len(o.data.polygons))

center = mathutils.Vector((SITE_W / 2, SITE_L / 2, 0.0))
view_dir = mathutils.Vector((1.0, 1.0, 1.0)).normalized()
cam_data = bpy.data.cameras.new("AxoCam")
cam_data.type = 'ORTHO'
cam_data.ortho_scale = max(SITE_W, SITE_L) * 1.3
cam_data.clip_start = 0.1
cam_data.clip_end = max(SITE_W, SITE_L) * 10
cam_obj = bpy.data.objects.new("AxoCam", cam_data)
bpy.context.collection.objects.link(cam_obj)
cam_obj.location = center + view_dir * max(SITE_W, SITE_L) * 2
direction = center - cam_obj.location
cam_obj.rotation_euler = direction.to_track_quat('-Z', 'Y').to_euler()
bpy.context.scene.camera = cam_obj
print("camera at", tuple(cam_obj.location), "ortho_scale", cam_data.ortho_scale)

bpy.ops.object.grease_pencil_add(type='EMPTY', location=(0, 0, 0))
gp_obj = bpy.context.object
gp_obj.name = "LineArt"
mod = gp_obj.modifiers.new(name="LineArt", type='LINEART')
mod.source_type = 'SCENE'
mod.use_contour = True
mod.use_crease = True
mod.crease_threshold = math.radians(25)
mod.use_loose_as_contour = True
mod.source_camera = cam_obj

print("gp data layers before bake:", len(gp_obj.data.layers))

bpy.context.view_layer.update()
bpy.ops.object.select_all(action='DESELECT')
gp_obj.select_set(True)
bpy.context.view_layer.objects.active = gp_obj

result = bpy.ops.object.lineart_bake_strokes()
print("bake result:", result)

print("gp data layers after bake:", len(gp_obj.data.layers))
for layer in gp_obj.data.layers:
    print("  layer:", layer.name, "frames:", len(layer.frames))
    for frame in layer.frames:
        print("    frame", frame.frame_number, "drawing:", frame.drawing if hasattr(frame, 'drawing') else None)
        d = frame.drawing
        if d is not None:
            print("      strokes:", len(d.strokes))
