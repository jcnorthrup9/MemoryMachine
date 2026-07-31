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
import math
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
    # 2026-07-17: restrooms (support_amenity) reuse the same painted-
    # hardscape signal sports_recreation/outdoor already use -- "even
    # hardscape places that could have food" (user's own framing) is
    # covered directly by this existing mask, no fabricated cafe/food
    # program needed (the real amenity_needs.csv assessment explicitly
    # found no food-service deficit -- see program_requirements.json's
    # restrooms_metro/restrooms_recreation sizing_basis fields).
    "support_amenity": "hardscape",
}

# Program categories that imply an enclosed structure -- currently only
# gates PLACEMENT behavior (single contiguous footprint vs. "use all
# available space" jumping, below), not massing/display (every category
# gets a program_boxes extrusion now, see logic/pershing_api.py's
# rebuild() docstring). support_amenity added 2026-07-17 (restrooms) --
# a restroom is a real discrete building, same reasoning as enrichment_
# civic/health_care.
BUILDING_CATEGORIES = {"enrichment_civic", "health_care", "support_amenity"}

# 2026-07-13 shape-aware growth: without this, the greedy region-grower has
# zero shape constraint and blobs out into whatever organic outline scores
# highest bay-by-bay -- confirmed live (2026-07-13) Soccer Field's placement
# was an unrecognizable blob, not a rectangle, even though its target_sf
# (~75,000 sqft) is itself a realistic regulation field size. Keyed by
# program id (data/program_requirements.json's stable identifier, not the
# display label) -- a placement-engine-internal tuning value, deliberately
# NOT added to that JSON's own schema. Only programs where real-world shape
# actually matters get an entry; everything else keeps today's fully
# organic growth (a garden plot or picnic site has no real rectangularity
# requirement). Values are long:short side ratios (FIFA regulation field is
# ~100-110m x 64-75m, roughly 1.4-1.7; a volleyball court is 18m x 9m, 2.0).
TARGET_ASPECT_RATIO = {
    "soccer_field": 1.7,
    "volleyball_court": 1.8,
}
SHAPE_WEIGHT = 8.0  # same rough scale as PRIMARY_WEIGHT below -- meaningfully competes in frontier scoring without dominating it entirely

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
LEVEL_SPREAD_BONUS_WEIGHT = 6.0  # 2026-07-13: rewards claiming a bay on a level (floor_elev_ft)
                                 # this program hasn't already claimed -- without this, nothing in
                                 # _bay_score() ever referenced level at all, so a large program
                                 # (soccer field) would happily concentrate its whole footprint on
                                 # whichever single level scored best, never touching the garage's
                                 # other floors. Additive, not a hard requirement -- still loses out
                                 # to a strong mask/amenity match (PRIMARY_WEIGHT=10), but clearly
                                 # beats the tie-breaking-only SECONDARY_WEIGHT=1. Applied in the
                                 # frontier-growth and area-jump scoring below, not at the initial
                                 # seed bay (every candidate ties there -- no level is claimed yet).

# 2026-07-16 program-placement correlation logic -- see logic/pershing_api.py's
# _bay_grid_from_engine() for where "trees"/"major_attractor_proximity"/
# "minor_attractor_proximity" get computed onto each bay.
TREE_WEIGHT = 6.0  # scaled by the program's own shade_target_pct/100 (a
                   # program with no shade_target_pct, e.g. enclosed
                   # enrichment_civic/health_care programs, gets zero
                   # contribution) -- a 50%-target program (e.g.
                   # community_garden) gets ~3.0 pull, sub-PRIMARY_WEIGHT but
                   # clearly above the tie-breaking-only SECONDARY_WEIGHT=1.
                   # "trees" (TREE_MASK) is the closest live "this area will
                   # be shaded" proxy -- distinct from CANOPY_MASK (built
                   # canopy structure, a separate system not scored here).
ATTRACTOR_WEIGHT = 6.0  # same magnitude reasoning as TREE_WEIGHT

# First-pass, tunable (major_affinity, minor_affinity) signed multipliers per
# category -- same "category-based adjacency rule" precedent as
# ENRICHMENT_QUIET_PENALTY above (adapted from EllipseAgent.py's adjacency-
# rule concept, not its code). Positive = drawn toward that attractor tier,
# negative = repelled. sports_recreation/outdoor (active, social) lean
# toward major attractors; enrichment_civic (quiet study/practice program)
# is repelled from major attractors the same way it's already penalized
# near high-transit bays, with a mild pull toward minor/secondary nodes
# instead. Categories not listed get (0.0, 0.0) -- no attractor effect.
CATEGORY_ATTRACTOR_AFFINITY = {
    "green_space": (0.4, 0.5),
    "sports_recreation": (1.0, 0.3),
    "outdoor": (0.5, 0.5),
    "enrichment_civic": (-1.0, 0.3),
    "health_care": (-0.5, 0.0),
}

# 2026-07-17 restrooms correlation logic. Two distinct signals, both scored
# outside CATEGORY_ATTRACTOR_AFFINITY (which is about painted/imported
# attractor MARKERS) since these are about (a) the real surveyed metro
# entrance (already-computed bay["transit_influence"], see terracing_
# engine.py's TerracingEngine.__init__/entrance_x/entrance_y) and (b) bays
# already claimed by OTHER programs placed earlier in this same run -- a
# genuinely different, placement-outcome-dependent signal (see
# _gathering_proximity_bonus()'s docstring for why this only works because
# restrooms sort last).
GATHERING_CATEGORIES = {"sports_recreation", "outdoor", "green_space"}
GATHERING_PROXIMITY_RADIUS_FT = 100.0  # walking-distance scale, tighter than
                                        # ATTRACTOR_INFLUENCE_RADIUS_FT
                                        # (200ft) -- a restroom needs to be
                                        # NEAR the activity, not just "feel
                                        # its pull."

# (transit_weight, gathering_weight) per support_amenity program id -- how
# strongly THIS specific program is pulled toward the real metro entrance
# vs. toward bays other gathering-type programs have already claimed.
# restrooms_metro leans hard toward the entrance; restrooms_recreation
# leans hard toward the recreation cluster -- the whole point of splitting
# restrooms into two entries instead of one compromise-location building.
# Default (4.0, 4.0) for any future support_amenity program not listed here.
RESTROOM_PROXIMITY_WEIGHTS = {
    "restrooms_metro": (10.0, 2.0),
    "restrooms_recreation": (2.0, 8.0),
}

# 2026-07-30 program-to-program correlation (distinct from both mechanisms
# above): RESTROOM_PROXIMITY_WEIGHTS pulls toward a whole CATEGORY set
# (GATHERING_CATEGORIES) and is hard-gated to category == "support_amenity";
# this instead pulls one SPECIFIC dependent program toward one or more
# specific HOST program ids, regardless of category, since "workout
# equipment should cluster near the gym" is about that one relationship,
# not "outdoor programs in general should cluster near sports_recreation
# programs in general" (there's no reason e.g. a picnic site should get
# pulled toward the gym just for sharing workout_equipment's "outdoor"
# category). Keyed by the DEPENDENT program's id -> (host ids to pull
# toward, pull strength). Reuses _gathering_proximity_bonus()'s same
# falloff math and GATHERING_PROXIMITY_RADIUS_FT, just against a
# specific host's claimed bays instead of a whole category's.
PROGRAM_PROXIMITY_WEIGHTS = {
    # 2026-07-30: 6.0 (RESTROOM_PROXIMITY_WEIGHTS' rough scale) turned out too
    # weak here to change ANY placement outcome against the real bay grid --
    # confirmed by direct comparison (identical bay picks at weight 0 and 6).
    # 15.0 is the smallest value that reliably produces a real, stable effect
    # (mean distance from workout_equipment's bays to the nearest public_gym
    # bay dropped from 56.1ft to 30.7ft, 2 of 3 bays landing directly adjacent
    # to gym instead of 0; unchanged from 15.0 up through 30.0, so this isn't
    # a fragile threshold).
    "workout_equipment": {"host_ids": ("public_gym",), "weight": 15.0},
}


def _host_bays_by_ids(results, ids):
    """Union of bay-index sets already claimed by any placed program whose
    id is in `ids` (see PROGRAM_PROXIMITY_WEIGHTS) -- None if none of them
    have placed anything yet (e.g. the host was disabled via the enable/
    disable checklist, or simply hasn't been reached yet in `programs`'
    priority order)."""
    bay_sets = [
        {(gx, gy) for gx, gy, _ in r["bays"]}
        for r in results if r.get("id") in ids and r["bays"]
    ]
    if not bay_sets:
        return None
    union = set()
    for s in bay_sets:
        union |= s
    return union


def _gathering_proximity_bonus(bay, gathering_bay_centers, radius_ft=GATHERING_PROXIMITY_RADIUS_FT):
    """0..1 falloff to the NEAREST bay already claimed by an earlier program
    in GATHERING_CATEGORIES this same place_programs() run -- same falloff
    shape as pershing_api._attractor_proximity_bays, but computed from
    placement OUTCOME so far (results accumulated by place_programs()), not
    a static painted mask. 0.0 if gathering_bay_centers is empty (nothing
    gathering-like claimed yet)."""
    if not gathering_bay_centers:
        return 0.0
    nearest = min(math.hypot(bay["x_ft"] - gx, bay["z_ft"] - gz) for gx, gz in gathering_bay_centers)
    return max(0.0, 1.0 - nearest / radius_ft)


# 2026-07-17 restroom "host attachment" placement -- REPLACES the pure
# distance-falloff pull above with a hard requirement: a restroom's seed bay
# must physically TOUCH a specific host program's already-claimed footprint,
# the way a real restroom annex attaches to a building rather than floating
# nearby. Confirmed live (2026-07-17) the pure-pull model produced a real
# but architecturally unconvincing result -- both restrooms landed in the
# same leftover neighborhood near, but not touching, any other program.
# RESTROOM_PROXIMITY_WEIGHTS/_gathering_proximity_bonus are still used
# ALONGSIDE this, as a tie-breaker among the host-adjacent candidates, not
# removed.

def _nearest_host_bays(results, bays_by_index, ref_x, ref_z, categories=None):
    """Among already-placed `results` (optionally filtered to `categories`),
    find the program whose CLOSEST claimed bay is nearest to (ref_x, ref_z)
    -- e.g. "whichever program ended up nearest the real metro entrance."
    Returns that program's full {(gx, gy), ...} bay-index set, or None if
    nothing qualifies yet (nothing placed, or `categories` excludes
    everything placed so far). Looks up each bay's real x_ft/z_ft from
    `bays_by_index` (already computed by place_programs()) rather than
    re-deriving bay-center coordinates from gx/gy itself, so this can't
    silently drift from BAY_AREA_SF/STRUCTURAL_BAY_FT."""
    best_zone = None
    best_dist = None
    for r in results:
        if categories is not None and r["category"] not in categories:
            continue
        if not r["bays"]:
            continue
        zone_dist = min(
            math.hypot(bays_by_index[(bx, by)]["x_ft"] - ref_x, bays_by_index[(bx, by)]["z_ft"] - ref_z)
            for bx, by, _ in r["bays"]
        )
        if best_dist is None or zone_dist < best_dist:
            best_dist = zone_dist
            best_zone = r
    return {(gx, gy) for gx, gy, _ in best_zone["bays"]} if best_zone else None


def _largest_host_bays(results, categories):
    """Among already-placed `results` filtered to `categories`, the
    bay-index set of the program with the largest achieved_sf -- the
    dominant activity cluster (e.g. "whichever recreation zone is
    biggest"). None if nothing qualifies yet."""
    candidates = [r for r in results if r["category"] in categories and r["bays"]]
    if not candidates:
        return None
    biggest = max(candidates, key=lambda r: r["achieved_sf"])
    return {(gx, gy) for gx, gy, _ in biggest["bays"]}


def _adjacent_to_any(idx, host_bays, nx_bays, nz_bays):
    """True if idx is 4-connected-adjacent to (touches) any bay in
    host_bays -- the actual "attachment" test, same 4-neighbor pattern
    place_programs()'s own frontier-growth step already uses."""
    gx, gy = idx
    for ngx, ngy in ((gx + 1, gy), (gx - 1, gy), (gx, gy + 1), (gx, gy - 1)):
        if 0 <= ngx < nx_bays and 0 <= ngy < nz_bays and (ngx, ngy) in host_bays:
            return True
    return False


def load_programs(need_levels=("NEEDED", "Suggested"), path=PROGRAM_REQUIREMENTS_PATH, exclude_ids=None):
    """
    Load data/program_requirements.json's program list, filtered to the
    given need_levels (Optional excluded by default -- pass need_levels
    including "Optional" to include Health Care items too) and sorted
    NEEDED -> Suggested -> Optional, largest target_sf first within a tier
    (largest-first bin-packing: place the biggest asks while the most
    contiguous open area is still available).

    exclude_ids (2026-07-13 program enable/disable checklist): program
    `id`s to drop entirely before placement -- e.g. {"soccer_field"} to
    turn off the soccer field for this rebuild. None/empty means every
    program in need_levels participates, same as before this existed.
    """
    with open(path) as f:
        data = json.load(f)
    exclude_ids = exclude_ids or ()
    programs = [p for p in data["programs"]
                if p.get("need_level") in need_levels and p["id"] not in exclude_ids]
    programs.sort(key=lambda p: (NEED_LEVEL_ORDER[p["need_level"]], -p["target_sf"]))
    return programs


def _bay_score(bay, category, shade_target_pct=None, transit_weight=0.0):
    """Per-bay placement score for one program's category. Higher is better.
    Returns None if the bay is hard-excluded (majority water).

    shade_target_pct (2026-07-16 program-placement correlation logic):
    the placing program's own data/program_requirements.json shade_target_pct
    (None/0 for programs with no shade preference, e.g. enclosed structures)
    -- see TREE_WEIGHT's comment for the scoring rationale.

    transit_weight (2026-07-17 restrooms correlation logic): per-program
    override on top of the blanket SECONDARY_WEIGHT every program already
    gets from bay["transit_influence"] -- 0.0 (no extra pull) for every
    program except RESTROOM_PROXIMITY_WEIGHTS' entries, which need a much
    stronger, dedicated pull toward the real metro entrance than the
    tie-breaking-only SECONDARY_WEIGHT provides."""
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
    if shade_target_pct:
        score += TREE_WEIGHT * bay.get("trees", 0.0) * (shade_target_pct / 100.0)
    major_aff, minor_aff = CATEGORY_ATTRACTOR_AFFINITY.get(category, (0.0, 0.0))
    score += ATTRACTOR_WEIGHT * (major_aff * bay.get("major_attractor_proximity", 0.0)
                                  + minor_aff * bay.get("minor_attractor_proximity", 0.0))
    score += transit_weight * bay["transit_influence"]
    return score


def _level_spread_bonus(bay, claimed_levels):
    """0 if this bay's level is already among the bays this program has
    claimed so far; LEVEL_SPREAD_BONUS_WEIGHT otherwise -- see that
    constant's comment. `claimed_levels` is a set of floor_elev_ft values,
    tracked per-program by place_programs() (reset for each new program)."""
    level = bay.get("floor_elev_ft", 0.0)
    return 0.0 if level in claimed_levels else LEVEL_SPREAD_BONUS_WEIGHT


def _aspect_ratio_bonus(island_bays, candidate, target_ratio):
    """How much closer to target_ratio would the CURRENT ISLAND's bounding-
    box long:short side ratio get if `candidate` were added? 0 if this
    program has no target_aspect_ratio entry (the common case -- organic
    growth, unchanged). `island_bays` is only the current contiguous
    island's bays (see place_programs()), not every bay the program has
    claimed overall -- a program that had to jump to a second disjoint area
    (see place_programs()'s docstring) still gets each island individually
    steered toward the target shape, rather than one meaningless bounding
    box spanning both.
    """
    if target_ratio is None:
        return 0.0
    all_bays = island_bays + [candidate]
    min_gx = min(b[0] for b in all_bays)
    max_gx = max(b[0] for b in all_bays)
    min_gy = min(b[1] for b in all_bays)
    max_gy = max(b[1] for b in all_bays)
    w = max_gx - min_gx + 1
    d = max_gy - min_gy + 1
    ratio = max(w, d) / min(w, d)  # >=1, orientation-agnostic (a program can run either axis)
    return SHAPE_WEIGHT / (1.0 + abs(ratio - target_ratio))


def place_programs(bay_grid, programs):
    """
    bay_grid: the dict returned by logic.pershing_api.get_bay_grid() (or an
    equivalent {"nx_bays", "nz_bays", "bays": [...]} structure).
    programs: a list from load_programs().

    Greedy region-growing bin-packing: for each program in priority order,
    seed at the best-scoring unclaimed bay, then repeatedly grow into the
    best-scoring 4-connected unclaimed neighbor until cumulative bay area
    meets target_sf or no valid neighbor remains.

    2026-07-13 "use all available space" update: for non-building
    categories (BUILDING_CATEGORIES still need one real contiguous
    footprint, unchanged), running out of 4-connected room no longer means
    partial fulfillment -- the program instead jumps to the next best-
    scoring UNCLAIMED bay anywhere on the site (no adjacency requirement)
    and keeps growing from there. Confirmed live (2026-07-13) this was the
    actual missing piece behind "programming doesn't use the parking
    garage": the site's excavation depth genuinely varies bay-to-bay
    (deeper near the transit entrance, shallower elsewhere -- there's no
    separate "L1 grid" vs "L2 grid", just one bay grid whose floor_elev_ft
    already reflects whichever real level is currently exposed there), so
    once a program can span multiple disjoint areas instead of one blob, it
    naturally ends up spanning multiple real elevations too, using
    genuinely more of the site instead of exhausting one shallow region.

    2026-07-13 level-spread bonus (LEVEL_SPREAD_BONUS_WEIGHT/
    _level_spread_bonus): the above jump-to-new-area behavior only spreads
    a program across levels as a SIDE EFFECT of running out of local room;
    it doesn't actively prefer an unused level. This bonus makes that
    preference explicit -- both the frontier-growth step and the area-jump
    step now score a candidate bay higher if its level isn't one this
    program has already claimed, so large programs actively spread across
    the garage's levels instead of concentrating on whichever single level
    scores best overall.

    Returns a list of {id, program_item, category, need_level, bays,
    achieved_sf, target_sf, fulfilled} dicts, one per input program, in the same priority
    order they were placed. Each bays entry is [gx, gy, floor_elev_ft] (not
    just [gx, gy]) since a program can now legitimately span more than one
    real elevation -- see floor_elev_ft below for the single-value (seed-
    bay) summary kept for buildings/entrance-attractor purposes.
    """
    bays_by_index = {(b["gx"], b["gy"]): b for b in bay_grid["bays"]}
    nx_bays, nz_bays = bay_grid["nx_bays"], bay_grid["nz_bays"]
    claimed = set()

    results = []
    for program in programs:
        category = program["category"]
        shade_target_pct = program.get("shade_target_pct")
        # 2026-07-17 restrooms correlation logic -- see RESTROOM_PROXIMITY_
        # WEIGHTS' own comment. gathering_bay_centers is computed ONCE per
        # program, from `results` accumulated by EARLIER programs in this
        # same loop -- only meaningful because small support_amenity
        # programs (restrooms) sort to the end of their need_level tier
        # (largest target_sf first), so every gathering-type program is
        # already placed by the time this runs.
        transit_weight, gathering_weight = (
            RESTROOM_PROXIMITY_WEIGHTS.get(program["id"], (4.0, 4.0))
            if category == "support_amenity" else (0.0, 0.0)
        )
        gathering_bay_centers = [
            (bays_by_index[(gx, gy)]["x_ft"], bays_by_index[(gx, gy)]["z_ft"])
            for r in results if r["category"] in GATHERING_CATEGORIES
            for gx, gy, _ in r["bays"]
        ] if gathering_weight else []

        # 2026-07-30 program-to-program correlation -- see
        # PROGRAM_PROXIMITY_WEIGHTS' own comment. proximity_bay_centers stays
        # empty (no bonus) until the specific host program(s) this program
        # cares about have actually placed something in `results`.
        proximity_weight = 0.0
        proximity_bay_centers = []
        prox_cfg = PROGRAM_PROXIMITY_WEIGHTS.get(program["id"])
        if prox_cfg:
            host_bays = _host_bays_by_ids(results, prox_cfg["host_ids"])
            if host_bays:
                proximity_weight = prox_cfg["weight"]
                proximity_bay_centers = [
                    (bays_by_index[idx]["x_ft"], bays_by_index[idx]["z_ft"])
                    for idx in host_bays
                ]

        candidates = {
            idx: _bay_score(bay, category, shade_target_pct, transit_weight)
            for idx, bay in bays_by_index.items()
            if idx not in claimed
        }
        candidates = {idx: s for idx, s in candidates.items() if s is not None}
        # Unlike _aspect_ratio_bonus/_level_spread_bonus (genuinely undefined
        # before this program has claimed any bay of its own -- "every
        # candidate ties"), gathering_proximity_bonus is well-defined even
        # at the very first (seed) bay: it's scored against OTHER programs'
        # already-finished placements, not this program's own in-progress
        # island. Confirmed live (2026-07-17) this matters in practice --
        # restrooms are small enough that they're frequently satisfied by
        # their single seed bay alone (the growth loop below never runs),
        # so without this the gathering bonus would silently never affect
        # restrooms_recreation's actual placement at all.
        if gathering_weight:
            candidates = {
                idx: s + gathering_weight * _gathering_proximity_bonus(bays_by_index[idx], gathering_bay_centers)
                for idx, s in candidates.items()
            }
        if proximity_weight:
            candidates = {
                idx: s + proximity_weight * _gathering_proximity_bonus(bays_by_index[idx], proximity_bay_centers)
                for idx, s in candidates.items()
            }

        # 2026-07-17 restroom "host attachment" placement -- a restroom's
        # seed bay must physically TOUCH a specific host program's already-
        # claimed footprint (see _nearest_host_bays/_largest_host_bays'
        # own docstrings for how each restroom's host is chosen). Hard
        # filter, not another scoring bonus -- RESTROOM_PROXIMITY_WEIGHTS
        # above still ranks AMONG the filtered candidates as a tie-breaker.
        # host_bays is None (no filtering) if nothing qualifying has been
        # placed yet -- e.g. every gathering program disabled via the
        # enable/disable checklist -- so restrooms still place somewhere
        # via the unfiltered scoring above, rather than failing outright.
        host_bays = None
        if program["id"] == "restrooms_metro":
            entrance = bay_grid.get("metro_entrance")
            if entrance:
                host_bays = _nearest_host_bays(results, bays_by_index, entrance["x_ft"], entrance["z_ft"])
        elif program["id"] == "restrooms_recreation":
            host_bays = _largest_host_bays(results, GATHERING_CATEGORIES)
        if host_bays:
            adjacent_candidates = {
                idx: s for idx, s in candidates.items()
                if _adjacent_to_any(idx, host_bays, nx_bays, nz_bays)
            }
            # Fall back to the unfiltered (soft-pull) candidates if the
            # chosen host's entire perimeter is already claimed by OTHER
            # programs by the time this restroom places -- better to place
            # nearby than to vanish entirely.
            if adjacent_candidates:
                candidates = adjacent_candidates

        target_ratio = TARGET_ASPECT_RATIO.get(program["id"])

        placed_bays = []
        # Index into placed_bays where the CURRENT contiguous island
        # begins (2026-07-13 shape-aware growth) -- reset on every jump to
        # a new disjoint area, so _aspect_ratio_bonus steers each island's
        # OWN shape independently instead of one meaningless bounding box
        # spanning every island the program has claimed so far.
        island_start_idx = 0
        # Levels (floor_elev_ft values) this program has claimed so far --
        # see LEVEL_SPREAD_BONUS_WEIGHT/_level_spread_bonus. Reset per
        # program (each program spreads across levels independently).
        claimed_levels = set()
        if candidates:
            seed = max(candidates, key=candidates.get)
            placed_bays.append(seed)
            claimed.add(seed)
            claimed_levels.add(bays_by_index[seed].get("floor_elev_ft", 0.0))

            while len(placed_bays) * BAY_AREA_SF < program["target_sf"]:
                current_island = placed_bays[island_start_idx:]
                frontier = {}
                for (gx, gy) in current_island:
                    for ngx, ngy in ((gx + 1, gy), (gx - 1, gy), (gx, gy + 1), (gx, gy - 1)):
                        idx = (ngx, ngy)
                        if not (0 <= ngx < nx_bays and 0 <= ngy < nz_bays):
                            continue
                        if idx in claimed or idx in frontier:
                            continue
                        score = _bay_score(bays_by_index[idx], category, shade_target_pct, transit_weight)
                        if score is not None:
                            bonus = (_aspect_ratio_bonus(current_island, idx, target_ratio)
                                     + _level_spread_bonus(bays_by_index[idx], claimed_levels)
                                     + gathering_weight * _gathering_proximity_bonus(bays_by_index[idx], gathering_bay_centers)
                                     + proximity_weight * _gathering_proximity_bonus(bays_by_index[idx], proximity_bay_centers))
                            frontier[idx] = score + bonus
                if frontier:
                    best = max(frontier, key=frontier.get)
                    placed_bays.append(best)
                    claimed.add(best)
                    claimed_levels.add(bays_by_index[best].get("floor_elev_ft", 0.0))
                    continue

                # Local 4-connected room exhausted. Building categories need
                # one real contiguous footprint -- stop here (partial
                # fulfillment), same as always. Everything else jumps to a
                # new best-scoring unclaimed bay anywhere on the site and
                # keeps growing from there -- see docstring.
                if category in BUILDING_CATEGORIES:
                    break
                remaining = {
                    idx: _bay_score(bay, category, shade_target_pct, transit_weight)
                    for idx, bay in bays_by_index.items()
                    if idx not in claimed
                }
                remaining = {
                    idx: s + _level_spread_bonus(bays_by_index[idx], claimed_levels)
                          + gathering_weight * _gathering_proximity_bonus(bays_by_index[idx], gathering_bay_centers)
                          + proximity_weight * _gathering_proximity_bonus(bays_by_index[idx], proximity_bay_centers)
                    for idx, s in remaining.items() if s is not None
                }
                if not remaining:
                    break  # truly nothing left anywhere -- real partial fulfillment
                new_seed = max(remaining, key=remaining.get)
                placed_bays.append(new_seed)
                claimed.add(new_seed)
                claimed_levels.add(bays_by_index[new_seed].get("floor_elev_ft", 0.0))
                island_start_idx = len(placed_bays) - 1  # start a fresh island from here
        
        # Floor elevation (2026-07-13 "remove top slab" feature): the real
        # surface this zone actually sits on, from the SEED bay (region-
        # growing starts from one best-scoring bay and grows outward --
        # using the seed's elevation is the simplest defensible single
        # value; a zone that happens to straddle a real elevation step will
        # look slightly off until refined further, acceptable for a first
        # pass). Defaults to plain grade (0.0) when a bay grid has no
        # floor_elev_ft key at all (an older/test caller not yet updated),
        # matching this feature's pre-existing behavior.
        floor_elev_ft = bays_by_index[placed_bays[0]].get("floor_elev_ft", 0.0) if placed_bays else 0.0

        # building_spec REMOVED 2026-07-16 (was: one bounding-box over the
        # zone's whole min/max gx/gy span). Confirmed live this didn't
        # actually match what the flat-plane ProgramZoneFootprint shows for
        # any zone with an irregular/non-contiguous claimed shape (the "use
        # all available space" jump-to-new-area behavior above means most
        # non-BUILDING_CATEGORIES zones are NOT one solid rectangle) -- a
        # bounding box silently covers bays the zone never actually
        # claimed. Replaced by per-bay extrusion computed directly in
        # logic/pershing_api.py's rebuild() from this zone's own `bays`
        # list below (one box per claimed bay, exact same footprint the
        # flat plane already renders, just given real height) -- see that
        # function's "program_boxes" docstring. DEFAULT_BUILDING_HEIGHT_FT
        # is now unused for the same reason (real per-level height comes
        # from real_geometry.json's real_slabs instead, see
        # logic/pershing_api.py's REAL_LEVEL_HEIGHT_FT).

        # Entrance attractor (2026-07-12): centroid of this zone's claimed
        # bays, in feet -- feeds circulation_network.py's "program" motivator
        # so the pedestrian network actually grows toward placed amenities,
        # not just painted masks. Centroid (not e.g. nearest-bay-to-Metro)
        # per an explicit design decision -- works uniformly for every
        # zone category, building or not. +0.5 bay converts a bay INDEX to
        # that bay's real-feet CENTER, matching what "centroid of claimed
        # cells" should mean.
        entrance = None
        if placed_bays:
            bay_ft = BAY_AREA_SF ** 0.5
            entrance = {
                "x_ft": (sum(b[0] for b in placed_bays) / len(placed_bays) + 0.5) * bay_ft,
                "y_ft": (sum(b[1] for b in placed_bays) / len(placed_bays) + 0.5) * bay_ft,
            }

        achieved_sf = len(placed_bays) * BAY_AREA_SF
        results.append({
            "id": program["id"],
            "program_item": program["label"],
            "category": category,
            "need_level": program["need_level"],
            # [gx, gy, floor_elev_ft] per bay (2026-07-13) -- not just
            # [gx, gy]: a program can now legitimately span more than one
            # real elevation (see docstring), so each bay carries its own
            # floor_elev_ft rather than assuming the whole zone shares one.
            "bays": [[idx[0], idx[1], bays_by_index[idx].get("floor_elev_ft", 0.0)] for idx in placed_bays],
            # 2026-07-16: whether this program needs 2 real levels of clear
            # height instead of 1 when extruded to program_boxes (see
            # data/program_requirements.json's own per-program field) --
            # public_gym/skatepark are the two confirmed examples so far.
            "double_height": program.get("double_height", False),
            "entrance": entrance,
            "floor_elev_ft": floor_elev_ft,
            "achieved_sf": achieved_sf,
            "target_sf": program["target_sf"],
            "fulfilled": achieved_sf >= program["target_sf"],
        })

    return results
