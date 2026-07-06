"""
Headless Blender render of the Pershing Metabolizer phase diagrams.

Consumes blender_scene_data.json (written by generate_phase_scenes.py, which ports
index.html's attractor/voxel/color logic to Python) and renders one PNG per
requested phase, matching the Three.js prototype's axonometric framing, lighting,
and diagrammatic color language (violet/amber voxel heat map, real structural
columns/tunnel/ramps in flat real-world colors).

Run headless (no MCP / no running Blender instance needed):
  blender --background --python pershing_render.py -- \
      blender_scene_data.json renders 1 2 3

Args after '--': <scene_json_path> <output_dir> [phase ...]
  phase in {1, 2, 3, current}. Defaults to 1 2 3 if omitted.
"""
import json
import math
import sys
import os

import bpy
from mathutils import Vector


def parse_args():
    argv = sys.argv
    if "--" in argv:
        argv = argv[argv.index("--") + 1:]
    else:
        argv = []
    scene_json = argv[0] if len(argv) > 0 else "blender_scene_data.json"
    out_dir = argv[1] if len(argv) > 1 else "renders"
    phases = argv[2:] if len(argv) > 2 else ["1", "2", "3"]
    return scene_json, out_dir, phases


def chunk3(flat):
    return [tuple(flat[i:i + 3]) for i in range(0, len(flat), 3)]


def build_mesh(name, verts_flat, faces_flat):
    verts = chunk3(verts_flat)
    faces = chunk3(faces_flat)
    me = bpy.data.meshes.new(name)
    me.from_pydata(verts, [], faces)
    me.update()
    return me


def box_mesh(name, w, d, h):
    x, y, z = w / 2, d / 2, h / 2
    verts = [(-x, -y, -z), (x, -y, -z), (x, y, -z), (-x, y, -z),
             (-x, -y, z), (x, -y, z), (x, y, z), (-x, y, z)]
    faces = [(0, 1, 2, 3), (4, 7, 6, 5), (0, 4, 5, 1),
             (1, 5, 6, 2), (2, 6, 7, 3), (3, 7, 4, 0)]
    me = bpy.data.meshes.new(name)
    me.from_pydata(verts, [], faces)
    me.update()
    return me


def plane_mesh(name, w, d):
    x, y = w / 2, d / 2
    verts = [(-x, -y, 0), (x, -y, 0), (x, y, 0), (-x, y, 0)]
    faces = [(0, 1, 2, 3)]
    me = bpy.data.meshes.new(name)
    me.from_pydata(verts, [], faces)
    me.update()
    return me


def new_object(name, mesh, collection, location=(0, 0, 0)):
    obj = bpy.data.objects.new(name, mesh)
    obj.location = location
    collection.objects.link(obj)
    return obj


def look_at(obj, target):
    direction = Vector(target) - obj.location
    obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()


def flat_material(name, color, alpha=1.0, emissive=None, emissive_strength=0.0,
                   roughness=0.7, metallic=0.0, blended=False):
    mat = bpy.data.materials.new(name)
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = (*color, 1.0)
    bsdf.inputs["Roughness"].default_value = roughness
    bsdf.inputs["Metallic"].default_value = metallic
    bsdf.inputs["Alpha"].default_value = alpha
    if emissive:
        bsdf.inputs["Emission Color"].default_value = (*emissive, 1.0)
        bsdf.inputs["Emission Strength"].default_value = emissive_strength
    if alpha < 1.0 or blended:
        mat.surface_render_method = "BLENDED"
    return mat


def object_color_material(name, roughness=0.55, metallic=0.12):
    """Base color driven by each Object's .color -- lets many objects share one
    material while each renders its own per-instance voxel heat-map color."""
    mat = bpy.data.materials.new(name)
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    bsdf = nodes.get("Principled BSDF")
    objinfo = nodes.new("ShaderNodeObjectInfo")
    links.new(objinfo.outputs["Color"], bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = roughness
    bsdf.inputs["Metallic"].default_value = metallic
    return mat


def main():
    scene_json, out_dir, phases = parse_args()
    with open(scene_json, encoding="utf-8") as f:
        data = json.load(f)

    os.makedirs(out_dir, exist_ok=True)

    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    root = scene.collection

    site_w = data["site"]["width_ft"]
    site_l = data["site"]["length_ft"]
    garage_depth = data["garage_depth_ft"]

    # ── World / background (matches scene.background = 0xd6d1c8) ───────────
    world = bpy.data.worlds.new("PershingWorld")
    scene.world = world
    world.use_nodes = True
    bg = world.node_tree.nodes.get("Background")
    bg.inputs["Color"].default_value = (0xd6 / 255, 0xd1 / 255, 0xc8 / 255, 1.0)
    bg.inputs["Strength"].default_value = 1.0

    # ── Render settings ──────────────────────────────────────────────────
    scene.render.engine = "BLENDER_EEVEE"
    scene.render.resolution_x = 2400
    scene.render.resolution_y = 1500
    scene.render.image_settings.file_format = "PNG"
    try:
        scene.view_settings.view_transform = "AgX"
    except TypeError:
        scene.view_settings.view_transform = "Standard"

    # ── Camera (orthographic axonometric, matches index.html's camera) ─────
    cam_data = bpy.data.cameras.new("MainCam")
    cam_data.type = "ORTHO"
    cam_data.sensor_fit = "VERTICAL"
    cam_data.ortho_scale = 1300  # FRUSTUM_INIT (L3 context view), ft
    cam_data.clip_start = 0.1
    cam_data.clip_end = 10000
    cam_obj = bpy.data.objects.new("MainCam", cam_data)
    # Three.js: camera.position.set(W*0.9, L*0.7, L*0.9) in (x, y-up, z) ->
    # Blender (x, z, y-up) = (W*0.9, L*0.9, L*0.7)
    cam_obj.location = (site_w * 0.9, site_l * 0.9, site_l * 0.7)
    root.objects.link(cam_obj)
    scene.camera = cam_obj
    # controls.target.set(0, -garage_depth*0.5, 0) -> Blender (0, 0, -garage_depth*0.5)
    look_at(cam_obj, (0, 0, -garage_depth * 0.5))

    # ── Lights (key sun + cool fill sun, both aimed at site center) ─────────
    def add_sun(name, position, color, strength):
        sun_data = bpy.data.lights.new(name, type="SUN")
        sun_data.color = color
        sun_data.energy = strength
        sun_obj = bpy.data.objects.new(name, sun_data)
        sun_obj.location = position
        root.objects.link(sun_obj)
        look_at(sun_obj, (0, 0, 0))
        return sun_obj

    # sun.position.set(L*0.5, L*0.9, L*0.3) -> Blender (L*0.5, L*0.3, L*0.9)
    add_sun("KeySun", (site_l * 0.5, site_l * 0.3, site_l * 0.9),
            (0xff / 255, 0xf5 / 255, 0xe0 / 255), 3.0)
    # fill.position.set(-L*0.4, L*0.3, -L*0.4) -> Blender (-L*0.4, -L*0.4, L*0.3)
    add_sun("FillSun", (-site_l * 0.4, -site_l * 0.4, site_l * 0.3),
            (0xdd / 255, 0xe8 / 255, 1.0), 1.0)

    static = data["static"]

    # ── Structural columns (274 real, linked duplicates of one mesh) ───────
    column_mat = flat_material("ColumnMat", static["column_color"], roughness=0.7, metallic=0.08)
    column_mesh = build_mesh("ColumnMesh", static["column_mesh"]["vertices"], static["column_mesh"]["faces"])
    column_mesh.materials.append(column_mat)
    columns_coll = bpy.data.collections.new("Columns")
    root.children.link(columns_coll)
    for i, pos in enumerate(static["column_positions"]):
        new_object(f"Column_{i:03d}", column_mesh, columns_coll, location=pos)

    # ── Tunnel + entrance (real meshes, always visible, emissive accents) ──
    tunnel_mat = flat_material("TunnelMat", static["tunnel_color"],
                                emissive=static["tunnel_emissive"], emissive_strength=1.2, roughness=0.3)
    tunnel_mesh = build_mesh("TunnelMesh", static["tunnel_mesh"]["vertices"], static["tunnel_mesh"]["faces"])
    tunnel_mesh.materials.append(tunnel_mat)
    new_object("Tunnel", tunnel_mesh, root)

    entrance_mat = flat_material("EntranceMat", static["entrance_color"],
                                  emissive=static["entrance_emissive"], emissive_strength=1.0, roughness=0.35)
    entrance_mesh = build_mesh("EntranceMesh", static["entrance_mesh"]["vertices"], static["entrance_mesh"]["faces"])
    entrance_mesh.materials.append(entrance_mat)
    new_object("Entrance", entrance_mesh, root)

    # ── Spiral ramp clusters (real meshes) ──────────────────────────────────
    ramp_mat = flat_material("RampMat", static["ramp_color"], roughness=0.8, metallic=0.05)
    for cluster_key, levels in static["ramps"].items():
        for i, level in enumerate(levels):
            mesh = build_mesh(f"Ramp_{cluster_key}_{i}", level["vertices"], level["faces"])
            mesh.materials.append(ramp_mat)
            new_object(f"Ramp_{cluster_key}_{i}", mesh, root)

    # ── Parking garage floor plates (translucent) ───────────────────────────
    for i, plate in enumerate(static["floor_plates"]):
        mat = flat_material(f"FloorPlateMat_{i}", plate["color"], alpha=plate["opacity"], roughness=0.8)
        mesh = plane_mesh(f"FloorPlate_{i}", plate["w"], plate["l"])
        mesh.materials.append(mat)
        new_object(f"FloorPlate_{i}", mesh, root, location=(0, 0, plate["z"]))

    # ── Street tunnel connector (Phase 3 only) ──────────────────────────────
    tc = static["tunnel_connector"]
    tc_mat = flat_material("TunnelConnectorMat", [0x2a / 255, 0x2a / 255, 0x33 / 255],
                            alpha=0.55, roughness=0.6, metallic=0.1)
    tc_mesh = box_mesh("TunnelConnector", tc["w"], tc["l"], tc["h"])
    tc_mesh.materials.append(tc_mat)
    tunnel_connector_obj = new_object("TunnelConnector", tc_mesh, root, location=tc["center"])

    # ── "Current" as-built group (context/yellow/item meshes + trees) ──────
    current = data["current"]
    current_coll = bpy.data.collections.new("Current")
    root.children.link(current_coll)

    if current["context_mesh"]:
        mat = flat_material("ContextMat", [0xb7 / 255, 0xb0 / 255, 0xa3 / 255], roughness=0.85, metallic=0.02)
        mesh = build_mesh("ContextMesh", current["context_mesh"]["vertices"], current["context_mesh"]["faces"])
        mesh.materials.append(mat)
        new_object("ContextMesh", mesh, current_coll)

    if current["yellow_mesh"]:
        mat = flat_material("YellowMat", current["yellow_color"], roughness=0.7)
        mesh = build_mesh("YellowMesh", current["yellow_mesh"]["vertices"], current["yellow_mesh"]["faces"])
        mesh.materials.append(mat)
        new_object("YellowMesh", mesh, current_coll)

    for item_name, submeshes in current["items"].items():
        for j, sm in enumerate(submeshes):
            mat = flat_material(f"{item_name}_{j}_Mat", sm["color"], roughness=0.8, metallic=0.02)
            mesh = build_mesh(f"{item_name}_{j}", sm["vertices"], sm["faces"])
            mesh.materials.append(mat)
            new_object(f"{item_name}_{j}", mesh, current_coll)

    # Tree billboards: two crossed alpha-cutout planes per tree.
    tree_tex_cache = {}
    tree_dir = os.path.join(os.path.dirname(os.path.abspath(scene_json)), "..", "data", "PershingMetabolizer")
    for i, t in enumerate(current["trees"]):
        tex_path = os.path.join(tree_dir, t["texture"])
        if t["texture"] not in tree_tex_cache:
            mat = bpy.data.materials.new(f"Tree_{t['texture']}")
            mat.surface_render_method = "DITHERED"
            nodes = mat.node_tree.nodes
            links = mat.node_tree.links
            bsdf = nodes.get("Principled BSDF")
            if os.path.exists(tex_path):
                teximg = bpy.data.images.load(tex_path)
                texnode = nodes.new("ShaderNodeTexImage")
                texnode.image = teximg
                links.new(texnode.outputs["Color"], bsdf.inputs["Base Color"])
                links.new(texnode.outputs["Alpha"], bsdf.inputs["Alpha"])
            tree_tex_cache[t["texture"]] = mat
        mat = tree_tex_cache[t["texture"]]
        mesh = plane_mesh(f"Tree_{i}_A", t["width"], t["height"])
        mesh.materials.append(mat)
        # PlaneGeometry is built in XY; rotate to stand vertically (XZ facing +Y).
        obj_a = new_object(f"Tree_{i}_A", mesh, current_coll, location=t["center"])
        obj_a.rotation_euler = (math.pi / 2, 0, 0)
        obj_b = new_object(f"Tree_{i}_B", mesh, current_coll, location=t["center"])
        obj_b.rotation_euler = (math.pi / 2, 0, math.pi / 2)

    # ── Voxel heat-map grid (shared objects, updated per phase before render) ─
    voxel_ft = data["voxel_ft"]
    voxel_mat = object_color_material("VoxelMat")
    voxel_unit = box_mesh("VoxelUnit", 1, 1, 1)
    voxel_unit.materials.append(voxel_mat)
    voxel_coll = bpy.data.collections.new("Voxels")
    root.children.link(voxel_coll)

    n_voxels = len(data["phases"]["1"]["voxels"])
    voxel_objects = []
    for i in range(n_voxels):
        obj = bpy.data.objects.new(f"voxel_{i:04d}", voxel_unit)
        obj.color = (0.76, 0.74, 0.71, 1.0)
        voxel_coll.objects.link(obj)
        voxel_objects.append(obj)

    def apply_voxel_phase(phase_key):
        voxels = data["phases"]["1" if phase_key == "current" else phase_key]["voxels"]
        for obj, v in zip(voxel_objects, voxels):
            obj.location = v["pos"]
            obj.scale = (voxel_ft, voxel_ft, v["slab_h"])
            obj.color = (*v["color"], 1.0)

    # ── Render each requested phase ─────────────────────────────────────────
    for phase in phases:
        apply_voxel_phase(phase)
        current_coll.hide_render = (phase != "current")
        tunnel_connector_obj.hide_render = (phase != "3")

        out_path = os.path.join(out_dir, f"phase_{phase}.png")
        scene.render.filepath = out_path
        bpy.ops.render.render(write_still=True)
        print(f"Rendered {out_path}")


if __name__ == "__main__":
    main()
