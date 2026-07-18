"""
Memory Machine -- Terracing Engine ("Metabolizer v2" Adaptive Canyon Step Generator).

Ports the voxel-based canyon-terracing math out of
PershingMetabolizer_Prototype/index.html (client-side Three.js visualization
only, no server-side output) into a standalone, headless Python module so the
same depth field can feed a vector-export pipeline, not just a browser.

Scope: this module owns the *excavation depth* logic -- scoring each voxel's
transit/amenity-deficit influence, converting that into a stepped Z depth
capped at a real structural anchor's depth, then relaxing adjacent voxels so
no floating unsupported step exists. Sun/shade shadow-casting is a separate
concern (a data *layer*, not excavation geometry) and is not ported here.

Column keep-out-zone logic is intentionally absent: per project decision,
real columns are NOT protected from the cut -- a column can sit over an
excavated voxel with nothing under it. Ramp-void avoidance (an earlier hard
exclusion zone around the spiral ramps) was removed 2026-07-06 -- per
project decision, the canyon can now cut through/near ramp zones too, same
as everywhere else.
"""
import json
import math
import os
from dataclasses import dataclass, field

# Shared kind registry (2026-07-10 consolidation pass) -- single source of
# truth for every element kind's plan-footprint dims, viewport color, shape
# category, and material family, replacing three independently hand-
# maintained copies (this module's own MATERIAL_FAMILY/CUT_SHEET_
# PROTOTYPE_DIMS_FT, blender_cockpit.py's _PROTOTYPE_DIMS_FT/
# _VERTICAL_CYLINDER_KINDS/_HEX_KINDS, and Viewport.jsx's PROTOTYPE_DIMS_FT/
# KIND_COLOR/VERTICAL_CYLINDER_KINDS/HEX_KINDS) that had already drifted --
# blender_cockpit.py never picked up circulation_network.py's footpath/ramp/
# escalator kinds or the typology tree/building_mass kinds. Lives under
# frontend/src/ so Vite can import it directly as a build-time JSON asset;
# Python has no such restriction, so this module (and blender_cockpit.py)
# just read the same file from disk.
_KIND_REGISTRY_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "frontend", "src", "kindRegistry.json")
with open(_KIND_REGISTRY_PATH) as _f:
    KIND_REGISTRY = json.load(_f)


def clamp01(v):
    return max(0.0, min(1.0, v))


@dataclass
class Voxel:
    gx: int
    gy: int
    wx: float
    wy: float
    transit_influence: float
    deficit_influence: float
    foot_traffic_influence: float = 0.0
    noise_influence: float = 0.0
    sketch_weight: float = 0.0
    is_hardscape: bool = False
    is_water: bool = False
    is_tree: bool = False
    is_greenscape: bool = False
    is_amenity_resting: bool = False
    is_deck: bool = False
    z_ft: float = 0.0
    score: float = 0.0
    level: int = 0
    typology: str = None


# Default deficit hotspots ported from index.html's DEFICIT_HOTSPOTS -- an
# explicitly diagrammatic/placeholder amenity-deficit input (west/Olive St
# edge) pending real Section 2 data ingestion. Pass real hotspots in once
# that pipeline exists; these are only a stand-in default.
DEFAULT_DEFICIT_HOTSPOTS = [
    {"x_frac": 0.04, "y_frac": 0.65, "strength": 1.0, "radius_ft": 67.5},
    {"x_frac": 0.04, "y_frac": 0.30, "strength": 0.6, "radius_ft": 54.0},
]

# Same shape and same "diagrammatic placeholder, not real data" status as
# DEFAULT_DEFICIT_HOTSPOTS above -- pending real foot-traffic data (survey
# counters, mobility export, etc.) via foot_traffic.py's CSV loader. These
# two points are just a stand-in near a plausible plaza entry so the
# CIRCULATION classification has something non-trivial to show before real
# data exists.
#
# The first point stands in for real Metro ridership at the site's actual
# station entrance (real_geometry["secondary_entrance_anchor"]) -- checked
# 2026-07-09 whether a real station-level boarding count could replace this:
# Metro's own ArcGIS ridership portal requires SSO login, the public
# Streets-for-All alternative dashboard (ridership.streetsforall.org) is
# line-level only (no per-station breakdown), and LACMTA's public GitHub
# open-data repo has no ridership dataset at all. No real number is
# publicly accessible right now -- do not treat this strength value as a
# real ridership figure. Once a real number is obtained (direct Metro
# contact/public-records request), it drops in via foot_traffic.py's CSV
# path with zero code changes.
DEFAULT_FOOT_TRAFFIC_HOTSPOTS = [
    {"x_frac": 0.5, "y_frac": 0.08, "strength": 1.0, "radius_ft": 60.0},
    {"x_frac": 0.5, "y_frac": 0.92, "strength": 0.7, "radius_ft": 60.0},
]

# Same "diagrammatic placeholder, not real data" status as the two above --
# pending real noise data (acoustic sensor export, or a proxy like measured
# traffic volume) via noise_survey.py's CSV loader. Placed along the site's
# two long, street-facing edges (x_frac near 0 and 1, spanning the length
# axis) -- the same edges circulation_network.py's multi-root growth (2026-
# 07-12) treats as real pedestrian/street entries, so "louder near the
# street frontage, quieter toward the interior" is the same directional
# assumption already made elsewhere in this codebase, not a new one
# invented just for this placeholder.
DEFAULT_NOISE_HOTSPOTS = [
    {"x_frac": 0.02, "y_frac": 0.5, "strength": 0.8, "radius_ft": 90.0},
    {"x_frac": 0.98, "y_frac": 0.5, "strength": 0.8, "radius_ft": 90.0},
]

# _classify_typology's SANCTUARY check: a cell painted greenscape+
# amenity_resting only keeps SANCTUARY status if noise_influence * data_alpha
# stays below this -- not a UI-exposed slider (data_alpha already is; this
# is the fixed "how quiet counts as quiet" cutoff), same pattern as
# FIELD_ATTRACTOR_THRESHOLD in circulation_network.py.
SANCTUARY_NOISE_THRESHOLD = 0.5

# Depth-below-grade thresholds (ft) for the Botanical Attractor Module's
# level tagging (Section 3): Level 0 = surface/shade canopy zone, -1 =
# terraced planters, -2/-3 = deep canyon / structural sub-vault zone.
DEFAULT_LEVEL_DEPTH_THRESHOLDS_FT = (0.0, 10.0, 20.0, 40.0)


class TerracingEngine:
    """
    Computes a stepped excavation depth field over a site's structural
    footprint, driven by a transit-attractor anchor (real, from
    real_geometry.json) and amenity-deficit hotspots (placeholder pending
    Section 2). Site dimensions and column positions come from
    real_geometry (see extract_real_geometry.py) -- nothing here is
    Pershing-specific beyond the values already baked into that JSON.
    """

    def __init__(self, real_geometry, deficit_hotspots=None, foot_traffic_hotspots=None,
                 noise_hotspots=None, data_alpha=1.0, voxel_ft=9.0,
                 transit_falloff_ft=220.0, threshold=0.35, step_ft=9.0,
                 max_canyon_depth_ft=None,
                 level_depth_thresholds_ft=DEFAULT_LEVEL_DEPTH_THRESHOLDS_FT,
                 sketch_weights=None, sketch_alpha=0.75, deficit_alpha=1.0, hardscape_regions=None,
                 water_regions=None, tree_regions=None, greenscape_regions=None, amenity_resting_regions=None,
                 deck_regions=None,
                 circulation_threshold=0.35, remove_top_slab=False):
        self.real_geometry = real_geometry
        self.voxel_ft = voxel_ft
        # 2026-07-13 "remove top slab" feature: forces a minimum one-step
        # excavation depth everywhere except an explicitly painted DECK
        # region -- see _z_for_voxel. Deliberately a coarse, single-step
        # force, not an attempt to precisely target a specific real slab's
        # elevation from in here: StructuralFramingEngine's
        # real_slab_fragments()/classify_terrain_cells() (which run AFTER
        # this engine finishes, with full real-slab awareness) already
        # correctly derive "what's actually exposed now" from whatever z_ft
        # ends up here -- this constructor has no need to duplicate that
        # logic, just to guarantee the topmost (SURFACE) slab's elevation is
        # reliably cleared.
        #
        # Deliberately NOT gated on is_hardscape (2026-07-13 decouple):
        # hardscape paint also drives program_placement.py's scoring for
        # sports_recreation/outdoor programs, which actively SEEKS OUT
        # hardscape-painted cells -- if hardscape also protected from this
        # forced dig, sports programs would be systematically pulled toward
        # the exact cells "remove top slab" is supposed to clear (confirmed
        # live: 2026-07-13, Soccer Field landed a 103-bay zone entirely on
        # hardscape-protected grade). deck_regions is a separate paint
        # category (BakeGrids.deck) specifically for "keep this as an
        # access deck when the top slab comes off" -- unrelated to whether
        # that cell also happens to be a scored sports surface.
        self.remove_top_slab = remove_top_slab
        # Blend weight for noise_hotspots' effect on SANCTUARY classification
        # only (see SANCTUARY_NOISE_THRESHOLD) -- does NOT touch excavation
        # depth/_effective_influence, unlike sketch_alpha. 0 = noise data
        # never overrides painted intent (designer-dominant, matches
        # sketch_alpha's own default framing); 1 = full data-driven effect.
        self.data_alpha = data_alpha
        self.transit_falloff_ft = transit_falloff_ft
        self.threshold = threshold
        self.step_ft = step_ft
        # Hard structural cap on general canyon excavation, independent of
        # entrance_base_depth_ft (below) -- per 2026-07-05 finding, the real
        # columns are only 30ft tall (real_geometry["column_height_ft"]) and
        # terminate on shallow footings at Subfloor 3, so no voxel anywhere
        # may excavate deeper than that regardless of transit/deficit score,
        # or columns end up floating past their real unbraced-length limit.
        # Defaults to the real measured column height, not a bare literal.
        self.max_canyon_depth_ft = (
            max_canyon_depth_ft if max_canyon_depth_ft is not None
            else real_geometry.get("column_height_ft", 30.0)
        )
        self.level_depth_thresholds_ft = level_depth_thresholds_ft
        # sketch_weights: optional (nx, nz) array/grid of designer-sketch
        # weights (see sketch_weight_mapper.py), 0..1, ADDITIVELY blended
        # with the data-driven transit_influence -- per project decision
        # 2026-07-03, the sketch can create real excavation somewhere the
        # data alone wouldn't (not just mask/suppress it). sketch_alpha
        # defaults sketch-dominant (0.75), not an even 50/50 blend.
        self.sketch_weights = sketch_weights
        self.sketch_alpha = sketch_alpha
        # 2026-07-17 demand-driven excavation: deficit_influence (real
        # neighborhood program-deficit hotspots, see __init__'s
        # deficit_hotspots param) additively blended into _effective_
        # influence alongside transit_influence -- same "designer/data-
        # dominant" framing sketch_alpha/data_alpha already use. Previously
        # deficit_influence had ZERO effect on excavation depth (only
        # entered score_for_phase, a separate placement/typology signal) --
        # confirmed live 2026-07-17 this was the actual missing piece
        # behind "programming doesn't reach below-grade" (excavation was
        # ~85ft-radius/9ft-deep at default slider values, entrance-
        # proximity-only). Defaults co-equal with transit_influence (1.0),
        # not a secondary nudge -- real programmatic need should carve the
        # site as much as transit convenience does.
        self.deficit_alpha = deficit_alpha
        # hardscape_regions: optional list of {"mask": (nx, nz) bool array}
        # dicts, e.g. straight from sketch_weight_mapper.build_hardscape_regions().
        # Unlike sketch_weights (additive, can CREATE excavation), a hardscape
        # region is a hard veto -- "protect this, no matter what the transit/
        # deficit/sketch score says". Deliberately NOT folded into the
        # additive sketch_weight stack; see _z_for_voxel / _relax_depths.
        self.hardscape_regions = hardscape_regions or []
        # Programmatic Typology Mixing Engine inputs (New Feature Directives
        # section 4): same {"mask": (nx, nz) bool grid} OR-list shape as
        # hardscape_regions, but these never appear in _z_for_voxel -- they
        # only feed _classify_typology below, purely a post-process asset
        # decoration layer on top of whatever depth the real excavation math
        # already produced.
        #
        # water_regions/tree_regions (2026-07-11 split, renamed from "shade"
        # to "trees" 2026-07-16): previously one combined water_shade_regions
        # -- split because circulation_network.py's motivator system already
        # treated "trees" (nee "shade") and "water" as distinct weighted
        # attractors, but derived them asymmetrically from the one upstream
        # mask (trees read the raw mask directly, water only came from
        # already-excavated GROTTO props) -- see that module's
        # sample_attraction_points for the fix on that side. tree_regions
        # drives TypologyAssetEngine.tree_specs() directly -- painting this
        # category always meant "put trees here" (see that method below),
        # the field/category name just didn't say so until this rename.
        # Replaces the old is_greenscape-driven placement -- greenscape is
        # pure grass now, see that method below.
        self.water_regions = water_regions or []
        self.tree_regions = tree_regions or []
        self.greenscape_regions = greenscape_regions or []
        self.amenity_resting_regions = amenity_resting_regions or []
        # Deck-survival paint (2026-07-13) -- see __init__'s remove_top_slab
        # comment above for why this is deliberately separate from
        # hardscape_regions rather than reusing it.
        self.deck_regions = deck_regions or []
        # Threshold for _classify_typology's CIRCULATION check below --
        # independent of self.threshold (which gates excavation depth)
        # despite sharing the same default value; unverifiable/cosmetic
        # until real foot-traffic data exists (see DEFAULT_FOOT_TRAFFIC_HOTSPOTS).
        self.circulation_threshold = circulation_threshold

        self.site_width_ft = real_geometry["site"]["width_ft"]
        self.site_length_ft = real_geometry["site"]["length_ft"]
        self.nx = math.ceil(self.site_width_ft / voxel_ft)
        self.nz = math.ceil(self.site_length_ft / voxel_ft)

        anchor = real_geometry["secondary_entrance_anchor"]
        self.entrance_x = anchor["x"]
        self.entrance_y = anchor["z"]
        # Real, informational depth of the entrance/tunnel anchor itself --
        # NOT used to scale or cap general canyon excavation (that's
        # max_canyon_depth_ft above). Kept for anyone placing the entrance's
        # own context mesh, which legitimately runs deeper than the garage
        # (a real transit tunnel, not open canyon void).
        self.entrance_base_depth_ft = anchor["bottom_depth_ft"]

        if deficit_hotspots is None:
            deficit_hotspots = [
                {
                    "x": h["x_frac"] * self.site_width_ft,
                    "y": h["y_frac"] * self.site_length_ft,
                    "strength": h["strength"],
                    "radius": h["radius_ft"],
                }
                for h in DEFAULT_DEFICIT_HOTSPOTS
            ]
        self.deficit_hotspots = deficit_hotspots

        if foot_traffic_hotspots is None:
            foot_traffic_hotspots = [
                {
                    "x": h["x_frac"] * self.site_width_ft,
                    "y": h["y_frac"] * self.site_length_ft,
                    "strength": h["strength"],
                    "radius": h["radius_ft"],
                }
                for h in DEFAULT_FOOT_TRAFFIC_HOTSPOTS
            ]
        self.foot_traffic_hotspots = foot_traffic_hotspots

        if noise_hotspots is None:
            noise_hotspots = [
                {
                    "x": h["x_frac"] * self.site_width_ft,
                    "y": h["y_frac"] * self.site_length_ft,
                    "strength": h["strength"],
                    "radius": h["radius_ft"],
                }
                for h in DEFAULT_NOISE_HOTSPOTS
            ]
        self.noise_hotspots = noise_hotspots

        self.voxels = self._build_base_voxels()

    def _build_base_voxels(self):
        voxels = []
        for gx in range(self.nx):
            row = []
            for gy in range(self.nz):
                wx = (gx + 0.5) * self.voxel_ft
                wy = (gy + 0.5) * self.voxel_ft

                entrance_dist = math.hypot(wx - self.entrance_x, wy - self.entrance_y)
                transit_influence = math.exp(-entrance_dist / self.transit_falloff_ft)

                deficit_influence = 0.0
                for h in self.deficit_hotspots:
                    d = math.hypot(wx - h["x"], wy - h["y"])
                    deficit_influence += h["strength"] * math.exp(-d / h["radius"])
                deficit_influence = clamp01(deficit_influence)

                # Independent of deficit_influence -- a separate real-data
                # channel (foot traffic vs. amenity deficit), not folded
                # together despite the identical summed-falloff shape. Not
                # used anywhere in the excavation-depth math (_effective_influence/
                # _z_for_voxel/score_for_phase); it only feeds
                # _classify_typology's CIRCULATION check below.
                foot_traffic_influence = 0.0
                for h in self.foot_traffic_hotspots:
                    d = math.hypot(wx - h["x"], wy - h["y"])
                    foot_traffic_influence += h["strength"] * math.exp(-d / h["radius"])
                foot_traffic_influence = clamp01(foot_traffic_influence)

                # Independent of the two above too -- only ever read by
                # _classify_typology's SANCTUARY check, scaled by
                # self.data_alpha. See noise_survey.py's module docstring.
                noise_influence = 0.0
                for h in self.noise_hotspots:
                    d = math.hypot(wx - h["x"], wy - h["y"])
                    noise_influence += h["strength"] * math.exp(-d / h["radius"])
                noise_influence = clamp01(noise_influence)

                sketch_weight = 0.0
                if self.sketch_weights is not None:
                    sketch_weight = float(self.sketch_weights[gx][gy])

                is_hardscape = any(region["mask"][gx][gy] for region in self.hardscape_regions)
                is_water = any(region["mask"][gx][gy] for region in self.water_regions)
                is_tree = any(region["mask"][gx][gy] for region in self.tree_regions)
                is_greenscape = any(region["mask"][gx][gy] for region in self.greenscape_regions)
                is_amenity_resting = any(region["mask"][gx][gy] for region in self.amenity_resting_regions)
                is_deck = any(region["mask"][gx][gy] for region in self.deck_regions)

                row.append(Voxel(
                    gx=gx, gy=gy, wx=wx, wy=wy,
                    transit_influence=transit_influence,
                    deficit_influence=deficit_influence,
                    foot_traffic_influence=foot_traffic_influence,
                    noise_influence=noise_influence,
                    sketch_weight=sketch_weight,
                    is_hardscape=is_hardscape,
                    is_water=is_water,
                    is_tree=is_tree,
                    is_greenscape=is_greenscape,
                    is_amenity_resting=is_amenity_resting,
                    is_deck=is_deck,
                ))
            voxels.append(row)
        return voxels

    def _flat_voxels(self):
        return [v for row in self.voxels for v in row]

    def _effective_influence(self, v):
        """
        transit_influence, additively boosted by real programmatic deficit
        (deficit_alpha * v.deficit_influence, 2026-07-17) and the
        designer's sketch weight (if any). This is the one place both
        depth (_z_for_voxel) and score (score_for_phase) read "how much
        does this cell want to excavate" -- keeping the two consistent by
        construction.

        Literal addition, not a weighted average -- v.sketch_weight == 0
        (nowhere near a sketched line, i.e. most of the site) must leave
        transit_influence completely unchanged, or the sketch would dampen
        the data-driven excavation everywhere it wasn't drawn, not just add
        to where it was. (An earlier version used
        alpha*sketch + (1-alpha)*transit -- that's an interpolation between
        two full fields, and wiped out the real entrance-driven excavation
        everywhere the sketch was blank. Caught by testing before/after
        against real data, not assumed correct.) Same reasoning applies to
        deficit_influence -- it's added on top, never blended down, so a
        cell far from any deficit hotspot keeps its full transit-driven
        excavation unchanged.
        """
        influence = v.transit_influence + self.deficit_alpha * v.deficit_influence
        if self.sketch_weights is not None:
            influence += self.sketch_alpha * v.sketch_weight
        return clamp01(influence)

    def score_for_phase(self, v, phase):
        if phase == 1:
            return 0.0
        if phase == 2:
            return v.deficit_influence
        return clamp01(self._effective_influence(v) + v.deficit_influence)

    def _z_for_voxel(self, v, phase):
        # 2026-07-13 decouple: which veto applies depends on remove_top_slab.
        # Normal dig (off) -- hardscape paint protects, exactly as always.
        # remove_top_slab (on) -- hardscape paint does NOT protect (it also
        # drives program_placement.py's sports_recreation/outdoor scoring,
        # which actively seeks out hardscape-painted cells -- letting it
        # also veto excavation here would systematically pull those
        # programs toward the cells this toggle exists to clear). Only an
        # explicitly painted deck region (v.is_deck, a separate paint
        # category) can keep a cell at grade once this toggle is on.
        if self.remove_top_slab:
            if v.is_deck:
                return 0.0  # explicitly preserved deck -- separate signal from hardscape
        elif v.is_hardscape:
            return 0.0  # designer-protected region -- veto wins regardless of score
        if phase != 3 or self._effective_influence(v) <= self.threshold:
            # Below the normal excavation threshold -- would ordinarily stay
            # at grade (0.0), but "remove top slab" still forces a minimum
            # one-step cut here too, or every low-score cell (most of the
            # site, away from the transit/deficit attractors) would keep the
            # SURFACE slab intact regardless of the toggle.
            return -self.step_ft if self.remove_top_slab else 0.0
        raw_depth = self._effective_influence(v) * self.max_canyon_depth_ft
        z = -round(raw_depth / self.step_ft) * self.step_ft
        if self.remove_top_slab:
            z = min(z, -self.step_ft)  # at least one step deep, deeper if the score already says so
        return z

    def _relax_depths(self, phase):
        flat = self._flat_voxels()
        nx, nz = self.nx, self.nz
        cur = [v.z_ft for v in flat]
        max_iter = math.ceil(self.max_canyon_depth_ft / self.step_ft) + 2

        def idx(gx, gy):
            return gx * nz + gy

        for _ in range(max_iter):
            nxt = cur[:]
            changed = False
            for gx in range(nx):
                for gy in range(nz):
                    i = idx(gx, gy)
                    # Same remove_top_slab-dependent veto swap as
                    # _z_for_voxel above -- keep the two in lockstep, or a
                    # cell could get correctly excavated by _z_for_voxel but
                    # then get pinned back up to grade by relaxation reading
                    # the wrong veto.
                    if self.remove_top_slab:
                        if flat[i].is_deck:
                            continue  # pinned at grade -- explicitly preserved deck
                    elif flat[i].is_hardscape:
                        continue  # pinned at grade -- designer-protected region
                    max_neighbor = None
                    for ngx, ngy in ((gx - 1, gy), (gx + 1, gy), (gx, gy - 1), (gx, gy + 1)):
                        if 0 <= ngx < nx and 0 <= ngy < nz:
                            nz_val = cur[idx(ngx, ngy)]
                            if max_neighbor is None or nz_val > max_neighbor:
                                max_neighbor = nz_val
                    if max_neighbor is None:
                        continue
                    floor = max_neighbor - self.step_ft
                    if cur[i] < floor:
                        nxt[i] = floor
                        changed = True
            cur = nxt
            if not changed:
                break

        for v, z in zip(flat, cur):
            v.z_ft = z

    def _classify_typology(self, v):
        """
        Programmatic Typology Mixing Engine (New Feature Directives section
        4). GROTTO requires the voxel to actually be excavated (z_ft < 0) --
        water cascades and misting along real structural columns only make
        sense standing in an actual void, not a flat, undug cell that merely
        happens to be painted Canyon+Water (confirmed 2026-07-05: this
        is a post-process classification over the already-computed terrace,
        not a new input to the depth formula). Reads is_water only (2026-07-11
        split, was is_water_shade) -- painting Trees alone over an excavated
        cell no longer implies a grotto, since that paint category's own
        semantics are "trees go here" (see TypologyAssetEngine.tree_specs). SANCTUARY is
        paint-only -- Greenscape and Amenity/Resting can both sit at grade,
        unrelated to excavation depth. CIRCULATION is checked last, after
        GROTTO/SANCTUARY -- existing classifications win outright if a cell
        happens to be painted both ways, no new priority system needed
        (foot-traffic data driving CIRCULATION is independent of the
        water/trees/greenscape/amenity_resting masks the other two read).

        SANCTUARY additionally requires real-world quiet (2026-07-12): a
        cell painted greenscape+amenity_resting only keeps SANCTUARY status
        if noise_influence * self.data_alpha stays below
        SANCTUARY_NOISE_THRESHOLD -- data_alpha=0 means noise data never
        overrides painted intent, same "designer-dominant unless told
        otherwise" framing sketch_alpha already uses (RebuildParams
        defaults data_alpha to 1.0, full data-driven effect, but a caller
        can zero it). A loud real-world spot that fails this check simply
        isn't SANCTUARY -- it falls through to the CIRCULATION check below
        like any other cell, not a third typology.
        """
        if v.z_ft < 0 and v.is_water:
            return "GROTTO"
        if (v.is_greenscape and v.is_amenity_resting
                and v.noise_influence * self.data_alpha < SANCTUARY_NOISE_THRESHOLD):
            return "SANCTUARY"
        if v.is_hardscape and v.foot_traffic_influence >= self.circulation_threshold:
            return "CIRCULATION"
        return None

    def _tag_levels(self, v):
        depth = -v.z_ft  # z_ft is negative-down; depth is positive-down
        thresholds = self.level_depth_thresholds_ft
        level = 0
        for i, t in enumerate(thresholds):
            if depth > t:
                level = -i
        return level

    def run(self, phase=3):
        """
        Compute score/depth/level for every voxel at the given phase (1 =
        baseline/no excavation, 2 = deficit heat only, 3 = deficit + transit
        attractor with real stepped depth). Returns the flat voxel list.
        """
        for v in self._flat_voxels():
            v.z_ft = 0.0
        if phase == 3:
            for v in self._flat_voxels():
                v.z_ft = self._z_for_voxel(v, phase)
            self._relax_depths(phase)
        for v in self._flat_voxels():
            v.score = self.score_for_phase(v, phase)
            v.level = self._tag_levels(v) if phase == 3 else 0
            v.typology = self._classify_typology(v) if phase == 3 else None
        return self._flat_voxels()


# Normal-weight structural concrete, lb/ft^3 -- standard engineering value,
# used for the Slab Harvest tonnage readout below.
CONCRETE_UNIT_WEIGHT_PCF = 150.0
STRUCTURAL_BAY_FT = 27.0
RETAINING_BLOCK_THICKNESS_FT = 8.0 / 12.0  # diamond wire-sawn plate, not a solid cube
RUNNING_BOND_STAGGER_FT = 1.5              # half a 3ft block width, alternating courses

# STEEL mode tectonics (Hyper-Realistic Structural Connections supplement,
# 2026-07-05): a collar is not a beam just touching a column, it's a split
# sleeve that wraps the real column and extends past the real cut line.
COLLAR_EXTENSION_FT = 1.75          # 1.5-2ft above/below the slab cut line
COLLAR_FLANGE_OFFSET_FT = 0.5 / 12.0  # 0.5" flange standoff for the bolt ring
COLLAR_BOLT_COUNT = 8
COLLAR_BOLT_RADIUS_FT = 0.1
STRUT_PIPE_RADIUS_FT = 0.75
GUSSET_PLATE_DIMS_FT = (1.5, 0.1, 1.5)
BOLT_FLANGE_RADIUS_FT = 0.9
BOLT_FLANGE_THICKNESS_FT = 0.15
TIE_ROD_RADIUS_FT = 0.15
TURNBUCKLE_RADIUS_FT = 0.3
TURNBUCKLE_LENGTH_FT = 1.5

# WOOD mode tectonics
KNEE_BRACE_OFFSET_FT = 1.75   # 1.5-2ft off the post/beam corner, both legs
KNEE_BRACE_RADIUS_FT = 0.25
TIMBER_BEAM_RADIUS_FT = 0.5   # ~12in heavy-timber beam, rendered as a round member like the steel struts
POST_PACK_THRESHOLD_LEVELS = 3   # depth (levels) at which posts start clustering
POST_PACK_SPACING_FT = 1.1
STRAP_BAND_HEIGHT_FT = 0.3
FOOTING_SHOE_HEIGHT_FT = 1.0


@dataclass
class BayCell:
    """One cell of the 27ft structural bay grid -- coarser than
    TerracingEngine's voxel grid (STRUCTURAL_BAY_FT == 3 * the default 9ft
    voxel_ft, the same 3-voxels-per-bay relationship circulation_network.py
    calls BUCKET_VOXELS). Built by build_bay_grid() below, which extracts
    what used to be StructuralFramingEngine._column_grid()'s private,
    on-demand, sparse (column-occupied bays only) dict into a real, reusable,
    densely-populated structure -- every bay in the site gets an entry, not
    just the ones a real column happens to round into -- so callers (e.g.
    logic/program_placement.py's bay-grid placement engine) can walk the
    whole site without re-deriving bay geometry themselves."""
    gx: int
    gy: int
    x_ft: float  # bay center, real_geometry's x axis (site width)
    z_ft: float  # bay center, real_geometry's z axis (site length) -- matches
                 # real_columns' own "x"/"z" naming, not TerracingEngine's wx/wy
    column_id: str = None
    is_buildable: bool = True  # False if a real column occupies this bay


def build_bay_grid(real_geometry):
    """
    Returns (grid, nx_bays, nz_bays): a dense dict of every (gx, gy) bay in
    the site's structural grid -> BayCell, keyed the same way
    StructuralFramingEngine._column_grid() keys its own private dict
    (round(col_x / STRUCTURAL_BAY_FT)). nz_bays is computed here for the
    first time -- previously only NX_BAYS existed anywhere in the codebase
    (an ad hoc scalar in logic/pershing_api.py/blender_cockpit.py, for UI
    slider bounds only), with no equivalent depth-axis count.

    Real columns that round to a bay index just outside [0, nx_bays) /
    [0, nz_bays) (the site's own dimensions aren't always an exact multiple
    of STRUCTURAL_BAY_FT) are clamped into range rather than dropped, so
    every real column still marks some bay non-buildable.
    """
    width_ft = real_geometry["site"]["width_ft"]
    length_ft = real_geometry["site"]["length_ft"]
    nx_bays = max(1, round(width_ft / STRUCTURAL_BAY_FT))
    nz_bays = max(1, round(length_ft / STRUCTURAL_BAY_FT))

    grid = {}
    for gx in range(nx_bays):
        for gy in range(nz_bays):
            grid[(gx, gy)] = BayCell(
                gx=gx, gy=gy,
                x_ft=(gx + 0.5) * STRUCTURAL_BAY_FT,
                z_ft=(gy + 0.5) * STRUCTURAL_BAY_FT,
            )

    columns = real_geometry.get("real_columns") or real_geometry.get("column_positions") or []
    for col in columns:
        gx = min(max(round(col["x"] / STRUCTURAL_BAY_FT), 0), nx_bays - 1)
        gy = min(max(round(col["z"] / STRUCTURAL_BAY_FT), 0), nz_bays - 1)
        cell = grid[(gx, gy)]
        cell.column_id = col.get("id", f"{gx}_{gy}")
        cell.is_buildable = False

    return grid, nx_bays, nz_bays


def voxel_attr_grid(voxels, nx, nz, attr):
    """Build a dense (nx, nz) list-of-lists from a flat Voxel list (as
    returned by TerracingEngine._flat_voxels()/run()), reading one numeric
    or bool attribute per cell. Feeds aggregate_grid_to_bays below -- that
    function needs a dense nx*nz grid, but TerracingEngine only exposes a
    flat list of Voxel objects with their own .gx/.gy indices."""
    out = [[0.0] * nz for _ in range(nx)]
    for v in voxels:
        out[v.gx][v.gy] = getattr(v, attr)
    return out


def aggregate_grid_to_bays(grid, nx_bays, nz_bays, bays_per_side=3):
    """
    Downsample a dense (nx, nz) voxel-resolution grid (list-of-lists of bool
    or float, TerracingEngine's own gx/gy indexing -- either a raw painted
    mask like GREENSCAPE_MASK, or voxel_attr_grid()'s output) into a coarser
    (nx_bays, nz_bays) grid of per-bay averages, by averaging each bay's
    bays_per_side x bays_per_side block of voxels. bays_per_side=3 is the
    real relationship at this site's default voxel_ft=9.0 (STRUCTURAL_BAY_FT
    / voxel_ft == 3, see circulation_network.py's BUCKET_VOXELS) -- pass a
    different value only if voxel_ft is overridden elsewhere.

    A bool grid averages to a 0..1 "true fraction" per bay; a float grid
    (e.g. transit_influence/deficit_influence) averages to a plain mean.
    Voxel indices that fall outside the source grid's own bounds (site
    dimensions aren't always an exact multiple of bays_per_side * voxel_ft)
    are skipped, not zero-padded, so a partial edge bay's average isn't
    dragged down by phantom cells.
    """
    nx = len(grid)
    nz = len(grid[0]) if nx else 0
    out = [[0.0] * nz_bays for _ in range(nx_bays)]
    for bx in range(nx_bays):
        for bz in range(nz_bays):
            total = 0.0
            count = 0
            for dx in range(bays_per_side):
                gx = bx * bays_per_side + dx
                if gx >= nx:
                    continue
                for dz in range(bays_per_side):
                    gz = bz * bays_per_side + dz
                    if gz >= nz:
                        continue
                    total += float(grid[gx][gz])
                    count += 1
            out[bx][bz] = total / count if count else 0.0
    return out


@dataclass
class StructuralElement:
    """One procedurally-placed structural/salvage instance -- kind selects
    which prototype mesh blender_cockpit.py instances (linked mesh data, not
    a unique mesh per element, so viewport stays responsive while sliders
    are dragged -- see New Feature Directives section 4).

    x2/y2/z2/radius_ft are optional: set together, they mean "instance a real
    cylinder between (x,y,z_top) and (x2,y2,z2)" -- struts, tie-rods, and knee
    braces are true two-point diagonals, not a single rotated box guessing at
    the angle (see Hyper-Realistic Structural Connections supplement).

    scale_y is optional and only meaningful for box-shaped kinds: None (the
    default, used by every existing kind) means "scale both plan axes by
    `scale` uniformly," the original behavior. Set it alongside `scale` only
    when a kind genuinely needs an independent width vs. depth (e.g.
    BuildingMassEngine's rectangular footprints) -- everything else keeps
    scaling isotropically.

    column_id/column_id2/slab_id (added 2026-07-09, real-slab-graph
    supplement): which real column(s) (real_geometry["real_columns"][i]["id"])
    and real floor slab (real_geometry["real_slabs"][i]["parent"]) this
    element is actually attached to -- column_id2 only set for two-column
    members (struts/tie-rods bridging a pair). None for elements that aren't
    part of the column/slab load path (bolts, gussets, amenities, etc --
    those inherit their parent member's attachment implicitly, not tagged
    separately, per the plan's decision to tag the load-bearing members
    themselves rather than every piece of hardware)."""
    kind: str
    x_ft: float
    y_ft: float
    z_top_ft: float
    height_ft: float
    scale: float = 1.0
    rotation_deg: float = 0.0
    x2_ft: float = None
    y2_ft: float = None
    z2_ft: float = None
    radius_ft: float = None
    scale_y: float = None
    column_id: str = None
    column_id2: str = None
    slab_id: str = None
    # Which network root a circulation_network.py path segment traces back
    # to -- "metro_entrance" (the one real, surveyed entry) vs "site_edge"
    # (fabricated-but-plausible boundary entries, added 2026-07-12 so the
    # network isn't single-rooted). None for every non-network-path kind.
    source: str = None
    # Unit surface-normal components (2026-07-16, Canopy Redesign) -- only
    # meaningful for "panel"-shape kinds (canopy_panel), which need a full
    # per-instance tilt that rotation_deg's single Y-axis rotation can't
    # express. Stored in this dataclass's own real-feet Z-up frame, same as
    # every position field -- NOT the Three.js Y-up frame (see Viewport.
    # jsx's toThreeDir() for that conversion). None for every other kind.
    normal_x: float = None
    normal_y: float = None
    normal_z: float = None
    # Which program_requirements.json program this element's massing
    # represents (2026-07-16, program_boxes per-program coloring) -- only
    # set on rebuild()'s program_box_specs (one building_mass box per
    # claimed bay), so the frontend can color each box by its actual
    # program (matching the flat-plane ProgramZoneFootprint's PROGRAM_COLOR)
    # instead of every program box sharing building_mass's one kind color.
    # None for every other building_mass use (manual/user-placed buildings).
    program_item: str = None


def slab_key(slab):
    """Unique identifier for one real slab PLATE, not one real Rhino object --
    a single object (e.g. "L2_east_slab") can yield multiple real_slabs
    entries (two flat landings + one connecting ramp, see the real-slab-
    graph supplement), all sharing the same `parent` name. z_top_ft
    disambiguates them (each real plate sits at its own real elevation).
    Used everywhere a specific plate needs to be referenced (the column<->
    slab graph, framing's slab_id tagging, real_slab_fragments, harvested
    salvage) -- fixed 2026-07-09 after finding build_column_slab_graph and
    slabs_by_parent were both keying on bare `parent`, silently merging a
    west/east object's two distinct floor_slab landings into one entry."""
    return f"{slab['parent']}_{slab['z_top_ft']}"


def build_column_slab_graph(real_geometry):
    """
    Link each real column (real_geometry["real_columns"]) to the real
    floor_slab(s) (real_geometry["real_slabs"], kind == "floor_slab") whose
    plan footprint contains it, and the inverse. ramp_slab plates connect
    between levels and don't bear columns, so they're excluded here.

    Footprints are plain axis-aligned rectangles in plan (confirmed directly
    against the live Rhino model 2026-07-09: even the tilted ramp_slab plates
    only tilt vertically -- real per-corner z varies, x/y don't -- so a
    min/max corner test on just the x/y components is exact, not an
    approximation).

    Returns (column_to_slabs, slab_to_columns):
      column_to_slabs: column id -> [slab_key(slab), ...]
      slab_to_columns: slab_key(slab) -> [column id, ...]
    """
    columns = real_geometry.get("real_columns", [])
    floor_slabs = [s for s in real_geometry.get("real_slabs", []) if s["kind"] == "floor_slab"]

    column_to_slabs = {}
    slab_to_columns = {slab_key(s): [] for s in floor_slabs}

    for col in columns:
        cx, cz = col["x"], col["z"]
        hits = []
        for slab in floor_slabs:
            xs = [c[0] for c in slab["top_corners_ft"]]
            zs = [c[1] for c in slab["top_corners_ft"]]
            if min(xs) <= cx <= max(xs) and min(zs) <= cz <= max(zs):
                hits.append(slab_key(slab))
                slab_to_columns[slab_key(slab)].append(col["id"])
        column_to_slabs[col["id"]] = hits

    return column_to_slabs, slab_to_columns


def _nearest_slab_for_z(column_to_slabs, slabs_by_key, col_id, z_ft, tolerance_ft=2.0):
    """Among the floor slabs a given column actually passes through, find the
    one whose real elevation is closest to z_ft (an excavation level's
    absolute height) -- e.g. a column exposed at level 2 should tag the real
    slab whose z_top_ft is ~-20ft, not just any slab the column happens to
    pierce. Returns None if the nearest is farther than tolerance_ft away
    (real slabs are spaced 10ft apart here, so 2ft is a generous margin for
    floating point, not a guess that could pick the wrong level)."""
    candidates = column_to_slabs.get(col_id, [])
    if not candidates:
        return None
    best_name, best_dist = None, float("inf")
    for name in candidates:
        slab = slabs_by_key.get(name)
        if slab is None:
            continue
        dist = abs(slab["z_top_ft"] - z_ft)
        if dist < best_dist:
            best_name, best_dist = name, dist
    return best_name if best_dist <= tolerance_ft else None


# Material family / fabrication method / cut-sheet dims per element kind,
# all derived from KIND_REGISTRY (2026-07-10 consolidation pass -- see that
# constant's own comment above for why this replaced three hand-maintained
# copies). Names are deliberately provisional -- "fill these in later as
# you develop the assets" was the explicit instruction, so edit
# kindRegistry.json's material_family values, not this derivation code.
MATERIAL_FAMILY = {kind: entry["material_family"] for kind, entry in KIND_REGISTRY["kinds"].items()}
FABRICATION_METHOD = {
    family: entry["fabrication_method"] for family, entry in KIND_REGISTRY["material_families"].items()
}
# Families actually worth putting on a fabrication cut sheet -- vegetation
# and existing as-built structure are real quantities but not something a
# shop drawing gets cut for, so they're reported separately, not mixed into
# the same manifest rows.
CUT_SHEET_MATERIAL_FAMILIES = set(KIND_REGISTRY["cut_sheet_families"])


def material_family_for(kind):
    """Falls back to "unclassified" (not a crash) for any kind not yet
    added to kindRegistry.json -- a new kind should show up on the cut
    sheet as something needing categorization, not silently disappear or
    break the manifest."""
    return MATERIAL_FAMILY.get(kind, "unclassified")


def fabrication_method_for(family):
    return FABRICATION_METHOD.get(family, "TBD")


# Plan-footprint dims (feet) per box-shaped kind -- real height always comes
# from the spec itself, not here (same convention the registry documents).
# Read once, server-side, purely for the cut-sheet quantity takeoff below.
CUT_SHEET_PROTOTYPE_DIMS_FT = {
    kind: tuple(entry["dims_ft"]) for kind, entry in KIND_REGISTRY["kinds"].items() if entry["shape"] == "box"
}
# Kinds whose real quantity is a run length (two-point cylinders), not a
# plan-footprint box -- detected structurally too (spec.x2_ft is not None),
# this set is just for kinds that are ALWAYS two-point even if a given specs
# list is empty, so the manifest still lists a zero row for them.
CUT_SHEET_LINEAR_KINDS = {
    kind for kind, entry in KIND_REGISTRY["kinds"].items() if entry["shape"] == "two_point"
}
# Panel-shape kinds (2026-07-16, Canopy Redesign) -- unlike box kinds, a
# panel's width/depth aren't a static per-kind dict entry (dims_ft); each
# instance's own scale/scale_y ARE its real width/depth (see
# canopy_engine.py's _panel_specs()), so area is computed directly from the
# spec in build_cut_sheet_manifest below, not looked up here.
CUT_SHEET_PANEL_KINDS = {
    kind for kind, entry in KIND_REGISTRY["kinds"].items() if entry["shape"] == "panel"
}


def build_cut_sheet_manifest(all_specs, real_slabs=None, real_columns=None):
    """Flattens every StructuralElement plus the real slab/column solids into
    one material-categorized manifest: count, plan area, volume, and/or
    linear run length per kind, grouped under the family's cut-sheet bucket.
    real_slabs/real_columns get their own "existing_structure" section
    (real, as-built quantities, not a fabrication line item) rather than
    being mixed into CUT_SHEET_MATERIAL_FAMILIES -- see MATERIAL_FAMILY's
    docstring above for why.

    Returns {"families": {family: {"kinds": {kind: {...}}, "total_count":
    int, "total_volume_ft3": float}}, "existing_structure": {...}}.
    """
    per_kind = {}

    def _bucket(kind):
        return per_kind.setdefault(kind, {"count": 0, "area_ft2": 0.0, "volume_ft3": 0.0, "linear_ft": 0.0})

    for s in all_specs:
        b = _bucket(s.kind)
        b["count"] += 1
        if s.x2_ft is not None or s.kind in CUT_SHEET_LINEAR_KINDS:
            if s.x2_ft is not None:
                length = math.dist((s.x_ft, s.y_ft, s.z_top_ft), (s.x2_ft, s.y2_ft, s.z2_ft))
                b["linear_ft"] += length
        elif s.kind in CUT_SHEET_PANEL_KINDS:
            area = s.scale * (s.scale_y if s.scale_y is not None else s.scale)
            b["area_ft2"] += area
            b["volume_ft3"] += area * max(s.height_ft, 0.0)
        else:
            dims = CUT_SHEET_PROTOTYPE_DIMS_FT.get(s.kind)
            if dims:
                sx = dims[0] * s.scale
                sy = dims[1] * (s.scale_y if s.scale_y is not None else s.scale)
                area = sx * sy
                b["area_ft2"] += area
                b["volume_ft3"] += area * max(s.height_ft, 0.0)

    families = {}
    for kind, qty in per_kind.items():
        family = material_family_for(kind)
        if family not in CUT_SHEET_MATERIAL_FAMILIES:
            continue  # vegetation/tbd_massing/existing_structure/unclassified reported separately
        fam = families.setdefault(family, {
            "fabrication_method": fabrication_method_for(family),
            "kinds": {}, "total_count": 0, "total_volume_ft3": 0.0, "total_linear_ft": 0.0,
        })
        fam["kinds"][kind] = qty
        fam["total_count"] += qty["count"]
        fam["total_volume_ft3"] += qty["volume_ft3"]
        fam["total_linear_ft"] += qty["linear_ft"]

    existing = {"floor_slab": {"count": 0, "area_ft2": 0.0, "volume_ft3": 0.0},
                "ramp_slab": {"count": 0, "area_ft2": 0.0, "volume_ft3": 0.0},
                "column": {"count": 0, "volume_ft3": 0.0}}
    for slab in (real_slabs or []):
        b = existing.setdefault(slab["kind"], {"count": 0, "area_ft2": 0.0, "volume_ft3": 0.0})
        b["count"] += 1
        b["area_ft2"] += slab["area_ft2"]
        b["volume_ft3"] += slab["area_ft2"] * slab["thickness_ft"]
    for col in (real_columns or []):
        b = existing["column"]
        b["count"] += 1
        radius = col["diameter_ft"] / 2.0
        height = col["top_ft"] - col["bottom_ft"]
        b["volume_ft3"] += math.pi * radius * radius * height

    return {
        "families": families,
        "existing_structure": existing,
        "not_fabricated": {
            kind: qty for kind, qty in per_kind.items()
            if material_family_for(kind) == "vegetation"
        },
    }


class StructuralFramingEngine:
    """
    Structural framing + slab-harvest engine for the cockpit's Material Mode /
    Shoring Density sliders. There is only one canyon -- the real
    sketch/transit/deficit-scored voxel field TerracingEngine.run() already
    produces (this project's own "Adaptive Canyon Step Generator" name, see
    module docstring, already says as much). Canyon Width and Canyon Depth do
    NOT carve an independent shape here; they are inputs to that same
    TerracingEngine run (transit_falloff_ft and max_canyon_depth_ft -- see
    blender_cockpit.rebuild_all), and this class only reads the resulting
    voxel grid to derive tonnage and instance placement. (An earlier draft
    carved its own deterministic rectangle disconnected from the real
    excavation -- corrected 2026-07-05: a column position or retaining wall
    placed there had no guarantee the real terrace mesh was actually cut
    there too.)
    """

    def __init__(self, real_geometry, terracing_engine, material_mode='STEEL', shoring_density=1.0):
        self.rg = real_geometry
        self.te = terracing_engine
        self.material_mode = material_mode
        self.shoring_density = shoring_density
        self.voxel_ft = terracing_engine.voxel_ft
        self.step_ft = terracing_engine.step_ft
        # Real column<->slab assembly graph (2026-07-09 real-slab-graph
        # supplement) -- only populated when real_geometry actually has the
        # real_columns/real_slabs arrays (extracted straight from live Rhino,
        # see plan doc); harmless empty dicts otherwise, so older
        # real_geometry.json snapshots without these fields still work.
        self.column_to_slabs, self.slab_to_columns = build_column_slab_graph(real_geometry)
        self.slabs_by_key = {slab_key(s): s for s in real_geometry.get("real_slabs", [])}

    def _voxel_at(self, gx, gy):
        if 0 <= gx < self.te.nx and 0 <= gy < self.te.nz:
            return self.te.voxels[gx][gy]
        return None

    def _levels_breached(self, v):
        return round(-v.z_ft / self.step_ft) if v.z_ft < 0 else 0

    def real_slab_fragments(self):
        """Classifies every voxel cell within each real slab's real
        footprint as still-remaining (excavation hasn't reached that slab's
        real elevation there yet) or removed (it has) -- 2026-07-09 real-
        slab-driven harvest supplement, replacing the old voxel-generic
        slab_harvest_tons/harvested_block_specs math below. Footprint
        containment uses the same axis-aligned min/max simplification
        build_column_slab_graph already relies on (the new SURFACE slab's
        ~0.4deg rotation is negligible at voxel-grid resolution). Each
        slab's own z_top_ft is tested independently, so stacked slabs at the
        same XY (e.g. L1/L2/L3_center) each correctly read remaining/removed
        based on how deep the real excavation actually reached, not on each
        other.

        Returns {slab_key: {"slab": slab_dict, "remaining": [(gx,gy,wx,wy),...],
        "removed_count": int}}.
        """
        nx, nz = self.te.nx, self.te.nz
        result = {}
        for slab in self.rg.get("real_slabs", []):
            xs = [c[0] for c in slab["top_corners_ft"]]
            ys = [c[1] for c in slab["top_corners_ft"]]
            x_min, x_max = min(xs), max(xs)
            y_min, y_max = min(ys), max(ys)
            remaining = []
            removed = []
            # Ramp plates are structural connectors between a level's own
            # stepped sub-elevations (2026-07-13, "remove top slab" feature)
            # -- not paint-derived like floor_slab, and the only physical
            # way to move between L1's -0/-5/-10ft steps. Always kept
            # regardless of how deep excavation reached, or forcing a
            # uniform minimum dig depth (see TerracingEngine.remove_top_slab)
            # would strand one step from another.
            is_ramp = slab.get("kind") == "ramp_slab"
            for gx in range(nx):
                for gy in range(nz):
                    v = self.te.voxels[gx][gy]
                    if not (x_min <= v.wx <= x_max and y_min <= v.wy <= y_max):
                        continue
                    if is_ramp:
                        remaining.append((gx, gy, v.wx, v.wy))
                        continue
                    # A cell is only "removed" if it's genuinely excavated
                    # (v.z_ft < 0) AND that cut reached at or below this
                    # slab's real elevation -- v.z_ft < 0 alone isn't
                    # redundant here: real_geometry's new SURFACE slab sits
                    # at z_top_ft=+0.25 (just above the v.z_ft==0 "untouched"
                    # reference), so the old `v.z_ft <= slab["z_top_ft"]`
                    # test alone was true for EVERY untouched cell (0 <=
                    # 0.25), marking nearly the whole site "removed" by
                    # default regardless of painting -- confirmed live
                    # 2026-07-09 (2613/2680 cells reported removed with only
                    # 917 actually excavated). Below-grade slabs (negative
                    # z_top_ft) are unaffected either way, since a cut can't
                    # satisfy z_ft <= a negative number without already
                    # being < 0.
                    if v.z_ft < 0 and v.z_ft <= slab["z_top_ft"]:
                        removed.append((gx, gy, v.wx, v.wy))
                    else:
                        remaining.append((gx, gy, v.wx, v.wy))
            result[slab_key(slab)] = {
                "slab": slab, "remaining": remaining, "removed": removed, "removed_count": len(removed),
            }
        return result

    def classify_terrain_cells(self, fragments=None):
        """
        Per-cell classification of which REAL slab (if any) a voxel
        currently "belongs to" -- the exposed real surface a vector-export
        mesh builder should draw there, vs. cells with no real precedent at
        all (2026-07-11, vector-export terrain-mesh rewrite: replaces the
        old approach of boxing every voxel individually regardless of
        whether it ever corresponded to real structure, which produced a
        mesh too dense for hidden-line-removal to complete -- see
        vector_export.build_terraced_solid).

        For each cell, considers every real slab whose footprint contains
        it and picks the SHALLOWEST one not yet excavated away (max
        z_top_ft among real_slab_fragments()'s "remaining" classification
        for that cell) -- that's the currently-exposed real surface, since
        real_slab_fragments()'s removal test is monotone in the stack: a
        cut that has passed a deeper slab's elevation has necessarily also
        passed every shallower slab's elevation at that same XY (confirmed
        against live real_geometry.json data -- stacked slabs like
        L2_east_slab/L3_east_slab share identical XY footprints at
        different elevations, never two same-elevation slabs claiming the
        same cell).

        Returns {(gx, gy): slab_key or None} -- None means no real slab is
        currently exposed there at all (either excavated past every real
        slab present at that XY, or outside every real slab's footprint
        entirely) -- genuinely new/designed terracing with no real
        precedent, the vector-export builder's fallback case.

        `fragments`: pass an already-computed real_slab_fragments() result
        to avoid a second full voxel-grid scan when the caller already has
        one (vector_export.py's builder will).
        """
        if fragments is None:
            fragments = self.real_slab_fragments()

        best_slab_for_cell = {}  # (gx, gy) -> (z_top_ft, slab_key)
        for key, entry in fragments.items():
            z_top_ft = entry["slab"]["z_top_ft"]
            for gx, gy, _wx, _wy in entry["remaining"]:
                cell = (gx, gy)
                current = best_slab_for_cell.get(cell)
                if current is None or z_top_ft > current[0]:
                    best_slab_for_cell[cell] = (z_top_ft, key)

        result = {}
        for gx in range(self.te.nx):
            for gy in range(self.te.nz):
                entry = best_slab_for_cell.get((gx, gy))
                result[(gx, gy)] = entry[1] if entry is not None else None
        return result

    def slab_harvest_tons(self):
        """Real-slab-driven harvest calc (2026-07-09, replaces the old
        voxel-generic version): for every real slab, the real footprint area
        that's been excavated past that slab's real elevation is gone --
        sum those real removed volumes (real per-slab thickness, not a
        flat 8" guess) and convert to tons."""
        voxel_area_ft2 = self.voxel_ft * self.voxel_ft
        total_ft3 = 0.0
        for entry in self.real_slab_fragments().values():
            total_ft3 += entry["removed_count"] * voxel_area_ft2 * entry["slab"]["thickness_ft"]
        return total_ft3 * CONCRETE_UNIT_WEIGHT_PCF / 2000.0

    def harvested_block_specs(self):
        """Salvaged concrete re-instanced as clean, sharp diamond wire-sawn
        blocks: real-slab-driven floor plates (2026-07-09, replacing the old
        voxel-generic version) plus voxel-driven retaining-wall plates
        (unchanged -- no real retaining-wall geometry exists yet to tie
        those to).

        Floor blocks: one `concrete_floor_block` per real slab cell that's
        actually been excavated past that slab's real elevation
        (real_slab_fragments' "removed" cells), at that slab's real
        thickness and tagged slab_id -- not a generic "local floor" guess at
        every voxel regardless of whether a real slab was ever there
        (voxels outside every real slab's real footprint, e.g. near the
        tunnel gap, correctly emit nothing now).

        Retaining-wall blocks: coursed plates stacked up every real exposed
        retaining-wall face (a neighbor shallower than this voxel, including
        the site edge, which reads as grade). Alternate courses are
        staggered sideways along the wall's own run (running bond) so the
        stack reads as a real coursed crib-wall, not a column of identical
        blocks -- per New Feature Directives / Concrete Loop supplement.
        """
        specs = []
        nx, nz = self.te.nx, self.te.nz
        block_t = RETAINING_BLOCK_THICKNESS_FT

        for entry in self.real_slab_fragments().values():
            slab = entry["slab"]
            sid = slab_key(slab)
            for gx, gy, wx, wy in entry["removed"]:
                specs.append(StructuralElement(
                    "concrete_floor_block", wx, wy, slab["z_top_ft"], slab["thickness_ft"], slab_id=sid))

        for gx in range(nx):
            for gy in range(nz):
                v = self.te.voxels[gx][gy]
                if v.z_ft >= 0:
                    continue
                neighbor_zs = []
                for ngx, ngy in ((gx - 1, gy), (gx + 1, gy), (gx, gy - 1), (gx, gy + 1)):
                    nv = self._voxel_at(ngx, ngy)
                    neighbor_zs.append((ngx, ngy, nv.z_ft if nv is not None else 0.0))

                for ngx, ngy, nz_val in neighbor_zs:
                    if nz_val <= v.z_ft:
                        continue  # neighbor at least as deep -- no exposed wall face this direction
                    wall_height = nz_val - v.z_ft
                    courses = max(1, round(wall_height / block_t))
                    wx = v.wx + (ngx - gx) * self.voxel_ft / 2.0
                    wy = v.wy + (ngy - gy) * self.voxel_ft / 2.0
                    # Stagger runs along the wall face (perpendicular to its
                    # outward normal (ngx-gx, ngy-gy)), alternating every
                    # other course.
                    along_dx, along_dy = -(ngy - gy), (ngx - gx)
                    for c in range(courses):
                        cz = nz_val - block_t * (c + 0.5)
                        off = RUNNING_BOND_STAGGER_FT if c % 2 else 0.0
                        specs.append(StructuralElement(
                            "concrete_retaining_block", wx + along_dx * off, wy + along_dy * off, cz, block_t))
        return specs

    def _column_grid(self):
        """Real columns indexed by their real 27ft grid cell, so adjacency
        (for horizontal struts / X-bracing) is a simple dict lookup rather
        than a distance search.

        Prefers real_columns (real id + real diameter/top/bottom, extracted
        straight from the live Rhino STRUC__Columns Breps -- 2026-07-09 real-
        slab-graph supplement) over the older column_positions (points only,
        no id, no way to look up which real slab a column bears on). Falls
        back to column_positions with a synthetic id when real_columns is
        absent, so this keeps working against older real_geometry.json
        snapshots -- just without slab_id/column_id tagging downstream."""
        grid = {}
        columns = self.rg.get("real_columns")
        if columns:
            for col in columns:
                gx = round(col["x"] / STRUCTURAL_BAY_FT)
                gy = round(col["z"] / STRUCTURAL_BAY_FT)
                grid[(gx, gy)] = col
        else:
            for col in self.rg["column_positions"]:
                gx = round(col["x"] / STRUCTURAL_BAY_FT)
                gy = round(col["z"] / STRUCTURAL_BAY_FT)
                grid[(gx, gy)] = {**col, "id": f"{gx}_{gy}"}
        return grid

    def _anchored_z(self, col_id, lvl):
        """Real slab elevations (10ft spacing, e.g. -10/-20/-30) don't line
        up with the voxel grid's excavation-level spacing (9ft, matching
        voxel_ft) -- collars/struts placed at the raw voxel-derived height
        therefore floated near, but not exactly at, the real slab they're
        conceptually attached to (2026-07-09 fix, user-reported: horizontal
        bracing wasn't visually anchored into the real slab it should
        terminate at). When a real slab actually matches this column/level
        (via _nearest_slab_for_z's tolerance), snap to that slab's real
        z_top_ft instead of the voxel-derived height, so the geometry
        visually terminates AT the real slab, not near it; otherwise (no
        real slab exists at this particular excavation level) fall back to
        the voxel z unchanged. Returns (z_ft, slab_id_or_None)."""
        z = -lvl * self.step_ft
        slab_id = _nearest_slab_for_z(self.column_to_slabs, self.slabs_by_key, col_id, z)
        if slab_id is not None:
            return self.slabs_by_key[slab_id]["z_top_ft"], slab_id
        return z, None

    def steel_frame_specs(self):
        """STEEL mode -- Industrial Sleeve & Strut System: only real columns
        (real_geometry["column_positions"]) whose voxel cell the real
        excavation actually cut get framed.

        - Split-sleeve collar at every exposed level, extending past the real
          cut line, with a bolt-ring standing off it (the "friction
          connection").
        - A horizontal large-diameter pipe strut between every pair of real
          adjacent (27ft grid) exposed columns at their shared exposed
          levels, capped at each end with a gusset plate + bolt-flange plate
          so the strut-to-collar transition reads as a real load path.
        - A true two-point X-brace tie-rod (with a turnbuckle at its
          midpoint) to each diagonal neighbor where vertical exposure
          exceeds 2 continuous levels.
        """
        specs = []
        grid = self._column_grid()
        exposure = {}  # (gx, gy) -> (col, levels) for exposed columns only

        for key, col in grid.items():
            gx = int(col["x"] // self.voxel_ft)
            gy = int(col["z"] // self.voxel_ft)
            v = self._voxel_at(gx, gy)
            levels = self._levels_breached(v) if v is not None else 0
            if levels == 0:
                continue  # real excavation never reached this column -- nothing to brace
            exposure[key] = levels

            for lvl in range(levels):
                z, slab_id = self._anchored_z(col["id"], lvl)
                specs.append(StructuralElement(
                    "steel_collar_sleeve", col["x"], col["z"], z + COLLAR_EXTENSION_FT,
                    self.step_ft + 2 * COLLAR_EXTENSION_FT, scale=self.shoring_density,
                    column_id=col["id"], slab_id=slab_id))
                collar_r = 0.75 * self.shoring_density + COLLAR_FLANGE_OFFSET_FT
                for b in range(COLLAR_BOLT_COUNT):
                    ang = 2 * math.pi * b / COLLAR_BOLT_COUNT
                    specs.append(StructuralElement(
                        "steel_bolt",
                        col["x"] + math.cos(ang) * collar_r, col["z"] + math.sin(ang) * collar_r,
                        z + 0.15, 0.3, radius_ft=COLLAR_BOLT_RADIUS_FT))

            if levels > 2:
                top_z, bottom_z = 0.0, -levels * self.step_ft
                for dgx, dgy in ((key[0] + 1, key[1] + 1), (key[0] + 1, key[1] - 1)):
                    other = grid.get((dgx, dgy))
                    if other is None:
                        continue
                    e = StructuralElement("steel_tie_rod", col["x"], col["z"], top_z, 0.0,
                                          radius_ft=TIE_ROD_RADIUS_FT,
                                          column_id=col["id"], column_id2=other["id"])
                    e.x2_ft, e.y2_ft, e.z2_ft = other["x"], other["z"], bottom_z
                    specs.append(e)
                    mx, my, mz = (col["x"] + other["x"]) / 2, (col["z"] + other["z"]) / 2, (top_z + bottom_z) / 2
                    specs.append(StructuralElement(
                        "steel_turnbuckle", mx, my, mz, TURNBUCKLE_LENGTH_FT, radius_ft=TURNBUCKLE_RADIUS_FT))

        for key, levels in exposure.items():
            col = grid[key]
            for dkey in ((key[0] + 1, key[1]), (key[0], key[1] + 1)):
                other_levels = exposure.get(dkey)
                if other_levels is None:
                    continue
                other = grid[dkey]
                shared_levels = min(levels, other_levels)
                strut_r = STRUT_PIPE_RADIUS_FT * self.shoring_density
                bearing = math.degrees(math.atan2(other["z"] - col["z"], other["x"] - col["x"]))
                for lvl in range(shared_levels):
                    z, slab_id = self._anchored_z(col["id"], lvl)
                    e = StructuralElement("steel_strut", col["x"], col["z"], z, 0.0, radius_ft=strut_r,
                                          column_id=col["id"], column_id2=other["id"],
                                          slab_id=slab_id)
                    e.x2_ft, e.y2_ft, e.z2_ft = other["x"], other["z"], z
                    specs.append(e)
                    for px, py in ((col["x"], col["z"]), (other["x"], other["z"])):
                        specs.append(StructuralElement(
                            "gusset_plate", px, py, z + GUSSET_PLATE_DIMS_FT[2] / 2, GUSSET_PLATE_DIMS_FT[2],
                            rotation_deg=bearing))
                        specs.append(StructuralElement(
                            "bolt_flange_plate", px, py, z, BOLT_FLANGE_THICKNESS_FT,
                            radius_ft=BOLT_FLANGE_RADIUS_FT))
        return specs

    @staticmethod
    def _pack_offsets(count):
        """Timber Column Packing: 1 post at shallow exposure, clustering to
        2-3 tightly-bound posts as depth (hence real load) increases."""
        if count <= 1:
            return [(0.0, 0.0)]
        s = POST_PACK_SPACING_FT
        if count == 2:
            return [(-s / 2, 0.0), (s / 2, 0.0)]
        return [(-s, 0.0), (0.0, 0.0), (s, 0.0)]

    def timber_frame_specs(self):
        """WOOD mode -- Tectonic Glulam Lattice: since voxel_ft is already
        9ft (see TerracingEngine), the real excavated voxel grid IS the 9ft
        heavy-timber sub-grid -- no synthetic sub-nodes needed.

        - Post cluster per node (1 post normally, "packed" to 2-3 posts +
          a steel strapping band once exposure reaches
          POST_PACK_THRESHOLD_LEVELS, per the Depth-Scaling directive).
        - A real horizontal timber beam between every pair of adjacent
          sub-grid nodes at every level both nodes share -- corrected
          2026-07-05: an earlier version placed knee braces with nothing to
          brace against (no beam element existed anywhere in WOOD mode) and
          only at the topmost level of a post regardless of how many levels
          it actually crossed, so a post spanning e.g. 3 levels read as one
          bare continuous post with a single cosmetic brace at grade instead
          of a real story-by-story timber frame.
        - A real 45-degree knee brace at EVERY post-to-beam intersection
          (one per real breached level, not just the top), offset out from
          the corner by KNEE_BRACE_OFFSET_FT on both the horizontal and
          vertical leg -- a true two-point hypotenuse, not a box centered on
          the post.
        - A steel bracket shoe where each post meets the canyon floor.
        Shoring Density subdivides each voxel into an n x n sub-cluster of
        nodes (n = round(shoring_density), floor 1) to pack nodes tighter as
        the safety factor rises.
        """
        specs = []
        n = max(1, round(self.shoring_density))
        pitch = self.voxel_ft / n
        nx, nz = self.te.nx, self.te.nz

        # Global sub-grid node key -> (x_ft, y_ft, levels), spanning the
        # whole site so beams can connect neighboring nodes across a voxel
        # boundary too -- same dict-lookup-adjacency pattern steel_frame_specs
        # already uses for its column grid.
        nodes = {}
        for gx in range(nx):
            for gy in range(nz):
                v = self.te.voxels[gx][gy]
                levels = self._levels_breached(v)
                if levels == 0:
                    continue
                for sx in range(n):
                    for sy in range(n):
                        cx = v.wx - self.voxel_ft / 2 + (sx + 0.5) * pitch
                        cy = v.wy - self.voxel_ft / 2 + (sy + 0.5) * pitch
                        nodes[(gx * n + sx, gy * n + sy)] = (cx, cy, levels)

        for (ngx, ngy), (cx, cy, levels) in nodes.items():
            height_ft = levels * self.step_ft
            pack_count = 1
            if levels >= POST_PACK_THRESHOLD_LEVELS + 1:
                pack_count = 3
            elif levels >= POST_PACK_THRESHOLD_LEVELS:
                pack_count = 2

            for ox, oy in self._pack_offsets(pack_count):
                px, py = cx + ox, cy + oy
                specs.append(StructuralElement("glulam_post", px, py, 0.0, height_ft))
                specs.append(StructuralElement(
                    "footing_shoe", px, py, -height_ft, FOOTING_SHOE_HEIGHT_FT))
            if pack_count > 1:
                specs.append(StructuralElement(
                    "steel_strap_band", cx, cy, -height_ft * 0.15, STRAP_BAND_HEIGHT_FT,
                    scale=pack_count))

            for lvl in range(levels):
                z = -lvl * self.step_ft

                for angle_deg in (45.0, 135.0, 225.0, 315.0):
                    ang = math.radians(angle_deg)
                    e = StructuralElement(
                        "knee_brace", cx, cy, z - KNEE_BRACE_OFFSET_FT, 0.0, radius_ft=KNEE_BRACE_RADIUS_FT)
                    e.x2_ft = cx + math.cos(ang) * KNEE_BRACE_OFFSET_FT
                    e.y2_ft = cy + math.sin(ang) * KNEE_BRACE_OFFSET_FT
                    e.z2_ft = z
                    specs.append(e)

                for dngx, dngy in ((ngx + 1, ngy), (ngx, ngy + 1)):
                    other = nodes.get((dngx, dngy))
                    if other is None or other[2] <= lvl:
                        continue  # no neighbor node, or neighbor doesn't reach this level
                    ox2, oy2, _ = other
                    e = StructuralElement("timber_beam", cx, cy, z, 0.0, radius_ft=TIMBER_BEAM_RADIUS_FT)
                    e.x2_ft, e.y2_ft, e.z2_ft = ox2, oy2, z
                    specs.append(e)
        return specs

    def structural_specs(self):
        return self.timber_frame_specs() if self.material_mode == 'WOOD' else self.steel_frame_specs()

    def run(self):
        return {
            "slab_harvest_tons": self.slab_harvest_tons(),
            "harvested_blocks": self.harvested_block_specs(),
            "structural": self.structural_specs(),
        }


TREE_TRUNK_HEIGHT_FT = 8.0
TREE_TRUNK_RADIUS_FT = 0.4
TREE_CANOPY_HEIGHT_FT = 10.0
TREE_CANOPY_RADIUS_FT = 6.0
# A 9ft voxel is far denser than real tree spacing -- thin placement to
# roughly one tree per TREE_GRID_SPACING cells along each axis via a
# deterministic grid-modulo check (not randomness), so the same params
# always produce the same layout.
TREE_GRID_SPACING = 3


class TypologyAssetEngine:
    """
    Programmatic Typology Mixing Engine (New Feature Directives section 4).
    Reads TerracingEngine's already-computed, already-classified voxel field
    (v.typology, set by TerracingEngine._classify_typology) and instances
    themed asset bundles for GROTTO and SANCTUARY cells -- purely a
    decorative/furnishing layer on top of the real terrace; does not affect
    excavation depth itself. Returns StructuralElement specs so
    blender_cockpit.py's existing one-mesh-per-kind instancing path (see
    build_structural_meshes) can absorb these for free -- no new instancing
    mechanism needed, same reason that path exists at all (viewport stays
    responsive at any density, per the original directive's closing note).
    """

    def __init__(self, real_geometry, terracing_engine):
        self.rg = real_geometry
        self.te = terracing_engine
        self.voxel_ft = terracing_engine.voxel_ft

    def _nearby_columns(self, wx, wy, radius_ft):
        return [c for c in self.rg["column_positions"]
                if math.hypot(c["x"] - wx, c["z"] - wy) <= radius_ft]

    def grotto_specs(self):
        """
        Water-plane at every GROTTO cell. Vertical Disbursement Rule: the
        full cascade + misting treatment is reserved for deep cells
        (level <= -2) -- "shaded" is a depth proxy here, not a real sun/
        shadow calculation (this module explicitly doesn't model that, see
        its docstring); shallower GROTTO cells get just the reflecting
        water plane. Misting lines are deduped per real column, not per
        voxel -- several adjacent deep GROTTO cells can share one column.
        """
        specs = []
        misted_columns = set()
        for row in self.te.voxels:
            for v in row:
                if v.typology != "GROTTO":
                    continue
                deep = v.level <= -2
                specs.append(StructuralElement("water_plane", v.wx, v.wy, v.z_ft + 0.1, 0.1))
                if deep:
                    specs.append(StructuralElement("water_cascade_block", v.wx, v.wy, v.z_ft + 1.0, 2.0))
                    for col in self._nearby_columns(v.wx, v.wy, self.voxel_ft * 0.75):
                        key = (col["x"], col["z"])
                        if key not in misted_columns:
                            misted_columns.add(key)
                            specs.append(StructuralElement("misting_line", col["x"], col["z"], 0.0, -v.z_ft))
        return specs

    def sanctuary_specs(self):
        """
        Every SANCTUARY cell gets a baseline bench. Vertical Disbursement
        Rule: heavy civic infrastructure (restroom pods) only where shallow
        AND near circulation (v.transit_influence, the existing entrance-
        proximity measure); water fountains only where deep -- these are
        additions on top of the baseline bench, not exclusive alternatives,
        so density of each naturally follows the rule across a real
        SANCTUARY zone spanning multiple levels.
        """
        specs = []
        for row in self.te.voxels:
            for v in row:
                if v.typology != "SANCTUARY":
                    continue
                specs.append(StructuralElement("bench_assembly", v.wx, v.wy, v.z_ft, 1.5))
                if v.level >= -1 and v.transit_influence > 0.5:
                    specs.append(StructuralElement("restroom_pod", v.wx, v.wy, v.z_ft, 8.0))
                if v.level <= -2:
                    specs.append(StructuralElement("fountain", v.wx, v.wy, v.z_ft, 3.0))
        return specs

    def tree_specs(self):
        """
        Trees on tree-painted cells (2026-07-11: moved off is_greenscape --
        trees ARE the shade-casting object, so this paint category places
        them directly; greenscape is pure grass, see the frontend's
        GreenscapeGround). Category renamed from "shade" to "trees" 2026-07-16
        so the paint brush's name matches what it actually places, rather
        than requiring this docstring to explain the indirection.
        Hybrid asset strategy Tier 1: a plain cylinder trunk + hex-prism
        canopy stand-in (fits the existing kind-dispatch paths with zero new
        geometry code), swappable for a real tree model/GLB later without
        touching this placement logic.
        """
        specs = []
        for row in self.te.voxels:
            for v in row:
                if not v.is_tree:
                    continue
                if v.gx % TREE_GRID_SPACING != 0 or v.gy % TREE_GRID_SPACING != 0:
                    continue
                trunk_top = v.z_ft + TREE_TRUNK_HEIGHT_FT
                specs.append(StructuralElement(
                    "tree_trunk", v.wx, v.wy, trunk_top, TREE_TRUNK_HEIGHT_FT,
                    radius_ft=TREE_TRUNK_RADIUS_FT))
                canopy_center = trunk_top + TREE_CANOPY_HEIGHT_FT / 2
                specs.append(StructuralElement(
                    "tree_canopy", v.wx, v.wy, canopy_center, TREE_CANOPY_HEIGHT_FT,
                    radius_ft=TREE_CANOPY_RADIUS_FT))
        return specs

    def run(self):
        return self.grotto_specs() + self.sanctuary_specs() + self.tree_specs()


class BuildingMassEngine:
    """
    Programmatic building-massing layer for surface-intervention planning
    (establishing structures on the site over time) -- purely parameterized
    (its only live caller, 2026-07-17, is rebuild()'s program_box_specs,
    computed from real program placement -- manual user-typed buildings
    were removed as redundant with that), NOT read from
    data/building_heights.json: that file is
    off-site context (real-world buildings around Pershing Square, e.g. the
    Biltmore Hotel) in an abstract coordinate frame that doesn't correspond
    to real_geometry.json's site-feet frame, so it's not usable as an
    on-site massing input without a remap effort this pipeline has no other
    need for.

    v1 is single-box massing per footprint, not per-story architectural
    detail -- appropriate for iterating layout/placement before committing
    to real building form. Emits the same "building_mass" StructuralElement
    kind for every building so it fits the existing kind-lookup-table
    triple with just the one new StructuralElement.scale_y field (see that
    dataclass) rather than any new instancing/export machinery -- same
    hybrid-strategy reasoning as TypologyAssetEngine.tree_specs(): cheap box
    now, swappable for a real/generated model later without touching this
    placement logic.
    """

    def __init__(self, buildings):
        """buildings: list of dicts, each {x_ft, y_ft, width_ft, depth_ft,
        height_ft, setback_ft=0.0, z_ft=0.0}. x_ft/y_ft is the footprint's
        real-feet origin (not center), snapped to the nearest
        STRUCTURAL_BAY_FT grid line -- same convention
        StructuralFramingEngine._column_grid() uses for real columns -- so
        massing reads as intentional, bay-aligned architecture rather than
        an arbitrary floating box. z_ft (2026-07-13 "remove top slab"
        feature) is the real base elevation the footprint actually sits on
        -- 0.0 (grade) unless program placement supplied a real
        floor_elev_ft (see logic/program_placement.py)."""
        self.buildings = buildings

    @staticmethod
    def _snap(v):
        return round(v / STRUCTURAL_BAY_FT) * STRUCTURAL_BAY_FT

    def run(self):
        specs = []
        for b in self.buildings:
            setback = b.get("setback_ft", 0.0)
            width = max(b["width_ft"] - 2 * setback, 1.0)
            depth = max(b["depth_ft"] - 2 * setback, 1.0)
            height = b["height_ft"]
            base_z = b.get("z_ft", 0.0)
            ox, oy = self._snap(b["x_ft"]), self._snap(b["y_ft"])
            cx, cy = ox + width / 2, oy + depth / 2
            # StructuralElement's z_top_ft is the TOP of the box, extending
            # DOWNWARD by height_ft (same top-anchored convention every real
            # slab/column element in this pipeline already uses) -- top =
            # base + height, not just height, once base_z can be non-zero.
            spec = StructuralElement("building_mass", cx, cy, base_z + height, height, scale=width)
            spec.scale_y = depth
            specs.append(spec)
        return specs
