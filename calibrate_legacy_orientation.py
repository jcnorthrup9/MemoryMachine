"""
Memory Machine -- one-time calibration tool for ingest_legacy_diagram.py's
FLIP_X/FLIP_Y constants.

detect_boundary_affine() (ingest_legacy_diagram.py) recovers the site
boundary's rotation angle from the dashed white polygon, but cv2.minAreaRect
can't resolve which SIDE of that rectangle is which street -- rotating the
correction 180 degrees in either axis produces an equally "axis-aligned"
result. This is a real ambiguity, not a bug: same class of problem
sketch_weight_mapper.py already solved once by hand for a real labeled
sketch (see that module's docstring).

This script renders all 4 (flip_x, flip_y) hypotheses by burning
vector_export.py's STREET_LABELS ("OLIVE ST"/"HILL ST"/"5TH ST"/"6TH ST")
directly onto a copy of the ORIGINAL (still-rotated) diagram image, using
BoundaryAffine.inverse_transform to place each label at the correct pixel
location under that hypothesis. A human (or an image-capable reviewer)
picks whichever preview correctly labels the real streets, then that
(flip_x, flip_y) pair gets hardcoded into ingest_legacy_diagram.py's
FLIP_X/FLIP_Y/CALIBRATION_REFERENCE_IMAGE constants.

Usage: python calibrate_legacy_orientation.py <reference_image.jpg>
Writes 4 preview PNGs next to the input: <name>_orientation_FF.png,
_FT.png, _TF.png, _TT.png (flip_x, flip_y).
"""
import os
import sys

from ingest_legacy_diagram import detect_boundary_affine
from vector_export import STREET_LABELS

SITE_WIDTH_FT = 354.22
SITE_LENGTH_FT = 602.53


def _edge_label_points_ft():
    """(text, (x_ft, y_ft)) pairs at the midpoint of each site edge, mirroring
    vector_export.py's street_label_points but inset slightly so labels land
    inside the boundary rather than exactly on it."""
    inset = 20.0
    edge_pos = {
        "x0": (inset, SITE_LENGTH_FT / 2),
        "xmax": (SITE_WIDTH_FT - inset, SITE_LENGTH_FT / 2),
        "y0": (SITE_WIDTH_FT / 2, inset),
        "ymax": (SITE_WIDTH_FT / 2, SITE_LENGTH_FT - inset),
    }
    return [(text, edge_pos[edge]) for text, edge in STREET_LABELS]


def render_orientation_preview(image_path, flip_x, flip_y, out_path):
    from PIL import Image, ImageDraw, ImageFont

    affine, _box_pts, _angle = detect_boundary_affine(
        image_path, SITE_WIDTH_FT, SITE_LENGTH_FT, flip_x=flip_x, flip_y=flip_y)

    img = Image.open(image_path).convert("RGB")
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("arialbd.ttf", 36)
    except OSError:
        font = ImageFont.load_default()

    labels_ft = _edge_label_points_ft()
    for text, (x_ft, y_ft) in labels_ft:
        px = affine.inverse_transform([[x_ft, y_ft]])[0]
        px_x, px_y = float(px[0]), float(px[1])
        # Red text with a black outline stroke for legibility over any
        # background color (green/blue/black/gray all appear in these diagrams).
        draw.text((px_x, px_y), text, fill=(255, 0, 0), font=font, anchor="mm",
                   stroke_width=3, stroke_fill=(0, 0, 0))

    img.save(out_path)
    return out_path


def main():
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(1)

    image_path = sys.argv[1]
    base, _ext = os.path.splitext(image_path)

    combos = [(False, False, "FF"), (False, True, "FT"), (True, False, "TF"), (True, True, "TT")]
    out_paths = []
    for flip_x, flip_y, suffix in combos:
        out_path = f"{base}_orientation_{suffix}.png"
        render_orientation_preview(image_path, flip_x, flip_y, out_path)
        out_paths.append(out_path)
        print(f"flip_x={flip_x!s:5s} flip_y={flip_y!s:5s} -> {out_path}")

    print("\nInspect the 4 previews above. Whichever one correctly labels the "
          "real OLIVE/HILL/5TH/6TH streets against known site geography is the "
          "correct (flip_x, flip_y) pair -- hardcode it into "
          "ingest_legacy_diagram.py's FLIP_X/FLIP_Y/CALIBRATION_REFERENCE_IMAGE.")


if __name__ == "__main__":
    main()
