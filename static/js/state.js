/**
 * MEMORY MACHINE // APPLICATION STATE
 * Centralized store for the layer stack, SVG cache, and transformation data.
 */

// ── PATH GEOMETRY HELPERS ────────────────────────────────────────────────────

/**
 * Extracts an ordered [x0,y0, x1,y1, ...] vertex array from a single SVG element.
 * Returns a Float32Array, or null if the element contributes no area.
 */
function _extractVertices(el) {
  const tag = el.tagName.toLowerCase();

  if (tag === 'rect') {
    const x = parseFloat(el.getAttribute('x') || 0);
    const y = parseFloat(el.getAttribute('y') || 0);
    const w = parseFloat(el.getAttribute('width') || 0);
    const h = parseFloat(el.getAttribute('height') || 0);
    if (w === 0 || h === 0) return null;
    return new Float32Array([x, y, x+w, y, x+w, y+h, x, y+h]);
  }

  if (tag === 'circle') {
    const cx = parseFloat(el.getAttribute('cx') || 0);
    const cy = parseFloat(el.getAttribute('cy') || 0);
    const r  = parseFloat(el.getAttribute('r')  || 0);
    if (r === 0) return null;
    // 16-point polygon approximation — accurate to <0.2% for Shoelace
    const pts = [];
    for (let i = 0; i < 16; i++) {
      const a = (i / 16) * Math.PI * 2;
      pts.push(cx + Math.cos(a) * r, cy + Math.sin(a) * r);
    }
    return new Float32Array(pts);
  }

  if (tag === 'line') return null; // lines have no area

  // path / polyline / polygon
  let d = el.getAttribute('d') || el.getAttribute('points') || '';
  if (!d) return null;

  // Strip SVG arc parameters (rx ry x-rot large-arc sweep) to avoid treating
  // arc radii as coordinate pairs
  d = d.replace(/[Aa]\s*[-+]?[\d.]+\s*[,\s]+[-+]?[\d.]+\s*[,\s]+[-+]?[\d.]+\s*[,\s]+[01]\s*[,\s]+[01]\s*[,\s]*/g, '');

  const nums = [];
  // Optimization: use matchAll for faster parsing and less index management
  const matches = d.matchAll(/(-?\d+\.?\d*(?:e[-+]?\d+)?)/gi);
  for (const m of matches) {
    const v = parseFloat(m[0]);
    if (!isNaN(v)) nums.push(v);
  }

  if (nums.length < 4) return null;

  // Ensure even count — drop trailing orphan
  const len = nums.length % 2 === 0 ? nums.length : nums.length - 1;
  return new Float32Array(nums.slice(0, len));
}

/**
 * True if this element is actually filled (fill != none/absent/empty) --
 * same semantic ingest_diagram_svg.py's _has_real_fill() already enforces
 * server-side. Required, not optional: a stroke-only shape (e.g. one of
 * PEDESTRIAN_PATH's 583 dash segments in the real site SVG, or any of
 * PARKING/STREET's pure linework) has no real area, but _extractVertices()
 * above happily returns a vertex loop for anything with >=3 points
 * regardless of fill -- getProgramStats() would then force-close and fill
 * it on the stats canvas, counting decorative dash-marks as solid
 * Hardscape area. This is also why the HUD previously didn't match what's
 * visually drawn: engine2D.js's context-group rendering forces fill:none
 * on every locked base layer (STREET/PARKING/PEDESTRIAN_PATH/etc. always
 * render as thin outlines only), but getProgramStats() had no equivalent
 * check and was filling their real underlying geometry regardless.
 */
function _hasRealFill(el) {
  let fill = el.getAttribute('fill') || '';
  const style = el.getAttribute('style') || '';
  const m = /fill\s*:\s*([^;]+)/.exec(style);
  if (m) fill = m[1].trim();
  return fill !== '' && fill !== 'none';
}

// ── OCCLUSION-CORRECT STATS RASTERIZATION ──────────────────────────────────
// 2026-07-12: replaces the old Shoelace-area-summed-per-category approach,
// which had no z-order occlusion -- an overlapping SHADE canopy over a
// GREEN lawn contributed full area to BOTH categories, so totals could
// exceed 100%. Fix stays synchronous (no Blob/Image/onload round-trip --
// vertex data is already in memory from _getLayerGeometry's cache) and
// avoids engine2D.js's 0.3 fill-opacity display colors (which would blend
// on overlap, defeating simple color-bucket classification) by rasterizing
// onto a small, invisible, stats-only canvas with fully OPAQUE per-category
// colors instead. Later-drawn (topmost) items overwrite earlier ones at the
// pixel level -- that IS topmost-wins occlusion, for free, via the canvas's
// own compositing, no hand-written polygon clipper needed.
const STATS_CANVAS_W = 300;
const STATS_CANVAS_H = 200;

// Must match TARGET_LAYERS' colors in constants.js (SHADE maps to the
// "Floating Canopy" / CANOPY entry).
const _STATS_CATEGORY_COLORS = {
  SOFT:  [76, 175, 80],    // #4CAF50
  SHADE: [255, 235, 59],   // #FFEB3B
  HARD:  [158, 158, 158],  // #9E9E9E
  PROG:  [255, 152, 0],    // #FF9800
  BLUE:  [3, 169, 244],    // #03A9F4
};

// Sentinel fill for the real (possibly rotated) BOUNDARY polygon, painted
// onto the stats canvas BEFORE any category -- see getProgramStats()'s
// totalPixels comment for why this exists: a rotated boundary's own
// axis-aligned bbox (Pershing Square's real boundary measures ~48% of its
// own bbox area) is NOT the same shape as the site, so dividing by the
// full canvas area silently deflates every percentage by ~2x. Distinct
// from every _STATS_CATEGORY_COLORS value so it can't be miscounted as a
// real category.
const _SITE_MASK_COLOR = [1, 1, 1];

// ── STATE OBJECT ─────────────────────────────────────────────────────────────

const MemoryState = {
  // ── 1. THE LAYER STACK ───────────────────────────────────────────────────
  stack: [],

  // ── 2. SELECTION & EDITING ───────────────────────────────────────────────
  editingId: null,

  // ── 3. DATA CACHE ────────────────────────────────────────────────────────
  svgCache: {
    'PershingSquare':   null,
    'ParcdelaVillette': null,
    'ZaryadyePark':     null,
    'Schouwburgplein':  null
  },

  /**
   * Geometry cache: Map<"site::layerId", {polys: Float32Array[], precBBox: obj}>
   * Populated lazily on first getProgramStats() call for each combination.
   * Avoids re-parsing SVG text and running regex on every HUD update.
   */
  pathCache: new Map(),

  // ── 4. APP MODE ──────────────────────────────────────────────────────────
  dreamMode: false,

  // ── 5. AI GENERATION DATA ───────────────────────────────────────────────
  lastGeneration: { narrative: "", geometries: [], diagram: "" },

  // ── 5.5 BASE CONTEXT ─────────────────────────────────────────────────────
  baseCleared: false,

  // ── 5.6 SITE GRID (spatial organizer overlay) ────────────────────────────
  // Deliberately separate from `stack` -- a visual/organizing aid, not a
  // paintable layer. Must stay untouched by getProgramStats()'s pixel tally.
  // null when hidden; set to the /api/site-grid response's `grid` object
  // (see logic/site_grid.py) when the grid toggle is on.
  siteGrid: null,

  // ── 6. STATE HELPERS ─────────────────────────────────────────────────────

  /**
   * Returns cached parsed geometry for a site+layer combination.
   * On miss: parses the SVG once and stores results in pathCache.
   */
  _getLayerGeometry(siteId, layerId) {
    const key = `${siteId}::${layerId}`;
    if (this.pathCache.has(key)) return this.pathCache.get(key);

    const svgText = this.svgCache[siteId];
    if (!svgText || !window.Engine2D) return null;

    const el      = window.Engine2D.parseSVG(svgText);
    const precBBox = window.Engine2D.getBoundaryBBox(el);
    const layerG  = el.querySelector(`g[id*="${layerId}"]`) ||
                    el.querySelector(`g[id="${layerId}"]`);
    if (!layerG) {
      this.pathCache.set(key, null);
      return null;
    }

    const polys = [];
    layerG.querySelectorAll('path, polyline, polygon, rect, circle, line')
          .forEach(p => {
            if (!_hasRealFill(p)) return; // stroke-only linework contributes no area
            const verts = _extractVertices(p);
            if (verts) polys.push(verts);
          });

    const result = { polys, precBBox };
    this.pathCache.set(key, result);
    return result;
  },

  /**
   * Calculates the programmatic mix of the current stack by rasterizing
   * every layer's real, per-vertex-transformed polygons (not just their
   * AABB) onto a small offscreen canvas in stack (z-)order, using fully
   * opaque per-category colors, then tallying pixels once. See the
   * STATS_CANVAS_W/_STATS_CATEGORY_COLORS block above for why this
   * replaced the old per-category-summed-Shoelace-area approach: that
   * approach had no occlusion, so overlapping layers double-counted area
   * and totals could exceed 100%. Percentages here can never exceed 100%
   * by construction -- each pixel belongs to at most one category.
   */
  getProgramStats() {
    if (this.stack.length === 0 || !window.Engine2D) return { SOFT: 0, SHADE: 0, HARD: 0, PROG: 0, BLUE: 0 };

    const baseSVG = this.svgCache['PershingSquare'];
    if (!baseSVG) return { SOFT: 0, SHADE: 0, HARD: 0, PROG: 0, BLUE: 0 };

    const baseEl   = window.Engine2D.parseSVG(baseSVG);
    const baseBBox = window.Engine2D.getBoundaryBBox(baseEl);
    if (baseBBox.w === 0 || baseBBox.h === 0) return { SOFT: 0, SHADE: 0, HARD: 0, PROG: 0, BLUE: 0 };

    const cx = baseBBox.x + baseBBox.w / 2;
    const cy = baseBBox.y + baseBBox.h / 2;

    const canvas = document.createElement('canvas');
    canvas.width = STATS_CANVAS_W;
    canvas.height = STATS_CANVAS_H;
    const ctx = canvas.getContext('2d', { willReadFrequently: true });
    // World (site-boundary) space -> canvas pixel space, 1:1 over the full
    // canvas -- anything drawn outside baseBBox lands outside [0,W]x[0,H],
    // which <canvas> clips natively, so no separate AABB-overlap-ratio clip
    // is needed for THAT. But baseBBox is the boundary's axis-aligned bbox,
    // not the boundary's own (possibly rotated) shape -- Pershing Square's
    // real boundary polygon measures only ~48% of its own bbox area, so
    // totalPixels must come from the boundary MASK painted below, not
    // STATS_CANVAS_W*STATS_CANVAS_H, or every percentage silently deflates
    // by ~2x from counting bbox corners that are never part of the site.
    const px = (wx) => ((wx - baseBBox.x) / baseBBox.w) * STATS_CANVAS_W;
    const py = (wy) => ((wy - baseBBox.y) / baseBBox.h) * STATS_CANVAS_H;

    // Paint the real BOUNDARY polygon first, as a sentinel mask -- same
    // point-extraction convention as engine2D.js's buildBoundaryClipPath()
    // (concatenate every number from every <path> under the BOUNDARY group,
    // in document order; Rhino/CAD exports emit boundary segments in
    // perimeter order, so this traces a valid closed loop without needing
    // per-segment endpoint matching).
    const boundaryG = baseEl.querySelector('g[id*="BOUNDARY"]') || baseEl.querySelector('g[id="BOUNDARY"]');
    if (boundaryG) {
      const bPts = [];
      boundaryG.querySelectorAll('path').forEach(p => {
        const d = p.getAttribute('d') || '';
        const matches = d.matchAll(/(-?\d+\.?\d*(?:e[-+]?\d+)?)/gi);
        for (const m of matches) bPts.push(parseFloat(m[0]));
      });
      if (bPts.length >= 6) {
        const [sr, sg, sb] = _SITE_MASK_COLOR;
        ctx.fillStyle = `rgb(${sr},${sg},${sb})`;
        ctx.beginPath();
        for (let i = 0; i < bPts.length - 1; i += 2) {
          const x = px(bPts[i]), y = py(bPts[i + 1]);
          if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
        }
        ctx.closePath();
        ctx.fill();
      }
    }

    // Stack order = z-order (later index drawn later = topmost), same
    // convention as engine2D.js's own forEach+appendChild rendering.
    this.stack.forEach(item => {
      if (item.visible === false) return;

      const lId = item.layerId || '';

      // Zone classification — PEDESTRIAN_PATH counts as HARD
      let type = 'HARD';
      if (lId.includes('SHADE'))                                     type = 'SHADE';
      else if (lId.includes('GREEN'))                                type = 'SOFT';
      else if (lId.includes('WATER'))                                type = 'BLUE';
      else if (lId.includes('ATTRACTOR') || lId.includes('UNIQUE')) type = 'PROG';

      const geom = this._getLayerGeometry(item.site, item.layerId);
      if (!geom || geom.polys.length === 0) return;

      const { polys, precBBox } = geom;
      const fitScale   = Math.min(baseBBox.w / (precBBox.w || 1), baseBBox.h / (precBBox.h || 1));
      const finalScale = fitScale * (item.transform.scale || 1.0);
      const pcx = precBBox.x + precBBox.w / 2;
      const pcy = precBBox.y + precBBox.h / 2;
      // Same translate(-pivot) -> rotate -> scale -> translate(final) point
      // transform as engine2D.js's own SVG `transform` attribute
      // (`translate(cx+tx,cy+ty) scale(s) rotate(r) translate(-pcx,-pcy)`,
      // read right-to-left) -- applied per VERTEX here, not just to the
      // polygon's bbox corners like the old AABB-based clip did, which is
      // what makes real per-pixel occlusion possible.
      const rot = ((item.transform.rot || 0) * Math.PI) / 180;
      const cosR = Math.cos(rot), sinR = Math.sin(rot);
      const [r, g, b] = _STATS_CATEGORY_COLORS[type];
      ctx.fillStyle = `rgb(${r},${g},${b})`;

      polys.forEach(verts => {
        if (verts.length < 6) return; // need >= 3 points to fill anything
        ctx.beginPath();
        for (let i = 0; i < verts.length; i += 2) {
          const dx = verts[i]     - pcx;
          const dy = verts[i + 1] - pcy;
          const rx = dx * cosR - dy * sinR;
          const ry = dx * sinR + dy * cosR;
          const wx = cx + item.transform.x + rx * finalScale;
          const wy = cy + item.transform.y + ry * finalScale;
          const x = px(wx), y = py(wy);
          if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
        }
        ctx.closePath();
        ctx.fill();
      });
    });

    const { data } = ctx.getImageData(0, 0, STATS_CANVAS_W, STATS_CANVAS_H);
    const pixelCounts = { SOFT: 0, SHADE: 0, HARD: 0, PROG: 0, BLUE: 0 };
    // Every painted pixel (site mask OR any category drawn over it) counts
    // toward the real site area -- this is the boundary's TRUE pixel count,
    // not STATS_CANVAS_W*STATS_CANVAS_H (which includes the bbox corners
    // outside a rotated boundary; see the mask-painting comment above).
    let siteMaskPixels = 0;
    for (let i = 0; i < data.length; i += 4) {
      if (data[i + 3] === 0) continue; // untouched pixel -- outside the site entirely
      siteMaskPixels++;
      for (const type in _STATS_CATEGORY_COLORS) {
        const [cr, cg, cb] = _STATS_CATEGORY_COLORS[type];
        if (data[i] === cr && data[i + 1] === cg && data[i + 2] === cb) {
          pixelCounts[type]++;
          break;
        }
      }
    }

    // Fallback to the full canvas only if the boundary mask painted nothing
    // at all (e.g. no BOUNDARY group found) -- keeps this from ever
    // dividing by zero rather than silently reproducing the bbox-area bug.
    const totalPixels = siteMaskPixels || (STATS_CANVAS_W * STATS_CANVAS_H);
    return {
      SOFT:  (pixelCounts.SOFT  / totalPixels) * 100,
      SHADE: (pixelCounts.SHADE / totalPixels) * 100,
      HARD:  (pixelCounts.HARD  / totalPixels) * 100,
      PROG:  (pixelCounts.PROG  / totalPixels) * 100,
      BLUE:  (pixelCounts.BLUE  / totalPixels) * 100,
    };
  },

  /**
   * Resets the entire application state.
   * Clears pathCache so stale geometry doesn't survive a reload.
   */
  clear() {
    this.stack = [];
    this.editingId = null;
    this.lastGeneration = { narrative: '', geometries: [], diagram: '' };
    this.baseCleared = true;
    this.pathCache.clear();
  }
};

// ── EXPORT FOR GLOBAL ACCESS ─────────────────────────────────────────────────
window.MemoryState = MemoryState;

// ── UI STATUS MESSENGER ──────────────────────────────────────────────────────
window.setStatus = (text, type = 'info') => {
  const statusText = document.getElementById('status-text');
  const statusDot  = document.getElementById('status-dot');
  if (statusText) statusText.textContent = text.toUpperCase();
  if (statusDot) {
    statusDot.className = '';
    statusDot.classList.add(type);
  }
};
