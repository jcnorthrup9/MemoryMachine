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
import math
import os
import shutil
import sys
import time

import numpy as np
from pydantic import BaseModel, Field

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from terracing_engine import (  # noqa: E402
    TerracingEngine, StructuralFramingEngine, TypologyAssetEngine, BuildingMassEngine,
    STRUCTURAL_BAY_FT, build_cut_sheet_manifest, slab_key,
    build_bay_grid, aggregate_grid_to_bays, voxel_attr_grid)
# sketch_weight_mapper.py's find_latest_sketch is pure os.listdir/getmtime --
# safe to import here even though the rest of that module needs PIL/
# svgpathtools (those imports are local to the functions that need them,
# same reasoning blender_cockpit.py already relies on).
from sketch_weight_mapper import find_latest_sketch  # noqa: E402
# amenity_deficit.py only needs the stdlib csv module -- same reasoning as
# above, safe to import directly at module level.
from amenity_deficit import load_deficit_hotspots_from_csv, find_latest_csv  # noqa: E402
from logic.program_placement import load_programs, place_programs  # noqa: E402
from logic.canopy_engine import CanopyEngine, zone_centroids_and_radii  # noqa: E402
# foot_traffic.py mirrors amenity_deficit.py's CSV contract exactly, for a
# separate real-data channel (foot traffic vs. amenity deficit) -- aliased
# since both modules define a same-named find_latest_csv().
from foot_traffic import (  # noqa: E402
    load_foot_traffic_hotspots_from_csv, find_latest_csv as find_latest_foot_traffic_csv)
# noise_survey.py mirrors the same CSV contract, a third real-data channel
# (2026-07-12) -- see terracing_engine.py's SANCTUARY_NOISE_THRESHOLD/
# data_alpha for what it actually feeds.
from noise_survey import (  # noqa: E402
    load_noise_hotspots_from_csv, find_latest_csv as find_latest_noise_csv)
from circulation_network import CirculationNetworkEngine, rasterize_network_canyon  # noqa: E402
import drawing_styles  # noqa: E402
# Aliased -- this module defines its own juror_chat() function below (the
# route handler), which would otherwise shadow the imported module of the
# same name at module scope.
from logic import juror_chat as juror_chat_agent  # noqa: E402
import ingest_diagram_svg  # noqa: E402

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
# Server-side build archive (2026-07-12, ARCHIVE tab) -- distinct from
# App.jsx's client-side "Save Build" download: same snapshot schema
# (memory-machine-build-v1), but persisted here so it survives a page
# reload/different machine and can be browsed as a real gallery instead of
# just a one-off file download.
ARCHIVE_DIR = os.path.join(BASE_DIR, "outputs", "pershing_archive")
os.makedirs(ARCHIVE_DIR, exist_ok=True)

with open(REAL_GEOMETRY_PATH) as f:
    REAL_GEOMETRY = json.load(f)


def _empty_mask(nx, nz):
    return [[False] * nz for _ in range(nx)]


def _empty_attractor_points():
    return {"major_attractor": [], "minor_attractor": [], "amphitheatre": []}


def _atomic_write_json(path, data):
    """Write-to-temp-then-rename so a crash/kill mid-write can't leave a
    truncated, unreadable file behind (os.replace is atomic on both Windows
    and POSIX). Shared by _save_paint_state() (runtime persist) and the
    one-time water_shade->water/trees migration below (bootstrap-time) --
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

# How far a major/minor attractor's pull reaches (2026-07-16 program-
# placement correlation logic) -- roughly a third of the site's ~600ft
# length, "close enough to plausibly feel the pull of a major draw."
# Linear falloff to 0 beyond this radius, see _attractor_proximity_bays().
ATTRACTOR_INFLUENCE_RADIUS_FT = 200.0

# 2026-07-17 demand-driven excavation ceiling -- ASPO Planning Advisory
# Service Report No. 194 (Jan 1965, "Standards for Outdoor Recreational
# Areas"), citing Butler's Standards for Municipal Recreation Areas (NRA,
# rev. 1962, p.6): "30 to 50 per cent of the total park and recreation
# land of a community should be set aside for active recreation."
# Midpoint used as the active-recreation area budget. ACTIVE_RECREATION_
# CATEGORIES maps onto sports_recreation only -- the one category in
# program_requirements.json unambiguously "active" per that standard;
# "outdoor" mixes active items (playground/workout_equipment) with
# passive ones (picnic_grill_site), and splitting it further isn't
# grounded in any real categorization this project already tracks, so
# it's conservatively excluded rather than guessed at. See rebuild()'s
# excavation_scale computation.
ACTIVE_RECREATION_SITE_FRACTION = 0.40
ACTIVE_RECREATION_CATEGORIES = {"sports_recreation"}

# One real full floor-to-floor step (2026-07-16 program_boxes per-bay
# extrusion) -- real_geometry.json's real_slabs "floor_slab" kind entries
# (the real full floor plates, as opposed to the mid-level "ramp_slab"
# entries) sit at a uniform 10ft z_top_ft spacing (0 / -10 / -20 / -30), so
# this is ground truth, not a guess -- confirmed by direct inspection, not
# derived from Voxel.level (irregular depth-bucket bands) or voxel_ft/
# STRUCTURAL_BAY_FT (9ft/27ft excavation and column grids, unrelated to
# floor-to-floor height).
REAL_LEVEL_HEIGHT_FT = 10.0

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

# Same lookup, third real-data channel (2026-07-12) -- None if
# data/noise_survey/ has no CSV yet, in which case rebuild() stays on
# TerracingEngine's own DEFAULT_NOISE_HOTSPOTS placeholder regardless of
# what the frontend's toggle is set to.
NOISE_CSV_PATH = find_latest_noise_csv()

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
    if "water" in _paint_state and "trees" in _paint_state:
        WATER_MASK = _paint_state["water"]
        TREE_MASK = _paint_state["trees"]
    elif "water" in _paint_state and "shade" in _paint_state:
        # One-time migration (2026-07-16 shade -> trees rename): this file
        # predates the rename and only has the old "shade" key. Straight
        # key rename, same data, no ambiguity to resolve (unlike the
        # water_shade split below) -- "shade" always meant "trees go here"
        # since the 2026-07-11 split (see TypologyAssetEngine.tree_specs()),
        # this just makes the paint category's name match what it places.
        WATER_MASK = _paint_state["water"]
        TREE_MASK = _paint_state["shade"]
        print(f"[pershing_api] migrated {PAINT_STATE_PATH} from shade to trees (same data, key rename only)")
        _atomic_write_json(PAINT_STATE_PATH, {
            "canyon": SKETCH_WEIGHTS, "hardscape": HARDSCAPE_MASK,
            "water": WATER_MASK, "trees": TREE_MASK,
            "greenscape": _paint_state["greenscape"], "amenity_resting": _paint_state["amenity_resting"],
        })
    else:
        # One-time migration (2026-07-11 water_shade -> water/trees split):
        # this file predates the split and only has the old combined
        # "water_shade" key. Back it up with a TIMESTAMPED filename before
        # touching it -- a fixed ".bak" name caused a real data-loss
        # incident earlier this session (a second migration/install run
        # silently clobbered the first backup). Migrate water_shade -> water
        # only, trees starts empty: this specific file's water_shade mask
        # is provably pure water (it came from ingest_legacy_diagram.py's
        # blue-pixel-only segmentation, and the SHADE/GREEN_SPACE color-
        # collision bug in static/main.js's _getLayerColor meant no diagram
        # exported before that fix could ever have produced a real shade/
        # tree signal) -- duplicating into both would fabricate tree
        # placement the user never actually specified. See
        # archive/memoryMachine/MILESTONE_07112026_PlanningSession.md.
        _backup_path = f"{PAINT_STATE_PATH}.{int(time.time())}.bak"
        shutil.copy2(PAINT_STATE_PATH, _backup_path)
        WATER_MASK = _paint_state["water_shade"]
        TREE_MASK = _empty_mask(NX, NZ)
        print(f"[pershing_api] migrated {PAINT_STATE_PATH} from water_shade to water/trees "
              f"(trees starts empty) -- pre-migration backup at {_backup_path}")
        _atomic_write_json(PAINT_STATE_PATH, {
            "canyon": SKETCH_WEIGHTS, "hardscape": HARDSCAPE_MASK,
            "water": WATER_MASK, "trees": TREE_MASK,
            "greenscape": _paint_state["greenscape"], "amenity_resting": _paint_state["amenity_resting"],
        })
    GREENSCAPE_MASK = _paint_state["greenscape"]
    AMENITY_RESTING_MASK = _paint_state["amenity_resting"]
    # DECK_MASK (2026-07-13, "remove top slab" excavation/hardscape
    # decouple) -- .get() with an empty-mask fallback, not a hard key
    # lookup like the others above: this field is new, so any
    # PAINT_STATE_PATH written before today simply won't have it yet, and
    # (unlike the water_shade/shade->trees migrations) there's no ambiguity to migrate --
    # "no deck painted yet" is exactly what an empty mask already means.
    DECK_MASK = _paint_state.get("deck") or _empty_mask(NX, NZ)
    # CANOPY_MASK (2026-07-13, Canopy Engine) -- same .get()-with-fallback
    # as DECK_MASK above: new field, no legacy-payload ambiguity to migrate.
    CANOPY_MASK = _paint_state.get("canopy") or _empty_mask(NX, NZ)
    # ATTRACTOR_POINTS (2026-07-16, program-placement correlation logic) --
    # same .get()-with-fallback as DECK_MASK/CANOPY_MASK: new field, no
    # legacy-payload ambiguity to migrate ("no attractors baked yet" is
    # exactly what an empty per-category dict already means).
    ATTRACTOR_POINTS = _paint_state.get("attractor_points") or _empty_attractor_points()
    # PATH_HINT_POINTS (2026-07-23) -- same .get()-with-fallback pattern as
    # DECK_MASK/CANOPY_MASK/ATTRACTOR_POINTS above.
    PATH_HINT_POINTS = _paint_state.get("path_hints") or []
elif os.path.exists(SKETCH_CACHE_PATH):
    with open(SKETCH_CACHE_PATH) as f:
        _cache = json.load(f)
    SKETCH_WEIGHTS = _cache["weights"]
    HARDSCAPE_MASK = _cache.get("hardscape_mask") or _empty_mask(NX, NZ)
    WATER_MASK = _empty_mask(NX, NZ)
    TREE_MASK = _empty_mask(NX, NZ)
    GREENSCAPE_MASK = _empty_mask(NX, NZ)
    AMENITY_RESTING_MASK = _empty_mask(NX, NZ)
    DECK_MASK = _empty_mask(NX, NZ)
    CANOPY_MASK = _empty_mask(NX, NZ)
    ATTRACTOR_POINTS = _empty_attractor_points()
    PATH_HINT_POINTS = []
else:
    SKETCH_WEIGHTS = _empty_mask(NX, NZ)
    HARDSCAPE_MASK = _empty_mask(NX, NZ)
    WATER_MASK = _empty_mask(NX, NZ)
    TREE_MASK = _empty_mask(NX, NZ)
    GREENSCAPE_MASK = _empty_mask(NX, NZ)
    AMENITY_RESTING_MASK = _empty_mask(NX, NZ)
    DECK_MASK = _empty_mask(NX, NZ)
    CANOPY_MASK = _empty_mask(NX, NZ)
    ATTRACTOR_POINTS = _empty_attractor_points()
    PATH_HINT_POINTS = []

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
    canyon and canopy are continuous weight grids (painted alpha IS the
    weight); the other five are boolean zone masks, already thresholded
    client-side. water/trees split 2026-07-11 (was one combined
    water_shade field; the "trees" field itself was named "shade" until
    the 2026-07-16 rename) -- see terracing_engine.py's Voxel docstring.
    """
    canyon: list[list[float]]
    hardscape: list[list[bool]]
    water: list[list[bool]]
    trees: list[list[bool]]
    greenscape: list[list[bool]]
    amenity_resting: list[list[bool]]
    # 2026-07-13 "remove top slab" excavation/hardscape decouple: a
    # DEDICATED "keep this as a deck" signal, separate from hardscape paint
    # (which keeps its existing meaning everywhere else -- program scoring,
    # and the normal score-driven canyon dig's own hardscape veto, both
    # stay exactly as before). See TerracingEngine._z_for_voxel. Defaulted
    # (unlike the other six grids) so legacy_diagram_bridge.py's
    # preview_import() -- which predates this field and has no equivalent
    # signal to convert -- can keep calling bakePaint() without needing its
    # own update; "no deck painted" is exactly what an empty default means.
    deck: list[list[bool]] = Field(default_factory=lambda: _empty_mask(NX, NZ))
    # 2026-07-13 Canopy Engine: a continuous weight grid, same role as
    # canyon above (painted alpha IS the weight, not thresholded to a
    # boolean) -- see CanopyEngine's height equation. Defaulted, like deck,
    # NOT undefaulted like canyon: logic/legacy_diagram_bridge.py's
    # preview_import() builds a BakeGrids-shaped dict from
    # ingest_legacy_diagram.convert_one(), which predates this field and has
    # no equivalent color-segmented signal to convert -- "no canopy painted"
    # is exactly what an empty default means, same reasoning as deck's.
    canopy: list[list[float]] = Field(default_factory=lambda: _empty_mask(NX, NZ))
    # 2026-07-16 program-placement correlation logic: discrete major/minor
    # attractor (+ amphitheatre) marker positions, in site-feet -- NOT an
    # area mask like the seven grids above. Defaulted like deck/canopy: only
    # logic/legacy_diagram_bridge.py's preview_import() has an equivalent
    # signal to forward (see ingest_diagram_svg.extract_attractor_points());
    # freehand painting has no discrete-point concept, so "not provided"
    # correctly means "no attractors this bake."
    attractor_points: dict[str, list[dict]] = Field(default_factory=_empty_attractor_points)
    # 2026-07-23: points sampled from a 2D-diagram PEDESTRIAN_PATH layer
    # (see ingest_diagram_svg.extract_path_hints_from_composed_layers()) --
    # NOT an area mask, and not categorized like attractor_points (all one
    # motivator, "path_hint"), just a flat list. Defaulted like
    # attractor_points: only the SPATIALIZE/2D-generation bake paths have an
    # equivalent signal to forward; freehand painting has no path concept.
    path_hints: list[dict] = Field(default_factory=list)


def _save_paint_state():
    """Persist all live grids (+ attractor points) to PAINT_STATE_PATH
    (2026-07-10 persistence supplement, water/trees split 2026-07-11, deck
    mask 2026-07-13, canopy mask 2026-07-13, attractor points 2026-07-16) so
    a backend restart doesn't lose painted work -- previously bake() only
    updated the in-memory globals, never written anywhere. See
    _atomic_write_json for the actual write mechanics (shared with the
    one-time bootstrap migration above)."""
    _atomic_write_json(PAINT_STATE_PATH, {
        "canyon": SKETCH_WEIGHTS, "hardscape": HARDSCAPE_MASK, "water": WATER_MASK, "trees": TREE_MASK,
        "greenscape": GREENSCAPE_MASK, "amenity_resting": AMENITY_RESTING_MASK, "deck": DECK_MASK,
        "canopy": CANOPY_MASK, "attractor_points": ATTRACTOR_POINTS, "path_hints": PATH_HINT_POINTS,
    })


def bake(grids: BakeGrids):
    """Overwrite the live grids (+ attractor points) from a completed paint
    session and persist them (see _save_paint_state). Does NOT trigger a
    rebuild itself -- the frontend calls /rebuild right after, reusing its
    existing rebuild path rather than duplicating it here with a second copy
    of the current slider params."""
    global SKETCH_WEIGHTS, HARDSCAPE_MASK, WATER_MASK, TREE_MASK, GREENSCAPE_MASK, AMENITY_RESTING_MASK, DECK_MASK, CANOPY_MASK, ATTRACTOR_POINTS, PATH_HINT_POINTS
    SKETCH_WEIGHTS = grids.canyon
    HARDSCAPE_MASK = grids.hardscape
    WATER_MASK = grids.water
    TREE_MASK = grids.trees
    GREENSCAPE_MASK = grids.greenscape
    AMENITY_RESTING_MASK = grids.amenity_resting
    DECK_MASK = grids.deck
    CANOPY_MASK = grids.canopy
    ATTRACTOR_POINTS = grids.attractor_points
    PATH_HINT_POINTS = grids.path_hints
    _save_paint_state()
    return {
        "status": "ok",
        "counts": {
            "canyon": sum(1 for row in SKETCH_WEIGHTS for v in row if v > 0.01),
            "hardscape": sum(1 for row in HARDSCAPE_MASK for v in row if v),
            "water": sum(1 for row in WATER_MASK for v in row if v),
            "trees": sum(1 for row in TREE_MASK for v in row if v),
            "greenscape": sum(1 for row in GREENSCAPE_MASK for v in row if v),
            "amenity_resting": sum(1 for row in AMENITY_RESTING_MASK for v in row if v),
            "deck": sum(1 for row in DECK_MASK for v in row if v),
            "canopy": sum(1 for row in CANOPY_MASK for v in row if v > 0.01),
            **{f"{cat}_count": len(pts) for cat, pts in ATTRACTOR_POINTS.items()},
        },
    }


class BuildingSpec(BaseModel):
    """One parameterized building mass -- see BuildingMassEngine's
    docstring for why this is parameterized rather than read from
    data/building_heights.json (wrong coordinate frame, off-site data).
    2026-07-17: the only live producer is rebuild()'s program_box_specs
    (server-computed from real program placement) -- manual user-typed
    buildings were removed as redundant with that."""
    x_ft: float
    y_ft: float
    width_ft: float = 40.0
    depth_ft: float = 30.0
    height_ft: float = 20.0
    setback_ft: float = 0.0
    # Base elevation the building's footprint actually sits on (2026-07-13
    # "remove top slab" feature) -- 0.0 (grade) unless program placement
    # supplies its own real per-bay floor_elev_ft (see rebuild()'s
    # program_box_specs). User-placed buildings (via the UI/API, not
    # program placement) default to grade, same pre-existing behavior as
    # before this field existed.
    z_ft: float = 0.0


class NetworkParams(BaseModel):
    motivator_weights: dict[str, float] = {
        "trees": 1.0, "water": 1.0, "rest": 1.0, "foot_traffic": 1.0, "deficit": 1.0,
        # Placed program-zone entrances (2026-07-12) -- see grow_network().
        "program": 1.0,
    }
    step_ft: float = 15.0
    max_iterations: int = 300


class RebuildParams(BaseModel):
    sketch_alpha: float = 0.75
    canyon_width: int = 3
    # 2026-07-17 demand-driven excavation: bumped 1 -> 4 (36ft raw, clamped
    # to the real 30ft column-height cap) to match frontend/src/App.jsx's
    # DEFAULT_PARAMS -- keeps this Pydantic default (used by get_bay_grid()
    # and any caller that omits canyon_depth) in sync with what the live UI
    # actually sends, so "out of the box" means the same thing either way.
    canyon_depth: int = 4
    material_mode: str = "STEEL"
    shoring_density: float = 1.0
    use_real_amenity_data: bool = AMENITY_CSV_PATH is not None
    use_real_foot_traffic_data: bool = FOOT_TRAFFIC_CSV_PATH is not None
    # Blend weight for noise_hotspots' effect on SANCTUARY typology only --
    # see terracing_engine.py's SANCTUARY_NOISE_THRESHOLD/data_alpha
    # docstring. Defaults to full effect (1.0), unlike sketch_alpha's
    # designer-dominant 0.75 default, since this channel doesn't touch
    # excavation depth at all -- there's no equivalent risk of data
    # silently overriding the designer's dig.
    data_alpha: float = 1.0
    use_real_noise_data: bool = NOISE_CSV_PATH is not None
    # 2026-07-13 "remove top slab" feature: forces excavation to clear the
    # SURFACE slab everywhere except designer-protected (painted hardscape)
    # cells -- see terracing_engine.py's TerracingEngine.remove_top_slab/
    # _z_for_voxel. Real column geometry is unaffected either way (already
    # always rendered full-height regardless of this).
    remove_top_slab: bool = False
    # 2026-07-13 program enable/disable checklist -- program `id`s (data/
    # program_requirements.json's stable identifier, e.g. "soccer_field")
    # to exclude entirely from this rebuild's placement pass. Empty by
    # default (every NEEDED/Suggested program participates, same as
    # before this existed). See _program_zones_from_engine's
    # disabled_programs param and ParamPanel.jsx's Programs checklist.
    disabled_programs: list[str] = []
    # 2026-07-23: optional inline circulation-network growth -- when set,
    # rebuild() also runs CirculationNetworkEngine using the SAME engine/
    # voxels/typology_specs its own _run_pipeline() call already produced
    # (one pipeline run instead of the two a separate rebuild()+
    # grow_network() round-trip used to cost), folding "network"/
    # "kind_counts" additions into this same response. None (default)
    # keeps rebuild()'s existing behavior byte-for-byte for any caller that
    # doesn't ask for network data. See App.jsx's debounced rebuild effect,
    # which now always supplies this instead of a separate manual
    # "Grow Network" button/action.
    network: NetworkParams | None = None


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
        "noise_csv": os.path.basename(NOISE_CSV_PATH) if NOISE_CSV_PATH else None,
        # 2026-07-13 program enable/disable checklist -- every NEEDED/
        # Suggested program's id/label/target_sf, so ParamPanel.jsx can
        # render a checkbox for each one even while it's currently disabled
        # (and therefore absent from the last rebuild's own program_zones,
        # which only lists programs that actually went through placement).
        "all_programs": [
            {"id": p["id"], "label": p["label"], "category": p["category"], "target_sf": p["target_sf"]}
            for p in load_programs()
        ],
    }


def _serialize_specs(specs):
    """Shared StructuralElement -> JSON dict shape, used by rebuild()'s
    "structural" key, grow_network()'s "network" key, and generate_canopy()'s
    "canopy_panels"/"canopy_columns" keys -- keeping this in one place means
    these response payloads can never silently drift apart in which fields
    they expose."""
    return [
        {
            "kind": s.kind, "x_ft": s.x_ft, "y_ft": s.y_ft, "z_top_ft": s.z_top_ft,
            "height_ft": s.height_ft, "scale": s.scale, "rotation_deg": s.rotation_deg,
            "x2_ft": s.x2_ft, "y2_ft": s.y2_ft, "z2_ft": s.z2_ft, "radius_ft": s.radius_ft,
            "scale_y": s.scale_y,
            "column_id": s.column_id, "column_id2": s.column_id2, "slab_id": s.slab_id,
            "source": s.source,
            # 2026-07-16 Canopy Redesign -- unit surface normal, only set for
            # "panel"-shape kinds (canopy_panel). None for everything else.
            "normal_x": s.normal_x, "normal_y": s.normal_y, "normal_z": s.normal_z,
            # 2026-07-16 program_boxes per-program coloring -- see
            # StructuralElement.program_item's own docstring.
            "program_item": s.program_item,
        }
        for s in specs
    ]


def _run_pipeline(params: RebuildParams):
    """
    Same math blender_cockpit.rebuild_all() runs, minus the bpy mesh build
    -- builds the TerracingEngine/StructuralFramingEngine/TypologyAssetEngine
    stack from RebuildParams. Shared by rebuild() and grow_network(), which
    both need the identical terrain-shaping setup (the grown network must
    reflect whatever canyon/amenity state is currently on screen, not a
    separately-derived copy of it) -- extracted here specifically so the two
    can't silently drift out of sync.

    hardscape_regions is applied unconditionally -- there's no separate
    "protect hardscape" toggle anymore (removed 2026-07-06): with painting
    as the only way to mark a hardscape zone, painting one already means
    "protect this," so a second switch to also enable that protection was
    redundant, dead-looking UI.

    Building mass is deliberately NOT computed here (2026-07-12; manual
    user-placed buildings removed entirely 2026-07-17, redundant with
    program-zone-derived massing) -- program-zone-derived building specs
    (see rebuild()'s per-bay program_box_specs, built from each zone's
    "bays" list) are only knowable *after* engine/voxels exist (they come
    from placing programs onto the bay grid), and building mass has zero
    feedback into excavation/framing/typology (purely additive). Rather
    than call the bay-grid/program-zone derivation from inside here (which
    would need its own engine/voxels and reintroduce exactly the
    double-pipeline-run problem _bay_grid_from_engine()/
    _program_zones_from_engine() exist to avoid), rebuild() computes
    program_box_specs itself, after this returns, from the programmatic
    zones it derives from this same engine/voxels.

    Returns (engine, voxels, typology_specs, base_specs, meta) -- voxels is
    the flat, already-classified list engine.run() returns (every voxel,
    not just excavated ones: an unexcavated voxel still gets a solid block
    built from floor_z up to grade, so the un-cut majority of the site
    reads as a real base slab the canyon is cut INTO, not a disconnected
    floating island of excavated cells -- an earlier version filtered
    these out as a payload-size optimization, which silently dropped that
    entire base slab from the web viewport). typology_specs is
    TypologyAssetEngine's own output alone (grow_network() needs these
    positions as circulation-network attractors, separate from the full
    base_specs list rebuild() renders). base_specs does NOT include
    buildings -- see above.
    """
    hardscape_regions = [{"mask": HARDSCAPE_MASK}]

    # 2026-07-17 demand-driven excavation ceiling -- see ACTIVE_RECREATION_
    # SITE_FRACTION's own comment for the real ASPO-sourced 40% basis.
    # Floored at 1.0 (never shrinks canyon_depth's own baseline) -- this
    # only ever RAISES the ceiling when real active-recreation program
    # demand exceeds what the site's own real standard allots it.
    total_active_demand_sf = sum(
        p["target_sf"] for p in load_programs(exclude_ids=params.disabled_programs)
        if p["category"] in ACTIVE_RECREATION_CATEGORIES
    )
    active_recreation_budget_sf = (
        REAL_GEOMETRY["site"]["width_ft"] * REAL_GEOMETRY["site"]["length_ft"] * ACTIVE_RECREATION_SITE_FRACTION
    )
    excavation_scale = max(1.0, total_active_demand_sf / active_recreation_budget_sf)

    transit_falloff_ft = params.canyon_width * STRUCTURAL_BAY_FT
    max_canyon_depth_ft = min(
        params.canyon_depth * 9.0 * excavation_scale, REAL_GEOMETRY.get("column_height_ft", 30.0)
    )

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

    # Same conditional-load pattern, third real-data channel (2026-07-12).
    noise_hotspots = None
    if params.use_real_noise_data and NOISE_CSV_PATH:
        noise_hotspots = load_noise_hotspots_from_csv(
            NOISE_CSV_PATH, REAL_GEOMETRY["site"]["width_ft"], REAL_GEOMETRY["site"]["length_ft"])

    engine = TerracingEngine(
        REAL_GEOMETRY, sketch_weights=SKETCH_WEIGHTS, sketch_alpha=params.sketch_alpha,
        deficit_alpha=1.0, hardscape_regions=hardscape_regions,
        transit_falloff_ft=transit_falloff_ft, max_canyon_depth_ft=max_canyon_depth_ft,
        water_regions=[{"mask": WATER_MASK}],
        tree_regions=[{"mask": TREE_MASK}],
        greenscape_regions=[{"mask": GREENSCAPE_MASK}],
        amenity_resting_regions=[{"mask": AMENITY_RESTING_MASK}],
        deck_regions=[{"mask": DECK_MASK}],
        deficit_hotspots=deficit_hotspots,
        foot_traffic_hotspots=foot_traffic_hotspots,
        noise_hotspots=noise_hotspots,
        data_alpha=params.data_alpha,
        remove_top_slab=params.remove_top_slab,
    )
    voxels = engine.run(phase=3)

    structural = StructuralFramingEngine(
        REAL_GEOMETRY, engine, material_mode=params.material_mode, shoring_density=params.shoring_density)
    result = structural.run()

    typology = TypologyAssetEngine(REAL_GEOMETRY, engine)
    typology_specs = typology.run()
    base_specs = result["harvested_blocks"] + result["structural"] + typology_specs

    meta = {
        "max_canyon_depth_ft": max_canyon_depth_ft,
        # 2026-07-17 demand-driven excavation ceiling -- see
        # ACTIVE_RECREATION_SITE_FRACTION's own comment. 1.0 means dormant
        # (today's real program list doesn't exceed the real ASPO-sourced
        # active-recreation budget), >1.0 means it's actively raising
        # max_canyon_depth_ft above canyon_depth's own slider-derived value.
        "excavation_scale": excavation_scale,
        "used_real_amenity_data": deficit_hotspots is not None,
        "used_real_foot_traffic_data": foot_traffic_hotspots is not None,
        "used_real_noise_data": noise_hotspots is not None,
        "slab_harvest_tons": result["slab_harvest_tons"],
        # Real-slab-driven remaining/removed cells (2026-07-09 real-slab-
        # driven harvest supplement) -- depends on this rebuild's live
        # excavation params, unlike real_slabs/real_columns below which are
        # fixed geometry, so this is recomputed every call, not passed
        # through from REAL_GEOMETRY as-is.
        "real_slab_fragments": structural.real_slab_fragments(),
    }
    return engine, voxels, typology_specs, base_specs, meta


def _bay_floor_elevations(engine, voxels, nx_bays, nz_bays, bays_per_side=3):
    """
    Per-bay "what real surface is actually exposed now" elevation
    (2026-07-13, "remove top slab" feature) -- reuses
    StructuralFramingEngine.classify_terrain_cells() (already does exactly
    "per-cell, picks the shallowest not-yet-excavated real slab", see its
    own docstring) rather than re-deriving that logic. A throwaway
    StructuralFramingEngine here is cheap relative to a full _run_pipeline
    call -- it only needs build_column_slab_graph() (pure function of
    REAL_GEOMETRY, not excavation state) plus one more nx*nz classification
    pass, not a second full terracing/typology/steel-frame run.

    Mode (most common value), not mean, per bay: floor elevation is a
    fundamentally discrete/categorical quantity (which real slab, if any,
    is exposed) -- aggregate_grid_to_bays' usual plain-average approach
    (fine for continuous fields like transit_influence) would blend two
    genuinely different real elevations into a physically meaningless
    number wherever a bay straddles a step between them.

    Cells with no real slab exposed at all (classify_terrain_cells()
    returns None -- excavated past every real slab present there, or
    outside every slab's footprint) fall back to 0.0 (grade) -- a
    reasonable default absent any real precedent, and matches this
    feature's pre-existing behavior when remove_top_slab is off (nearly
    every cell resolves to the SURFACE slab's ~0.25ft elevation either way,
    a difference too small to matter for placing programs/buildings on).
    """
    structural = StructuralFramingEngine(REAL_GEOMETRY, engine)
    classified = structural.classify_terrain_cells()
    slab_z_by_key = {slab_key(s): s["z_top_ft"] for s in REAL_GEOMETRY.get("real_slabs", [])}

    nx, nz = engine.nx, engine.nz
    out = [[0.0] * nz_bays for _ in range(nx_bays)]
    for bx in range(nx_bays):
        for bz in range(nz_bays):
            counts = {}
            for dx in range(bays_per_side):
                gx = bx * bays_per_side + dx
                if gx >= nx:
                    continue
                for dz in range(bays_per_side):
                    gz = bz * bays_per_side + dz
                    if gz >= nz:
                        continue
                    k = classified.get((gx, gz))
                    z = slab_z_by_key.get(k, 0.0) if k is not None else 0.0
                    counts[z] = counts.get(z, 0) + 1
            out[bx][bz] = max(counts, key=counts.get) if counts else 0.0
    return out


def _attractor_proximity_bays(bay_cells, points, radius_ft=ATTRACTOR_INFLUENCE_RADIUS_FT):
    """{(gx, gy): 0..1} proximity-to-nearest-point falloff for one attractor
    category (2026-07-16 program-placement correlation logic) -- 1.0 AT a
    point, linearly down to 0.0 at radius_ft away, 0.0 for every bay if
    `points` is empty (nothing painted/imported yet). `points` entries are
    {"x_ft":.., "y_ft":..} in site-feet (ingest_diagram_svg.extract_
    attractor_points()'s output shape); "y_ft" here means the plan z-axis,
    same convention BuildingSpec.y_ft and every painted mask already use --
    matched against each bay's own (x_ft, z_ft) center, NOT a vertical
    coordinate."""
    if not points:
        return {idx: 0.0 for idx in bay_cells}
    out = {}
    for idx, cell in bay_cells.items():
        nearest = min(math.hypot(cell.x_ft - p["x_ft"], cell.z_ft - p["y_ft"]) for p in points)
        out[idx] = max(0.0, 1.0 - nearest / radius_ft)
    return out


def _bay_grid_from_engine(engine, voxels):
    """
    Body of get_bay_grid(), extracted (2026-07-12) to take an already-
    computed (engine, voxels) pair instead of running _run_pipeline itself
    -- lets rebuild()/grow_network() derive the bay grid from their OWN
    already-computed, live-params engine/voxels without paying for a
    second, default-params _run_pipeline call. get_bay_grid() below (and
    the standalone GET /api/pershing/bay-grid route) still get a fresh
    default-params engine themselves and call this.

    Returns the 27ft structural bay grid (build_bay_grid(), previously only
    an ephemeral private dict inside StructuralFramingEngine._column_grid())
    plus per-bay aggregated placement signals, for logic/program_placement.py
    (or any future consumer) to build on without re-deriving bay geometry or
    re-running the terracing pipeline itself.

    Two signal tiers, both aggregated from voxel resolution up to bay
    resolution (aggregate_grid_to_bays): the PRIMARY signal is whatever the
    designer has actually painted or imported via either live ingestion
    channel (GREENSCAPE_MASK/HARDSCAPE_MASK/AMENITY_RESTING_MASK/WATER_MASK
    -- see bake()/legacy_diagram_bridge.py), since that's real, already-
    expressed design intent; the SECONDARY signal is the existing
    transit/deficit fields from TerracingEngine, meant as a tie-breaker when
    a site (or region of one) has no painted/imported intent yet.
    """
    bay_cells, nx_bays, nz_bays = build_bay_grid(REAL_GEOMETRY)

    greenscape_bay = aggregate_grid_to_bays(GREENSCAPE_MASK, nx_bays, nz_bays)
    hardscape_bay = aggregate_grid_to_bays(HARDSCAPE_MASK, nx_bays, nz_bays)
    amenity_resting_bay = aggregate_grid_to_bays(AMENITY_RESTING_MASK, nx_bays, nz_bays)
    water_bay = aggregate_grid_to_bays(WATER_MASK, nx_bays, nz_bays)
    # 2026-07-16 program-placement correlation logic: TREE_MASK aggregated
    # the same way as the other painted masks -- the closest live "this area
    # will be shaded" proxy (trees are literally the shade-producing typology
    # asset), distinct from CANOPY_MASK (architectural canopy structure, a
    # separate system) -- see [[memorymachine_shade_trees_canopy_naming]].
    trees_bay = aggregate_grid_to_bays(TREE_MASK, nx_bays, nz_bays)
    transit_bay = aggregate_grid_to_bays(voxel_attr_grid(voxels, engine.nx, engine.nz, "transit_influence"),
                                          nx_bays, nz_bays)
    deficit_bay = aggregate_grid_to_bays(voxel_attr_grid(voxels, engine.nx, engine.nz, "deficit_influence"),
                                          nx_bays, nz_bays)
    # 2026-07-13 "remove top slab" feature -- see _bay_floor_elevations()'s
    # own docstring for why this is a separate mode-based aggregation, not
    # another aggregate_grid_to_bays() mean.
    floor_elev_bay = _bay_floor_elevations(engine, voxels, nx_bays, nz_bays)
    # 2026-07-16 program-placement correlation logic: per-bay 0..1 proximity
    # to the nearest major/minor attractor marker (see bake()/BakeGrids'
    # attractor_points, sourced from a diagram import) -- see
    # _attractor_proximity_bays()'s own docstring for the falloff math.
    # amphitheatre points are persisted but not scored here (out of scope).
    major_attractor_bay = _attractor_proximity_bays(bay_cells, ATTRACTOR_POINTS.get("major_attractor") or [])
    minor_attractor_bay = _attractor_proximity_bays(bay_cells, ATTRACTOR_POINTS.get("minor_attractor") or [])

    bays = [
        {
            "gx": gx, "gy": gy, "x_ft": cell.x_ft, "z_ft": cell.z_ft,
            "column_id": cell.column_id, "is_buildable": cell.is_buildable,
            "greenscape": greenscape_bay[gx][gy], "hardscape": hardscape_bay[gx][gy],
            "amenity_resting": amenity_resting_bay[gx][gy], "water": water_bay[gx][gy],
            "trees": trees_bay[gx][gy],
            "transit_influence": transit_bay[gx][gy], "deficit_influence": deficit_bay[gx][gy],
            "floor_elev_ft": floor_elev_bay[gx][gy],
            "major_attractor_proximity": major_attractor_bay[(gx, gy)],
            "minor_attractor_proximity": minor_attractor_bay[(gx, gy)],
        }
        for (gx, gy), cell in bay_cells.items()
    ]

    return {
        "nx_bays": nx_bays, "nz_bays": nz_bays, "bay_ft": STRUCTURAL_BAY_FT, "bays": bays,
        # 2026-07-17 restroom "host attachment" placement -- the real
        # surveyed metro entrance, passed through the bay_grid dict rather
        # than as a loose param so logic/program_placement.py stays
        # decoupled from pershing_api/REAL_GEOMETRY (it only ever reads
        # bay_grid, same as every other spatial signal it consumes).
        "metro_entrance": {"x_ft": REAL_GEOMETRY["secondary_entrance_anchor"]["x"],
                            "z_ft": REAL_GEOMETRY["secondary_entrance_anchor"]["z"]},
    }


def get_bay_grid():
    """
    Thin default-params wrapper around _bay_grid_from_engine() -- still used
    by the standalone GET /api/pershing/bay-grid route and get_program_zones()
    below, i.e. any caller that doesn't already have a live engine/voxels
    pair of its own to reuse.

    Uses default RebuildParams() rather than whatever sliders the frontend
    currently has set: the primary (painted/imported mask) signal doesn't
    depend on slider state at all, and the secondary (transit/deficit)
    tie-breaker only needs to be roughly current, not pixel-perfect against
    live sliders -- rebuild() remains the source of truth for that.
    """
    engine, voxels, *_ = _run_pipeline(RebuildParams())
    return _bay_grid_from_engine(engine, voxels)


def _program_zones_from_engine(engine, voxels, disabled_programs=None):
    """Body of get_program_zones(), extracted (2026-07-12) the same way as
    _bay_grid_from_engine() -- see that function's docstring for why.

    disabled_programs (2026-07-13 program enable/disable checklist):
    passed straight through to load_programs()'s exclude_ids -- None here
    (get_program_zones()'s own default-params wrapper below) means every
    program participates, same pre-existing behavior; rebuild() passes
    params.disabled_programs instead (see its own call site)."""
    bay_grid = _bay_grid_from_engine(engine, voxels)
    programs = load_programs(exclude_ids=disabled_programs)
    return {"bay_ft": bay_grid["bay_ft"], "zones": place_programs(bay_grid, programs)}


def get_program_zones():
    """
    Runs logic/program_placement.py's greedy region-growing bin-packing
    algorithm against the live bay grid (get_bay_grid()) and
    data/program_requirements.json's NEEDED/Suggested programs (Optional --
    the two Health Care items -- excluded by default, same as
    load_programs()'s own default), returning one zone per program: which
    bays it claimed, achieved vs. target square footage, and whether it was
    fully satisfied.

    Thin default-params wrapper around _program_zones_from_engine() -- see
    get_bay_grid()'s docstring for why this uses RebuildParams() defaults
    rather than live slider state. Recomputed on every call rather than
    cached -- reflects whatever masks are currently painted/imported.
    """
    engine, voxels, *_ = _run_pipeline(RebuildParams())
    return _program_zones_from_engine(engine, voxels)


# Auto-seeded tree fallback (2026-07-24) -- mirrors CanopyEngine's
# _auto_coverage_mask() (see logic/canopy_engine.py), but green_space is
# deliberately the ONLY category here, unlike canopy's green_space/
# sports_recreation/outdoor: trees are a real ground obstacle, planting them
# through an active sports court or outdoor gathering surface would be wrong
# in a way a floating canopy panel overhead isn't. radius_scale=1.0 (no
# padding past the zone's own footprint, unlike canopy's crest falloff) for
# the same reason -- trees spilling past a green_space zone's edge into a
# neighboring claimed zone would be the same kind of mistake.
DEFAULT_TREE_COVERAGE_CATEGORIES = ("green_space",)
TREE_COVERAGE_RADIUS_SCALE = 1.0


def _auto_seed_trees(voxels, zones):
    """Marks is_tree=True on every not-yet-tree, not-hardscape, not-water
    voxel within a green_space program zone's real footprint -- same
    "auto-seed near qualifying program zones, painting/diagram content
    still works as an addable override, never erased" pattern
    CanopyEngine's _auto_coverage_mask() already established, applied here
    so trees stop depending entirely on a 2D diagram happening to include
    SHADE content. That dependency was real and narrow: of the 5 precedent
    SVGs this app draws diagram layers from (data/PershingMetabolizer/
    parkSVG/PrecedentSVG/), only Schouwburgplein.svg actually has a SHADE
    group at all -- a generation that doesn't happen to pick a layer from
    that one site, with nothing painted either, previously produced zero
    trees with no fallback.

    Mutates `voxels` in place -- these are the same real Voxel objects
    TerracingEngine._flat_voxels()/engine.voxels[gx][gy] both reference (a
    flatten, not a copy, see that method's own body), so this correctly
    affects everything downstream that reads is_tree, including
    TypologyAssetEngine.tree_specs() and CanopyEngine's puncture mask.

    Returns how many cells got newly seeded, purely for a log line -- 0
    means either no qualifying green_space zone exists yet, or every
    candidate cell was already tree/hardscape/water."""
    zone_info = zone_centroids_and_radii(
        zones, DEFAULT_TREE_COVERAGE_CATEGORIES, VOXEL_FT, TREE_COVERAGE_RADIUS_SCALE)
    if not zone_info:
        return 0
    seeded = 0
    for v in voxels:
        if v.is_tree or v.is_hardscape or v.is_water:
            continue
        for cx, cy, radius in zone_info:
            if math.hypot(v.wx - cx, v.wy - cy) <= radius:
                v.is_tree = True
                seeded += 1
                break
    return seeded


_QUADRANT_FEATURES = [
    ("is_tree", "TREES"), ("is_water", "WATER"), ("is_greenscape", "GREENSCAPE"),
    ("is_amenity_resting", "AMENITY_RESTING"), ("is_hardscape", "HARDSCAPE"),
]


def _build_spatial_summary(voxels, zones, engine):
    """
    Turns the full per-voxel classification (voxels, already computed by
    this same rebuild()'s _run_pipeline() call -- no extra work) plus
    placed program zones into a list[str] of plain-language observations,
    the exact shape logic/juror_chat.py's critique_design()/
    _build_critique_prompt() expect -- deliberately coarse (quadrant-level,
    not per-voxel) since "The Metabolist" persona is meant to receive a
    "simplified summary," not the raw grid (see CRITIC_PERSONA_SYSTEM_TEXT).

    Cheap and synchronous (no LLM call here) -- included in every rebuild()
    response so the frontend always has fresh grounding data on hand before
    a juror ever clicks "Ask The Metabolist" (that button then just POSTs
    this back, see critique() below -- kept as a separate on-demand call
    since _post_to_ollama has up to a 30s timeout, too slow to fold into
    every live-slider rebuild).
    """
    mid_x, mid_y = engine.nx / 2.0, engine.nz / 2.0

    def quadrant_of(gx, gy):
        ns = "north" if gy >= mid_y else "south"
        ew = "east" if gx >= mid_x else "west"
        return f"{ns}{ew}"

    counts = {
        q: {"total": 0, "typologies": {}, **{label: 0 for _, label in _QUADRANT_FEATURES}}
        for q in ("northeast", "northwest", "southeast", "southwest")
    }
    for v in voxels:
        q = counts[quadrant_of(v.gx, v.gy)]
        q["total"] += 1
        for attr, label in _QUADRANT_FEATURES:
            if getattr(v, attr):
                q[label] += 1
        if v.typology:
            q["typologies"][v.typology] = q["typologies"].get(v.typology, 0) + 1

    lines = []
    for q_name, q in counts.items():
        total = q["total"] or 1
        dominant_attr, dominant_label = max(_QUADRANT_FEATURES, key=lambda f: q[f[1]])
        if q[dominant_label] / total >= 0.15:
            lines.append(f"The {q_name} area is largely {dominant_label} "
                         f"({q[dominant_label]}/{total} voxels there).")
        if q["typologies"]:
            top_typology = max(q["typologies"], key=q["typologies"].get)
            if q["typologies"][top_typology] >= 3:
                lines.append(f"A cluster of {top_typology} typology is present in the {q_name}.")

    for zone in zones:
        entrance = zone.get("entrance")
        if entrance is None:
            continue
        gx = min(max(int(entrance["x_ft"] // engine.voxel_ft), 0), engine.nx - 1)
        gy = min(max(int(entrance["y_ft"] // engine.voxel_ft), 0), engine.nz - 1)
        lines.append(f"The '{zone['program_item']}' program zone ({zone['category']}) "
                     f"is located in the {quadrant_of(gx, gy)}.")

    return lines


def rebuild(params: RebuildParams):
    """Returns JSON voxels + structural/typology specs for the frontend to
    render however it likes (Three.js instancing, etc).

    Manual user-placed buildings (2026-07-12) were removed entirely
    2026-07-17 -- redundant with program-zone box massing below, which
    covers the same "building_mass" visual with real program-driven
    placement instead of an arbitrary typed-in box with no connection to
    any program or real data.

    Program-zone box massing (2026-07-16 rework, per-bay extrusion): each
    placed program zone's box massing is now ONE building_mass box PER
    CLAIMED BAY (zone["bays"], the exact same [gx, gy, floor_elev_ft] list
    the flat-plane ProgramZoneFootprint already renders from), not one
    bounding box per zone -- confirmed live that a single bounding box
    misrepresents any zone with an irregular/non-contiguous claimed shape
    (it doesn't match what the flat-plane view shows, and for split zones
    it bridges gaps that were never actually claimed). Each bay box is
    extruded from that bay's own real floor_elev_ft up by
    REAL_LEVEL_HEIGHT_FT (one real level), doubled for programs flagged
    program_requirements.json's "double_height": true (public_gym,
    skatepark -- vertical-clearance programs named explicitly by the user,
    not inferred). This makes program_boxes a real sizing/massing study
    (accurate footprint + accurate real-world level height), not just a
    placeholder volume. Returned as its OWN "program_boxes" response field,
    NOT merged into base_specs -- these are an OPTIONAL placeholder-massing
    preview (Viewport.jsx's "Program Boxes" toggle), independent of both
    "Program Zones" (the existing flat-plane footprint markers) and
    "Structural" (which would otherwise force every program's box on
    whenever real structural framing is shown, the exact same kind-mixing
    problem the canopy_beam/Structural split fixed 2026-07-16 for a
    different feature)."""
    engine, voxels, typology_specs, base_specs, meta = _run_pipeline(params)

    zones = _program_zones_from_engine(engine, voxels, disabled_programs=params.disabled_programs)["zones"]

    # 2026-07-24: typology_specs/base_specs above were already computed
    # inside _run_pipeline(), BEFORE zones existed (chicken-and-egg: zones
    # need voxels from the same pipeline run, but tree geometry used to be
    # baked in at that same early voxel-processing phase, via
    # TypologyAssetEngine.run() -> tree_specs()). Auto-seeding trees here
    # AFTER zones are known means the tree_trunk/tree_canopy specs already
    # sitting in base_specs are stale -- patch them without re-running the
    # whole (expensive) pipeline: strip the old ones, regenerate fresh from
    # the now-mutated is_tree state (covers both originally-painted AND
    # newly-auto-seeded cells, no duplicates since we start from a clean
    # strip). See _auto_seed_trees()'s own docstring for why this exists.
    seeded_tree_count = _auto_seed_trees(voxels, zones)
    if seeded_tree_count:
        base_specs = [s for s in base_specs if s.kind not in ("tree_trunk", "tree_canopy")]
        base_specs += TypologyAssetEngine(REAL_GEOMETRY, engine).tree_specs()

    program_box_specs = [
        BuildingSpec(
            x_ft=gx * STRUCTURAL_BAY_FT,
            y_ft=gy * STRUCTURAL_BAY_FT,
            width_ft=STRUCTURAL_BAY_FT,
            depth_ft=STRUCTURAL_BAY_FT,
            height_ft=REAL_LEVEL_HEIGHT_FT * (2 if zone.get("double_height") else 1),
            z_ft=floor_elev_ft,
        )
        for zone in zones
        for gx, gy, floor_elev_ft in zone["bays"]
    ]
    # Which program each box in program_box_specs belongs to, same order as
    # the comprehension above -- BuildingMassEngine.run() below builds fresh
    # StructuralElements from BuildingSpec (which has no program identity of
    # its own), so this gets zipped back on afterward rather than threaded
    # through BuildingSpec.
    program_box_items = [
        zone["program_item"] for zone in zones for _ in zone["bays"]
    ]
    program_boxes = BuildingMassEngine([b.model_dump() for b in program_box_specs]).run()
    for spec, program_item in zip(program_boxes, program_box_items):
        spec.program_item = program_item

    kind_counts = {}
    for s in base_specs:
        kind_counts[s.kind] = kind_counts.get(s.kind, 0) + 1

    # 2026-07-23: optional inline circulation-network growth (see
    # RebuildParams.network's docstring) -- reuses THIS call's own
    # engine/voxels/typology_specs/zones (already computed above), same
    # reasoning grow_network() itself already documents for reusing
    # _program_zones_from_engine over get_program_zones(): avoids a second,
    # redundant _run_pipeline() run. None (the default) skips this entirely,
    # so any caller that doesn't ask for network data pays nothing extra.
    network_fields = {}
    if params.network is not None:
        net = CirculationNetworkEngine(
            REAL_GEOMETRY, engine, typology_specs,
            motivator_weights=params.network.motivator_weights,
            step_ft=params.network.step_ft,
            max_iterations=params.network.max_iterations,
            zones=zones, path_hints=PATH_HINT_POINTS,
        )
        network_specs = net.run()
        network_kind_counts = {}
        for s in network_specs:
            network_kind_counts[s.kind] = network_kind_counts.get(s.kind, 0) + 1
        network_fields = {
            "network": _serialize_specs(network_specs),
            # Named distinctly from "kind_counts" above (that one counts
            # STRUCTURAL FRAMING kinds -- steel_strut/timber_beam/etc; this
            # counts NETWORK kinds -- footpath/ramp/escalator/bridge/
            # lookout_point. Genuinely different concepts, would silently
            # collide under one key.
            "network_kind_counts": network_kind_counts,
            "network_node_count": len(net.nodes),
            "network_attractor_count": len(net.attractors),
            "network_attractors_unconsumed": sum(1 for a in net.attractors if not a.consumed),
        }

    return {
        **network_fields,
        "voxels": [
            {
                "gx": v.gx, "gy": v.gy, "z_ft": v.z_ft, "level": v.level, "typology": v.typology,
                "is_greenscape": v.is_greenscape,
            }
            for v in voxels
        ],
        "structural": _serialize_specs(base_specs),
        # 2026-07-16: every placed program zone's optional placeholder box
        # (see this function's own docstring for why these are kept OUT of
        # "structural"/kind_counts above, not merged in).
        "program_boxes": _serialize_specs(program_boxes),
        # 2026-07-12: lets App.jsx refresh placed program zones on every
        # rebuild instead of only fetching them once at mount (they were
        # already computed above for the buildings step, so this is free).
        "program_zones": zones,
        # 2026-07-16 program-placement correlation logic: cheap passthrough
        # (already live in-memory) so the frontend can render major/minor
        # attractor markers -- see _attractor_proximity_bays() for how these
        # now also influence WHERE program_zones/program_boxes above land.
        "attractor_points": ATTRACTOR_POINTS,
        # 2026-07-12: grounding data for "The Metabolist" critique -- see
        # _build_spatial_summary()'s docstring for why this is included
        # here (cheap) but the actual LLM call is a separate endpoint (slow).
        "spatial_summary": _build_spatial_summary(voxels, zones, engine),
        "kind_counts": kind_counts,
        "used_real_amenity_data": meta["used_real_amenity_data"],
        "used_real_foot_traffic_data": meta["used_real_foot_traffic_data"],
        "used_real_noise_data": meta["used_real_noise_data"],
        "slab_harvest_tons": meta["slab_harvest_tons"],
        "max_canyon_depth_ft": meta["max_canyon_depth_ft"],
        "excavation_scale": meta["excavation_scale"],
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
        # Real spiral-core parking ramp geometry (2026-07-13) -- pre-
        # tessellated vertices/faces per level per cluster, extracted
        # straight from Rhino (see PershingMetabolizer_Prototype/
        # real_geometry.json's own ramp_meshes). Passed through as-is,
        # fixed geometry like real_slabs/real_columns above -- doesn't
        # depend on excavation params. Only consumed by
        # blender/pershing_headless_build.py's OBJ export so far (not yet
        # rendered in the live Three.js viewport).
        "ramp_meshes": REAL_GEOMETRY.get("ramp_meshes", {}),
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
        # flattens base_specs (this rebuild's actual procedural elements)
        # plus the real slabs/columns into count/area/volume/linear-length
        # per kind, grouped by material family. Recomputed every rebuild
        # since base_specs depends on the live excavation/shoring params.
        "cut_sheet": build_cut_sheet_manifest(
            base_specs, REAL_GEOMETRY.get("real_slabs", []), REAL_GEOMETRY.get("real_columns", [])),
    }


class GrowNetworkRequest(BaseModel):
    rebuild: RebuildParams = RebuildParams()
    network: NetworkParams = NetworkParams()


def grow_network(payload: GrowNetworkRequest):
    """
    Grows a Space Colonization pedestrian circulation network from the
    real Metro entrance (plus fabricated site-boundary entries, see
    CirculationNetworkEngine.__init__) on top of whatever canyon/amenity
    state payload.rebuild describes -- runs the exact same _run_pipeline()
    setup rebuild() uses so the network reflects the current terrain, not a
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
    engine, voxels, typology_specs, _base_specs, _meta = _run_pipeline(payload.rebuild)
    # 2026-07-12: reuses this call's own already-computed engine/voxels via
    # _program_zones_from_engine (not get_program_zones(), which would
    # trigger a second, default-params _run_pipeline run) so placed program
    # zones can feed CirculationNetworkEngine's "program" attractors below.
    zones = _program_zones_from_engine(engine, voxels)["zones"]

    net = CirculationNetworkEngine(
        REAL_GEOMETRY, engine, typology_specs,
        motivator_weights=payload.network.motivator_weights,
        step_ft=payload.network.step_ft,
        max_iterations=payload.network.max_iterations,
        zones=zones, path_hints=PATH_HINT_POINTS,
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


def carve_network_canyon(payload: GrowNetworkRequest):
    """
    Carves a canyon along the grown circulation network's primary trunk
    (see circulation_network.rasterize_network_canyon()'s docstring for the
    flow-percentile selection/tapering logic) and commits it into the live
    SKETCH_WEIGHTS global, the same one bake() and the Hardscape∩Water
    overlap rupture (ingest_diagram_svg.apply_hardscape_water_overlap())
    both write into.

    Deliberately an EXPLICIT action, unlike network growth itself (which
    became automatic 2026-07-23, folded into every rebuild() call) --
    carving physically reshapes the terrain, and terrain reshaping feeds
    back into where the network would grow next time. Auto-carving on every
    debounced rebuild would risk a drift loop: carve -> next auto-regrow
    sees new terrain -> path shifts -> recarve drifts further. Carving stays
    a deliberate, one-time commit the designer chooses to make, same
    "compose then commit" posture bake()/spatialize_preview() already use
    elsewhere in this app.

    Merges via elementwise MAX against whatever canyon already exists
    (painted, or the Hardscape∩Water rupture) -- never erases another
    canyon source, only ever adds to it.
    """
    global SKETCH_WEIGHTS
    engine, voxels, typology_specs, _base_specs, _meta = _run_pipeline(payload.rebuild)
    zones = _program_zones_from_engine(engine, voxels)["zones"]

    net = CirculationNetworkEngine(
        REAL_GEOMETRY, engine, typology_specs,
        motivator_weights=payload.network.motivator_weights,
        step_ft=payload.network.step_ft,
        max_iterations=payload.network.max_iterations,
        zones=zones, path_hints=PATH_HINT_POINTS,
    )
    specs = net.run()

    carved = rasterize_network_canyon(specs, NX, NZ, VOXEL_FT)
    existing = np.array(SKETCH_WEIGHTS, dtype=float)
    merged = np.maximum(existing, carved)
    SKETCH_WEIGHTS = merged.tolist()
    _save_paint_state()

    carved_cells = int(np.count_nonzero(carved))
    return {
        "status": "ok",
        "carved_cells": carved_cells,
        "canyon_cells": int(np.count_nonzero(merged > 0.01)),
    }


class CanopyParams(BaseModel):
    """2026-07-16 Canopy Redesign -- every tunable CanopyEngine's __init__
    takes besides real_geometry/terracing_engine/voxels/zones/canopy_mask
    (those come from _run_pipeline()/CANOPY_MASK, not the client). Field
    names match CanopyEngine's constructor kwargs exactly (generate_canopy()
    passes this whole model in via **model_dump()), so keep them in sync --
    see logic/canopy_engine.py's module docstring for what each one does."""
    base_height_ft: float = 20.0
    wave_amplitude_ft: float = 8.0
    wave_length_x_ft: float = 120.0
    wave_length_y_ft: float = 90.0
    wave_phase_x: float = 0.0
    wave_phase_y: float = 0.0
    dip_weight_ft: float = 6.0
    program_boost_ft: float = 6.0
    sculpt_radius_scale: float = 1.3
    smoothing_iterations: int = 4
    puncture_threshold: float = 0.5
    panel_pitch_ft: float = 9.0
    # Rotation (degrees) of the panel-faceting grid -- reuses
    # logic/site_grid.py's build_site_grid() (the same rotatable overlay the
    # 2D Digital Palimpsest canvas exposes via /api/site-grid), given its own
    # independent control here rather than synced live from that separate
    # process. 0 = axis-aligned, matching pre-2026-07-24 behavior.
    panel_grid_rotation_deg: float = 0.0
    panel_thickness_ft: float = 0.15
    fork_height_fraction: float = 0.6
    fork_spread_ft: float = 4.0
    column_search_radius_ft: float = 40.0
    # Deliberately low (see _footprint_mask's own docstring) -- any
    # deliberate brush stroke should count as "painted here."
    footprint_paint_threshold: float = 0.05
    support_tie_back_tolerance_ft: float = 15.0


class GenerateCanopyRequest(BaseModel):
    rebuild: RebuildParams = RebuildParams()
    canopy: CanopyParams = CanopyParams()


def generate_canopy(payload: GenerateCanopyRequest):
    """
    Generates the organic panelized canopy roof + branching support columns
    ONLY where the user has painted the canopy brush (CANOPY_MASK) -- see
    logic/canopy_engine.py's module docstring for the full paint-as-
    footprint / sliders-as-shape design. Runs the exact same _run_pipeline()
    setup rebuild() uses so the canopy reflects the current terrain/program
    placement, not a separately-derived snapshot -- same reasoning as
    grow_network().

    Synchronous, explicit action -- not part of rebuild()'s live 200ms-
    debounced loop. Canopy generation used to run inside rebuild() itself
    (2026-07-13), gated to a flat plane by paint intensity; moved out
    2026-07-16 once panel/support generation became real per-cell work (up
    to a few thousand panels + hundreds of support elements) that has no
    reason to rerun on every trivial slider tweak -- mirrors grow_network()'s
    own already-established "heavier one-shot computation -> explicit
    button, not the live loop" pattern.
    """
    engine, voxels, _typology_specs, _base_specs, _meta = _run_pipeline(payload.rebuild)
    zones = _program_zones_from_engine(
        engine, voxels, disabled_programs=payload.rebuild.disabled_programs)["zones"]

    canopy = CanopyEngine(
        REAL_GEOMETRY, engine, voxels, zones,
        canopy_mask=CANOPY_MASK,
        **payload.canopy.model_dump(),
    )
    height_matrix, puncture_mask, panel_specs, support_specs = canopy.run()

    all_specs = panel_specs + support_specs
    kind_counts = {}
    for s in all_specs:
        kind_counts[s.kind] = kind_counts.get(s.kind, 0) + 1

    return {
        "canopy_panels": _serialize_specs(panel_specs),
        "canopy_columns": _serialize_specs(support_specs),
        "canopy_height_matrix": height_matrix,
        "canopy_puncture_mask": puncture_mask,
        "kind_counts": kind_counts,
    }


class DrawingParams(BaseModel):
    """logic/drawing_styles.py's three renderer functions, dispatched by
    `style`. `view` only matters for style="lineweight" (plan/section/axo --
    view="axo" is real and callable here, but NOT exposed in the frontend
    UI (2026-07-24: confirmed it can crash the whole shared server, not
    just fail gracefully -- see drawing_styles.py::lineweight_layers's own
    WARNING comment before wiring a UI path to it again). `show_labels`
    toggles each style's text annotations (lineweight: street-edge labels +
    title; color: street-edge labels, new 2026-07-23; diagram: per-band
    program names) -- off by default nowhere, on by default everywhere."""
    style: str = "lineweight"  # "lineweight" | "color" | "diagram"
    view: str = "plan"  # "plan" | "section" | "axo"
    # Only matters for style="lineweight" + view="plan" -- one of
    # drawing_styles.LEVEL_NAMES (SURFACE/LEVEL 1/LEVEL 2/LEVEL 3 / METRO,
    # same 4 elevations vector_export.py's GARAGE_LEVEL_ELEVATIONS_FT
    # already names). Added 2026-07-23: a single fixed cut height can't show
    # a meaningful plan once the current design has excavated the whole site
    # to varying depths -- see lineweight_layers()'s own docstring.
    level: str = "SURFACE"
    show_labels: bool = True


class GenerateDrawingsRequest(BaseModel):
    rebuild: RebuildParams = RebuildParams()
    drawing: DrawingParams = DrawingParams()


def _drawing_program_boxes(zones):
    """Same per-bay building_mass construction rebuild() itself uses (lines
    ~936-958), reused here (by generate_drawings() and save_drawing() both)
    rather than duplicated a third time."""
    program_box_specs = [
        BuildingSpec(
            x_ft=gx * STRUCTURAL_BAY_FT,
            y_ft=gy * STRUCTURAL_BAY_FT,
            width_ft=STRUCTURAL_BAY_FT,
            depth_ft=STRUCTURAL_BAY_FT,
            height_ft=REAL_LEVEL_HEIGHT_FT * (2 if zone.get("double_height") else 1),
            z_ft=floor_elev_ft,
        )
        for zone in zones
        for gx, gy, floor_elev_ft in zone["bays"]
    ]
    program_box_items = [zone["program_item"] for zone in zones for _ in zone["bays"]]
    program_boxes = BuildingMassEngine([b.model_dump() for b in program_box_specs]).run()
    for spec, program_item in zip(program_boxes, program_box_items):
        spec.program_item = program_item
    return program_boxes


def generate_drawings(payload: GenerateDrawingsRequest):
    """
    Renders one of three 2D drawing styles (see logic/drawing_styles.py)
    against whatever terrain/program params the frontend currently has set
    -- same "current in view site" contract as generate_canopy()/
    grow_network(): runs the exact same _run_pipeline() setup rebuild()
    uses, so the drawing reflects the live site, not a separately-derived
    snapshot. Synchronous, explicit action (the Drawings tab's own
    "Generate"/style-switch button), same reasoning as those two siblings.
    """
    engine, voxels, typology_specs, _base_specs, _meta = _run_pipeline(payload.rebuild)
    zones = _program_zones_from_engine(
        engine, voxels, disabled_programs=payload.rebuild.disabled_programs)["zones"]

    style = payload.drawing.style
    show_labels = payload.drawing.show_labels
    if style == "lineweight":
        svg = drawing_styles.render_lineweight_svg(
            REAL_GEOMETRY, engine, voxels, view=payload.drawing.view,
            level=payload.drawing.level, show_labels=show_labels)
        return {"svg": svg}

    program_boxes = _drawing_program_boxes(zones)

    if style == "color":
        circulation_specs = CirculationNetworkEngine(
            REAL_GEOMETRY, engine, typology_specs, zones=zones, path_hints=PATH_HINT_POINTS).run()
        svg = drawing_styles.render_color_svg(
            program_boxes, circulation_specs, voxels, engine.voxel_ft,
            REAL_GEOMETRY, typology_specs, engine.site_width_ft, engine.site_length_ft,
            show_labels=show_labels,
        )
        return {"svg": svg}

    if style == "diagram":
        svg = drawing_styles.render_diagram_svg(zones, program_boxes, show_labels=show_labels)
        return {"svg": svg}

    raise ValueError(f"unknown drawing style {style!r}")


DRAWINGS_EXPORT_DIR = os.path.join(BASE_DIR, "outputs", "drawings_export")


class SaveDrawingRequest(BaseModel):
    rebuild: RebuildParams = RebuildParams()
    drawing: DrawingParams = DrawingParams()
    label: str = ""


def save_drawing(payload: SaveDrawingRequest):
    """
    Writes the current style/view to disk as SVG + PNG + DXF. DXF for
    "lineweight" and "color" uses real site-feet coordinates (genuinely
    georeferenced geometry); "diagram" is an abstract program-distribution
    diagram, so its DXF represents each band/peak/label as plain 2D
    entities on one true-color layer per program category instead --
    still a real, colored, layered DXF, just not tied to site coordinates.

    Re-runs the pipeline fresh from `payload.rebuild` (same "explicit
    action always recomputes" convention every sibling endpoint in this
    file already follows) rather than trying to reuse whatever the client
    last had on screen -- guarantees the saved files match the params
    actually requested, not a possibly-stale client-side copy.

    Returns the written filenames (caller builds full paths/URLs itself if
    it ever needs to serve them back -- for now this only needs to confirm
    to the user what was written and where, same as exportViewPng()'s
    existing "write server-side, log the result" pattern).
    """
    os.makedirs(DRAWINGS_EXPORT_DIR, exist_ok=True)
    style = payload.drawing.style
    view = payload.drawing.view
    show_labels = payload.drawing.show_labels
    ts = time.strftime("%Y%m%d_%H%M%S")
    level_slug = payload.drawing.level.replace("/", "-").replace(" ", "")
    view_tag = f"{view}_{level_slug}" if style == "lineweight" and view == "plan" else view
    slug = f"{style}_{view_tag}_{ts}" + (f"_{payload.label}" if payload.label else "")

    engine, voxels, typology_specs, _base_specs, _meta = _run_pipeline(payload.rebuild)
    zones = _program_zones_from_engine(
        engine, voxels, disabled_programs=payload.rebuild.disabled_programs)["zones"]

    written = []

    def _write(name, mode, content):
        path = os.path.join(DRAWINGS_EXPORT_DIR, name)
        with open(path, mode) as f:
            f.write(content)
        written.append(name)

    if style == "lineweight":
        level = payload.drawing.level
        _write(f"{slug}.svg", "w", drawing_styles.render_lineweight_svg(
            REAL_GEOMETRY, engine, voxels, view=view, level=level, show_labels=show_labels))
        _write(f"{slug}.png", "wb", drawing_styles.render_lineweight_png(
            REAL_GEOMETRY, engine, voxels, view=view, level=level, show_labels=show_labels))
        layers, title = drawing_styles.lineweight_layers(REAL_GEOMETRY, engine, voxels, view, level=level)
        if layers is not None:
            drawing_styles.export_lineweight_dxf(
                REAL_GEOMETRY, engine, layers, title,
                os.path.join(DRAWINGS_EXPORT_DIR, f"{slug}.dxf"), show_labels=show_labels)
            written.append(f"{slug}.dxf")

    elif style == "color":
        program_boxes = _drawing_program_boxes(zones)
        circulation_specs = CirculationNetworkEngine(
            REAL_GEOMETRY, engine, typology_specs, zones=zones, path_hints=PATH_HINT_POINTS).run()
        args = (program_boxes, circulation_specs, voxels, engine.voxel_ft,
                 REAL_GEOMETRY, typology_specs, engine.site_width_ft, engine.site_length_ft)
        _write(f"{slug}.svg", "w", drawing_styles.render_color_svg(*args, show_labels=show_labels))
        _write(f"{slug}.png", "wb", drawing_styles.render_color_png(*args, show_labels=show_labels))
        drawing_styles.export_color_dxf(
            *args, out_path=os.path.join(DRAWINGS_EXPORT_DIR, f"{slug}.dxf"), show_labels=show_labels)
        written.append(f"{slug}.dxf")

    elif style == "diagram":
        program_boxes = _drawing_program_boxes(zones)
        _write(f"{slug}.svg", "w", drawing_styles.render_diagram_svg(zones, program_boxes, show_labels=show_labels))
        _write(f"{slug}.png", "wb", drawing_styles.render_diagram_png(zones, program_boxes, show_labels=show_labels))
        drawing_styles.export_diagram_dxf(
            zones, program_boxes, os.path.join(DRAWINGS_EXPORT_DIR, f"{slug}.dxf"), show_labels=show_labels)
        written.append(f"{slug}.dxf")

    else:
        raise ValueError(f"unknown drawing style {style!r}")

    return {"dir": DRAWINGS_EXPORT_DIR, "files": written}


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


class CritiqueRequest(BaseModel):
    # The frontend already has this from its last rebuild()'s
    # "spatial_summary" key -- forwarded here verbatim rather than this
    # endpoint recomputing it server-side, same "frontend already has the
    # grounding data, just forward it" pattern JurorChatRequest.context uses
    # above.
    spatial_summary: list[str]


def critique(payload: CritiqueRequest):
    """"The Metabolist" -- on-demand qualitative critique, deliberately a
    SEPARATE endpoint from rebuild() (not folded into every rebuild
    response) since logic/juror_chat.py's _post_to_ollama has up to a 30s
    timeout; every live-slider rebuild blocking on that would make editing
    feel broken. See juror_chat.py's CRITIC_PERSONA_SYSTEM_TEXT for the
    persona/prompt."""
    return {"critique": juror_chat_agent.critique_design(payload.spatial_summary)}


# Same layerId substring convention static/js/state.js's getProgramStats()
# classification uses (SHADE/GREEN/WATER/ATTRACTOR|UNIQUE, else hardscape)
# -- reused here so a precedent layer's inferred paint-mask role matches
# what a human would expect from that layer's own visual category, not a
# new, separate taxonomy. "excavation"/canyon has no equivalent in the OLD
# app's SOFT/HARD/PROG/BLUE/SHADE categories (canyon is a NEW-app-only
# concept), so no layer infers that role automatically.
_ROLE_BY_LAYER_SUBSTRING = [
    ("SHADE", "trees"), ("GREEN", "greenscape"), ("WATER", "water"),
    ("ATTRACTOR", "amenity_resting"), ("UNIQUE", "amenity_resting"),
    # 2026-07-23: PEDESTRIAN_PATH previously fell through to the default
    # "hardscape" role. rasterize_precedent_layers()'s category_polygons_ft
    # dict has no "path_hint" key, so items with this role are silently
    # skipped there, same as "canyon" already is -- see
    # ingest_diagram_svg.extract_path_hints_from_composed_layers() for
    # where this role's actual data gets pulled instead.
    ("PEDESTRIAN", "path_hint"),
]


def _infer_role(layer_id):
    for substr, role in _ROLE_BY_LAYER_SUBSTRING:
        if substr in layer_id:
            return role
    return "hardscape"


def _deficit_weighted_location_weights():
    """
    Buckets the live bay grid's deficit_influence field (see
    _bay_grid_from_engine()'s own docstring -- real amenity-deficit survey
    data when a CSV is loaded, terracing_engine.py's DEFAULT_DEFICIT_HOTSPOTS
    placeholder otherwise, same signal either way) into the same 9 cardinal
    zones ingest_diagram_svg.LOCATION_OFFSET_FRAC defines, for
    random_spatial_seed()'s location_weights param.

    Conversion: each bay's corner-origin (x_ft, z_ft) (see
    terracing_engine.build_bay_grid()) is re-centered into the same
    site-fraction convention LOCATION_OFFSET_FRAC's keys already use
    (East/South positive, West/North negative, Center at origin) --
    x_frac=(x_ft - width_ft/2)/width_ft, y_frac=(z_ft - length_ft/2)/length_ft
    -- then assigned to its nearest LOCATION_OFFSET_FRAC bucket by Euclidean
    distance in frac-space. Deficit scores in a bucket are summed.

    2026-07-17: this reuses the exact frac convention remix_layers()/
    rasterize_precedent_layers() already use to PLACE a chosen layer, so
    the round-trip (read deficit here in real feet -> bucket into a
    LOCATION string -> later re-expand that same LOCATION string back into
    a frac offset for placement) is self-consistent regardless of which
    literal compass direction each bucket "really" is -- a weight computed
    for "North" gets placed back at the exact same frac position "North"
    always resolves to, so a real deficit hotspot and its resulting
    amenity placement always land in the same real-world region even if
    the North/South/East/West label attached to that region turns out to
    be flipped from true compass orientation. Worth a live sanity check
    (does the highest-weighted bucket's placed output actually land near
    the real highest-deficit bays) rather than trusting this comment alone.
    """
    bay_grid = get_bay_grid()
    width_ft = REAL_GEOMETRY["site"]["width_ft"]
    length_ft = REAL_GEOMETRY["site"]["length_ft"]

    weights = {loc: 0.0 for loc in ingest_diagram_svg.LOCATION_OFFSET_FRAC}
    locations = list(ingest_diagram_svg.LOCATION_OFFSET_FRAC.items())

    for bay in bay_grid["bays"]:
        x_frac = (bay["x_ft"] - width_ft / 2) / width_ft
        y_frac = (bay["z_ft"] - length_ft / 2) / length_ft

        nearest_loc = min(
            locations,
            key=lambda kv: (kv[1][0] - x_frac) ** 2 + (kv[1][1] - y_frac) ** 2,
        )[0]
        weights[nearest_loc] += bay.get("deficit_influence") or 0.0

    return weights


def _compose_layers_to_3d(composed):
    """
    Shared tail of remix_precedent() (and now import_2d_generation() below):
    tags each composed layer (site/layerId/transform, e.g. remix_layers()'s
    output OR a saved root-app /api/generate spatial_seed) with a paint-mask
    role, then rasterizes onto the voxel grid and extracts attractor
    markers. Factored out 2026-07-22 so a second caller (importing an
    already-saved 2D generation) doesn't duplicate this exact sequence.

    Each role's polygons OR independently (rasterize_precedent_layers()'s
    default behavior) -- an overlapping cell CAN be True in multiple roles
    at once. Most such combinations still fall through to
    terracing_engine.py's own per-module rules; spatialize_preview() below
    applies one deliberate, specific treatment on top of this (Hardscape ∩
    Water -> canyon rupture, see apply_hardscape_water_overlap()) rather
    than this shared helper picking a generic winner -- a generic
    "occlusion" pass was tried and reverted (2026-07-23): it silently
    erased the very overlap signal a designed per-pair effect needs to see.

    Returns (layers_with_role, grids, counts, attractor_points, path_hints, resolved_count).
    """
    layers = [{**item, "role": _infer_role(item["layerId"])} for item in composed]

    grids, resolved_count = ingest_diagram_svg.rasterize_precedent_layers(layers, nx=NX, nz=NZ, voxel_ft=VOXEL_FT)
    counts = {
        key: sum(row.count(True) for row in grids[key])
        for key in ("hardscape", "water", "trees", "greenscape", "amenity_resting")
    }

    # 2026-07-17: any MAJOR_ATTRACTORS/MINOR_ATTRACTORS/AMPHITHEATRE layers
    # in the pick (previously always aliased away, see remix_layers()'s
    # LAYER_SITE_MEMBERSHIP comment) now resolve to real point markers here,
    # same shape/consumer as the diagram-import path's extract_attractor_points()
    # -- flows into _bay_grid_from_engine()'s attractor-proximity scoring on
    # bake(), same as a manually-composed diagram.
    attractor_points = ingest_diagram_svg.extract_attractor_points_from_composed_layers(layers)
    # 2026-07-23: same idea, but for PEDESTRIAN_PATH ("path_hint" role) --
    # flows into circulation_network.sample_attraction_points()'s path_hints
    # param via bake()'s PATH_HINT_POINTS global, so a hand-drawn 2D path
    # actually biases where the procedural network grows.
    path_hints = ingest_diagram_svg.extract_path_hints_from_composed_layers(layers)

    return layers, grids, counts, attractor_points, path_hints, resolved_count


# ---------------------------------------------------------------------------
# Import a saved 2D-app generation (2026-07-22)
# ---------------------------------------------------------------------------
# The root "Digital Palimpsest" 2D app (app.py, port 8000) already saves each
# GET/POST /api/generate call's full spatial_seed as
# archive/diagrams/generated/memory_machine_generation_<epoch_ms>.json (see
# app.py's generate_memory_node()). That spatial_seed is EXACTLY remix_layers()'s
# output shape (site/layerId/transform per item) -- the same shape
# remix_precedent() above already knows how to 3D-ify via
# _compose_layers_to_3d(). So importing a past 2D generation needs no SVG
# re-parsing/pixel classification at all (unlike legacy_diagram_bridge.py's
# JPG/SVG-image ingestion path, built for diagram_tool's exports, which
# don't carry structured layer data) -- just load the JSON and reuse the
# exact same rasterization tail remix_precedent() already uses.
GENERATIONS_DIR = os.path.join(BASE_DIR, "archive", "diagrams", "generated")


class Preview2DGenerationRequest(BaseModel):
    filename: str


def list_2d_generations(limit=20):
    """Recent memory_machine_generation_*.json records from the 2D app,
    newest first by mtime -- same pattern as
    legacy_diagram_bridge.list_recent_diagrams(), different source dir/glob."""
    import glob
    pattern = os.path.join(GENERATIONS_DIR, "memory_machine_generation_*.json")
    paths = glob.glob(pattern)
    paths.sort(key=os.path.getmtime, reverse=True)
    result = []
    for p in paths[:limit]:
        try:
            with open(p, encoding="utf-8") as f:
                record = json.load(f)
        except Exception:
            continue
        result.append({
            "filename": os.path.basename(p),
            "mtime": os.path.getmtime(p),
            "prompt": record.get("prompt", ""),
            "narrative": record.get("narrative", ""),
        })
    return result


def preview_2d_generation(filename):
    """
    Load one archived 2D-app generation and run it through the same
    role-inference + rasterization + attractor-extraction pipeline
    remix_precedent() uses, so the 3D Pershing Metabolizer can preview-then-
    bake() a layout the 2D GEN button already produced -- same response
    shape as remix_precedent() (narrative/layers/grids/counts/
    attractor_points) so an existing frontend consumer of that shape needs
    minimal changes to also handle this path.

    `filename` is resolved via os.path.basename() only -- same
    path-traversal guard save_uploaded_sketch()/legacy_diagram_bridge.
    preview_import() already use, never trust a client-supplied filename as
    a path.
    """
    safe_name = os.path.basename(filename)
    if not safe_name:
        raise ValueError("empty filename")
    path = os.path.join(GENERATIONS_DIR, safe_name)
    if not os.path.exists(path):
        raise FileNotFoundError(f"no such generation record: {safe_name}")

    with open(path, encoding="utf-8") as f:
        record = json.load(f)

    composed = record.get("spatial_seed") or []
    # The 2D app's own BOUNDARY base_seed item (app.py's generate_memory_node())
    # carries no real site/layerId content for the 3D pipeline -- it's a
    # client-render anchor only, same reason remix_precedent()'s own
    # composed list never includes one.
    composed = [item for item in composed if item.get("layerId") != "BOUNDARY"]

    layers, grids, counts, attractor_points, path_hints, resolved_count = _compose_layers_to_3d(composed)

    return {
        "filename": safe_name,
        "prompt": record.get("prompt", ""),
        "narrative": record.get("narrative", ""),
        "layers": layers,
        "grids": grids, "counts": counts,
        "resolved_layers": resolved_count, "requested_layers": len(layers),
        "attractor_points": attractor_points,
        "path_hints": path_hints,
    }


# ---------------------------------------------------------------------------
# Live "SPATIALIZE" tab (2026-07-23) -- 2D authoring ported natively into the
# 3D Pershing Metabolizer React app (frontend/src/components/SpatializerPanel.jsx)
# ---------------------------------------------------------------------------
# preview_2d_generation() above works from an already-saved JSON file. The
# live-authoring tab has its stack in memory (React state) and shouldn't need
# a save-then-reload round-trip just to preview a bake -- this takes the
# spatial_seed straight from the request body instead.
class SpatializePreviewRequest(BaseModel):
    spatial_seed: list


def spatialize_preview(spatial_seed):
    """
    Same pipeline as preview_2d_generation(), minus the file load: takes
    the live SPATIALIZE canvas's in-memory stack directly.

    2026-07-23: also applies apply_hardscape_water_overlap() -- the first
    of what's meant to become several deliberate, category-specific
    treatments for overlapping 2D layers (see that function's docstring
    for why "just pick one category and discard the other" -- an earlier
    approach here, since reverted -- was the wrong move: it erases the
    exact signal a designed overlap effect needs to see). Recomputes
    `counts` afterward since the overlap pass can change hardscape/canyon.
    """
    composed = [item for item in (spatial_seed or []) if item.get("layerId") != "BOUNDARY"]
    layers, grids, _stale_counts, attractor_points, path_hints, resolved_count = _compose_layers_to_3d(composed)

    grids, overlap_cells = ingest_diagram_svg.apply_hardscape_water_overlap(grids)
    if overlap_cells:
        print(f"      -> [SPATIALIZE] {overlap_cells} cell(s) ruptured (hardscape ∩ water overlap)")
    counts = {
        key: sum(row.count(True) for row in grids[key])
        for key in ("hardscape", "water", "trees", "greenscape", "amenity_resting")
    }

    return {
        "layers": layers,
        "grids": grids, "counts": counts,
        "resolved_layers": resolved_count, "requested_layers": len(layers),
        "attractor_points": attractor_points,
        "path_hints": path_hints,
    }


def get_deficit_weights():
    """Public wrapper around _deficit_weighted_location_weights() -- that
    function was previously only ever called internally (by app.py's
    /api/generate deficit-weighting step); this exposes it directly too.
    Kept for whatever still wants the coarse 9-cardinal-zone summary, but
    SPATIALIZE's own overlay uses get_deficit_hotspots() below instead
    (2026-07-23) -- see that function's docstring for why: bucketing into 9
    fixed points was throwing away the real per-bay position data this
    same signal already carries."""
    return _deficit_weighted_location_weights()


def get_deficit_hotspots(top_n=12):
    """
    Real per-bay deficit-hotspot positions, NOT bucketed into
    _deficit_weighted_location_weights()'s 9 fixed cardinal points -- that
    bucketing exists because random_spatial_seed()/apply_deficit_weighting()
    need a LOCATION STRING (their placement vocabulary is cardinal
    strings), but a live visual overlay has no such constraint and should
    just show where the deficits actually are.

    Reuses the exact same bay grid and x_frac/y_frac conversion
    _deficit_weighted_location_weights() already does (same corner-origin
    (x_ft, z_ft) -> center-relative frac math, see that function's own
    docstring) -- just skips the nearest-cardinal-bucket step and returns
    individual bays directly instead.

    Returns the top_n highest-deficit_influence bays (0 excluded --
    "no deficit here" shouldn't render a hotspot at all), each as
    {"x_frac":.., "y_frac":.., "weight":..}, sorted strongest-first. Capped
    at top_n (default 12, roughly matching the old 9-point overlay's visual
    density) rather than every bay -- this site's bay grid can run into the
    hundreds of cells, and deficit_influence is typically a smooth field,
    not sparse, so returning everything above zero would flood the overlay
    with near-identical dots instead of highlighting real hotspots.
    """
    bay_grid = get_bay_grid()
    width_ft = REAL_GEOMETRY["site"]["width_ft"]
    length_ft = REAL_GEOMETRY["site"]["length_ft"]

    points = []
    for bay in bay_grid["bays"]:
        weight = bay.get("deficit_influence") or 0.0
        if weight <= 0:
            continue
        x_frac = (bay["x_ft"] - width_ft / 2) / width_ft
        y_frac = (bay["z_ft"] - length_ft / 2) / length_ft
        points.append({"x_frac": x_frac, "y_frac": y_frac, "weight": weight})

    points.sort(key=lambda p: p["weight"], reverse=True)
    return points[:top_n]


class ArchiveSaveRequest(BaseModel):
    """The frontend's own memory-machine-build-v1 snapshot object (see
    App.jsx's buildSnapshot()), forwarded here verbatim plus an optional
    user-supplied label. Loosely typed (dict) since this endpoint just
    persists whatever the frontend already assembled -- same reasoning as
    JurorChatRequest.context above -- rather than re-validating a shape
    only the frontend needs to keep consistent with its own restore logic."""
    label: str = ""
    snapshot: dict


def _safe_archive_path(filename):
    """basename()-guard a client-supplied filename against the archive dir --
    same pattern as save_uploaded_sketch()/legacy_diagram_bridge.preview_import()
    elsewhere in this file, never trust a client-supplied filename as a path."""
    safe_name = os.path.basename(filename)
    if not safe_name:
        raise ValueError("empty filename")
    return os.path.join(ARCHIVE_DIR, safe_name)


def save_build_to_archive(payload: ArchiveSaveRequest):
    """Persist a build snapshot to ARCHIVE_DIR. Filename is a sortable
    millisecond timestamp plus a slugified label (ASCII alnum/dash/underscore
    only, same reasoning as _safe_archive_path's basename guard -- the label
    is free user text and must not become a path/traversal vector), so
    list_archived_builds() can sort by filename alone without re-parsing
    every file's saved_at."""
    label = payload.label.strip()
    slug = "".join(c if c.isalnum() else "-" for c in label).strip("-")[:60] or "build"
    filename = f"{int(time.time() * 1000)}_{slug}.json"
    record = {**payload.snapshot, "label": label}
    _atomic_write_json(os.path.join(ARCHIVE_DIR, filename), record)
    return {"filename": filename, "saved_at": record.get("saved_at"), "label": label}


def list_archived_builds():
    """Lightweight summary per archived build -- deliberately does NOT
    return each file's full geometry (voxels/structural arrays can be a few
    hundred KB each; a gallery listing doesn't need them, only
    get_archived_build() below does, on actual load)."""
    entries = []
    for fname in sorted(os.listdir(ARCHIVE_DIR), reverse=True):
        if not fname.endswith(".json"):
            continue
        try:
            with open(os.path.join(ARCHIVE_DIR, fname)) as f:
                record = json.load(f)
        except (OSError, ValueError):
            continue  # skip unreadable/corrupt entries rather than failing the whole list
        data = record.get("data") or {}
        params = record.get("params") or {}
        program_zones = record.get("program_zones") or {}
        entries.append({
            "filename": fname,
            "saved_at": record.get("saved_at"),
            "label": record.get("label", ""),
            "material_mode": params.get("material_mode"),
            "slab_harvest_tons": data.get("slab_harvest_tons"),
            "instance_count": sum(data.get("kind_counts", {}).values()),
            "program_zone_count": len(program_zones.get("zones", [])),
        })
    return entries


def get_archived_build(filename):
    """Full snapshot JSON for one archived build, in the exact shape a
    locally-saved-then-loaded file already has -- App.jsx's
    handleLoadFromArchive() feeds this straight into the same
    restoreSnapshot() helper handleLoadBuild() (client-side file) uses."""
    path = _safe_archive_path(filename)
    if not os.path.exists(path):
        raise FileNotFoundError(f"no such archived build: {filename}")
    with open(path) as f:
        return json.load(f)


def delete_archived_build(filename):
    path = _safe_archive_path(filename)
    if os.path.exists(path):
        os.remove(path)
    return {"status": "ok"}
