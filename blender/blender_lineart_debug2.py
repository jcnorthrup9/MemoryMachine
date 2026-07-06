import bpy
import mathutils

OBJ_PATH = r"D:\MemoryMachine\outputs\vector_export_test\combined_clean.obj"
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.wm.obj_import(filepath=OBJ_PATH, up_axis='Z', forward_axis='Y')
mesh_objs = [o for o in bpy.context.scene.objects if o.type == 'MESH']
obj = mesh_objs[0]

print("has lineart attr:", hasattr(obj, "lineart"))
if hasattr(obj, "lineart"):
    la = obj.lineart
    for p in la.bl_rna.properties:
        if p.identifier != "rna_type":
            print(" ", p.identifier, "=", getattr(la, p.identifier, None))

print("\nmesh has normals? checking a few polygon normals:")
for poly in list(obj.data.polygons)[:5]:
    print("  normal:", tuple(poly.normal))

print("\nobj.data.polygons count:", len(obj.data.polygons))
print("obj.visible_get():", obj.visible_get())
print("obj.hide_render:", obj.hide_render)
print("obj.hide_viewport:", obj.hide_viewport)

# check scene / view layer collections
print("\nscene collection objects:", [o.name for o in bpy.context.scene.collection.all_objects])
vl = bpy.context.view_layer
print("view layer name:", vl.name)
print("layer_collection excluded?:", vl.layer_collection.exclude)
