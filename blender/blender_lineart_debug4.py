import bpy

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.mesh.primitive_cube_add(size=2, location=(0, 0, 0))
cube = bpy.context.object

bpy.ops.object.grease_pencil_add(type='EMPTY', location=(0, 0, 0))
gp = bpy.context.object
mod = gp.modifiers.new(name="LA", type='LINEART')

print("render engine:", bpy.context.scene.render.engine)
print("\n--- FULL LineArt modifier property list ---")
for p in mod.bl_rna.properties:
    if p.identifier == "rna_type":
        continue
    try:
        val = getattr(mod, p.identifier)
    except Exception as e:
        val = "<err %s>" % e
    print(p.identifier, "=", val, "  --", p.description[:70])
