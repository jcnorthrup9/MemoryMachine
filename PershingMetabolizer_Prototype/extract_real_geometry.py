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


def _make_box_mesh(xmin, xmax, ymin, ymax, zmin, zmax):
    """Crude 24-vertex/12-triangle axis-aligned box, matching the flat
    {"vertices": [...], "faces": [...]} convention every mesh field in
    real_geometry.json already uses (tunnel_mesh, secondary_entrance_mesh,
    ramp_meshes, column_prototype_mesh). Hard normals (4 unique verts per
    face) -- winding doesn't matter for visibility, frontend/src/shading.js
    sets side: THREE.DoubleSide on every material mode. Lives here (not in
    build_real_geometry.py, which also uses it) since it's fundamentally a
    geometry-construction utility, same category as mesh_for() below."""
    faces_corners = [
        [(xmin, ymin, zmin), (xmin, ymin, zmax), (xmin, ymax, zmax), (xmin, ymax, zmin)],  # -X
        [(xmax, ymin, zmin), (xmax, ymax, zmin), (xmax, ymax, zmax), (xmax, ymin, zmax)],  # +X
        [(xmin, ymin, zmin), (xmax, ymin, zmin), (xmax, ymin, zmax), (xmin, ymin, zmax)],  # -Y (deep)
        [(xmin, ymax, zmin), (xmin, ymax, zmax), (xmax, ymax, zmax), (xmax, ymax, zmin)],  # +Y (shallow)
        [(xmin, ymin, zmin), (xmin, ymax, zmin), (xmax, ymax, zmin), (xmax, ymin, zmin)],  # -Z
        [(xmin, ymin, zmax), (xmax, ymin, zmax), (xmax, ymax, zmax), (xmin, ymax, zmax)],  # +Z
    ]
    vertices, faces = [], []
    for quad in faces_corners:
        base = len(vertices) // 3
        for (x, y, z) in quad:
            vertices.extend([x, y, z])
        faces.extend([base, base + 1, base + 2, base, base + 2, base + 3])
    return {"vertices": vertices, "faces": faces}


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
    """Parse an OBJ into per-named-group vertex/face tables plus the flat global vertex list.

    Also tracks `g` (layer) vs `o` (object) distinctly via obj_group, which
    maps each named object to whichever `g` layer most recently preceded it
    (None for a top-level `g` itself, or an object with no enclosing g at
    all). Added 2026-07-08: PershingCurrentMetabolism.obj exports real Rhino
    layer names as `g` groups (e.g. "g STRUC__Columns" containing many
    "o object_N" per-instance objects within it) -- OBJ has no true nested-
    group syntax, so this is inferred purely from line order (every `o`
    belongs to the most recently seen `g`), not real hierarchy, but that's
    exactly how Rhino's own "layers as OBJ groups" export writes it.
    """
    global_verts = []          # 1-based via index+1
    obj_vstart = {}            # name -> first global vertex index (1-based)
    obj_vcount = {}            # name -> count of vertices
    obj_faces = {}             # name -> list of [global_idx,...] (0-based after conversion)
    obj_group = {}             # name -> enclosing g layer name, or None
    order = []

    cur = None
    cur_group = None
    with open(obj_path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            if line.startswith("g "):
                cur_group = line[2:].strip()
                cur = cur_group
                if cur not in obj_vstart:
                    order.append(cur)
                    obj_vstart[cur] = None
                    obj_vcount[cur] = 0
                    obj_faces[cur] = []
                    obj_group[cur] = None
            elif line.startswith("o "):
                cur = line[2:].strip()
                if cur not in obj_vstart:
                    order.append(cur)
                    obj_vstart[cur] = None
                    obj_vcount[cur] = 0
                    obj_faces[cur] = []
                obj_group[cur] = cur_group
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
    return global_verts, obj_vstart, obj_vcount, obj_faces, order, obj_group


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
    # Fallback grade reference (raw OBJ Y) for when column extraction finds
    # nothing usable at all (heuristic mismatch, not a real absence of
    # columns -- see column_vertex_count_range's docstring above). grade_y
    # is a physical constant of the site (every real column's shared top
    # elevation) -- added 2026-07-08 rather than fixing the heuristic
    # itself, since a known-good value already exists from a prior
    # successful run and re-deriving it isn't required every time the
    # heuristic happens to miss. Ignored when column extraction succeeds.
    grade_y_override=None,
):
    """
    Extract site geometry from `obj_path` using the given object-name mapping
    and write the resulting JSON to `out_path`. See module docstring -- the
    mapping args are the only site-specific inputs; everything below is
    generic OBJ-group extraction/derivation.
    """
    global_verts, obj_vstart, obj_vcount, obj_faces, order, _obj_group = parse_obj(obj_path)
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

        c_verts, c_vstart, c_vcount, c_faces, c_order, _c_group = parse_obj(column_obj_path)
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
    # expressed relative to it (positive = below grade). Falls back to an
    # explicit override when column extraction found nothing usable --
    # see grade_y_override's docstring above.
    if column_positions:
        grade_y = column_positions[0]["top_y"]
        assert all(abs(c["top_y"] - grade_y) < 1e-3 for c in column_positions), "columns not coplanar"
    elif grade_y_override is not None:
        grade_y = grade_y_override
        print(f"[extract] no column_positions matched (heuristic mismatch, not a real absence of "
              f"columns) -- using grade_y_override={grade_y}")
    else:
        raise ValueError(
            "No column_positions extracted and no grade_y_override given -- cannot establish a "
            "grade reference. Either fix the column-matching heuristic (column_vertex_count_range "
            "/ column_obj_path) or pass a known-good grade_y_override."
        )

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


def extract_positions_from_layered_obj(
    obj_path,
    column_layer="STRUC__Columns",
    boundary_layer="BOUNDARY",
    entrance_layer="metroConnection",
    ramp_layer="CIRC__Ramps",
):
    """
    Extract position/depth facts (deliberately NOT mesh geometry) from an
    OBJ exported with "layers as OBJ groups" checked (e.g.
    PershingCurrentMetabolism.obj) -- real Rhino layer names as `g` groups,
    each containing the real per-instance `o` objects on that layer.

    Added 2026-07-08 specifically because extract_real_geometry()'s vertex-
    count heuristic (column_vertex_count_range) finds zero columns in the
    current grid-base OBJ, and its hardcoded secondary_entrance_name=
    "object_2" mapping is stale (see PIPELINE_STATUS_AND_NEXT_STEPS.md).
    Reading by real layer name sidesteps both: STRUC__Columns/BOUNDARY/
    metroConnection/CIRC__Ramps are the same names already used throughout
    this project's Rhino MCP work and structural_grid_analyzer.py's SVG
    parsing, not a guess.

    Deliberately position/depth-only, not mesh geometry: most groups in
    this specific export (metroConnection, CIRC__Ramps, BOUNDARY -- every
    layer checked except metroTunnel's "metro_station_box") have vertices
    but zero faces (Rhino exported them as trim curves, not triangulated
    mesh, for whatever object types those are) -- fine for centroid/bbox
    math, useless for mesh_for()'s face-driven vertex walk (mesh_for only
    collects a vertex at all when it's referenced by a face). Mesh fields
    (tunnel_mesh, secondary_entrance_mesh, ramp_meshes, column_prototype_mesh)
    still come from extract_real_geometry()'s existing OBJ path, which
    already extracts those correctly -- this function only replaces the
    position/depth facts that path gets wrong.

    Ramp clustering: no name-based cluster distinction exists in this
    export (unlike the old ramp_cluster_a/b name-tuple convention), so the
    layer's objects are split into two spatial clusters at the largest gap
    in their sorted x-centroids -- confirmed 2026-07-08 against real data
    to cleanly separate two x-value pairs (0ft within a cluster, ~190ft
    between clusters), not an approximation that needs tuning.

    Returns a dict: site (width_ft/length_ft), grade_y_raw, column_positions,
    secondary_entrance_anchor, ramp_anchors -- same shapes as
    extract_real_geometry()'s equivalent fields, in the same site-local
    (BOUNDARY min corner) origin.

    Z-axis sign, fixed 2026-07-09: Rhino's OBJ exporter (up_axis='Z',
    forward_axis='Y', used throughout this project) converts Rhino's
    right-handed Z-up WCS to OBJ's Y-up convention via OBJ_x=Rhino_x,
    OBJ_y=Rhino_z (unchanged), OBJ_z=-Rhino_y (NEGATED -- required to
    preserve right-handedness when swapping two axes; confirmed directly
    by comparing metroTunnel's live-Rhino-queried Y range against its raw
    OBJ Z-column values). Every z-axis site-local value below is therefore
    computed as `site_max_z - v[2]`, NOT `v[2] - site_min_z` -- taking
    min() of a negated axis anchors the origin at the WRONG end of the
    site. Proven with real numbers: metroConnection's live-Rhino bbox
    converts to site_local_z=566.11 via the correct formula (matching the
    independently-trusted, SVG-derived secondary_entrance_anchor.z=566.267
    to 0.15ft) vs. 36.29 via the old, backwards formula -- an exact
    mirror (602.4 - 566.11 = 36.29), not a rounding difference. This bug
    predates today but was masked: SVG (unaffected, different coordinate
    source) wins secondary_entrance_anchor.x/z in the final merged output,
    and ramp_anchors happens to sit almost exactly at the site's Z-midpoint
    (a mirror-invariant point), so its output was accidentally close to
    correct. X is NOT negated (OBJ_x=Rhino_x directly, confirmed
    separately) -- only Z needs this treatment.
    """
    global_verts, obj_vstart, obj_vcount, obj_faces, order, obj_group = parse_obj(obj_path)

    def verts_of(name):
        start = obj_vstart[name]
        count = obj_vcount[name]
        return global_verts[start - 1: start - 1 + count]

    members = {}  # group_name -> [object names directly in it]
    for name, g in obj_group.items():
        if g is not None and name != g:
            members.setdefault(g, []).append(name)

    # --- Site extent from BOUNDARY -- same real curve
    # structural_grid_analyzer.py's SVG path already reads, just via OBJ
    # export instead of SVG export. ---
    boundary_objs = members.get(boundary_layer, [])
    if not boundary_objs:
        raise ValueError(f"no objects found under g {boundary_layer!r}")
    boundary_verts = [v for name in boundary_objs for v in verts_of(name)]
    site_min_x = min(v[0] for v in boundary_verts)
    site_max_x = max(v[0] for v in boundary_verts)
    site_min_z = min(v[2] for v in boundary_verts)
    site_max_z = max(v[2] for v in boundary_verts)
    site_width_ft = site_max_x - site_min_x
    site_length_ft = site_max_z - site_min_z

    # --- Columns: one centroid + top_y per object in column_layer. ---
    column_objs = members.get(column_layer, [])
    if not column_objs:
        raise ValueError(f"no objects found under g {column_layer!r}")
    column_positions = []
    for name in column_objs:
        vs = verts_of(name)
        cx = sum(v[0] for v in vs) / len(vs)
        cz = sum(v[2] for v in vs) / len(vs)
        top_y = max(v[1] for v in vs)
        column_positions.append({"x": cx - site_min_x, "z": site_max_z - cz, "top_y": top_y})

    # --- Grade reference: same real, unambiguous shared-top_y check
    # extract_real_geometry() uses, just actually succeeding here since
    # column_positions is real this time. ---
    grade_y = column_positions[0]["top_y"]
    assert all(abs(c["top_y"] - grade_y) < 1e-3 for c in column_positions), \
        f"columns not coplanar in g {column_layer!r} -- real grade reference unreliable"

    def depth_below_grade(abs_y):
        return grade_y - abs_y

    # --- Entrance anchor: single object's centroid + full y-range. ---
    entrance_objs = members.get(entrance_layer, [])
    if not entrance_objs:
        raise ValueError(f"no objects found under g {entrance_layer!r}")
    if len(entrance_objs) > 1:
        print(f"[extract] {len(entrance_objs)} objects found under g {entrance_layer!r}, "
              f"expected one -- using all of them combined.")
    entrance_verts = [v for name in entrance_objs for v in verts_of(name)]
    secondary_entrance_anchor = {
        "x": sum(v[0] for v in entrance_verts) / len(entrance_verts) - site_min_x,
        "z": site_max_z - sum(v[2] for v in entrance_verts) / len(entrance_verts),
        "top_depth_ft": round(depth_below_grade(max(v[1] for v in entrance_verts)), 2),
        "bottom_depth_ft": round(depth_below_grade(min(v[1] for v in entrance_verts)), 2),
    }

    # --- Ramps: cluster this layer's objects into two groups by x-position
    # (see docstring above for why -- no name-based distinction available). ---
    ramp_objs = members.get(ramp_layer, [])
    ramp_anchors = {}
    if ramp_objs:
        ramp_centroids = [(name, sum(v[0] for v in verts_of(name)) / obj_vcount[name], verts_of(name))
                           for name in ramp_objs]
        ramp_centroids.sort(key=lambda t: t[1])
        xs = [t[1] for t in ramp_centroids]
        gaps = [(xs[i + 1] - xs[i], i) for i in range(len(xs) - 1)]
        if gaps:
            _, split_i = max(gaps)
            cluster_a, cluster_b = ramp_centroids[:split_i + 1], ramp_centroids[split_i + 1:]
        else:
            cluster_a, cluster_b = ramp_centroids, []

        def anchor_from(cluster):
            verts = [v for _, _, vs in cluster for v in vs]
            xs_ = [v[0] for v in verts]
            zs_ = [v[2] for v in verts]
            ys_ = [v[1] for v in verts]
            return {
                "x": (min(xs_) + max(xs_)) / 2 - site_min_x,
                "z": site_max_z - (min(zs_) + max(zs_)) / 2,
                "half_width_ft": (max(xs_) - min(xs_)) / 2,
                "half_length_ft": (max(zs_) - min(zs_)) / 2,
                "top_depth_ft": round(depth_below_grade(max(ys_)), 2),
                "bottom_depth_ft": round(depth_below_grade(min(ys_)), 2),
            }

        if cluster_a:
            ramp_anchors["cluster_a"] = anchor_from(cluster_a)
        if cluster_b:
            ramp_anchors["cluster_b"] = anchor_from(cluster_b)

    print(f"[extract] layered OBJ: {len(column_positions)} columns, "
          f"site {site_width_ft:.2f}x{site_length_ft:.2f}ft, "
          f"entrance anchor {secondary_entrance_anchor}, {len(ramp_anchors)} ramp clusters")

    return {
        "site": {"width_ft": round(site_width_ft, 2), "length_ft": round(site_length_ft, 2)},
        "grade_y_raw": grade_y,
        "column_positions": [{"x": c["x"], "z": c["z"]} for c in column_positions],
        "secondary_entrance_anchor": secondary_entrance_anchor,
        "ramp_anchors": ramp_anchors,
    }


def extract_meshes_from_layered_obj(
    obj_path,
    boundary_layer="BOUNDARY",
    tunnel_group="metroTunnel",
    entrance_group="metroConnection",
):
    """
    Extract REAL mesh geometry (not just position facts, unlike
    extract_positions_from_layered_obj above) for tunnel_mesh and
    secondary_entrance_mesh directly from an OBJ exported with "layers as
    OBJ groups" (e.g. PershingCurrentMetabolism.obj).

    Added 2026-07-09 after confirming this export now has real triangulated
    face data for the Metro tunnel/station-box (g metroTunnel -> o
    metro_station_box, 196 real faces) -- previously absent, which is why
    this project fell back to a much older grid-base OBJ (June 28) for
    mesh geometry while using this file only for position/depth facts.
    That fallback is now stale: build_real_geometry.py used to patch the
    old mesh's position/depth with translate/rescale hacks to match the
    freshly-verified secondary_entrance_anchor (see PIPELINE_STATUS_AND_
    NEXT_STEPS.md's 2026-07-08/09 entries) -- fixing where a stale mesh
    displayed, not what geometry it should have been in the first place.
    Extracting directly from the same file/object the anchor itself comes
    from sidesteps that class of bug entirely, and happened to catch a
    small additional error in one of those patches (it assumed
    depth_ft = -y, but the real convention used everywhere else in this
    file is depth_ft = grade_y_raw - y, and grade_y_raw is ~3.73, not 0).

    metroConnection (o object_1) still has no face data (Rhino exported it
    as an Extrusion, not a triangulated mesh) but its 24 vertices form a
    perfect axis-aligned box (confirmed: exactly 2 unique values per axis),
    so its mesh is reconstructed via _make_box_mesh from that box's own
    real bounding box.

    Returns site-local (BOUNDARY min-corner-origin), OBJ-vertex-order
    ({"vertices": flat x,y,z,..., "faces": flat tri-index ints}) mesh dicts
    -- the same convention every mesh field in real_geometry.json already
    uses (matches mesh_for()'s own uncentered output, just offset by
    site_min_x/site_min_z instead of left in raw Rhino-export coordinates).

    Z-axis sign, fixed 2026-07-09: same bug and same fix as
    extract_positions_from_layered_obj's docstring describes in full --
    OBJ_z is a NEGATED Rhino Y, so site-local Z must be `site_max_z - v[2]`,
    not `v[2] - site_min_z`. For tunnel_mesh specifically (a real,
    asymmetric triangulated mesh, not a symmetric box) this negation is a
    genuine mirror and inverts triangle winding/normals, so each face's
    vertex order is reversed to compensate -- same principle
    vector_export.py's own mirror_mesh_y() already applies for exactly
    this reason (see its docstring).
    """
    global_verts, obj_vstart, obj_vcount, obj_faces, order, obj_group = parse_obj(obj_path)

    def verts_of(name):
        start = obj_vstart[name]
        count = obj_vcount[name]
        return global_verts[start - 1: start - 1 + count]

    members = {}
    for name, g in obj_group.items():
        if g is not None and name != g:
            members.setdefault(g, []).append(name)

    boundary_objs = members.get(boundary_layer, [])
    if not boundary_objs:
        raise ValueError(f"no objects found under g {boundary_layer!r}")
    boundary_verts = [v for name in boundary_objs for v in verts_of(name)]
    site_min_x = min(v[0] for v in boundary_verts)
    site_max_z = max(v[2] for v in boundary_verts)

    def _offset_flat(flat_verts):
        out = []
        for i in range(0, len(flat_verts), 3):
            out.extend([flat_verts[i] - site_min_x, flat_verts[i + 1], site_max_z - flat_verts[i + 2]])
        return out

    def _reverse_winding(flat_faces):
        # Z-mirror inverts triangle winding -- swap the last two indices of
        # each triangle (a b c -> a c b) to restore outward-facing normals.
        out = list(flat_faces)
        for i in range(0, len(out), 3):
            out[i + 1], out[i + 2] = out[i + 2], out[i + 1]
        return out

    # --- Tunnel: real triangulated mesh, wherever its faces actually live
    # -- the enclosing g group itself, or (as in this export) a single
    # nested o sub-object, since OBJ has no true nested-group syntax and
    # Rhino's own "layers as OBJ groups" export writes real per-instance
    # object names underneath each layer's g line (see parse_obj's
    # docstring). ---
    tunnel_face_owner = tunnel_group if obj_faces.get(tunnel_group) else next(
        (n for n, g in obj_group.items() if g == tunnel_group and obj_faces.get(n)), None)
    if tunnel_face_owner is None:
        raise ValueError(f"no face data found for g {tunnel_group!r} or any object under it")
    tunnel_raw = mesh_for(tunnel_face_owner, obj_faces, global_verts)
    tunnel_mesh = {
        "vertices": _offset_flat(tunnel_raw["vertices"]),
        "faces": _reverse_winding(tunnel_raw["faces"]),
    }

    # --- Entrance: no face data (Extrusion, not a mesh) -- reconstruct a
    # box from its own real bounding box instead of borrowing a stale,
    # differently-positioned/sized placeholder from another file. ---
    entrance_objs = members.get(entrance_group, [])
    if not entrance_objs:
        raise ValueError(f"no objects found under g {entrance_group!r}")
    entrance_verts = [v for name in entrance_objs for v in verts_of(name)]
    ex = [v[0] for v in entrance_verts]
    ey = [v[1] for v in entrance_verts]
    ez = [v[2] for v in entrance_verts]
    secondary_entrance_mesh = _make_box_mesh(
        min(ex) - site_min_x, max(ex) - site_min_x,
        min(ey), max(ey),
        site_max_z - max(ez), site_max_z - min(ez),
    )

    print(f"[extract] layered-OBJ meshes: tunnel_mesh from {tunnel_face_owner!r} "
          f"({len(tunnel_raw['faces']) // 3} real tris), secondary_entrance_mesh "
          f"reconstructed as a box from {entrance_group!r}'s own real bbox")

    return {"tunnel_mesh": tunnel_mesh, "secondary_entrance_mesh": secondary_entrance_mesh}


if __name__ == "__main__":
    PERSHING_OBJ_PATH = r"D:\MemoryMachine\data\PershingMetabolizer\OBJ\PershingMetablismGridBase.obj"
    PERSHING_OUT_PATH = r"D:\MemoryMachine\PershingMetabolizer_Prototype\real_geometry.json"
    extract_real_geometry(PERSHING_OBJ_PATH, PERSHING_OUT_PATH)
