"""
logic/canopy_engine.py
-----------------------
CanopyEngine -- an organic, doubly-curved canopy roof made of individually
oriented panels, generated wherever the painted `canopy` brush OR the
automatic program-correlated coverage mask says "covered" (a footprint, not
an intensity dial -- see the module-level note below and
_auto_coverage_mask()'s docstring), held up by branching support columns
tying back to real structural columns or grade.

Automated coverage (2026-07-23): painting canopy by hand used to be
required before anything would generate at all. _auto_coverage_mask() now
seeds coverage automatically around green_space/sports_recreation/outdoor
program zones (the categories data/program_requirements.json's own
_shade_meta documents as shade-relevant), max-merged against the painted
mask -- painting still works as an addable override, it's just no longer a
prerequisite.

Rebuilt 2026-07-16, replacing the original 2026-07-13 version (flat 27ft
rectilinear beam grid, height entirely gated by paint so it was flat
everywhere unpainted, no vertical support). Two design changes drove the
rewrite:

1. **Paint now means "where," not "how much."** The original equation was
   `height = base + canopy_mask * variable` -- painted alpha scaled the
   height deviation, so a lightly-painted cell was almost flat and an
   unpainted cell was *exactly* flat, but every cell everywhere on the site
   still got a canopy element. Confirmed live (2026-07-16) this produced a
   perfectly flat full-site plane, since nothing had been painted. Real
   user intent, clarified in the same session: the canopy should only
   *exist* where painted at all (a footprint), and the shape itself
   (dips/crests, their position and scale) should be slider-driven,
   unconditionally, wherever a panel exists -- not diluted by paint
   opacity. See `_footprint_mask()`/`_panel_specs()`.

2. **The shape itself is now a real wave, not a linear dip/crest heuristic.**
   `_base_height_matrix()` sums three terms: two orthogonal sine waves
   (genuinely doubly-curved, like the Canopée des Halles reference this
   redesign targets), smooth cosine-falloff crests centered on civic/sports
   program zones (replacing the old hard 0/1 boolean boost), and the
   original excavation-depth dip (now one additive term, not the whole
   equation).

Still reuses terracing_engine.py's own idioms:
- Smoothing follows _relax_depths's flat-array/idx(gx,gy)=gx*nz+gy/
  4-neighbor/fixed-iteration-count idiom (true Laplacian averaging, not
  one-sided clamping).
- Support-column landing points reuse the exact nearest-real-column pattern
  TypologyAssetEngine._nearby_columns already established.
- Panel/support kinds (canopy_panel/canopy_column_trunk/canopy_column_branch)
  reuse the existing StructuralElement shape + the existing box/two_point
  rendering pipelines end-to-end (Viewport.jsx, both Blender scripts) --
  see frontend/src/kindRegistry.json for the "panel" shape this module
  introduces.

Puncturing (holes over painted shade/water, gated on the canopy mask's own
continuous weight exceeding puncture_threshold) is unchanged from the
original design -- see _puncture_mask()'s own docstring note, carried over
verbatim, for why a continuous shade/water intensity doesn't exist to
compare against instead.

No numpy: this module (like terracing_engine.py) stays pure math/stdlib on
purpose -- at this site's grid size (a few thousand cells, at most a
handful of program zones) every pass here is sub-millisecond in plain
Python, not worth breaking that convention.
"""
import math

from terracing_engine import STRUCTURAL_BAY_FT, StructuralElement, clamp01, voxel_attr_grid
from logic.site_grid import build_site_grid

# civic/sports category strings, per logic/program_placement.py's real
# program_requirements.json categories.
DEFAULT_CIVIC_SPORTS_CATEGORIES = ("sports_recreation", "enrichment_civic")

# Shade-relevant program categories (2026-07-23 automated canopy) -- per
# data/program_requirements.json's own "_shade_meta" note: "shade_target_pct
# applies only to surface-level/open program (green_space, sports_recreation,
# outdoor); enrichment_civic and health_care entries are enclosed cassette
# program, so shade is not applicable." Deliberately a DIFFERENT set from
# DEFAULT_CIVIC_SPORTS_CATEGORIES above -- that one answers "which zones
# deserve height/massing drama," this one answers "which zones are outdoor
# and heat-exposed enough to need automatic canopy coverage." Drives
# _auto_coverage_mask() below, not the height sculpt term.
DEFAULT_SHADE_COVERAGE_CATEGORIES = ("green_space", "sports_recreation", "outdoor")

# Support-column tube radii -- trunk heavier than branches, same round-tube
# reasoning the original canopy_beam kind documented (a real canopy/support
# space-frame legitimately IS round structural steel, unlike footpath/ramp/
# escalator's flat ribbon treatment).
TRUNK_RADIUS_FT = 0.6
BRANCH_RADIUS_FT = 0.4


def zone_centroids_and_radii(zones, categories, voxel_ft, radius_scale, bay_ft=STRUCTURAL_BAY_FT):
    """One (cx_ft, cy_ft, radius_ft) per zone matching `categories` --
    centroid and half-span of its bay-index bounding box (zone["bays"] =
    [[gx, gy, floor_elev_ft], ...] per program_placement.place_programs()'s
    documented return shape), radius padded by radius_scale so a zone's
    influence extends a bit past its own footprint rather than stopping
    exactly at its edge (pass 1.0 for no padding). Replaces the original
    _program_zone_boost()'s hard 0/1 grid -- same design intent ("crest over
    program zones"), continuous instead of a flat plateau.

    Module-level (2026-07-24, previously a CanopyEngine method) -- reused by
    logic/pershing_api.py's tree auto-seeding (_auto_seed_trees()) with its
    own category set and radius_scale, so both features share this exact
    geometry instead of a second, possibly-drifting copy. CanopyEngine calls
    this twice itself: once with civic_sports_categories for the height-
    sculpt term, once with shade_coverage_categories for
    _auto_coverage_mask()'s footprint correlation -- same geometry, three
    different "which zones matter, how far does their influence reach"
    answers now, not just two."""
    bays_per_side = round(bay_ft / voxel_ft)
    zone_info = []
    for zone in zones:
        if zone["category"] not in categories:
            continue
        bays = zone["bays"]
        if not bays:
            continue
        gxs = [b[0] for b in bays]
        gys = [b[1] for b in bays]
        min_x_ft = min(gxs) * bays_per_side * voxel_ft
        max_x_ft = (max(gxs) + 1) * bays_per_side * voxel_ft
        min_y_ft = min(gys) * bays_per_side * voxel_ft
        max_y_ft = (max(gys) + 1) * bays_per_side * voxel_ft
        cx = (min_x_ft + max_x_ft) / 2
        cy = (min_y_ft + max_y_ft) / 2
        span = max(max_x_ft - min_x_ft, max_y_ft - min_y_ft, bay_ft)
        zone_info.append((cx, cy, (span / 2) * radius_scale))
    return zone_info


class CanopyEngine:
    def __init__(self, real_geometry, terracing_engine, voxels, zones, canopy_mask,
                 base_height_ft, wave_amplitude_ft, wave_length_x_ft, wave_length_y_ft,
                 wave_phase_x, wave_phase_y, dip_weight_ft, program_boost_ft,
                 sculpt_radius_scale, smoothing_iterations, puncture_threshold,
                 panel_pitch_ft, panel_thickness_ft, fork_height_fraction, fork_spread_ft,
                 column_search_radius_ft, footprint_paint_threshold, support_tie_back_tolerance_ft,
                 panel_grid_rotation_deg=0.0,
                 civic_sports_categories=DEFAULT_CIVIC_SPORTS_CATEGORIES,
                 shade_coverage_categories=DEFAULT_SHADE_COVERAGE_CATEGORIES):
        self.rg = real_geometry
        self.te = terracing_engine
        self.voxels = voxels
        self.zones = zones
        self.canopy_mask = canopy_mask
        self.base_height_ft = base_height_ft
        self.wave_amplitude_ft = wave_amplitude_ft
        self.wave_length_x_ft = wave_length_x_ft
        self.wave_length_y_ft = wave_length_y_ft
        self.wave_phase_x = wave_phase_x
        self.wave_phase_y = wave_phase_y
        self.dip_weight_ft = dip_weight_ft
        self.program_boost_ft = program_boost_ft
        self.sculpt_radius_scale = sculpt_radius_scale
        self.smoothing_iterations = smoothing_iterations
        self.puncture_threshold = puncture_threshold
        self.panel_pitch_ft = panel_pitch_ft
        self.panel_thickness_ft = panel_thickness_ft
        self.fork_height_fraction = fork_height_fraction
        self.fork_spread_ft = fork_spread_ft
        self.column_search_radius_ft = column_search_radius_ft
        self.footprint_paint_threshold = footprint_paint_threshold
        self.support_tie_back_tolerance_ft = support_tie_back_tolerance_ft
        self.panel_grid_rotation_deg = panel_grid_rotation_deg
        self.civic_sports_categories = set(civic_sports_categories)
        self.shade_coverage_categories = set(shade_coverage_categories)

    def _zone_centroids_and_radii(self, nx, nz, voxel_ft, categories, bay_ft=STRUCTURAL_BAY_FT):
        """One (cx_ft, cy_ft, radius_ft) per zone matching `categories` --
        see the standalone zone_centroids_and_radii() below (module-level
        since 2026-07-24, extracted so logic/pershing_api.py's tree
        auto-seeding can reuse the exact same bay-index-bbox math instead of
        a second, possibly-drifting copy) for the actual geometry. This is
        just a thin instance-state wrapper (self.zones/self.sculpt_radius_scale)."""
        return zone_centroids_and_radii(self.zones, categories, voxel_ft, self.sculpt_radius_scale, bay_ft)

    def _base_height_matrix(self, z_grid, zone_info, nx, nz, voxel_ft):
        """height[gx][gy] = base_height_ft + wave_term + sculpt_term -
        dip_weight_ft * dip -- unconditional, no canopy_mask multiplier
        (mask now gates panel EXISTENCE only, see _footprint_mask(), not
        height intensity). wave_term is two orthogonal sine waves (doubly-
        curved); sculpt_term sums a smooth cosine falloff per civic/sports
        zone centroid; dip pulls down over deep excavation, unchanged from
        the original design."""
        max_depth = self.te.max_canyon_depth_ft or 1.0
        flat = []
        for gx in range(nx):
            x_ft = gx * voxel_ft + voxel_ft / 2
            for gy in range(nz):
                y_ft = gy * voxel_ft + voxel_ft / 2
                z_ft = z_grid[gx][gy]
                dip = clamp01(-z_ft / max_depth)

                wave = self.wave_amplitude_ft * 0.5 * (
                    math.sin(2 * math.pi * x_ft / self.wave_length_x_ft + self.wave_phase_x)
                    + math.sin(2 * math.pi * y_ft / self.wave_length_y_ft + self.wave_phase_y)
                )

                sculpt = 0.0
                for cx, cy, radius in zone_info:
                    d = math.hypot(x_ft - cx, y_ft - cy)
                    if d < radius:
                        sculpt += self.program_boost_ft * 0.5 * (1 + math.cos(math.pi * d / radius))

                variable = wave + sculpt - self.dip_weight_ft * dip
                flat.append(self.base_height_ft + variable)
        return flat

    def _smooth(self, height_flat, nx, nz, iterations):
        """True Laplacian averaging pass -- same flat-array/idx(gx,gy)/
        4-neighbor/iteration idiom as TerracingEngine._relax_depths, but
        averages with neighbors instead of clamping to a one-sided max.
        Runs the full requested iteration count (no early-break): unlike
        _relax_depths's monotonic constraint, Laplacian smoothing has no
        natural fixed point to converge to -- the iteration count itself is
        the user-facing "how smooth" dial."""
        def idx(gx, gy):
            return gx * nz + gy

        cur = height_flat[:]
        for _ in range(iterations):
            nxt = cur[:]
            for gx in range(nx):
                for gy in range(nz):
                    neighbors = [
                        cur[idx(ngx, ngy)]
                        for ngx, ngy in ((gx - 1, gy), (gx + 1, gy), (gx, gy - 1), (gx, gy + 1))
                        if 0 <= ngx < nx and 0 <= ngy < nz
                    ]
                    if neighbors:
                        nxt[idx(gx, gy)] = (cur[idx(gx, gy)] + sum(neighbors)) / (1 + len(neighbors))
            cur = nxt
        return cur

    def _footprint_mask(self, mask, nx, nz, threshold):
        """Boolean nx x nz grid: True wherever `mask` (painted canopy_mask
        max-merged with the auto program-coverage mask, see run()) exceeds
        threshold. This is the ONLY thing that controls whether a
        panel/support gets generated here at all -- completely decoupled
        from the height equation above, which never reads either mask.
        Threshold is deliberately low (default 0.05): any deliberate brush
        stroke (or, now, any auto-covered cell, which is always exactly 1.0)
        should count as "covered here," not require a fully-opaque stroke."""
        return [[mask[gx][gy] > threshold for gy in range(nz)] for gx in range(nx)]

    def _auto_coverage_mask(self, nx, nz, voxel_ft, coverage_zone_info):
        """Continuous nx x nz grid, weight 1.0 inside each shade-coverage
        zone's radius (green_space/sports_recreation/outdoor -- see
        DEFAULT_SHADE_COVERAGE_CATEGORIES), 0.0 elsewhere. Merged via max
        against the painted canopy_mask in run() (2026-07-23) so a program
        zone that real shade standards say should be covered gets canopy
        automatically, without requiring the user to paint it first --
        painting still layers on top as an addable override, never erased by
        this (same max-merge, never-erase pattern already established by
        circulation_network.rasterize_network_canyon). Bounded to each
        zone's own bounding box rather than scanning the whole grid per
        zone -- cheap even with several zones on a several-thousand-cell
        site."""
        mask = [[0.0] * nz for _ in range(nx)]
        for cx, cy, radius in coverage_zone_info:
            gx_min = max(0, int((cx - radius) // voxel_ft))
            gx_max = min(nx - 1, int((cx + radius) // voxel_ft))
            gy_min = max(0, int((cy - radius) // voxel_ft))
            gy_max = min(nz - 1, int((cy + radius) // voxel_ft))
            for gx in range(gx_min, gx_max + 1):
                x_ft = gx * voxel_ft + voxel_ft / 2
                for gy in range(gy_min, gy_max + 1):
                    y_ft = gy * voxel_ft + voxel_ft / 2
                    if math.hypot(x_ft - cx, y_ft - cy) <= radius:
                        mask[gx][gy] = 1.0
        return mask

    def _dilate_mask(self, mask, nx, nz, tolerance_ft, voxel_ft):
        """Expand True cells outward by round(tolerance_ft / voxel_ft)
        4-neighbor steps -- used only for support-column placement
        tolerance (_support_specs), never for panels: the roof's visible
        edge should faithfully follow what was painted, only the structural
        supports get slack to reach something solid just past that edge."""
        steps = max(0, round(tolerance_ft / voxel_ft))
        cur = [row[:] for row in mask]
        for _ in range(steps):
            nxt = [row[:] for row in cur]
            for gx in range(nx):
                for gy in range(nz):
                    if cur[gx][gy]:
                        continue
                    for ngx, ngy in ((gx - 1, gy), (gx + 1, gy), (gx, gy - 1), (gx, gy + 1)):
                        if 0 <= ngx < nx and 0 <= ngy < nz and cur[ngx][ngy]:
                            nxt[gx][gy] = True
                            break
            cur = nxt
        return cur

    def _puncture_mask(self, nx, nz):
        """Boolean trees/water presence gates the puncture; the threshold
        itself applies to the canopy mask's own continuous weight (a
        heavier brush stroke = a more deliberate puncture request) -- there
        is no continuous trees/water intensity to compare against instead.
        Unchanged from the original design; still operates within whatever
        footprint _footprint_mask ends up describing, since a panel is
        never generated at all outside that footprint regardless of this
        mask. (is_shade renamed to is_tree 2026-07-16 when the "shade"
        paint category was renamed to "trees" -- same underlying signal.)"""
        punctures = [[False] * nz for _ in range(nx)]
        for v in self.voxels:
            if (v.is_tree or v.is_water) and self.canopy_mask[v.gx][v.gy] > self.puncture_threshold:
                punctures[v.gx][v.gy] = True
        return punctures

    def _sample_bilinear(self, height_matrix, x_ft, y_ft, voxel_ft, nx, nz):
        """Bilinear sample of the nx x nz voxel-resolution height_matrix at
        an arbitrary (x_ft, y_ft) -- at the default panel_pitch_ft (== the
        voxel grid's own spacing) this degenerates to an exact grid read;
        only matters once panel_pitch_ft is set finer than the voxel grid.
        Cell centers match node_pos's own convention (gx*voxel_ft +
        voxel_ft/2)."""
        fx = x_ft / voxel_ft - 0.5
        fy = y_ft / voxel_ft - 0.5
        gx0 = int(math.floor(fx))
        gy0 = int(math.floor(fy))
        tx = fx - gx0
        ty = fy - gy0

        def h(gx, gy):
            gx = min(max(gx, 0), nx - 1)
            gy = min(max(gy, 0), nz - 1)
            return height_matrix[gx][gy]

        h00, h10 = h(gx0, gy0), h(gx0 + 1, gy0)
        h01, h11 = h(gx0, gy0 + 1), h(gx0 + 1, gy0 + 1)
        return h00 * (1 - tx) * (1 - ty) + h10 * tx * (1 - ty) + h01 * (1 - tx) * ty + h11 * tx * ty

    @staticmethod
    def _mask_at(mask, x_ft, y_ft, voxel_ft, nx, nz):
        """Nearest-voxel boolean lookup, shared by the footprint and
        puncture checks in _panel_specs -- panels live on their own
        (possibly finer) grid, masks live on the voxel grid, so this is a
        simple nearest-cell lookup, not an interpolation (booleans don't
        blend meaningfully)."""
        gx = min(max(int(x_ft // voxel_ft), 0), nx - 1)
        gy = min(max(int(y_ft // voxel_ft), 0), nz - 1)
        return mask[gx][gy]

    def _panel_specs(self, height_matrix, footprint_mask, puncture_mask, nx, nz, voxel_ft,
                      site_width_ft, site_length_ft, panel_pitch_ft, panel_thickness_ft,
                      panel_grid_rotation_deg):
        """One canopy_panel StructuralElement per cell of a build_site_grid()
        overlay (logic/site_grid.py -- the same rotatable spatial-organizer
        grid the 2D Digital Palimpsest canvas overlays via /api/site-grid,
        reused here so panel seams can be dialed to any angle instead of
        always axis-aligned) that falls inside the painted footprint
        (skipped entirely otherwise -- this IS "canopy only exists where
        painted") and outside any puncture hole. Normal computed via central
        differences on the bilinear sampler; each panel also carries
        panel_grid_rotation_deg as its own rotation_deg so renderers can spin
        the panel's in-plane u/v basis to match, not just tilt it (see
        StructuralElement.rotation_deg's docstring). build_site_grid() only
        returns cells whose center falls inside the site rectangle, so the
        previous "ragged boundary remainder dropped, not clipped" behavior
        carries over unchanged -- acceptable v1 edge cosmetic, consistent
        with this app's existing tolerance for abstraction over literal
        precision elsewhere (e.g. no column keep-out zones)."""
        grid = build_site_grid(site_width_ft, site_length_ft, panel_pitch_ft, panel_grid_rotation_deg)
        h = panel_pitch_ft / 2.0
        specs = []
        for cell in grid["cells"]:
            x_ft, y_ft = cell["x_ft"], cell["z_ft"]

            if not self._mask_at(footprint_mask, x_ft, y_ft, voxel_ft, nx, nz):
                continue
            if self._mask_at(puncture_mask, x_ft, y_ft, voxel_ft, nx, nz):
                continue

            z_ft = self._sample_bilinear(height_matrix, x_ft, y_ft, voxel_ft, nx, nz)
            dzdx = (
                self._sample_bilinear(height_matrix, x_ft + h, y_ft, voxel_ft, nx, nz)
                - self._sample_bilinear(height_matrix, x_ft - h, y_ft, voxel_ft, nx, nz)
            ) / (2 * h)
            dzdy = (
                self._sample_bilinear(height_matrix, x_ft, y_ft + h, voxel_ft, nx, nz)
                - self._sample_bilinear(height_matrix, x_ft, y_ft - h, voxel_ft, nx, nz)
            ) / (2 * h)
            nrm_x, nrm_y, nrm_z = -dzdx, -dzdy, 1.0
            length = math.sqrt(nrm_x ** 2 + nrm_y ** 2 + nrm_z ** 2)
            nrm_x, nrm_y, nrm_z = nrm_x / length, nrm_y / length, nrm_z / length

            specs.append(StructuralElement(
                "canopy_panel", x_ft, y_ft, z_ft, panel_thickness_ft,
                scale=panel_pitch_ft, scale_y=panel_pitch_ft,
                rotation_deg=panel_grid_rotation_deg,
                normal_x=nrm_x, normal_y=nrm_y, normal_z=nrm_z))
        return specs

    def _nearest_real_column(self, x_ft, y_ft, radius_ft):
        """Nearest real_columns[i] within radius_ft, or None -- same
        nearest-column-within-radius pattern TypologyAssetEngine.
        _nearby_columns already established (terracing_engine.py) for
        attaching procedural elements to real Rhino structure. A plain
        linear scan over 295 real columns is trivially cheap here (called
        at most ~a few hundred times per generate-canopy request, itself
        an explicit action, not the live rebuild loop)."""
        best, best_d = None, radius_ft
        for c in self.rg.get("real_columns", []):
            d = math.hypot(c["x"] - x_ft, c["z"] - y_ft)
            if d <= best_d:
                best, best_d = c, d
        return best

    def _support_specs(self, height_matrix, footprint_mask, nx, nz, voxel_ft, bay_ft,
                        tolerance_ft, column_search_radius_ft, fork_height_fraction,
                        fork_spread_ft, panel_thickness_ft):
        """Branching support columns on the 27ft STRUCTURAL_BAY_FT grid --
        same node placement the original _frame_specs() used, but a node
        only survives if it falls within the footprint mask DILATED by
        tolerance_ft (strictly more permissive than the panel footprint
        check above, by design -- this is the "tie back to real structural
        supports" slack). Each surviving node gets one canopy_column_trunk
        (landing point, real column if one's within column_search_radius_ft
        else grade, up to a fork point) and two canopy_column_branch
        segments (fork point out to the panel attachment, spread
        fork_spread_ft apart along local x) -- a deliberately simple first
        pass, not a full space-colonization branch network (that's a much
        heavier, separate engine class this project already has for
        circulation paths)."""
        dilated = self._dilate_mask(footprint_mask, nx, nz, tolerance_ft, voxel_ft)

        bays_per_side = round(bay_ft / voxel_ft)
        node_gx = list(range(0, nx, bays_per_side))
        if node_gx[-1] != nx - 1:
            node_gx.append(nx - 1)
        node_gy = list(range(0, nz, bays_per_side))
        if node_gy[-1] != nz - 1:
            node_gy.append(nz - 1)

        specs = []
        for gx in node_gx:
            for gy in node_gy:
                if not dilated[gx][gy]:
                    continue

                x_ft = gx * voxel_ft + voxel_ft / 2
                y_ft = gy * voxel_ft + voxel_ft / 2
                top_z = self._sample_bilinear(height_matrix, x_ft, y_ft, voxel_ft, nx, nz) - panel_thickness_ft / 2

                col = self._nearest_real_column(x_ft, y_ft, column_search_radius_ft)
                if col is not None:
                    land_x, land_y, land_z = col["x"], col["z"], col["top_ft"]
                else:
                    land_x, land_y, land_z = x_ft, y_ft, 0.0

                fork_x = land_x + (x_ft - land_x) * fork_height_fraction
                fork_y = land_y + (y_ft - land_y) * fork_height_fraction
                fork_z = land_z + (top_z - land_z) * fork_height_fraction

                specs.append(StructuralElement(
                    "canopy_column_trunk", land_x, land_y, land_z, 0.0,
                    x2_ft=fork_x, y2_ft=fork_y, z2_ft=fork_z, radius_ft=TRUNK_RADIUS_FT))
                specs.append(StructuralElement(
                    "canopy_column_branch", fork_x, fork_y, fork_z, 0.0,
                    x2_ft=x_ft - fork_spread_ft, y2_ft=y_ft, z2_ft=top_z, radius_ft=BRANCH_RADIUS_FT))
                specs.append(StructuralElement(
                    "canopy_column_branch", fork_x, fork_y, fork_z, 0.0,
                    x2_ft=x_ft + fork_spread_ft, y2_ft=y_ft, z2_ft=top_z, radius_ft=BRANCH_RADIUS_FT))
        return specs

    def run(self):
        """Returns (height_matrix, puncture_mask, panel_specs, support_specs).
        height_matrix/puncture_mask are nx x nz nested lists (matching
        TerracingEngine's own list-of-lists convention, no numpy) computed
        for the FULL site regardless of paint (the equation is
        unconditional, see _base_height_matrix) -- panel_specs/support_specs
        are what actually respect the painted footprint."""
        nx, nz = self.te.nx, self.te.nz
        voxel_ft = self.te.voxel_ft
        site_width_ft = self.rg["site"]["width_ft"]
        site_length_ft = self.rg["site"]["length_ft"]

        z_grid = voxel_attr_grid(self.voxels, nx, nz, "z_ft")
        zone_info = self._zone_centroids_and_radii(nx, nz, voxel_ft, self.civic_sports_categories)
        coverage_zone_info = self._zone_centroids_and_radii(nx, nz, voxel_ft, self.shade_coverage_categories)

        flat_height = self._base_height_matrix(z_grid, zone_info, nx, nz, voxel_ft)
        smoothed = self._smooth(flat_height, nx, nz, self.smoothing_iterations)
        height_matrix = [smoothed[gx * nz:(gx + 1) * nz] for gx in range(nx)]

        # 2026-07-23: footprint existence now comes from whichever is higher,
        # painted canopy_mask OR the auto program-correlated coverage mask --
        # see _auto_coverage_mask()'s own docstring for the max-merge/
        # never-erase reasoning.
        auto_coverage = self._auto_coverage_mask(nx, nz, voxel_ft, coverage_zone_info)
        merged_mask = [
            [max(self.canopy_mask[gx][gy], auto_coverage[gx][gy]) for gy in range(nz)]
            for gx in range(nx)
        ]
        footprint_mask = self._footprint_mask(merged_mask, nx, nz, self.footprint_paint_threshold)
        puncture_mask = self._puncture_mask(nx, nz)

        panel_specs = self._panel_specs(
            height_matrix, footprint_mask, puncture_mask, nx, nz, voxel_ft,
            site_width_ft, site_length_ft, self.panel_pitch_ft, self.panel_thickness_ft,
            self.panel_grid_rotation_deg)
        support_specs = self._support_specs(
            height_matrix, footprint_mask, nx, nz, voxel_ft, STRUCTURAL_BAY_FT,
            self.support_tie_back_tolerance_ft, self.column_search_radius_ft,
            self.fork_height_fraction, self.fork_spread_ft, self.panel_thickness_ft)

        return height_matrix, puncture_mask, panel_specs, support_specs
