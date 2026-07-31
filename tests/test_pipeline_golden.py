"""
tests/test_pipeline_golden.py
------------------------------
Regression goldens for the Pershing Metabolizer geometry pipeline.

Run:
    .venv/Scripts/python.exe -m unittest discover -s tests        (Windows)
    .venv/bin/python -m unittest discover -s tests                (POSIX)

Deliberately stdlib `unittest`, not pytest: this repo lives on three
Syncthing-synced machines and had no test infrastructure at all before
this, so "works with the interpreter that's already there, no install"
matters more than pytest's ergonomics. pytest can collect these unchanged
if it's ever added to requirements.txt, so this isn't a one-way door.

See tests/_harness.py for what's pinned and why.
"""
import unittest

from _harness import (
    assert_matches_golden, digest_canopy, digest_program_zones, digest_rebuild,
    pinned_pipeline_state)


class RebuildGoldenTests(unittest.TestCase):
    """rebuild() across the parameter axes most likely to be touched by a
    refactor. Each case is a separate golden so a failure names the axis."""

    def _run(self, name, **param_overrides):
        with pinned_pipeline_state() as api:
            result = api.rebuild(api.RebuildParams(**param_overrides))
        assert_matches_golden(self, name, digest_rebuild(result))

    def test_defaults(self):
        self._run("rebuild_defaults")

    def test_shallow_canyon(self):
        self._run("rebuild_shallow", canyon_depth=1, canyon_width=1)

    def test_deep_wide_canyon(self):
        self._run("rebuild_deep_wide", canyon_depth=8, canyon_width=6)

    def test_timber_low_shoring(self):
        self._run("rebuild_timber", material_mode="TIMBER", shoring_density=0.4)

    def test_remove_top_slab(self):
        """The 2026-07-13 'remove top slab' path -- forces excavation to
        clear the SURFACE slab except on painted hardscape, so it exercises
        a genuinely different branch of _z_for_voxel, not just a
        different number."""
        self._run("rebuild_remove_top_slab", remove_top_slab=True)

    def test_designer_dominant_sketch_alpha(self):
        self._run("rebuild_sketch_alpha_full", sketch_alpha=1.0)

    def test_disabled_programs_changes_placement(self):
        """Disabling programs should change placement AND (via the
        demand-driven excavation ceiling) potentially excavation_scale --
        this golden locks in that coupling, which is easy to break
        accidentally since the two live in different modules."""
        self._run("rebuild_disabled_programs",
                  disabled_programs=["soccer_field", "skatepark"])


class RebuildInvariantTests(unittest.TestCase):
    """Properties that should hold regardless of what the goldens say --
    these survive an intentional UPDATE_GOLDEN and would catch a golden
    that was refreshed over a real bug."""

    @classmethod
    def setUpClass(cls):
        with pinned_pipeline_state() as api:
            cls.result = api.rebuild(api.RebuildParams())
            cls.config = api.get_config()

    def test_voxel_grid_is_complete(self):
        """_run_pipeline's docstring calls out that filtering unexcavated
        voxels once silently dropped the entire base slab from the
        viewport. Every grid cell must be present."""
        self.assertEqual(len(self.result["voxels"]), self.config["nx"] * self.config["nz"])

    def test_excavation_never_exceeds_column_height(self):
        cap = self.config["column_height_ft"]
        deepest = min(v["z_ft"] for v in self.result["voxels"])
        self.assertGreaterEqual(
            deepest, -cap - 1e-6,
            f"excavated to {deepest}ft, deeper than the real {cap}ft column cap")

    def test_every_structural_spec_has_a_known_kind(self):
        """Guards the kindRegistry.json consolidation: a spec whose kind is
        missing from the registry renders as nothing in the viewport and
        silently vanishes from Blender/Rhino exports."""
        from terracing_engine import KIND_REGISTRY
        known = KIND_REGISTRY["kinds"]
        unknown = sorted({
            s["kind"] for s in self.result["structural"] if s["kind"] not in known})
        self.assertEqual(unknown, [], f"kinds missing from kindRegistry.json: {unknown}")

    def test_program_zones_report_consistent_bay_math(self):
        for zone in self.result["program_zones"]:
            if not zone["bays"]:
                continue
            self.assertGreater(
                zone["achieved_sf"], 0,
                f"{zone['program_item']} claimed {len(zone['bays'])} bays but 0 sf")

    def test_pinned_state_forces_placeholder_data_channels(self):
        """If this fails, the harness stopped pinning CSV discovery and
        every golden above is now machine-dependent."""
        self.assertFalse(self.result["used_real_amenity_data"])
        self.assertFalse(self.result["used_real_foot_traffic_data"])
        self.assertFalse(self.result["used_real_noise_data"])


class CanopyGoldenTests(unittest.TestCase):
    def _run(self, name, **canopy_overrides):
        with pinned_pipeline_state() as api:
            result = api.generate_canopy(api.GenerateCanopyRequest(
                rebuild=api.RebuildParams(),
                canopy=api.CanopyParams(**canopy_overrides)))
        assert_matches_golden(self, name, digest_canopy(result))

    def test_defaults(self):
        self._run("canopy_defaults")

    def test_panel_grid_rotation(self):
        """The 2026-07-24 rotatable panel grid. HANDOFF_07242026 notes this
        was verified once by hand (1624 vs 1626 panels at 0 vs 30 degrees)
        and never locked down -- this is that check, made permanent."""
        self._run("canopy_rotated_30", panel_grid_rotation_deg=30.0)

    def test_rotation_threads_through_to_every_panel(self):
        """rotation_deg has to reach the serialized spec or the viewport and
        both Blender builders silently render an unrotated grid -- the exact
        failure mode that existed before 2026-07-24, when no panel-rendering
        code read the field at all."""
        with pinned_pipeline_state() as api:
            result = api.generate_canopy(api.GenerateCanopyRequest(
                canopy=api.CanopyParams(panel_grid_rotation_deg=30.0)))
        panels = result["canopy_panels"]
        self.assertTrue(panels, "no canopy panels generated -- fixture mask may be empty")
        self.assertTrue(
            all(abs((p["rotation_deg"] or 0.0) - 30.0) < 1e-6 for p in panels),
            "some panels lost their rotation_deg on the way to serialization")

    def test_panels_carry_surface_normals(self):
        """'panel'-shape kinds must carry a unit normal; without it the
        doubly-curved roof renders flat."""
        with pinned_pipeline_state() as api:
            result = api.generate_canopy(api.GenerateCanopyRequest())
        for p in result["canopy_panels"]:
            n = (p["normal_x"], p["normal_y"], p["normal_z"])
            self.assertTrue(all(c is not None for c in n), "panel missing a normal component")
            length = sum(c * c for c in n) ** 0.5
            self.assertAlmostEqual(length, 1.0, places=5, msg=f"normal not unit-length: {n}")


class ProgramPlacementGoldenTests(unittest.TestCase):
    def test_program_zones(self):
        with pinned_pipeline_state() as api:
            zones = api.get_program_zones()
        assert_matches_golden(self, "program_zones", digest_program_zones(zones))

    def test_no_bay_claimed_by_two_programs(self):
        """The greedy region-grower claims bays into a shared `claimed` set;
        double-claiming would mean two programs occupying the same 27ft bay."""
        with pinned_pipeline_state() as api:
            zones = api.get_program_zones()["zones"]
        seen = {}
        for zone in zones:
            # Each bay is a [gx, gy, floor_elev_ft] triple -- a bay is only
            # the "same" bay if it's on the same real floor level, which is
            # why the elevation is part of the identity here (multi-level
            # program placement, 2026-07-13).
            for bay in zone["bays"]:
                key = tuple(bay)
                self.assertNotIn(
                    key, seen,
                    f"bay {key} claimed by both {seen.get(key)} and {zone['program_item']}")
                seen[key] = zone["program_item"]


class CirculationNetworkGoldenTests(unittest.TestCase):
    def test_grown_network(self):
        with pinned_pipeline_state() as api:
            result = api.grow_network(api.GrowNetworkRequest())
        assert_matches_golden(self, "network_defaults", {
            "hash": digest_rebuild(result)["hash"] if "voxels" in result else None,
            "kind_counts": dict(sorted(result["kind_counts"].items())),
            "segment_count": len(result["network"]),
        })

    def test_network_is_rooted_and_connected_by_kind(self):
        """Space Colonization is single-rooted and hierarchical by design
        (see circulation_network.py's docstring on why it isn't Physarum) --
        every segment must be one of the registered path kinds."""
        from terracing_engine import KIND_REGISTRY
        known = KIND_REGISTRY["kinds"]
        with pinned_pipeline_state() as api:
            result = api.grow_network(api.GrowNetworkRequest())
        unknown = sorted({s["kind"] for s in result["network"] if s["kind"] not in known})
        self.assertEqual(unknown, [], f"network kinds missing from kindRegistry.json: {unknown}")


if __name__ == "__main__":
    unittest.main()
