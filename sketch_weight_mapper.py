"""
Memory Machine -- Sketch Weight Mapper (design-agency input, Phase 2 extension).

Reads a designer-drawn sketch (SVG or raster image) and maps it onto
terracing_engine.py's voxel grid as a normalized weight matrix: 1.0 directly
on a sketched line, falling off smoothly with distance, ~0 a few voxel
widths away. Feed the result into TerracingEngine(sketch_weights=...) --
see that module's `_effective_influence` for how it's blended (ADDITIVELY,
not just masking/suppressing -- per project decision 2026-07-03, the sketch
can create real excavation somewhere the transit-proximity data alone
wouldn't, since the whole point is designer agency over the automated
process, not just editing its output).

Scope (per project decision 2026-07-03): PLAN sketches only. A SECTION
sketch (drawing a depth profile directly) is a different, bigger feature --
the engine computes a single z per (x,y) column from a formula, so a section
sketch would mean overriding that z directly along a cutline, not blending a
0..1 weight. Not attempted here; a separate mechanism if/when built.

Coordinate convention -- VERIFIED 2026-07-04 against a real hand-drawn,
hand-labeled test sketch (data/sketches/b84c0d16-....jpg, the sketch itself
had "HILL"/"OLIVE"/"6th"/"5th" written on it): HILL was on the LEFT, OLIVE on
the RIGHT, "6th" at TOP, "5th" at BOTTOM -- a 180-degree rotation from the
"5thup" plan convention this pipeline otherwise treats as correct (Hill on
the right, 5th on top -- see vector_export.py). So both axes are flipped
here relative to a naive top-left-origin reading of the sketch. This is
confirmed for that one physical sketch's drawing habit -- if a future sketch
is oriented differently (or its own labels say otherwise), this default
needs revisiting; don't assume it generalizes blindly.
"""
import os
import numpy as np


def _falloff_weights(distances_ft, voxel_ft, falloff_scale_ft=None):
    """
    1.0 within half a voxel-width of the nearest sketch point, exponential
    decay beyond that. A smooth continuous curve rather than the blueprint's
    literal discrete "1.0 / 0.7 / 0.4 / 0.0" steps, to avoid visible banding
    in the resulting weight field.
    """
    if falloff_scale_ft is None:
        falloff_scale_ft = voxel_ft * 1.5
    return np.where(
        distances_ft <= voxel_ft / 2,
        1.0,
        np.exp(-(distances_ft - voxel_ft / 2) / falloff_scale_ft),
    )


def _rasterize_points_to_grid(points_xy, nx, nz, voxel_ft, falloff_scale_ft=None, chunk_size=2000):
    """
    points_xy: (N, 2) array of site-local (x, y) points sampled along the
    sketch. Returns an (nx, nz) weight grid matching TerracingEngine's voxel
    indexing (cell (gx, gy) center = ((gx+0.5)*voxel_ft, (gy+0.5)*voxel_ft)).
    Chunked distance computation so a dense sketch (many sample points)
    doesn't force one huge (nx*nz, N) matrix into memory at once.
    """
    if len(points_xy) == 0:
        return np.zeros((nx, nz))

    points_xy = np.asarray(points_xy, dtype=float)
    gx_centers = (np.arange(nx) + 0.5) * voxel_ft
    gy_centers = (np.arange(nz) + 0.5) * voxel_ft
    gxx, gyy = np.meshgrid(gx_centers, gy_centers, indexing="ij")
    grid_pts = np.stack([gxx.ravel(), gyy.ravel()], axis=1)  # (nx*nz, 2)

    min_dist = np.full(grid_pts.shape[0], np.inf)
    for i in range(0, len(points_xy), chunk_size):
        pts = points_xy[i:i + chunk_size]
        d = np.hypot(
            grid_pts[:, 0:1] - pts[:, 0][None, :],
            grid_pts[:, 1:2] - pts[:, 1][None, :],
        )
        min_dist = np.minimum(min_dist, d.min(axis=1))

    weights = _falloff_weights(min_dist, voxel_ft, falloff_scale_ft)
    return weights.reshape(nx, nz)


def load_svg_sketch(svg_path, site_width_ft, site_length_ft, sample_step_ft=1.0, flip_x=True, flip_y=True):
    """
    Parse a designer sketch SVG -- real bezier curves, not just the simple
    straight polylines structural_grid_analyzer.py's regex parser handles
    (that one only ever needed to read clean Rhino CAD exports) -- and
    return site-local (x, y) sample points spaced ~sample_step_ft apart
    along every path. Uses svgpathtools for correct curve sampling.
    `flip_x`/`flip_y`: see module docstring -- defaults match the one real
    sketch calibrated so far; an SVG drawn directly (not photographed) may
    not share that convention, override if so.
    """
    import svgpathtools

    paths, _attributes, svg_attributes = svgpathtools.svg2paths2(svg_path)

    if "viewBox" in svg_attributes:
        min_x, min_y, w, h = (float(v) for v in svg_attributes["viewBox"].split())
    else:
        bboxes = [p.bbox() for p in paths if len(p) > 0]
        if not bboxes:
            return np.zeros((0, 2))
        min_x = min(b[0] for b in bboxes)
        max_x = max(b[1] for b in bboxes)
        min_y = min(b[2] for b in bboxes)
        max_y = max(b[3] for b in bboxes)
        w, h = max_x - min_x, max_y - min_y

    scale_x = site_width_ft / w
    scale_y = site_length_ft / h

    points = []
    for path in paths:
        length = path.length()
        if length <= 0:
            continue
        n_samples = max(2, int(length / (sample_step_ft / min(scale_x, scale_y))))
        for i in range(n_samples + 1):
            pt = path.point(i / n_samples)
            fx = (pt.real - min_x) / w
            fy = (pt.imag - min_y) / h
            if flip_x:
                fx = 1.0 - fx
            if flip_y:
                fy = 1.0 - fy
            points.append((fx * site_width_ft, fy * site_length_ft))

    return np.array(points) if points else np.zeros((0, 2))


def _detect_photo_border(gray_arr, dark_threshold=100, margin_frac=0.15):
    """
    Auto-detect a hand-drawn rectangular border in a photographed sketch, by
    finding the row/column with the most dark ("ink") pixels within the
    outer margin_frac of each edge -- assumes the border sits somewhere in
    the outer ~15% of the frame, with any photo/table background artifacts
    further out still (a wood-grain table edge, a stray pen, the photo's
    own edge). Returns (left, top, right, bottom) pixel bounds.

    This is a heuristic, tuned and verified against exactly one real
    photographed sketch (2026-07-04) -- confirm it still finds the right
    lines as more/differently-composed sketches come in; it is not a
    general-purpose document scanner.
    """
    h, w = gray_arr.shape
    dark = gray_arr < dark_threshold
    my = int(h * margin_frac)
    mx = int(w * margin_frac)

    row_sums = dark[:, mx:w - mx].sum(axis=1)
    col_sums = dark[my:h - my, :].sum(axis=0)

    top = int(np.argmax(row_sums[:2 * my]))
    bottom = int(np.argmax(row_sums[h - 2 * my:]) + (h - 2 * my))
    left = int(np.argmax(col_sums[:2 * mx]))
    right = int(np.argmax(col_sums[w - 2 * mx:]) + (w - 2 * mx))
    return left, top, right, bottom


def load_image_sketch(image_path, site_width_ft, site_length_ft, threshold=100,
                       sample_stride=4, flip_x=True, flip_y=True,
                       auto_crop_border=False, exclude_red=True, crop_box=None):
    """
    Threshold a raster sketch (photo or PNG/JPG) to find drawn pixels, map
    them to site-local (x, y) points.

    Working convention as of 2026-07-04: the USER crops the photo down to
    (roughly) the drawn border before saving it, so the whole image is
    treated as the site bounds by default (auto_crop_border=False) -- no
    guessing needed. `_detect_photo_border`'s automatic version exists and
    can still be opted into (auto_crop_border=True) or given an explicit
    `crop_box=(left, top, right, bottom)`, but on the one real test sketch
    so far it picked up wood-table-grain/photo-edge artifacts instead of the
    real border -- not trustworthy yet without more examples. A more
    reliable long-term fix discussed with the user: draw the border in a
    distinct color (e.g. blue) so it can be found by color instead of by
    guessing from ink density -- not built yet, cropping is the interim plan.

    `exclude_red`: if True (default), treats red pen/highlighter marks as
    NOT part of the design-intent signal -- on the one real test sketch,
    red marks traced over/emphasized the site's own boundary edges rather
    than indicating new excavation paths. If red is meant to carry design
    intent on a future sketch, pass False.

    Prefers the alpha channel if the image has one (a transparent PNG with
    just a drawn stroke gives a much cleaner signal than thresholding a
    flattened image); otherwise treats dark, non-red pixels as the drawn line.
    `sample_stride`: only sample every Nth pixel in each axis, for speed.
    """
    from PIL import Image

    img = Image.open(image_path)

    if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
        rgba = np.array(img.convert("RGBA"))
        if crop_box is None and auto_crop_border:
            gray_full = np.array(img.convert("L"))
            crop_box = _detect_photo_border(gray_full, threshold)
        if crop_box is not None:
            l, t, r, b = crop_box
            rgba = rgba[t:b, l:r]
        mask = rgba[:, :, 3] > threshold
    else:
        rgb = np.array(img.convert("RGB")).astype(int)
        if crop_box is None and auto_crop_border:
            gray_full = np.array(img.convert("L"))
            crop_box = _detect_photo_border(gray_full, threshold)
        if crop_box is not None:
            l, t, r, b = crop_box
            rgb = rgb[t:b, l:r]
        r_ch, g_ch, b_ch = rgb[:, :, 0], rgb[:, :, 1], rgb[:, :, 2]
        mask = (r_ch < threshold) & (g_ch < threshold) & (b_ch < threshold)
        if exclude_red:
            is_reddish = (r_ch - g_ch > 40) & (r_ch - b_ch > 40)
            mask = mask & ~is_reddish

    sub = mask[::sample_stride, ::sample_stride]
    ys, xs = np.where(sub)
    xs = xs * sample_stride
    ys = ys * sample_stride
    h, w = mask.shape
    if h == 0 or w == 0 or len(xs) == 0:
        return np.zeros((0, 2))

    fx = xs / w
    fy = ys / h
    if flip_x:
        fx = 1.0 - fx
    if flip_y:
        fy = 1.0 - fy

    return np.column_stack([fx * site_width_ft, fy * site_length_ft])


def find_latest_sketch(folder=r"D:\MemoryMachine\data\sketches"):
    """Return the most recently modified sketch file (.svg/.png/.jpg/.jpeg) in `folder`, or None."""
    exts = (".svg", ".png", ".jpg", ".jpeg")
    candidates = [
        os.path.join(folder, f) for f in os.listdir(folder)
        if f.lower().endswith(exts)
    ]
    if not candidates:
        return None
    return max(candidates, key=os.path.getmtime)


def build_sketch_weights(engine, svg_path=None, image_path=None, use_latest=False,
                          sketches_folder=r"D:\MemoryMachine\data\sketches",
                          sample_step_ft=1.0, threshold=100, falloff_scale_ft=None,
                          flip_x=True, flip_y=True, **image_kwargs):
    """
    Build an (engine.nx, engine.nz) sketch-weight grid, ready to pass as
    TerracingEngine(sketch_weights=...). Pass exactly one of svg_path,
    image_path, or use_latest=True (pulls the newest file from
    sketches_folder, dispatching on its extension).

    `flip_x`/`flip_y`: forwarded to whichever loader is actually used
    (load_svg_sketch or load_image_sketch), both of which default to
    True/True per the module docstring's verified convention -- override
    here if a given sketch doesn't match it.

    BUGFIX 2026-07-05: previously this function only forwarded flip_x/
    flip_y for the image path (via **image_kwargs) -- the SVG branch called
    load_svg_sketch() without them, so an SVG sketch had no way to override
    the flip convention even though load_svg_sketch's signature supports
    it. Now both branches take the same explicit params. Default behavior
    (flip_x=True, flip_y=True) is unchanged for existing callers.
    """
    n_given = sum(x is not None for x in (svg_path, image_path)) + int(use_latest)
    if n_given != 1:
        raise ValueError("pass exactly one of svg_path, image_path, or use_latest=True")

    if use_latest:
        latest = find_latest_sketch(sketches_folder)
        if latest is None:
            raise FileNotFoundError(f"no sketch files found in {sketches_folder}")
        if latest.lower().endswith(".svg"):
            svg_path = latest
        else:
            image_path = latest

    if svg_path is not None:
        points = load_svg_sketch(svg_path, engine.site_width_ft, engine.site_length_ft,
                                  sample_step_ft, flip_x=flip_x, flip_y=flip_y)
    else:
        points = load_image_sketch(image_path, engine.site_width_ft, engine.site_length_ft,
                                    threshold, flip_x=flip_x, flip_y=flip_y, **image_kwargs)

    return _rasterize_points_to_grid(points, engine.nx, engine.nz, engine.voxel_ft, falloff_scale_ft)


# ---------------------------------------------------------------------------
# Stage 2: "blue = hardscape/protect" filled-region detection.
#
# Black lines (above) are a falloff signal -- 1.0 on the line, decaying with
# distance. A blue mark means something categorically different: a *closed
# region claim* ("everything inside this boundary is hardscape, protect it"),
# not a line to measure distance from. So this needs region/fill detection,
# not point-distance rasterization -- hence the separate functions below
# rather than reusing _rasterize_points_to_grid.
#
# UNVERIFIED as of 2026-07-05: there is no real designer sketch with blue
# marks in data/sketches/ yet -- the only real sketch on hand
# (b84c0d16-....jpg, see module docstring) is black-line-only. Everything
# below is only checked against synthetic test input (see bottom of this
# file / the task report), the same way the black-line ingestion above was
# first checked against a synthetic image before any real sketch existed.
# Treat the mechanics as working, NOT the color thresholds/tolerances as
# tuned for a real hand-drawn or photographed blue mark.
# ---------------------------------------------------------------------------


def _fill_holes(mask):
    """
    Pure-BFS "fill holes": given a 2D bool array, returns `mask` plus any
    False pixels fully enclosed by True ones (i.e. NOT 4-connected-reachable
    from the array border while staying on False pixels) -- the same result
    scipy.ndimage.binary_fill_holes would give. Implemented by hand instead
    of importing scipy: scipy is not a declared dependency of this project
    (checked requirements.txt 2026-07-05, only fastapi/uvicorn/pydantic are
    listed) and no other module here imports it, so this avoids adding a new
    dependency for one function. Fine at sketch-photo resolution; a full
    scan-line/union-find approach would be needed if this ever runs on much
    larger rasters.
    """
    from collections import deque

    h, w = mask.shape
    outside = np.zeros((h, w), dtype=bool)
    q = deque()

    for x in range(w):
        for y in (0, h - 1):
            if not mask[y, x] and not outside[y, x]:
                outside[y, x] = True
                q.append((y, x))
    for y in range(h):
        for x in (0, w - 1):
            if not mask[y, x] and not outside[y, x]:
                outside[y, x] = True
                q.append((y, x))

    while q:
        y, x = q.popleft()
        for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            ny, nx_ = y + dy, x + dx
            if 0 <= ny < h and 0 <= nx_ < w and not mask[ny, nx_] and not outside[ny, nx_]:
                outside[ny, nx_] = True
                q.append((ny, nx_))

    return mask | ~outside


def _label_regions(mask):
    """
    Hand-rolled 4-connected component labeling (BFS flood fill) -- stands in
    for scipy.ndimage.label without adding scipy as a dependency (see
    _fill_holes above for why). Returns a list of (ys, xs) pixel-index
    arrays, one per disjoint True-region in `mask`.
    """
    from collections import deque

    h, w = mask.shape
    visited = np.zeros((h, w), dtype=bool)
    regions = []
    ys_all, xs_all = np.where(mask)

    for y0, x0 in zip(ys_all.tolist(), xs_all.tolist()):
        if visited[y0, x0]:
            continue
        visited[y0, x0] = True
        q = deque([(y0, x0)])
        pixels = []
        while q:
            y, x = q.popleft()
            pixels.append((y, x))
            for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                ny, nx_ = y + dy, x + dx
                if 0 <= ny < h and 0 <= nx_ < w and mask[ny, nx_] and not visited[ny, nx_]:
                    visited[ny, nx_] = True
                    q.append((ny, nx_))
        pixels = np.array(pixels)
        regions.append((pixels[:, 0], pixels[:, 1]))

    return regions


def find_color_regions(image_path, site_width_ft, site_length_ft, nx, nz, voxel_ft,
                        color="blue", threshold=40, sample_stride=4,
                        flip_x=True, flip_y=True, min_region_px=25):
    """
    Detect filled/closed ink regions of `color` in a raster sketch -- the
    raster-side half of Stage-2 "blue = hardscape/protect" (see the block
    comment above this function for background).

    Handles both a solid-filled blue blob AND a blue outline around an
    otherwise-white interior the same way: `_fill_holes` closes any
    background pixels enclosed by the colored pixels, so a hollow outline
    and a solid fill produce the same region. (If the outline has a gap --
    not actually closed -- fill will "leak" out and no region is found for
    it; that is a real, not-yet-handled limitation, see report.)

    `color`: "blue" or "red" (channel-difference thresholding, matching the
    style of load_image_sketch's exclude_red logic) or an explicit (r, g, b)
    tuple (near-match within `threshold` per channel).

    Returns a list of {"type": "hardscape", "mask": <bool (nx, nz) array>}
    dicts, one per disjoint region found. `mask[gx, gy]` is True if that
    grid cell (same voxel indexing as TerracingEngine / _rasterize_points_to_grid,
    cell (gx, gy) spans [gx*voxel_ft, (gx+1)*voxel_ft) x [gy*voxel_ft,
    (gy+1)*voxel_ft)) contains at least one region pixel, after applying the
    same flip_x/flip_y + site-scaling convention as load_image_sketch.

    `min_region_px`: drop regions smaller than this many (downsampled)
    pixels -- a noise/JPEG-artifact filter, analogous in spirit to
    exclude_red, not verified against a real photographed blue mark.
    """
    from PIL import Image

    img = Image.open(image_path).convert("RGB")
    rgb = np.array(img).astype(int)
    rgb = rgb[::sample_stride, ::sample_stride]
    r_ch, g_ch, b_ch = rgb[:, :, 0], rgb[:, :, 1], rgb[:, :, 2]

    if color == "blue":
        color_mask = (b_ch - r_ch > threshold) & (b_ch - g_ch > threshold)
    elif color == "red":
        color_mask = (r_ch - g_ch > threshold) & (r_ch - b_ch > threshold)
    else:
        cr, cg, cb = color
        color_mask = (
            (np.abs(r_ch - cr) < threshold)
            & (np.abs(g_ch - cg) < threshold)
            & (np.abs(b_ch - cb) < threshold)
        )

    if not color_mask.any():
        return []

    filled = _fill_holes(color_mask)
    h, w = filled.shape

    results = []
    for ys, xs in _label_regions(filled):
        if len(ys) < min_region_px:
            continue

        fx = xs.astype(float) / w
        fy = ys.astype(float) / h
        if flip_x:
            fx = 1.0 - fx
        if flip_y:
            fy = 1.0 - fy
        x_ft = fx * site_width_ft
        y_ft = fy * site_length_ft

        gx_idx = np.clip((x_ft / voxel_ft).astype(int), 0, nx - 1)
        gy_idx = np.clip((y_ft / voxel_ft).astype(int), 0, nz - 1)
        mask = np.zeros((nx, nz), dtype=bool)
        mask[gx_idx, gy_idx] = True
        results.append({"type": "hardscape", "mask": mask})

    return results


def _points_in_polygon(polygon_xy, test_pts):
    """
    Vectorized even-odd-rule point-in-polygon test (ray casting), hand-
    written instead of pulling in matplotlib.path/shapely -- neither is a
    project dependency and this is a small, standard algorithm.
    `polygon_xy`: (P, 2) vertex loop (site-local ft). `test_pts`: (N, 2)
    points to test. Returns an (N,) bool array.
    """
    poly = np.asarray(polygon_xy, dtype=float)
    x, y = test_pts[:, 0], test_pts[:, 1]
    inside = np.zeros(len(test_pts), dtype=bool)
    n = len(poly)
    j = n - 1
    for i in range(n):
        xi, yi = poly[i]
        xj, yj = poly[j]
        dy = yj - yi
        dy = dy if dy != 0 else 1e-12
        cond = ((yi > y) != (yj > y)) & (x < (xj - xi) * (y - yi) / dy + xi)
        inside ^= cond
        j = i
    return inside


def find_closed_svg_regions(svg_path, site_width_ft, site_length_ft, nx, nz, voxel_ft,
                             sample_step_ft=1.0, flip_x=True, flip_y=True,
                             close_tol_frac=0.01):
    """
    Detect CLOSED subpaths in a sketch SVG as hardscape/protect region
    boundaries -- the SVG-side half of Stage-2 "blue = hardscape" (see the
    block comment above find_color_regions for background). Unlike the
    raster case there is no ink color to key off of here; "closed" is the
    signal instead -- a subpath whose start and end points are within
    `close_tol_frac` of the sketch's own bounding-box diagonal of each
    other counts as a claimed region, not a line. The tolerance is looser
    than requiring an exact SVG "Z" close command, since a hand-drawn-then-
    traced path may not emit one even when visually closed.

    Returns a list of {"type": "hardscape", "mask": <bool (nx, nz) array>}
    dicts, one per closed subpath, built by testing every grid-cell center
    against the subpath's sampled polygon with `_points_in_polygon` (same
    even-odd ray-cast used for both SVG and, indirectly, the raster case).
    Grid centers use `voxel_ft` directly (not site_width_ft / nx), matching
    how TerracingEngine actually places cell (gx, gy) at ((gx+0.5)*voxel_ft,
    (gy+0.5)*voxel_ft) -- nx = ceil(site_width_ft / voxel_ft), so the two
    are not interchangeable near the far edge.
    """
    import svgpathtools

    paths, _attributes, svg_attributes = svgpathtools.svg2paths2(svg_path)

    if "viewBox" in svg_attributes:
        min_x, min_y, w, h = (float(v) for v in svg_attributes["viewBox"].split())
    else:
        bboxes = [p.bbox() for p in paths if len(p) > 0]
        if not bboxes:
            return []
        min_x = min(b[0] for b in bboxes)
        max_x = max(b[1] for b in bboxes)
        min_y = min(b[2] for b in bboxes)
        max_y = max(b[3] for b in bboxes)
        w, h = max_x - min_x, max_y - min_y

    diag = float(np.hypot(w, h))
    scale_x = site_width_ft / w
    scale_y = site_length_ft / h

    gx_centers = (np.arange(nx) + 0.5) * voxel_ft
    gy_centers = (np.arange(nz) + 0.5) * voxel_ft
    gxx, gyy = np.meshgrid(gx_centers, gy_centers, indexing="ij")
    grid_pts = np.stack([gxx.ravel(), gyy.ravel()], axis=1)

    results = []
    for path in paths:
        for sub in path.continuous_subpaths():
            length = sub.length()
            if length <= 0:
                continue
            start, end = sub.point(0), sub.point(1)
            if abs(start - end) > close_tol_frac * diag:
                continue  # not closed -- a line, not a region claim; skip

            n_samples = max(8, int(length / (sample_step_ft / min(scale_x, scale_y))))
            poly = []
            for i in range(n_samples):
                pt = sub.point(i / n_samples)
                fx = (pt.real - min_x) / w
                fy = (pt.imag - min_y) / h
                if flip_x:
                    fx = 1.0 - fx
                if flip_y:
                    fy = 1.0 - fy
                poly.append((fx * site_width_ft, fy * site_length_ft))

            inside = _points_in_polygon(np.array(poly), grid_pts)
            mask = inside.reshape(nx, nz)
            if mask.any():
                results.append({"type": "hardscape", "mask": mask})

    return results


def build_hardscape_regions(engine, svg_path=None, image_path=None, use_latest=False,
                             sketches_folder=r"D:\MemoryMachine\data\sketches", **kwargs):
    """
    Convenience dispatcher mirroring build_sketch_weights: pass exactly one
    of svg_path, image_path, or use_latest=True, get back the list of
    {"type": "hardscape", "mask": (engine.nx, engine.nz) bool array} dicts
    from find_color_regions (raster) or find_closed_svg_regions (SVG).
    Extra `kwargs` are forwarded to whichever one runs (e.g. `color`,
    `threshold`, `close_tol_frac`).

    NOT wired into TerracingEngine's blending -- out of scope here, another
    track's concern (see task notes). This only builds the region data in
    the documented shape.
    """
    n_given = sum(x is not None for x in (svg_path, image_path)) + int(use_latest)
    if n_given != 1:
        raise ValueError("pass exactly one of svg_path, image_path, or use_latest=True")

    if use_latest:
        latest = find_latest_sketch(sketches_folder)
        if latest is None:
            raise FileNotFoundError(f"no sketch files found in {sketches_folder}")
        if latest.lower().endswith(".svg"):
            svg_path = latest
        else:
            image_path = latest

    if svg_path is not None:
        return find_closed_svg_regions(svg_path, engine.site_width_ft, engine.site_length_ft,
                                        engine.nx, engine.nz, engine.voxel_ft, **kwargs)
    return find_color_regions(image_path, engine.site_width_ft, engine.site_length_ft,
                               engine.nx, engine.nz, engine.voxel_ft, **kwargs)
