"""
assign_layers_from_obj_names.py
--------------------------------
Run this inside Rhino 8 via:  Tools > Python Script > Run...  (or RunPythonScript)
AFTER opening/importing a headless-exported OBJ (e.g. from
blender/pershing_headless_build.py's bpy.ops.wm.obj_export call).

Why this exists: double-clicking/drag-and-dropping an OBJ into Rhino skips
the Import options dialog entirely and silently uses default settings, which
typically dump every object onto one layer -- even though Rhino's OBJ reader
still sets each object's Name attribute from the OBJ's per-object ("o") line.
This script doesn't depend on how the file got imported or what the Blender
exporter did or didn't write for grouping ("o" vs "g" vs materials) -- it
just reads back whatever Name each object already has (which Rhino DOES
preserve on import) and builds one real layer per unique name, moving every
object onto its matching layer. Guaranteed to work regardless of Rhino
version/import-dialog quirks, since it operates purely on already-imported
document state.

Objects with no Name (blank) get parked on a single fallback layer
("Unlabeled_OBJ_Import") rather than silently left wherever they landed, so
nothing goes missing without at least being visible as a group to sort out.

No geometry is touched or moved -- only object Layer assignments and the
layer table change.
"""

import rhinoscriptsyntax as rs
import scriptcontext as sc
import Rhino

FALLBACK_LAYER = "Unlabeled_OBJ_Import"

# Rhino layer full-paths use "::" as the parent/child separator and disallow
# a handful of characters in a single layer name -- OBJ object names coming
# out of Blender are plain identifiers (e.g. "mm_struct_restroom_pod",
# "amp_tier_ring_0_R") so collisions are unlikely, but sanitize defensively
# rather than let Layers.Add silently fail on an unexpected name.
_INVALID_CHARS = '<>/\\":|?*'


def _sanitize(name):
    cleaned = "".join(("_" if c in _INVALID_CHARS else c) for c in name)
    return cleaned.replace("::", "__") or FALLBACK_LAYER


def _ensure_layer(name):
    idx = sc.doc.Layers.FindByFullPath(name, -1)
    if idx >= 0:
        return sc.doc.Layers[idx].Id
    new_layer = Rhino.DocObjects.Layer()
    new_layer.Name = name
    idx = sc.doc.Layers.Add(new_layer)
    if idx < 0:
        # Add() returns -1 on a genuine failure (not "already exists" --
        # that's handled by the FindByFullPath check above), so this is
        # worth a loud warning rather than a silent skip.
        print("  [WARN] Could not create layer: {}".format(name))
        return None
    return sc.doc.Layers[idx].Id


def main():
    print("=" * 60)
    print("assign_layers_from_obj_names — starting")
    print("=" * 60)

    obj_ids = rs.AllObjects()
    if not obj_ids:
        print("[INFO] No objects in the current document. Nothing to do.")
        return

    layer_counts = {}
    moved = 0

    for obj_id in obj_ids:
        raw_name = rs.ObjectName(obj_id)
        layer_name = _sanitize(raw_name) if raw_name else FALLBACK_LAYER

        if _ensure_layer(layer_name) is None:
            continue

        # rs.ObjectLayer is a no-op if the object is already on this layer,
        # so no need to check current layer first -- simpler and avoids
        # relying on RhinoCommon Layer-index/Guid comparison details.
        rs.ObjectLayer(obj_id, layer_name)
        moved += 1
        layer_counts[layer_name] = layer_counts.get(layer_name, 0) + 1

    sc.doc.Views.Redraw()

    print("\nLayers created/used ({} total):".format(len(layer_counts)))
    for name, count in sorted(layer_counts.items()):
        flag = "  <- unnamed objects, check these" if name == FALLBACK_LAYER else ""
        print("  {:40s}  {} object(s){}".format(name, count, flag))

    print("\n" + "=" * 60)
    print("DONE — {} object(s) assigned to their name-matched layer.".format(moved))
    print("=" * 60)


main()
