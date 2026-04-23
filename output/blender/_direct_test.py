
import sys, os
sys.path.insert(0, r"D:\MemoryMachine")
import importlib.util
spec = importlib.util.spec_from_file_location("generator", r"D:\MemoryMachine\pershing_square_generator.py")
mod  = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
print("CHECKPOINT_A")
mod.build_park(
    option_name  = 'DirectTest',
    svg_path     = r"",
    dense_hills  = True,
    height_scale = 1.0,
    trunk_r      = 0.65,
)
print("CHECKPOINT_B")
import bpy, struct
out = r"D:\MemoryMachine\output\blender\DirectTest.stl"
os.makedirs(os.path.dirname(out), exist_ok=True)
try:
    print("CHECKPOINT_C")
    depsgraph = bpy.context.evaluated_depsgraph_get()
    print("CHECKPOINT_D")
    triangles = []
    for obj in bpy.data.objects:
        if obj.type != "MESH":
            continue
        obj_eval = obj.evaluated_get(depsgraph)
        me = obj_eval.to_mesh()
        me.calc_loop_triangles()
        mat = obj.matrix_world
        mat3 = mat.to_3x3().normalized()
        for tri in me.loop_triangles:
            verts = [mat @ me.vertices[vi].co for vi in tri.vertices]
            normal = mat3 @ tri.normal
            triangles.append((normal, verts))
        obj_eval.to_mesh_clear()
    print(f"TRIANGLES: {len(triangles)}")
    with open(out, "wb") as f:
        header = b"MemoryMachine STL export"
        f.write(header + bytes(80 - len(header)))
        f.write(struct.pack("<I", len(triangles)))
        for normal, verts in triangles:
            f.write(struct.pack("<fff", normal.x, normal.y, normal.z))
            for v in verts:
                f.write(struct.pack("<fff", v.x, v.y, v.z))
            f.write(struct.pack("<H", 0))
    print("BLENDER_DONE:" + out)
except Exception as e:
    import traceback
    print("STL_EXPORT_FAILED:", traceback.format_exc())
