"""
apply_facade_materials.py
---------------------------
Run via: python rhino/run_rhino_script.py rhino/apply_facade_materials.py
(the win32com/_-ScriptEditor Run COM bridge), AFTER any Grasshopper facade
bake (FidelityGrid1's PM_FacadePanelizer, FidelityGrid2's PM_FacadeScreen,
etc.) has written geometry into Detailed_Facades::*/Detailed_Screen::*
layers.

Why this exists: materials created and assigned from *inside* a Grasshopper
Python 3 Script component (via RhinoCommon Material/PhysicallyBased +
Layer.RenderMaterialIndex) set the data correctly -- verifiable via
Cordyceps' rhino_render material_list -- but do not visibly render in
Rhino's Rendered display mode. Confirmed by a side-by-side test: identical
RhinoCommon material-creation code, run through this classic scripting
engine instead of Grasshopper's Python 3 engine, rendered correctly on the
first try. Root cause not fully diagnosed -- some display-pipeline
notification the classic engine triggers that Grasshopper's Python 3
engine doesn't -- but the workaround is reliable. This script redoes the
material step through that working pathway.

This must be re-run after every re-bake in Grasshopper, since each bake's
own clear_previous_bake() + find_or_make_material() regenerates objects
with the (invisible) in-Grasshopper material assignment.

Two more things learned the hard way, worth knowing before touching this:
  - This document's Materials table is enormous (13,000+ entries -- long
    predating anything built this session, likely per-object duplicates
    accumulated over the OBJ-import pipeline's history). find_or_make_material
    UPDATES an existing same-named entry IN PLACE via Materials.Modify()
    rather than deleting and recreating it -- Materials.Delete() on an
    entry already referenced by hundreds of objects/layers was observed to
    fail (silently or by halting the rest of the script), leaving orphaned
    "(1)"-suffixed duplicates behind. Modify() has no such in-use
    restriction and is the only approach confirmed reliable here.
  - Materials created purely through this classic-engine path (via
    doc.Materials.Add/Modify) do NOT show up in Cordyceps' rhino_render
    material_list/material_apply -- those tools appear scoped to the
    separate RenderMaterial/RenderContent table, which classic-engine
    Material.Add() does not populate. This does not affect whether the
    material actually renders (it does -- that's the whole point of this
    script), only whether Cordyceps' own tools can see/target it by name.
    Verify success via a viewport capture, not via rhino_render actions.
"""
import Rhino
import System.Drawing
import scriptcontext as sc

doc = sc.doc

print("=" * 60)
print("apply_facade_materials -- starting")
print("=" * 60)


def find_or_make_material(name, color_hex, metallic=0.0, roughness=0.3, transparency=0.0):
    mat = Rhino.DocObjects.Material()
    mat.Name = name
    c = color_hex.lstrip("#")
    r, g, b = int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)
    color = System.Drawing.Color.FromArgb(r, g, b)
    mat.DiffuseColor = color
    mat.Transparency = transparency
    mat.Reflectivity = metallic
    pbr = mat.PhysicallyBased
    if pbr is None:
        mat.ToPhysicallyBased()
        pbr = mat.PhysicallyBased
    if pbr is not None:
        pbr.BaseColor = Rhino.Display.Color4f(color)
        pbr.Metallic = metallic
        pbr.Roughness = roughness
        pbr.Opacity = max(0.0, 1.0 - transparency)

    existing_idx = -1
    for i in range(doc.Materials.Count):
        if doc.Materials[i].Name == name:
            existing_idx = i
            break
    if existing_idx >= 0:
        doc.Materials.Modify(mat, existing_idx, True)
        return existing_idx
    return doc.Materials.Add(mat)


def apply_to_layer(full_path, mat_idx):
    idx = doc.Layers.FindByFullPath(full_path, -1)
    if idx < 0:
        return 0
    layer = doc.Layers[idx]
    layer.RenderMaterialIndex = mat_idx
    count = 0
    # Belt-and-suspenders: also set MaterialSource=MaterialFromObject on
    # every existing object, not just relying on MaterialFromLayer
    # inheritance, since this classic-engine pathway is the one confirmed
    # to actually render.
    for rh_obj in doc.Objects.FindByLayer(layer):
        attrs = rh_obj.Attributes
        attrs.MaterialSource = Rhino.DocObjects.ObjectMaterialSource.MaterialFromObject
        attrs.MaterialIndex = mat_idx
        doc.Objects.ModifyAttributes(rh_obj, attrs, True)
        count += 1
    return count


glass_idx = find_or_make_material("PM_Glass_Panel", "#CFE6E4", metallic=0.0, roughness=0.05, transparency=0.8)
mullion_idx = find_or_make_material("PM_Mullion_Metal", "#4A4A4A", metallic=0.9, roughness=0.3, transparency=0.0)
hybrid_idx = find_or_make_material("PM_Hybrid_Overlap", "#553C5F", metallic=0.2, roughness=0.55, transparency=0.0)
scaffold_idx = find_or_make_material("PM_Scaffold_Timber", "#B07C4A", metallic=0.0, roughness=0.75, transparency=0.0)
pin_coarse_idx = find_or_make_material("PM_Pin_Coarse", "#5A5A5A", metallic=0.1, roughness=0.7, transparency=0.0)
pin_fine_idx = find_or_make_material("PM_Pin_Fine", "#2FA6A0", metallic=0.2, roughness=0.4, transparency=0.0)
growth_major_idx = find_or_make_material("PM_Growth_Major", "#5A5A5A", metallic=0.1, roughness=0.7, transparency=0.0)
growth_mullion_idx = find_or_make_material("PM_Growth_Mullion", "#C97B3D", metallic=0.0, roughness=0.6, transparency=0.0)
print("PM_Glass_Panel material index: {}".format(glass_idx))
print("PM_Mullion_Metal material index: {}".format(mullion_idx))
print("PM_Hybrid_Overlap material index: {}".format(hybrid_idx))
print("PM_Scaffold_Timber material index: {}".format(scaffold_idx))
print("PM_Pin_Coarse material index: {}".format(pin_coarse_idx))
print("PM_Pin_Fine material index: {}".format(pin_fine_idx))
print("PM_Growth_Major material index: {}".format(growth_major_idx))
print("PM_Growth_Mullion material index: {}".format(growth_mullion_idx))

PROGRAM_LAYERS = [
    "PracticeSpace", "ComputerTechSpace", "ArtsAndCraftsStudio",
    "WorkOutEquipment", "PicnicGrillSpace", "Greenspace",
    "Skatepark", "CommunityCenter",
]


def apply_layer_set(root, name_mat_pairs):
    applied_layers, applied_objects = 0, 0
    for name in PROGRAM_LAYERS:
        for suffix, mat_idx in name_mat_pairs:
            full_path = "{}::{}::{}".format(root, name, suffix)
            n = apply_to_layer(full_path, mat_idx)
            if n > 0 or doc.Layers.FindByFullPath(full_path, -1) >= 0:
                applied_layers += 1
                applied_objects += n
    return applied_layers, applied_objects


fg1_layers, fg1_objects = apply_layer_set(
    "Detailed_Facades", (("Panels", glass_idx), ("Mullions", mullion_idx)))
print("FidelityGrid1 (Detailed_Facades): applied to {} layers, {} objects".format(fg1_layers, fg1_objects))

fg2_layers, fg2_objects = apply_layer_set(
    "Detailed_Screen",
    (("Screen", mullion_idx), ("ScreenHybrid", hybrid_idx), ("Standoffs", mullion_idx)))
print("FidelityGrid2 (Detailed_Screen): applied to {} layers, {} objects".format(fg2_layers, fg2_objects))

scaffold_objects = sum(apply_to_layer("Detailed_Scaffold::Members::" + ax, scaffold_idx)
                        for ax in ("X", "Y", "Z"))
print("GrowthScaffold (Detailed_Scaffold, disabled/superseded): applied to {} objects".format(scaffold_objects))

scaffoldframe_layers, scaffoldframe_objects = 0, 0
for name in PROGRAM_LAYERS:
    full_path = "Detailed_ScaffoldFrame::{}::Members".format(name)
    n = apply_to_layer(full_path, scaffold_idx)
    if n > 0 or doc.Layers.FindByFullPath(full_path, -1) >= 0:
        scaffoldframe_layers += 1
        scaffoldframe_objects += n
print("ScaffoldFrame (Detailed_ScaffoldFrame): applied to {} layers, {} objects".format(
    scaffoldframe_layers, scaffoldframe_objects))

pingrid_layers, pingrid_objects = 0, 0
for i in range(50):
    scaffold_path = "Detailed_PinGrid::Footprint{}::Scaffold".format(i)
    mullion_path = "Detailed_PinGrid::Footprint{}::Mullion".format(i)
    if doc.Layers.FindByFullPath(scaffold_path, -1) < 0 and doc.Layers.FindByFullPath(mullion_path, -1) < 0:
        continue
    n_s = apply_to_layer(scaffold_path, pin_coarse_idx)
    n_m = apply_to_layer(mullion_path, pin_fine_idx)
    pingrid_layers += 2
    pingrid_objects += n_s + n_m
print("PinGrid (Detailed_PinGrid): applied to {} layers, {} objects".format(pingrid_layers, pingrid_objects))

growth_layers, growth_objects = 0, 0
for i in range(50):
    major_path = "Detailed_GrowthColumns::Footprint{}::Major".format(i)
    mullion_path = "Detailed_GrowthColumns::Footprint{}::MullionPoints".format(i)
    if doc.Layers.FindByFullPath(major_path, -1) < 0 and doc.Layers.FindByFullPath(mullion_path, -1) < 0:
        continue
    n_major = apply_to_layer(major_path, growth_major_idx)
    n_mullion = apply_to_layer(mullion_path, growth_mullion_idx)
    growth_layers += 2
    growth_objects += n_major + n_mullion
print("GrowthColumns (Detailed_GrowthColumns): applied to {} layers, {} objects".format(growth_layers, growth_objects))

doc.Views.Redraw()
print("\n" + "=" * 60)
print("DONE -- check Rendered viewport for glass vs metal distinction.")
print("=" * 60)
