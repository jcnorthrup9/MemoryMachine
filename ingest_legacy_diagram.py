"""
Memory Machine -- Legacy Diagram Ingestion (offline batch converter).

Reads a color diagram export from the OLD diagram tool (static/main.js's
POST /api/export-diagram, archived at archive/diagrams/generated/
memory_machine_jpg-color_<epoch_ms>.jpg) and converts it into the SAME JSON
shape logic/pershing_api.py's PAINT_STATE_PATH bootstrap expects
(outputs/cockpit/web_paint_state.json: {"canyon", "hardscape", "water",
"trees", "greenscape", "amenity_resting"}, each an (nx, nz) nested list
matching TerracingEngine's voxel grid). This is a standalone offline tool --
per project decision, NOT wired into the live upload/bake flow (though see
logic/legacy_diagram_bridge.py, which wraps this module's functions behind
a real HTTP preview endpoint for the live app's Diagram Input panel -- that
bridge is read-only and still routes the actual commit through the existing
bake() endpoint, this module itself remains standalone); use
--install-as-live to promote one converted output into the live app's state.

THE ROTATION PROBLEM this module exists to solve: the old diagram tool
rendered the site true-north-up. DTLA's street grid runs the site itself at
roughly 36-40 degrees off true north (an unverified figure, see
PershingMetabolizer_Prototype/index.html's SITE_ROTATION_DEG=36 and
archive/memoryMachine/TODO_Metabolizer_NextSteps_20260629.md's flag that it
was never sourced to a survey). The live pipeline's working frame is
orthogonal to the SITE's own street grid instead (vector_export.py's
STREET_LABELS: Olive=x0, Hill=xmax, 6th=y0, 5th=ymax) -- so these diagrams
must be rectified (un-rotated) before their pixel colors can be mapped onto
site-local feet. Rather than trust the unverified fixed-angle constants,
this module detects each image's own dashed site-boundary polygon (via
cv2.minAreaRect) and derives the rectification transform from that directly
-- the legacy constants are used only as a sanity-range check.

Color legend -- EMPIRICALLY VERIFIED 2026-07-10 by sampling quantized pixel
colors across 3 sample images (memory_machine_jpg-color_1775589552807.jpg,
_1775590162274.jpg, _1775590622731.jpg) against harvest/pershing_square_
generator.py's COLOR_MAP (itself reverse-engineered from static/main.js's
own hex constants, the same tool that rendered these images):
  - green  (76,175,80)  -> observed (72-80,168-176,72-80)   -> greenscape
  - blue   (3,169,244)  -> observed (0-8,160-169,232-244)   -> water
  - gray   (158,158,158)-> observed (144-160,144-168,144-160) -> hardscape
    (this also covers the hatched/stippled "path" texture seen blended over
    green in some diagrams -- per user decision 2026-07-10, dotted/hatched
    paths fold into hardscape rather than getting a new pipeline category,
    since terracing_engine.py/PaintOverlay.jsx only have 5 categories and
    none of them is "path")
  - white  (255,255,255)-> observed (248-255,248-255,248-255) -> BOUNDARY
    (dashed site-edge line -- used only for boundary detection, not a
    design category)
  - plain black (0,0,0) is background/unpainted, NOT a distinct hardscape
    fill -- confirmed by sampling: the "solid black interior" a first visual
    read worried might be indistinguishable hardscape is actually just the
    canvas background showing through; hardscape is exclusively the gray.
  - tan/beige (188,170,164), i.e. 0xBCAAA4 -> trees. Added 2026-07-11 after
    static/main.js's _getLayerColor() bug was fixed (SHADE previously
    rendered identically to GREEN_SPACE, so no diagram exported before that
    fix could ever have contained this color at all). UNLIKE the other four
    entries above, this threshold is NOT yet empirically verified against a
    real exported pixel -- it's derived arithmetically from the
    ZONE_MATERIALS.SHADE constant, and (188,170,164) sits close to
    HARDSCAPE_GRAY_RGB's (158,158,158) (distinguished mainly by the tree
    color being visibly R>G>B tinted rather than channel-flat gray -- see
    segment_legacy_colors' tan_mask). Re-verify by sampling a few freshly
    generated diagrams that actually contain SHADE-layer picks before
    trusting this in production, the same way the other four colors were
    verified against real samples.
No legacy diagram color maps to `canyon` (continuous excavation weight) or
`amenity_resting` -- both stay all-zero/all-False in the converted output.
"""
import glob
import json
import math
import os

import numpy as np

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
REAL_GEOMETRY_PATH = os.path.join(BASE_DIR, "PershingMetabolizer_Prototype", "real_geometry.json")
PAINT_STATE_PATH = os.path.join(BASE_DIR, "outputs", "cockpit", "web_paint_state.json")
DEFAULT_OUT_DIR = os.path.join(BASE_DIR, "outputs", "legacy_diagram_ingest")
DEFAULT_GLOB = os.path.join(BASE_DIR, "archive", "diagrams", "generated", "memory_machine_jpg-color_*.jpg")

VOXEL_FT = 9.0

# COLOR_MAP RGB legend, reused from harvest/pershing_square_generator.py
# (same renderer). Thresholds below are per-channel tolerance, widened past
# the "empirically verified" ranges in this module's docstring to absorb
# JPEG compression noise across the whole ~222-image batch, not just the 3
# samples actually inspected.
GREEN_RGB = (76, 175, 80)
BLUE_RGB = (3, 169, 244)
HARDSCAPE_GRAY_RGB = (158, 158, 158)
# Tan/beige, 0xBCAAA4 -- matches ZONE_MATERIALS.SHADE in static/main.js and
# paintCategories.js's trees brush (renamed from "shade" 2026-07-16). NOT
# yet empirically re-verified against a real exported pixel -- see module
# docstring's color-legend note.
TREE_TAN_RGB = (188, 170, 164)
WHITE_RGB = (255, 255, 255)
COLOR_THRESHOLD = 30
GRAY_CHANNEL_SPREAD = 20  # max |R-G|, |G-B|, |R-B| to count as "gray" (vs. green/blue/tan tinted)

# Confirmed 2026-07-13 via direct pixel scan of a real export
# (memory_machine_jpg-color_1783990667145.jpg): the dashed white boundary
# line's JPEG-compression/antialiasing halo produces mid-gray and warm-gray
# transitional pixels that land inside HARDSCAPE_GRAY_RGB's and
# TREE_TAN_RGB's threshold bands, misclassifying the boundary OUTLINE
# itself as hardscape/trees content (traced the boundary instead of showing
# real diagram content in the live Diagram Input preview). Erode the
# boundary polygon inward by this many pixels before using it as
# segment_legacy_colors' interior test, so that halo can never register --
# applied only to the interior-test polygon, NOT to BoundaryAffine's own
# raw_w_px/raw_h_px (which must stay the true detected size for accurate
# pixel-to-feet scaling).
BOUNDARY_EROSION_PX = 6

# Orientation calibration -- CONFIRMED 2026-07-10 via calibrate_legacy_
# orientation.py against memory_machine_jpg-color_1775590162274.jpg, using
# the CORRECTED BoundaryAffine (an earlier axis-swap bug in transform()/
# inverse_transform() produced a wrong first determination of
# flip_x=False/flip_y=True -- fixed, then this was re-derived and
# re-confirmed against the fixed transform, don't trust any note elsewhere
# referencing the old value). Checked against DTLA street geography (5th
# St=north/top, 6th St=south/bottom since numbered streets increase going
# south from downtown's core; Olive=west/left, Hill=east/right): only
# flip_x=False, flip_y=False places BOTH axes correctly. Internally
# cross-validated: TT (the exact opposite flip) gets both axes wrong, and
# FT/TF (single-axis flips of FF) each get exactly the one flipped axis
# wrong -- fully self-consistent. User signed off on this determination
# directly. Verified for THIS renderer/scene setup (confirmed consistent
# across the whole batch via calibrate_batch_affine's tight angle/aspect
# agreement) -- if a differently-oriented diagram source is ever ingested,
# this needs revisiting, don't assume it generalizes blindly (same caveat
# sketch_weight_mapper.py documents for its own flip convention).
FLIP_X = False
FLIP_Y = False
CALIBRATION_REFERENCE_IMAGE = "archive/diagrams/generated/memory_machine_jpg-color_1775590162274.jpg"

# Legacy rotation constants -- NOT trusted as ground truth (see module
# docstring), used only as a sanity-range check on the per-image detected
# angle. PershingMetabolizer_Prototype/index.html: SITE_ROTATION_DEG=36;
# archive/diagrams/pershing_square_diagram_diagram.json's Gemini-vision
# estimate: ~40 degrees. Widened generously since neither is a survey source.
SANITY_ANGLE_RANGE_DEG = (20, 55)


class BoundaryAffine:
    """
    Rectification transform: original-image pixel coords -> site-local feet
    in the live pipeline's orthogonal (Olive/Hill/6th/5th) frame.

    Derived from a single detected rotated rectangle (the dashed site
    boundary): rotate by -raw_angle_deg about the rectangle's own center
    (raw_angle_deg is cv2.minAreaRect's UNADJUSTED angle -- rotating by
    -raw_angle_deg always puts the "w"-labeled dimension on the resulting
    local x-axis and "h" on local y, empirically verified, NOT something to
    re-derive by reasoning about OpenCV's angle convention), then pick
    which local axis is width vs. length based on which of raw_w_px/
    raw_h_px is shorter (site_width_ft=354 < site_length_ft=602), then flip
    per FLIP_X/FLIP_Y (orientation calibration, resolves the 180-degree
    ambiguity minAreaRect can't), then scale to site_width_ft/site_length_ft.
    """

    def __init__(self, center_px, raw_angle_deg, raw_w_px, raw_h_px,
                 site_width_ft, site_length_ft, flip_x, flip_y):
        self.center_px = np.asarray(center_px, dtype=float)
        self.raw_angle_deg = float(raw_angle_deg)
        self.raw_w_px = float(raw_w_px)
        self.raw_h_px = float(raw_h_px)
        # width_is_raw_x: True if raw_w_px (which rot_x always spans, see
        # _rotate_to_local below) is the SHORTER pixel dimension -- i.e.
        # local x already IS the width axis, no swap needed.
        self.width_is_raw_x = raw_w_px <= raw_h_px
        self.box_w_px = min(raw_w_px, raw_h_px)   # short pixel edge -> site_width_ft
        self.box_h_px = max(raw_w_px, raw_h_px)   # long pixel edge  -> site_length_ft
        self.site_width_ft = float(site_width_ft)
        self.site_length_ft = float(site_length_ft)
        self.flip_x = flip_x
        self.flip_y = flip_y

    def _rotate_to_local(self, points_px):
        """pixel coords -> local frame where rot_x always spans raw_w_px and
        rot_y always spans raw_h_px (empirically verified cv2.minAreaRect
        convention -- see class docstring)."""
        theta = math.radians(-self.raw_angle_deg)
        cos_t, sin_t = math.cos(theta), math.sin(theta)
        centered = points_px - self.center_px
        rot_x = centered[:, 0] * cos_t - centered[:, 1] * sin_t
        rot_y = centered[:, 0] * sin_t + centered[:, 1] * cos_t
        return rot_x, rot_y

    def _rotate_from_local(self, rot_x, rot_y):
        """Inverse of _rotate_to_local: local frame -> pixel coords."""
        theta = math.radians(self.raw_angle_deg)
        cos_t, sin_t = math.cos(theta), math.sin(theta)
        px_x = rot_x * cos_t - rot_y * sin_t + self.center_px[0]
        px_y = rot_x * sin_t + rot_y * cos_t + self.center_px[1]
        return np.column_stack([px_x, px_y])

    def transform(self, points_px):
        """(N, 2) original-image pixel coords -> (N, 2) site-local feet."""
        pts = np.asarray(points_px, dtype=float)
        if len(pts) == 0:
            return np.zeros((0, 2))

        rot_x, rot_y = self._rotate_to_local(pts)
        width_component, length_component = (
            (rot_x, rot_y) if self.width_is_raw_x else (rot_y, rot_x))

        fx = width_component / self.box_w_px + 0.5
        fy = length_component / self.box_h_px + 0.5
        if self.flip_x:
            fx = 1.0 - fx
        if self.flip_y:
            fy = 1.0 - fy

        return np.column_stack([fx * self.site_width_ft, fy * self.site_length_ft])

    def inverse_transform(self, points_ft):
        """(N, 2) site-local feet -> (N, 2) original-image pixel coords.
        Exact inverse of transform() -- used by calibrate_legacy_orientation.py
        to place street-edge labels back onto the original (still-rotated)
        diagram image for visual sign-off."""
        pts = np.asarray(points_ft, dtype=float)
        if len(pts) == 0:
            return np.zeros((0, 2))

        fx = pts[:, 0] / self.site_width_ft
        fy = pts[:, 1] / self.site_length_ft
        if self.flip_x:
            fx = 1.0 - fx
        if self.flip_y:
            fy = 1.0 - fy

        width_component = (fx - 0.5) * self.box_w_px
        length_component = (fy - 0.5) * self.box_h_px
        rot_x, rot_y = (
            (width_component, length_component) if self.width_is_raw_x
            else (length_component, width_component))

        return self._rotate_from_local(rot_x, rot_y)

    def to_dict(self):
        return {
            "center_px": self.center_px.tolist(),
            "raw_angle_deg": self.raw_angle_deg,
            "raw_w_px": self.raw_w_px,
            "raw_h_px": self.raw_h_px,
            "site_width_ft": self.site_width_ft,
            "site_length_ft": self.site_length_ft,
            "flip_x": self.flip_x,
            "flip_y": self.flip_y,
        }


def detect_boundary_affine(image_path, site_width_ft, site_length_ft,
                            flip_x, flip_y, white_threshold=225,
                            sanity_angle_range=SANITY_ANGLE_RANGE_DEG):
    """
    Load image_path, threshold near-white pixels (the dashed site-boundary
    line), and run cv2.minAreaRect on the raw (N, 2) pixel-coordinate array
    -- minAreaRect works directly on a scattered point cloud, so dash gaps
    don't need to be closed into a contour first.

    Returns (BoundaryAffine, boundary_polygon_px, detected_angle_deg). Prints
    a warning (does not raise) if detected_angle_deg's nearest equivalent
    falls outside sanity_angle_range -- see module docstring on why that
    range is a sanity check, not ground truth.

    boundary_polygon_px is eroded inward by BOUNDARY_EROSION_PX before being
    returned (see that constant's comment) -- segment_legacy_colors' only
    consumer of this polygon -- so the boundary line's own antialiasing halo
    can never be classified as hardscape/trees. affine itself is built from
    the FULL, non-eroded w/h so the feet-per-pixel scale stays accurate.

    site width/length determine which minAreaRect axis is width vs. height:
    the site is a 1:1.70 rectangle (not square), so whichever detected pixel
    edge is longer must correspond to site_length_ft (the longer real
    dimension), independent of the raw angle minAreaRect happens to report.
    """
    import cv2
    from PIL import Image

    img = Image.open(image_path).convert("RGB")
    rgb = np.array(img).astype(int)
    r_ch, g_ch, b_ch = rgb[:, :, 0], rgb[:, :, 1], rgb[:, :, 2]
    white_mask = (r_ch > white_threshold) & (g_ch > white_threshold) & (b_ch > white_threshold)

    ys, xs = np.where(white_mask)
    if len(xs) < 10:
        raise ValueError(f"{image_path}: fewer than 10 near-white pixels found, "
                          f"can't detect boundary (threshold={white_threshold})")

    pts = np.column_stack([xs, ys]).astype(np.float32)
    (cx, cy), (w, h), raw_angle = cv2.minAreaRect(pts)

    affine = BoundaryAffine(
        center_px=(cx, cy), raw_angle_deg=raw_angle, raw_w_px=w, raw_h_px=h,
        site_width_ft=site_width_ft, site_length_ft=site_length_ft,
        flip_x=flip_x, flip_y=flip_y,
    )
    eroded_w = max(w - 2 * BOUNDARY_EROSION_PX, 1.0)
    eroded_h = max(h - 2 * BOUNDARY_EROSION_PX, 1.0)
    box_pts = cv2.boxPoints(((cx, cy), (eroded_w, eroded_h), raw_angle))

    # Sanity check only -- warn, don't raise, per module docstring. Checked
    # against raw_angle (not width_is_raw_x-adjusted) since the sanity range
    # is mod-90 either way.
    normalized = raw_angle % 90.0
    lo, hi = sanity_angle_range
    if not (lo <= normalized <= hi or lo <= (90 - normalized) <= hi):
        print(f"WARNING: {image_path}: detected boundary angle {raw_angle:.1f} deg "
              f"(normalized {normalized:.1f}) falls outside the sanity range "
              f"{sanity_angle_range} derived from unverified legacy constants "
              f"(SITE_ROTATION_DEG=36 / ~40deg Gemini estimate). Proceeding "
              f"anyway since per-image detection is trusted over those "
              f"constants -- but double check this image.")

    return affine, box_pts, raw_angle


def calibrate_batch_affine(sample_image_paths, site_width_ft, site_length_ft,
                            flip_x, flip_y, agreement_tol_deg=1.0, agreement_tol_aspect=0.05):
    """
    Run detect_boundary_affine on each of sample_image_paths, assert the
    detected angle (mod 90) and box aspect ratio agree tightly across all
    samples -- this IS the empirical check that "same renderer/scene" holds
    for the whole ~222-image batch. Raises AssertionError if they don't
    (falls back to per-image detection is the caller's responsibility, not
    handled silently here). Returns one averaged BoundaryAffine intended for
    reuse across the whole batch, NOT re-detected per image.
    """
    angles, aspects, affines = [], [], []
    for path in sample_image_paths:
        affine, _box_pts, angle = detect_boundary_affine(
            path, site_width_ft, site_length_ft, flip_x, flip_y)
        angles.append(angle % 90.0)
        aspects.append(affine.box_h_px / affine.box_w_px)
        affines.append(affine)

    angle_spread = max(angles) - min(angles)
    aspect_spread = max(aspects) - min(aspects)
    if angle_spread > agreement_tol_deg:
        raise AssertionError(
            f"detected angles disagree by {angle_spread:.2f} deg across "
            f"{len(sample_image_paths)} samples (tol={agreement_tol_deg}) -- "
            f"the 'one fixed affine for the whole batch' assumption doesn't "
            f"hold; fall back to per-image detection instead. angles={angles}")
    if aspect_spread > agreement_tol_aspect:
        raise AssertionError(
            f"detected box aspect ratios disagree by {aspect_spread:.3f} "
            f"across {len(sample_image_paths)} samples (tol={agreement_tol_aspect}) "
            f"-- crop framing may vary per image; fall back to per-image "
            f"detection instead. aspects={aspects}")

    mid = len(affines) // 2
    return affines[mid]  # median-ish sample, not an actual numeric average of two different images' crops


def segment_legacy_colors(image_path, boundary_polygon_px, sample_stride=2,
                           green_rgb=GREEN_RGB, blue_rgb=BLUE_RGB,
                           hardscape_gray_rgb=HARDSCAPE_GRAY_RGB, tree_tan_rgb=TREE_TAN_RGB,
                           threshold=COLOR_THRESHOLD, gray_spread=GRAY_CHANNEL_SPREAD):
    """
    Threshold image_path's ORIGINAL (unwarped) pixels against the COLOR_MAP
    legend, restricted to the interior of boundary_polygon_px -- reuses
    sketch_weight_mapper._points_in_polygon for the interior test, so
    exterior city-block-context pixels of a similar color never leak in.

    Per user decision 2026-07-10: hardscape_gray_rgb also covers the
    hatched/stippled "path" texture (dotted lines fold into hardscape, no
    separate category). Returns {"greenscape": (N,2) px, "water": (M,2) px,
    "trees": (P,2) px, "hardscape": (K,2) px} -- pixel coordinates, NOT yet
    transformed to site-feet (caller applies BoundaryAffine.transform()).
    """
    from PIL import Image
    from sketch_weight_mapper import _points_in_polygon

    img = Image.open(image_path).convert("RGB")
    rgb = np.array(img).astype(int)
    rgb = rgb[::sample_stride, ::sample_stride]
    r_ch, g_ch, b_ch = rgb[:, :, 0], rgb[:, :, 1], rgb[:, :, 2]

    def near(rgb_target):
        cr, cg, cb = rgb_target
        return ((np.abs(r_ch - cr) < threshold)
                & (np.abs(g_ch - cg) < threshold)
                & (np.abs(b_ch - cb) < threshold))

    green_mask = near(green_rgb)
    blue_mask = near(blue_rgb)
    # Gray hardscape: near the target gray AND channel-flat (not a green-,
    # blue-, or tan-tinted pixel that happens to also be within `threshold`
    # of gray on each channel independently).
    gray_mask = (
        near(hardscape_gray_rgb)
        & (np.abs(r_ch - g_ch) < gray_spread)
        & (np.abs(g_ch - b_ch) < gray_spread)
        & (np.abs(r_ch - b_ch) < gray_spread)
    )
    # Tan trees: near the target tan AND visibly R>G>B tinted (not
    # channel-flat gray) -- tree_tan_rgb=(188,170,164) sits only ~30 away
    # from hardscape_gray_rgb=(158,158,158) on the R channel alone (right at
    # `threshold`'s own boundary), so this tint check is real insurance
    # against real-world JPEG noise blurring that edge, not just belt-and-
    # suspenders over already-clean synthetic math. NOT yet empirically
    # verified against a real exported pixel -- see module docstring.
    tan_mask = (
        near(tree_tan_rgb)
        & (r_ch - g_ch > 5)
        & (g_ch - b_ch > 0)
    )

    h, w = r_ch.shape
    yy, xx = np.mgrid[0:h, 0:w]
    xx = (xx * sample_stride).ravel()
    yy = (yy * sample_stride).ravel()

    poly = np.asarray(boundary_polygon_px, dtype=float)

    def pixels_for(mask):
        flat_mask = mask.ravel()
        if not flat_mask.any():
            return np.zeros((0, 2))
        px = np.column_stack([xx[flat_mask], yy[flat_mask]]).astype(float)
        inside = _points_in_polygon(poly, px)
        return px[inside]

    return {
        "greenscape": pixels_for(green_mask),
        "water": pixels_for(blue_mask),
        "trees": pixels_for(tan_mask),
        "hardscape": pixels_for(gray_mask),
    }


def rasterize_to_paint_state(category_points_ft, nx, nz, voxel_ft=VOXEL_FT):
    """
    category_points_ft: {"greenscape": (N,2) ft, "water": (M,2) ft,
    "trees": (P,2) ft, "hardscape": (K,2) ft}. Returns the full 6-key dict
    matching outputs/cockpit/web_paint_state.json's shape. `canyon` and
    `amenity_resting` stay all-zero/all-False -- no legacy diagram color
    maps to either (see module docstring).
    """
    def empty_bool():
        return np.zeros((nx, nz), dtype=bool)

    masks = {"hardscape": empty_bool(), "water": empty_bool(), "trees": empty_bool(), "greenscape": empty_bool()}
    for category, pts_ft in category_points_ft.items():
        if len(pts_ft) == 0:
            continue
        gx_idx = np.clip((pts_ft[:, 0] / voxel_ft).astype(int), 0, nx - 1)
        gy_idx = np.clip((pts_ft[:, 1] / voxel_ft).astype(int), 0, nz - 1)
        masks[category][gx_idx, gy_idx] = True

    return {
        "canyon": np.zeros((nx, nz)).tolist(),
        "hardscape": masks["hardscape"].tolist(),
        "water": masks["water"].tolist(),
        "trees": masks["trees"].tolist(),
        "greenscape": masks["greenscape"].tolist(),
        "amenity_resting": np.zeros((nx, nz), dtype=bool).tolist(),
    }


def render_debug_preview(paint_state, out_path, cell_px=8):
    """
    Render a paint_state dict (this module's own output shape) as a plan-
    view PNG in the live pipeline's orthogonal frame -- x=Olive(left)->
    Hill(right), y=6th(bottom)->5th(top), matching vector_export.py's
    STREET_LABELS convention (image row 0 = ymax = 5th St, so this flips
    the grid's y-index for display). For visually sanity-checking a
    converted diagram against the original JPG and against the live app's
    Viewport rendering (requirement 5's verification plan) -- not used by
    the conversion pipeline itself.
    """
    from PIL import Image

    hardscape = np.array(paint_state["hardscape"], dtype=bool)
    water = np.array(paint_state["water"], dtype=bool)
    trees = np.array(paint_state["trees"], dtype=bool)
    green = np.array(paint_state["greenscape"], dtype=bool)
    nx, nz = hardscape.shape

    img = np.zeros((nz, nx, 3), dtype=np.uint8)
    img[green.T] = (76, 175, 80)
    img[water.T] = (3, 169, 244)
    img[trees.T] = TREE_TAN_RGB
    img[hardscape.T] = (158, 158, 158)
    img = img[::-1, :, :]  # row 0 at top should be ymax (5th St), per STREET_LABELS

    out_img = Image.fromarray(img, mode="RGB").resize(
        (nx * cell_px, nz * cell_px), resample=Image.NEAREST)
    out_img.save(out_path)
    return out_path


def _load_real_geometry():
    with open(REAL_GEOMETRY_PATH) as f:
        return json.load(f)


def _require_calibration():
    if FLIP_X is None or FLIP_Y is None:
        raise RuntimeError(
            "FLIP_X/FLIP_Y are not calibrated yet. Run calibrate_legacy_orientation.py "
            "against a reference image, get explicit human sign-off on which of the 4 "
            "orientations is correct, then hardcode FLIP_X/FLIP_Y/CALIBRATION_REFERENCE_IMAGE "
            "at the top of this module before converting real diagrams.")


def convert_one(image_path, affine=None, nx=None, nz=None, voxel_ft=VOXEL_FT,
                 out_path=None, debug_path=None):
    """
    Full pipeline for one image: detect boundary (unless `affine` is
    supplied, e.g. from calibrate_batch_affine) -> segment colors on
    original pixels -> transform to site-feet -> rasterize. Returns the
    web_paint_state.json-shaped dict; writes it to out_path if given.
    `debug_path`: if given, also renders a plan-view PNG of the result via
    render_debug_preview, for visually sanity-checking against the original
    JPG (requirement 5's verification plan).
    """
    _require_calibration()
    real_geometry = _load_real_geometry()
    site_width_ft = real_geometry["site"]["width_ft"]
    site_length_ft = real_geometry["site"]["length_ft"]

    if nx is None or nz is None:
        nx = math.ceil(site_width_ft / voxel_ft)
        nz = math.ceil(site_length_ft / voxel_ft)

    # boundary_polygon_px (this image's own detected boundary) is always
    # needed for segment_legacy_colors' interior-only test, even when the
    # caller supplies a shared batch-wide `affine` for the actual transform
    # -- crop framing can vary per image even when rotation angle doesn't
    # (see calibrate_batch_affine's aspect-ratio check).
    detected_affine, boundary_polygon_px, _angle = detect_boundary_affine(
        image_path, site_width_ft, site_length_ft, FLIP_X, FLIP_Y)
    if affine is None:
        affine = detected_affine

    category_pixels = segment_legacy_colors(image_path, boundary_polygon_px)
    category_points_ft = {
        cat: affine.transform(pts_px) for cat, pts_px in category_pixels.items()
    }
    paint_state = rasterize_to_paint_state(category_points_ft, nx, nz, voxel_ft)

    if out_path:
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        with open(out_path, "w") as f:
            json.dump(paint_state, f)

    if debug_path:
        os.makedirs(os.path.dirname(debug_path), exist_ok=True)
        render_debug_preview(paint_state, debug_path)

    return paint_state


def convert_batch(glob_pattern=DEFAULT_GLOB, out_dir=DEFAULT_OUT_DIR,
                   calibration_sample_count=15, voxel_ft=VOXEL_FT):
    """
    Convert every image matching glob_pattern. First runs
    calibrate_batch_affine on a sample of calibration_sample_count images
    PURELY as a consistency check (confirms the whole batch shares the same
    rotation angle/aspect ratio, i.e. the same renderer/scene setup) -- if
    it raises, this re-raises rather than silently proceeding.

    IMPORTANT: despite that consistency check, each image is converted with
    its OWN freshly-detected BoundaryAffine, not a single shared one.
    Different exports in this corpus have different pixel resolutions/crops
    (confirmed: some are 2448x1584, others 1221x1284) even when the
    rotation angle and aspect ratio agree -- BoundaryAffine's center_px/
    box_w_px/box_h_px are absolute pixel measurements specific to one
    image's resolution and crop framing, so reusing one image's affine
    object for another's pixel coordinates silently misaligns everything
    (caught 2026-07-10 via a live-app spot check: a shared-affine version
    of this function produced 63 greenscape cells where per-image detection
    produces the expected ~1541 for the same reference image). Detection is
    fast and reliable per-image (verified consistent across the initial
    10-sample test), so there's no real benefit to reuse anyway.

    Writes one JSON per image to out_dir plus a manifest.csv (image, out,
    painted_area_fraction, error) for spot-checking outliers.
    """
    import csv

    _require_calibration()
    paths = sorted(glob.glob(glob_pattern))
    if not paths:
        raise FileNotFoundError(f"no files matched {glob_pattern}")

    real_geometry = _load_real_geometry()
    site_width_ft = real_geometry["site"]["width_ft"]
    site_length_ft = real_geometry["site"]["length_ft"]
    nx = math.ceil(site_width_ft / voxel_ft)
    nz = math.ceil(site_length_ft / voxel_ft)

    sample = paths[:: max(1, len(paths) // calibration_sample_count)][:calibration_sample_count]
    calibrate_batch_affine(sample, site_width_ft, site_length_ft, FLIP_X, FLIP_Y)  # consistency check only

    os.makedirs(out_dir, exist_ok=True)
    manifest_rows = []
    for path in paths:
        epoch_ms = os.path.splitext(os.path.basename(path))[0].rsplit("_", 1)[-1]
        out_path = os.path.join(out_dir, f"{epoch_ms}.json")
        try:
            paint_state = convert_one(path, affine=None, nx=nx, nz=nz,
                                       voxel_ft=voxel_ft, out_path=out_path)
            painted = sum(
                sum(row.count(True) for row in paint_state[cat])
                for cat in ("hardscape", "water", "trees", "greenscape")
            )
            fraction = painted / float(nx * nz)
            manifest_rows.append({"image": path, "out": out_path,
                                   "painted_area_fraction": f"{fraction:.4f}", "error": ""})
        except Exception as exc:  # noqa: BLE001 -- batch tool, one bad image shouldn't kill the run
            manifest_rows.append({"image": path, "out": "", "painted_area_fraction": "", "error": str(exc)})

    manifest_path = os.path.join(out_dir, "manifest.csv")
    with open(manifest_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["image", "out", "painted_area_fraction", "error"])
        writer.writeheader()
        writer.writerows(manifest_rows)

    return manifest_rows


def install_as_live(converted_json_path):
    """
    Promote one already-converted output into the live app's
    outputs/cockpit/web_paint_state.json, backing up any existing file
    first. logic/pershing_api.py's bootstrap-load branch (PAINT_STATE_PATH,
    lines ~112-119) picks this up on next import/restart with zero pipeline
    code changes.

    Backup filename includes a timestamp (not a fixed ".bak") -- an earlier
    version of this function used a fixed ".bak" suffix, and calling it
    twice in a row (once with a since-fixed-buggy conversion, once with the
    corrected one) silently overwrote the FIRST backup -- which held the
    user's real hand-painted original -- with the buggy intermediate
    conversion, permanently losing the original (2026-07-10 incident, no
    git history or other copy existed to recover it). Never repeat that:
    each call gets its own uniquely-named backup.
    """
    import time

    with open(converted_json_path) as f:
        paint_state = json.load(f)

    if os.path.exists(PAINT_STATE_PATH):
        backup_path = f"{PAINT_STATE_PATH}.{int(time.time())}.bak"
        os.replace(PAINT_STATE_PATH, backup_path)
        print(f"backed up existing live paint state to {backup_path}")

    os.makedirs(os.path.dirname(PAINT_STATE_PATH), exist_ok=True)
    with open(PAINT_STATE_PATH, "w") as f:
        json.dump(paint_state, f)
    print(f"installed {converted_json_path} as {PAINT_STATE_PATH}")


def main():
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", nargs="?", help="single image to convert")
    parser.add_argument("--batch", action="store_true", help="convert all images matching --glob")
    parser.add_argument("--glob", default=DEFAULT_GLOB)
    parser.add_argument("--out-dir", default=DEFAULT_OUT_DIR)
    parser.add_argument("--out", help="output path for single-image conversion")
    parser.add_argument("--debug", action="store_true",
                         help="also render a plan-view debug PNG next to --out (single-image only)")
    parser.add_argument("--install-as-live", metavar="JSON_PATH",
                         help="promote an already-converted JSON to the live app's paint state")
    args = parser.parse_args()

    if args.install_as_live:
        install_as_live(args.install_as_live)
    elif args.batch:
        rows = convert_batch(glob_pattern=args.glob, out_dir=args.out_dir)
        n_ok = sum(1 for r in rows if not r["error"])
        print(f"converted {n_ok}/{len(rows)} images -> {args.out_dir}")
    elif args.image:
        out_path = args.out or os.path.join(
            DEFAULT_OUT_DIR, os.path.splitext(os.path.basename(args.image))[0] + ".json")
        debug_path = os.path.splitext(out_path)[0] + "_debug.png" if args.debug else None
        convert_one(args.image, out_path=out_path, debug_path=debug_path)
        print(f"converted -> {out_path}" + (f" (debug: {debug_path})" if debug_path else ""))
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
