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
import sys

from pydantic import BaseModel

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from terracing_engine import (  # noqa: E402
    TerracingEngine, StructuralFramingEngine, TypologyAssetEngine, BuildingMassEngine,
    STRUCTURAL_BAY_FT)
# sketch_weight_mapper.py's find_latest_sketch is pure os.listdir/getmtime --
# safe to import here even though the rest of that module needs PIL/
# svgpathtools (those imports are local to the functions that need them,
# same reasoning blender_cockpit.py already relies on).
from sketch_weight_mapper import find_latest_sketch  # noqa: E402
# amenity_deficit.py only needs the stdlib csv module -- same reasoning as
# above, safe to import directly at module level.
from amenity_deficit import load_deficit_hotspots_from_csv, find_latest_csv  # noqa: E402

REAL_GEOMETRY_PATH = os.path.join(BASE_DIR, "PershingMetabolizer_Prototype", "real_geometry.json")
SKETCH_CACHE_PATH = os.path.join(BASE_DIR, "outputs", "cockpit", "sketch_weights_cache.json")
SKETCH_DIR = os.path.join(BASE_DIR, "data", "sketches")
os.makedirs(SKETCH_DIR, exist_ok=True)

with open(REAL_GEOMETRY_PATH) as f:
    REAL_GEOMETRY = json.load(f)


def _empty_mask(nx, nz):
    return [[False] * nz for _ in range(nx)]


_probe = TerracingEngine(REAL_GEOMETRY)  # cheap -- only used for nx/nz/voxel_ft below
NX, NZ, VOXEL_FT = _probe.nx, _probe.nz, _probe.voxel_ft
NX_BAYS = max(1, round(REAL_GEOMETRY["site"]["width_ft"] / STRUCTURAL_BAY_FT))

# Same lookup blender_cockpit.py does at import time -- None if
# data/amenity_survey/ has no CSV yet, in which case rebuild() stays on
# TerracingEngine's own DEFAULT_DEFICIT_HOTSPOTS placeholder regardless of
# what the frontend's toggle is set to.
AMENITY_CSV_PATH = find_latest_csv()

# Same bootstrap pattern as blender_cockpit.py: start from the precomputed
# sketch cache if one exists, empty grids otherwise.
if os.path.exists(SKETCH_CACHE_PATH):
    with open(SKETCH_CACHE_PATH) as f:
        _cache = json.load(f)
    SKETCH_WEIGHTS = _cache["weights"]
    HARDSCAPE_MASK = _cache.get("hardscape_mask") or _empty_mask(NX, NZ)
else:
    SKETCH_WEIGHTS = _empty_mask(NX, NZ)
    HARDSCAPE_MASK = _empty_mask(NX, NZ)

WATER_SHADE_MASK = _empty_mask(NX, NZ)
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
    weight); the other four are boolean zone masks, already thresholded
    client-side.
    """
    canyon: list[list[float]]
    hardscape: list[list[bool]]
    water_shade: list[list[bool]]
    greenscape: list[list[bool]]
    amenity_resting: list[list[bool]]


def bake(grids: BakeGrids):
    """Overwrite the five live grids from a completed paint session. Does
    NOT trigger a rebuild itself -- the frontend calls /rebuild right
    after, reusing its existing rebuild path rather than duplicating it
    here with a second copy of the current slider params."""
    global SKETCH_WEIGHTS, HARDSCAPE_MASK, WATER_SHADE_MASK, GREENSCAPE_MASK, AMENITY_RESTING_MASK
    SKETCH_WEIGHTS = grids.canyon
    HARDSCAPE_MASK = grids.hardscape
    WATER_SHADE_MASK = grids.water_shade
    GREENSCAPE_MASK = grids.greenscape
    AMENITY_RESTING_MASK = grids.amenity_resting
    return {
        "status": "ok",
        "counts": {
            "canyon": sum(1 for row in SKETCH_WEIGHTS for v in row if v > 0.01),
            "hardscape": sum(1 for row in HARDSCAPE_MASK for v in row if v),
            "water_shade": sum(1 for row in WATER_SHADE_MASK for v in row if v),
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
    }


def rebuild(params: RebuildParams):
    """
    Same math blender_cockpit.rebuild_all() runs, minus the bpy mesh build
    -- returns JSON voxels + structural/typology specs for the frontend to
    render however it likes (Three.js instancing, etc). Returns every
    voxel (not just excavated ones) -- see build_terrace_mesh's
    floor_z-referenced height, which is always positive: the unexcavated
    majority of the site is a real base slab the canyon cuts into, not
    empty space, so it can't be filtered out.

    hardscape_regions is applied unconditionally now -- there's no
    separate "protect hardscape" toggle anymore (removed 2026-07-06):
    with painting as the only way to mark a hardscape zone, painting one
    already means "protect this," so a second switch to also enable that
    protection was redundant, dead-looking UI.
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

    engine = TerracingEngine(
        REAL_GEOMETRY, sketch_weights=SKETCH_WEIGHTS, sketch_alpha=params.sketch_alpha,
        hardscape_regions=hardscape_regions,
        transit_falloff_ft=transit_falloff_ft, max_canyon_depth_ft=max_canyon_depth_ft,
        water_shade_regions=[{"mask": WATER_SHADE_MASK}],
        greenscape_regions=[{"mask": GREENSCAPE_MASK}],
        amenity_resting_regions=[{"mask": AMENITY_RESTING_MASK}],
        deficit_hotspots=deficit_hotspots,
    )
    voxels = engine.run(phase=3)

    structural = StructuralFramingEngine(
        REAL_GEOMETRY, engine, material_mode=params.material_mode, shoring_density=params.shoring_density)
    result = structural.run()

    typology = TypologyAssetEngine(REAL_GEOMETRY, engine)
    buildings = BuildingMassEngine([b.model_dump() for b in params.buildings]).run()
    all_specs = result["harvested_blocks"] + result["structural"] + typology.run() + buildings

    kind_counts = {}
    for s in all_specs:
        kind_counts[s.kind] = kind_counts.get(s.kind, 0) + 1

    return {
        # Every voxel, not just excavated ones -- mirrors
        # blender_cockpit.py's build_terrace_mesh exactly: an unexcavated
        # voxel (z_ft == 0) still gets a solid block built from floor_z up
        # to grade, so the un-cut majority of the site reads as a real
        # base slab the canyon is cut INTO, not a disconnected floating
        # island of excavated cells. An earlier version filtered these out
        # as a payload-size optimization, which silently dropped that
        # entire base slab from the web viewport.
        "voxels": [
            {
                "gx": v.gx, "gy": v.gy, "z_ft": v.z_ft, "level": v.level, "typology": v.typology,
                "is_greenscape": v.is_greenscape,
            }
            for v in voxels
        ],
        "structural": [
            {
                "kind": s.kind, "x_ft": s.x_ft, "y_ft": s.y_ft, "z_top_ft": s.z_top_ft,
                "height_ft": s.height_ft, "scale": s.scale, "rotation_deg": s.rotation_deg,
                "x2_ft": s.x2_ft, "y2_ft": s.y2_ft, "z2_ft": s.z2_ft, "radius_ft": s.radius_ft,
                "scale_y": s.scale_y,
            }
            for s in all_specs
        ],
        "kind_counts": kind_counts,
        "used_real_amenity_data": deficit_hotspots is not None,
        "slab_harvest_tons": result["slab_harvest_tons"],
        "max_canyon_depth_ft": max_canyon_depth_ft,
        "voxel_ft": VOXEL_FT,
    }
