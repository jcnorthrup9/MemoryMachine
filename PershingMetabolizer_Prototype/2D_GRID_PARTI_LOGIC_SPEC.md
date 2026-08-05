# Pershing Square 2D Grid / Parti Diagram — Generation Logic Spec

## Purpose

This documents the 2D site-parti generation logic built for the SCI-Arc thesis
Rhino model (`C:\Users\john\OneDrive - SCI-Arc\2026_Summer\Thesis\Rhino\`),
so it can be reimplemented for the Metabolizer app's own 2D diagram generator.
It's a layered stack — each step depends on the ones before it, all in one
shared 2D working frame (real feet, anchored to a specific real site column).

**Site-specific numbers below (ORIGIN, BOUNDARY_PTS, spacing) are from the
Rhino thesis model's own coordinate frame and boundary survey — they are NOT
directly transferable to the Metabolizer app's coordinate system.** The
Metabolizer's `index.html` already has its own site frame (`SITE_WIDTH_FT` /
`SITE_LENGTH_FT`, SW-corner origin, `real_geometry.json`-derived column
positions) — re-derive equivalent anchor/boundary/column values from that
data rather than reusing the numbers here. The *algorithms* are what's
portable; the constants are not.

**Notable existing overlap**: `index.html` already defines
`SITE_ROTATION_DEG = 36` for its sun/shade shadow casting ("DTLA street grid
runs 36° west-of-north from true north"). That is the exact same rotation
used below for the DTLA city grid relative to the column grid — the
Metabolizer app has already independently encoded half of this system for a
different purpose. Worth reconciling rather than re-deriving from scratch.

Two sections marked **[reconstructed]** below were only ever run as one-off
inline scripts during the Rhino session and were never saved to a file — the
algorithm description is precise (pulled from contemporaneous documentation)
but treat exact numeric outputs as a starting point to verify, not a spec to
match bit-for-bit.

---

## 0. Anchor point (ORIGIN)

Every step below shares one anchor: the real-world position of a specific
surveyed site column, used as the datum for grid rotation, seed-distance
falloff, and (later) canopy height. In the Rhino model this is the column at
the **Hill St / metro-entrance corner** (`ORIGIN = (319.89, 596.22)` in that
model's local frame) — chosen deliberately as the metro-adjacent corner, not
an arbitrary corner. For the Metabolizer app, the equivalent point is
`METRO_ENTRANCE` / `secondary_entrance_anchor`, already present in
`real_geometry.json` and used in `index.html`.

---

## 1. Shared grid-line builder (pure function, portable as-is)

Both the column grid and the DTLA grid are just two different parameter
calls into one function. This is the core reusable piece — copy the algorithm
directly, no adaptation needed beyond language syntax.

```python
def build_grid_lines(origin, spacing_u, spacing_v, angle_deg, boundary_pts, offset):
    """Return grid lines covering boundary_pts (expanded by offset), in a
    frame rotated angle_deg off world XY and anchored at origin.

    origin: (x, y) world point the grid is anchored to (a grid intersection).
    spacing_u, spacing_v: cell spacing along the grid's own two local axes.
    angle_deg: rotation of the grid's local frame off world XY, degrees.
    boundary_pts: list of (x, y) world points describing the region to
        cover (e.g. a site boundary polygon) - need not be axis-aligned.
    offset: distance to expand the boundary's local bounding box on all
        sides before generating lines.

    Returns a list of (start_pt, end_pt, axis, index) tuples in world xy,
    where axis is "U" (line of constant local-u) or "V" (constant local-v).
    """
    ox, oy = origin
    theta = radians(angle_deg)
    cos_t, sin_t = cos(theta), sin(theta)

    def to_local(x, y):
        dx, dy = x - ox, y - oy
        return (dx * cos_t + dy * sin_t, -dx * sin_t + dy * cos_t)

    def to_world(lu, lv):
        return (ox + lu * cos_t - lv * sin_t, oy + lu * sin_t + lv * cos_t)

    local_pts = [to_local(x, y) for x, y in boundary_pts]
    us = [p[0] for p in local_pts]
    vs = [p[1] for p in local_pts]
    min_u, max_u = min(us) - offset, max(us) + offset
    min_v, max_v = min(vs) - offset, max(vs) + offset

    lines = []

    n_lo, n_hi = ceil(min_u / spacing_u), floor(max_u / spacing_u)
    for n in range(n_lo, n_hi + 1):
        u = n * spacing_u
        lines.append((to_world(u, min_v), to_world(u, max_v), "U", n))

    m_lo, m_hi = ceil(min_v / spacing_v), floor(max_v / spacing_v)
    for m in range(m_lo, m_hi + 1):
        v = m * spacing_v
        lines.append((to_world(min_u, v), to_world(max_u, v), "V", m))

    return lines
```

Key idea: rotate the boundary into the grid's own local frame, find the
integer line-index range that covers it (plus the offset margin), generate
lines at each integer multiple of the spacing, convert back to world space.
Each returned line carries its axis (`U`/`V`) and integer index — later steps
(seeds) reuse this tag.

---

## 2. Column grid (orthogonal)

`build_grid_lines(ORIGIN, 27.0, 27.0, 0.4, BOUNDARY_PTS, 9.0)`

- **Spacing**: 27ft both axes — a 9×3 parking-stall bay module, not
  arbitrary.
- **Rotation**: a *small real rotation* measured from the as-built column
  survey (~0.4°, could be exactly 0° for a from-scratch site — the Rhino
  model kept it deliberately as a trace of as-surveyed vs. idealized
  geometry; a design choice, not a requirement).
- **Boundary offset**: 9ft overhang past the site boundary, expanded in the
  grid's own rotated local frame (not a naive world-axis bbox expand).
- Result in the Rhino model: 13 × 23 = 299 lines lines, matching a real
  13×23 column survey grid.

## 3. DTLA city grid

`build_grid_lines(ORIGIN, 336.0, 600.0, 36.4, BOUNDARY_PTS, 9.0)`

- **Spacing**: 336ft × 600ft — the real 1849 Ord Survey block module (112×200
  yards). If the Metabolizer site isn't in this survey system, substitute
  whatever real large-scale city grid module applies, or omit this layer.
- **Rotation**: 36° off the *column grid* (not off world directly) → 36.4°
  off world total (36 + the column grid's own 0.4° drift). **This 36° is the
  same number already in `index.html`'s `SITE_ROTATION_DEG`.**
- Same `ORIGIN`, same 9ft boundary-offset convention.
- At a site this size relative to a 336×600ft module, expect only a
  handful of lines (a couple of diagonals crossing the site), not a fine
  mesh — that's expected, not a bug.

---

## 4. Parti seeds (grid-collision points)

Pairwise line-segment intersection between **every column-grid line** and
**every DTLA-grid line** (standard 2D parametric line intersection),
deduplicated within a small tolerance (0.05ft in the Rhino model — raw
crossings collapse where multiple lines meet near the anchor point). Each
seed retains which grid line (axis + integer index) it came from, reused by
later steps. In the Rhino model this produced 55 seed points from 36 column
lines × 3 DTLA lines.

Standard segment-segment intersection (not full-line — clip to each
segment's own extent):

```python
def segment_intersection(p1, p2, p3, p4):
    """p1-p2 and p3-p4 are (x,y) segment endpoints. Returns (x,y) if the
    segments actually cross within both their extents, else None."""
    x1, y1 = p1; x2, y2 = p2; x3, y3 = p3; x4, y4 = p4
    denom = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
    if abs(denom) < 1e-12:
        return None  # parallel (or collinear) - no single intersection
    t = ((x1 - x3) * (y3 - y4) - (y1 - y3) * (x3 - x4)) / denom
    u = ((x1 - x3) * (y1 - y2) - (y1 - y3) * (x1 - x2)) / denom
    if 0 <= t <= 1 and 0 <= u <= 1:
        return (x1 + t * (x2 - x1), y1 + t * (y2 - y1))
    return None
```

Dedup pass: sort/bucket candidate points, merge any within tolerance of each
other into a single seed (keep one representative position).

---

## 5. Threshold markers + warped grid lines **[reconstructed]**

Two outputs from the seed set:

**Markers**: each seed gets a small circle + crosshair marker aligned to the
DTLA axis rotation (36.4° in the Rhino model) — a "survey monument" reading
that marks the collision without implying physical program. (Rhino model:
3ft circle radius, 165 total marker objects = 55 seeds × 3 sub-elements each.)

**Warped lines**: the DTLA grid lines are resampled at a fixed step interval
(~3ft in the Rhino model) into a polyline of closely-spaced points. Each
sample point is pushed away from *every* seed within a falloff radius — force
accumulates across all seeds in range, not just the nearest one:

```python
def warp_point(pt, seeds, anchor):
    x, y = pt
    for seed in seeds:
        sx, sy = seed.x, seed.y
        d = hypot(x - sx, y - sy)
        # both maxRadius and maxForce fade with the SEED's own distance
        # from the anchor point (closer to anchor = stronger repulsion) -
        # this is a property of the seed, computed once, not per-sample
        max_radius = seed.max_radius   # e.g. fades ~32 -> ~18 with anchor distance
        max_force  = seed.max_force    # e.g. fades ~16 -> ~6 with anchor distance
        if d < max_radius:
            force = lerp(max_force, 0, d / max_radius)   # force decays to 0 at max_radius
            angle = atan2(y - sy, x - sx)
            x += cos(angle) * force
            y += sin(angle) * force
    return (x, y)
```

The per-seed `max_radius`/`max_force` fade is a linear map from each seed's
distance-from-anchor (0 = at anchor, max = farthest seed) onto a chosen
range — in the Rhino model tuned so the max deviation from a straight line
lands around 7–9ft (subtle at full-site zoom, by design — adjust to taste
for the target diagram scale). This exact force-accumulation pattern also
appears in the standalone Processing sketch found in this repo at
`Processing/gridSketch1/GridCollisionSandboxVolumetri.txt` (see its
`maxRadius`/`maxForce` `map()` calls) — that file is a close relative of
this same idea and may be a useful second reference.

---

## 6. Behavior B — recursive subdivision **[reconstructed]**

The column grid divides the site into an (N-1)×(M-1) cell field (one fewer
than the line count in each direction — 12×22 in the Rhino model, from 13×23
lines). For every seed, mark the two cells straddling its grid line (a seed
sitting on a V-line straddles the two cells at that V-index; a seed on a
U-line straddles the two at that U-index). Rhino model: 47 unique marked
cells out of 264 total.

Each marked cell gets a 4×4 sub-grid inside it (3 internal lines each
direction, i.e. divide the cell into 4 equal sub-cells): 6 lines per cell ×
47 cells = 282 lines total.

```python
def subdivide_cell(cell_min, cell_max, n_subdivisions=4):
    """Returns internal line segments splitting the cell into n_subdivisions
    equal parts each direction (n_subdivisions - 1 internal lines per axis)."""
    lines = []
    w = cell_max.x - cell_min.x
    h = cell_max.y - cell_min.y
    for i in range(1, n_subdivisions):
        x = cell_min.x + w * i / n_subdivisions
        lines.append(((x, cell_min.y), (x, cell_max.y)))
    for j in range(1, n_subdivisions):
        y = cell_min.y + h * j / n_subdivisions
        lines.append(((cell_min.x, y), (cell_max.x, y)))
    return lines
```

## 7. Behavior A — Voronoi webbing **[reconstructed]**

Same 47 marked cells as Behavior B, an alternate treatment. Per cell:

1. Build a regular 3×3 point grid inside the cell (9 points, evenly spaced).
2. Jitter each point ±half-spacing per axis using a **deterministic PRNG
   keyed by cell index** (reproducible across runs — not `Math.random()`).
   The Rhino model used mulberry32; standard JS implementation:

```javascript
function mulberry32(seed) {
  return function () {
    seed |= 0; seed = (seed + 0x6D2B79F5) | 0;
    let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}
// usage: const rand = mulberry32(cellIndex); const jitterX = (rand()*2-1) * halfSpacing;
```

3. For each jittered point, build its Voronoi region by half-plane clipping
   (Sutherland-Hodgman) of the cell's own bounding square against the
   perpendicular bisector of every *other* point in the cell:

```python
def clip_halfplane(polygon, keep_side_pt, other_pt):
    """Sutherland-Hodgman clip of polygon against the perpendicular
    bisector of (keep_side_pt, other_pt), keeping the half-plane closer
    to keep_side_pt."""
    A, B = keep_side_pt, other_pt
    mx, my = (A[0] + B[0]) / 2, (A[1] + B[1]) / 2
    nx, ny = A[0] - B[0], A[1] - B[1]   # normal pointing toward A

    def inside(p):
        return (p[0] - mx) * nx + (p[1] - my) * ny >= 0

    def intersect(p, q):
        # line-segment p-q against the bisector line
        d1 = (p[0] - mx) * nx + (p[1] - my) * ny
        d2 = (q[0] - mx) * nx + (q[1] - my) * ny
        t = d1 / (d1 - d2)
        return (p[0] + t * (q[0] - p[0]), p[1] + t * (q[1] - p[1]))

    out = []
    n = len(polygon)
    for i in range(n):
        cur, nxt = polygon[i], polygon[(i + 1) % n]
        cur_in, nxt_in = inside(cur), inside(nxt)
        if cur_in:
            out.append(cur)
            if not nxt_in:
                out.append(intersect(cur, nxt))
        elif nxt_in:
            out.append(intersect(cur, nxt))
    return out
```

4. Only keep **interior** edges (edges not lying on the cell's own boundary)
   — those are the shared boundaries between neighboring point regions
   within the cell; drop edges that coincide with the outer cell square.
   Rhino model result: 763 total interior edges across 47 cells.

---

## 8. Canopy height field (extends into 3D — optional for a purely 2D diagram)

The first genuinely 3D layer in the Rhino model; skip if the Metabolizer
diagram stays flat. Height at any point, driven by distance to the nearest
seed:

```python
def smoothstep(t):
    t = max(0.0, min(1.0, t))
    return t * t * (3.0 - 2.0 * t)

def height_field(pt, seeds, min_h, max_h, radius):
    """Height at pt=(x,y): lowest near the nearest seed, opening up to
    max_h beyond radius."""
    x, y = pt
    d_min = min(hypot(x - sx, y - sy) for sx, sy in seeds)
    t = smoothstep(d_min / radius)
    return min_h + (max_h - min_h) * t
```

Rhino model parameters: `MIN_H = 9ft` (walkable clearance) at a seed, opening
to `MAX_H = 24ft` by `RADIUS = 54ft` (2 column bays) away. Sampled at real
column centers (299 of them), not a new lattice.

---

## Source files (Rhino thesis model, for reference / verification)

- `Rhino/scripts/grid_common.py` — §1 (`build_grid_lines`), verbatim above.
- `Rhino/scripts/grid_ortho.py` — §2 params.
- `Rhino/scripts/grid_dtla.py` — §3 params.
- `Rhino/scripts/canopy_height_field.py` — §8, verbatim above.
- `Rhino/GRID_LOGIC_AND_MODEL_ALGORITHMS.md` — prose source for the
  **[reconstructed]** sections (§5–7), plus the 3D pedestal-model logic
  (not relevant to a 2D diagram generator, omitted here).
