// Single source of truth for the paintable design-input categories --
// extracted 2026-07-11 after PaintOverlay.jsx and ParamPanel.jsx maintained
// two independently-drifting copies of this list (the water_shade split
// would have been the second time that duplication caused friction).
// PaintOverlay.jsx uses label+color (brush swatches); ParamPanel.jsx only
// uses key+label (category-select buttons that open PaintOverlay on a
// given category) -- both read from this one array.
export const PAINT_CATEGORIES = [
  { key: 'canyon', label: 'Canyon', color: '#111111' },
  { key: 'hardscape', label: 'Hardscape', color: '#2f6fd6' },
  { key: 'water', label: 'Water', color: '#22b8c8' },
  // Tan/beige (0xBCAAA4), matches the legacy diagram tool's
  // ZONE_MATERIALS.SHADE and blender_cockpit.py's PAINT_CATEGORIES tint --
  // kept consistent across all three so "shade" reads as the same color
  // everywhere it appears.
  { key: 'shade', label: 'Shade', color: '#bcaaa4' },
  { key: 'greenscape', label: 'Greenscape', color: '#2fae4a' },
  { key: 'amenity_resting', label: 'Amenity/Resting', color: '#e08a2f' },
];
