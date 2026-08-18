import os
import re
import json
import random
import math
import xml.etree.ElementTree as ET

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Mirrors logic/pershing_api.py's private _ROLE_BY_LAYER_SUBSTRING/_infer_role
# (not imported directly -- pershing_api.py is a heavy module with real
# import-time side effects, e.g. probing NX/NZ off calibrated site geometry,
# not something this module should drag in just to reuse a 6-line lookup).
# Keep in sync if that table changes: this is what decides which layers can
# actually contribute rasterized AREA (for _solve_zonal_scales() below) vs.
# which only ever produce a "path_hint" (PEDESTRIAN_PATH) that
# ingest_diagram_svg.rasterize_precedent_layers() silently skips.
_RASTER_ROLE_BY_LAYER_SUBSTRING = [
    ("SHADE", "trees"), ("GREEN", "greenscape"), ("WATER", "water"),
    ("ATTRACTOR", "amenity_resting"), ("UNIQUE", "amenity_resting"),
    ("PEDESTRIAN", "path_hint"),
]
_RASTERIZABLE_ROLES = {"hardscape", "water", "trees", "greenscape", "amenity_resting"}


def _infer_raster_role(layer_id):
    for substr, role in _RASTER_ROLE_BY_LAYER_SUBSTRING:
        if substr in layer_id:
            return role
    return "hardscape"


def _weighted_choice(items, weights):
    """Weighted random choice without a numpy dependency. Mirrors
    logic/ai_synthesizer.py's helper of the same name -- duplicated rather
    than imported since ai_synthesizer.py imports THIS module (guideline_
    manager), so importing back here would be circular. Falls back to
    uniform choice if every weight is 0/negative."""
    total = sum(w for w in weights if w > 0)
    if total <= 0:
        return random.choice(items)
    r = random.uniform(0, total)
    upto = 0
    for item, w in zip(items, weights):
        if w <= 0:
            continue
        upto += w
        if upto >= r:
            return item
    return items[-1]


def _best_area_anchor(layers, layer_site_membership, valid_sites):
    """Among every (layer, site) combo for this category's candidate
    layers, measure each one's NATURAL (scale=1.0) rasterized area and
    return one chosen by weighted random (weight = area) across every
    candidate with nonzero area -- biases toward real headroom (see
    remix_layers()'s comment on why "resolves at all" isn't a strong
    enough bar) while giving every site with any real coverage a genuine,
    non-zero chance, instead of deterministically always picking the
    single largest. Returns None if nothing in this category resolves to
    any real geometry anywhere.

    2026-08-13: replaced the original "randomize among top 20% by area"
    hard cutoff -- confirmed empirically (direct area measurement across
    all 5 precedent sites) to collapse to exactly ONE candidate for EVERY
    guideline category given this precedent set's real area distribution
    (e.g. GREEN_SPACE: ParcVillette=628 vs runner-up ZaryadyePark=390,
    only 62% of best, already below the 80% floor -- HARDSCAPE/
    WATER_FEATURES/MAJOR_ATTRACTORS all showed the identical one-candidate
    collapse), making every generated diagram's anchor layers fully
    deterministic despite the "random" framing. Weighted-random restores
    genuine variety (matching this function's pre-2026-07-31 unweighted-
    random spirit) while keeping the real-coverage guarantee that
    pre-2026-07-31 behavior lacked."""
    import ingest_diagram_svg

    candidates = []
    for layer in layers:
        if layer == "BOUNDARY" or _infer_raster_role(layer) not in _RASTERIZABLE_ROLES:
            continue
        for site in (layer_site_membership.get(layer) or valid_sites):
            try:
                root = ingest_diagram_svg._load_precedent_svg(site)
            except FileNotFoundError:
                continue
            g = ingest_diagram_svg._find_layer_group(root, layer)
            if g is None or not ingest_diagram_svg._group_polygons(g):
                continue
            probe_item = {
                "site": site, "layerId": layer, "role": _infer_raster_role(layer),
                "transform": {"x_frac": 0.0, "y_frac": 0.0, "scale": 1.0, "rot": 0},
            }
            masks, resolved = ingest_diagram_svg.rasterize_precedent_layers([probe_item], nx=None, nz=None)
            if not resolved:
                continue
            area = sum(row.count(True) for row in masks[probe_item["role"]])
            if area > 0:
                candidates.append((area, layer, site))

    if not candidates:
        return None
    areas = [c[0] for c in candidates]
    _area, layer, site = _weighted_choice(candidates, areas)
    return layer, site

class GuidelineManager:
    """Parses urban_design_guidelines.md table for dynamic Zonal Metadata."""
    def __init__(self, filepath):
        self.filepath = filepath
        self.all_exact_layers = [
            "BOUNDARY", "GREEN_SPACE", "SHADE", "WATER_FEATURES", 
            "STREET", "PEDESTRIAN_PATH", "MAJOR_ATTRACTORS", 
            "MINOR_ATTRACTORS", "UNIQUE_ELEMENTS", "STREET_FURNITURE", "PARKING"
        ]

    def parse(self):
        guidelines, metadata, primitives, locked = {}, {}, {}, []
        
        # Translation Bridge: Maps Markdown theory to exact Rhino layer IDs
        layer_map = {
            "**SOFT_01**": (["GREEN_SPACE", "SHADE"], "sphere", False),
            "**HARD_01**": (["STREET", "PEDESTRIAN_PATH", "STREET_FURNITURE", "PARKING", "BOUNDARY", "HARDSCAPE"], "box", True),
            "**PROG_01**": (["MAJOR_ATTRACTORS", "MINOR_ATTRACTORS", "UNIQUE_ELEMENTS"], "cylinder", False),
            "**BLUE_01**": (["WATER_FEATURES"], "disc", False)
        }

        if os.path.exists(self.filepath):
            with open(self.filepath, "r", encoding="utf-8") as f:
                content = f.read()

            table_lines = re.findall(r"\|.*\|", content)
            
            for line in table_lines:
                if "Zone ID" in line or "---" in line:
                    continue
                cols = [c.strip() for c in line.split('|')][1:-1]
                if len(cols) >= 5:
                    cat = cols[0].strip()
                    label = cols[1].strip()
                    targets = cols[2].replace("%", "").strip()
                    
                    t_min, t_max = 0, 100
                    if "-" in targets or "–" in targets:
                        parts = targets.replace("–", "-").split("-")
                        t_min, t_max = int(parts[0]), int(parts[1])
                        
                    base_cat = cat.replace("*", "").split("_")[0] # Maps "**SOFT_01**" to "SOFT"
                    guidelines[base_cat] = {"min": t_min, "max": t_max, "label": label}
                    
                    if cat in layer_map:
                        layers, prim, is_locked = layer_map[cat]
                        metadata[base_cat] = layers
                        for l in layers:
                            primitives[l] = prim
                            if is_locked and l in ["PARKING", "STREET", "BOUNDARY"] and l not in locked:
                                locked.append(l)

        if not metadata:
            metadata = {
                "SOFT": ["GREEN_SPACE", "SHADE"],
                "HARD": ["STREET", "PEDESTRIAN_PATH", "STREET_FURNITURE", "PARKING", "BOUNDARY", "HARDSCAPE"],
                "PROG": ["MAJOR_ATTRACTORS", "MINOR_ATTRACTORS", "UNIQUE_ELEMENTS"],
                "BLUE": ["WATER_FEATURES"]
            }
        if not guidelines:
            guidelines = {
                "SOFT": {"min": 30, "max": 50},
                "HARD": {"min": 40, "max": 60},
                "PROG": {"min": 10, "max": 20},
                "BLUE": {"min": 2, "max": 10},
                "Infrastructure": {"min": 100, "max": 100}
            }
        if not primitives:
            primitives = {
                "GREEN_SPACE": "sphere", "SHADE": "sphere",
                "WATER_FEATURES": "disc",
                "STREET": "box", "PEDESTRIAN_PATH": "box", "STREET_FURNITURE": "box", "PARKING": "box", "BOUNDARY": "box", "HARDSCAPE": "box",
                "MAJOR_ATTRACTORS": "cylinder", "MINOR_ATTRACTORS": "cylinder", "UNIQUE_ELEMENTS": "cylinder"
            }
        if not locked:
            locked = ["PARKING", "STREET", "BOUNDARY"]

        return {"guidelines": guidelines, "metadata": metadata, "primitives": primitives, "locked": locked}

guideline_manager = GuidelineManager(os.path.join(BASE_DIR, "urban_design_guidelines.md"))

def remix_layers(seed_items):
    """
    Offsets and scales the selected SVG layers within the Pershing Square bounds.
    Cardinal location from AI is translated to fractional offsets (of
    Pershing's own detected boundary size) relative to site center -- see
    LOCATION_OFFSET_FRAC in ingest_diagram_svg.py, which is what actually
    resolves these into real placement (this function only picks WHICH
    layer/site/location, not the final pixel math).
    """
    import random
    import math

    # Pull exclusively from GuidelineManager
    gm_data = guideline_manager.parse()
    zonal_metadata = gm_data.get("metadata", {})
    primitives_map = gm_data.get("primitives", {})
    urban_guidelines = gm_data.get("guidelines", {})

    valid_layers = [layer for category in zonal_metadata.values() for layer in category]

    # Bug fix #4: HARDSCAPE exists in SVGs but wasn't in valid_layers
    if "HARDSCAPE" not in valid_layers:
        valid_layers.append("HARDSCAPE")

    # 2026-07-16: repointed at the current canonical precedent SVG dir
    # (data/ParkSVG was the OLD, stale source -- huge multi-MB files with
    # sync-conflict artifacts, superseded 2026-07-14 by this cleaner,
    # solid-filled export set that diagram_tool/ and ingest_diagram_svg.py
    # already use as the single source of truth).
    SVG_DIR = os.path.join(BASE_DIR, 'data', 'PershingMetabolizer', 'parkSVG', 'PrecedentSVG')

    # Bug fix #3: normalize site names to match the canonical SVG filenames
    # in SVG_DIR above (2026-07-16: corrected to match those exact
    # filenames -- "ParcVillette"/"GardensBytheBay", not the old
    # "ParcdelaVillette"/"GardensByTheBay" spellings, which don't exist in
    # the current directory and would have silently failed to resolve).
    SITE_NAME_CANONICAL = {
        "pershingsquare":    "PershingSquare",
        "parcdelavillette":  "ParcVillette",
        "parcvillette":      "ParcVillette",
        "zaryadyepark":      "ZaryadyePark",
        "schouwburgplein":   "Schouwburgplein",
        "gardensbythebay":   "GardensBytheBay",
    }
    valid_sites = list(SITE_NAME_CANONICAL.values())
    if os.path.exists(SVG_DIR):
        for f in os.listdir(SVG_DIR):
            if f.lower().endswith(".svg"):
                raw = f[:-4].replace("_", "").replace(" ", "").lower()
                canonical = SITE_NAME_CANONICAL.get(raw, f[:-4])
                if canonical not in valid_sites:
                    valid_sites.append(canonical)

    # Layers that only exist in specific SVGs — route to a site that actually
    # has them. 2026-07-17: replaced the old single-site hardcode (every
    # HARDSCAPE pick forced to Schouwburgplein, every AMPHITHEATRE pick
    # forced to ZaryadyePark) with the real per-layer membership, verified
    # by grepping <g id="..."> out of every file in PrecedentSVG/. The old
    # map collapsed AI/random site variety onto one site per layer even
    # though HARDSCAPE exists in 3 of 5 sites and AMPHITHEATRE in 4 of 5 --
    # a real contributor to "the remixes look the same every few pulls".
    #
    # MAJOR_ATTRACTORS/MINOR_ATTRACTORS were previously force-aliased to
    # UNIQUE_ELEMENTS below on the premise that they "don't exist" -- false,
    # confirmed by the same SVG grep: MAJOR_ATTRACTORS is real in
    # ParcVillette/Schouwburgplein/ZaryadyePark, MINOR_ATTRACTORS in
    # GardensBytheBay/ParcVillette/Schouwburgplein. Preserving them as their
    # own layers (rather than aliasing away) is what lets a diagram's real
    # attractor-marker positions reach ingest_diagram_svg's
    # extract_attractor_points_from_composed_layers() and actually flow
    # into 3D program placement -- aliasing them to UNIQUE_ELEMENTS (a
    # plain area-fill layer, not a point marker) silently dropped that.
    LAYER_SITE_MEMBERSHIP = {
        "SHADE":            ["Schouwburgplein"],
        "HARDSCAPE":        ["PershingSquare", "Schouwburgplein", "ZaryadyePark"],
        "AMPHITHEATRE":     ["GardensBytheBay", "PershingSquare", "Schouwburgplein", "ZaryadyePark"],
        "UNIQUE_ELEMENTS":  ["PershingSquare", "Schouwburgplein"],
        "MAJOR_ATTRACTORS": ["ParcVillette", "Schouwburgplein", "ZaryadyePark"],
        "MINOR_ATTRACTORS": ["GardensBytheBay", "ParcVillette", "Schouwburgplein"],
    }

    # Bug fix #1: cardinal location -> FRACTIONAL offsets (2026-07-16,
    # replacing hand-tuned pixel values calibrated against a since-replaced
    # precedent SVG -- see ingest_diagram_svg.py's LOCATION_OFFSET_FRAC,
    # the single source of truth for these fractions now; kept here as a
    # plain re-export so this function's own composed["transform"] shape
    # doesn't need a second copy of the same table).
    from ingest_diagram_svg import LOCATION_OFFSET_FRAC as LOCATION_OFFSETS

    composed = []

    if not isinstance(seed_items, list):
        return composed

    seed_items = seed_items[:5]

    for item in seed_items:
        raw_site  = item.get("site", "PershingSquare")
        layer     = item.get("layer", "GREEN_SPACE")
        location  = item.get("location", "Center")
        # The AI's raw generation response occasionally puts a nested object
        # in "location" instead of a cardinal string (e.g. "Center"/"North")
        # -- LOCATION_OFFSETS.get(location, ...) below then crashes with
        # "unhashable type: 'dict'" since dicts can't be dict keys. Only
        # plain strings are ever valid LOCATION_OFFSETS keys, so fall back
        # to the same default this field already has instead of trusting
        # whatever shape the AI actually returned.
        if not isinstance(location, str):
            location = "Center"

        if layer not in valid_layers:
            layer = "GREEN_SPACE"

        # Normalize site name
        raw_key = raw_site.replace("_", "").replace(" ", "").lower()
        site = SITE_NAME_CANONICAL.get(raw_key, raw_site)

        # Override site only if the current pick doesn't actually have this
        # layer -- preserves the AI's/random pick's site whenever it's
        # already valid, instead of always overwriting it.
        if layer in LAYER_SITE_MEMBERSHIP:
            valid_for_layer = LAYER_SITE_MEMBERSHIP[layer]
            if site not in valid_for_layer:
                site = random.choice(valid_for_layer)
        elif site not in valid_sites:
            site = "PershingSquare"

        prim = primitives_map.get(layer, "box")

        # Bug fix #1: translate cardinal location to a fractional offset
        x_frac, y_frac = LOCATION_OFFSETS.get(location, (0.0, 0.0))

        transform = {
            "x_frac": x_frac,
            "y_frac": y_frac,
            "scale": 1.0,
            "rot": 0
        }

        composed.append({
            "site": site,
            "layerId": layer,
            "transform": transform,
            "opacity": 0.85,
            "target_width": 400,
            "target_height": 400,
            "primitive": prim,
            # 2026-08-13: carried through from seed_items so the anchor
            # loop below can tell "user explicitly asked for this
            # category" apart from "the AI/random picker happened to land
            # here" -- see extract_prompt_hints()/_ensure_hints_present()
            # in logic/ai_synthesizer.py.
            "_explicit_hint": bool(item.get("_explicit_hint")),
        })

    layer_to_category = {
        l: cat for cat, layers in zonal_metadata.items() for l in layers
    }

    # Guarantee every guideline category (SOFT/HARD/PROG/BLUE) has a placed
    # "anchor" layer with real, sizeable natural area -- otherwise
    # _solve_zonal_scales() below has nothing usable to scale for that
    # category and it can never reach its target %.
    #
    # Two separate problems confirmed by direct probing (2026-07-30,
    # _find_layer_group + _group_polygons/rasterize against every site in
    # PrecedentSVG/), and why this can't just check "does the AI/random pick
    # resolve at all":
    #  1. STREET, PEDESTRIAN_PATH, STREET_FURNITURE, PARKING, and
    #     UNIQUE_ELEMENTS don't exist as real geometry in ANY of the 5
    #     precedent SVGs at all -- a pick of one of these silently resolves
    #     to zero polygons downstream (rasterize_precedent_layers()'s own
    #     "layer id not found... silently skipped" tolerance).
    #  2. Even among layers that DO resolve, natural area varies wildly by
    #     site -- e.g. HARDSCAPE is ~76% of PershingSquare's site but <1% of
    #     ZaryadyePark's. A tiny natural polygon usually can't be scaled UP
    #     into a meaningful target range either: rasterize_precedent_layers()
    #     scales each layer around its SOURCE SITE's own boundary-bbox
    #     center, not the layer's own centroid, so an off-center sliver
    #     mostly translates away from the site as "scale" grows rather than
    #     growing in place, and collapses to 0% once it drifts off the
    #     placed grid (see _solve_zonal_scales()'s own docstring).
    # So this always resolves the single BEST-natural-area (layer, site)
    # combo per category (among a few near-best candidates, for variety) and
    # adds it as long as it isn't already exactly what's placed -- not just
    # "when the category is empty".
    for cat, layers in zonal_metadata.items():
        if not layers:
            continue
        # 2026-08-13: don't add a competing anchor for a category the user
        # already explicitly requested (via extract_prompt_hints) -- even
        # though this wouldn't overwrite their pick, appending a different
        # site's layer in the same category visually dilutes/competes with
        # what they specifically asked for. See composed's own
        # "_explicit_hint" field, set above.
        category_explicitly_requested = any(
            it.get("_explicit_hint") and layer_to_category.get(it["layerId"]) == cat
            for it in composed
        )
        if category_explicitly_requested:
            continue
        anchor = _best_area_anchor(layers, LAYER_SITE_MEMBERSHIP, valid_sites)
        if anchor is None:
            continue  # no real geometry backs this category at all
        anchor_layer, anchor_site = anchor
        already_present = any(
            it["layerId"] == anchor_layer and it["site"] == anchor_site
            for it in composed
        )
        if already_present:
            continue
        location = random.choice(list(LOCATION_OFFSETS.keys()))
        x_frac, y_frac = LOCATION_OFFSETS.get(location, (0.0, 0.0))
        composed.append({
            "site": anchor_site,
            "layerId": anchor_layer,
            "transform": {"x_frac": x_frac, "y_frac": y_frac, "scale": 1.0, "rot": 0},
            "opacity": 0.85,
            "target_width": 400,
            "target_height": 400,
            "primitive": primitives_map.get(anchor_layer, "box"),
        })

    # Fix up any attractor-marker item whose LOCATION alone (independent of
    # scale) would already place it outside the real site -- confirmed
    # 2026-07-30 this is a SEPARATE cause of markers landing off-site from
    # the scale issue _solve_zonal_scales()/_scale_keeps_markers_in_bounds()
    # below handles: translation (x_frac/y_frac) is applied on top of
    # scale/rotation (see ingest_diagram_svg.py's rasterize_precedent_
    # layers()/extract_attractor_points_from_composed_layers(): offset_x =
    # pcx + x_frac*pw), so a bad cardinal LOCATION choice can push a marker
    # off-site even at scale=1.0, before the scale solver ever runs. Must
    # happen BEFORE _solve_zonal_scales(), which only searches scale, not
    # location, and would otherwise be solving against an already-broken
    # position. Best-effort, same as the solver below.
    try:
        _pin_attractor_locations_in_bounds(composed, LOCATION_OFFSETS)
    except Exception as e:
        print(f"      -> [ATTRACTOR LOCATION FIX ERROR] {e}")

    # Solve each category's transform["scale"] against the real rasterizer
    # so this generation's actual coverage lands inside its guideline range
    # (see _solve_zonal_scales() docstring). Best-effort: if rasterization
    # fails for any reason (e.g. site geometry not calibrated in this
    # environment), fall back to the scale=1.0 already set on every item
    # above rather than breaking generation entirely.
    try:
        _solve_zonal_scales(composed, zonal_metadata, urban_guidelines, layer_to_category, LOCATION_OFFSETS)
    except Exception as e:
        print(f"      -> [ZONAL SCALE SOLVER ERROR] {e}")

    return composed


def _pin_attractor_locations_in_bounds(composed, location_offsets):
    """For every attractor-marker item (layerId containing "ATTRACTOR") in
    `composed`, re-pick its location (transform's x_frac/y_frac) if the
    CURRENT one would place any of its markers outside the real site
    bounds even at scale=1.0. Tries every location_offsets candidate
    (shuffled, for variety) and keeps the first that works; falls back to
    "Center" (always (0.0, 0.0), the safest option) if none do -- e.g. one
    marker within a multi-marker SVG group sits so far from the group's own
    center that no single translation keeps every marker in bounds at once.
    """
    import ingest_diagram_svg
    real_geometry = ingest_diagram_svg._load_real_geometry()
    width_ft = real_geometry["site"]["width_ft"]
    length_ft = real_geometry["site"]["length_ft"]

    def in_bounds(item):
        probe = {**item, "transform": {**item["transform"], "scale": 1.0}}
        pts = ingest_diagram_svg.extract_attractor_points_from_composed_layers([probe])
        all_pts = pts["major_attractor"] + pts["minor_attractor"] + pts["amphitheatre"]
        if not all_pts:
            return True  # didn't resolve -- not a bounds violation, nothing to fix here
        return all(0 <= p["x_ft"] <= width_ft and 0 <= p["y_ft"] <= length_ft for p in all_pts)

    for item in composed:
        if "ATTRACTOR" not in item["layerId"] or in_bounds(item):
            continue
        candidates = list(location_offsets.values())
        random.shuffle(candidates)
        for xf, yf in candidates:
            item["transform"]["x_frac"], item["transform"]["y_frac"] = xf, yf
            if in_bounds(item):
                break
        else:
            item["transform"]["x_frac"], item["transform"]["y_frac"] = location_offsets.get("Center", (0.0, 0.0))


def _fit_markers_at_scale(items, scale, location_offsets):
    """For every attractor-marker item (layerId containing "ATTRACTOR") in
    `items`, set its transform["scale"] to `scale` and, if that pushes its
    markers out of the real site bounds, try re-picking its LOCATION
    (x_frac/y_frac, mutated in place) until one keeps them in bounds at
    THIS scale. Returns True if every marker item ended up in-bounds (with
    a location fix-up if needed), False if at least one has no working
    location at this scale at all -- the caller should then treat `scale`
    as disqualified rather than leave a bad position applied. True
    immediately if `items` has no attractor-marker layer -- nothing to
    check for HARD/SOFT/BLUE, or for PROG's other member UNIQUE_ELEMENTS
    (never resolves to real geometry in any precedent SVG, confirmed
    separately).

    2026-07-30: re-fits location freshly PER CANDIDATE SCALE, rather than
    only disqualifying scales against whatever location was already picked
    once (at scale=1.0, before the scale sweep). A location that's safe at
    one scale isn't necessarily safe at another -- translation is applied
    on top of scale (rasterize_precedent_layers()/
    extract_attractor_points_from_composed_layers() both compute
    offset_x/offset_y = pcx/pcy + x_frac/y_frac * pw/ph, added AFTER the
    scaled/rotated polygon). Confirmed live: disqualifying against a fixed
    location left many higher scales disqualified that a different
    location would have made safe, which regressed PROG's measured
    coverage well below its target range (growing scale is PROG's only
    real lever, since its only resolving layers -- MAJOR_ATTRACTORS/
    MINOR_ATTRACTORS -- are exactly the attractor-marker layers this
    function is about).
    """
    marker_items = [it for it in items if "ATTRACTOR" in it["layerId"]]
    if not marker_items:
        return True
    import ingest_diagram_svg
    real_geometry = ingest_diagram_svg._load_real_geometry()
    width_ft = real_geometry["site"]["width_ft"]
    length_ft = real_geometry["site"]["length_ft"]

    def in_bounds(item):
        pts = ingest_diagram_svg.extract_attractor_points_from_composed_layers([item])
        all_pts = pts["major_attractor"] + pts["minor_attractor"] + pts["amphitheatre"]
        if not all_pts:
            return True
        return all(0 <= p["x_ft"] <= width_ft and 0 <= p["y_ft"] <= length_ft for p in all_pts)

    for item in marker_items:
        item["transform"]["scale"] = scale
        if in_bounds(item):
            continue
        candidates = list(location_offsets.values())
        random.shuffle(candidates)
        fixed = False
        for xf, yf in candidates:
            item["transform"]["x_frac"], item["transform"]["y_frac"] = xf, yf
            if in_bounds(item):
                fixed = True
                break
        if not fixed:
            return False
    return True


def _solve_zonal_scales(composed, zonal_metadata, guidelines, layer_to_category, location_offsets):
    """
    Binary-searches each guideline category's (SOFT/HARD/PROG/BLUE) shared
    transform["scale"] multiplier so the category's REAL rasterized
    voxel-grid coverage lands inside urban_design_guidelines.md's target
    range for this generation, mutating `composed` in place.

    Uses ingest_diagram_svg.rasterize_precedent_layers() itself as the
    measurement oracle rather than an area formula -- precedent-SVG layer
    shapes are irregular, so scale -> covered-area isn't analytically
    predictable. That function already applies
    final_scale = fit_scale * transform["scale"] on the same real NX/NZ
    voxel grid logic/pershing_api.py's spatialize_preview() measures
    against, so solving directly against it guarantees this matches what
    actually gets baked, not just a separate estimate of it.

    Filters out BOUNDARY items before measuring, matching
    spatialize_preview()'s own filter (`layerId != "BOUNDARY"`) -- otherwise
    a BOUNDARY pick would be counted here but silently dropped by the real
    bake path, desyncing the solved scale from the real measurement.

    Runs a few outer coordinate-descent passes over all categories rather
    than solving each once in isolation: categories can spatially overlap
    (e.g. the deliberate hardscape (cap) water "canyon rupture" in
    ingest_diagram_svg.apply_hardscape_water_overlap()), so adjusting one
    category's scale can shift another's measured coverage.
    """
    import ingest_diagram_svg

    items_by_cat = {}
    for item in composed:
        if item["layerId"] == "BOUNDARY":
            continue
        cat = layer_to_category.get(item["layerId"])
        if cat is not None:
            items_by_cat.setdefault(cat, []).append(item)

    if not items_by_cat:
        return

    # (target_fraction, roles-to-sum) per category. Sampled fresh within the
    # guideline range each call (rather than fixed to the range midpoint) so
    # repeated generations stay compliant without collapsing to one layout.
    targets = {}
    for cat, items in items_by_cat.items():
        roles = {_infer_raster_role(it["layerId"]) for it in items} & _RASTERIZABLE_ROLES
        if not roles:
            continue  # e.g. only a PEDESTRIAN_PATH pick landed here -- nothing to scale
        g = guidelines.get(cat)
        if not g:
            continue
        lo, hi = g.get("min", 0), g.get("max", 100)
        targets[cat] = (random.uniform(lo, hi) / 100.0, roles)

    if not targets:
        return

    # rasterize_precedent_layers() reads item["role"] to decide which
    # category_polygons_ft bucket a layer fills (skips it entirely if
    # missing/unrecognized -- see that function's own `role not in
    # category_polygons_ft: continue`); remix_layers()'s own composed items
    # never carry one (only logic/pershing_api.py's _compose_layers_to_3d()
    # attaches it, downstream of this function). Shallow copy so each
    # raster_item's "transform" dict is still the SAME object as the
    # corresponding composed item's -- mutating transform["scale"] below
    # must be visible through both.
    raster_items = [
        {**item, "role": _infer_raster_role(item["layerId"])}
        for item in composed if item["layerId"] != "BOUNDARY"
    ]

    def measure(roles):
        # Union (not sum) across a category's roles -- e.g. SOFT covers both
        # "trees" and "greenscape" grids, and a cell True in both must only
        # count once, or overlapping shade+greenspace would inflate SOFT's
        # measured % past what it physically represents.
        masks, _resolved = ingest_diagram_svg.rasterize_precedent_layers(raster_items, nx=None, nz=None)
        grids = [masks[r] for r in roles if r in masks]
        if not grids:
            return 0.0
        total_cells = sum(len(row) for row in grids[0])
        if not total_cells:
            return 0.0
        covered = sum(
            1
            for rows in zip(*grids)
            for cells in zip(*rows)
            if any(cells)
        )
        return covered / total_cells

    # Sweep candidate scales and keep whichever gets closest, rather than
    # bisecting on the assumption that coverage grows monotonically with
    # scale. It doesn't: rasterize_precedent_layers() scales each layer
    # around its SOURCE SITE's own boundary-bbox center, not the layer's own
    # centroid (same `scx, scy` used for every layer pulled from that site --
    # see ingest_diagram_svg.py:680). For a layer whose shape sits off that
    # center (most of them -- particularly the small MAJOR_ATTRACTORS/
    # MINOR_ATTRACTORS marker icons PROG relies on), growing "scale" mostly
    # translates it further from the site center rather than growing it in
    # place, so coverage can rise then collapse to 0% once it drifts off the
    # placed grid entirely. Confirmed empirically 2026-07-30: e.g.
    # MAJOR_ATTRACTORS/ParcVillette measured 6% at scale=1, 17% at 2.5, then
    # 0% at 6+. A bisection search would misinterpret that collapse as "too
    # big, shrink" and converge on the wrong side.
    SCALE_MIN, SCALE_MAX = 0.2, 4.0
    SWEEP_STEPS = 14
    OUTER_PASSES, TOLERANCE = 3, 0.01
    candidate_scales = [
        SCALE_MIN * (SCALE_MAX / SCALE_MIN) ** (i / (SWEEP_STEPS - 1))
        for i in range(SWEEP_STEPS)
    ]

    def _sweep_best(items, roles, target, scales):
        best_scale, best_diff = None, None
        best_locations = None
        for cand in scales:
            for item in items:
                item["transform"]["scale"] = cand
            if not _fit_markers_at_scale(items, cand, location_offsets):
                continue
            diff = abs(measure(roles) - target)
            if best_diff is None or diff < best_diff:
                best_diff, best_scale = diff, cand
                # _fit_markers_at_scale may have moved marker items to a
                # new (x_frac, y_frac) to make this scale work -- remember
                # it so the winning candidate keeps its safe position, not
                # whatever location a LATER (losing) candidate left behind.
                best_locations = {
                    id(it): (it["transform"]["x_frac"], it["transform"]["y_frac"])
                    for it in items if "ATTRACTOR" in it["layerId"]
                }
            if diff <= TOLERANCE:
                break
        if best_scale is None:
            # Every candidate would push a marker off-site with no working
            # location -- fall back to the safe, always-in-bounds scale=1.0
            # default rather than leaving a disqualified scale applied.
            best_scale = 1.0
            _fit_markers_at_scale(items, best_scale, location_offsets)
        else:
            for item in items:
                item["transform"]["scale"] = best_scale
            if best_locations:
                for item in items:
                    if id(item) in best_locations:
                        item["transform"]["x_frac"], item["transform"]["y_frac"] = best_locations[id(item)]
        return best_scale, best_diff

    for _pass in range(OUTER_PASSES):
        for cat, items in items_by_cat.items():
            if cat not in targets:
                continue
            target, roles = targets[cat]
            coarse_scale, coarse_diff = _sweep_best(items, roles, target, candidate_scales)
            if coarse_diff is not None and coarse_diff > TOLERANCE:
                # Zoom in: a finer sweep around the coarse winner, since the
                # 14-point log grid above can land a couple points short of
                # the guideline boundary even when a nearby scale would
                # clear it.
                lo = max(SCALE_MIN, coarse_scale * 0.7)
                hi = min(SCALE_MAX, coarse_scale * 1.3)
                fine_scales = [lo + (hi - lo) * i / 7 for i in range(8)]
                _sweep_best(items, roles, target, fine_scales)