// Shared raster-preview helper (2026-07-23) -- extracted from PaintOverlay.jsx
// so both its "Diagram" tab and Recent2DGenerationsPanel.jsx can draw a
// BakeGrids-shaped response (hardscape/water/trees/greenscape/amenity_resting
// boolean grids) as a colored-cell canvas without duplicating the function.
import { PAINT_CATEGORIES as CATEGORIES } from './paintCategories.js';

export const PREVIEW_CELL_PX = 6;

export function drawDiagramPreview(canvas, grids) {
  if (!canvas || !grids) return;
  const nx = grids.hardscape.length;
  const nz = grids.hardscape[0].length;
  canvas.width = nx * PREVIEW_CELL_PX;
  canvas.height = nz * PREVIEW_CELL_PX;
  const ctx = canvas.getContext('2d');
  ctx.fillStyle = '#000000';
  ctx.fillRect(0, 0, canvas.width, canvas.height);
  // Same category order as PaintOverlay's own sketch-canvas composite() --
  // later entries draw on top, matching how overlapping painted strokes
  // already resolve there.
  for (const cat of CATEGORIES) {
    if (cat.key === 'canyon' || cat.key === 'canopy') continue; // continuous weights, not boolean regions -- no fill color to preview here
    const grid = grids[cat.key];
    if (!grid) continue;
    ctx.fillStyle = cat.color;
    for (let gx = 0; gx < nx; gx++) {
      for (let gy = 0; gy < nz; gy++) {
        if (!grid[gx][gy]) continue;
        // row 0 at top = ymax (5th St), matching vector_export.py's
        // STREET_LABELS convention and ingest_legacy_diagram.py's own
        // render_debug_preview.
        const py = nz - 1 - gy;
        ctx.fillRect(gx * PREVIEW_CELL_PX, py * PREVIEW_CELL_PX, PREVIEW_CELL_PX, PREVIEW_CELL_PX);
      }
    }
  }
}
