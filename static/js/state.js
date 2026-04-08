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
  const re = /(-?\d+\.?\d*(?:e[-+]?\d+)?)/gi;
  let m;
  while ((m = re.exec(d)) !== null) {
    const v = parseFloat(m[1]);
    if (!isNaN(v)) nums.push(v);
  }

  if (nums.length < 4) return null;

  // Ensure even count — drop trailing orphan
  const len = nums.length % 2 === 0 ? nums.length : nums.length - 1;
  return new Float32Array(nums.slice(0, len));
}

/**
 * Shoelace formula: true signed area of a polygon defined by
 * a flat Float32Array of [x0,y0, x1,y1, ...] in SVG source space.
 */
function _shoelace(verts) {
  const n = verts.length >> 1; // pair count
  if (n < 3) return 0;
  let sum = 0;
  for (let i = 0; i < n; i++) {
    const j = (i + 1) % n;
    sum += verts[i * 2] * verts[j * 2 + 1]
         - verts[j * 2] * verts[i * 2 + 1];
  }
  return Math.abs(sum) * 0.5;
}

/**
 * AABB of a Float32Array vertex list. Returns {minX,minY,maxX,maxY}.
 */
function _vertsBBox(verts) {
  let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
  for (let i = 0; i < verts.length; i += 2) {
    if (verts[i]   < minX) minX = verts[i];
    if (verts[i]   > maxX) maxX = verts[i];
    if (verts[i+1] < minY) minY = verts[i+1];
    if (verts[i+1] > maxY) maxY = verts[i+1];
  }
  return { minX, minY, maxX, maxY };
}

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
            const verts = _extractVertices(p);
            if (verts) polys.push(verts);
          });

    const result = { polys, precBBox };
    this.pathCache.set(key, result);
    return result;
  },

  /**
   * Calculates the programmatic mix of the current stack using:
   * - Cached parsed geometry (Float32Array, populated once per site+layer)
   * - Shoelace formula for true polygon area instead of AABB rectangle
   * - AABB overlap with site boundary for visible-area clipping
   *
   * All zone types (SOFT/HARD/PROG/BLUE) are summed directly — no residual.
   */
  getProgramStats() {
    if (this.stack.length === 0 || !window.Engine2D) return { SOFT: 0, HARD: 0, PROG: 0, BLUE: 0 };

    const baseSVG = this.svgCache['PershingSquare'];
    if (!baseSVG) return { SOFT: 0, HARD: 0, PROG: 0, BLUE: 0 };

    const baseEl   = window.Engine2D.parseSVG(baseSVG);
    const baseBBox = window.Engine2D.getBoundaryBBox(baseEl);
    const siteArea = baseBBox.w * baseBBox.h;
    if (siteArea === 0) return { SOFT: 0, HARD: 0, PROG: 0, BLUE: 0 };

    const totals = { SOFT: 0, HARD: 0, PROG: 0, BLUE: 0 };
    const cx = baseBBox.x + baseBBox.w / 2;
    const cy = baseBBox.y + baseBBox.h / 2;

    this.stack.forEach(item => {
      if (item.visible === false) return;

      const lId = item.layerId || '';

      // Zone classification — PEDESTRIAN_PATH counts as HARD
      let type = 'HARD';
      if (lId.includes('GREEN') || lId.includes('SHADE'))           type = 'SOFT';
      else if (lId.includes('WATER'))                                type = 'BLUE';
      else if (lId.includes('ATTRACTOR') || lId.includes('UNIQUE')) type = 'PROG';

      const geom = this._getLayerGeometry(item.site, item.layerId);
      if (!geom || geom.polys.length === 0) return;

      const { polys, precBBox } = geom;
      const fitScale   = Math.min(baseBBox.w / (precBBox.w || 1), baseBBox.h / (precBBox.h || 1));
      const finalScale = fitScale * (item.transform.scale || 1.0);
      const pcx = precBBox.x + precBBox.w / 2;
      const pcy = precBBox.y + precBBox.h / 2;

      polys.forEach(verts => {
        // ── Shoelace area in source SVG space, then scale²  ──────────────
        const rawArea = _shoelace(verts);
        if (rawArea === 0) return;
        const worldArea = rawArea * finalScale * finalScale;

        // ── Transform polygon AABB to world space for boundary clipping ──
        const bb = _vertsBBox(verts);
        const rot = item.transform.rot || 0;

        let wW = (bb.maxX - bb.minX) * finalScale;
        let wH = (bb.maxY - bb.minY) * finalScale;
        if (Math.abs(rot) === 90 || Math.abs(rot) === 270) {
          [wW, wH] = [wH, wW];
        }

        // Centroid of this polygon in world space
        const srcCx = (bb.minX + bb.maxX) / 2;
        const srcCy = (bb.minY + bb.maxY) / 2;
        const dx = (srcCx - pcx) * finalScale;
        const dy = (srcCy - pcy) * finalScale;
        const wCx = cx + item.transform.x + dx;
        const wCy = cy + item.transform.y + dy;

        // Overlap of polygon AABB with site boundary
        const overlapW = Math.max(0,
          Math.min(wCx + wW / 2, baseBBox.x + baseBBox.w) -
          Math.max(wCx - wW / 2, baseBBox.x));
        const overlapH = Math.max(0,
          Math.min(wCy + wH / 2, baseBBox.y + baseBBox.h) -
          Math.max(wCy - wH / 2, baseBBox.y));
        const polyAABB = wW * wH;

        // Visible fraction of this polygon: Shoelace area × clipped/total AABB ratio
        const visibleArea = polyAABB > 0
          ? worldArea * ((overlapW * overlapH) / polyAABB)
          : 0;

        totals[type] += visibleArea;
      });
    });

    return {
      SOFT: Math.min(100, (totals.SOFT / siteArea) * 100),
      HARD: Math.min(100, (totals.HARD / siteArea) * 100),
      PROG: Math.min(100, (totals.PROG / siteArea) * 100),
      BLUE: Math.min(100, (totals.BLUE / siteArea) * 100)
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
