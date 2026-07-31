// Single source of truth for the paintable design-input categories --
// extracted 2026-07-11 after PaintOverlay.jsx and ParamPanel.jsx maintained
// two independently-drifting copies of this list (the water_shade split
// would have been the second time that duplication caused friction).
// PaintOverlay.jsx uses label+color (brush swatches); ParamPanel.jsx only
// uses key+label (category-select buttons that open PaintOverlay on a
// given category) -- both read from this one array.
export const PAINT_CATEGORIES = [
  { key: 'canyon', label: 'Canyon', color: '#111111' },
  // Gray (0x9E9E9E), reconciled 2026-07-14 to match the diagram tool's
  // (diagram_tool/, forked from the old Digital Palimpsest app)
  // _getLayerColor() hardscape color exactly -- was previously blue
  // (#2f6fd6), a completely different color for the same category name
  // between the two authoring tools. The diagram tool's colors were
  // decided as canonical, so this one moved to match it, not the reverse.
  { key: 'hardscape', label: 'Hardscape', color: '#9e9e9e' },
  { key: 'water', label: 'Water', color: '#22b8c8' },
  // Tan/beige (0xBCAAA4), matches the legacy diagram tool's
  // ZONE_MATERIALS.SHADE and blender_cockpit.py's PAINT_CATEGORIES tint --
  // kept consistent across all three so "trees" reads as the same color
  // everywhere it appears. Renamed from "shade" 2026-07-16 -- this
  // category always meant "place trees here" (see terracing_engine.py's
  // TypologyAssetEngine.tree_specs()), the name just didn't say so before.
  { key: 'trees', label: 'Trees', color: '#bcaaa4' },
  { key: 'greenscape', label: 'Greenscape', color: '#2fae4a' },
  { key: 'amenity_resting', label: 'Amenity/Resting', color: '#e08a2f' },
  // 2026-07-13 "remove top slab" excavation/hardscape decouple -- a
  // DEDICATED "keep this as an access deck" signal, separate from
  // hardscape (which stays purely a program-scoring/normal-dig-veto
  // paint). See terracing_engine.py's TerracingEngine.deck_regions.
  { key: 'deck', label: 'Deck (Keep on Top-Slab Removal)', color: '#9c27b0' },
  // 2026-07-13 Canopy Engine: a continuous weight brush (like canyon, NOT a
  // boolean zone mask) -- painted alpha scales how much the canopy height-
  // field deviates from its flat base height at that cell. See
  // PaintOverlay.jsx's handleBake() and logic/canopy_engine.py.
  { key: 'canopy', label: 'Canopy Weight', color: '#4dd0e1' },
];
