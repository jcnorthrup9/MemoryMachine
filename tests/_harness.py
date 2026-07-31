"""
tests/_harness.py
------------------
Shared machinery for the golden-file regression tests.

WHY GOLDEN FILES AND NOT ASSERTIONS ON VALUES: the pipeline
(TerracingEngine -> StructuralFramingEngine -> TypologyAssetEngine ->
program_placement -> CanopyEngine) is deterministic numeric math with JSON
in and JSON out, but there is no independent oracle for "is a 4278-element
structural spec list correct?" -- correctness here has always been
established by looking at the viewport. What these tests CAN do is prove a
refactor changed nothing: capture a digest of today's output, and fail loudly
if tomorrow's differs. That's the gap they fill -- not "is it right", but
"did it move".

TWO THINGS MAKE A NAIVE TEST NON-REPRODUCIBLE, AND BOTH ARE PINNED HERE:

1. **Live paint state.** logic/pershing_api.py bootstraps SKETCH_WEIGHTS /
   HARDSCAPE_MASK / WATER_MASK / ... as module globals read from
   outputs/cockpit/web_paint_state.json at import time (see that file's own
   bootstrap block and its "single-session state, same pattern as the
   Blender cockpit" docstring). That file changes every time anyone paints
   and bakes, so a test that used it would fail for reasons that have
   nothing to do with code. pinned_pipeline_state() swaps in a synthetic,
   formula-generated paint state for the duration of a test and restores the
   real one afterward.

2. **Real-data CSV presence.** AMENITY_CSV_PATH / FOOT_TRAFFIC_CSV_PATH /
   NOISE_CSV_PATH are resolved at import time from whatever CSVs happen to
   sit in data/*_survey/. Whether a channel is on changes the output, so
   the pinning context forces all three OFF -- every golden below therefore
   exercises TerracingEngine's own DEFAULT_*_HOTSPOTS placeholders, which
   are checked-in constants and identical on every machine. Tests that
   specifically want a real-data channel should pass its hotspots
   explicitly rather than relying on ambient CSV discovery.

The synthetic paint state is GENERATED, not stored as a fixture file: a
40x67 grid x 8 masks would be a ~2MB JSON committed to a repo that already
has a size problem, and a formula is both smaller and easier to reason
about than an opaque blob.
"""
import contextlib
import hashlib
import json
import math
import os
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

GOLDEN_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "golden")

# Set UPDATE_GOLDEN=1 to rewrite goldens instead of asserting against them.
# Intended for a deliberate, reviewed behavior change -- the diff on the
# golden file is then the record of what moved, which is the whole point.
UPDATE_GOLDEN = os.environ.get("UPDATE_GOLDEN") == "1"

# Rounded before hashing so the goldens survive last-bit float differences
# across machines/numpy builds. 6dp is far finer than any dimension this
# pipeline cares about (feet, at 9ft voxel resolution) while still catching
# any real change in the math.
FLOAT_PRECISION = 6


def _synthetic_masks(nx, nz):
    """Deterministic stand-in for a designer's painted state.

    Chosen so every mask is non-empty and non-uniform (an all-zero paint
    state would leave most of the pipeline's mask-driven branches untested)
    and so the regions overlap only partially (overlap semantics are real
    behavior here -- see HANDOFF_07052026_ZONE_OVERLAP_SEMANTICS.md). The
    exact shapes carry no design meaning; they're an arbitrary but fixed
    input, which is all a regression golden needs.
    """
    canyon, hardscape, water, trees = [], [], [], []
    greenscape, amenity_resting, deck, canopy = [], [], [], []
    for gx in range(nx):
        fx = gx / max(1, nx - 1)
        c_col, h_col, w_col, t_col = [], [], [], []
        g_col, a_col, d_col, k_col = [], [], [], []
        for gy in range(nz):
            fy = gy / max(1, nz - 1)
            # Smooth radial falloff from a point left-of-center -- gives the
            # canyon a real gradient rather than a binary blob, so the
            # depth-stepping and relaxation passes both have something to do.
            r = math.hypot(fx - 0.35, fy - 0.5)
            c_col.append(round(max(0.0, 1.0 - r * 2.2), 4))
            h_col.append(0.30 < fx < 0.55 and 0.15 < fy < 0.45)
            w_col.append(fx > 0.72 and 0.55 < fy < 0.75)
            t_col.append((gx + gy) % 11 == 0 and fx > 0.20)
            g_col.append(fx < 0.28 and fy > 0.30)
            a_col.append(0.58 < fx < 0.70 and 0.20 < fy < 0.80)
            d_col.append(fx > 0.80 and fy < 0.25)
            k_col.append(round(1.0 if (0.25 < fx < 0.75 and 0.30 < fy < 0.70) else 0.0, 4))
        canyon.append(c_col)
        hardscape.append(h_col)
        water.append(w_col)
        trees.append(t_col)
        greenscape.append(g_col)
        amenity_resting.append(a_col)
        deck.append(d_col)
        canopy.append(k_col)
    return {
        "canyon": canyon, "hardscape": hardscape, "water": water, "trees": trees,
        "greenscape": greenscape, "amenity_resting": amenity_resting,
        "deck": deck, "canopy": canopy,
    }


# Module-global names on logic.pershing_api that pinned_pipeline_state()
# saves/overwrites/restores. Kept as an explicit list (rather than inferred)
# so that if pershing_api grows another global mask, the mismatch surfaces
# here as a KeyError in a test rather than as a silently un-pinned input
# that makes goldens drift with live state again.
_PINNED_MASK_ATTRS = {
    "SKETCH_WEIGHTS": "canyon",
    "HARDSCAPE_MASK": "hardscape",
    "WATER_MASK": "water",
    "TREE_MASK": "trees",
    "GREENSCAPE_MASK": "greenscape",
    "AMENITY_RESTING_MASK": "amenity_resting",
    "DECK_MASK": "deck",
    "CANOPY_MASK": "canopy",
}

_PINNED_OTHER_ATTRS = {
    # Forced off -- see this module's docstring, point 2.
    "AMENITY_CSV_PATH": None,
    "FOOT_TRAFFIC_CSV_PATH": None,
    "NOISE_CSV_PATH": None,
    # 2026-07-16 program-placement correlation logic. Deliberately NOT empty:
    # an empty dict is the honest real-world default (attractors are baked
    # from explicit user clicks), but _attractor_proximity_bays() early-returns
    # all-zeros for empty `points`, so leaving it empty left that whole
    # correlation path unexercised. With the points below, moving them
    # measurably changes both the rebuild digest and program placement
    # (verified by mutation).
    #
    # Note for anyone mutation-testing this: ATTRACTOR_INFLUENCE_RADIUS_FT is
    # captured as _attractor_proximity_bays()'s default argument at import
    # time (logic/pershing_api.py:713), so reassigning the module global at
    # runtime does NOT change behavior -- mutate the points, not the radius.
    #
    # Fixed synthetic points in site feet ("y_ft" is the plan z-axis, per
    # _attractor_proximity_bays()'s own docstring), one per category, spread
    # across quadrants so the falloff discriminates between bays.
    "ATTRACTOR_POINTS": {
        "major_attractor": [{"x_ft": 120.0, "y_ft": 180.0}],
        "minor_attractor": [{"x_ft": 300.0, "y_ft": 430.0}],
        "amphitheatre": [{"x_ft": 210.0, "y_ft": 300.0}],
    },
    "PATH_HINT_POINTS": [],
}


@contextlib.contextmanager
def pinned_pipeline_state():
    """Swap logic.pershing_api's live module globals for deterministic ones.

    Restores the originals on exit, including on exception -- these globals
    are the running app's real state when the test suite is run in the same
    interpreter as anything else, so leaking a synthetic mask out of a test
    would be a genuine side effect, not just untidy.
    """
    from logic import pershing_api

    masks = _synthetic_masks(pershing_api.NX, pershing_api.NZ)
    saved = {}
    try:
        for attr, mask_key in _PINNED_MASK_ATTRS.items():
            saved[attr] = getattr(pershing_api, attr)
            setattr(pershing_api, attr, masks[mask_key])
        for attr, value in _PINNED_OTHER_ATTRS.items():
            saved[attr] = getattr(pershing_api, attr)
            setattr(pershing_api, attr, value)
        yield pershing_api
    finally:
        for attr, value in saved.items():
            setattr(pershing_api, attr, value)


def _canonical(obj):
    """Recursively round floats so the digest is stable across machines."""
    if isinstance(obj, float):
        # normalize -0.0 to 0.0; they hash differently but mean the same thing
        r = round(obj, FLOAT_PRECISION)
        return 0.0 if r == 0 else r
    if isinstance(obj, dict):
        return {k: _canonical(v) for k, v in sorted(obj.items())}
    if isinstance(obj, (list, tuple)):
        return [_canonical(v) for v in obj]
    return obj


def payload_hash(payload):
    blob = json.dumps(_canonical(payload), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode()).hexdigest()[:16]


def _kind_histogram(specs):
    """Counts by "kind". Keys are coerced to str because Voxel.typology is
    None for any voxel the TypologyAssetEngine didn't classify, and a dict
    mixing None with str keys can't be sorted."""
    counts = {}
    for s in specs:
        key = s.get("kind")
        key = "<none>" if key is None else str(key)
        counts[key] = counts.get(key, 0) + 1
    return dict(sorted(counts.items()))


def digest_rebuild(result):
    """Small, human-readable summary of a rebuild() payload, plus a hash of
    the whole thing.

    The summary exists so a failing diff is *readable* ("program_boxes went
    105 -> 98") instead of just "hash changed"; the hash exists so a change
    the summary doesn't happen to cover still fails. Full payloads are
    deliberately not stored -- rebuild() returns ~4300 structural specs and
    2680 voxels, which is megabytes per golden in a repo that already has a
    size problem.
    """
    voxels = result["voxels"]
    excavated = [v for v in voxels if v.get("z_ft", 0) < 0]
    return {
        "hash": payload_hash(result),
        "counts": {
            "voxels": len(voxels),
            "voxels_excavated": len(excavated),
            "structural": len(result["structural"]),
            "program_boxes": len(result["program_boxes"]),
            "program_zones": len(result["program_zones"]),
            "real_columns": len(result["real_columns"]),
            "real_slabs": len(result["real_slabs"]),
            "spatial_summary": len(result["spatial_summary"]),
        },
        "kind_counts": dict(sorted(result["kind_counts"].items())),
        "structural_kinds": _kind_histogram(result["structural"]),
        "scalars": _canonical({
            "max_canyon_depth_ft": result["max_canyon_depth_ft"],
            "excavation_scale": result["excavation_scale"],
            "slab_harvest_tons": result["slab_harvest_tons"],
            "voxel_ft": result["voxel_ft"],
            "used_real_amenity_data": result["used_real_amenity_data"],
            "used_real_foot_traffic_data": result["used_real_foot_traffic_data"],
            "used_real_noise_data": result["used_real_noise_data"],
        }),
        "depth_ft": _canonical({
            "min": min((v["z_ft"] for v in voxels), default=0.0),
            "max": max((v["z_ft"] for v in voxels), default=0.0),
            "mean": (sum(v["z_ft"] for v in voxels) / len(voxels)) if voxels else 0.0,
        }),
        "typologies": _kind_histogram([{"kind": v.get("typology")} for v in voxels]),
    }


def digest_canopy(result):
    panels = result.get("canopy_panels", [])
    columns = result.get("canopy_columns", [])
    return {
        "hash": payload_hash(result),
        "counts": {"panels": len(panels), "columns": len(columns)},
        "column_kinds": _kind_histogram(columns),
        "panel_z_ft": _canonical({
            "min": min((p["z_top_ft"] for p in panels), default=0.0),
            "max": max((p["z_top_ft"] for p in panels), default=0.0),
            "mean": (sum(p["z_top_ft"] for p in panels) / len(panels)) if panels else 0.0,
        }),
        "rotation_deg_distinct": sorted({round(p.get("rotation_deg") or 0.0, 3) for p in panels}),
    }


def digest_program_zones(result):
    zones = result["zones"] if isinstance(result, dict) else result
    return {
        "hash": payload_hash(zones),
        "zone_count": len(zones),
        "placed_count": sum(1 for z in zones if z["bays"]),
        "bays_per_program": {z["program_item"]: len(z["bays"]) for z in sorted(
            zones, key=lambda z: z["program_item"])},
    }


def assert_matches_golden(test_case, name, digest):
    """Compare `digest` against tests/golden/<name>.json, or write it if
    UPDATE_GOLDEN=1 / the golden doesn't exist yet."""
    path = os.path.join(GOLDEN_DIR, f"{name}.json")
    if UPDATE_GOLDEN or not os.path.exists(path):
        os.makedirs(GOLDEN_DIR, exist_ok=True)
        with open(path, "w") as f:
            json.dump(digest, f, indent=2, sort_keys=True)
            f.write("\n")
        if not UPDATE_GOLDEN:
            print(f"[golden] created {os.path.relpath(path, BASE_DIR)} (first run)")
        return

    with open(path) as f:
        expected = json.load(f)

    # Compare the readable summary first so an unexpected change reports as
    # a specific field diff, and only fall through to the opaque whole-payload
    # hash if every summarized field already matched.
    for key in sorted(set(expected) | set(digest)):
        if key == "hash":
            continue
        test_case.assertEqual(
            expected.get(key), digest.get(key),
            f"golden '{name}' field '{key}' changed.\n"
            f"If this change is intentional, re-run with UPDATE_GOLDEN=1 and "
            f"commit the golden diff as the record of what moved.")
    test_case.assertEqual(
        expected.get("hash"), digest.get("hash"),
        f"golden '{name}': summarized fields all match but the full-payload "
        f"hash changed -- something moved in a field the summary doesn't "
        f"cover (a coordinate, a rotation, a per-spec attribute).\n"
        f"If intentional, re-run with UPDATE_GOLDEN=1.")
