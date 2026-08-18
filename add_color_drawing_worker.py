"""
Reproduces ONE existing outputs/batchExport/iter{N:03d}/ folder's exact
design from its already-saved params.json and renders just the color-style
categorized site plan, by default into that same folder as color.png.
Invoked as its own subprocess by add_color_drawing.py (or
add_color_drawings_flat.py, which passes --out-file to redirect output into
outputs/batchExport/colorDiagrams/iter{N:03d}_color.png instead).

SAFETY: same as batch_export_worker.py -- applies the diagram's grids to
logic.pershing_api's module globals IN THIS PROCESS ONLY, never calling
bake() (which persists to outputs/cockpit/web_paint_state.json). See that
file's own top-of-file note for why this matters.
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import drawing_styles
import logic.pershing_api as pershing_api
from circulation_network import CirculationNetworkEngine
from logic.pershing_api import NX, NZ, REAL_GEOMETRY, RebuildParams, _empty_mask, _run_pipeline


def _apply_diagram_in_memory(composed):
    """Mirrors batch_export_worker.py's function of the same name -- see
    its docstring. Duplicated rather than imported to keep each worker
    independently invocable without cross-importing another __main__-style
    script."""
    _layers, grids, _counts, attractor_points, path_hints, resolved_count = \
        pershing_api._compose_layers_to_3d(composed)
    empty = _empty_mask(NX, NZ)
    pershing_api.SKETCH_WEIGHTS = empty
    pershing_api.HARDSCAPE_MASK = grids["hardscape"]
    pershing_api.WATER_MASK = grids["water"]
    pershing_api.TREE_MASK = grids["trees"]
    pershing_api.GREENSCAPE_MASK = grids["greenscape"]
    pershing_api.AMENITY_RESTING_MASK = grids["amenity_resting"]
    pershing_api.DECK_MASK = empty
    pershing_api.CANOPY_MASK = empty
    pershing_api.ATTRACTOR_POINTS = attractor_points
    pershing_api.PATH_HINT_POINTS = path_hints
    return resolved_count


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--iter-dir", required=True)
    ap.add_argument("--out-file", default=None,
                     help="Defaults to <iter-dir>/color.png if omitted.")
    args = ap.parse_args()

    with open(os.path.join(args.iter_dir, "params.json")) as f:
        saved = json.load(f)

    rebuild_params = RebuildParams(**saved["rebuild_params"])
    _apply_diagram_in_memory(saved["spatial_seed"])

    engine, voxels, typology_specs, _base_specs, _meta = _run_pipeline(rebuild_params)
    zones = pershing_api._program_zones_from_engine(
        engine, voxels, disabled_programs=rebuild_params.disabled_programs,
        placement_seed=rebuild_params.placement_seed)["zones"]

    program_boxes = pershing_api._drawing_program_boxes(zones)
    circulation_specs = CirculationNetworkEngine(
        REAL_GEOMETRY, engine, typology_specs, zones=zones,
        path_hints=pershing_api.PATH_HINT_POINTS).run()

    png_bytes = drawing_styles.render_color_png(
        program_boxes, circulation_specs, voxels, engine.voxel_ft,
        REAL_GEOMETRY, typology_specs, engine.site_width_ft, engine.site_length_ft,
        show_labels=False, zones=zones)

    out_file = args.out_file or os.path.join(args.iter_dir, "color.png")
    with open(out_file, "wb") as f:
        f.write(png_bytes)
    print(f"{out_file} written")


if __name__ == "__main__":
    main()
