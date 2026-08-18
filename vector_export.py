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
import math
import time

import numpy as np

# trimesh is a lazy, per-function import (2026-07-09 cut-sheet flatten
# supplement) -- only the mesh-building/cutting functions below actually
# need it (_mesh_from_real, build_terraced_solid, build_combined_mesh,
# build_named_scene, mirror_mesh_y); the DXF/SVG/PNG export primitives and
# the real_slab_plan_layers flatten (both pure 2D, no mesh construction)
# don't. blender_cockpit.py's own docstring already flags trimesh as a real
# friction point ("Deliberately does NOT import vector_export.py -- that
# module needs trimesh") -- same reasoning sketch_weight_mapper.py/
# amenity_deficit.py already use for their own heavier optional imports.

LAYER_CUT = "LAYER_01_CUT"
LAYER_PROJECTION = "LAYER_02_PROJECTION"
LAYER_BOTANICAL = "LAYER_03_BOTANICAL"
LAYER_GRID = "LAYER_04_GRID"
LAYER_LABELS = "LAYER_05_LABELS"
LAYER_GREENSCAPE = "LAYER_06_GREENSCAPE"

LAYER_COLORS = {
    LAYER_CUT: "#000000",
    LAYER_PROJECTION: "#999999",
    LAYER_BOTANICAL: "#2e7d32",
    LAYER_GRID: "#cc0000",
    LAYER_LABELS: "#0066cc",
    LAYER_GREENSCAPE: "#4caf50",
}

# 2026-08-04: named hatch patterns for closed massing/ground-cover polygons
# (see export_svg/export_png/export_dxf's `hatch_layers` param -- a
# dict of layer_name -> one of these keys, not the raw pattern itself, so
# each format can supply its own concrete rendering of the same concept).
# "building" = diagonal poche (standard site-plan massing convention),
# "grass" = blade/tick texture (standard ground-cover convention -- ezdxf's
# own built-in pattern is literally named GRASS), "tree" = stipple/dot
# texture (standard canopy-foliage convention).
HATCH_BUILDING = "building"
HATCH_GRASS = "grass"
HATCH_TREE = "tree"

_PNG_HATCH_CHARS = {HATCH_BUILDING: "///", HATCH_GRASS: "|||", HATCH_TREE: "..."}
_DXF_HATCH_PATTERN = {HATCH_BUILDING: "ANSI31", HATCH_GRASS: "GRASS", HATCH_TREE: "DOTS"}
_SVG_HATCH_DEFS = {
    HATCH_BUILDING: (
        '<pattern id="hatch-building" patternUnits="userSpaceOnUse" width="4" height="4" '
        'patternTransform="rotate(45)">'
        '<rect width="4" height="4" fill="white"/>'
        '<line x1="0" y1="0" x2="0" y2="4" stroke="#000000" stroke-width="1.1"/>'
        '</pattern>'
    ),
    HATCH_GRASS: (
        '<pattern id="hatch-grass" patternUnits="userSpaceOnUse" width="4" height="4">'
        '<rect width="4" height="4" fill="white"/>'
        '<line x1="1" y1="0.4" x2="1" y2="2.4" stroke="#000000" stroke-width="0.6"/>'
        '<line x1="3" y1="1.6" x2="3" y2="3.6" stroke="#000000" stroke-width="0.6"/>'
        '</pattern>'
    ),
    HATCH_TREE: (
        '<pattern id="hatch-tree" patternUnits="userSpaceOnUse" width="3" height="3">'
        '<rect width="3" height="3" fill="white"/>'
        '<circle cx="1.5" cy="1.5" r="0.5" fill="#000000"/>'
        '</pattern>'
    ),
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

# 2026-08-03: labels used to sit exactly on the boundary coordinate with no
# rotation, so long labels on the x0/xmax edges (vertical streets, rendered
# horizontally) routinely overlapped well past the drawing's own margin into
# real site geometry. LABEL_OFFSET_FT pushes each label out past the
# boundary into the margin; street_label_points' rotation lets each label
# run parallel to its own street instead of always reading left-to-right.
LABEL_OFFSET_FT = 8.0


def street_label_points(site_width_ft, site_length_ft):
    """(text, (x, y), rotation_deg) triples at the midpoint of each site
    edge, offset LABEL_OFFSET_FT outward into the margin and rotated to run
    parallel to that edge's own street (0 deg for the y0/ymax edges, 90 deg
    for the x0/xmax edges), for LAYER_LABELS."""
    edge_pos = {
        "x0": ((-LABEL_OFFSET_FT, site_length_ft / 2), 90),
        "xmax": ((site_width_ft + LABEL_OFFSET_FT, site_length_ft / 2), 90),
        "y0": ((site_width_ft / 2, -LABEL_OFFSET_FT), 0),
        "ymax": ((site_width_ft / 2, site_length_ft + LABEL_OFFSET_FT), 0),
    }
    return [(text, *edge_pos[edge]) for text, edge in STREET_LABELS]


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
    import trimesh
    verts = _obj_to_site(mesh_dict["vertices"])
    faces = np.array(mesh_dict["faces"], dtype=int).reshape(-1, 3)
    return trimesh.Trimesh(vertices=verts, faces=faces, process=False)


# The real column_prototype_mesh (Rhino export) is a ~2.2x2.2x30ft column
# tessellated to 1984 faces -- a real Rhino NURBS-to-mesh tessellation
# setting, not intentional detail (confirmed: not even watertight). Reused
# per-instance across 294 real column positions, this alone was 583,296 of
# the 587,456 total faces in the combined export mesh (99.3%) -- the actual
# dominant cause of axonometric_projection's hidden-line-removal crashing
# with a 27+ GiB memory allocation on the real site (2026-07-11 finding;
# the terrain-mesh rewrite above fixed a real, separate problem but barely
# moved this number). Decimating the ONE prototype mesh once, before
# instancing 294 times, is cheap and preserves the column's real bounds/
# silhouette (verified: extents unchanged within a few thousandths of a
# foot at target=100) -- more than enough detail for a line drawing's
# silhouette/crease edges, which don't need the original NURBS tessellation
# density. Only affects THIS module's export output, not the live 3D
# viewport (which loads real_geometry.json's meshes independently).
COLUMN_DECIMATE_TARGET_FACES = 100


def build_context_meshes(real_geometry, decimate_columns=True):
    """
    Real static structure from real_geometry.json, converted to site-local
    Z-up coordinates: one mesh per real column instance, plus the tunnel,
    secondary entrance, and both ramp clusters (3 levels each).

    `decimate_columns`: simplify the column prototype (see
    COLUMN_DECIMATE_TARGET_FACES comment above) before instancing -- default
    True since every current caller needs the lighter mesh for hidden-line
    removal to complete at all; kept as a parameter (not hardcoded) in case
    a future caller needs the original full-fidelity column geometry.
    """
    meshes = {}

    proto = _mesh_from_real(real_geometry["column_prototype_mesh"])
    if decimate_columns:
        proto = proto.simplify_quadric_decimation(face_count=COLUMN_DECIMATE_TARGET_FACES)
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


# --- Hybrid real-slab + greedy-mesh terrain reconstruction (2026-07-11) ---
#
# build_terraced_solid's original approach -- one trimesh.creation.box() per
# voxel, unconditionally, regardless of whether excavation ever touched that
# cell -- produces a mesh with massive numbers of exactly-touching, coplanar
# faces between adjacent same-elevation voxels (the full real site: 618,900
# faces). This isn't just wasteful: it crashes axonometric_projection()'s
# hidden-line-removal outright (confirmed via direct testing: a
# numpy._core._exceptions._ArrayMemoryError trying to allocate 27+ GiB during
# trimesh's ray-triangle candidate search -- a real, pre-existing trimesh/
# rtree performance pathology with dense grids of touching boxes, confirmed
# via scaling tests: 400 touching boxes completes in ~7s, ~2680 crashes).
#
# The fix reuses data StructuralFramingEngine.real_slab_fragments() already
# computes (which voxel cells are still "remaining" vs "removed" per real,
# Rhino-extracted slab plate -- already load-bearing for the frontend's
# RealSlabFragments rendering and the slab-harvest-tonnage math, but
# previously never consumed here) instead of reconstructing an approximate
# voxel-box terrain from scratch:
#   - Cells still covered by a real slab -> that slab's own thin plate
#     geometry (its real top_corners_ft/thickness_ft), boolean-cut where
#     excavated -- accurate shape, and dramatically fewer faces than a full-
#     depth box grid (a real slab is one thin plate, not thousands of boxes).
#   - Cells with no real precedent (excavated deeper than every real slab
#     present at that XY, or outside every real slab's footprint --
#     genuinely new/designed terracing) -> greedy-merged boxes (adjacent
#     same-elevation cells combined into the fewest rectangles before
#     extruding), still running full-depth to the shared floor so new/
#     designed excavation still reads as one solid stepped canyon.
# See terracing_engine.py's StructuralFramingEngine.classify_terrain_cells
# for the per-cell classification this all depends on.


def _merge_voxel_rectangles(cells):
    """
    Greedy rectangle-merge over a set of (gx, gy) grid indices (already
    filtered to one homogeneous group -- one elevation, or one slab's
    removed set) -- turns "one box per voxel" into "one box per merged
    region." NOT globally minimal in rectangle count (that's the harder
    largest-rectangle-in-histogram problem); this greedy strip-growing
    approach is simple, fast, and effective on the kind of large contiguous
    blocks real terrace/slab data actually produces (Voxel.z_ft is already
    a STEPPED value, not a smooth continuum, so most same-band regions
    genuinely are large contiguous rectangles already). Worst case (e.g. a
    checkerboard pattern) degrades to one rectangle per cell -- never worse
    than the original per-voxel approach, just usually far better.

    Returns a list of inclusive grid-index rectangles (gx0, gy0, gx1, gy1).
    """
    remaining = set(cells)
    rects = []
    while remaining:
        gx0, gy0 = min(remaining)
        gx1 = gx0
        while (gx1 + 1, gy0) in remaining:
            gx1 += 1
        gy1 = gy0
        while all((gx, gy1 + 1) in remaining for gx in range(gx0, gx1 + 1)):
            gy1 += 1
        rects.append((gx0, gy0, gx1, gy1))
        for gx in range(gx0, gx1 + 1):
            for gy in range(gy0, gy1 + 1):
                remaining.discard((gx, gy))
    return rects


def _extrude_grid_rect(gx0, gy0, gx1, gy1, vf, z_top, z_bottom):
    """One box spanning grid cells [gx0,gx1] x [gy0,gy1] inclusive (voxel_ft
    units), extruded from z_bottom up to z_top -- replaces build_terraced_
    solid's old per-voxel trimesh.creation.box() call site, now called once
    per _merge_voxel_rectangles() result instead of once per voxel."""
    import trimesh
    width = (gx1 - gx0 + 1) * vf
    depth = (gy1 - gy0 + 1) * vf
    height = z_top - z_bottom
    box = trimesh.creation.box(extents=[width, depth, height])
    cx = gx0 * vf + width / 2
    cy = gy0 * vf + depth / 2
    cz = z_bottom + height / 2
    box.apply_translation([cx, cy, cz])
    return box


def _order_quad_corners(corners):
    """Sort 4 [x,y,z] corners into a non-crossing loop by angle around
    their own centroid (plan XY only; Z tags along unchanged) -- mirrors
    Viewport.jsx's orderQuadCorners, since Rhino's Brep.Vertices order for
    a planar face isn't guaranteed to trace a boundary loop (raster/grid
    order empirically), which would triangulate into a crossed/bowtie quad
    used directly."""
    cx = sum(c[0] for c in corners) / len(corners)
    cy = sum(c[1] for c in corners) / len(corners)
    return sorted(corners, key=lambda c: math.atan2(c[1] - cy, c[0] - cx))


# top(0,1,2,3) / bottom(4,5,6,7), matching corner order on both faces (bottom
# is top shifted straight down in Z) -- identical convention to Viewport.jsx's
# SLAB_PLATE_INDICES, kept in sync deliberately so the live viewport and this
# export path render the exact same plate shape.
_SLAB_PLATE_INDICES = [
    0, 1, 2, 0, 2, 3,       # top
    4, 6, 5, 4, 7, 6,       # bottom (reversed winding)
    0, 4, 1, 1, 4, 5,       # side 0-1
    1, 5, 2, 2, 5, 6,       # side 1-2
    2, 6, 3, 3, 6, 7,       # side 2-3
    3, 7, 0, 0, 7, 4,       # side 3-0
]


def _build_slab_plate_mesh(slab, removed_cells, vf, pad_ft=0.5):
    """
    One real slab plate, built from its own top_corners_ft/thickness_ft (a
    thin plate, NOT a full-depth voxel-box approximation), boolean-cut where
    removed_cells (a list of (gx, gy) grid indices, already merged into few
    rectangles) were excavated away -- ONE batched trimesh.boolean.difference
    call per slab, not one per removed cell.

    Bottom face offset straight down in world Z by thickness_ft (not along
    the tilted normal) -- same simplification Viewport.jsx's RealSlabPlate
    already uses and documents: at real ramp tilt angles (~1.7deg here,
    cos(1.7deg) > 0.9995) the difference is sub-1/8" over a 1ft-thick plate.

    Cutter boxes are oversized by pad_ft in XY and in Z beyond the plate's
    own thickness -- exact-coincident faces at a cut boundary are exactly
    the kind of degenerate case that make manifold boolean engines fail or
    produce garbage, so the cutter deliberately fully and unambiguously
    penetrates the plate.

    Returns None only if removed_cells covers the whole plate (nothing
    left -- caller should skip this slab). If the boolean cut fails or
    produces a non-watertight/empty result (realistic for tilted ramp_slab
    geometry), falls back to the ORIGINAL UNCUT plate with a printed
    warning -- never crashes the whole export over one problematic slab,
    never silently drops a real structural element by returning None here.
    """
    import trimesh

    ordered = _order_quad_corners(slab["top_corners_ft"])
    top = [tuple(c) for c in ordered]
    thickness = slab["thickness_ft"]
    bottom = [(x, y, z - thickness) for x, y, z in top]
    verts = top + bottom
    faces = [_SLAB_PLATE_INDICES[i:i + 3] for i in range(0, len(_SLAB_PLATE_INDICES), 3)]
    plate = trimesh.Trimesh(vertices=verts, faces=faces, process=True)

    if not removed_cells:
        return plate

    cutters = []
    z_top = slab["z_top_ft"] + thickness + pad_ft
    z_bottom = slab["z_top_ft"] - thickness - pad_ft
    for gx0, gy0, gx1, gy1 in _merge_voxel_rectangles(removed_cells):
        width = (gx1 - gx0 + 1) * vf + pad_ft
        depth = (gy1 - gy0 + 1) * vf + pad_ft
        cutter = trimesh.creation.box(extents=[width, depth, z_top - z_bottom])
        cx = gx0 * vf + (gx1 - gx0 + 1) * vf / 2
        cy = gy0 * vf + (gy1 - gy0 + 1) * vf / 2
        cz = (z_top + z_bottom) / 2
        cutter.apply_translation([cx, cy, cz])
        cutters.append(cutter)

    label = f"{slab.get('parent', '?')}@{slab.get('z_top_ft', '?')}"
    try:
        result = trimesh.boolean.difference([plate, *cutters], engine="manifold")
        if result is None or len(result.faces) == 0 or not result.is_watertight or result.volume <= 0:
            raise ValueError(f"non-watertight or empty result (is_watertight="
                              f"{getattr(result, 'is_watertight', None)}, "
                              f"faces={len(result.faces) if result is not None else 0})")
        return result
    except Exception as exc:  # noqa: BLE001 -- one slab's CSG failure must not sink the whole export
        print(f"WARNING: boolean cut failed for real slab {label}, keeping uncut plate: {exc}")
        return plate


def build_real_slab_meshes(real_geometry, engine, framing_engine=None):
    """
    One thin, boolean-cut mesh per real slab plate, using
    StructuralFramingEngine.real_slab_fragments()'s already-computed
    remaining/removed classification instead of reconstructing an
    approximate voxel-box terrain from scratch. Returns {slab_key: mesh},
    omitting any slab with zero remaining area (fully excavated away).

    `framing_engine`: pass an already-constructed StructuralFramingEngine
    to avoid rebuilding the column<->slab graph when the caller already has
    one; builds its own otherwise.
    """
    from terracing_engine import StructuralFramingEngine

    if framing_engine is None:
        framing_engine = StructuralFramingEngine(real_geometry, engine)
    fragments = framing_engine.real_slab_fragments()

    meshes = {}
    for key, entry in fragments.items():
        if len(entry["remaining"]) == 0:
            continue
        removed_cells = [(gx, gy) for gx, gy, _wx, _wy in entry["removed"]]
        mesh = _build_slab_plate_mesh(entry["slab"], removed_cells, engine.voxel_ft)
        if mesh is not None:
            meshes[key] = mesh
    return meshes


def build_terraced_solid(engine, voxels, real_geometry, floor_margin_ft=10.0):
    """
    Build the site's terrain mesh as a hybrid of real slab plates (where
    real Rhino-extracted structure exists and is at least partially
    exposed) plus greedy-merged boxes (for cells with no real precedent --
    genuinely new/designed terracing deeper than every real slab present at
    that XY). See the module-level comment above this section for the full
    rationale -- this replaces the old one-box-per-voxel-unconditionally
    approach, which produced a mesh too dense for axonometric_projection's
    hidden-line-removal to complete on the real site.

    Fallback cells (no real slab classification) keep running full-depth to
    a shared floor_z (same convention/value as the original implementation)
    so genuinely new/designed excavation still reads as one solid stepped
    canyon -- only real slabs become thin plates, by explicit design
    decision (a cut between two real garage levels now correctly shows real
    void there instead of solid material, matching how an actual parking
    garage has real floor-to-floor voids).
    """
    import trimesh
    from terracing_engine import StructuralFramingEngine

    vf = engine.voxel_ft
    floor_z = -(engine.max_canyon_depth_ft + floor_margin_ft)

    framing = StructuralFramingEngine(real_geometry, engine)
    fragments = framing.real_slab_fragments()
    cell_class = framing.classify_terrain_cells(fragments)
    slab_meshes = build_real_slab_meshes(real_geometry, engine, framing)

    by_z = {}
    for v in voxels:
        if cell_class.get((v.gx, v.gy)) is not None:
            continue  # covered by a real slab plate above
        by_z.setdefault(v.z_ft, []).append((v.gx, v.gy))

    fallback_boxes = []
    for z_top, cells in by_z.items():
        for gx0, gy0, gx1, gy1 in _merge_voxel_rectangles(cells):
            fallback_boxes.append(_extrude_grid_rect(gx0, gy0, gx1, gy1, vf, z_top, floor_z))

    return trimesh.util.concatenate([*slab_meshes.values(), *fallback_boxes])


def build_combined_mesh(real_geometry, engine, voxels):
    import trimesh
    context = build_context_meshes(real_geometry)
    terrace = build_terraced_solid(engine, voxels, real_geometry)
    all_meshes = [terrace, context["tunnel"], context["secondary_entrance"], context["metro_connector"]]
    all_meshes.extend(context["columns"])
    all_meshes.extend(context["ramps"])
    return trimesh.util.concatenate(all_meshes)


def concat_meshes(meshes):
    """trimesh.util.concatenate, skipping None entries -- lets callers pass
    build_combined_mesh(...)'s result alongside build_massing_mesh(...)'s
    (which is None when there's no massing to add) without a None check at
    every call site."""
    import trimesh
    meshes = [m for m in meshes if m is not None]
    return trimesh.util.concatenate(meshes) if meshes else None


def build_massing_mesh(building_specs):
    """One trimesh box per program-derived building mass (terracing_engine.
    BuildingMassEngine's StructuralElement("building_mass", ...) output --
    see drawing_styles.py's own massing box builder for how these get
    constructed from `zones`). x_ft/y_ft are the box CENTER (BuildingMassEngine's
    own convention, NOT build_terraced_solid's grid-corner one), z_top_ft is
    the box TOP -- matches StructuralElement's top-anchored convention used
    everywhere else in this pipeline. Returns None if building_specs is
    empty (2026-08-12: section/axo/long_section never included building
    massing at all before this -- only the separate "plan" aerial view drew
    it, via its own zones-polygon path -- confirmed by direct code reading
    that build_combined_mesh() above never touches zones/program massing)."""
    import trimesh
    if not building_specs:
        return None
    boxes = []
    for spec in building_specs:
        box = trimesh.creation.box(extents=[spec.scale, spec.scale_y, spec.height_ft])
        box.apply_translation([spec.x_ft, spec.y_ft, spec.z_top_ft - spec.height_ft / 2])
        boxes.append(box)
    return trimesh.util.concatenate(boxes)


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
    import trimesh
    context = build_context_meshes(real_geometry)
    terrace = build_terraced_solid(engine, voxels, real_geometry)
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
    import trimesh
    verts = mesh.vertices.copy()
    verts[:, 1] = site_length_ft - verts[:, 1]
    faces = mesh.faces[:, ::-1]
    return trimesh.Trimesh(vertices=verts, faces=faces, process=False)


# Default axonometric view direction: true isometric (equal angles to all
# three axes). Originally [1,-1,1] (chosen 2026-07-03, "Hill St, entrance
# on the right"). Corrected 2026-08-12: the real invariant that matters is
# the Hill St / 5th St corner (the real-world Pershing Square Station
# entrance location) reading at the TOP of the frame, CONSISTENTLY -- not
# just "the metro connector mesh happens to look like it's in the top-right
# region" (an earlier pass here tried [-1,-1,1], picked by eyeballing an
# unlabeled render; it put the connector on the right side but NOT at the
# actual top -- see the numeric check below). Verified properly this time
# by projecting all 4 site corners (via axo_label_points' own u/v basis,
# same math as the real STREET_LABELS) through each of the 4 above-grade
# isometric octants and comparing which one ranks the Hill/5th corner
# (xmax, ymax) highest on the v axis: [-1,-1,1] ranked it only 3rd of 4
# (Hill/6th was actually topmost there); [-1,1,1] ranks Hill/5th 1st (true
# topmost) while still 2nd-most-rightward of the 4 corners (not
# left-leaning) -- confirmed visually too (HILL ST/5TH ST labels meet
# exactly at the top corner, right at the connector). Still a proper
# rotation of the same view family, not a post-hoc 2D mirror (a mirror_y
# page-flip was tried first and rejected -- it broke handedness, since
# axo's v-axis encodes real 3D structure unlike a flat plan's, making the
# drawing read as upside-down/mirrored instead of just relocated). Applied
# to the Y-mirrored mesh (see mirror_mesh_y) -- kept as-is; only this
# view_dir changed.
AXO_VIEW_DIR = np.array([-1.0, 1.0, 1.0]) / np.sqrt(3.0)


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


def _batch_visible(intersector, points, view_dir, eps=0.02, chunk_size=2000, time_budget_s=60):
    """
    Vectorized orthographic visibility test: a point is visible from the
    camera (positioned at +infinity along view_dir) if a ray cast from that
    point (nudged eps toward the camera, to clear its own source face)
    along view_dir hits nothing before leaving the scene.

    Chunked rather than one intersects_location() call over every point at
    once -- trimesh's ray-triangle candidate search has a real, confirmed
    memory pathology on dense grids of touching/coplanar faces (see
    build_terraced_solid's own comment above, and axonometric_projection's
    docstring: a live repeat of this during dev testing hit ~50GB RSS on a
    single monolithic call). Chunking bounds peak memory to whatever one
    chunk costs regardless of total point count. A chunk that still throws
    MemoryError, or a total runtime past time_budget_s, fails OPEN (those
    points are left marked visible, i.e. hidden-line removal is skipped for
    just that slice) rather than crashing the whole render -- a degraded
    drawing beats none. Embree (embreex, when installed) makes this path
    fast/stable enough that chunking rarely matters in practice; it's kept
    as the defense-in-depth backstop regardless of which ray backend trimesh
    picked, since embreex isn't guaranteed to be present everywhere this
    runs.
    """
    origins_all = points + view_dir * eps
    directions_all = np.tile(view_dir, (len(points), 1))
    hit_mask = np.zeros(len(points), dtype=bool)
    start = time.monotonic()
    for i in range(0, len(points), chunk_size):
        if time.monotonic() - start > time_budget_s:
            break
        try:
            _, index_ray, _ = intersector.intersects_location(
                origins_all[i:i + chunk_size], directions_all[i:i + chunk_size], multiple_hits=False)
            hit_mask[i + index_ray] = True
        except MemoryError:
            continue
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
    # Rotation isn't re-derived for the isometric basis here (this view is
    # unreachable from the UI -- see drawing_styles.py's view=="axo" comment
    # -- so it's not worth the extra projection math); the plan-space angle
    # is passed through unchanged.
    for text, (x, y), angle in plan_labels:
        if mirror_y:
            y = site_length_ft - y
        pt3d = np.array([[x, y, 0.0]])
        pt2d = _project_points(pt3d, view_dir, u, v)[0]
        out.append((text, tuple(pt2d), angle))
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


def mesh_top_edges(mesh, crease_angle_deg=25.0):
    """
    Flattens ONE mesh's silhouette/crease edges straight down (view_dir=
    [0,0,-1]) to 2D (x, y), with NO depth-sorted hidden-line removal --
    deliberately skips axonometric_projection's ray-cast visibility pass
    (_batch_visible/mesh.ray), the documented crash-prone code path on this
    site's geometry (see lineweight_layers' view=="axo" comment in
    drawing_styles.py). Candidate edges come from the same cheap, ray-cast-
    free compute_feature_edges() axonometric_projection also uses
    (silhouette/crease/boundary edges via face adjacency, O(faces), no
    rtree).

    2026-08-04: this used to be called ONCE on the entire combined mesh
    (terrace/excavation solid + all real context objects) to build a whole-
    site "PLAN -- AERIAL" view -- but that drew excavation/retaining-wall
    edges regardless of depth, i.e. showed geometry a covering surface
    would actually hide, which violates real site-plan convention (nothing
    below what's visible from directly above, no hidden-line dashing).
    lineweight_layers' view=="plan" branch now calls this per small, real,
    at-grade context object (secondary entrance, metro connector, columns,
    ramps -- see vector_export.build_context_meshes) instead, since those
    are already small/shallow enough that skipping full hidden-line removal
    on each individually is a safe simplification; the terrace/excavation
    floor and building massing are instead derived from the voxel/bay grid
    heightfield directly in drawing_styles.py (exact occlusion, no mesh
    ray-casting needed there either -- bays are claimed exclusively, so a
    simple coverage mask is enough).
    Returns a list of 2D (x, y) polylines.
    """
    view_dir = np.array([0.0, 0.0, -1.0])
    edges = compute_feature_edges(mesh, view_dir, crease_angle_deg)
    if len(edges) == 0:
        return []
    return [edge[:, :2] for edge in edges]


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


def _order_quad_corners_xy(corners_xy):
    """Sort 4 (x, y) corners by angle around their own centroid so they trace
    a proper non-crossing loop -- same fix as Viewport.jsx's
    orderQuadCorners, needed for the same reason: Rhino's real per-plate
    corner order (real_slabs[i]["top_corners_ft"], see the real-slab-graph
    supplement) is a raster/grid order, not a boundary loop, and using it
    directly would draw a crossed/bowtie polygon."""
    cx = sum(p[0] for p in corners_xy) / len(corners_xy)
    cy = sum(p[1] for p in corners_xy) / len(corners_xy)
    import math as _math
    return sorted(corners_xy, key=lambda p: _math.atan2(p[1] - cy, p[0] - cx))


def _circle_polyline(cx, cy, radius, segments=16):
    import math as _math
    pts = [
        (cx + radius * _math.cos(2 * _math.pi * i / segments),
         cy + radius * _math.sin(2 * _math.pi * i / segments))
        for i in range(segments)
    ]
    return pts + [pts[0]]


def real_slab_plan_layers(real_geometry):
    """Flattened structural plan of the REAL slabs/columns (2026-07-09
    cut-sheet flatten supplement) -- one DXF/SVG layer per real level
    ("SLABS_L1"/"SLABS_L2"/"SLABS_L3", each holding that level's real
    floor_slab + ramp_slab footprints as closed polygons, plan-projected --
    dropping z is exact for footprint purposes even for the tilted ramp_slab
    plates, since their tilt is purely vertical/length-plane, never in-plan,
    same fact build_column_slab_graph relies on) plus one "COLUMNS" layer
    (real per-column circles at real diameter, not centroid points like the
    older grid_layer_points above).

    This is a real quantity/schedule drawing, not a CNC nesting layout --
    cast concrete slabs and existing columns are the wrong scale to "nest"
    on a stock sheet; a labeled plan is what a contractor actually uses for
    these two material families. True nested cut-layouts for the smaller
    shop-fabricated kinds (steel plates, timber members) are a separate,
    later step once their real fabrication method is decided (per the plan
    doc).

    Returns (layers, labels) ready for export_dxf/export_svg/export_png.
    """
    layers = {}
    labels = []

    for slab in real_geometry.get("real_slabs", []):
        layer_name = f"SLABS_{slab['level']}"
        corners_xy = _order_quad_corners_xy([(c[0], c[1]) for c in slab["top_corners_ft"]])
        polygon = corners_xy + [corners_xy[0]]
        layers.setdefault(layer_name, []).append(polygon)
        cx = sum(p[0] for p in corners_xy) / len(corners_xy)
        cy = sum(p[1] for p in corners_xy) / len(corners_xy)
        tag = "RAMP" if slab["kind"] == "ramp_slab" else "SLAB"
        labels.append((
            f"{slab['parent']} [{tag}] {slab['area_ft2']:.0f}sf x {slab['thickness_ft']*12:.0f}\"",
            (cx, cy), 0,
        ))

    columns = real_geometry.get("real_columns", [])
    if columns:
        layers["COLUMNS"] = [_circle_polyline(c["x"], c["z"], c["diameter_ft"] / 2) for c in columns]
        labels.append((
            f"{len(columns)} real columns, {columns[0]['diameter_ft']:.2f}ft dia typ.",
            (columns[0]["x"], columns[0]["z"]), 0,
        ))

    return layers, labels


def export_real_slab_plan(real_geometry, out_path, fmt="dxf", mirror_y=False):
    """Convenience wrapper: real_slab_plan_layers() -> export_dxf/svg/png.
    fmt: "dxf", "svg", or "png"."""
    layers, labels = real_slab_plan_layers(real_geometry)
    title = "Real Slab/Column Plan -- Pershing Metabolizer"
    if fmt == "dxf":
        return export_dxf(out_path, layers, title=title, labels=labels, mirror_y=mirror_y)
    if fmt == "svg":
        return export_svg(out_path, layers, title=title, labels=labels, mirror_y=mirror_y)
    if fmt == "png":
        return export_png(out_path, layers, title=title, labels=labels, mirror_y=mirror_y)
    raise ValueError(f"unknown fmt {fmt!r}, expected dxf/svg/png")


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
    mirrored_labels = [(text, flip_pt(pos), angle) for text, pos, angle in labels] if labels else labels
    return mirrored_layers, mirrored_labels


def export_dxf(out_path, layers, title=None, labels=None, mirror_y=False, hatch_layers=None):
    """
    layers: dict of layer_name -> list of 2D polylines (each a list/array of
    (x, y) points). Writes one DXF with each layer as a named DXF layer;
    LWPOLYLINE for polylines with >=2 points, POINT for single points.
    `title` (e.g. an elevation tag) is placed as TEXT below the drawing.
    `labels` (e.g. street_label_points() output): list of (text, (x, y),
    rotation_deg), placed as TEXT in-place on LAYER_LABELS -- this is the
    "labels" toggle: pass None/[] to omit, pass street_label_points(...)
    to bake them in.
    `mirror_y`: flip the page vertically (see _mirror_y) -- a layout choice,
    not a geometry fix.
    `hatch_layers`: see export_svg -- dict of layer_name -> HATCH_BUILDING/
    HATCH_GRASS/HATCH_TREE. Closed polygons on these layers also get a real
    DXF HATCH entity (the matching named pattern -- ezdxf ships "ANSI31"/
    "GRASS"/"DOTS" built in) on top of the LWPOLYLINE outline, so massing/
    ground-cover reads as a solid tonal shape in CAD too, not just an
    outline.
    """
    hatch_layers = hatch_layers or {}
    if mirror_y:
        _, _, min_y, max_y = _layers_bounds(layers)
        layers, labels = _mirror_y(layers, labels, min_y, max_y)

    import ezdxf
    doc = ezdxf.new("R2010")
    msp = doc.modelspace()
    for name in (LAYER_CUT, LAYER_PROJECTION, LAYER_BOTANICAL, LAYER_GRID, LAYER_LABELS, LAYER_GREENSCAPE):
        if name not in doc.layers:
            doc.layers.add(name)

    for layer_name, polylines in layers.items():
        pattern_key = hatch_layers.get(layer_name)
        for pts in polylines:
            pts = list(pts)
            if len(pts) >= 2:
                msp.add_lwpolyline(pts, dxfattribs={"layer": layer_name})
                if pattern_key and len(pts) >= 3:
                    hatch = msp.add_hatch(dxfattribs={"layer": layer_name})
                    hatch.set_pattern_fill(_DXF_HATCH_PATTERN.get(pattern_key, "ANSI31"), scale=2.0)
                    hatch.paths.add_polyline_path(pts, is_closed=True)
            elif len(pts) == 1:
                msp.add_point(pts[0], dxfattribs={"layer": layer_name})

    if title:
        min_x, max_x, min_y, max_y = _layers_bounds(layers)
        text_height = max((max_x - min_x), (max_y - min_y)) * 0.01
        msp.add_text(title, dxfattribs={"height": text_height, "layer": LAYER_GRID}).set_placement(
            (min_x, min_y - text_height * 2)
        )

    if labels:
        min_x, max_x, min_y, max_y = _layers_bounds(layers)
        text_height = max((max_x - min_x), (max_y - min_y)) * 0.015
        for text, pos, angle in labels:
            msp.add_text(
                text, dxfattribs={"height": text_height, "layer": LAYER_LABELS, "rotation": angle}
            ).set_placement(pos)

    doc.saveas(out_path)
    return out_path


def export_svg(out_path, layers, margin=20.0, title=None, labels=None, mirror_y=False, hatch_layers=None):
    """Minimal hand-rolled SVG writer -- one <g> per layer, polylines as <polyline>.
    `title` (e.g. an elevation tag) is placed as <text> below the drawing.
    `labels`: see export_dxf -- placed as in-place <text> on LAYER_LABELS.
    `mirror_y`: see export_dxf -- flips the page vertically, a layout choice.
    `hatch_layers` (2026-08-04): dict of layer_name -> HATCH_BUILDING/
    HATCH_GRASS/HATCH_TREE for layers whose polylines are closed massing/
    ground-cover footprints -- rendered as hatch-filled <polygon>s with a
    bolder outline instead of plain unfilled <polyline> strokes, so each
    reads as a solid tonal shape at a glance (standard site-plan "poche"/
    ground-cover convention) instead of just more thin outline
    indistinguishable from the site's other linework."""
    hatch_layers = hatch_layers or {}
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
    used_patterns = set(hatch_layers.values())
    if used_patterns:
        defs = "".join(_SVG_HATCH_DEFS[p] for p in used_patterns if p in _SVG_HATCH_DEFS)
        parts.append(f'<defs>{defs}</defs>')
    for layer_name, polylines in layers.items():
        color = layer_colors.get(layer_name, "#000000")
        pattern_key = hatch_layers.get(layer_name)
        hatched = pattern_key is not None
        fill = f'url(#hatch-{pattern_key})' if hatched else 'none'
        stroke_width = 0.9 if hatched else 0.5
        parts.append(f'<g id="{layer_name}" stroke="{color}" fill="{fill}" stroke-width="{stroke_width}">')
        for pts in polylines:
            pts = list(pts)
            if len(pts) >= 2:
                pts_str = " ".join(f"{p[0]:.3f},{p[1]:.3f}" for p in (flip(p) for p in pts))
                tag = 'polygon' if hatched else 'polyline'
                parts.append(f'<{tag} points="{pts_str}" />')
            elif len(pts) == 1:
                fx, fy = flip(pts[0])
                parts.append(f'<circle cx="{fx:.3f}" cy="{fy:.3f}" r="1" fill="{color}" stroke="none"/>')
        parts.append("</g>")
    if labels:
        parts.append(f'<g id="{LAYER_LABELS}" fill="{layer_colors[LAYER_LABELS]}">')
        for text, pos, angle in labels:
            fx, fy = flip(pos)
            rotate = f' transform="rotate({angle} {fx:.3f} {fy:.3f})"' if angle else ''
            parts.append(
                f'<text x="{fx:.3f}" y="{fy:.3f}" font-family="sans-serif" '
                f'font-size="10" text-anchor="middle"{rotate}>{text}</text>'
            )
        parts.append("</g>")
    if title:
        parts.append(
            f'<text x="{margin:.2f}" y="{height - 6:.2f}" '
            f'font-family="sans-serif" font-size="7" fill="#000000">{title}</text>'
        )
    parts.append("</svg>")

    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(parts))
    return out_path


def export_png(out_path, layers, title=None, labels=None, mirror_y=False, dpi=150, hatch_layers=None):
    """
    Raster PNG rendering of the same layer data as export_svg -- a quick
    visual reference, not a CAD deliverable (that's DXF/SVG). Uses
    matplotlib (already a project dependency) rather than rasterizing the
    SVG, so there's no extra rendering-library dependency to keep in sync
    with the vector writers' layer/color scheme.
    `hatch_layers`: see export_svg -- rendered as hatch-filled polygons via
    matplotlib's native `hatch=` patch support (_PNG_HATCH_CHARS maps each
    pattern key to a valid matplotlib hatch string).
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.collections import LineCollection
    from matplotlib.patches import Polygon as MplPolygon

    hatch_layers = hatch_layers or {}
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
        pattern_key = hatch_layers.get(layer_name)
        if pattern_key:
            hatch_str = _PNG_HATCH_CHARS.get(pattern_key, "///")
            for pts in polylines:
                if len(pts) >= 3:
                    ax.add_patch(MplPolygon(
                        pts, closed=True, facecolor='none', hatch=hatch_str, edgecolor=color, linewidth=1.0))
            continue
        lines = [pts for pts in polylines if len(pts) >= 2]
        if lines:
            ax.add_collection(LineCollection(lines, colors=color, linewidths=0.8))
        for pts in polylines:
            if len(pts) == 1:
                ax.plot(pts[0][0], pts[0][1], "o", color=color, markersize=1.5)

    if labels:
        for text, pos, angle in labels:
            ax.text(pos[0], pos[1], text, color=LAYER_COLORS[LAYER_LABELS],
                     fontsize=8, ha="center", va="center", rotation=angle)

    margin = max(width_ft, height_ft) * 0.03
    ax.set_xlim(min_x - margin, max_x + margin)
    ax.set_ylim(min_y - margin, max_y + margin)
    ax.set_aspect("equal")
    ax.axis("off")
    if title:
        ax.set_title(title, fontsize=5, loc="left")

    fig.savefig(out_path, dpi=dpi, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return out_path
