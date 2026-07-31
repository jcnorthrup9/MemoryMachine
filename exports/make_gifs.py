"""
Create animated GIFs from the page-05 image carousels.
Run from anywhere: py exports/make_gifs.py
Output: exports/phase01.gif, phase02.gif, phase03.gif
"""
from PIL import Image
import os

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIAG = os.path.join(BASE, "archive", "diagrams", "PershingMetabolizer")
REF  = os.path.join(BASE, "archive", "reference_images")
OUT  = os.path.dirname(os.path.abspath(__file__))

POOLS = [
    ("phase01.gif", [
        os.path.join(REF,  "ViewCapture20260701_093804.png"),
        os.path.join(DIAG, "Access.png"),
        os.path.join(DIAG, "Amenities.png"),
        os.path.join(DIAG, "Connection.png"),
    ]),
    ("phase02.gif", [
        os.path.join(DIAG, "flux2_klein_00223_.png"),
        os.path.join(DIAG, "programming.png"),
        os.path.join(DIAG, "ComfyUI_00586_.png"),
    ]),
    ("phase03.gif", [
        os.path.join(DIAG, "image (5).png"),
        os.path.join(DIAG, "image (4).png"),
    ]),
]

FRAME_MS = 3000  # match the 3-second carousel interval

for name, paths in POOLS:
    frames = []
    for p in paths:
        if not os.path.exists(p):
            print(f"  MISSING: {p}")
            continue
        img = Image.open(p).convert("RGBA")
        frames.append(img)

    if len(frames) < 2:
        print(f"{name}: not enough frames, skipping")
        continue

    out_path = os.path.join(OUT, name)
    frames[0].save(
        out_path,
        save_all=True,
        append_images=frames[1:],
        duration=FRAME_MS,
        loop=0,
        optimize=False,
    )
    print(f"Saved {out_path}  ({len(frames)} frames)")
