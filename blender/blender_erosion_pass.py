"""
Blender erosion/weathering pass (Section 4 rehearsal).

Run headless: blender --background --python blender_erosion_pass.py

Imports the named multi-part site OBJ (see vector_export.py's
build_named_scene), applies subdivision + noise-driven Displace modifier
("concrete erosion" look) to the terrace object only -- the real existing
structure (columns/tunnel/entrance/ramps) stays clean/unweathered for this
first pass, since it represents existing structure, not the new designed
intervention the "30-year caregiver" narrative is about.

Deliberately uses a Displace modifier + noise texture, not a hand-authored
Geometry Nodes node tree -- simpler and much lower API risk than building a
custom GN tree via bpy scripting blind (see the Line Art rehearsal's session
notes for how much trial-and-error even a "simple" GN-adjacent feature took).
Revisit with real Geometry Nodes only if this doesn't give enough control.

Same up_axis/forward_axis gotcha as the Line Art bridge: wm.obj_import
defaults to up_axis='Y' (classic OBJ convention), which would silently
rotate this Z-up-exported mesh wrong.
"""
import bpy

OBJ_PATH = r"D:\MemoryMachine\outputs\vector_export_test\site_named.obj"
OUT_BLEND = r"D:\MemoryMachine\outputs\vector_export_test\site_eroded.blend"
OUT_RENDER = r"D:\MemoryMachine\outputs\vector_export_test\erosion_test_render.png"

bpy.ops.wm.read_factory_settings(use_empty=True)

bpy.ops.wm.obj_import(filepath=OBJ_PATH, up_axis='Z', forward_axis='Y')
objs = {o.name: o for o in bpy.context.scene.objects if o.type == 'MESH'}
print("imported objects:", list(objs.keys()))

terrace = objs["terrace"]

# Subdivide so the Displace modifier has enough vertices to actually show
# erosion detail (a single flat quad per tread can't display noise texture).
subsurf = terrace.modifiers.new(name="Subdivide", type='SUBSURF')
subsurf.subdivision_type = 'SIMPLE'  # keep flat step edges crisp, don't smooth the terrace shape itself
subsurf.levels = 3
subsurf.render_levels = 3

# Noise texture driving the displacement -- "concrete erosion" surface
# roughening. Pushed stronger per user feedback on the first pass (v1 read
# as too subtle): higher noise_depth = more turbulent/organic (fractal)
# variation instead of smooth clouds, and a much larger displacement strength.
tex = bpy.data.textures.new("ErosionNoise", type='CLOUDS')
tex.noise_scale = 4.0
tex.noise_depth = 6
tex.noise_type = 'HARD_NOISE'  # sharper, more weathered-looking ridges than soft clouds

disp = terrace.modifiers.new(name="Erosion", type='DISPLACE')
disp.texture = tex
disp.strength = 4.5  # feet -- pushed up from 1.5 (v1, read as too subtle)
disp.mid_level = 0.5

print("modifiers on terrace:", [m.name for m in terrace.modifiers])

# --- Weathered-concrete material: patchy staining via a second noise
# texture feeding a ColorRamp into Base Color, not just a flat gray. ---
mat = bpy.data.materials.new("WeatheredConcrete")
mat.use_nodes = True
nodes = mat.node_tree.nodes
links = mat.node_tree.links
bsdf = nodes["Principled BSDF"]

stain_noise = nodes.new("ShaderNodeTexNoise")
stain_noise.inputs["Scale"].default_value = 8.0
stain_noise.inputs["Detail"].default_value = 6.0
stain_noise.inputs["Roughness"].default_value = 0.7

ramp = nodes.new("ShaderNodeValToRGB")
ramp.color_ramp.elements[0].position = 0.35
ramp.color_ramp.elements[0].color = (0.10, 0.13, 0.09, 1.0)  # dark mossy/water-stained concrete
ramp.color_ramp.elements[1].position = 0.65
ramp.color_ramp.elements[1].color = (0.62, 0.60, 0.55, 1.0)  # base weathered concrete gray

links.new(stain_noise.outputs["Fac"], ramp.inputs["Fac"])
links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
bsdf.inputs["Roughness"].default_value = 0.85

terrace.data.materials.clear()
terrace.data.materials.append(mat)
print("material assigned:", mat.name)

# Apply both modifiers so the eroded shape is baked into real geometry
# (not just a live modifier preview) before export/render.
wm = bpy.context.window_manager
win = wm.windows[0]
area3d = next(a for a in win.screen.areas if a.type == 'VIEW_3D')
with bpy.context.temp_override(window=win, screen=win.screen, area=area3d):
    bpy.context.view_layer.objects.active = terrace
    bpy.ops.object.modifier_apply(modifier="Subdivide")
    bpy.ops.object.modifier_apply(modifier="Erosion")
print("modifiers applied -- eroded geometry baked in. verts now:", len(terrace.data.vertices))

bpy.ops.wm.save_as_mainfile(filepath=OUT_BLEND)
print("saved", OUT_BLEND)
