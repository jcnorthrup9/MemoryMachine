"""
One-time offline extraction: pull real column/tunnel/entrance/ramp geometry out of
a site's structural OBJ export and the real site footprint out of its own terrace
slabs, write a small JSON a browser prototype can load directly (no OBJLoader,
no multi-hundred-MB file ever touching the browser).

Generalized from a Pershing-only script: the OBJ object-name mapping (which
`o`/`g` group is the tunnel, the column prototype, etc.) is passed in as
arguments rather than hardcoded, so a different site's OBJ export -- with its
own object names -- can reuse the same extraction logic. Pershing's own
mapping is preserved as the default and as the __main__ entry point below.
"""
import json
import os


def mesh_for(name, obj_faces, global_verts, recenter_xz=False, recenter_y_to_top=False):
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


def parse_obj(obj_path):
    """Parse an OBJ into per-named-group vertex/face tables plus the flat global vertex list."""
    global_verts = []          # 1-based via index+1
    obj_vstart = {}            # name -> first global vertex index (1-based)
    obj_vcount = {}            # name -> count of vertices
    obj_faces = {}             # name -> list of [global_idx,...] (0-based after conversion)
    order = []

    cur = None
    with open(obj_path, "r", encoding="utf-8", errors="ignore") as f:
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
    return global_verts, obj_vstart, obj_vcount, obj_faces, order


def extract_real_geometry(
    obj_path,
    out_path,
    tunnel_name="object_1",
    secondary_entrance_name="object_2",
    terrace_names=("object_3", "object_4", "object_5", "object_6"),
    ramp_cluster_a=("object_7", "object_8", "object_9"),
    ramp_cluster_b=("object_10", "object_11", "object_12"),
    column_prototype_name="object_13",
    # Vertex-count heuristic: fragile, only a fallback. Confirmed 2026-07-05
    # that once a site's combined OBJ accumulates enough unrelated small
    # geometry, several hundred non-column objects can coincidentally share
    # the same vertex count as a real column (verified via the coplanarity
    # check below catching only ~30-46 of 480 "6-vertex" candidates at the
    # real shared grade height) -- vertex count alone is not a safe column
    # filter on a busy combined export. Prefer column_obj_path instead.
    column_vertex_count_range=(5, 7),
    # Preferred path: a dedicated, columns-only OBJ export (no other
    # geometry mixed in), so every object in the file is a real column by
    # construction -- no heuristic needed at all. When given, this
    # supersedes column_vertex_count_range entirely for position/prototype
    # extraction, though obj_path is still used for the site footprint
    # (terrace_names) and everything else non-column.
    column_obj_path=None,
    # Override for the column file's own (site_min_x, site_min_z) origin --
    # only needed when obj_path's terrace_names mapping is stale (as it was
    # 2026-07-05: object numbering shifted after a lot of new geometry was
    # added/removed, so the "terrace" objects derived below no longer point
    # at the real slab and give a nonsense 132x123ft footprint instead of
    # the real ~354x602ft). Defaults to reusing the terrace-derived origin
    # when that mapping is still trustworthy.
    column_site_origin=None,
):
    """
    Extract site geometry from `obj_path` using the given object-name mapping
    and write the resulting JSON to `out_path`. See module docstring -- the
    mapping args are the only site-specific inputs; everything below is
    generic OBJ-group extraction/derivation.
    """
    global_verts, obj_vstart, obj_vcount, obj_faces, order = parse_obj(obj_path)
    terrace_names = set(terrace_names)

    # --- Site footprint from the terrace slabs (real rectangle, real OBJ-space) ---
    tx, tz = [], []
    for name in terrace_names:
        vs = global_verts[obj_vstart[name] - 1: obj_vstart[name] - 1 + obj_vcount[name]]
        tx.extend(v[0] for v in vs)
        tz.extend(v[2] for v in vs)
    site_min_x, site_max_x = min(tx), max(tx)
    site_min_z, site_max_z = min(tz), max(tz)
    site_width_ft = site_max_x - site_min_x   # short axis, matches SVG width_ft
    site_length_ft = site_max_z - site_min_z  # long axis, matches SVG height_ft
    print(f"Real site footprint (from terrace slabs): {site_width_ft:.2f} x {site_length_ft:.2f} ft")
    print(f"  origin (site-local 0,0) = OBJ-space ({site_min_x:.2f}, {site_min_z:.2f})")

    if column_obj_path:
        # Dedicated columns-only export: every named object with real faces
        # IS a column, no filtering needed. Assumes the same absolute Rhino
        # document coordinate system as obj_path (true for per-part exports
        # from the same document -- verified 2026-07-05 by cross-checking
        # against live Rhino MCP query results and the already-established
        # grade Z value, both matched exactly).
        col_origin_x, col_origin_z = column_site_origin if column_site_origin else (site_min_x, site_min_z)

        c_verts, c_vstart, c_vcount, c_faces, c_order = parse_obj(column_obj_path)
        column_names = [n for n in c_order if c_vstart.get(n) is not None and len(c_faces[n]) > 0]

        column_mesh = mesh_for(column_names[0], c_faces, c_verts, recenter_xz=True, recenter_y_to_top=True)
        column_height_ft = column_mesh["bbox"]["max"][1] - column_mesh["bbox"]["min"][1]
        print(f"Column prototype (from {column_obj_path}, {column_names[0]}): "
              f"{column_mesh['vertex_count']}v {column_mesh['face_count']}tris, height {column_height_ft:.2f}ft")

        column_positions = []
        for name in column_names:
            vs = c_verts[c_vstart[name] - 1: c_vstart[name] - 1 + c_vcount[name]]
            cx = sum(p[0] for p in vs) / len(vs)
            cz = sum(p[2] for p in vs) / len(vs)
            top_y = max(p[1] for p in vs)
            column_positions.append({
                "x": cx - col_origin_x,
                "z": cz - col_origin_z,
                "top_y": top_y,
            })
        print(f"Real column positions extracted (dedicated file): {len(column_positions)}")
    else:
        # --- Column prototype mesh (recentered to its own base, local space) ---
        column_mesh = mesh_for(column_prototype_name, obj_faces, global_verts, recenter_xz=True, recenter_y_to_top=True)
        column_height_ft = column_mesh["bbox"]["max"][1] - column_mesh["bbox"]["min"][1]
        print(f"Column prototype ({column_prototype_name}): {column_mesh['vertex_count']}v "
              f"{column_mesh['face_count']}tris, height {column_height_ft:.2f}ft")

        # --- All real column positions (any object matching the mid-vertex-count bucket) ---
        lo, hi = column_vertex_count_range
        column_positions = []
        for name in order:
            v = obj_vcount[name]
            if lo < v <= hi:
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

    # --- Grade reference: every real column shares the exact same top_y --
    # that's the real, unambiguous grade plane. Every depth below is
    # expressed relative to it (positive = below grade). ---
    grade_y = column_positions[0]["top_y"]
    assert all(abs(c["top_y"] - grade_y) < 1e-3 for c in column_positions), "columns not coplanar"

    def depth_below_grade(abs_y):
        return grade_y - abs_y

    # --- Tunnel + secondary entrance + ramps, baked to site-local coords with y
    # already shifted so 0 = grade (matching the recentered column mesh). ---
    def mesh_site_local(name):
        m = mesh_for(name, obj_faces, global_verts, recenter_xz=False, recenter_y_to_top=False)
        verts = m["vertices"]
        out_verts = []
        for i in range(0, len(verts), 3):
            out_verts.extend([verts[i] - site_min_x, verts[i + 1] - grade_y, verts[i + 2] - site_min_z])
        m["vertices"] = out_verts
        m["centroid_xz"] = [m["centroid_xz"][0] - site_min_x, m["centroid_xz"][1] - site_min_z]
        return m

    tunnel_mesh = mesh_site_local(tunnel_name)
    secondary_entrance_mesh = mesh_site_local(secondary_entrance_name)
    ramp_meshes = {
        "cluster_a": [mesh_site_local(n) for n in ramp_cluster_a],
        "cluster_b": [mesh_site_local(n) for n in ramp_cluster_b],
    }

    # --- Tunnel endpoints: the box has two flat end-caps. Split on raw z at the
    # tunnel's own midpoint so this works for any site's tunnel length/position,
    # not just one hardcoded to Pershing's z=600 split. ---
    raw_tunnel_verts = global_verts[obj_vstart[tunnel_name] - 1: obj_vstart[tunnel_name] - 1 + obj_vcount[tunnel_name]]
    tunnel_z_mid = (min(v[2] for v in raw_tunnel_verts) + max(v[2] for v in raw_tunnel_verts)) / 2
    end_hi = [v for v in raw_tunnel_verts if v[2] > tunnel_z_mid]
    end_lo = [v for v in raw_tunnel_verts if v[2] <= tunnel_z_mid]

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
    raw_entrance_verts = global_verts[obj_vstart[secondary_entrance_name] - 1:
                                       obj_vstart[secondary_entrance_name] - 1 + obj_vcount[secondary_entrance_name]]
    secondary_entrance_anchor = {
        "x": sum(v[0] for v in raw_entrance_verts) / len(raw_entrance_verts) - site_min_x,
        "z": sum(v[2] for v in raw_entrance_verts) / len(raw_entrance_verts) - site_min_z,
        "top_depth_ft": round(depth_below_grade(max(v[1] for v in raw_entrance_verts)), 2),
        "bottom_depth_ft": round(depth_below_grade(min(v[1] for v in raw_entrance_verts)), 2),
    }

    # --- Ramp anchors: centroid + rectangular footprint half-extents + depth range,
    # one anchor per cluster (the stacked levels share the same x/z footprint). ---
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

    ramp_anchors = {"cluster_a": ramp_anchor(ramp_cluster_a), "cluster_b": ramp_anchor(ramp_cluster_b)}
    print(f"Ramp anchors: {ramp_anchors}")
    print(f"Secondary entrance anchor: {secondary_entrance_anchor}")
    print(f"Grade Y (raw OBJ units): {grade_y}")

    print(f"Tunnel ({tunnel_name}): {tunnel_mesh['vertex_count']}v, bbox {tunnel_mesh['bbox']}")
    print(f"Secondary entrance ({secondary_entrance_name}): {secondary_entrance_mesh['vertex_count']}v")
    print(f"Ramp cluster A: {[m['vertex_count'] for m in ramp_meshes['cluster_a']]} verts")
    print(f"Ramp cluster B: {[m['vertex_count'] for m in ramp_meshes['cluster_b']]} verts")

    out = {
        "_meta": "Extracted via extract_real_geometry.py (generalized: object-name mapping "
                 "passed in, not hardcoded -- see this script's extract_real_geometry() args). "
                 "Columns, tunnel, ramps all share one coordinate frame, no cross-file "
                 "registration guessing needed. Site-local origin (0,0) = OBJ-space "
                 f"({site_min_x:.3f}, {site_min_z:.3f}), the SW corner of the real terrace "
                 "footprint. +x = short axis, +z = long axis; y is vertical, 0 = real grade "
                 "plane (the exact, shared top_y of all real columns) -- tunnel/entrance/ramp "
                 "meshes and anchors are pre-shifted to this same reference, so all depth_ft / "
                 "bottom_depth_ft values are real feet below grade.",
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

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f)

    size_kb = os.path.getsize(out_path) / 1024
    print(f"\nWrote {out_path} ({size_kb:.1f} KB)")
    return out


if __name__ == "__main__":
    PERSHING_OBJ_PATH = r"D:\MemoryMachine\data\PershingMetabolizer\OBJ\PershingMetablismGridBase.obj"
    PERSHING_OUT_PATH = r"D:\MemoryMachine\PershingMetabolizer_Prototype\real_geometry.json"
    extract_real_geometry(PERSHING_OBJ_PATH, PERSHING_OUT_PATH)
