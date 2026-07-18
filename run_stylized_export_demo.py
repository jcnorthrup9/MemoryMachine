"""
run_stylized_export_demo.py
----------------------------
Manually-run script (same convention as run_vector_export_demo.py -- not a
pipeline entry point) that pulls one realistic snapshot of the Metabolizer's
real site geometry (buildings, circulation, landscape, hardscape paths)
through the existing engines, categorizes it, and writes a layered DXF +
quick-look SVG to outputs/stylized_export_test/ -- the plain, un-styled
geometry a Grasshopper definition will apply the actual pattern-language
styling to (see the "Categorized-geometry export for a Rhino+Grasshopper
styling pass" plan).

Deliberately standalone and isolated: only reads from logic.pershing_api /
terracing_engine / circulation_network via their existing, already-public
functions/classes (the same calls rebuild()/grow_network() themselves
already make) -- doesn't modify or get imported by any of them, and writes
to its own output folder, never outputs/vector_export_test/ (that folder,
and every existing SVG/PNG/DXF export in the app, stays untouched by this
file's existence).
"""
import os

from logic.pershing_api import (
    REAL_GEOMETRY, REAL_LEVEL_HEIGHT_FT, RebuildParams, BuildingSpec,
    _run_pipeline, _program_zones_from_engine,
)
from terracing_engine import BuildingMassEngine, STRUCTURAL_BAY_FT
from circulation_network import CirculationNetworkEngine
from stylized_pattern_export import categorize_site_geometry, export_categorized_dxf, export_categorized_svg

OUT_DIR = os.path.join("outputs", "stylized_export_test")


def main():
    os.makedirs(OUT_DIR, exist_ok=True)

    rebuild_params = RebuildParams()
    engine, voxels, typology_specs, _base_specs, _meta = _run_pipeline(rebuild_params)
    zones = _program_zones_from_engine(
        engine, voxels, disabled_programs=rebuild_params.disabled_programs)["zones"]

    # Same program_box_specs construction logic/pershing_api.py::rebuild()
    # itself uses (one building_mass box per claimed bay).
    program_box_specs = [
        BuildingSpec(
            x_ft=gx * STRUCTURAL_BAY_FT,
            y_ft=gy * STRUCTURAL_BAY_FT,
            width_ft=STRUCTURAL_BAY_FT,
            depth_ft=STRUCTURAL_BAY_FT,
            height_ft=REAL_LEVEL_HEIGHT_FT * (2 if zone.get("double_height") else 1),
            z_ft=floor_elev_ft,
        )
        for zone in zones
        for gx, gy, floor_elev_ft in zone["bays"]
    ]
    program_boxes = BuildingMassEngine([b.model_dump() for b in program_box_specs]).run()

    net = CirculationNetworkEngine(REAL_GEOMETRY, engine, typology_specs, zones=zones)
    circulation_specs = net.run()

    categorized = categorize_site_geometry(program_boxes, circulation_specs, voxels, engine.voxel_ft)

    dxf_path = export_categorized_dxf(categorized, os.path.join(OUT_DIR, "stylized_categorized.dxf"))
    svg_path = export_categorized_svg(
        categorized, engine.site_width_ft, engine.site_length_ft,
        os.path.join(OUT_DIR, "stylized_categorized_preview.svg"),
    )

    for category, polylines in categorized.items():
        print(f"{category}: {len(polylines)} polylines")
    print(f"\nWrote {dxf_path}\nWrote {svg_path}")


if __name__ == "__main__":
    main()
