# Metabolizer Logic — Rethink Checklist
*Created 2026-06-29*

## 1. Tunnel/Garage Alignment (OBJ)
- [ ] Re-scope alignment logic: don't align to the *entire* tunnel OBJ — that mesh is diagrammatic only.
- [ ] Logic should instead align with cutting down into the parking garage **until it meets `metroEntrance`**.
- [ ] Visual target: terracing down under the street, focused toward the metro entrance corner of the park — conical/focal pixel convergence toward that point, not a uniform tunnel-wide cut.

## 2. Amenities Deficit Logic (programming, food court, truck parking, lounging, sports)
- [ ] Decide: does deficit-driven program need to go underground, or operate as a *surface condition* (marking areas to be modified at grade)?
- [ ] Define how these amenities develop **over time** (phased growth, not static placement).
- [ ] Reference: Lina Bo Bardi, SESC Pompeia — stratified/modular program distribution as a precedent for how amenities metabolize across levels and time.

## 3. Light & Shade Logic
- [ ] Determine where shade, trees, and lightwell placement need to occur.
- [ ] Clarify how this logic is represented in the diagram (surface overlay? color-coded canopy zones? lightwell apertures?).
- [ ] Confirm it is actually using:
  - [ ] Parks & Rec data (LA Landscape Ordinance shade targets, `program_requirements.json`)
  - [ ] Surrounding building data (`building_heights.json` — solar/enclosure indices)

## Other considerations to weigh
- [ ] Phasing logic consistency: do tunnel-alignment, amenities, and light/shade all need to share the same 3-phase cumulative model already used in PershingMetabolizer_Prototype?
- [ ] Memory-volatility overlay is still a placeholder — should it inform any of the above three systems before final thesis presentation?
- [ ] Program-to-cassette assignment (which amenity goes in which puncture zone) is unresolved — tied directly to Q2 above.
- [ ] Constructability constraints (ramp slopes, egress, waterproofing) not yet considered — may constrain how literally the "terracing toward metroEntrance" can be built.
