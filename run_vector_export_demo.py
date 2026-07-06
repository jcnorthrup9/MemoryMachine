"""
Demo/test driver for vector_export.py: generates the Metro-entrance section
cut plus a plan cut at each named garage level (see
GARAGE_LEVEL_ELEVATIONS_FT), each tagged with an elevation label, to both
DXF and SVG under outputs/vector_export_test/.

Per project decision (2026-07-03): this "clean" diagram export always runs,
even after the Blender high-fidelity/eroded pass (Section 4) exists -- that
pass will export additionally to its own folder, not replace this one. Two
parallel output styles by design, not a placeholder waiting to be swapped out.

Not a pipeline entry point yet -- a manually-run script for exercising and
eyeballing the export engine while it's still being built out. Re-run any
time after editing the source Rhino OBJ/SVG and regenerating
real_geometry.json (see extract_real_geometry.py).
"""
import json
import os

from terracing_engine import TerracingEngine
from vector_export import (
    build_combined_mesh, mirror_mesh_y, section_cut, plan_cut, path3d_to_2d_segments,
    grid_layer_points, export_dxf, export_svg, export_png, format_elevation_ft,
    axonometric_projection, filter_short_polylines, street_label_points, axo_label_points,
    GARAGE_LEVEL_ELEVATIONS_FT,
    LAYER_CUT, LAYER_PROJECTION, LAYER_BOTANICAL, LAYER_GRID,
)

OUT_DIR = os.path.join("outputs", "vector_export_test")
# Tiny offset off any exact nominal elevation -- cutting exactly coplanar
# with the grade plate / column tops / a level slab is a degenerate case
# for mesh-plane intersection (see terracing_engine session notes).
CUT_EPSILON_FT = 0.05
# Toggle: bake street-name labels (LAYER_05_LABELS) into plan-view exports.
SHOW_LABELS = True


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    real_geometry = json.load(open("PershingMetabolizer_Prototype/real_geometry.json"))
    engine = TerracingEngine(real_geometry)
    voxels = engine.run(phase=3)
    combined = build_combined_mesh(real_geometry, engine, voxels)
    grid_pts = [[pt] for pt in grid_layer_points(real_geometry)]
    labels = street_label_points(engine.site_width_ft, engine.site_length_ft) if SHOW_LABELS else None

    # --- Section cut through the Metro entrance ---
    entrance_y = real_geometry["secondary_entrance_anchor"]["z"]
    path = section_cut(combined, plane_origin=[0, entrance_y, 0], plane_normal=[0, 1, 0])
    segs, _ = path3d_to_2d_segments(path)
    layers = {LAYER_CUT: segs, LAYER_PROJECTION: [], LAYER_BOTANICAL: []}
    title = f"SECTION THRU METRO ENTRANCE (y={entrance_y:.1f}ft)"
    export_dxf(os.path.join(OUT_DIR, "section_entrance.dxf"), layers, title=title)
    export_svg(os.path.join(OUT_DIR, "section_entrance.svg"), layers, title=title)
    export_png(os.path.join(OUT_DIR, "section_entrance.png"), layers, title=title)
    print(f"section_entrance: {len(segs)} cut segments")

    # --- Plan cuts, one per named garage level ---
    for name, z in GARAGE_LEVEL_ELEVATIONS_FT:
        cut_z = z - CUT_EPSILON_FT  # nudge off the exact nominal elevation
        p = plan_cut(combined, cut_z)
        if p is None:
            print(f"{name} ({format_elevation_ft(z)}): NO INTERSECTION -- skipped")
            continue
        psegs, _ = path3d_to_2d_segments(p)
        plan_layers = {
            LAYER_CUT: psegs,
            LAYER_PROJECTION: [],
            LAYER_BOTANICAL: [],
            LAYER_GRID: grid_pts,
        }
        tag = f"{name} -- {format_elevation_ft(z)}"
        slug = name.lower().replace(" ", "_").replace("/", "_")
        # Site grid is ~36deg off true north (see index.html SITE_ROTATION_DEG) and
        # these are orthogonal-to-site-grid drawings, not true-north-up -- "which
        # end is up" is an undecided page-layout choice, so export both variants.
        export_dxf(os.path.join(OUT_DIR, f"plan_{slug}_6thup.dxf"), plan_layers, title=tag, labels=labels)
        export_svg(os.path.join(OUT_DIR, f"plan_{slug}_6thup.svg"), plan_layers, title=tag, labels=labels)
        export_png(os.path.join(OUT_DIR, f"plan_{slug}_6thup.png"), plan_layers, title=tag, labels=labels)
        export_dxf(os.path.join(OUT_DIR, f"plan_{slug}_5thup.dxf"), plan_layers, title=tag, labels=labels, mirror_y=True)
        export_svg(os.path.join(OUT_DIR, f"plan_{slug}_5thup.svg"), plan_layers, title=tag, labels=labels, mirror_y=True)
        export_png(os.path.join(OUT_DIR, f"plan_{slug}_5thup.png"), plan_layers, title=tag, labels=labels, mirror_y=True)
        print(f"{tag}: {len(psegs)} cut segments (exported 5th-up and 6th-up)")

    # --- Axonometric (isometric, hidden-line-removed) ---
    # Mirrored along the short edge (site-length/5th-6th axis) per user
    # confirmation 2026-07-03: the un-mirrored view put the Metro entrance/
    # tunnel toward the bottom of the frame -- a result of which direction
    # Rhino's own Y axis happened to run in the source model, not a bug in
    # this projection. X (Olive/Hill) is untouched, already correct.
    axo_mesh = mirror_mesh_y(combined, engine.site_length_ft)
    axo_polylines = axonometric_projection(axo_mesh)
    axo_filtered = filter_short_polylines(axo_polylines)
    print(f"axo: {len(axo_filtered)}/{len(axo_polylines)} polylines survived span filter")
    axo_layers = {LAYER_PROJECTION: axo_filtered}
    axo_title = "AXONOMETRIC (isometric, hidden-line-removed)"
    axo_labels = axo_label_points(engine.site_width_ft, engine.site_length_ft, mirror_y=True) if SHOW_LABELS else None
    export_dxf(os.path.join(OUT_DIR, "axo_isometric.dxf"), axo_layers, title=axo_title, labels=axo_labels)
    export_svg(os.path.join(OUT_DIR, "axo_isometric.svg"), axo_layers, title=axo_title, labels=axo_labels)
    export_png(os.path.join(OUT_DIR, "axo_isometric.png"), axo_layers, title=axo_title, labels=axo_labels)

    print(f"\nAll exports written to {os.path.abspath(OUT_DIR)}")


if __name__ == "__main__":
    main()
