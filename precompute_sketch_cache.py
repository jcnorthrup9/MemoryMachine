"""
Precompute the sketch-weight grid for the Blender cockpit (blender_cockpit.py).

Blender's bundled Python can't be relied on to have PIL/svgpathtools (the
dependencies sketch_weight_mapper.py needs to actually parse a sketch file),
so this runs in the normal project venv instead, and dumps the resulting
(nx, nz) grid to plain JSON (nested list, no numpy dtype) -- the cockpit
script only ever needs to load that JSON plus terracing_engine.py, which is
pure stdlib.

Re-run this any time the sketch file or TerracingEngine's voxel_ft changes.
"""
import json
import os

from terracing_engine import TerracingEngine
from sketch_weight_mapper import build_sketch_weights, build_hardscape_regions, find_latest_sketch

OUT_DIR = os.path.join("outputs", "cockpit")
OUT_PATH = os.path.join(OUT_DIR, "sketch_weights_cache.json")


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    real_geometry = json.load(open("PershingMetabolizer_Prototype/real_geometry.json"))
    engine = TerracingEngine(real_geometry)

    sketch_path = find_latest_sketch()
    if sketch_path is None:
        raise FileNotFoundError("no sketch files found in data/sketches")

    weights = build_sketch_weights(engine, image_path=sketch_path)
    grid = weights.tolist()

    # Hardscape (blue) regions -- combined via OR into one (nx, nz) mask, same
    # cheap-to-cache plain-JSON approach as sketch_weights. The one real sketch
    # on hand is black-line-only, so this is currently expected to come back
    # empty (all False) -- cached anyway so the cockpit's toggle has real,
    # if currently no-op, data to flip on/off rather than a stub.
    regions = build_hardscape_regions(engine, image_path=sketch_path)
    hardscape_mask = [[False] * engine.nz for _ in range(engine.nx)]
    for region in regions:
        mask = region["mask"]
        for gx in range(engine.nx):
            for gy in range(engine.nz):
                if mask[gx][gy]:
                    hardscape_mask[gx][gy] = True

    with open(OUT_PATH, "w") as f:
        json.dump({
            "sketch_path": sketch_path,
            "nx": engine.nx, "nz": engine.nz,
            "weights": grid,
            "hardscape_mask": hardscape_mask,
        }, f)

    nonzero = sum(1 for row in grid for v in row if v > 0.01)
    hardscape_count = sum(1 for row in hardscape_mask for v in row if v)
    print(f"sketch: {sketch_path}")
    print(f"grid: {engine.nx} x {engine.nz}, {nonzero} cells with weight > 0.01")
    print(f"hardscape regions found: {len(regions)}, {hardscape_count} cells flagged")
    print(f"wrote {OUT_PATH}")


if __name__ == "__main__":
    main()
