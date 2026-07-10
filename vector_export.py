"""
Memory Machine -- Vector Export Engine (Section 6, "clean" pass).

Builds an actual 3D solid from terracing_engine.py's stepped depth field plus
the real static context geometry (columns, tunnel, secondary entrance, ramps
from real_geometry.json), then mesh-slices it for true geometric section/plan
cuts -- not an approximation of the voxel grid, an intersection against real
triangle geometry.

Scope of this pass (deliberately, per project decision): pre-Blender "clean"
geometry only -- no erosion/weathering deformation. Botanical planting
geometry (LAYER_03_BOTANICAL) doesn't exist yet, so that layer is emitted
empty. Background/projected-beyond-the-cut-plane geometry (LAYER_02_PROJECTION)
needs real hidden-line visibility logic this pass doesn't attempt yet -- also
emitted empty for now. Both are explicit, not silent, gaps.

Coordinate convention: this module uses a Z-up site-local frame (x = site
width, y = site length, z = vertical, 0 = grade, negative = below grade) to
match architectural/DXF convention. real_geometry.json's meshes are Y-up
(OBJ convention, already grade-shifted so y=0 is grade) -- every context mesh
is converted via (x, y_obj, z_obj) -> (x, z_obj, y_obj) on load.
"""
import numpy as np
import trimesh

LAYER_CUT = "LAYER_01_CUT"
LAYER_PROJECTION = "LAYER_02_PROJECTION"
LAYER_BOTANICAL = "LAYER_03_BOTANICAL"
LAYER_GRID = "LAYER_04_GRID"
LAYER_LABELS = "LAYER_05_LABELS"

LAYER_COLORS = {
    LAYER_CUT: "#000000",
    LAYER_PROJECTION: "#999999",
    LAYER_BOTANICAL: "#2e7d32",
    LAYER_GRID: "#cc0000",
    LAYER_LABELS: "#0066cc",
}

# Street-edge labels for plan/axo views, in this module's site-local (x, y)
# frame. Re-corrected 2026-07-09: the 2026-07-03 assignment below (5TH
# ST=y0) was itself derived from the metroConnection object's position at
# the time, which was later found (2026-07-08/09) to be a stale, pre-fix
# snapshot -- once the real Z-axis sign bug was fixed and the entrance
# position was re-verified multiple independent ways against live Rhino
# data (see PIPELINE_STATUS_AND_NEXT_STEPS.md's 2026-07-08/09 entries),
# the entrance/tunnel land at y-MAX, not y0. User confirmed directly
# (2026-07-09): the real Metro entrance/connector is at the 5th & Hill
# corner, so 5TH ST is the ymax edge, not y0 -- swapped from the 07-03
# assignment accordingly. HILL ST=xmax was never in question (X was
# unaffected by the Z-axis bug, confirmed separately).
STREET_LABELS = [
    ("OLIVE ST", "x0"),
    ("HILL ST", "xmax"),
    ("5TH ST", "ymax"),
    ("6TH ST", "y0"),
]


def street_label_points(site_width_ft, site_length_ft):
    """(text, (x, y)) pairs at the midpoint of each site edge, for LAYER_LABELS."""
    edge_pos = {
        "x0": (0.0, site_length_ft / 2),
        "xmax": (site_width_ft, site_length_ft / 2),
        "y0": (site_width_ft / 2, 0.0),
        "ymax": (site_width_ft / 2, site_length_ft),
    }
    return [(text, edge_pos[edge]) for text, edge in STREET_LABELS]


def _obj_to_site(flat_verts):
    """Convert a flat [x,y,z,x,y,z,...] OBJ-convention (Y-up) vertex list to
    this module's Z-up site-local convention: (x, y_obj, z_obj) -> (x, z_obj, y_obj)."""
    arr = np.array(flat_verts, dtype=float).reshape(-1, 3)
    out = np.empty_like(arr)
    out[:, 0] = arr[:, 0]
    out[:, 1] = arr[:, 2]
    out[:, 2] = arr[:, 1]
    return out


def _mesh_from_real(mesh_dict):
    verts = _obj_to_site(mesh_dict["vertices"])
    faces = np.array(mesh_dict["faces"], dtype=int).reshape(-1, 3)
    return trimesh.Trimesh(vertices=verts, faces=faces, process=False)


def build_context_meshes(real_geometry):
    """
    Real static structure from real_geometry.json, converted to site-local
    Z-up coordinates: one mesh per real column instance, plus the tunnel,
    secondary entrance, and both ramp clusters (3 levels each).
    """
    meshes = {}

    proto = _mesh_from_real(real_geometry["column_prototype_mesh"])
    columns = []
    for c in real_geometry["column_positions"]:
        m = proto.copy()
        m.apply_translation([c["x"], c["z"], 0.0])
        columns.append(m)
    meshes["columns"] = columns

    meshes["tunnel"] = _mesh_from_real(real_geometry["tunnel_mesh"])
    meshes["secondary_entrance"] = _mesh_from_real(real_geometry["secondary_entrance_mesh"])
    meshes["metro_connector"] = _mesh_from_real(real_geometry["metro_connector_mesh"])

    ramps = []
    for cluster in real_geometry["ramp_meshes"].values():
        for level in cluster:
            ramps.append(_mesh_from_real(level))
    meshes["ramps"] = ramps

    return meshes


def build_terraced_solid(engine, voxels, floor_margin_ft=10.0):
    """
    Build a real 3D "terrain" solid from the terracing engine's stepped
    depth field: one watertight box per voxel, running from that voxel's
    own top (grade for untouched cells, its excavation depth otherwise)
    DOWN to a shared floor reference below the deepest possible cut. Every
    voxel's TOP face therefore sits exactly at its own elevation, facing
    upward -- a real, addressable tread surface at every terrace step
    (including the flat plaza "step" at grade), which is what the Botanical
    Attractor Module's per-level surface conditions (see terracing_engine.py
    Voxel.level) are meant to attach to.

    Deliberately NOT a shaft running from grade down to each voxel's own
    depth (an earlier version was) -- that buried every voxel's exposed
    surface at grade, so only vertical shaft walls were ever visible from
    an oblique angle, never real flat treads looking down from above.
    """
    parts = []
    vf = engine.voxel_ft
    floor_z = -(engine.max_canyon_depth_ft + floor_margin_ft)

    for v in voxels:
        top = v.z_ft
        height = top - floor_z
        if height <= 0:
            continue
        box = trimesh.creation.box(extents=[vf, vf, height])
        cx = v.gx * vf + vf / 2
        cy = v.gy * vf + vf / 2
        cz = top - height / 2
        box.apply_translation([cx, cy, cz])
        parts.append(box)

    return trimesh.util.concatenate(parts)


def build_combined_mesh(real_geometry, engine, voxels):
    context = build_context_meshes(real_geometry)
    terrace = build_terraced_solid(engine, voxels)
    all_meshes = [terrace, context["tunnel"], context["secondary_entrance"], context["metro_connector"]]
    all_meshes.extend(context["columns"])
    all_meshes.extend(context["ramps"])
    return trimesh.util.concatenate(all_meshes)


def build_named_scene(real_geometry, engine, voxels):
    """
    Same geometry as build_combined_mesh, but kept as separate NAMED parts
    (a trimesh.Scene) instead of one concatenated mesh -- for bridging into
    Blender (see blender_erosion_pass.py), where different parts need
    different treatment (the terrace gets eroded/weathered, the real
    existing structure -- columns/tunnel/entrance/ramps -- doesn't). A
    plain OBJ export of a concatenated mesh loses this distinction (Blender
    only sees one object); exporting a Scene preserves per-part names as
    separate Blender objects on import.
    """
    context = build_context_meshes(real_geometry)
    terrace = build_terraced_solid(engine, voxels)
    scene = trimesh.Scene()
    scene.add_geometry(terrace, node_name="terrace", geom_name="terrace")
    scene.add_geometry(context["tunnel"], node_name="tunnel", geom_name="tunnel")
    scene.add_geometry(context["secondary_entrance"], node_name="secondary_entrance", geom_name="secondary_entrance")
    scene.add_geometry(context["metro_connector"], node_name="metro_connector", geom_name="metro_connector")
    scene.add_geometry(trimesh.util.concatenate(context["columns"]), node_name="columns", geom_name="columns")
    scene.add_geometry(trimesh.util.concatenate(context["ramps"]), node_name="ramps", geom_name="ramps")
    return scene


def mirror_mesh_y(mesh, site_length_ft):
    """
    Mirror a mesh's Y (site-length) coordinate: y -> site_length_ft - y.
    A single-axis mirror inverts handedness, so face winding is reversed to
    keep normals pointing outward correctly (otherwise silhouette/crease
    detection in axonometric_projection would read front/back-facing
    backwards). Used for the axo view specifically (see AXO_VIEW_DIR /
    axo_label_points mirror_y) -- section/plan cuts don't need this, they
    have their own post-projection mirror_y in export_dxf/export_svg.
    """
    verts = mesh.vertices.copy()
    verts[:, 1] = site_length_ft - verts[:, 1]
    faces = mesh.faces[:, ::-1]
    return trimesh.Trimesh(vertices=verts, faces=faces, process=False)


# Default axonometric view direction: true isometric (equal angles to all
# three axes). Chosen (2026-07-03) per user request -- camera "pointing
# towards Hill St, entrance on the right" -- verified numerically (this
# view_dir puts HILL/entrance at the largest positive u of the candidates
# checked, ~+460/+695, with 5TH still the topmost reference point at
# v=+174). Applied to the Y-mirrored mesh (see mirror_mesh_y / the
# axo-section of run_vector_export_demo.py) -- X (Olive/Hill) was already
# confirmed correct and untouched by that mirror.
AXO_VIEW_DIR = np.array([1.0, -1.0, 1.0]) / np.sqrt(3.0)


def _axo_basis(view_dir):
    """Orthonormal (u, v) basis spanning the plane perpendicular to view_dir,
    for projecting 3D points to 2D screen-space under orthographic axo."""
    world_up = np.array([0.0, 0.0, 1.0])
    if abs(np.dot(view_dir, world_up)) > 0.99:
        world_up = np.array([0.0, 1.0, 0.0])
    u = np.cross(world_up, view_dir)
    u /= np.linalg.norm(u)
    v = np.cross(view_dir, u)
    v /= np.linalg.norm(v)
    return u, v


def _project_points(points, view_dir, u, v):
    points = np.asarray(points)
    return np.column_stack([points @ u, points @ v])


def compute_feature_edges(mesh, view_dir, crease_angle_deg=25.0):
    """
    Candidate line-drawing edges: silhouette edges (adjacent faces straddle
    the view direction -- one front-facing, one back-facing) and crease
    edges (dihedral angle past crease_angle_deg, e.g. a box corner, visible
    regardless of view direction). Boundary edges (owned by only one face --
    true for none of this mesh's closed solids, but included for
    robustness) are always kept. Returns an (N, 2, 3) array of edge
    endpoint pairs.
    """
    fa = mesh.face_adjacency
    fa_edges = mesh.face_adjacency_edges
    fa_angles = mesh.face_adjacency_angles
    normals = mesh.face_normals

    facing = normals @ view_dir
    front_a = facing[fa[:, 0]] > 0
    front_b = facing[fa[:, 1]] > 0
    is_silhouette = front_a != front_b
    is_crease = fa_angles > np.radians(crease_angle_deg)
    keep = is_silhouette | is_crease

    edge_vert_idx = fa_edges[keep]
    edges = mesh.vertices[edge_vert_idx]  # (N, 2, 3)

    # Boundary edges: edges belonging to exactly one face (open mesh edges).
    edges_sorted = np.sort(mesh.edges_sorted, axis=1)
    unique_sorted, inverse, edge_counts = np.unique(edges_sorted, axis=0, return_inverse=True, return_counts=True)
    boundary_edge_idx = unique_sorted[edge_counts == 1]
    if len(boundary_edge_idx):
        boundary_edges = mesh.vertices[boundary_edge_idx]
        edges = np.concatenate([edges, boundary_edges], axis=0)

    return edges


def _batch_visible(intersector, points, view_dir, eps=0.02):
    """
    Vectorized orthographic visibility test: a point is visible from the
    camera (positioned at +infinity along view_dir) if a ray cast from that
    point (nudged eps toward the camera, to clear its own source face)
    along view_dir hits nothing before leaving the scene.
    """
    origins = points + view_dir * eps
    directions = np.tile(view_dir, (len(points), 1))
    _, index_ray, _ = intersector.intersects_location(origins, directions, multiple_hits=False)
    hit_mask = np.zeros(len(points), dtype=bool)
    hit_mask[index_ray] = True
    return ~hit_mask


def axonometric_projection(mesh, view_dir=AXO_VIEW_DIR, crease_angle_deg=25.0, samples_per_edge=5):
    """
    Hidden-line-removed axonometric projection: candidate silhouette/crease
    edges, each sampled and visibility-tested by ray casting against the
    same mesh, hidden sub-segments dropped, remaining visible runs projected
    to 2D. Returns a list of 2D polylines.
    """
    view_dir = view_dir / np.linalg.norm(view_dir)
    u, v = _axo_basis(view_dir)
    edges = compute_feature_edges(mesh, view_dir, crease_angle_deg)
    if len(edges) == 0:
        return []

    intersector = mesh.ray

    t = np.linspace(0.0, 1.0, samples_per_edge)[None, :, None]  # (1, S, 1)
    starts = edges[:, 0, :][:, None, :]  # (N, 1, 3)
    ends = edges[:, 1, :][:, None, :]
    samples = starts + (ends - starts) * t  # (N, S, 3)
    n_edges, n_samples = samples.shape[0], samples.shape[1]
    flat_samples = samples.reshape(-1, 3)

    visible_flat = _batch_visible(intersector, flat_samples, view_dir)
    visible = visible_flat.reshape(n_edges, n_samples)

    polylines_3d = []
    for i in range(n_edges):
        run = []
        for s in range(n_samples):
            if visible[i, s]:
                run.append(samples[i, s])
            else:
                if len(run) >= 2:
                    polylines_3d.append(np.array(run))
                run = []
        if len(run) >= 2:
            polylines_3d.append(np.array(run))

    return [_project_points(poly, view_dir, u, v) for poly in polylines_3d]


def axo_label_points(site_width_ft, site_length_ft, view_dir=AXO_VIEW_DIR, mirror_y=False):
    """
    Street labels (see street_label_points) projected through the SAME
    view_dir/u/v basis axonometric_projection uses, at grade (z=0) -- so the
    axo drawing's orientation can be read directly instead of inferred.
    `mirror_y`: mirror the site-length coordinate before projecting (y ->
    site_length_ft - y) -- pass the same value used to build the mesh via
    mirror_mesh_y, so labels and geometry stay consistent.
    """
    view_dir = view_dir / np.linalg.norm(view_dir)
    u, v = _axo_basis(view_dir)
    plan_labels = street_label_points(site_width_ft, site_length_ft)
    out = []
    for text, (x, y) in plan_labels:
        if mirror_y:
            y = site_length_ft - y
        pt3d = np.array([[x, y, 0.0]])
        pt2d = _project_points(pt3d, view_dir, u, v)[0]
        out.append((text, tuple(pt2d)))
    return out


# Below this span, a 2D polyline from axonometric_projection is essentially
# always crease-edge noise off a column's detailed prototype mesh (median
# noise-fragment span measured at ~0.17ft on real Pershing data) rather than
# a real architectural line -- real terrace-step edges are >=9ft (VOXEL_FT).
DEFAULT_MIN_AXO_SPAN_FT = 1.5


def filter_short_polylines(polylines, min_span_ft=DEFAULT_MIN_AXO_SPAN_FT):
    """Drop 2D polylines whose max point-to-point span is under min_span_ft."""
    def span(poly):
        return max(np.hypot(*(poly[i] - poly[j])) for i in range(len(poly)) for j in range(i + 1, len(poly)))
    return [p for p in polylines if span(p) >= min_span_ft]


def section_cut(mesh, plane_origin, plane_normal):
    """
    True mesh-plane intersection. Returns a trimesh.path.Path3D of the cut
    curves, or None if the plane misses the mesh entirely.
    """
    return mesh.section(plane_origin=plane_origin, plane_normal=plane_normal)


def plan_cut(mesh, z):
    return section_cut(mesh, plane_origin=[0, 0, z], plane_normal=[0, 0, 1])


def path3d_to_2d_segments(path3d):
    """
    Flatten a trimesh Path3D's entities into a list of 2D polylines by
    dropping the (near-constant) axis the cutting plane was normal to.
    Works for both plan cuts (drop Z) and axis-aligned section cuts (drop
    the constant horizontal axis) without needing Path3D.to_planar()'s PCA,
    which can rotate the result in a way that's harder to reason about for
    a simple architectural cut.
    """
    verts = path3d.vertices
    ranges = verts.max(axis=0) - verts.min(axis=0)
    drop_axis = int(np.argmin(ranges))
    keep_axes = [i for i in range(3) if i != drop_axis]

    segments = []
    for entity in path3d.entities:
        pts = verts[entity.points][:, keep_axes]
        segments.append(pts)
    return segments, keep_axes


def grid_layer_points(real_geometry):
    """LAYER_04_GRID reference points: real column centers, (x, y_length)."""
    return [(c["x"], c["z"]) for c in real_geometry["column_positions"]]


def format_elevation_ft(z_ft):
    """Architectural elevation notation, e.g. -10.0 -> 'EL. -10'-0\"'."""
    sign = "+" if z_ft >= 0 else "-"
    total_in = round(abs(z_ft) * 12)
    ft, inch = divmod(total_in, 12)
    return f'EL. {sign}{ft}\'-{inch}"'


# Named plan-cut levels: surface + the 3 garage levels. DIAGRAMMATIC, not
# surveyed -- only the total garage depth (30ft) is real/measured (cross-
# validated from both the elevation SVGs and the OBJ column mesh); the split
# into 3 EQUAL 10ft levels is inherited from index.html's placeholder floor-
# plate slabs (its own comment flags them as assumed, not sourced from real
# per-level slab geometry). Correct GARAGE_LEVEL_ELEVATIONS_FT if the real
# garage has uneven level heights.
GARAGE_LEVEL_ELEVATIONS_FT = [
    ("SURFACE", 0.0),
    ("LEVEL 1", -10.0),
    ("LEVEL 2", -20.0),
    ("LEVEL 3 / METRO", -30.0),
]


def _layers_bounds(layers):
    all_pts = [pt for polylines in layers.values() for pts in polylines for pt in pts]
    if not all_pts:
        raise ValueError("no geometry to export")
    xs = [p[0] for p in all_pts]
    ys = [p[1] for p in all_pts]
    return min(xs), max(xs), min(ys), max(ys)


def _mirror_y(layers, labels, min_y, max_y):
    """Flip every point's y about the drawing's own vertical center (min_y/max_y
    from the UNMIRRORED data) -- a pure page-layout transform. The site's own
    grid (Olive/Hill x5th/6th), not true north, is what these drawings are
    orthogonal to (confirmed: the real DTLA street grid runs ~36 deg off true
    north here) -- so "which end is up" is a page-layout choice, not a
    geometric fact, and both are legitimate to export."""
    def flip_pt(p):
        return (p[0], (max_y - p[1]) + min_y)
    mirrored_layers = {name: [[flip_pt(p) for p in poly] for poly in polys] for name, polys in layers.items()}
    mirrored_labels = [(text, flip_pt(pos)) for text, pos in labels] if labels else labels
    return mirrored_layers, mirrored_labels


def export_dxf(out_path, layers, title=None, labels=None, mirror_y=False):
    """
    layers: dict of layer_name -> list of 2D polylines (each a list/array of
    (x, y) points). Writes one DXF with each layer as a named DXF layer;
    LWPOLYLINE for polylines with >=2 points, POINT for single points.
    `title` (e.g. an elevation tag) is placed as TEXT below the drawing.
    `labels` (e.g. street_label_points() output): list of (text, (x, y)),
    placed as TEXT in-place on LAYER_LABELS -- this is the "labels" toggle:
    pass None/[] to omit, pass street_label_points(...) to bake them in.
    `mirror_y`: flip the page vertically (see _mirror_y) -- a layout choice,
    not a geometry fix.
    """
    if mirror_y:
        _, _, min_y, max_y = _layers_bounds(layers)
        layers, labels = _mirror_y(layers, labels, min_y, max_y)

    import ezdxf
    doc = ezdxf.new("R2010")
    msp = doc.modelspace()
    for name in (LAYER_CUT, LAYER_PROJECTION, LAYER_BOTANICAL, LAYER_GRID, LAYER_LABELS):
        if name not in doc.layers:
            doc.layers.add(name)

    for layer_name, polylines in layers.items():
        for pts in polylines:
            pts = list(pts)
            if len(pts) >= 2:
                msp.add_lwpolyline(pts, dxfattribs={"layer": layer_name})
            elif len(pts) == 1:
                msp.add_point(pts[0], dxfattribs={"layer": layer_name})

    if title:
        min_x, max_x, min_y, max_y = _layers_bounds(layers)
        text_height = max((max_x - min_x), (max_y - min_y)) * 0.02
        msp.add_text(title, dxfattribs={"height": text_height, "layer": LAYER_GRID}).set_placement(
            (min_x, min_y - text_height * 2)
        )

    if labels:
        min_x, max_x, min_y, max_y = _layers_bounds(layers)
        text_height = max((max_x - min_x), (max_y - min_y)) * 0.015
        for text, pos in labels:
            msp.add_text(text, dxfattribs={"height": text_height, "layer": LAYER_LABELS}).set_placement(pos)

    doc.saveas(out_path)
    return out_path


def export_svg(out_path, layers, margin=20.0, title=None, labels=None, mirror_y=False):
    """Minimal hand-rolled SVG writer -- one <g> per layer, polylines as <polyline>.
    `title` (e.g. an elevation tag) is placed as <text> below the drawing.
    `labels`: see export_dxf -- placed as in-place <text> on LAYER_LABELS.
    `mirror_y`: see export_dxf -- flips the page vertically, a layout choice."""
    if mirror_y:
        _, _, min_y0, max_y0 = _layers_bounds(layers)
        layers, labels = _mirror_y(layers, labels, min_y0, max_y0)
    min_x, max_x, min_y, max_y = _layers_bounds(layers)
    title_space = 24.0 if title else 0.0
    width = (max_x - min_x) + 2 * margin
    height = (max_y - min_y) + 2 * margin + title_space

    def flip(pt):
        # SVG y-down; flip so the drawing reads right-side-up.
        return (pt[0] - min_x + margin, (max_y - pt[1]) + margin)

    layer_colors = LAYER_COLORS

    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width:.2f} {height:.2f}">']
    parts.append(f'<rect width="{width:.2f}" height="{height:.2f}" fill="white"/>')
    for layer_name, polylines in layers.items():
        color = layer_colors.get(layer_name, "#000000")
        parts.append(f'<g id="{layer_name}" stroke="{color}" fill="none" stroke-width="0.5">')
        for pts in polylines:
            pts = list(pts)
            if len(pts) >= 2:
                pts_str = " ".join(f"{p[0]:.3f},{p[1]:.3f}" for p in (flip(p) for p in pts))
                parts.append(f'<polyline points="{pts_str}" />')
            elif len(pts) == 1:
                fx, fy = flip(pts[0])
                parts.append(f'<circle cx="{fx:.3f}" cy="{fy:.3f}" r="1" fill="{color}" stroke="none"/>')
        parts.append("</g>")
    if labels:
        parts.append(f'<g id="{LAYER_LABELS}" fill="{layer_colors[LAYER_LABELS]}">')
        for text, pos in labels:
            fx, fy = flip(pos)
            parts.append(
                f'<text x="{fx:.3f}" y="{fy:.3f}" font-family="sans-serif" '
                f'font-size="10" text-anchor="middle">{text}</text>'
            )
        parts.append("</g>")
    if title:
        parts.append(
            f'<text x="{margin:.2f}" y="{height - 6:.2f}" '
            f'font-family="sans-serif" font-size="14" fill="#000000">{title}</text>'
        )
    parts.append("</svg>")

    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(parts))
    return out_path


def export_png(out_path, layers, title=None, labels=None, mirror_y=False, dpi=150):
    """
    Raster PNG rendering of the same layer data as export_svg -- a quick
    visual reference, not a CAD deliverable (that's DXF/SVG). Uses
    matplotlib (already a project dependency) rather than rasterizing the
    SVG, so there's no extra rendering-library dependency to keep in sync
    with the vector writers' layer/color scheme.
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.collections import LineCollection

    if mirror_y:
        _, _, min_y0, max_y0 = _layers_bounds(layers)
        layers, labels = _mirror_y(layers, labels, min_y0, max_y0)
    min_x, max_x, min_y, max_y = _layers_bounds(layers)
    width_ft = max_x - min_x
    height_ft = max_y - min_y

    fig_w = 10.0
    fig_h = fig_w * (height_ft / width_ft) if width_ft > 0 else fig_w
    fig, ax = plt.subplots(figsize=(fig_w, fig_h))

    for layer_name, polylines in layers.items():
        color = LAYER_COLORS.get(layer_name, "#000000")
        lines = [pts for pts in polylines if len(pts) >= 2]
        if lines:
            ax.add_collection(LineCollection(lines, colors=color, linewidths=0.8))
        for pts in polylines:
            if len(pts) == 1:
                ax.plot(pts[0][0], pts[0][1], "o", color=color, markersize=1.5)

    if labels:
        for text, pos in labels:
            ax.text(pos[0], pos[1], text, color=LAYER_COLORS[LAYER_LABELS],
                     fontsize=8, ha="center", va="center")

    margin = max(width_ft, height_ft) * 0.03
    ax.set_xlim(min_x - margin, max_x + margin)
    ax.set_ylim(min_y - margin, max_y + margin)
    ax.set_aspect("equal")
    ax.axis("off")
    if title:
        ax.set_title(title, fontsize=10, loc="left")

    fig.savefig(out_path, dpi=dpi, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return out_path
