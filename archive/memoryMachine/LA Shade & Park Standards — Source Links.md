**Tags:** #research #shade #parks-standards #pershing-metabolizer
**Purpose:** Backs the shade-coverage targets added to `data/program_requirements.json`. Originated from Gemini's research pass (pasted into chat 2026-06-28/29); links below are from an independent verification search run the same day, not from Gemini directly.

## Verified standards (independently confirmed via search)

- **City of LA Landscape Ordinance (No. 170,978)** — requires parking-lot trees sized/placed to shade ≥50% of the stall area at solar zenith on the summer solstice, after 10 years of growth.
  [City of Los Angeles Landscape Ordinance Guidelines (PDF)](https://planning.lacity.gov/odocument/3de931fb-5553-4db1-8d0b-a1b4fcfaf0d5/Landscape%20Guidelines%20%5BCity%20of%20Los%20Angeles%20Landscape%20Ordinance%20Guidelines%5D.pdf)
- **General CA municipal parking-lot ordinances** (Davis, Sacramento, and similar) — 50% of paved lot area shaded 15 years after development.
  [Evaluating Parking Lot Shading — Phytosphere Research](https://phytosphere.com/treeord/parkinglots.htm)
- **LA County Tree Planting Guide** — county-level canopy/species guidance referenced for street and park tree sizing.
  [LA County Dept. of Regional Planning — Tree Planting Guide (PDF)](https://planning.lacounty.gov/wp-content/uploads/2023/04/tree-planting_guide.pdf)
- **LA County Countywide Parks & Recreation Needs Assessment (PNA / PNA+)** — the underlying needs study this whole project's "neighborhood deficit" framing leans on.
  [LA County Park Needs Assessment (site)](https://lacountyparkneeds.org/) · [RPOSD Park Needs Assessment](https://rposd.lacounty.gov/park-needs-assessment/) · [NRPA feature: LA County's Parks Needs Assessment Plus](https://www.nrpa.org/parks-recreation-magazine/2023/march/los-angeles-countys-parks-needs-assessment-plus/)
- **NRPA Park Metrics / Agency Performance Review** — national benchmarking (10 acres parkland per 1,000 residents; 6.25–10.5 acres developed open space per 1,000 minimum).
  [NRPA Park Metrics](https://www.nrpa.org/publications-research/ParkMetrics/) · [2026 NRPA Agency Performance Review](https://www.nrpa.org/APR/) · [Agency Performance Review (PDF)](https://www.nrpa.org/siteassets/nrpa-agency-performance-review.pdf)

## Pedestrian thermal-comfort research (academic, for the "why shade matters" framing)

- [Pedestrian-Oriented Microclimate Optimization for Urban Plazas (Buildings, 2026)](https://doi.org/10.3390/buildings16101874) — plaza-wide UTCI up to ~46°C in unshaded hot-climate plazas under summer extremes; no fully comfortable zones without shade.
- [Thermal Exposure Risk: Supply/Demand Disparity Between Urban Shade and Pedestrian Flows (Land, 2026)](https://doi.org/10.3390/land15040548) — mobile-signaling-data study of shade supply vs. actual pedestrian demand.
- [Analytical evaluation of thermal comfort using pedestrian shade-space distribution (ScienceDirect)](https://www.sciencedirect.com/science/article/abs/pii/S2212095523002596) — quantifies PET (perceived temperature) dropping ~0.018°C per 1% increase in shade coverage along a route.

## Claims from Gemini's research pass that could NOT be independently confirmed

These were in Gemini's findings and used qualitatively, but a follow-up search did not turn up a citable primary source — treat as plausible-but-unverified, not load-bearing for the thesis citation list:
- "Dog parks require 100% shade coverage within 10 years" — no ordinance located naming this figure specifically for dog parks (parking-lot ordinances use 50%/10–15yr; nothing found at 100% for any use class).
- "San Diego requires 50% shade over play equipment" — San Diego's Consultant's Guide to Park Design and the relevant municipal code chapters were located, but neither explicitly states this figure in the search results.
- Qualitative critique of Pershing Square / Grand Park as comparatively shade-poor/shade-rich — this is a design observation, not a cited standard; keep it framed as project analysis, not as a sourced fact.

## How this maps to `data/program_requirements.json`

`shade_target_pct` and `shade_basis` fields were added per program category using the **City of LA 50%/10yr parking-lot standard** as the only fully-verifiable cross-applicable number (extended by analogy to other paved/active-use program types), with the dog-park and play-equipment figures flagged as unverified rather than silently asserted as code-backed.
