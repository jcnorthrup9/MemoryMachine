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
from logic.canopy_engine import CanopyEngine  # noqa: E402
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
from circulation_network import CirculationNetworkEngine  # noqa: E402
# Aliased -- this module defines its own juror_chat() function below (the
# route handler), which would otherwise shadow the imported module of the
# same name at module scope.
from logic import juror_chat as juror_chat_agent  # noqa: E402
# Precedent Remixer (2026-07-12): reuses the OLD app's already-built,
# already-working AI layer-picker (generate_spatial_seed, which itself
# falls back Gemini -> local Ollama, see ai_synthesizer.query_ai) and
# offset composer (remix_layers) rather than re-deriving either -- see
# remix_precedent() below for what's actually NEW here.
from logic.ai_synthesizer import generate_spatial_seed  # noqa: E402
from logic.urban_engine import remix_layers  # noqa: E402
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
    # DECK_MASK (2026-07-13, "remove top slab" excavation/hardscape
    # decouple) -- .get() with an empty-mask fallback, not a hard key
    # lookup like the others above: this field is new, so any
    # PAINT_STATE_PATH written before today simply won't have it yet, and
    # (unlike the water_shade split) there's no ambiguity to migrate --
    # "no deck painted yet" is exactly what an empty mask already means.
    DECK_MASK = _paint_state.get("deck") or _empty_mask(NX, NZ)
    # CANOPY_MASK (2026-07-13, Canopy Engine) -- same .get()-with-fallback
    # as DECK_MASK above: new field, no legacy-payload ambiguity to migrate.
    CANOPY_MASK = _paint_state.get("canopy") or _empty_mask(NX, NZ)
elif os.path.exists(SKETCH_CACHE_PATH):
    with open(SKETCH_CACHE_PATH) as f:
        _cache = json.load(f)
    SKETCH_WEIGHTS = _cache["weights"]
    HARDSCAPE_MASK = _cache.get("hardscape_mask") or _empty_mask(NX, NZ)
    WATER_MASK = _empty_mask(NX, NZ)
    SHADE_MASK = _empty_mask(NX, NZ)
    GREENSCAPE_MASK = _empty_mask(NX, NZ)
    AMENITY_RESTING_MASK = _empty_mask(NX, NZ)
    DECK_MASK = _empty_mask(NX, NZ)
    CANOPY_MASK = _empty_mask(NX, NZ)
else:
    SKETCH_WEIGHTS = _empty_mask(NX, NZ)
    HARDSCAPE_MASK = _empty_mask(NX, NZ)
    WATER_MASK = _empty_mask(NX, NZ)
    SHADE_MASK = _empty_mask(NX, NZ)
    GREENSCAPE_MASK = _empty_mask(NX, NZ)
    AMENITY_RESTING_MASK = _empty_mask(NX, NZ)
    DECK_MASK = _empty_mask(NX, NZ)
    CANOPY_MASK = _empty_mask(NX, NZ)

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
    client-side. water/shade split 2026-07-11 (was one combined
    water_shade field) -- see terracing_engine.py's Voxel docstring.
    """
    canyon: list[list[float]]
    hardscape: list[list[bool]]
    water: list[list[bool]]
    shade: list[list[bool]]
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


def _save_paint_state():
    """Persist all 8 live grids to PAINT_STATE_PATH (2026-07-10 persistence
    supplement, water/shade split 2026-07-11, deck mask 2026-07-13, canopy
    mask 2026-07-13) so a backend restart doesn't lose painted work --
    previously bake() only updated the in-memory globals, never written
    anywhere. See _atomic_write_json for the actual write mechanics (shared
    with the one-time bootstrap migration above)."""
    _atomic_write_json(PAINT_STATE_PATH, {
        "canyon": SKETCH_WEIGHTS, "hardscape": HARDSCAPE_MASK, "water": WATER_MASK, "shade": SHADE_MASK,
        "greenscape": GREENSCAPE_MASK, "amenity_resting": AMENITY_RESTING_MASK, "deck": DECK_MASK,
        "canopy": CANOPY_MASK,
    })


def bake(grids: BakeGrids):
    """Overwrite the eight live grids from a completed paint session and
    persist them (see _save_paint_state). Does NOT trigger a rebuild itself
    -- the frontend calls /rebuild right after, reusing its existing
    rebuild path rather than duplicating it here with a second copy of the
    current slider params."""
    global SKETCH_WEIGHTS, HARDSCAPE_MASK, WATER_MASK, SHADE_MASK, GREENSCAPE_MASK, AMENITY_RESTING_MASK, DECK_MASK, CANOPY_MASK
    SKETCH_WEIGHTS = grids.canyon
    HARDSCAPE_MASK = grids.hardscape
    WATER_MASK = grids.water
    SHADE_MASK = grids.shade
    GREENSCAPE_MASK = grids.greenscape
    AMENITY_RESTING_MASK = grids.amenity_resting
    DECK_MASK = grids.deck
    CANOPY_MASK = grids.canopy
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
            "deck": sum(1 for row in DECK_MASK for v in row if v),
            "canopy": sum(1 for row in CANOPY_MASK for v in row if v > 0.01),
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
    # Base elevation the building's footprint actually sits on (2026-07-13
    # "remove top slab" feature) -- 0.0 (grade) unless a program-placement-
    # derived building_spec supplies its own real floor_elev_ft. User-placed
    # buildings (via the UI/API, not program placement) default to grade,
    # same pre-existing behavior as before this field existed.
    z_ft: float = 0.0


class RebuildParams(BaseModel):
    sketch_alpha: float = 0.75
    canyon_width: int = 3
    canyon_depth: int = 1
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
    buildings: list[BuildingSpec] = []
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

    Building mass is deliberately NOT computed here (2026-07-12) even
    though params.buildings is available -- program-zone-derived building
    specs (see logic/program_placement.py's building_spec) are only knowable
    *after* engine/voxels exist (they come from placing programs onto the
    bay grid), and building mass has zero feedback into excavation/framing/
    typology (purely additive). Rather than call the bay-grid/program-zone
    derivation from inside here (which would need its own engine/voxels and
    reintroduce exactly the double-pipeline-run problem
    _bay_grid_from_engine()/_program_zones_from_engine() exist to avoid),
    rebuild() computes buildings itself, after this returns, from both
    params.buildings and the programmatic zones it derives from this same
    engine/voxels.

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

    # Same conditional-load pattern, third real-data channel (2026-07-12).
    noise_hotspots = None
    if params.use_real_noise_data and NOISE_CSV_PATH:
        noise_hotspots = load_noise_hotspots_from_csv(
            NOISE_CSV_PATH, REAL_GEOMETRY["site"]["width_ft"], REAL_GEOMETRY["site"]["length_ft"])

    engine = TerracingEngine(
        REAL_GEOMETRY, sketch_weights=SKETCH_WEIGHTS, sketch_alpha=params.sketch_alpha,
        hardscape_regions=hardscape_regions,
        transit_falloff_ft=transit_falloff_ft, max_canyon_depth_ft=max_canyon_depth_ft,
        water_regions=[{"mask": WATER_MASK}],
        shade_regions=[{"mask": SHADE_MASK}],
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
    transit_bay = aggregate_grid_to_bays(voxel_attr_grid(voxels, engine.nx, engine.nz, "transit_influence"),
                                          nx_bays, nz_bays)
    deficit_bay = aggregate_grid_to_bays(voxel_attr_grid(voxels, engine.nx, engine.nz, "deficit_influence"),
                                          nx_bays, nz_bays)
    # 2026-07-13 "remove top slab" feature -- see _bay_floor_elevations()'s
    # own docstring for why this is a separate mode-based aggregation, not
    # another aggregate_grid_to_bays() mean.
    floor_elev_bay = _bay_floor_elevations(engine, voxels, nx_bays, nz_bays)

    bays = [
        {
            "gx": gx, "gy": gy, "x_ft": cell.x_ft, "z_ft": cell.z_ft,
            "column_id": cell.column_id, "is_buildable": cell.is_buildable,
            "greenscape": greenscape_bay[gx][gy], "hardscape": hardscape_bay[gx][gy],
            "amenity_resting": amenity_resting_bay[gx][gy], "water": water_bay[gx][gy],
            "transit_influence": transit_bay[gx][gy], "deficit_influence": deficit_bay[gx][gy],
            "floor_elev_ft": floor_elev_bay[gx][gy],
        }
        for (gx, gy), cell in bay_cells.items()
    ]

    return {"nx_bays": nx_bays, "nz_bays": nz_bays, "bay_ft": STRUCTURAL_BAY_FT, "bays": bays}


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


_QUADRANT_FEATURES = [
    ("is_shade", "SHADE"), ("is_water", "WATER"), ("is_greenscape", "GREENSCAPE"),
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

    Buildings (2026-07-12): params.buildings (user-placed, via the UI/API)
    render unconditionally as real structural mass, merged into all_specs
    -- these are explicit manual placements, not tied to any program zone.

    Program-zone box massing (2026-07-16 rework): EVERY placed program zone
    now gets a building_spec (see logic/program_placement.py's place_programs()
    -- previously only enrichment_civic/health_care zones did), sized to
    that zone's real claimed bay footprint, not a separate target_sf-
    derived shape. Returned as its OWN "program_boxes" response field,
    NOT merged into all_specs -- these are an OPTIONAL placeholder-massing
    preview (Viewport.jsx's "Program Boxes" toggle), independent of both
    "Program Zones" (the existing flat-plane footprint markers) and
    "Structural" (which would otherwise force every program's box on
    whenever real structural framing is shown, the exact same kind-mixing
    problem the canopy_beam/Structural split fixed 2026-07-16 for a
    different feature)."""
    engine, voxels, typology_specs, base_specs, meta = _run_pipeline(params)

    zones = _program_zones_from_engine(engine, voxels, disabled_programs=params.disabled_programs)["zones"]

    manual_buildings = BuildingMassEngine([b.model_dump() for b in params.buildings]).run()
    all_specs = base_specs + manual_buildings

    program_box_specs = [
        BuildingSpec(**z["building_spec"]) for z in zones if z["building_spec"]
    ]
    program_boxes = BuildingMassEngine([b.model_dump() for b in program_box_specs]).run()

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
        # 2026-07-16: every placed program zone's optional placeholder box
        # (see this function's own docstring for why these are kept OUT of
        # "structural"/kind_counts above, not merged in).
        "program_boxes": _serialize_specs(program_boxes),
        # 2026-07-12: lets App.jsx refresh placed program zones on every
        # rebuild instead of only fetching them once at mount (they were
        # already computed above for the buildings step, so this is free).
        "program_zones": zones,
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
        # Placed program-zone entrances (2026-07-12) -- see grow_network().
        "program": 1.0,
    }
    step_ft: float = 15.0
    max_iterations: int = 300


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
        zones=zones,
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


class RemixPrecedentRequest(BaseModel):
    prompt: str


# Same layerId substring convention static/js/state.js's getProgramStats()
# classification uses (SHADE/GREEN/WATER/ATTRACTOR|UNIQUE, else hardscape)
# -- reused here so a precedent layer's inferred paint-mask role matches
# what a human would expect from that layer's own visual category, not a
# new, separate taxonomy. "excavation"/canyon has no equivalent in the OLD
# app's SOFT/HARD/PROG/BLUE/SHADE categories (canyon is a NEW-app-only
# concept), so no layer infers that role automatically -- see
# remix_precedent()'s docstring.
_ROLE_BY_LAYER_SUBSTRING = [
    ("SHADE", "shade"), ("GREEN", "greenscape"), ("WATER", "water"),
    ("ATTRACTOR", "amenity_resting"), ("UNIQUE", "amenity_resting"),
]


def _infer_role(layer_id):
    for substr, role in _ROLE_BY_LAYER_SUBSTRING:
        if substr in layer_id:
            return role
    return "hardscape"


def remix_precedent(payload: RemixPrecedentRequest):
    """
    "Precedent Remixer" (2026-07-12) -- MVP first slice of the workflow
    discussed in the 2026-07-12 Gemini planning session (see
    archive/memoryMachine/STRATEGY_SUMMARY_07122026.md), replacing the OLD
    app's dead-end (image-only, no editable data model) diagram generator
    with one whose output can actually drive this app's live paint-mask
    pipeline.

    Reuses two already-built, already-working pieces rather than
    re-deriving either: logic.ai_synthesizer.generate_spatial_seed() (the
    OLD app's LLM layer-picker -- Gemini API if configured, else falls back
    to local Ollama, see its own query_ai()) selects up to 5 precedent
    layers + cardinal placements for the given text prompt; logic.
    urban_engine.remix_layers() converts that into concrete site/layerId/
    transform offsets, the exact shape static/js/state.js's MemoryState.stack
    already knows how to render and sample. The only genuinely NEW piece
    here is _infer_role(): tagging each selected layer with which of the
    six live paint-mask categories (hardscape/water/shade/greenscape/
    amenity_resting -- "excavation"/canyon has no automatic inference, not
    part of the OLD app's taxonomy) it should feed into once applied.

    2026-07-16: the "does NOT yet rasterize" gap this docstring used to
    describe is closed -- ingest_diagram_svg.rasterize_precedent_layers()
    now converts the composed layer stack (precedent SVG-unit space, via
    each site's own boundary bbox) into real site feet and rasterizes onto
    the voxel grid, reusing this app's already-calibrated BoundaryAffine
    rather than a new bridge. Returns `grids`/`counts`/`resolved_layers`
    alongside narrative/layers so the frontend can preview-then-bake, the
    SAME pattern legacy_diagram_bridge.preview_import() already
    established (client calls bakePaint(grids) directly once the user
    confirms, no separate "apply" endpoint needed).
    """
    seed_items, narrative = generate_spatial_seed(payload.prompt)
    composed = remix_layers(seed_items)
    layers = [{**item, "role": _infer_role(item["layerId"])} for item in composed]

    grids, resolved_count = ingest_diagram_svg.rasterize_precedent_layers(layers, nx=NX, nz=NZ, voxel_ft=VOXEL_FT)
    counts = {
        key: sum(row.count(True) for row in grids[key])
        for key in ("hardscape", "water", "shade", "greenscape", "amenity_resting")
    }

    return {
        "narrative": narrative, "layers": layers,
        "grids": grids, "counts": counts,
        "resolved_layers": resolved_count, "requested_layers": len(layers),
    }


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
