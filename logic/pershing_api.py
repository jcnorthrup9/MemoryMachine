"""
logic/pershing_api.py
----------------------
Wraps terracing_engine.py's TerracingEngine / StructuralFramingEngine /
TypologyAssetEngine (pure Python, no bpy) for the web frontend -- the same
math blender_cockpit.py's rebuild_all() already runs in Blender, just
returning JSON instead of building a bpy mesh.

In-memory, single-session state (SKETCH_WEIGHTS/HARDSCAPE_MASK/etc as
module globals), same pattern as the Blender cockpit -- this is a local
single-user dev tool, not a multi-tenant service, so no database is needed
for this state yet.
"""
import json
import os
import shutil
import sys
import time

from pydantic import BaseModel

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from terracing_engine import (  # noqa: E402
    TerracingEngine, StructuralFramingEngine, TypologyAssetEngine, BuildingMassEngine,
    STRUCTURAL_BAY_FT, build_cut_sheet_manifest, slab_key)
# sketch_weight_mapper.py's find_latest_sketch is pure os.listdir/getmtime --
# safe to import here even though the rest of that module needs PIL/
# svgpathtools (those imports are local to the functions that need them,
# same reasoning blender_cockpit.py already relies on).
from sketch_weight_mapper import find_latest_sketch  # noqa: E402
# amenity_deficit.py only needs the stdlib csv module -- same reasoning as
# above, safe to import directly at module level.
from amenity_deficit import load_deficit_hotspots_from_csv, find_latest_csv  # noqa: E402
# foot_traffic.py mirrors amenity_deficit.py's CSV contract exactly, for a
# separate real-data channel (foot traffic vs. amenity deficit) -- aliased
# since both modules define a same-named find_latest_csv().
from foot_traffic import (  # noqa: E402
    load_foot_traffic_hotspots_from_csv, find_latest_csv as find_latest_foot_traffic_csv)
from circulation_network import CirculationNetworkEngine  # noqa: E402
# Aliased -- this module defines its own juror_chat() function below (the
# route handler), which would otherwise shadow the imported module of the
# same name at module scope.
from logic import juror_chat as juror_chat_agent  # noqa: E402

REAL_GEOMETRY_PATH = os.path.join(BASE_DIR, "PershingMetabolizer_Prototype", "real_geometry.json")
SKETCH_CACHE_PATH = os.path.join(BASE_DIR, "outputs", "cockpit", "sketch_weights_cache.json")
# All 5 painted grids, written by THIS module's own bake() (2026-07-10
# persistence supplement) -- SKETCH_CACHE_PATH above is a different,
# externally-produced bootstrap (a Blender-side precompute script writes
# only {"weights", "hardscape_mask"}; this app never wrote to it, so
# painting in the web app was previously lost on every backend restart).
# Kept as a separate file rather than repurposing SKETCH_CACHE_PATH's
# schema, since other tools may still read that one in its original shape.
PAINT_STATE_PATH = os.path.join(BASE_DIR, "outputs", "cockpit", "web_paint_state.json")
SKETCH_DIR = os.path.join(BASE_DIR, "data", "sketches")
os.makedirs(SKETCH_DIR, exist_ok=True)

with open(REAL_GEOMETRY_PATH) as f:
    REAL_GEOMETRY = json.load(f)


def _empty_mask(nx, nz):
    return [[False] * nz for _ in range(nx)]


def _atomic_write_json(path, data):
    """Write-to-temp-then-rename so a crash/kill mid-write can't leave a
    truncated, unreadable file behind (os.replace is atomic on both Windows
    and POSIX). Shared by _save_paint_state() (runtime persist) and the
    one-time water_shade->water/shade migration below (bootstrap-time) --
    extracted so the migration doesn't need a duplicate copy of this logic,
    and so _save_paint_state() can stay defined near bake() where it's
    actually called from, rather than needing to move earlier in the file
    just to be available during module-import-time bootstrap."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp_path = path + ".tmp"
    with open(tmp_path, "w") as f:
        json.dump(data, f)
    os.replace(tmp_path, path)


_probe = TerracingEngine(REAL_GEOMETRY)  # cheap -- only used for nx/nz/voxel_ft below
NX, NZ, VOXEL_FT = _probe.nx, _probe.nz, _probe.voxel_ft
NX_BAYS = max(1, round(REAL_GEOMETRY["site"]["width_ft"] / STRUCTURAL_BAY_FT))

# Same lookup blender_cockpit.py does at import time -- None if
# data/amenity_survey/ has no CSV yet, in which case rebuild() stays on
# TerracingEngine's own DEFAULT_DEFICIT_HOTSPOTS placeholder regardless of
# what the frontend's toggle is set to.
AMENITY_CSV_PATH = find_latest_csv()

# Same lookup, separate real-data channel -- None if
# data/foot_traffic_survey/ has no CSV yet, in which case rebuild() stays on
# TerracingEngine's own DEFAULT_FOOT_TRAFFIC_HOTSPOTS placeholder regardless
# of what the frontend's toggle is set to.
FOOT_TRAFFIC_CSV_PATH = find_latest_foot_traffic_csv()

# Bootstrap all 6 grids: prefer this app's own saved state (PAINT_STATE_PATH,
# written by bake() below every time you paint+bake) if one exists -- that's
# real prior work, more recent than anything else. Otherwise fall back to
# the older precomputed-sketch-cache bootstrap (blender_cockpit.py's pattern,
# weights/hardscape only) for a first-ever run, empty grids if neither exists.
if os.path.exists(PAINT_STATE_PATH):
    with open(PAINT_STATE_PATH) as f:
        _paint_state = json.load(f)
    SKETCH_WEIGHTS = _paint_state["canyon"]
    HARDSCAPE_MASK = _paint_state["hardscape"]
    if "water" in _paint_state and "shade" in _paint_state:
        WATER_MASK = _paint_state["water"]
        SHADE_MASK = _paint_state["shade"]
    else:
        # One-time migration (2026-07-11 water_shade -> water/shade split):
        # this file predates the split and only has the old combined
        # "water_shade" key. Back it up with a TIMESTAMPED filename before
        # touching it -- a fixed ".bak" name caused a real data-loss
        # incident earlier this session (a second migration/install run
        # silently clobbered the first backup). Migrate water_shade -> water
        # only, shade starts empty: this specific file's water_shade mask
        # is provably pure water (it came from ingest_legacy_diagram.py's
        # blue-pixel-only segmentation, and the SHADE/GREEN_SPACE color-
        # collision bug in static/main.js's _getLayerColor meant no diagram
        # exported before that fix could ever have produced a real shade
        # signal) -- duplicating into both would fabricate tree placement
        # the user never actually specified. See
        # archive/memoryMachine/MILESTONE_07112026_PlanningSession.md.
        _backup_path = f"{PAINT_STATE_PATH}.{int(time.time())}.bak"
        shutil.copy2(PAINT_STATE_PATH, _backup_path)
        WATER_MASK = _paint_state["water_shade"]
        SHADE_MASK = _empty_mask(NX, NZ)
        print(f"[pershing_api] migrated {PAINT_STATE_PATH} from water_shade to water/shade "
              f"(shade starts empty) -- pre-migration backup at {_backup_path}")
        _atomic_write_json(PAINT_STATE_PATH, {
            "canyon": SKETCH_WEIGHTS, "hardscape": HARDSCAPE_MASK,
            "water": WATER_MASK, "shade": SHADE_MASK,
            "greenscape": _paint_state["greenscape"], "amenity_resting": _paint_state["amenity_resting"],
        })
    GREENSCAPE_MASK = _paint_state["greenscape"]
    AMENITY_RESTING_MASK = _paint_state["amenity_resting"]
elif os.path.exists(SKETCH_CACHE_PATH):
    with open(SKETCH_CACHE_PATH) as f:
        _cache = json.load(f)
    SKETCH_WEIGHTS = _cache["weights"]
    HARDSCAPE_MASK = _cache.get("hardscape_mask") or _empty_mask(NX, NZ)
    WATER_MASK = _empty_mask(NX, NZ)
    SHADE_MASK = _empty_mask(NX, NZ)
    GREENSCAPE_MASK = _empty_mask(NX, NZ)
    AMENITY_RESTING_MASK = _empty_mask(NX, NZ)
else:
    SKETCH_WEIGHTS = _empty_mask(NX, NZ)
    HARDSCAPE_MASK = _empty_mask(NX, NZ)
    WATER_MASK = _empty_mask(NX, NZ)
    SHADE_MASK = _empty_mask(NX, NZ)
    GREENSCAPE_MASK = _empty_mask(NX, NZ)
    AMENITY_RESTING_MASK = _empty_mask(NX, NZ)

# The sketch image the paint canvas displays as its background -- starts
# as whatever's already in data/sketches/ (same lookup blender_cockpit.py
# uses), but can be replaced at runtime via save_uploaded_sketch() once a
# designer uploads a new photo through the web UI.
_current_sketch_path = find_latest_sketch(SKETCH_DIR)


def get_sketch_info():
    """Filename + static-served URL for the currently active sketch image,
    or both None if data/sketches/ is empty and nothing's been uploaded
    yet -- the frontend falls back to a blank canvas in that case."""
    if _current_sketch_path is None:
        return {"filename": None, "url": None}
    filename = os.path.basename(_current_sketch_path)
    return {"filename": filename, "url": f"/pershing-sketch/{filename}"}


def save_uploaded_sketch(filename, content: bytes):
    """Save an uploaded sketch photo into data/sketches/ and make it the
    active one. basename() strips any directory component from the
    client-supplied filename -- never trust that value as a path."""
    global _current_sketch_path
    safe_name = os.path.basename(filename)
    if not safe_name:
        raise ValueError("empty filename")
    dest = os.path.join(SKETCH_DIR, safe_name)
    with open(dest, "wb") as f:
        f.write(content)
    _current_sketch_path = dest
    return get_sketch_info()


class BakeGrids(BaseModel):
    """
    Painted mask grids from the browser's paint canvas, already sampled
    client-side (Canvas ImageData -> per-cell averaged alpha, same
    real-feet cell indexing TerracingEngine uses) -- mirrors
    blender_cockpit.py's bake_paint_canvas, just with the sampling done in
    JS against a 2D canvas instead of Python against a Blender Image.
    canyon is the one continuous weight grid (painted alpha IS the
    weight); the other five are boolean zone masks, already thresholded
    client-side. water/shade split 2026-07-11 (was one combined
    water_shade field) -- see terracing_engine.py's Voxel docstring.
    """
    canyon: list[list[float]]
    hardscape: list[list[bool]]
    water: list[list[bool]]
    shade: list[list[bool]]
    greenscape: list[list[bool]]
    amenity_resting: list[list[bool]]


def _save_paint_state():
    """Persist all 6 live grids to PAINT_STATE_PATH (2026-07-10 persistence
    supplement, water/shade split 2026-07-11) so a backend restart doesn't
    lose painted work -- previously bake() only updated the in-memory
    globals, never written anywhere. See _atomic_write_json for the actual
    write mechanics (shared with the one-time bootstrap migration above)."""
    _atomic_write_json(PAINT_STATE_PATH, {
        "canyon": SKETCH_WEIGHTS, "hardscape": HARDSCAPE_MASK, "water": WATER_MASK, "shade": SHADE_MASK,
        "greenscape": GREENSCAPE_MASK, "amenity_resting": AMENITY_RESTING_MASK,
    })


def bake(grids: BakeGrids):
    """Overwrite the six live grids from a completed paint session and
    persist them (see _save_paint_state). Does NOT trigger a rebuild itself
    -- the frontend calls /rebuild right after, reusing its existing
    rebuild path rather than duplicating it here with a second copy of the
    current slider params."""
    global SKETCH_WEIGHTS, HARDSCAPE_MASK, WATER_MASK, SHADE_MASK, GREENSCAPE_MASK, AMENITY_RESTING_MASK
    SKETCH_WEIGHTS = grids.canyon
    HARDSCAPE_MASK = grids.hardscape
    WATER_MASK = grids.water
    SHADE_MASK = grids.shade
    GREENSCAPE_MASK = grids.greenscape
    AMENITY_RESTING_MASK = grids.amenity_resting
    _save_paint_state()
    return {
        "status": "ok",
        "counts": {
            "canyon": sum(1 for row in SKETCH_WEIGHTS for v in row if v > 0.01),
            "hardscape": sum(1 for row in HARDSCAPE_MASK for v in row if v),
            "water": sum(1 for row in WATER_MASK for v in row if v),
            "shade": sum(1 for row in SHADE_MASK for v in row if v),
            "greenscape": sum(1 for row in GREENSCAPE_MASK for v in row if v),
            "amenity_resting": sum(1 for row in AMENITY_RESTING_MASK for v in row if v),
        },
    }


class BuildingSpec(BaseModel):
    """One user-parameterized building mass -- see BuildingMassEngine's
    docstring for why this is parameterized rather than read from
    data/building_heights.json (wrong coordinate frame, off-site data)."""
    x_ft: float
    y_ft: float
    width_ft: float = 40.0
    depth_ft: float = 30.0
    height_ft: float = 20.0
    setback_ft: float = 0.0


class RebuildParams(BaseModel):
    sketch_alpha: float = 0.75
    canyon_width: int = 3
    canyon_depth: int = 1
    material_mode: str = "STEEL"
    shoring_density: float = 1.0
    use_real_amenity_data: bool = AMENITY_CSV_PATH is not None
    use_real_foot_traffic_data: bool = FOOT_TRAFFIC_CSV_PATH is not None
    buildings: list[BuildingSpec] = []


def get_config():
    """Static bounds the frontend needs to size its sliders correctly --
    mirrors blender_cockpit.py's NX_BAYS / register() slider min/max."""
    return {
        "site_width_ft": REAL_GEOMETRY["site"]["width_ft"],
        "site_length_ft": REAL_GEOMETRY["site"]["length_ft"],
        "voxel_ft": VOXEL_FT,
        "nx": NX,
        "nz": NZ,
        "nx_bays": NX_BAYS,
        "column_height_ft": REAL_GEOMETRY.get("column_height_ft", 30.0),
        # Mirrors the Blender cockpit panel's "csv: <name>" / "no amenity
        # CSV found" label, so the React toggle can show the same status
        # instead of just silently no-op'ing when no CSV exists yet.
        "amenity_csv": os.path.basename(AMENITY_CSV_PATH) if AMENITY_CSV_PATH else None,
        "foot_traffic_csv": os.path.basename(FOOT_TRAFFIC_CSV_PATH) if FOOT_TRAFFIC_CSV_PATH else None,
    }


def _serialize_specs(specs):
    """Shared StructuralElement -> JSON dict shape, used by both rebuild()'s
    "structural" key and grow_network()'s "network" key -- keeping this in
    one place means the two response payloads can never silently drift
    apart in which fields they expose."""
    return [
        {
            "kind": s.kind, "x_ft": s.x_ft, "y_ft": s.y_ft, "z_top_ft": s.z_top_ft,
            "height_ft": s.height_ft, "scale": s.scale, "rotation_deg": s.rotation_deg,
            "x2_ft": s.x2_ft, "y2_ft": s.y2_ft, "z2_ft": s.z2_ft, "radius_ft": s.radius_ft,
            "scale_y": s.scale_y,
            "column_id": s.column_id, "column_id2": s.column_id2, "slab_id": s.slab_id,
        }
        for s in specs
    ]


def _run_pipeline(params: RebuildParams):
    """
    Same math blender_cockpit.rebuild_all() runs, minus the bpy mesh build
    -- builds the TerracingEngine/StructuralFramingEngine/TypologyAssetEngine/
    BuildingMassEngine stack from RebuildParams. Shared by rebuild() and
    grow_network(), which both need the identical terrain-shaping setup
    (the grown network must reflect whatever canyon/amenity state is
    currently on screen, not a separately-derived copy of it) -- extracted
    here specifically so the two can't silently drift out of sync.

    hardscape_regions is applied unconditionally -- there's no separate
    "protect hardscape" toggle anymore (removed 2026-07-06): with painting
    as the only way to mark a hardscape zone, painting one already means
    "protect this," so a second switch to also enable that protection was
    redundant, dead-looking UI.

    Returns (engine, voxels, typology_specs, all_specs, meta) -- voxels is
    the flat, already-classified list engine.run() returns (every voxel,
    not just excavated ones: an unexcavated voxel still gets a solid block
    built from floor_z up to grade, so the un-cut majority of the site
    reads as a real base slab the canyon is cut INTO, not a disconnected
    floating island of excavated cells -- an earlier version filtered
    these out as a payload-size optimization, which silently dropped that
    entire base slab from the web viewport). typology_specs is
    TypologyAssetEngine's own output alone (grow_network() needs these
    positions as circulation-network attractors, separate from the full
    all_specs list rebuild() renders).
    """
    hardscape_regions = [{"mask": HARDSCAPE_MASK}]
    transit_falloff_ft = params.canyon_width * STRUCTURAL_BAY_FT
    max_canyon_depth_ft = min(params.canyon_depth * 9.0, REAL_GEOMETRY.get("column_height_ft", 30.0))

    # Mirrors blender_cockpit.py's rebuild_all(): None -> TerracingEngine
    # falls back to its own DEFAULT_DEFICIT_HOTSPOTS placeholder. Only
    # loaded when both the toggle is on AND a CSV actually exists, same
    # as the Blender panel's disabled-checkbox behavior.
    deficit_hotspots = None
    if params.use_real_amenity_data and AMENITY_CSV_PATH:
        deficit_hotspots = load_deficit_hotspots_from_csv(
            AMENITY_CSV_PATH, REAL_GEOMETRY["site"]["width_ft"], REAL_GEOMETRY["site"]["length_ft"])

    # Same conditional-load pattern, separate real-data channel.
    foot_traffic_hotspots = None
    if params.use_real_foot_traffic_data and FOOT_TRAFFIC_CSV_PATH:
        foot_traffic_hotspots = load_foot_traffic_hotspots_from_csv(
            FOOT_TRAFFIC_CSV_PATH, REAL_GEOMETRY["site"]["width_ft"], REAL_GEOMETRY["site"]["length_ft"])

    engine = TerracingEngine(
        REAL_GEOMETRY, sketch_weights=SKETCH_WEIGHTS, sketch_alpha=params.sketch_alpha,
        hardscape_regions=hardscape_regions,
        transit_falloff_ft=transit_falloff_ft, max_canyon_depth_ft=max_canyon_depth_ft,
        water_regions=[{"mask": WATER_MASK}],
        shade_regions=[{"mask": SHADE_MASK}],
        greenscape_regions=[{"mask": GREENSCAPE_MASK}],
        amenity_resting_regions=[{"mask": AMENITY_RESTING_MASK}],
        deficit_hotspots=deficit_hotspots,
        foot_traffic_hotspots=foot_traffic_hotspots,
    )
    voxels = engine.run(phase=3)

    structural = StructuralFramingEngine(
        REAL_GEOMETRY, engine, material_mode=params.material_mode, shoring_density=params.shoring_density)
    result = structural.run()

    typology = TypologyAssetEngine(REAL_GEOMETRY, engine)
    typology_specs = typology.run()
    buildings = BuildingMassEngine([b.model_dump() for b in params.buildings]).run()
    all_specs = result["harvested_blocks"] + result["structural"] + typology_specs + buildings

    meta = {
        "max_canyon_depth_ft": max_canyon_depth_ft,
        "used_real_amenity_data": deficit_hotspots is not None,
        "used_real_foot_traffic_data": foot_traffic_hotspots is not None,
        "slab_harvest_tons": result["slab_harvest_tons"],
        # Real-slab-driven remaining/removed cells (2026-07-09 real-slab-
        # driven harvest supplement) -- depends on this rebuild's live
        # excavation params, unlike real_slabs/real_columns below which are
        # fixed geometry, so this is recomputed every call, not passed
        # through from REAL_GEOMETRY as-is.
        "real_slab_fragments": structural.real_slab_fragments(),
    }
    return engine, voxels, typology_specs, all_specs, meta


def rebuild(params: RebuildParams):
    """Returns JSON voxels + structural/typology specs for the frontend to
    render however it likes (Three.js instancing, etc)."""
    engine, voxels, typology_specs, all_specs, meta = _run_pipeline(params)

    kind_counts = {}
    for s in all_specs:
        kind_counts[s.kind] = kind_counts.get(s.kind, 0) + 1

    return {
        "voxels": [
            {
                "gx": v.gx, "gy": v.gy, "z_ft": v.z_ft, "level": v.level, "typology": v.typology,
                "is_greenscape": v.is_greenscape,
            }
            for v in voxels
        ],
        "structural": _serialize_specs(all_specs),
        "kind_counts": kind_counts,
        "used_real_amenity_data": meta["used_real_amenity_data"],
        "used_real_foot_traffic_data": meta["used_real_foot_traffic_data"],
        "slab_harvest_tons": meta["slab_harvest_tons"],
        "max_canyon_depth_ft": meta["max_canyon_depth_ft"],
        "voxel_ft": VOXEL_FT,
        # Real slab/column solids extracted directly from live Rhino (2026-07-09
        # real-slab-graph supplement, see plan doc) -- fixed geometry, doesn't
        # depend on excavation params, so just passed through from REAL_GEOMETRY
        # as-is rather than recomputed per rebuild.
        # `key` added per entry (2026-07-09) so the frontend can look up
        # real_slab_fragments[slab.key] directly -- reconstructing
        # slab_key()'s f"{parent}_{z_top_ft}" string in JS would silently
        # mismatch Python's float formatting (JSON -20.0 parses to the JS
        # number -20, and `${-20}` stringifies to "-20" not "-20.0").
        "real_slabs": [{**s, "key": slab_key(s)} for s in REAL_GEOMETRY.get("real_slabs", [])],
        "real_columns": REAL_GEOMETRY.get("real_columns", []),
        # Per-slab remaining (not-yet-excavated) fragment cells, keyed by the
        # same slab_key() string as each real_slabs entry's `key` above --
        # only remaining/removed_count sent (not the full "slab" sub-dict
        # real_slab_fragments() also returns, since the frontend already has
        # that from real_slabs above).
        "real_slab_fragments": {
            key: {"remaining": [[wx, wy] for _, _, wx, wy in entry["remaining"]],
                  "removed_count": entry["removed_count"]}
            for key, entry in meta["real_slab_fragments"].items()
        },
        # Material-categorized cut sheet (2026-07-09 cut-sheet supplement) --
        # flattens all_specs (this rebuild's actual procedural elements) plus
        # the real slabs/columns into count/area/volume/linear-length per
        # kind, grouped by material family. Recomputed every rebuild since
        # all_specs depends on the live excavation/shoring params.
        "cut_sheet": build_cut_sheet_manifest(
            all_specs, REAL_GEOMETRY.get("real_slabs", []), REAL_GEOMETRY.get("real_columns", [])),
    }


class NetworkParams(BaseModel):
    motivator_weights: dict[str, float] = {
        "shade": 1.0, "water": 1.0, "rest": 1.0, "foot_traffic": 1.0, "deficit": 1.0,
    }
    step_ft: float = 15.0
    max_iterations: int = 300


class GrowNetworkRequest(BaseModel):
    rebuild: RebuildParams = RebuildParams()
    network: NetworkParams = NetworkParams()


def grow_network(payload: GrowNetworkRequest):
    """
    Grows a Space Colonization pedestrian circulation network from the
    real Metro entrance on top of whatever canyon/amenity state
    payload.rebuild describes -- runs the exact same _run_pipeline() setup
    rebuild() uses so the network reflects the current terrain, not a
    separately-derived snapshot.

    Synchronous, not an async job like the headless-Blender build tier --
    that pattern exists specifically because a `--background` Blender
    subprocess launch has real, unavoidable multi-second startup cost;
    this is pure in-process Python+numpy over this site's 40x67 voxel
    grid, designed to finish well under a second, so it mirrors rebuild()'s
    own existing synchronous pattern instead of introducing job-polling
    machinery for an operation with no external process and no meaningful
    blocking risk.
    """
    engine, _voxels, typology_specs, _all_specs, _meta = _run_pipeline(payload.rebuild)

    net = CirculationNetworkEngine(
        REAL_GEOMETRY, engine, typology_specs,
        motivator_weights=payload.network.motivator_weights,
        step_ft=payload.network.step_ft,
        max_iterations=payload.network.max_iterations,
    )
    specs = net.run()

    kind_counts = {}
    for s in specs:
        kind_counts[s.kind] = kind_counts.get(s.kind, 0) + 1

    return {
        "network": _serialize_specs(specs),
        "kind_counts": kind_counts,
        "node_count": len(net.nodes),
        "attractor_count": len(net.attractors),
        "attractors_unconsumed": sum(1 for a in net.attractors if not a.consumed),
    }


class JurorChatRequest(BaseModel):
    message: str
    # Whatever live design state the frontend already holds client-side
    # (current RebuildParams/NetworkParams, light summaries of the last
    # rebuild()/grow_network() results) -- loosely typed since this is
    # purely grounding context for the prompt, not something this endpoint
    # validates or acts on.
    context: dict = {}


def juror_chat(payload: JurorChatRequest):
    """Grounded Q&A for the live juror chat -- merges get_config()'s real
    site facts with whatever live state the frontend supplied, then
    delegates to logic/juror_chat.py's JurorChatAgent. See that module's
    docstring for the reply/action contract (action is always null in this
    pass -- see PERSONA_SYSTEM_TEXT)."""
    site_facts = get_config()
    context = {**site_facts, **payload.context}
    return juror_chat_agent.chat(payload.message, context)
