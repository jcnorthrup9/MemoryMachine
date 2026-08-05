"""
PershingMetabolizer_Prototype/build_real_geometry.py
------------------------------------------------------
Unified real_geometry.json builder: merges three sources into one file.

  1. SVG (structural_grid_analyzer.py, pershingRhinoPlanView.svg) -- site
     extent, column positions, entrance-anchor x/z.
  2. Layered OBJ (extract_real_geometry.extract_positions_from_layered_obj
     + extract_meshes_from_layered_obj, PershingCurrentMetabolism.obj) --
     site extent, column positions, grade_y, ramp anchors, entrance-anchor
     depth, AND (added 2026-07-09) real tunnel_mesh/secondary_entrance_mesh
     geometry. Real Rhino layer names as `g` groups (added 2026-07-08
     specifically to fix the grid-base OBJ's broken column heuristic and
     stale entrance mapping at the root).
  3. Grid-base OBJ (extract_real_geometry.extract_real_geometry,
     PershingMetablismGridBase.obj) -- ramp_meshes, column_prototype_mesh,
     column_height_ft only as of 2026-07-09 (tunnel_mesh/
     secondary_entrance_mesh moved to the layered OBJ, see below -- this
     file has no real face data for either of those, and is far older,
     June 28 vs. the layered OBJ's July exports). Its own position/depth
     extraction is known-broken (see PIPELINE_STATUS_AND_NEXT_STEPS.md)
     and isn't used for anything except the mesh fields above, which
     extract correctly independent of that.

Authority split, per the 2026-07-08/09 design discussion:
  - SVG wins for: site.width_ft/length_ft, column_positions (x/z),
    secondary_entrance_anchor.x/z. Proven this session via two independent
    cross-validations (live Rhino MCP query, and now the layered OBJ's own
    BOUNDARY/column extraction) to agree closely.
  - Layered OBJ wins for: grade_y_raw, ramp_anchors, secondary_entrance_
    anchor's depth values (SVG has no Z-axis data at all), AND (2026-07-09)
    tunnel_mesh/secondary_entrance_mesh -- real, freshly-extracted geometry
    (see extract_meshes_from_layered_obj's own docstring for why this beats
    the grid-base OBJ's mesh fields: real 196-face tunnel geometry now
    exists in this export where it previously didn't, and the entrance box
    is reconstructed from its own real bounding box instead of a stale,
    differently-positioned/sized placeholder). Its own entrance-anchor x/z
    is NOT trusted, deliberately -- confirmed 2026-07-08 that
    `metroConnection`'s object in this specific export reproduces the
    exact original pre-fix bug value (x=462.99, z=36.29) for the ANCHOR
    field specifically (a separate extraction path, position-only, see
    extract_positions_from_layered_obj) -- meaning that particular snapshot
    predates the live-Rhino correction verified earlier. Only its depth
    values (which do match the verified-correct ones) are used from that
    path; the newer mesh-geometry path (extract_meshes_from_layered_obj)
    reads the same underlying object fresh and isn't affected by that
    staleness.
  - Grid-base OBJ wins for: ramp_meshes, column_prototype_mesh,
    column_height_ft only -- nothing positional, and no longer tunnel/
    entrance mesh geometry either (see above).

Whenever sources disagree on the same field, this prints a [WARN] rather
than blocking -- same pattern as structural_grid_analyzer.py and
load_garage_depth_from_svg.

Run directly: python build_real_geometry.py
"""
import math
import os
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))   # PershingMetabolizer_Prototype/
REPO_ROOT = os.path.dirname(BASE_DIR)                     # derived, not hardcoded -- portable across synced machines

if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

import structural_grid_analyzer  # noqa: E402
from extract_real_geometry import (  # noqa: E402
    extract_real_geometry, extract_positions_from_layered_obj,
    extract_meshes_from_layered_obj, _make_box_mesh,
)

DEFAULT_SVG_PATH = os.path.join(REPO_ROOT, "data", "PershingMetabolizer", "parkSVG", "pershingRhinoPlanView.svg")
# .objbak, not the live .obj: on 2026-07-09 the user re-exported
# PershingMetablismGridBase.obj as a small, focused "layers as OBJ groups"
# file (floorplates/BOUNDARY/ramps/tunnel/metroConnection) -- useful fresh
# data (see extract_meshes_from_layered_obj usage above), but it no longer
# has STRUC__Columns at all, which extract_real_geometry()'s vertex-count-
# heuristic/hardcoded-name approach needs. .objbak is the untouched
# original (June 28) content this function was built against -- still the
# only current source with real column_prototype_mesh/ramp_meshes geometry.
DEFAULT_OBJ_PATH = os.path.join(REPO_ROOT, "data", "PershingMetabolizer", "OBJ", "PershingMetablismGridBase.objbak")
DEFAULT_LAYERED_OBJ_PATH = os.path.join(REPO_ROOT, "data", "PershingMetabolizer", "OBJ", "PershingCurrentMetabolism.obj")
DEFAULT_OUT_PATH = os.path.join(BASE_DIR, "real_geometry.json")
# Real on-center column spacing -- matches terracing_engine.py's own
# STRUCTURAL_BAY_FT. Duplicated rather than imported, same reasoning
# already established elsewhere in this project (blender_cockpit.py,
# pershing_headless_build.py): avoids pulling in terracing_engine.py's
# numpy dependency for one constant.
DEFAULT_COLUMN_SPACING_FT = 27.0

# Disagreement tolerances (feet) -- past this, print a [WARN] rather than
# silently trusting the winning source.
DIMENSION_TOLERANCE_FT = 5.0
ANCHOR_TOLERANCE_FT = 5.0
DEPTH_TOLERANCE_FT = 1.0


def build_real_geometry(svg_path=DEFAULT_SVG_PATH, obj_path=DEFAULT_OBJ_PATH,
                         layered_obj_path=DEFAULT_LAYERED_OBJ_PATH,
                         out_path=DEFAULT_OUT_PATH, spacing_ft=DEFAULT_COLUMN_SPACING_FT,
                         write=True):
    """
    Merge SVG + layered-OBJ + grid-base-OBJ geometry into one
    real_geometry.json. Returns the merged dict; writes to out_path when
    write=True (extract_real_geometry also writes a mesh-only intermediate
    to out_path along the way -- harmless, immediately overwritten with
    the final merged version below).
    """
    layered_result = extract_positions_from_layered_obj(layered_obj_path)
    # grade_y_override: the grid-base OBJ's own column extraction is broken
    # (see module docstring), so it can't establish this itself -- feed it
    # the layered OBJ's real, freshly-derived value instead of the old
    # file-bootstrap hack.
    obj_result = extract_real_geometry(obj_path, out_path, grade_y_override=layered_result["grade_y_raw"])
    svg_result = structural_grid_analyzer.load_structural_grid_from_svg(svg_path, spacing_ft)

    print(f"[build] SVG site: {svg_result['site_width_ft']:.2f} x {svg_result['site_height_ft']:.2f} ft")
    print(f"[build] layered-OBJ site: {layered_result['site']['width_ft']} x {layered_result['site']['length_ft']} ft")
    spread_w = abs(layered_result["site"]["width_ft"] - svg_result["site_width_ft"])
    spread_h = abs(layered_result["site"]["length_ft"] - svg_result["site_height_ft"])
    if spread_w > DIMENSION_TOLERANCE_FT or spread_h > DIMENSION_TOLERANCE_FT:
        print(f"[build][WARN] SVG/layered-OBJ site dimensions disagree by {spread_w:.1f}ft (width) / "
              f"{spread_h:.1f}ft (height) -- using SVG, but this is worth checking.")

    merged = dict(obj_result)

    # SVG wins: site extent.
    merged["site"] = {
        "width_ft": round(svg_result["site_width_ft"], 2),
        "length_ft": round(svg_result["site_height_ft"], 2),
    }

    # Layered OBJ wins: grade_y_raw -- real, freshly derived this run (not
    # bootstrapped from a prior file), see grade_y_override above.
    merged["grade_y_raw"] = layered_result["grade_y_raw"]

    # SVG wins: column positions (x/z). Both OBJ sources' column_positions
    # are only needed for the cross-validation print, not written out.
    svg_columns = [{"x": round(x, 3), "z": round(z, 3)} for x, z in svg_result["columns_ft"]]
    layered_columns = layered_result["column_positions"]
    if len(svg_columns) != len(layered_columns):
        print(f"[build][WARN] column count disagrees: SVG={len(svg_columns)} "
              f"layered-OBJ={len(layered_columns)} -- using SVG's column_positions.")
    merged["column_positions"] = svg_columns

    # Layered OBJ wins: ramp_anchors (real, position-only extraction --
    # see extract_positions_from_layered_obj's docstring for the spatial
    # clustering it uses). Grid-base OBJ's own ramp_anchors (in obj_result,
    # inherited via `merged = dict(obj_result)` above) were already working
    # correctly too -- this is a genuine upgrade to a freshly-verified
    # source, not a bug fix, so no disagreement warning is printed, just
    # the swap.
    if layered_result["ramp_anchors"]:
        merged["ramp_anchors"] = layered_result["ramp_anchors"]

    # Entrance anchor: SVG wins x/z (when it has the marker); layered OBJ
    # wins depth (verified correct -- matches the already-known-good
    # values exactly). Layered OBJ's OWN x/z is deliberately NOT used --
    # see module docstring: this file's metroConnection object reproduces
    # the exact original pre-fix bug value, a stale snapshot, not a live
    # cross-check.
    layered_anchor = layered_result["secondary_entrance_anchor"]
    top_depth_ft = layered_anchor["top_depth_ft"]
    bottom_depth_ft = layered_anchor["bottom_depth_ft"]

    grid_base_anchor = obj_result["secondary_entrance_anchor"]
    if abs(grid_base_anchor["top_depth_ft"] - top_depth_ft) > DEPTH_TOLERANCE_FT:
        print(f"[build][WARN] entrance anchor top_depth_ft disagrees: layered-OBJ={top_depth_ft} "
              f"grid-base-OBJ={grid_base_anchor['top_depth_ft']} -- using layered-OBJ "
              f"(grid-base's secondary_entrance_name mapping is known-stale).")
    if abs(grid_base_anchor["bottom_depth_ft"] - bottom_depth_ft) > DEPTH_TOLERANCE_FT:
        print(f"[build][WARN] entrance anchor bottom_depth_ft disagrees: layered-OBJ={bottom_depth_ft} "
              f"grid-base-OBJ={grid_base_anchor['bottom_depth_ft']} -- using layered-OBJ "
              f"(grid-base's secondary_entrance_name mapping is known-stale).")

    if svg_result["entrance_anchor_ft"] is not None:
        svg_x, svg_z = svg_result["entrance_anchor_ft"]
        spread = math.hypot(svg_x - layered_anchor["x"], svg_z - layered_anchor["z"])
        if spread > ANCHOR_TOLERANCE_FT:
            print(f"[build][WARN] entrance anchor x/z disagrees between SVG ({svg_x:.2f},{svg_z:.2f}) "
                  f"and layered-OBJ ({layered_anchor['x']:.2f},{layered_anchor['z']:.2f}) by {spread:.1f}ft -- "
                  f"expected, and NOT staleness (the 2026-07-09 Z-axis sign fix means layered-OBJ's z "
                  f"now agrees with SVG closely): this is X centroid (layered-OBJ, 462.99) vs X-min-bound "
                  f"(SVG, 378.51), two different, both-valid reference points on the same real "
                  f"metroConnection extrusion -- an intentional choice from earlier in this project, not "
                  f"a bug. Using SVG (its X-min-bound convention is what secondary_entrance_mesh's own "
                  f"real extraction also naturally aligns with).")
        merged["secondary_entrance_anchor"] = {
            "x": round(svg_x, 3),
            "z": round(svg_z, 3),
            "top_depth_ft": top_depth_ft,
            "bottom_depth_ft": bottom_depth_ft,
        }
    else:
        print("[build] no entrance-anchor marker in SVG -- using layered-OBJ x/z and depth.")
        merged["secondary_entrance_anchor"] = {
            "x": round(layered_anchor["x"], 3),
            "z": round(layered_anchor["z"], 3),
            "top_depth_ft": top_depth_ft,
            "bottom_depth_ft": bottom_depth_ft,
        }

    # tunnel_mesh / secondary_entrance_mesh: real geometry, extracted fresh
    # from the layered OBJ (PershingCurrentMetabolism.obj) instead of the
    # grid-base OBJ's much older (June 28) placeholder versions -- added
    # 2026-07-09 after the user pointed out the app didn't cleanly reflect
    # the most recent OBJ export. This REPLACES the earlier approach (patch
    # a stale, wrongly-positioned/wrongly-sized grid-base-OBJ mesh via
    # translate+rescale to match the anchor) with direct extraction from
    # the same real object the anchor itself comes from -- see
    # extract_meshes_from_layered_obj's docstring for the full story,
    # including a small sign-convention bug that approach had (assumed
    # depth_ft = -y; the real convention, used everywhere else in this
    # file, is depth_ft = grade_y_raw - y, and grade_y_raw is ~3.73, not 0).
    layered_meshes = extract_meshes_from_layered_obj(layered_obj_path)

    def _bounds(mesh_dict):
        vs = list(zip(*[iter(mesh_dict["vertices"])] * 3))
        return (min(v[0] for v in vs), max(v[0] for v in vs),
                min(v[1] for v in vs), max(v[1] for v in vs),
                min(v[2] for v in vs), max(v[2] for v in vs))

    old_tunnel_bounds = _bounds(merged["tunnel_mesh"])
    new_tunnel_bounds = _bounds(layered_meshes["tunnel_mesh"])
    if math.hypot(*(a - b for a, b in zip(old_tunnel_bounds, new_tunnel_bounds))) > DIMENSION_TOLERANCE_FT:
        print(f"[build][WARN] tunnel_mesh bounds disagree between grid-base OBJ {old_tunnel_bounds} "
              f"and layered OBJ {new_tunnel_bounds} -- expected (layered OBJ is far newer and now has "
              f"real face data, grid-base OBJ's mesh predates the current Rhino model). Using layered OBJ.")
    merged["tunnel_mesh"] = layered_meshes["tunnel_mesh"]

    # secondary_entrance_mesh: real shape/size/depth/position, all four
    # straight from extract_meshes_from_layered_obj's own (2026-07-09
    # Z-axis-sign-fixed) extraction -- no translate/rescale patch needed
    # anymore. Sanity-check against the anchor rather than blindly patch:
    # if this and the (SVG-sourced) anchor still disagree beyond tolerance,
    # something is wrong again and worth a fresh look, not silent papering.
    se_mesh = layered_meshes["secondary_entrance_mesh"]
    se_verts = [list(v) for v in zip(*[iter(se_mesh["vertices"])] * 3)]
    mesh_center_z = (min(v[2] for v in se_verts) + max(v[2] for v in se_verts)) / 2.0
    anchor_z = merged["secondary_entrance_anchor"]["z"]
    if abs(mesh_center_z - anchor_z) > ANCHOR_TOLERANCE_FT:
        print(f"[build][WARN] secondary_entrance_mesh's own Z-centroid ({mesh_center_z:.2f}) disagrees "
              f"with secondary_entrance_anchor.z ({anchor_z:.2f}) by {abs(mesh_center_z - anchor_z):.1f}ft "
              f"-- expected these to closely agree post-2026-07-09-Z-fix (both derive from the same "
              f"metroConnection object). Worth investigating, not silently patching.")
    merged["secondary_entrance_mesh"] = se_mesh
    print(f"[build] tunnel_mesh/secondary_entrance_mesh replaced with real, freshly-extracted "
          f"geometry from {os.path.basename(layered_obj_path)} (mesh Z-centroid {mesh_center_z:.2f} "
          f"vs anchor.z {anchor_z:.2f} -- no patch needed, extraction is correct at the source)")

    # ramp_meshes: real spiral-core geometry (only source with actual face
    # data for ramps -- CIRC__Ramps has vertices but zero faces in every
    # current "layers as OBJ groups" export, layered or grid-base), but
    # positioned ~11-30ft off from the freshly-verified ramp_anchors
    # (layered OBJ). Investigated 2026-07-09 whether this is the same
    # Z-axis sign bug found elsewhere today: ruled out -- a real sign-flip
    # bug would either leave a near-center object's position nearly
    # untouched (as it did for ramp_anchors itself, sitting almost exactly
    # at the site Z-midpoint) or shift it by a clean mirror amount
    # (site_length_ft - value); neither pattern matches here, and the two
    # clusters' mutual spacing also differs between sources (192ft vs
    # 246ft), which a pure coordinate-convention bug wouldn't cause. Most
    # likely explanation: the grid-base OBJ is from 2026-06-28, 11 days
    # before the layered OBJ -- genuine staleness (the ramps were likely
    # refined/repositioned in Rhino since), not a formula bug. Translated
    # per-cluster (X and Z) onto the trusted anchor position, same
    # established pattern as other real-but-stale-positioned meshes this
    # session -- keeps the real spiral-core shape, fixes its site position.
    for cluster_name, anchor in merged["ramp_anchors"].items():
        levels = merged["ramp_meshes"].get(cluster_name)
        if not levels:
            continue
        first_verts = list(zip(*[iter(levels[0]["vertices"])] * 3))
        mesh_cx = (min(v[0] for v in first_verts) + max(v[0] for v in first_verts)) / 2.0
        mesh_cz = (min(v[2] for v in first_verts) + max(v[2] for v in first_verts)) / 2.0
        dx, dz = anchor["x"] - mesh_cx, anchor["z"] - mesh_cz
        for level in levels:
            lverts = [list(v) for v in zip(*[iter(level["vertices"])] * 3)]
            for v in lverts:
                v[0] += dx
                v[2] += dz
            level["vertices"] = [c for v in lverts for c in v]
        print(f"[build] translated ramp_meshes[{cluster_name}] by ({dx:+.2f}, {dz:+.2f})ft "
              f"(real spiral-core shape from grid-base OBJ, ~11-30ft stale position -> "
              f"matched to freshly-verified ramp_anchors)")

    # metro_connector_mesh: a placeholder box bridging the park's own site
    # boundary (width axis) out to the vestibule -- both
    # secondary_entrance_mesh and tunnel_mesh sit entirely outside the site
    # boundary (under the street, as expected for real Metro
    # infrastructure), leaving a real, unmodeled gap the user noticed
    # visually in the running app. Ports generate_phase_scenes.py's (the
    # older, superseded prototype) own orphaned `tunnel_connector` concept
    # -- same X/Z/Y derivation, never carried over to this
    # real_geometry.json-driven pipeline. Z/Y match the vestibule's own
    # (now real, not patched) footprint/depth; X spans from the site
    # boundary to the vestibule's own near edge, read from its vertices,
    # not hardcoded, so it stays correct if the vestibule position ever
    # changes again.
    se_xmin, se_xmax, se_ymin, se_ymax, se_zmin, se_zmax = _bounds(merged["secondary_entrance_mesh"])
    connector_xmin = merged["site"]["width_ft"]
    connector_xmax = se_xmin
    merged["metro_connector_mesh"] = _make_box_mesh(
        min(connector_xmin, connector_xmax), max(connector_xmin, connector_xmax),
        se_ymin, se_ymax,
        se_zmin, se_zmax,
    )
    print(f"[build] added metro_connector_mesh: X {connector_xmin:.2f}..{connector_xmax:.2f}, "
          f"Y {se_ymin:.2f}..{se_ymax:.2f}, Z {se_zmin:.2f}..{se_zmax:.2f} "
          f"(park boundary -> vestibule, ports generate_phase_scenes.py's orphaned tunnel_connector)")

    merged["_meta"] = (
        "Built via build_real_geometry.py (2026-07-09): merges SVG-derived "
        "(structural_grid_analyzer.py), layered-OBJ-derived "
        "(extract_real_geometry.extract_positions_from_layered_obj + "
        "extract_meshes_from_layered_obj, real Rhino layer names as g "
        "groups), and grid-base-OBJ-derived (extract_real_geometry."
        "extract_real_geometry) geometry. SVG wins site.width_ft/length_ft, "
        "column_positions, secondary_entrance_anchor.x/z; layered OBJ wins "
        "grade_y_raw, ramp_anchors, secondary_entrance_anchor's depth, AND "
        "(2026-07-09) tunnel_mesh/secondary_entrance_mesh -- real, freshly-"
        "extracted geometry, no longer the grid-base OBJ's much older "
        "placeholders; grid-base OBJ now wins only ramp_meshes/"
        "column_prototype_mesh/column_height_ft. metro_connector_mesh is a "
        "new, procedurally-generated placeholder box bridging the site "
        "boundary to the vestibule (ports generate_phase_scenes.py's "
        "orphaned tunnel_connector concept). See "
        "PIPELINE_STATUS_AND_NEXT_STEPS.md's 2026-07-08/09 entries for why."
    )

    if write:
        import json
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(merged, f)
        size_kb = os.path.getsize(out_path) / 1024
        print(f"[build] wrote merged real_geometry.json -> {out_path} ({size_kb:.1f} KB)")

    return merged


if __name__ == "__main__":
    build_real_geometry()
