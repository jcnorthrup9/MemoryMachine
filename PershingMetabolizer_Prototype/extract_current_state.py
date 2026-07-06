"""
One-time offline extraction: pull the "Current" (existing, as-built) site geometry out of
PershingCurrentMetabolism.obj -- plaza, pool, sport court -- plus any number of separately
exported item files (PershingWallsMetabolism.obj, PershingFountainMetabolism.obj,
PershingTable3Metabolism.obj, etc.) into a compact JSON the browser prototype can load
directly (no multi-MB OBJ ever touching the browser).

Coordinate frame: same file family / same Rhino origin as PershingMetablismGridBase.obj.
Verified (not assumed) by converting raw vertex bboxes through the already-established
site-local offset (site_min_x=-2575.338, site_min_z=626.525, grade_y_raw=3.728271245956421,
taken directly from real_geometry.json) and confirming the result lands almost exactly on the
known 354.14 x 602.40 ft terrace footprint.

Item files are auto-discovered: any "Pershing*Metabolism.obj" in OBJ_DIR other than the main
PershingCurrentMetabolism.obj and the unrelated PershingMetablismGridBase.obj (a much larger,
differently-purposed grid file, not site furniture). Each item file is parsed generically into
one flat-color sub-mesh per material, using that file's own .mtl Kd value -- no hardcoded
per-object names or colors, since the user is actively dropping in more separated exports
(walls, fountain, plinth, tables, individual table re-exports, elevators, trees, ...) as they
work, and each new file should "just work" without code changes.

Multi-object batch exports were found to weld near-coincident vertices ACROSS objects in
Rhino's OBJ exporter, visibly dragging unrelated meshes toward each other. Exporting each
object as its own file avoids that cross-object welding -- hence the move to many small
per-item OBJ files instead of one merged export.

Trees are handled specially (cross-billboard quads, by material name) wherever they're found
-- originally embedded in the main file (now empty there), now in their own
PershingTreesMetabolism.obj.

Any item geometry that's ALSO still embedded in the main file's merged "Default" blob (e.g.
the fountain was, before being separated out) is excluded from the merged context mesh by raw
vertex-bbox overlap against the item files, so it isn't rendered twice.
"""
import glob
import json
import re
import sys
import time
import os

OBJ_DIR = r"C:\Users\john\MemoryMachine\data\PershingMetabolizer\OBJ"
OBJ_PATH = os.path.join(OBJ_DIR, "PershingCurrentMetabolism.obj")
OUT_PATH = r"C:\Users\john\MemoryMachine\PershingMetabolizer_Prototype\current_state.json"

# Files matching Pershing*Metabolism.obj in OBJ_DIR that are NOT separate site-furniture items
# and should never be auto-discovered as one.
EXCLUDE_ITEM_NAMES = {"current", "metablismgridbase"}

# Same reference frame as real_geometry.json -- verified above, not re-derived.
SITE_MIN_X = -2575.338
SITE_MIN_Z = 626.525
GRADE_Y_RAW = 3.728271245956421

TREE_MATERIALS = {"tree4", "tree7", "tree9", "palm_tree", "eik3_ic"}
TREE_TEXTURE = {
    "tree4": "tree4.png",
    "tree7": "tree7.png",
    "tree9": "tree9.png",
    "palm_tree": "palm_tree.png",
    "eik3_ic": "eik3_ic.png",
}


def site_local(x, y, z):
    return (x - SITE_MIN_X, y - GRADE_Y_RAW, z - SITE_MIN_Z)


def item_name_from_path(path):
    """PershingWallsMetabolism.obj -> 'walls', PershingTable3Metabolism.obj -> 'table3'."""
    base = os.path.splitext(os.path.basename(path))[0]
    name = re.sub(r"^Pershing", "", base)
    name = re.sub(r"Metabolism$", "", name)
    return name.lower()


def discover_item_files():
    found = []
    for path in glob.glob(os.path.join(OBJ_DIR, "Pershing*Metabolism.obj")):
        name = item_name_from_path(path)
        if name in EXCLUDE_ITEM_NAMES:
            continue
        found.append((name, path))
    return sorted(found)


def parse_mtl_colors(mtl_path):
    """material name -> [r,g,b] Kd. Missing/unreadable .mtl -> {}."""
    colors = {}
    cur = None
    if not os.path.exists(mtl_path):
        return colors
    with open(mtl_path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            if line.startswith("newmtl "):
                cur = line.split(None, 1)[1].strip()
            elif line.startswith("Kd ") and cur:
                p = line.split()
                colors[cur] = [float(p[1]), float(p[2]), float(p[3])]
    return colors


def parse_objects(path):
    """Yield (material, verts, faces) per o/g-delimited object block in an OBJ file."""
    cur_mat = [None]
    cur_verts = []
    cur_faces = []
    yield_buf = []

    def flush():
        if cur_verts:
            yield_buf.append((cur_mat[0], list(cur_verts), list(cur_faces)))
        cur_verts.clear()
        cur_faces.clear()

    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            if line.startswith("o ") or line.startswith("g "):
                flush()
                cur_mat[0] = None
            elif line.startswith("usemtl "):
                cur_mat[0] = line.split(None, 1)[1].strip()
            elif line.startswith("v "):
                p = line.split()
                cur_verts.append((float(p[1]), float(p[2]), float(p[3])))
            elif line.startswith("f "):
                idxs = [int(tok.split("/")[0]) for tok in line.split()[1:]]
                cur_faces.append(idxs)
    flush()
    return yield_buf


def raw_bbox(verts):
    xs = [v[0] for v in verts]; ys = [v[1] for v in verts]; zs = [v[2] for v in verts]
    return (min(xs), min(ys), min(zs), max(xs), max(ys), max(zs))


def union_bbox(a, b):
    if a is None:
        return b
    return (min(a[0], b[0]), min(a[1], b[1]), min(a[2], b[2]),
            max(a[3], b[3]), max(a[4], b[4]), max(a[5], b[5]))


def bbox_overlaps(a, b):
    return not (a[3] < b[0] or a[0] > b[3] or a[4] < b[1] or a[1] > b[4] or a[5] < b[2] or a[2] > b[5])


def append_mesh(verts_out, faces_out, verts, faces):
    base = len(verts_out)
    for (x, y, z) in verts:
        verts_out.append(list(site_local(x, y, z)))
    for f in faces:
        tri = [base + (i - 1) for i in f]
        if len(tri) == 3:
            faces_out.append(tri)
        elif len(tri) == 4:
            faces_out.append([tri[0], tri[1], tri[2]])
            faces_out.append([tri[0], tri[2], tri[3]])


def extract_trees(path):
    trees = []
    for mat, verts, faces in parse_objects(path):
        if mat not in TREE_MATERIALS or not verts:
            continue
        sx0, sy0, sz0 = site_local(*raw_bbox(verts)[:3])
        sx1, sy1, sz1 = site_local(*raw_bbox(verts)[3:])
        trees.append({
            "mat": mat,
            "texture": TREE_TEXTURE[mat],
            "x": round((sx0 + sx1) / 2.0, 3),
            "z": round((sz0 + sz1) / 2.0, 3),
            "width": round(max(sx1 - sx0, sz1 - sz0), 3),
            "baseHeight": round(sy0, 3),
            "topHeight": round(sy1, 3),
        })
    return trees


def extract():
    """Parse the main OBJ plus all auto-discovered item OBJs and write OUT_PATH."""
    trees = []
    context_verts, context_faces = [], []
    yellow_verts, yellow_faces = [], []
    items = {}          # name -> list of {verts, faces, color}
    exclude_bbox = None  # union of all non-tree item file bboxes, for de-dup against the main file

    for name, path in discover_item_files():
        mtl_path = os.path.splitext(path)[0] + ".mtl"
        mtl_colors = parse_mtl_colors(mtl_path)
        objects = parse_objects(path)

        if name == "trees":
            trees.extend(extract_trees(path))
            continue

        submeshes = {}
        for mat, verts, faces in objects:
            if not verts:
                continue
            if mat in TREE_MATERIALS:
                trees.extend(extract_trees(path))
                continue
            key = mat or "Default"
            if key not in submeshes:
                submeshes[key] = {
                    "verts": [], "faces": [],
                    "color": mtl_colors.get(key, [0.7, 0.7, 0.7]),
                }
            append_mesh(submeshes[key]["verts"], submeshes[key]["faces"], verts, faces)
            exclude_bbox = union_bbox(exclude_bbox, raw_bbox(verts))

        if submeshes:
            items[name] = list(submeshes.values())

    # PershingCurrentMetabolism.obj has been retired -- the user now exports every site
    # element as its own item file instead, to avoid the multi-object export's cross-object
    # vertex welding and to cut down on file size. context_mesh/yellow_mesh stay empty
    # (and just don't get added in rebuildCurrentGroup) when this file isn't present.
    if os.path.exists(OBJ_PATH):
        for mat, verts, faces in parse_objects(OBJ_PATH):
            if not verts:
                continue
            if mat in TREE_MATERIALS:
                trees.extend(extract_trees(OBJ_PATH))
            elif mat == "Default":
                if exclude_bbox is not None and bbox_overlaps(raw_bbox(verts), exclude_bbox):
                    continue   # already covered by a dedicated item export -- skip to avoid duplicates
                append_mesh(context_verts, context_faces, verts, faces)
            elif mat == "yellow":
                append_mesh(yellow_verts, yellow_faces, verts, faces)
            elif mat is not None:
                continue   # materials with no generic-item handling yet -- dropped, not silently lossy elsewhere
            # Default-less / Google Earth Snapshot1 / diffuse_250_250_250_255 objects are
            # skipped: confirmed too small (<=4 verts) or not part of the rendered plaza context.

    out = {
        "_meta": (
            "Extracted from PershingCurrentMetabolism.obj plus every auto-discovered "
            "Pershing*Metabolism.obj item file in the OBJ folder, all in the SAME site-local frame "
            "as real_geometry.json (site_min_x=-2575.338, site_min_z=626.525, "
            "grade_y_raw=3.728271245956421). Trees are Rhino cross-billboards (2 perpendicular quads "
            "each); stored here as instance position + height range only. Context mesh is the merged "
            "'Default'-material geometry from the main file MINUS anything that overlaps a dedicated "
            "item file's bbox (avoids duplicate/z-fighting geometry, e.g. the fountain). 'items' is "
            "keyed by item name (derived from each file's name, e.g. PershingWallsMetabolism.obj -> "
            "'walls'), each a list of flat-color sub-meshes split by material, colored from that "
            "file's own .mtl Kd value."
        ),
        "trees": trees,
        "context_mesh": {"verts": context_verts, "faces": context_faces},
        "yellow_mesh": {"verts": yellow_verts, "faces": yellow_faces},
        "items": items,
    }

    # Write atomically so the dev server / browser never sees a half-written file
    # mid-poll (the browser polls this same path every few seconds in watch mode).
    tmp_path = OUT_PATH + ".tmp"
    with open(tmp_path, "w") as f:
        json.dump(out, f)
    os.replace(tmp_path, OUT_PATH)

    item_vert_count = sum(len(sm["verts"]) for subs in items.values() for sm in subs)
    return (len(trees), len(context_verts), len(context_faces), len(yellow_verts), len(yellow_faces),
            len(items), item_vert_count)


def report(counts):
    nt, ncv, ncf, nyv, nyf, n_items, item_verts = counts
    print(f"[{time.strftime('%H:%M:%S')}] trees={nt} context_verts={ncv} context_faces={ncf} "
          f"yellow_verts={nyv} yellow_faces={nyf} items={n_items} item_verts={item_verts} -> {OUT_PATH}")


def watch_signature():
    """mtime + size per Pershing*Metabolism.obj/.mtl in OBJ_DIR, plus the file set itself --
    changes whenever a file is added, removed, or (re-)written, even mid-write."""
    sig = {}
    for path in glob.glob(os.path.join(OBJ_DIR, "Pershing*Metabolism.obj")) + \
                glob.glob(os.path.join(OBJ_DIR, "Pershing*Metabolism.mtl")):
        try:
            st = os.stat(path)
            sig[path] = (st.st_mtime, st.st_size)
        except FileNotFoundError:
            pass
    return sig


if __name__ == "__main__":
    if "--watch" in sys.argv:
        print(f"Watching {OBJ_DIR} for new/changed Pershing*Metabolism.obj/.mtl files (poll every 2s). "
              f"Ctrl+C to stop.")
        last_sig = None
        while True:
            sig = watch_signature()
            if sig != last_sig:
                # Small settle delay: large OBJ exports can still be mid-write when mtime first changes.
                time.sleep(0.5)
                sig2 = watch_signature()
                if sig2 == sig:   # stable -- safe to extract
                    last_sig = sig2
                    try:
                        report(extract())
                    except Exception as e:
                        print(f"[{time.strftime('%H:%M:%S')}] extraction failed (file likely still being written): {e}")
            time.sleep(2)
    else:
        report(extract())
