"""
One-time offline extraction: pull real column/tunnel/entrance/ramp geometry out of
PershingMetablismGridBase.obj and the real site footprint out of its own terrace
slabs, write a small JSON the browser prototype can load directly (no OBJLoader,
no 68MB/1.7GB file ever touching the browser).
"""
import json
import os

OBJ_PATH = r"D:\MemoryMachine\data\PershingMetabolizer\OBJ\PershingMetablismGridBase.obj"
OUT_PATH = r"D:\MemoryMachine\PershingMetabolizer_Prototype\real_geometry.json"

TUNNEL_NAME = "object_1"
SECONDARY_ENTRANCE_NAME = "object_2"
TERRACE_NAMES = {"object_3", "object_4", "object_5", "object_6"}
RAMP_CLUSTER_A = ["object_7", "object_8", "object_9"]
RAMP_CLUSTER_B = ["object_10", "object_11", "object_12"]
COLUMN_PROTOTYPE_NAME = "object_13"

global_verts = []          # 1-based via index+1
obj_vstart = {}            # name -> first global vertex index (1-based)
obj_vcount = {}            # name -> count of vertices
obj_faces = {}             # name -> list of [global_idx,...] (0-based after conversion)
order = []

cur = None
with open(OBJ_PATH, "r", encoding="utf-8", errors="ignore") as f:
    for line in f:
        if line.startswith("o ") or line.startswith("g "):
            cur = line[2:].strip()
            if cur not in obj_vstart:
                order.append(cur)
                obj_vstart[cur] = None
                obj_vcount[cur] = 0
                obj_faces[cur] = []
        elif line.startswith("v "):
            parts = line.split()
            x, y, z = float(parts[1]), float(parts[2]), float(parts[3])
            global_verts.append((x, y, z))
            if cur is not None:
                if obj_vstart[cur] is None:
                    obj_vstart[cur] = len(global_verts)  # 1-based index of this vertex
                obj_vcount[cur] += 1
        elif line.startswith("f "):
            if cur is not None:
                idxs = []
                for tok in line.split()[1:]:
                    vi = tok.split("/")[0]
                    idxs.append(int(vi))
                obj_faces[cur].append(idxs)

print(f"Parsed {len(global_verts)} total vertices, {len(order)} named objects.")


def mesh_for(name, recenter_xz=False, recenter_y_to_top=False):
    """Build a compact local-indexed mesh (verts + triangle faces) for one object."""
    faces = obj_faces[name]
    used = {}
    local_verts = []
    local_faces = []
    for f in faces:
        local_idxs = []
        for gi in f:
            if gi not in used:
                used[gi] = len(local_verts)
                local_verts.append(global_verts[gi - 1])
            local_idxs.append(used[gi])
        # triangulate the (possibly quad) face as a fan
        for k in range(1, len(local_idxs) - 1):
            local_faces.append([local_idxs[0], local_idxs[k], local_idxs[k + 1]])

    xs = [v[0] for v in local_verts]
    ys = [v[1] for v in local_verts]
    zs = [v[2] for v in local_verts]
    cx = sum(xs) / len(xs)
    cz = sum(zs) / len(zs)
    top_y = max(ys)

    ox = cx if recenter_xz else 0.0
    oz = cz if recenter_xz else 0.0
    oy = top_y if recenter_y_to_top else 0.0

    flat_verts = []
    for (x, y, z) in local_verts:
        flat_verts.extend([x - ox, y - oy, z - oz])

    flat_faces = []
    for tri in local_faces:
        flat_faces.extend(tri)

    return {
        "vertices": flat_verts,
        "faces": flat_faces,
        "vertex_count": len(local_verts),
        "face_count": len(local_faces),
        "centroid_xz": [cx, cz],
        "top_y": top_y,
        "bbox": {"min": [min(xs), min(ys), min(zs)], "max": [max(xs), max(ys), max(zs)]},
    }


# --- Site footprint from the terrace slabs (real rectangle, real OBJ-space) ---
tx, ty, tz = [], [], []
for name in TERRACE_NAMES:
    vs = global_verts[obj_vstart[name] - 1: obj_vstart[name] - 1 + obj_vcount[name]]
    tx.extend(v[0] for v in vs)
    ty.extend(v[1] for v in vs)
    tz.extend(v[2] for v in vs)
site_min_x, site_max_x = min(tx), max(tx)
site_min_z, site_max_z = min(tz), max(tz)
site_width_ft = site_max_x - site_min_x   # short axis, matches SVG width_ft
site_length_ft = site_max_z - site_min_z  # long axis, matches SVG height_ft
print(f"Real site footprint (from terrace slabs): {site_width_ft:.2f} x {site_length_ft:.2f} ft")
print(f"  origin (site-local 0,0) = OBJ-space ({site_min_x:.2f}, {site_min_z:.2f})")

# --- Column prototype mesh (recentered to its own base, local space) ---
column_mesh = mesh_for(COLUMN_PROTOTYPE_NAME, recenter_xz=True, recenter_y_to_top=True)
column_height_ft = column_mesh["bbox"]["max"][1] - column_mesh["bbox"]["min"][1]
print(f"Column prototype ({COLUMN_PROTOTYPE_NAME}): {column_mesh['vertex_count']}v "
      f"{column_mesh['face_count']}tris, height {column_height_ft:.2f}ft")

# --- All 274 real column positions (any object matching the mid-vertex-count bucket) ---
column_positions = []
for name in order:
    if name in (TUNNEL_NAME, SECONDARY_ENTRANCE_NAME, COLUMN_PROTOTYPE_NAME):
        pass  # column prototype itself still counts as a real column position too
    v = obj_vcount[name]
    if 500 < v <= 1300:
        vs = global_verts[obj_vstart[name] - 1: obj_vstart[name] - 1 + v]
        cx = sum(p[0] for p in vs) / len(vs)
        cz = sum(p[2] for p in vs) / len(vs)
        top_y = max(p[1] for p in vs)
        column_positions.append({
            "x": cx - site_min_x,
            "z": cz - site_min_z,
            "top_y": top_y,
        })
print(f"Real column positions extracted: {len(column_positions)}")

# --- Grade reference: every one of the 274 real columns shares the exact same
# top_y -- that's the real, unambiguous grade plane. Every depth below is
# expressed relative to it (positive = below grade). ---
grade_y = column_positions[0]["top_y"]
assert all(abs(c["top_y"] - grade_y) < 1e-3 for c in column_positions), "columns not coplanar"


def depth_below_grade(abs_y):
    return grade_y - abs_y


# --- Tunnel + secondary entrance + ramps, baked to site-local coords with y
# already shifted so 0 = grade (matching the recentered column mesh). ---
def mesh_site_local(name):
    m = mesh_for(name, recenter_xz=False, recenter_y_to_top=False)
    verts = m["vertices"]
    out = []
    for i in range(0, len(verts), 3):
        out.extend([verts[i] - site_min_x, verts[i + 1] - grade_y, verts[i + 2] - site_min_z])
    m["vertices"] = out
    m["centroid_xz"] = [m["centroid_xz"][0] - site_min_x, m["centroid_xz"][1] - site_min_z]
    return m

tunnel_mesh = mesh_site_local(TUNNEL_NAME)
secondary_entrance_mesh = mesh_site_local(SECONDARY_ENTRANCE_NAME)
ramp_meshes = {
    "cluster_a": [mesh_site_local(n) for n in RAMP_CLUSTER_A],
    "cluster_b": [mesh_site_local(n) for n in RAMP_CLUSTER_B],
}


# --- Tunnel endpoints: the box has two flat end-caps (split on raw z, which
# cleanly separates into two clusters ~900ft apart -- no ambiguity). ---
raw_tunnel_verts = global_verts[obj_vstart[TUNNEL_NAME] - 1: obj_vstart[TUNNEL_NAME] - 1 + obj_vcount[TUNNEL_NAME]]
end_hi = [v for v in raw_tunnel_verts if v[2] > 600]
end_lo = [v for v in raw_tunnel_verts if v[2] <= 600]


def endpoint(verts):
    xs = [v[0] for v in verts]
    zs = [v[2] for v in verts]
    top_y = max(v[1] for v in verts)
    return {
        "x": sum(xs) / len(xs) - site_min_x,
        "z": sum(zs) / len(zs) - site_min_z,
        "depth_ft": round(depth_below_grade(top_y), 2),
    }


ep_hi, ep_lo = endpoint(end_hi), endpoint(end_lo)
# don't guess which raw end is "shallow" -- compare the actual computed depths
shallow_ep, deep_ep = (ep_hi, ep_lo) if ep_hi["depth_ft"] < ep_lo["depth_ft"] else (ep_lo, ep_hi)
tunnel_endpoints = {"shallow": shallow_ep, "deep": deep_ep}
print(f"Tunnel endpoints (site-local, depth below grade): {tunnel_endpoints}")

# --- Secondary entrance: single small chamber, just centroid + depth range. ---
raw_entrance_verts = global_verts[obj_vstart[SECONDARY_ENTRANCE_NAME] - 1:
                                  obj_vstart[SECONDARY_ENTRANCE_NAME] - 1 + obj_vcount[SECONDARY_ENTRANCE_NAME]]
secondary_entrance_anchor = {
    "x": sum(v[0] for v in raw_entrance_verts) / len(raw_entrance_verts) - site_min_x,
    "z": sum(v[2] for v in raw_entrance_verts) / len(raw_entrance_verts) - site_min_z,
    "top_depth_ft": round(depth_below_grade(max(v[1] for v in raw_entrance_verts)), 2),
    "bottom_depth_ft": round(depth_below_grade(min(v[1] for v in raw_entrance_verts)), 2),
}

# --- Ramp anchors: centroid + rectangular footprint half-extents + depth range,
# one anchor per cluster (the 3 stacked levels share the same x/z footprint). ---
def ramp_anchor(names):
    verts = []
    for n in names:
        verts.extend(global_verts[obj_vstart[n] - 1: obj_vstart[n] - 1 + obj_vcount[n]])
    xs = [v[0] for v in verts]
    zs = [v[2] for v in verts]
    ys = [v[1] for v in verts]
    return {
        "x": (min(xs) + max(xs)) / 2 - site_min_x,
        "z": (min(zs) + max(zs)) / 2 - site_min_z,
        "half_width_ft": (max(xs) - min(xs)) / 2,
        "half_length_ft": (max(zs) - min(zs)) / 2,
        "top_depth_ft": round(depth_below_grade(max(ys)), 2),
        "bottom_depth_ft": round(depth_below_grade(min(ys)), 2),
    }


ramp_anchors = {"cluster_a": ramp_anchor(RAMP_CLUSTER_A), "cluster_b": ramp_anchor(RAMP_CLUSTER_B)}
print(f"Ramp anchors: {ramp_anchors}")
print(f"Secondary entrance anchor: {secondary_entrance_anchor}")
print(f"Grade Y (raw OBJ units): {grade_y}")

print(f"Tunnel ({TUNNEL_NAME}): {tunnel_mesh['vertex_count']}v, bbox {tunnel_mesh['bbox']}")
print(f"Secondary entrance ({SECONDARY_ENTRANCE_NAME}): {secondary_entrance_mesh['vertex_count']}v")
print(f"Ramp cluster A: {[m['vertex_count'] for m in ramp_meshes['cluster_a']]} verts")
print(f"Ramp cluster B: {[m['vertex_count'] for m in ramp_meshes['cluster_b']]} verts")

out = {
    "_meta": "Extracted from PershingMetablismGridBase.obj (single source -- columns, "
             "tunnel, ramps all share one coordinate frame, no cross-file registration "
             "guessing needed). Site-local origin (0,0) = OBJ-space "
             f"({site_min_x:.3f}, {site_min_z:.3f}), the SW corner of the real terrace "
             "footprint. +x = short axis (354ft), +z = long axis (602ft); y is vertical, "
             "0 = real grade plane (the exact, shared top_y of all 274 real columns) -- "
             "tunnel/entrance/ramp meshes and anchors are pre-shifted to this same "
             "reference, so all depth_ft / bottom_depth_ft values are real feet below grade.",
    "site": {"width_ft": round(site_width_ft, 2), "length_ft": round(site_length_ft, 2)},
    "grade_y_raw": grade_y,
    "column_prototype_mesh": column_mesh,
    "column_height_ft": round(column_height_ft, 2),
    "column_positions": [{"x": c["x"], "z": c["z"]} for c in column_positions],
    "tunnel_mesh": tunnel_mesh,
    "tunnel_endpoints": tunnel_endpoints,
    "secondary_entrance_mesh": secondary_entrance_mesh,
    "secondary_entrance_anchor": secondary_entrance_anchor,
    "ramp_meshes": ramp_meshes,
    "ramp_anchors": ramp_anchors,
}

os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
with open(OUT_PATH, "w", encoding="utf-8") as f:
    json.dump(out, f)

size_kb = os.path.getsize(OUT_PATH) / 1024
print(f"\nWrote {OUT_PATH} ({size_kb:.1f} KB)")
