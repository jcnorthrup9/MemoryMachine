/**
 * MEMORY MACHINE // GLOBAL CONSTANTS
 * Shared definitions for sites, layers, and coordinate systems.
 */

// ── 1. PRECEDENT SITES ──────────────────────────────────────────────────────
// Populated dynamically via /api/available-sites on boot
const SITES = {};

// ── 2. ARCHITECTURAL LAYERS ────────────────────────────────────────────────
// Colors are mapped directly to the urban_design_guidelines.md
const TARGET_LAYERS = [
  {
    id: "SOFT_01",
    label: "Softscape",
    color: "#4CAF50",
    description: "Permeable surfaces and planting."
  },
  {
    id: "HARD_01",
    label: "Hardscape",
    color: "#9E9E9E",
    description: "Civic plazas and paving."
  },
  {
    id: "PROG_01",
    label: "Active Program",
    color: "#FF9800",
    description: "Social nodes and kiosks."
  },
  {
    id: "BLUE_01",
    label: "Blue Space",
    color: "#03A9F4",
    description: "Water features and acoustic buffers."
  },
  {
    id: "CANOPY",
    label: "Floating Canopy",
    color: "#FFEB3B",
    description: "Elevated shade structures."
  }
];

// ── 3. COORDINATE MAPPING ──────────────────────────────────────────────────
// Used to translate between Rhino Meters and SVG Points
const COORDINATE_SYSTEM = {
  METERS_TO_POINTS: 1.0, 
  CENTER_X: 612, // Standard center for 1224pt width
  CENTER_Y: 396  // Standard center for 792pt height
};

// ── 4. EXPORT FOR GLOBAL ACCESS ───────────────────────────────────────────
// These are attached to window for non-module script compatibility
window.SITES = SITES;
window.TARGET_LAYERS = TARGET_LAYERS;
window.COORDINATE_SYSTEM = COORDINATE_SYSTEM;