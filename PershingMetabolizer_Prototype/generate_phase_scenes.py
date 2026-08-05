"""
Port of index.html's attractor/voxel/color logic (buildBaseVoxels, scoreForPhase,
zForVoxel, relaxDepths, excavationColor) to Python, so the same phase geometry that
drives the Three.js prototype can be handed to a headless Blender render pipeline
with no browser in the loop.

Coordinate convention matches index.html's toWorld(): site-local (wx, wy) with a
SW-corner origin is recentered to (wx - SITE_WIDTH_FT/2, wy - SITE_LENGTH_FT/2).
Three.js is Y-up (height); Blender is Z-up, so every point here is emitted as
Blender-ready (x, y, z) = (wx - W/2, wy - L/2, height) -- i.e. Three's "y" (height)
becomes Blender's z, and Three's "z" (plan length-axis) becomes Blender's y.
Real-geometry meshes (columns/tunnel/entrance/ramps) already store raw vertices as
(x, height, z) triples in this same site-local frame (verified against index.html's
buildRealGeometry + placeRealMesh, which apply the identical recentring offset with
no axis flips), so the same remap is applied to them.

Run: python generate_phase_scenes.py
Writes: blender_scene_data.json (next to this script)
"""
import json
import math
import os

HERE = os.path.dirname(os.path.abspath(__file__))


def load(path):
    with open(os.path.join(HERE, path), encoding="utf-8") as f:
        return json.load(f)


REAL = load("real_geometry.json")
CURRENT_STATE = load("current_state.json")
BLDG_DATA = load(os.path.join("..", "data", "building_heights.json"))

# ── Site dimensions (real, from OBJ) ────────────────────────────────────────
SITE_WIDTH_FT = REAL["site"]["width_ft"]
SITE_LENGTH_FT = REAL["site"]["length_ft"]

# ── Voxel grid ───────────────────────────────────────────────────────────────
VOXEL_FT = 9
NX = math.ceil(SITE_WIDTH_FT / VOXEL_FT)
NZ = math.ceil(SITE_LENGTH_FT / VOXEL_FT)

# ── Excavation constants (verbatim from index.html) ─────────────────────────
GARAGE_DEPTH_FT = 30
TRANSIT_FALLOFF_FT = 220
THRESHOLD = 0.35
TILE_HEIGHT_FT = 2
ENTRANCE_BASE_DEPTH_FT = REAL["secondary_entrance_anchor"]["bottom_depth_ft"]
STEP_FT = 9

METRO_ENTRANCE = (
    REAL["secondary_entrance_anchor"]["x"],
    REAL["secondary_entrance_anchor"]["z"],
)

DEFICIT_HOTSPOTS = [
    {"x": SITE_WIDTH_FT * 0.04, "y": SITE_LENGTH_FT * 0.65, "strength": 1.0, "radius": 67.5},
    {"x": SITE_WIDTH_FT * 0.04, "y": SITE_LENGTH_FT * 0.30, "strength": 0.6, "radius": 54.0},
]

RAMP_CLEARANCE_FT = 20


def clamp01(v):
    return max(0.0, min(1.0, v))


def lerp(a, b, t):
    return a + (b - a) * t


def lerp_rgb(c1, c2, t):
    return tuple(lerp(c1[i], c2[i], t) for i in range(3))


def hex_to_rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4))


# ── Ramp cluster bounding boxes (for transit-cut hard avoidance) ────────────
def mesh_cluster_bbox(mesh_list):
    min_x = min_z = math.inf
    max_x = max_z = -math.inf
    for level in mesh_list:
        verts = level["vertices"]
        for i in range(0, len(verts), 3):
            x, z = verts[i], verts[i + 2]
            min_x, max_x = min(min_x, x), max(max_x, x)
            min_z, max_z = min(min_z, z), max(max_z, z)
    return {"minX": min_x, "maxX": max_x, "minZ": min_z, "maxZ": max_z}


RAMP_BBOXES = [mesh_cluster_bbox(REAL["ramp_meshes"][k]) for k in ("cluster_a", "cluster_b")]


def dist_to_bbox(x, y, box):
    dx = max(box["minX"] - x, 0, x - box["maxX"])
    dz = max(box["minZ"] - y, 0, y - box["maxZ"])
    return math.hypot(dx, dz)


def nearest_ramp_dist(x, y):
    return min(dist_to_bbox(x, y, b) for b in RAMP_BBOXES)


# ── Base voxel grid ──────────────────────────────────────────────────────────
def build_base_voxels():
    voxels = [None] * (NX * NZ)
    for gx in range(NX):
        for gy in range(NZ):
            wx = (gx + 0.5) * VOXEL_FT
            wy = (gy + 0.5) * VOXEL_FT

            entrance_dist = math.hypot(wx - METRO_ENTRANCE[0], wy - METRO_ENTRANCE[1])
            transit_influence = math.exp(-entrance_dist / TRANSIT_FALLOFF_FT)

            deficit_influence = 0.0
            for h in DEFICIT_HOTSPOTS:
                d = math.hypot(wx - h["x"], wy - h["y"])
                deficit_influence += h["strength"] * math.exp(-d / h["radius"])
            deficit_influence = clamp01(deficit_influence)

            voxels[gx * NZ + gy] = {
                "gx": gx, "gy": gy, "wx": wx, "wy": wy,
                "transitInfluence": transit_influence,
                "deficitInfluence": deficit_influence,
                "rampDist": nearest_ramp_dist(wx, wy),
            }
    return voxels


def score_for_phase(v, phase):
    if phase == 1:
        return 0.0
    if phase == 2:
        return v["deficitInfluence"]
    return clamp01(v["transitInfluence"] + v["deficitInfluence"])


def z_for_voxel(v, phase):
    if phase != 3 or v["transitInfluence"] <= THRESHOLD:
        return 0.0
    if v["rampDist"] < RAMP_CLEARANCE_FT:
        return 0.0
    raw_depth = min(v["transitInfluence"] * ENTRANCE_BASE_DEPTH_FT, ENTRANCE_BASE_DEPTH_FT)
    return -round(raw_depth / STEP_FT) * STEP_FT


def relax_depths(z_arr, voxels):
    max_iter = math.ceil(ENTRANCE_BASE_DEPTH_FT / STEP_FT) + 2
    cur = list(z_arr)
    for _ in range(max_iter):
        nxt = list(cur)
        changed = False
        for gx in range(NX):
            for gy in range(NZ):
                idx = gx * NZ + gy
                if voxels[idx]["rampDist"] < RAMP_CLEARANCE_FT:
                    continue
                max_neighbor = -math.inf
                for nx_, ny_ in ((gx - 1, gy), (gx + 1, gy), (gx, gy - 1), (gx, gy + 1)):
                    if nx_ < 0 or nx_ >= NX or ny_ < 0 or ny_ >= NZ:
                        continue
                    nz_ = cur[nx_ * NZ + ny_]
                    if nz_ > max_neighbor:
                        max_neighbor = nz_
                if max_neighbor == -math.inf:
                    continue
                floor = max_neighbor - STEP_FT
                if cur[idx] < floor:
                    nxt[idx] = floor
                    changed = True
        cur = nxt
        if not changed:
            break
    return cur


AMBER_A = hex_to_rgb("#FFF4CA")
AMBER_B = hex_to_rgb("#FF6B00")
VIOLET_A = hex_to_rgb("#4D00FF")
VIOLET_B = hex_to_rgb("#0A002F")
FLAT_COLOR = hex_to_rgb("#c2bdb4")


def excavation_color(v, score):
    if score <= THRESHOLD:
        return FLAT_COLOR
    amber = lerp_rgb(AMBER_A, AMBER_B, clamp01(v["deficitInfluence"]))
    violet = lerp_rgb(VIOLET_A, VIOLET_B, clamp01(v["transitInfluence"]))
    total_influence = v["transitInfluence"] + v["deficitInfluence"]
    violet_weight = clamp01(v["transitInfluence"] / total_influence) if total_influence > 0 else 0.0
    blended = lerp_rgb(amber, violet, violet_weight)
    return lerp_rgb(blended, FLAT_COLOR, 1 - score)


def to_blender(wx, wy, height):
    """Site-local (wx, wy, height) -> Blender world (x, y, z-up), SW-origin -> centered."""
    return [wx - SITE_WIDTH_FT / 2, wy - SITE_LENGTH_FT / 2, height]


def voxels_for_phase(base_voxels, phase):
    z_arr = [0.0] * len(base_voxels)
    if phase == 3:
        raw = [z_for_voxel(v, phase) for v in base_voxels]
        z_arr = relax_depths(raw, base_voxels)

    out = []
    for idx, v in enumerate(base_voxels):
        score = score_for_phase(v, phase)
        z = z_arr[idx]
        slab_h = STEP_FT if z < 0 else TILE_HEIGHT_FT
        center_y = z - slab_h / 2
        out.append({
            "pos": to_blender(v["wx"], v["wy"], center_y),
            "slab_h": slab_h,
            "color": list(excavation_color(v, score)),
        })
    return out


# ── Real static geometry (shared across all phases) ─────────────────────────
def remap_mesh_verts(mesh):
    verts = mesh["vertices"]
    out = []
    for i in range(0, len(verts), 3):
        out.extend(to_blender(verts[i], verts[i + 2], verts[i + 1]))
    return {"vertices": out, "faces": mesh["faces"]}


def build_static():
    columns_local = remap_mesh_verts(REAL["column_prototype_mesh"])
    column_positions = [
        to_blender(c["x"], c["z"], 0) for c in REAL["column_positions"]
    ]

    ramps = {
        key: [remap_mesh_verts(level) for level in REAL["ramp_meshes"][key]]
        for key in ("cluster_a", "cluster_b")
    }

    slab_w, slab_l = 328, 596
    level_depth_ft = GARAGE_DEPTH_FT / 3
    level_colors = [[0x90 / 255, 0x90 / 255, 0xb8 / 255],
                     [0x70 / 255, 0x70 / 255, 0xa0 / 255],
                     [0x50 / 255, 0x50 / 255, 0x88 / 255]]
    level_opacity = [0.18, 0.22, 0.28]
    floor_plates = [
        {"z": -level_depth_ft * lvl, "w": slab_w, "l": slab_l,
         "color": level_colors[i], "opacity": level_opacity[i]}
        for i, lvl in enumerate((1, 2, 3))
    ]

    # Street tunnel connector (Phase 3 only) -- real dimensions traced from the
    # entrance mesh's own bbox + anchor depths, per index.html's entranceBBoxSiteLocal().
    verts = REAL["secondary_entrance_mesh"]["vertices"]
    min_x = min(verts[i] for i in range(0, len(verts), 3))
    min_z = min(verts[i + 2] for i in range(0, len(verts), 3))
    max_z = max(verts[i + 2] for i in range(0, len(verts), 3))
    anchor = REAL["secondary_entrance_anchor"]
    tunnel_x0, tunnel_x1 = SITE_WIDTH_FT, min_x
    tunnel_z0, tunnel_z1 = min_z, max_z
    tunnel_top_y, tunnel_bottom_y = -anchor["top_depth_ft"], -anchor["bottom_depth_ft"]
    tunnel_connector = {
        "center": to_blender(
            (tunnel_x0 + tunnel_x1) / 2, (tunnel_z0 + tunnel_z1) / 2,
            (tunnel_top_y + tunnel_bottom_y) / 2,
        ),
        "w": abs(tunnel_x1 - tunnel_x0),
        "l": abs(tunnel_z1 - tunnel_z0),
        "h": abs(tunnel_top_y - tunnel_bottom_y),
    }

    return {
        "column_mesh": columns_local,
        "column_positions": column_positions,
        "column_color": [0x9a / 255, 0x9a / 255, 0xa8 / 255],
        "tunnel_mesh": remap_mesh_verts(REAL["tunnel_mesh"]),
        "tunnel_color": [0x00 / 255, 0x33 / 255, 0x18 / 255],
        "tunnel_emissive": [0.0, 1.0, 0.6],
        "entrance_mesh": remap_mesh_verts(REAL["secondary_entrance_mesh"]),
        "entrance_color": [0x33 / 255, 0x1f / 255, 0.0],
        "entrance_emissive": [1.0, 0.541, 0.169],
        "ramps": ramps,
        "ramp_color": [0x4a / 255, 0x4a / 255, 0x55 / 255],
        "floor_plates": floor_plates,
        "tunnel_connector": tunnel_connector,
    }


# ── "Current" as-built geometry (context/yellow/items meshes + tree billboards) ──
def build_current():
    def remap_nested(mesh):
        verts = mesh["verts"]
        flat = []
        for v in verts:
            flat.extend(to_blender(v[0], v[2], v[1]))
        return {"vertices": flat, "faces": [i for tri in mesh["faces"] for i in tri]}

    context_mesh = remap_nested(CURRENT_STATE["context_mesh"]) if CURRENT_STATE["context_mesh"]["verts"] else None
    yellow_mesh = remap_nested(CURRENT_STATE["yellow_mesh"]) if CURRENT_STATE["yellow_mesh"]["verts"] else None

    items = {}
    for name, submeshes in CURRENT_STATE.get("items", {}).items():
        items[name] = [
            {**remap_nested(sm), "color": sm["color"]}
            for sm in submeshes if sm["verts"]
        ]

    trees = []
    for t in CURRENT_STATE.get("trees", []):
        h = t["topHeight"] - t["baseHeight"]
        center_y = t["baseHeight"] + h / 2
        trees.append({
            "center": to_blender(t["x"], t["z"], center_y),
            "width": t["width"],
            "height": h,
            "texture": t["texture"],
        })

    return {
        "context_mesh": context_mesh,
        "yellow_mesh": yellow_mesh,
        "yellow_color": [0xe8 / 255, 0xc2 / 255, 0.0],
        "items": items,
        "trees": trees,
    }


def main():
    base_voxels = build_base_voxels()
    data = {
        "site": {"width_ft": SITE_WIDTH_FT, "length_ft": SITE_LENGTH_FT},
        "voxel_ft": VOXEL_FT,
        "garage_depth_ft": GARAGE_DEPTH_FT,
        "static": build_static(),
        "phases": {
            str(p): {"voxels": voxels_for_phase(base_voxels, p)} for p in (1, 2, 3)
        },
        "current": build_current(),
    }
    out_path = os.path.join(HERE, "blender_scene_data.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(data, f)
    print(f"Wrote {out_path}")
    print(f"Grid {NX}x{NZ} = {NX*NZ} voxels, {len(REAL['column_positions'])} columns")


if __name__ == "__main__":
    main()
