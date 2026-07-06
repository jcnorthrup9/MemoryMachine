# Metabolizer — Next Steps
*Created 2026-06-29, following the Metro Entrance attractor fix*

## Just completed (for reference)
- Removed an unverified coordinate flip on `METRO_ENTRANCE` — it now uses `secondary_entrance_anchor.x/z` directly, consistent with how columns and ramps already use real geometry (no flip).
- Replaced the disconnected tunnel-depth cap with a real attractor: voxel depth pulls toward `secondary_entrance_anchor.bottom_depth_ft` (63.29ft, the literal base of the Metro Entrance mesh in the OBJ), scaled by proximity.
- Diagnosed and fixed: the entrance sits ~24-84ft outside the actual site footprint (it's a street-level pavilion), so the old `TRANSIT_FALLOFF_FT=37.8` never crossed the cut threshold anywhere on site — what looked like "transit cuts" was actually the unrelated `DEFICIT_HOTSPOTS` placeholder rendering. Widened to `150` (a chosen design radius, not measured) so the attractor's pull is now real and visible — verified live (185/2680 voxels now cross threshold).

## 1. Street tunnel connection — DONE 2026-06-29
- [x] Connector volume built live from real data: x from `SITE_WIDTH_FT` (354.14) to the entrance mesh's own nearest-face vertex (scanned from `secondary_entrance_mesh.vertices`, ≈378.41), z spanning the entrance mesh's own real z-extent (≈0–54.53), y spanning the entrance's real depth range (`top_depth_ft=3.29` to `bottom_depth_ft=63.29`). Result: 24.3ft × 54.5ft × 60ft box, all dimensions traced to real_geometry.json, none pasted/guessed.
- [x] Wired as "Street Tunnel Connector" toggle, disabled+hidden outside Phase 3, shown by default once Phase 3 selected. Verified live (visible+enabled on Phase 3, hidden+disabled on Phase 1).
- [ ] STILL UNVERIFIED: which physical street this crosses — inferred as Hill St only from the entrance's east-side position, not confirmed against any surveyed plan (no street labels exist anywhere in the OBJ or SVG).
- [ ] STILL PLACEHOLDER: simple rectangular box geometry — no real street ROW width, utility clearance, or structural connection detail backs that simplification.

## 2. Audit remaining placeholders (user explicitly asked for this list, still open)
- [ ] `DEFICIT_HOTSPOTS` — fully invented coordinates/strengths at the west/Olive St edge. No real amenity-deficit dataset backs the actual (x,y) placement, only `program_requirements.json`'s category list.
- [ ] `MAX_EXCAVATION_FT = 90` — used to scale the deficit term's depth target; arbitrary, no real source.
- [ ] `SITE_ROTATION_DEG = 36` — asserted as "the true DTLA grid" in a code comment, never sourced to a survey or GIS reference.
- [ ] `BLDG_FOOTPRINT_FT = 60` — assumed shadow-caster half-width for all perimeter buildings; `building_heights.json` itself flags its building positions as "approximated from address-number ordering, not precisely geocoded."
- [ ] Parking slab footprint (`SLAB_W=328, SLAB_L=596`) — approximated from column position extents, not real slab-edge geometry from the OBJ.
- [ ] Sun condition times/weights (`SUN_CONDITIONS`) — five hand-picked solstice/flanking-time conditions with hand-assigned weights; directionally reasonable (real solar altitude/azimuth formulas) but the condition set itself is a diagrammatic sampling choice, not derived from a shading-requirement document.

## 3. Open from the original logic-rethink checklist (TODO_Metabolizer_Logic_Rethink.md), still unresolved
- [ ] Amenities-deficit logic: surface vs. underground resolution, phased growth over time, SESC Pompeia precedent not yet spatially mined.
- [ ] Program-to-cassette assignment (which deficit/amenity goes in which puncture zone).
- [ ] Memory-volatility overlay still a placeholder (0) in the scoring formula.
- [ ] Constructability pass (ramp slopes, egress, waterproofing) not yet considered — will directly constrain how literal the street-tunnel connector (item 1 above) can be.

## Side task (unrelated, still blocked)
- [ ] H: drive → Boxy (OMV server) media sync — blocked on real SMB credentials for `\\boxy`; admin/openmediavault login failed.
