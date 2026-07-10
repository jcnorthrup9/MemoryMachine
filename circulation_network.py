"""
Memory Machine -- Circulation Network Engine (organic pedestrian path growth).

Grows a real pedestrian circulation network outward from the site's real
Metro station entrance using the Space Colonization Algorithm (Runions et
al. 2007): a single root node grows step-by-step toward the averaged
direction of nearby weighted "attraction points" (sampled from the same
real per-voxel data TerracingEngine/TypologyAssetEngine already compute in
terracing_engine.py), consuming each attraction point once a branch gets
close enough. Produces StructuralElement specs that fit the SAME
kind-lookup-table triple every other feature in this pipeline already
uses -- footpath/ramp/escalator/*_bridge as two-point line segments
(identical mechanism to steel_strut/timber_beam), lookout_point as a
single-point box.

Deliberately NOT a Physarum/slime-mold multi-agent simulation (loops,
redundant connections) -- per project decision 2026-07-09, Space
Colonization's single-rooted, naturally hierarchical branching (trunk ->
branches -> twigs) maps more directly onto "grow paths OUT of the existing
metro entrance" and onto a real primary/secondary/tertiary path hierarchy
a designer can act on.

Scope, per the same 2026-07-09 decision: "food" is dropped as a motivator
(no real data source exists anywhere in this pipeline for it -- not
fabricated), and "exercise" is folded into "rest" (the codebase's own
is_amenity_resting/SANCTUARY typology already don't distinguish the two).
Column-avoidance and switchback/stair geometry for steep segments are also
out of scope -- escalator classification is the deliberately simple
mechanical-assist answer for grades a plain path/ramp can't handle.
Multi-root growth (from ramps/tunnel/street edges too) is left for later --
v1 is single-rooted at the metro entrance per the explicit ask.
"""
import math
from dataclasses import dataclass

import numpy as np

from terracing_engine import StructuralElement

# --- Tunable-by-UI defaults (see logic/pershing_api.py's NetworkParams) ---
DEFAULT_MOTIVATOR_WEIGHTS = {
    "shade": 1.0, "water": 1.0, "rest": 1.0, "foot_traffic": 1.0, "deficit": 1.0,
}
DEFAULT_STEP_FT = 15.0
DEFAULT_MAX_ITERATIONS = 300

# --- Hardcoded engineering/aesthetic constants (not UI knobs -- real-world
# anchors or rendering choices, not design-intent a reviewer would expect
# exposed as sliders) ---
FIELD_ATTRACTOR_THRESHOLD = 0.4      # min field value to become an attractor
BUCKET_VOXELS = 3                    # dedup bucket size; * 9ft voxel == 27ft == STRUCTURAL_BAY_FT
FOOTPATH_MAX_GRADE = 0.05            # 1:20 -- plain walking surface, no assist needed
RAMP_MAX_GRADE = 1.0 / 12.0          # 1:12 -- ADA max ramp grade
BRIDGE_CLEARANCE_FT = 6.0            # min headroom under a "floating" deck to count as a real bridge
BRIDGE_SAMPLE_COUNT = 5
BASE_PATH_RADIUS_FT = 1.5
MAX_PATH_RADIUS_FT = 6.0
FLOW_WIDTH_PER_UNIT_FT = 0.15
LOOKOUT_PERIMETER_MARGIN_FT = 18.0   # 2 voxels
LOOKOUT_PLATFORM_HEIGHT_FT = 1.0
STALL_EPS_FRAC = 0.1                 # fraction of step_ft; skip a new node this close to its parent


@dataclass
class Attractor:
    x: float
    y: float
    strength: float
    motivator: str
    consumed: bool = False


@dataclass
class NetworkNode:
    id: int
    x: float
    y: float
    z_ft: float
    parent_id: int = None
    captured: int = 0
    flow: int = 0


def _voxel_at(engine, x, y):
    """Nearest-voxel lookup for an arbitrary real-feet (x, y) -- same grid
    convention every other real-feet -> voxel lookup in this pipeline uses."""
    gx = min(max(int(x // engine.voxel_ft), 0), engine.nx - 1)
    gy = min(max(int(y // engine.voxel_ft), 0), engine.nz - 1)
    return engine.voxels[gx][gy]


def _bucket_key(x, y, engine):
    bucket_ft = engine.voxel_ft * BUCKET_VOXELS
    return (int(x // bucket_ft), int(y // bucket_ft))


# Fixed built-amenity kinds (from TypologyAssetEngine.run()'s already-placed
# specs) treated as strong fixed attractors -- confirmed real props, not a
# diffuse field guess, so they get full strength regardless of the
# threshold that gates field-driven motivators.
_AMENITY_MOTIVATOR = {
    "fountain": "water", "water_plane": "water", "water_cascade_block": "water",
    "bench_assembly": "rest", "restroom_pod": "rest",
}


def sample_attraction_points(engine, typology_specs, motivator_weights=None,
                              field_threshold=FIELD_ATTRACTOR_THRESHOLD):
    """
    Builds a manageable (tens-to-~150-point) set of weighted, motivator-
    labeled Attractors from the same real per-voxel fields/placed amenities
    TerracingEngine/TypologyAssetEngine already compute -- NOT one point per
    voxel (2680 voxels would be far too dense/slow for the growth loop).

    Field-driven motivators (foot_traffic/deficit) and boolean-mask
    motivators (shade/rest) are bucketed into 27ft x 27ft cells
    (BUCKET_VOXELS * voxel_ft == STRUCTURAL_BAY_FT, reusing the same real
    structural-bay unit already load-bearing elsewhere in this pipeline)
    and deduped to one Attractor per non-empty bucket, at the bucket's
    survivor centroid. Already-placed amenity props are used directly as
    strong fixed attractors (see _AMENITY_MOTIVATOR above).
    """
    weights = {**DEFAULT_MOTIVATOR_WEIGHTS, **(motivator_weights or {})}
    buckets = {}  # (bucket_key, motivator) -> list of (wx, wy, value)

    for row in engine.voxels:
        for v in row:
            if v.foot_traffic_influence >= field_threshold:
                key = (_bucket_key(v.wx, v.wy, engine), "foot_traffic")
                buckets.setdefault(key, []).append((v.wx, v.wy, v.foot_traffic_influence))
            if v.deficit_influence >= field_threshold:
                key = (_bucket_key(v.wx, v.wy, engine), "deficit")
                buckets.setdefault(key, []).append((v.wx, v.wy, v.deficit_influence))
            if v.is_water_shade:
                key = (_bucket_key(v.wx, v.wy, engine), "shade")
                buckets.setdefault(key, []).append((v.wx, v.wy, 1.0))
            if v.is_amenity_resting:
                key = (_bucket_key(v.wx, v.wy, engine), "rest")
                buckets.setdefault(key, []).append((v.wx, v.wy, 1.0))

    attractors = []
    for (_key, motivator), samples in buckets.items():
        cx = sum(s[0] for s in samples) / len(samples)
        cy = sum(s[1] for s in samples) / len(samples)
        strength = max(s[2] for s in samples)
        attractors.append(Attractor(cx, cy, strength * weights.get(motivator, 1.0), motivator))

    for spec in typology_specs:
        motivator = _AMENITY_MOTIVATOR.get(spec.kind)
        if motivator is None:
            continue
        attractors.append(Attractor(spec.x_ft, spec.y_ft, 1.0 * weights.get(motivator, 1.0), motivator))

    return attractors


class CirculationNetworkEngine:
    """
    Space Colonization pedestrian-path growth engine. Single root at the
    real Metro station entrance (terracing_engine.entrance_x/entrance_y --
    real_geometry["secondary_entrance_anchor"]); grows toward the weighted
    attraction points sample_attraction_points() builds; classifies the
    resulting edges into real construction guidance (footpath/ramp/
    escalator, optionally "_bridge"-suffixed) plus lookout_point markers at
    qualifying leaf tips.
    """

    def __init__(self, real_geometry, terracing_engine, typology_specs,
                 motivator_weights=None, step_ft=DEFAULT_STEP_FT,
                 max_iterations=DEFAULT_MAX_ITERATIONS,
                 field_threshold=FIELD_ATTRACTOR_THRESHOLD):
        self.rg = real_geometry
        self.te = terracing_engine
        self.step_ft = step_ft
        self.max_iterations = max_iterations
        # attraction_radius/kill_radius are DERIVED from step_ft, never
        # independently exposed -- guarantees attraction_radius > kill_radius
        # always, which the algorithm requires (an attractor consumed
        # before any node ever grows toward it is a degenerate state a
        # naive three-independent-knob UI could otherwise produce).
        self.attraction_radius_ft = 3.0 * step_ft
        self.kill_radius_ft = 1.2 * step_ft

        self.attractors = sample_attraction_points(
            terracing_engine, typology_specs, motivator_weights, field_threshold)

        root_z = _voxel_at(terracing_engine, terracing_engine.entrance_x, terracing_engine.entrance_y).z_ft
        self.nodes = [NetworkNode(0, terracing_engine.entrance_x, terracing_engine.entrance_y, root_z)]

    def _grow(self):
        te = self.te
        for _ in range(self.max_iterations):
            active = [a for a in self.attractors if not a.consumed]
            if not active:
                break

            node_xy = np.array([[n.x, n.y] for n in self.nodes])
            attr_xy = np.array([[a.x, a.y] for a in active])
            dist = np.linalg.norm(attr_xy[:, None, :] - node_xy[None, :, :], axis=2)  # (K, M)
            nearest_idx = dist.argmin(axis=1)
            nearest_dist = dist[np.arange(len(active)), nearest_idx]

            assigned = {}
            for k, a in enumerate(active):
                if nearest_dist[k] <= self.attraction_radius_ft:
                    assigned.setdefault(int(nearest_idx[k]), []).append(a)

            if not assigned:
                # Bootstrap fallback: every node is farther than
                # attraction_radius_ft from every remaining attractor -- a
                # real condition at this site (the metro entrance root sits
                # ~180ft from the nearest meaningful attractor cluster,
                # farther than a typical step_ft's radius reaches). Rather
                # than silently stall at zero growth, reach directly toward
                # the single globally nearest attractor once, ignoring the
                # radius gate -- normal radius-gated colonization resumes
                # automatically next round once that reach has closed the
                # gap.
                k = int(nearest_dist.argmin())
                assigned[int(nearest_idx[k])] = [active[k]]

            new_nodes = []
            for node_idx, attrs in assigned.items():
                parent = self.nodes[node_idx]
                dx = dy = 0.0
                for a in attrs:
                    vx, vy = a.x - parent.x, a.y - parent.y
                    d = math.hypot(vx, vy) or 1e-6
                    dx += a.strength * vx / d
                    dy += a.strength * vy / d
                mag = math.hypot(dx, dy)
                closest = min(attrs, key=lambda a: math.hypot(a.x - parent.x, a.y - parent.y))
                if mag < 1e-6:
                    # Exactly-opposing attractors -- steer toward the single
                    # closest one instead of stalling; a real motivator
                    # can't cancel out to literally nothing and still be
                    # respected.
                    dx, dy = closest.x - parent.x, closest.y - parent.y
                    mag = math.hypot(dx, dy) or 1e-6
                new_x = min(max(parent.x + (dx / mag) * self.step_ft, 0.0), te.site_width_ft)
                new_y = min(max(parent.y + (dy / mag) * self.step_ft, 0.0), te.site_length_ft)

                # Near-cancelling (not exactly opposing) blended directions
                # can point somewhere that makes no real progress toward
                # ANY assigned attractor -- confirmed empirically: without
                # this guard, a node stuck between two flanking attractors
                # gets reassigned round after round with the identical
                # nearest-distance value, endlessly spawning dead-end
                # children instead of ever closing the gap. Fall back to
                # heading straight at the single closest attractor whenever
                # the blended step wouldn't even improve on that one.
                old_min = math.hypot(closest.x - parent.x, closest.y - parent.y)
                new_min = math.hypot(closest.x - new_x, closest.y - new_y)
                if new_min >= old_min:
                    fdx, fdy = closest.x - parent.x, closest.y - parent.y
                    fmag = math.hypot(fdx, fdy) or 1e-6
                    new_x = min(max(parent.x + (fdx / fmag) * self.step_ft, 0.0), te.site_width_ft)
                    new_y = min(max(parent.y + (fdy / fmag) * self.step_ft, 0.0), te.site_length_ft)

                if math.hypot(new_x - parent.x, new_y - parent.y) < STALL_EPS_FRAC * self.step_ft:
                    continue  # clamped back onto the parent (site edge) -- would be a zero-length stub
                new_id = len(self.nodes) + len(new_nodes)
                z = _voxel_at(te, new_x, new_y).z_ft
                new_nodes.append(NetworkNode(new_id, new_x, new_y, z, parent_id=parent.id))

            if not new_nodes:
                break  # nothing grew this round -> nothing will grow next round either
            self.nodes.extend(new_nodes)

            all_xy = np.array([[n.x, n.y] for n in self.nodes])
            for a in self.attractors:
                if a.consumed:
                    continue
                d = np.linalg.norm(all_xy - np.array([a.x, a.y]), axis=1)
                min_i = int(d.argmin())
                if d[min_i] <= self.kill_radius_ft:
                    a.consumed = True
                    self.nodes[min_i].captured += 1

    def _compute_flow(self):
        by_id = {n.id: n for n in self.nodes}
        for n in self.nodes:
            n.flow = n.captured
        for n in reversed(self.nodes):  # creation order is a valid reverse-topological order
            if n.parent_id is not None:
                by_id[n.parent_id].flow += n.flow

    @staticmethod
    def _grade_kind(grade):
        if grade <= FOOTPATH_MAX_GRADE:
            return "footpath"
        if grade <= RAMP_MAX_GRADE:
            return "ramp"
        return "escalator"

    def _is_bridge(self, parent, child):
        te = self.te
        for i in range(1, BRIDGE_SAMPLE_COUNT + 1):
            t = i / (BRIDGE_SAMPLE_COUNT + 1)
            x = parent.x + (child.x - parent.x) * t
            y = parent.y + (child.y - parent.y) * t
            deck_z = parent.z_ft + (child.z_ft - parent.z_ft) * t
            terrain_z = _voxel_at(te, x, y).z_ft
            if deck_z - terrain_z > BRIDGE_CLEARANCE_FT:
                return True
        return False

    def _classify_edges(self):
        by_id = {n.id: n for n in self.nodes}
        specs = []
        for n in self.nodes:
            if n.parent_id is None:
                continue
            parent = by_id[n.parent_id]
            run = math.hypot(n.x - parent.x, n.y - parent.y)
            grade = abs(n.z_ft - parent.z_ft) / max(run, 1e-6)
            kind = self._grade_kind(grade)
            if self._is_bridge(parent, n):
                kind += "_bridge"
            radius_ft = min(MAX_PATH_RADIUS_FT, BASE_PATH_RADIUS_FT + FLOW_WIDTH_PER_UNIT_FT * n.flow)
            spec = StructuralElement(kind, parent.x, parent.y, parent.z_ft, 0.0, radius_ft=radius_ft)
            spec.x2_ft, spec.y2_ft, spec.z2_ft = n.x, n.y, n.z_ft
            specs.append(spec)
        return specs

    def _detect_lookouts(self):
        te = self.te
        has_child = {n.parent_id for n in self.nodes if n.parent_id is not None}
        specs = []
        for n in self.nodes:
            if n.id in has_child or n.parent_id is None:
                continue  # not a leaf, or is the root itself
            near_perimeter = (
                n.x <= LOOKOUT_PERIMETER_MARGIN_FT or n.x >= te.site_width_ft - LOOKOUT_PERIMETER_MARGIN_FT or
                n.y <= LOOKOUT_PERIMETER_MARGIN_FT or n.y >= te.site_length_ft - LOOKOUT_PERIMETER_MARGIN_FT
            )
            near_deep_grotto = False
            v = _voxel_at(te, n.x, n.y)
            for ngx, ngy in ((v.gx + 1, v.gy), (v.gx - 1, v.gy), (v.gx, v.gy + 1), (v.gx, v.gy - 1)):
                if 0 <= ngx < te.nx and 0 <= ngy < te.nz:
                    nv = te.voxels[ngx][ngy]
                    if nv.typology == "GROTTO" and nv.level <= -2:
                        near_deep_grotto = True
                        break
            if near_perimeter or near_deep_grotto:
                specs.append(StructuralElement(
                    "lookout_point", n.x, n.y, n.z_ft + LOOKOUT_PLATFORM_HEIGHT_FT, LOOKOUT_PLATFORM_HEIGHT_FT))
        return specs

    def run(self):
        self._grow()
        self._compute_flow()
        return self._classify_edges() + self._detect_lookouts()
