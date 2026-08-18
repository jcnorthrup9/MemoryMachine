"""
Runs ONE randomized design iteration, seeded from a random 2D remixed
diagram, and writes its drawing set into its own folder:
outputs/batchExport/iter{N:03d}/{source_diagram.png, plan.png, axo.png,
long_section.png, params.json}. Invoked as its own subprocess by
run_batch_export.py -- isolates one bad iteration from the rest of the
batch and from anyone else's shared server (no HTTP, no live app needed).

SAFETY (2026-08-12, load-bearing): applying a diagram's grids the obvious
way -- logic.pershing_api.bake() -- PERSISTS to outputs/cockpit/
web_paint_state.json and mutates shared module globals. Calling it from
here would silently overwrite the user's real saved design. This script
NEVER calls bake(); it only reassigns pershing_api's module-level grid
globals in this process's own memory (see _apply_diagram_in_memory), which
dies with the process when this subprocess exits -- never touches disk or
any other process's state.

Diagram, massing, placement, and axo orientation are otherwise the real
(non-workaround) pipeline as of 2026-08-12: axo no longer needs a separate
memory-capped sub-subprocess (embreex + vector_export._batch_visible()'s
chunked fallback fixed the underlying trimesh/rtree pathology at the
source -- see git history for the win_job.py/axo_render_worker.py this
replaced), section/axo/long_section now include real building massing
(previously terrain-only), and program placement takes an opt-in
placement_seed for genuine per-iteration footprint diversity (previously a
fully deterministic packer with no randomness lever at all).
"""
import argparse
import json
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import drawing_styles
import logic.ai_synthesizer as ai_synthesizer
import logic.diagram_compositor as diagram_compositor
import logic.pershing_api as pershing_api
import logic.urban_engine as urban_engine
from logic.pershing_api import NX, NX_BAYS, NZ, REAL_GEOMETRY, RebuildParams, _empty_mask, _run_pipeline
from logic.program_placement import load_programs

REPO_ROOT = os.path.dirname(os.path.abspath(__file__))
PRECEDENT_SVG_DIR = os.path.join(REPO_ROOT, "data", "PershingMetabolizer", "parkSVG", "PrecedentSVG")

# NEEDED-tier programs always participate; only Suggested-tier ones are
# ever candidates for random exclusion (Optional is already excluded by
# load_programs()'s own default need_levels).
SUGGESTED_PROGRAM_IDS = [p["id"] for p in load_programs() if p["need_level"] == "Suggested"]


def _seed_diagram(rng):
    """Random 2D remixed diagram (spatial_seed) -- the same non-AI
    algorithmic picker the live app's empty-prompt "Random Remix" button
    uses (logic/ai_synthesizer.py's random_spatial_seed()), no network/LLM
    call needed. Returns (composed_layers, seed_items).

    random_spatial_seed()/remix_layers() both draw from the GLOBAL random
    module internally (not an injectable Random instance) -- reseeding it
    here from our own --seed-derived rng keeps the whole iteration
    (diagram included) reproducible from one --seed value, without a second
    uncontrolled randomness source."""
    random.seed(rng.random())
    gm_data = ai_synthesizer.guideline_manager.parse()
    zonal_metadata = gm_data.get("metadata", {})
    guidelines = gm_data.get("guidelines", {})
    available_sites = [f[:-4].replace("_", "").replace(" ", "")
                        for f in os.listdir(PRECEDENT_SVG_DIR) if f.lower().endswith(".svg")]
    seed_items = ai_synthesizer.random_spatial_seed(zonal_metadata, available_sites, guidelines)
    composed = urban_engine.remix_layers(seed_items)
    return composed, seed_items


def _apply_diagram_in_memory(composed):
    """Sets pershing_api's module-level grid globals from a composed
    diagram, IN THIS PROCESS ONLY -- see this file's own top-of-file SAFETY
    note. _compose_layers_to_3d()'s grids only ever cover hardscape/water/
    trees/greenscape/amenity_resting (confirmed by reading _infer_role's
    substring table -- no diagram layer role maps to "canyon"/"deck"/
    "canopy"), so those three are set to empty masks for a clean,
    diagram-only origin rather than left as whatever the real saved state
    (loaded at this process's own import time) happened to have."""
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


def sample_rebuild_params(rng):
    n_disabled = rng.randint(0, len(SUGGESTED_PROGRAM_IDS) // 2)
    disabled_programs = rng.sample(SUGGESTED_PROGRAM_IDS, n_disabled)
    return RebuildParams(
        sketch_alpha=rng.uniform(0, 1),
        canyon_width=rng.randint(1, NX_BAYS),
        canyon_depth=rng.randint(1, 4),
        material_mode=rng.choice(["STEEL", "WOOD"]),
        shoring_density=rng.uniform(0.5, 2.0),
        disabled_programs=disabled_programs,
        placement_seed=rng.randint(0, 2**31 - 1),
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--iter", type=int, required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--seed", type=int, required=True)
    args = ap.parse_args()

    tag = f"iter{args.iter:03d}"
    iter_dir = os.path.join(args.out_dir, tag)
    os.makedirs(iter_dir, exist_ok=True)

    rng = random.Random(args.seed)

    composed, seed_items = _seed_diagram(rng)
    diagram_resolved = diagram_compositor.compose_spatial_seed_png(
        composed, os.path.join(iter_dir, "source_diagram.png"))
    print(f"{tag}/source_diagram.png written ({diagram_resolved} layers resolved)")
    grids_resolved = _apply_diagram_in_memory(composed)

    rebuild_params = sample_rebuild_params(rng)
    with open(os.path.join(iter_dir, "params.json"), "w") as f:
        json.dump({
            "rebuild_params": rebuild_params.model_dump(),
            "seed_items": seed_items,
            "spatial_seed": composed,
            "diagram_layers_resolved": diagram_resolved,
            "diagram_grids_resolved": grids_resolved,
        }, f, indent=2)

    engine, voxels, typology_specs, _base_specs, _meta = _run_pipeline(rebuild_params)
    zones = pershing_api._program_zones_from_engine(
        engine, voxels, disabled_programs=rebuild_params.disabled_programs,
        placement_seed=rebuild_params.placement_seed)["zones"]

    for view in ("plan", "axo", "long_section"):
        png_bytes = drawing_styles.render_lineweight_png(
            REAL_GEOMETRY, engine, voxels, view=view, level="SURFACE", show_labels=False,
            typology_specs=typology_specs, zones=zones)
        with open(os.path.join(iter_dir, f"{view}.png"), "wb") as f:
            f.write(png_bytes)
        print(f"{tag}/{view}.png written")


if __name__ == "__main__":
    main()
