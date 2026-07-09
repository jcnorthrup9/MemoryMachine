"""
PershingMetabolizer_Prototype/build_real_geometry.py
------------------------------------------------------
Unified real_geometry.json builder: merges three sources into one file.

  1. SVG (structural_grid_analyzer.py, pershingRhinoPlanView.svg) -- site
     extent, column positions, entrance-anchor x/z.
  2. Layered OBJ (extract_real_geometry.extract_positions_from_layered_obj,
     PershingCurrentMetabolism.obj) -- site extent, column positions,
     grade_y, ramp anchors, entrance-anchor depth. Real Rhino layer names
     as `g` groups (added 2026-07-08 specifically to fix the grid-base
     OBJ's broken column heuristic and stale entrance mapping at the root).
  3. Grid-base OBJ (extract_real_geometry.extract_real_geometry,
     PershingMetablismGridBase.obj) -- mesh geometry only (tunnel_mesh,
     secondary_entrance_mesh, ramp_meshes, column_prototype_mesh,
     column_height_ft). Its own position/depth extraction is known-broken
     (see PIPELINE_STATUS_AND_NEXT_STEPS.md) and isn't used for anything
     except those mesh fields, which extract correctly independent of that.

Authority split, per the 2026-07-08 design discussion:
  - SVG wins for: site.width_ft/length_ft, column_positions (x/z),
    secondary_entrance_anchor.x/z. Proven this session via two independent
    cross-validations (live Rhino MCP query, and now the layered OBJ's own
    BOUNDARY/column extraction) to agree closely.
  - Layered OBJ wins for: grade_y_raw, ramp_anchors, and
    secondary_entrance_anchor's depth values (SVG has no Z-axis data at
    all). Its own entrance-anchor x/z is NOT trusted, deliberately --
    confirmed 2026-07-08 that `metroConnection`'s object in this specific
    export reproduces the exact original pre-fix bug value (x=462.99,
    z=36.29), meaning this file's snapshot of that object predates the
    live-Rhino correction verified earlier this session. Only its depth
    values (which do match the verified-correct ones) are used.
  - Grid-base OBJ wins for: mesh geometry only, nothing positional.

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
from extract_real_geometry import extract_real_geometry, extract_positions_from_layered_obj  # noqa: E402

DEFAULT_SVG_PATH = os.path.join(REPO_ROOT, "data", "PershingMetabolizer", "parkSVG", "pershingRhinoPlanView.svg")
DEFAULT_OBJ_PATH = os.path.join(REPO_ROOT, "data", "PershingMetabolizer", "OBJ", "PershingMetablismGridBase.obj")
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
                  f"expected (layered-OBJ's metroConnection object is a stale pre-fix snapshot, "
                  f"see module docstring). Using SVG.")
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

    # secondary_entrance_mesh's own embedded vertex geometry comes from the
    # grid-base OBJ's stale "object_2" mapping (see module docstring / the
    # secondary_entrance_anchor discussion above) and was never repositioned
    # when the anchor's x/z got corrected via SVG+live-Rhino cross-validation
    # earlier -- confirmed 2026-07-08 (user report: "metro connection...on
    # the opposite corner of where they should be") that this mesh's own
    # length-axis span (site-local "z", ~0-54.5ft) sat near the *old*,
    # pre-fix anchor position while the anchor itself moved to ~566ft during
    # this session, an inconsistency nothing had caught since the two are
    # separate fields. X already matches (`min(mesh x) ~= anchor.x`, both
    # sampled from the same real Rhino extrusion) so only the length axis
    # needs shifting -- translate the mesh's own length-axis centroid onto
    # the now-verified-correct anchor.z, keeping its existing shape/size
    # (still a placeholder box, not real entrance-structure geometry, but at
    # least positioned where the real entrance actually is).
    se_mesh = merged.get("secondary_entrance_mesh")
    if se_mesh is not None:
        se_verts = [list(v) for v in zip(*[iter(se_mesh["vertices"])] * 3)]
        z_vals = [v[2] for v in se_verts]
        current_center_z = (min(z_vals) + max(z_vals)) / 2.0
        target_z = merged["secondary_entrance_anchor"]["z"]
        delta_z = target_z - current_center_z
        for v in se_verts:
            v[2] += delta_z
        se_mesh["vertices"] = [c for v in se_verts for c in v]
        print(f"[build] repositioned secondary_entrance_mesh's length-axis by {delta_z:+.2f}ft "
              f"(stale grid-base-OBJ position -> centered on corrected anchor.z={target_z:.2f})")

    merged["_meta"] = (
        "Built via build_real_geometry.py (2026-07-08): merges SVG-derived "
        "(structural_grid_analyzer.py), layered-OBJ-derived "
        "(extract_real_geometry.extract_positions_from_layered_obj, real "
        "Rhino layer names as g groups), and grid-base-OBJ-derived "
        "(extract_real_geometry.extract_real_geometry) geometry. SVG wins "
        "site.width_ft/length_ft, column_positions, "
        "secondary_entrance_anchor.x/z; layered OBJ wins grade_y_raw, "
        "ramp_anchors, secondary_entrance_anchor's depth; grid-base OBJ "
        "wins mesh geometry only (tunnel_mesh, secondary_entrance_mesh, "
        "ramp_meshes, column_prototype_mesh, column_height_ft). See "
        "PIPELINE_STATUS_AND_NEXT_STEPS.md's 2026-07-08 entries for why."
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
