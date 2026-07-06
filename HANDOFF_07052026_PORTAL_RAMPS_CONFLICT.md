Handoff to Gemini: Do the "4 straight portal ramps" actually exist?
=====================================================================
*2026-07-05. Claude, working via Rhino MCP against `PershingInterventionMidterm.3dm`, needs this reconciled before building anything else.*

## Context: what's been built this session (all verified against real Rhino data)

1. **Depth cap fix** (`terracing_engine.py`): general canyon excavation now correctly capped at 30ft (real column height), decoupled from the entrance's own genuine deeper depth. Verified end-to-end.
2. **Twin running-tunnel cylinders + station box** (per a "Subway Tunnel Alignment" handoff): 18'10" diameter tubes, invert at -55ft, station box 65×600×30ft tying into Subfloor 3. Built via Rhino MCP, verified by exact bounding-box math, user has since Boolean'd them into the surrounding mass.
3. **Sloped-floor helix slabs** (per a "Warping Garage Slabs" handoff): replaced the flat L1/L2/L3 plates with real geometry — 81ft-wide east and west ribbons (Hill St side and Olive St side respectively) running the *full* 602.4ft site length, sloping at ~3.01% (solved to hit the real 10ft floor-to-floor exactly, not the handoff's nominal 3.5%) through a 332.4ft middle section, flat for 135ft at each end. East ribbon slopes down heading south; west ribbon slopes down heading north. The 192ft-wide field between the two ribbons stays flat at each level's normal elevation (not addressed by that handoff). All 9 pieces verified solid/watertight.
4. Fixed a real parsing bug in `structural_grid_analyzer.py` (site-boundary extraction was reading only the first `<path>` in the `STRUC__Slabs` SVG group instead of the combined extent of all of them) — confirmed fixed, site dimensions now read correctly (354.0 × 602.2 ft vs. the real 354.14 × 602.4 ft).

## The new conflict: portal ramps

A separate, earlier handoff ("Subway Tunnel Alignment & Ramp System Modification") asked to:
> Verify there are 4 straight-cut trench ramps total flanking the site (2 on Olive, 2 on Hill) running parallel to the sidewalks... slope locked between 10% to 12% grade, cutting down from the sidewalk level (Z=-5.0) into the subterranean envelope.

Claude already found (via live Rhino MCP query) that these don't currently exist as built geometry — the `CIRC__Ramps` layer's 4 objects are the 2 circular spiral cores (2 clusters × 2 stacked levels), not straight portals. So this was flagged as new geometry to build, not an edit.

**Two problems have since come up, in order:**

1. **Spatial conflict with the ribbon helix.** The east and west ribbons (see #3 above) are 81ft wide and run the *entire* site length at the Olive edge (x: 0-81ft) and Hill edge (x: 273-354ft) — exactly where straight portal ramps "running parallel to the sidewalks" would need to sit. Building both as independently-specified, separately-positioned solids would mean they physically overlap.

2. **Real-site observation contradicts the premise.** The user visited the actual Pershing Square garage and reports: at the Hill St side spiral ramp core, at the P1 level, there's a visible incoming ramp connection — i.e., the real vehicle entrance appears to tie directly into the **spiral ramp core itself**, not into a separate straight trench ramp running alongside it.

**Question for Gemini:** given this, do the "4 straight-cut trench ramps" actually exist as a separate structure in the real 1951 garage, or was that handoff describing something that isn't real / doesn't need separate geometry? Specifically:

- Is the real vehicle entrance condition: street ramps down (short, at the curb) into the **existing spiral core** at P1 — meaning "4 straight portal ramps" should be scrapped or reinterpreted as short curb-to-core connector stubs, not full parallel ramp structures competing with the ribbon helix?
- Or do genuine separate straight entrance ramps exist *in addition to* the spiral cores, in which case: where exactly, relative to the ribbons, do they sit without overlapping? (E.g., do they only occupy the flat 135ft landing zones at the north/south ends of the ribbons, where the ribbon itself isn't sloping?)
- If real entrance ramps do exist independently, what's the real historical/as-built justification — is this documented, or another approximation like the earlier tunnel-depth number that turned out to conflate two different things?

Claude will hold off building any new portal-ramp geometry until this is resolved, to avoid building something that either duplicates the spiral core's real function or physically collides with the just-built ribbon helix.
