"""
logic/program_placement.py
---------------------------
Assigns site-programming square footage (data/program_requirements.json,
reconciled against data/amenityData/amenity_needs.csv) onto the 27ft
structural bay grid (logic.pershing_api.get_bay_grid() / terracing_engine.
build_bay_grid()) -- deciding WHERE each program goes and HOW MANY bays it
needs to hit its target_sf.

Not a port of the Grasshopper pipeline's continuous ellipse-agent simulation
(ProgramDiagram.gh's companion EllipseAgent.py) -- that's a boids-style
physics simulation built for a continuous site boundary, a poor fit for a
discrete 27ft grid. This is a purpose-built greedy region-growing/bin-packing
algorithm instead, adapted for discrete cells.

Spatial signal priority (see get_bay_grid()'s docstring for the full
rationale): the PRIMARY signal is whatever the designer already painted or
imported through either live ingestion channel (PaintOverlay.jsx's freehand
canvas, or the legacy-diagram color-segmentation import) -- greenscape/
hardscape/amenity_resting masks, aggregated to bay resolution. The SECONDARY
signal (transit_influence/deficit_influence) only breaks ties where no
painted/imported intent exists yet. Neither signal is spatial in
amenity_needs.csv itself -- that CSV only supplies WHAT to build, HOW MUCH,
and PRIORITY (need_level), never WHERE.
"""
import json
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROGRAM_REQUIREMENTS_PATH = os.path.join(BASE_DIR, "data", "program_requirements.json")

BAY_AREA_SF = 27.0 * 27.0  # one structural bay, matches terracing_engine.STRUCTURAL_BAY_FT

NEED_LEVEL_ORDER = {"NEEDED": 0, "Suggested": 1, "Optional": 2}

# Which painted/imported mask category-fits which program category -- see
# get_bay_grid()'s bay dict for the source fields (0..1 true-fraction per
# bay). Categories not listed here (enrichment_civic, health_care -- both
# enclosed-structure programs with no natural surface-material preference)
# get no primary-signal bonus beyond amenity_resting, and rely more on the
# secondary transit/deficit tie-breaker and the enrichment quiet-zone penalty
# below.
CATEGORY_MASK_FIELD = {
    "green_space": "greenscape",
    "sports_recreation": "hardscape",
    "outdoor": "hardscape",
}

# Program categories that imply an enclosed structure and should generate a
# 3D building mass. See BuildingMassEngine in terracing_engine.py.
BUILDING_CATEGORIES = {"enrichment_civic", "health_care"}
DEFAULT_BUILDING_HEIGHT_FT = 15.0

PRIMARY_WEIGHT = 10.0       # category-matched mask (greenscape/hardscape)
AMENITY_RESTING_WEIGHT = 5.0  # general "designer marked this an amenity zone" bonus, all categories
WATER_EXCLUSION_FRAC = 0.5   # bay >=50% water-masked is treated as unbuildable, not just penalized
WATER_PENALTY_WEIGHT = 20.0  # below that threshold, still penalized proportional to water fraction
COLUMN_PENALTY = 0.5         # soft penalty, not exclusion -- see build_bay_grid()'s docstring:
                             # 282/286 real bays have a column, so excluding them outright would
                             # leave almost nowhere to place anything; real programs (a gym, a
                             # soccer field) routinely span a column grid anyway.
SECONDARY_WEIGHT = 1.0       # transit_influence + deficit_influence tie-breaker, well below
                             # PRIMARY_WEIGHT so it only matters when masks are empty/tied
ENRICHMENT_QUIET_PENALTY = 3.0  # enrichment_civic programs (study rooms, music practice) penalized
                                # near high-transit bays -- adapted from EllipseAgent.py's adjacency-
                                # rule *concept* (keep quiet program away from high-traffic zones),
                                # not its code.


def load_programs(need_levels=("NEEDED", "Suggested"), path=PROGRAM_REQUIREMENTS_PATH):
    """
    Load data/program_requirements.json's program list, filtered to the
    given need_levels (Optional excluded by default -- pass need_levels
    including "Optional" to include Health Care items too) and sorted
    NEEDED -> Suggested -> Optional, largest target_sf first within a tier
    (largest-first bin-packing: place the biggest asks while the most
    contiguous open area is still available).
    """
    with open(path) as f:
        data = json.load(f)
    programs = [p for p in data["programs"] if p.get("need_level") in need_levels]
    programs.sort(key=lambda p: (NEED_LEVEL_ORDER[p["need_level"]], -p["target_sf"]))
    return programs


def _bay_score(bay, category):
    """Per-bay placement score for one program's category. Higher is better.
    Returns None if the bay is hard-excluded (majority water)."""
    if bay["water"] >= WATER_EXCLUSION_FRAC:
        return None

    score = 0.0
    mask_field = CATEGORY_MASK_FIELD.get(category)
    if mask_field is not None:
        score += PRIMARY_WEIGHT * bay[mask_field]
    score += AMENITY_RESTING_WEIGHT * bay["amenity_resting"]
    score -= WATER_PENALTY_WEIGHT * bay["water"]
    if bay["column_id"]:
        score -= COLUMN_PENALTY
    score += SECONDARY_WEIGHT * (bay["transit_influence"] + bay["deficit_influence"])
    if category == "enrichment_civic":
        score -= ENRICHMENT_QUIET_PENALTY * bay["transit_influence"]
    return score


def place_programs(bay_grid, programs):
    """
    bay_grid: the dict returned by logic.pershing_api.get_bay_grid() (or an
    equivalent {"nx_bays", "nz_bays", "bays": [...]} structure).
    programs: a list from load_programs().

    Greedy region-growing bin-packing: for each program in priority order,
    seed at the best-scoring unclaimed bay, then repeatedly grow into the
    best-scoring 4-connected unclaimed neighbor until cumulative bay area
    meets target_sf or no valid neighbor remains (recording partial
    fulfillment in that case -- the site can run out of room).

    Returns a list of {program_item, category, need_level, bays, achieved_sf,
    target_sf, fulfilled} dicts, one per input program, in the same priority
    order they were placed.
    """
    bays_by_index = {(b["gx"], b["gy"]): b for b in bay_grid["bays"]}
    nx_bays, nz_bays = bay_grid["nx_bays"], bay_grid["nz_bays"]
    claimed = set()

    results = []
    for program in programs:
        category = program["category"]
        candidates = {
            idx: _bay_score(bay, category)
            for idx, bay in bays_by_index.items()
            if idx not in claimed
        }
        candidates = {idx: s for idx, s in candidates.items() if s is not None}

        placed_bays = []
        if candidates:
            seed = max(candidates, key=candidates.get)
            placed_bays.append(seed)
            claimed.add(seed)

            while len(placed_bays) * BAY_AREA_SF < program["target_sf"]:
                frontier = {}
                for (gx, gy) in placed_bays:
                    for ngx, ngy in ((gx + 1, gy), (gx - 1, gy), (gx, gy + 1), (gx, gy - 1)):
                        idx = (ngx, ngy)
                        if not (0 <= ngx < nx_bays and 0 <= ngy < nz_bays):
                            continue
                        if idx in claimed or idx in frontier:
                            continue
                        score = _bay_score(bays_by_index[idx], category)
                        if score is not None:
                            frontier[idx] = score
                if not frontier:
                    break  # ran out of valid room -- partial fulfillment
                best = max(frontier, key=frontier.get)
                placed_bays.append(best)
                claimed.add(best)
        
        building_spec = None
        if category in BUILDING_CATEGORIES and placed_bays:
            min_gx = min(b[0] for b in placed_bays)
            max_gx = max(b[0] for b in placed_bays)
            min_gy = min(b[1] for b in placed_bays)
            max_gy = max(b[1] for b in placed_bays)

            # BuildingSpec origin is the corner, not center.
            # The bay grid gx/gy is already aligned with the structural grid,
            # so we can convert directly to feet.
            x_ft = min_gx * BAY_AREA_SF**0.5
            y_ft = min_gy * BAY_AREA_SF**0.5
            width_ft = (max_gx - min_gx + 1) * BAY_AREA_SF**0.5
            depth_ft = (max_gy - min_gy + 1) * BAY_AREA_SF**0.5

            building_spec = {
                "x_ft": x_ft, "y_ft": y_ft,
                "width_ft": width_ft, "depth_ft": depth_ft,
                "height_ft": DEFAULT_BUILDING_HEIGHT_FT,
            }

        achieved_sf = len(placed_bays) * BAY_AREA_SF
        results.append({
            "program_item": program["label"],
            "category": category,
            "need_level": program["need_level"],
            "bays": [list(idx) for idx in placed_bays],
            "building_spec": building_spec,
            "achieved_sf": achieved_sf,
            "target_sf": program["target_sf"],
            "fulfilled": achieved_sf >= program["target_sf"],
        })

    return results
