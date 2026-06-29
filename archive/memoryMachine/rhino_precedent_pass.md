# Memory Machine: Pershing Square Precedent Generator
**Context:** Master of Architecture Thesis - John C. Northrup II
**Target Environment:** VS Code + Rhino 8 (Rhino.Python 3)
**Objective:** Procedurally generate 3D spatial assets and a research deck based on "Successful Public Space" data.

---

## 1. Precedent Data & Research Synthesis
The following data was harvested by the Memory Machine's discovery engine. It maps qualitative sentiment to quantitative spatial parameters and forms the basis for both the HTML research deck and the procedural Rhino geometry.

```json
{
  "precedents": [
    {
      "id": "KINETIC_MAST",
      "site": "Schouwburgplein",
      "location": "Rotterdam, Netherlands",
      "sentiment": 0.85,
      "logic": "vertical_actuated",
      "feature": "Hydraulic lighting masts, operable by the public",
      "kit_part": "vertical_element",
      "key_qualities": ["interactivity", "night_performance", "acoustic_resonance", "thermal_radiation"]
    },
    {
      "id": "WADABLE_POOL",
      "site": "Grand Park LA",
      "location": "Downtown Los Angeles, CA",
      "sentiment": 0.92,
      "logic": "surface_membrane",
      "feature": "Shallow splash pad with bright pink rubber membrane floor",
      "kit_part": "ground_surface",
      "key_qualities": ["cooling", "social_activation", "color_identity", "barefoot_experience"]
    },
    {
      "id": "ART_WALL",
      "site": "Tanner Springs Park",
      "location": "Portland, OR",
      "sentiment": 0.78,
      "logic": "boundary_texture",
      "feature": "368 reclaimed railway tracks set vertically with fused glass inlays",
      "kit_part": "edge_element",
      "key_qualities": ["acoustic_baffle", "material_memory", "ecological_edge", "texture"]
    },
    {
      "id": "SUPERTREE",
      "site": "Gardens by the Bay",
      "location": "Singapore",
      "sentiment": 0.95,
      "logic": "infrastructure_vent",
      "feature": "Vertical garden columns 25-50m, solar canopy, rainwater collection",
      "kit_part": "vertical_element",
      "key_qualities": ["canopy_shade", "infrastructure_as_landscape", "living_surface", "scale"]
    },
    {
      "id": "GRAPHIC_PLAZA",
      "site": "Superkilen",
      "location": "Copenhagen, Denmark",
      "sentiment": 0.88,
      "logic": "ground_pattern",
      "feature": "Undulating black-and-white stripes on modeled topography",
      "kit_part": "ground_surface",
      "key_qualities": ["graphic_identity", "optical_disorientation", "topographic_modulation", "cultural_collection"]
    },
    {
      "id": "ACOUSTIC_WALL",
      "site": "Paley Park",
      "location": "New York, NY",
      "sentiment": 0.91,
      "logic": "acoustic_wall",
      "feature": "20ft full-width waterfall wall generating sustained white noise (~75dB)",
      "kit_part": "edge_element",
      "key_qualities": ["noise_masking", "thermal_cooling", "acoustic_privacy", "threshold_sequence"]
    },
    {
      "id": "DECK_PROGRAM",
      "site": "Klyde Warren Park",
      "location": "Dallas, TX",
      "sentiment": 0.87,
      "logic": "deck_program",
      "feature": "Deck park over freeway; shade trees, splash pad, food trucks, dog park",
      "kit_part": "ground_surface",
      "key_qualities": ["hot_climate_shade", "programmatic_activation", "infrastructure_concealment", "community_anchors"]
    },
    {
      "id": "INTERACTIVE_SURFACE",
      "site": "Millennium Park",
      "location": "Chicago, IL",
      "sentiment": 0.93,
      "logic": "interactive_surface",
      "feature": "Crown Fountain: twin glass towers projecting faces that jet water into shallow granite plaza",
      "kit_part": "water_element",
      "key_qualities": ["participatory_water", "shallow_cooling_pool", "event_acoustics", "reflective_ground"]
    },
    {
      "id": "FOLLY_GRID",
      "site": "Parc de la Villette",
      "location": "Paris, France",
      "sentiment": 0.86,
      "logic": "folly_grid",
      "feature": "26 red steel cube follies on 120m grid providing wayfinding and distributed program",
      "kit_part": "vertical_element",
      "key_qualities": ["distributed_program", "wayfinding", "repetition_rhythm", "covered_promenades"]
    },
    {
      "id": "LANDSCAPE_HYBRID",
      "site": "Zaryadye Park",
      "location": "Moscow, Russia",
      "sentiment": 0.89,
      "logic": "landscape_hybrid",
      "feature": "Four compressed biomes (tundra, steppe, forest, wetland) plus cantilevered floating bridge",
      "kit_part": "ground_surface",
      "key_qualities": ["biome_compression", "acoustic_zones", "topographic_variation", "cantilever_structure"]
    }
  ],
  "site_bounds": {"width": 110, "height": 150},
  "kit_of_parts": {
    "vertical_element": ["KINETIC_MAST", "SUPERTREE", "FOLLY_GRID"],
    "ground_surface":   ["WADABLE_POOL", "GRAPHIC_PLAZA", "DECK_PROGRAM", "LANDSCAPE_HYBRID"],
    "edge_element":     ["ART_WALL", "ACOUSTIC_WALL"],
    "water_element":    ["INTERACTIVE_SURFACE"]
  }
}