"""
Aggregates all submissions collected by qr_event_server.py into ONE final
design reflecting the audience's combined input, ready to reveal during
the presentation. Run this once collection has closed (past the server's
--deadline).

Tallies both structured quick-pick selections (already canonical layer/site
ids, no ambiguity) and free-text submissions (via
logic.ai_synthesizer.extract_prompt_hints -- same loose keyword matching
the live app uses, e.g. "too hot" -> SHADE) into one combined frequency
count, then builds a seed_items list from the top-ranked layers/site
(mirrors ai_synthesizer._ensure_hints_present's site+layers pairing, but
ranked by real vote count instead of just "was it mentioned at all").

SAFETY: mirrors batch_export_worker.py's own note -- applies the composed
diagram's grids to logic.pershing_api's module globals IN THIS PROCESS
ONLY, never calling bake() (which persists to outputs/cockpit/
web_paint_state.json and would overwrite your real saved design).

Usage: python ingest_qr_event.py
Output: outputs/qr_event/final_design/{source_diagram,plan,axo,long_section,color}.png
        outputs/qr_event/final_design/summary.json (raw vote tallies)
"""
import json
import os
import random
from collections import Counter

import drawing_styles
import logic.ai_synthesizer as ai_synthesizer
import logic.diagram_compositor as diagram_compositor
import logic.pershing_api as pershing_api
import logic.urban_engine as urban_engine
from circulation_network import CirculationNetworkEngine
from logic.pershing_api import NX, NZ, REAL_GEOMETRY, RebuildParams, _empty_mask, _run_pipeline

REPO_ROOT = os.path.dirname(os.path.abspath(__file__))
EVENT_DIR = os.path.join(REPO_ROOT, "outputs", "qr_event")
SUBMISSIONS_PATH = os.path.join(EVENT_DIR, "submissions.jsonl")
OUT_DIR = os.path.join(EVENT_DIR, "final_design")

TOP_N_LAYERS = 5  # remix_layers() caps seed_items at 5 anyway
AVAILABLE_SITES = ["PershingSquare", "Schouwburgplein", "GardensBytheBay", "ZaryadyePark", "ParcVillette"]
LOCATIONS = ["North", "North-East", "East", "South-East", "South", "South-West", "West", "North-West", "Center"]


def load_submissions():
    if not os.path.exists(SUBMISSIONS_PATH):
        return []
    with open(SUBMISSIONS_PATH, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def tally(submissions):
    layer_counts = Counter()
    site_counts = Counter()
    for sub in submissions:
        for layer in sub.get("layers") or []:
            layer_counts[layer] += 1
        if sub.get("site"):
            site_counts[sub["site"]] += 1
        hints = ai_synthesizer.extract_prompt_hints(sub.get("text") or "")
        for layer in hints["layers"]:
            layer_counts[layer] += 1
        for site in hints["sites"]:
            site_counts[site] += 1
    return layer_counts, site_counts


def build_seed_items(layer_counts, site_counts):
    top_layers = [layer for layer, _n in layer_counts.most_common(TOP_N_LAYERS)]
    if not top_layers:
        top_layers = ["GREEN_SPACE"]  # nobody submitted anything -- sane default, not an error
    winning_site = site_counts.most_common(1)[0][0] if site_counts else None

    return [
        {
            "site": winning_site or random.choice(AVAILABLE_SITES),
            "layer": layer,
            "location": random.choice(LOCATIONS),
            "width": 20, "height": 20,
            # Crowd-voted -- skip remix_layers()' anchor-coverage step
            # adding a competing pick for the same category, same as a
            # live user's explicit request would (see
            # ai_synthesizer._ensure_hints_present).
            "_explicit_hint": True,
        }
        for layer in top_layers
    ]


def apply_diagram_in_memory(composed):
    """Mirrors batch_export_worker.py's function of the same name -- see
    this file's own SAFETY note above."""
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
    submissions = load_submissions()
    print(f"{len(submissions)} submissions loaded from {SUBMISSIONS_PATH}")
    if not submissions:
        print("No submissions -- nothing to ingest.")
        return

    layer_counts, site_counts = tally(submissions)
    print("Layer votes:", dict(layer_counts.most_common()))
    print("Site votes:", dict(site_counts.most_common()))

    seed_items = build_seed_items(layer_counts, site_counts)
    composed = urban_engine.remix_layers(seed_items)

    os.makedirs(OUT_DIR, exist_ok=True)

    resolved = diagram_compositor.compose_spatial_seed_png(composed, os.path.join(OUT_DIR, "source_diagram.png"))
    print(f"source_diagram.png written ({resolved} layers resolved)")

    apply_diagram_in_memory(composed)

    # Crowd input drives the 2D diagram (what programs/atmosphere to
    # emphasize); 3D excavation params stay at their defaults -- the
    # audience wasn't asked about canyon depth/material, so there's
    # nothing to aggregate there.
    rebuild_params = RebuildParams()
    engine, voxels, typology_specs, _base_specs, _meta = _run_pipeline(rebuild_params)
    zones = pershing_api._program_zones_from_engine(
        engine, voxels, disabled_programs=rebuild_params.disabled_programs,
        placement_seed=rebuild_params.placement_seed)["zones"]

    for view in ("plan", "axo", "long_section"):
        png_bytes = drawing_styles.render_lineweight_png(
            REAL_GEOMETRY, engine, voxels, view=view, level="SURFACE", show_labels=False,
            typology_specs=typology_specs, zones=zones)
        with open(os.path.join(OUT_DIR, f"{view}.png"), "wb") as f:
            f.write(png_bytes)
        print(f"{view}.png written")

    program_boxes = pershing_api._drawing_program_boxes(zones)
    circulation_specs = CirculationNetworkEngine(
        REAL_GEOMETRY, engine, typology_specs, zones=zones, path_hints=pershing_api.PATH_HINT_POINTS).run()
    color_png = drawing_styles.render_color_png(
        program_boxes, circulation_specs, voxels, engine.voxel_ft,
        REAL_GEOMETRY, typology_specs, engine.site_width_ft, engine.site_length_ft,
        show_labels=False, zones=zones)
    with open(os.path.join(OUT_DIR, "color.png"), "wb") as f:
        f.write(color_png)
    print("color.png written")

    with open(os.path.join(OUT_DIR, "summary.json"), "w") as f:
        json.dump({
            "submission_count": len(submissions),
            "layer_votes": dict(layer_counts.most_common()),
            "site_votes": dict(site_counts.most_common()),
            "seed_items": seed_items,
        }, f, indent=2)
    print(f"\nDone. Final design in {OUT_DIR}")


if __name__ == "__main__":
    main()
