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
import math
from dataclasses import dataclass, field


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
    sketch_weight: float = 0.0
    is_hardscape: bool = False
    is_water_shade: bool = False
    is_greenscape: bool = False
    is_amenity_resting: bool = False
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

    def __init__(self, real_geometry, deficit_hotspots=None, voxel_ft=9.0,
                 transit_falloff_ft=220.0, threshold=0.35, step_ft=9.0,
                 max_canyon_depth_ft=None,
                 level_depth_thresholds_ft=DEFAULT_LEVEL_DEPTH_THRESHOLDS_FT,
                 sketch_weights=None, sketch_alpha=0.75, hardscape_regions=None,
                 water_shade_regions=None, greenscape_regions=None, amenity_resting_regions=None):
        self.real_geometry = real_geometry
        self.voxel_ft = voxel_ft
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
        self.water_shade_regions = water_shade_regions or []
        self.greenscape_regions = greenscape_regions or []
        self.amenity_resting_regions = amenity_resting_regions or []

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

                sketch_weight = 0.0
                if self.sketch_weights is not None:
                    sketch_weight = float(self.sketch_weights[gx][gy])

                is_hardscape = any(region["mask"][gx][gy] for region in self.hardscape_regions)
                is_water_shade = any(region["mask"][gx][gy] for region in self.water_shade_regions)
                is_greenscape = any(region["mask"][gx][gy] for region in self.greenscape_regions)
                is_amenity_resting = any(region["mask"][gx][gy] for region in self.amenity_resting_regions)

                row.append(Voxel(
                    gx=gx, gy=gy, wx=wx, wy=wy,
                    transit_influence=transit_influence,
                    deficit_influence=deficit_influence,
                    sketch_weight=sketch_weight,
                    is_hardscape=is_hardscape,
                    is_water_shade=is_water_shade,
                    is_greenscape=is_greenscape,
                    is_amenity_resting=is_amenity_resting,
                ))
            voxels.append(row)
        return voxels

    def _flat_voxels(self):
        return [v for row in self.voxels for v in row]

    def _effective_influence(self, v):
        """
        transit_influence, additively boosted by the designer's sketch
        weight (if any). This is the one place both depth (_z_for_voxel)
        and score (score_for_phase) read "how much does this cell want to
        excavate" -- keeping the two consistent by construction.

        Literal addition, not a weighted average -- v.sketch_weight == 0
        (nowhere near a sketched line, i.e. most of the site) must leave
        transit_influence completely unchanged, or the sketch would dampen
        the data-driven excavation everywhere it wasn't drawn, not just add
        to where it was. (An earlier version used
        alpha*sketch + (1-alpha)*transit -- that's an interpolation between
        two full fields, and wiped out the real entrance-driven excavation
        everywhere the sketch was blank. Caught by testing before/after
        against real data, not assumed correct.)
        """
        if self.sketch_weights is None:
            return v.transit_influence
        return clamp01(v.transit_influence + self.sketch_alpha * v.sketch_weight)

    def score_for_phase(self, v, phase):
        if phase == 1:
            return 0.0
        if phase == 2:
            return v.deficit_influence
        return clamp01(self._effective_influence(v) + v.deficit_influence)

    def _z_for_voxel(self, v, phase):
        if phase != 3 or self._effective_influence(v) <= self.threshold:
            return 0.0
        if v.is_hardscape:
            return 0.0  # designer-protected region -- veto wins regardless of score
        raw_depth = self._effective_influence(v) * self.max_canyon_depth_ft
        return -round(raw_depth / self.step_ft) * self.step_ft

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
                    if flat[i].is_hardscape:
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
        happens to be painted Canyon+Water/Shade (confirmed 2026-07-05: this
        is a post-process classification over the already-computed terrace,
        not a new input to the depth formula). SANCTUARY is paint-only --
        Greenscape and Amenity/Resting can both sit at grade, unrelated to
        excavation depth.
        """
        if v.z_ft < 0 and v.is_water_shade:
            return "GROTTO"
        if v.is_greenscape and v.is_amenity_resting:
            return "SANCTUARY"
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
SLAB_THICKNESS_IN = 8.0
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
    scaling isotropically."""
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

    def _voxel_at(self, gx, gy):
        if 0 <= gx < self.te.nx and 0 <= gy < self.te.nz:
            return self.te.voxels[gx][gy]
        return None

    def _levels_breached(self, v):
        return round(-v.z_ft / self.step_ft) if v.z_ft < 0 else 0

    def slab_harvest_tons(self):
        """Closed-loop harvest calc: for every real excavated voxel, the
        slab that used to occupy its 9'x9' footprint at each breached level
        is gone -- sum those real removed volumes (at an 8" slab thickness)
        and convert to tons. A direct function of whatever TerracingEngine
        actually excavated, not a synthetic bay count."""
        voxel_area_ft2 = self.voxel_ft * self.voxel_ft
        total_ft3 = 0.0
        for row in self.te.voxels:
            for v in row:
                levels = self._levels_breached(v)
                if levels:
                    total_ft3 += voxel_area_ft2 * (SLAB_THICKNESS_IN / 12.0) * levels
        return total_ft3 * CONCRETE_UNIT_WEIGHT_PCF / 2000.0

    def harvested_block_specs(self):
        """Salvaged concrete re-instanced as clean, sharp diamond wire-sawn
        blocks (9'x9'x8" floor plates, 3'x3'x8" retaining-wall plates) at the
        real excavation boundary: a floor plate at every voxel that is a true
        local floor (no neighbor is deeper), and coursed plates stacked up
        every real exposed retaining-wall face (a neighbor shallower than
        this voxel, including the site edge, which reads as grade). Alternate
        courses are staggered sideways along the wall's own run (running
        bond) so the stack reads as a real coursed crib-wall, not a column of
        identical blocks -- per New Feature Directives / Concrete Loop
        supplement."""
        specs = []
        nx, nz = self.te.nx, self.te.nz
        block_t = RETAINING_BLOCK_THICKNESS_FT
        for gx in range(nx):
            for gy in range(nz):
                v = self.te.voxels[gx][gy]
                if v.z_ft >= 0:
                    continue
                neighbor_zs = []
                for ngx, ngy in ((gx - 1, gy), (gx + 1, gy), (gx, gy - 1), (gx, gy + 1)):
                    nv = self._voxel_at(ngx, ngy)
                    neighbor_zs.append((ngx, ngy, nv.z_ft if nv is not None else 0.0))

                if all(v.z_ft <= nz_val for _, _, nz_val in neighbor_zs):
                    specs.append(StructuralElement(
                        "concrete_floor_block", v.wx, v.wy, v.z_ft, SLAB_THICKNESS_IN / 12.0))

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
        """Real column_positions indexed by their real 27ft grid cell, so
        adjacency (for horizontal struts / X-bracing) is a simple dict
        lookup rather than a distance search."""
        grid = {}
        for col in self.rg["column_positions"]:
            gx = round(col["x"] / STRUCTURAL_BAY_FT)
            gy = round(col["z"] / STRUCTURAL_BAY_FT)
            grid[(gx, gy)] = col
        return grid

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
                z = -lvl * self.step_ft
                specs.append(StructuralElement(
                    "steel_collar_sleeve", col["x"], col["z"], z + COLLAR_EXTENSION_FT,
                    self.step_ft + 2 * COLLAR_EXTENSION_FT, scale=self.shoring_density))
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
                                          radius_ft=TIE_ROD_RADIUS_FT)
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
                    z = -lvl * self.step_ft
                    e = StructuralElement("steel_strut", col["x"], col["z"], z, 0.0, radius_ft=strut_r)
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
        Trees on greenscape cells -- reuses the same is_greenscape mask
        driving the frontend's grass-cap ground layer, so trees only show
        up where grass has already been painted. Hybrid asset strategy
        Tier 1: a plain cylinder trunk + hex-prism canopy stand-in (fits
        the existing kind-dispatch paths with zero new geometry code),
        swappable for a real tree model/GLB later without touching this
        placement logic.
        """
        specs = []
        for row in self.te.voxels:
            for v in row:
                if not v.is_greenscape:
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
    (establishing structures on the site over time) -- purely user-
    parameterized, NOT read from data/building_heights.json: that file is
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
        height_ft, setback_ft=0.0}. x_ft/y_ft is the footprint's real-feet
        origin (not center), snapped to the nearest STRUCTURAL_BAY_FT grid
        line -- same convention StructuralFramingEngine._column_grid() uses
        for real columns -- so massing reads as intentional, bay-aligned
        architecture rather than an arbitrary floating box."""
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
            ox, oy = self._snap(b["x_ft"]), self._snap(b["y_ft"])
            cx, cy = ox + width / 2, oy + depth / 2
            spec = StructuralElement("building_mass", cx, cy, height, height, scale=width)
            spec.scale_y = depth
            specs.append(spec)
        return specs
