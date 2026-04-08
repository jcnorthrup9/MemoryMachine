/**
 * MEMORY MACHINE // APPLICATION STATE
 * Centralized store for the layer stack, SVG cache, and transformation data.
 */

const MemoryState = {
  // ── 1. THE LAYER STACK ───────────────────────────────────────────────────
  // Array of objects representing the current architectural remix
  stack: [], 
  
  // ── 2. SELECTION & EDITING ───────────────────────────────────────────────
  // The ID of the layer currently being manipulated by the user
  editingId: null, 
  
  // ── 3. DATA CACHE ────────────────────────────────────────────────────────
  // Stores raw SVG strings fetched from the server to avoid redundant API calls
  svgCache: {
    'PershingSquare': null,
    'ParcdelaVillette': null,
    'ZaryadyePark': null,
    'Schouwburgplein': null
  },
  
  // ── 4. APP MODE ──────────────────────────────────────────────────────────
  // false = Draft (Manual), true = Dream (AI-driven)
  dreamMode: false, 
  
  // ── 5. AI GENERATION DATA ───────────────────────────────────────────────
  // Stores the last successful response from /api/generate
  lastGeneration: {
    narrative: "",
    geometries: [],
    diagram: ""
  },

  // ── 5.5 BASE CONTEXT ─────────────────────────────────────────────────────
  baseCleared: false, // Flag to hide internal park geometry when stack is cleared

  // ── 6. STATE HELPERS ─────────────────────────────────────────────────────
  
  /**
   * Calculates the programmatic mix of the current stack.
   * Used to update the ZONAL CONSTRAINTS HUD.
   */
  getProgramStats() {
    if (this.stack.length === 0 || !window.Engine2D) return { SOFT: 0, HARD: 100, PROG: 0, BLUE: 0 };
    
    const baseSVG = this.svgCache['PershingSquare'];
    if (!baseSVG) return { SOFT: 0, HARD: 100, PROG: 0, BLUE: 0 };
    
    const baseEl = window.Engine2D.parseSVG(baseSVG);
    const baseBBox = window.Engine2D.getBoundaryBBox(baseEl);
    const siteArea = baseBBox.w * baseBBox.h;
    if (siteArea === 0) return { SOFT: 0, HARD: 100, PROG: 0, BLUE: 0 };
    
    const totals = { SOFT: 0, HARD: 0, PROG: 0, BLUE: 0 };
    let occupiedArea = 0;

    const cx = baseBBox.x + baseBBox.w / 2;
    const cy = baseBBox.y + baseBBox.h / 2;

    this.stack.forEach(item => {
      if (item.visible === false) return;
      
      const lId = item.layerId || "";
      if (lId.includes('PEDESTRIAN') || lId.includes('PATH')) return;
      
      let type = "HARD";
      if (lId.includes('GREEN') || lId.includes('SHADE')) type = 'SOFT';
      else if (lId.includes('WATER')) type = 'BLUE';
      else if (lId.includes('ATTRACTOR') || lId.includes('UNIQUE')) type = 'PROG';

      const precSVG = this.svgCache[item.site];
      if (!precSVG) return;
      const precEl = window.Engine2D.parseSVG(precSVG);
      const layerG = precEl.querySelector(`g[id*="${item.layerId}"]`) || precEl.querySelector(`g[id="${item.layerId}"]`);
      if (!layerG) return;

      const precBBox = window.Engine2D.getBoundaryBBox(precEl);
      const re = /(-?\d+\.?\d*)/g;

      layerG.querySelectorAll('path, polyline, polygon, rect, circle, line').forEach(p => {
        let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
        const tag = p.tagName.toLowerCase();
        if (tag === 'rect') {
          const x = parseFloat(p.getAttribute('x')||0), y = parseFloat(p.getAttribute('y')||0);
          const w = parseFloat(p.getAttribute('width')||0), h = parseFloat(p.getAttribute('height')||0);
          minX = Math.min(minX, x); maxX = Math.max(maxX, x+w);
          minY = Math.min(minY, y); maxY = Math.max(maxY, y+h);
        } else if (tag === 'circle') {
          const x = parseFloat(p.getAttribute('cx')||0), y = parseFloat(p.getAttribute('cy')||0);
          const r = parseFloat(p.getAttribute('r')||0);
          minX = Math.min(minX, x-r); maxX = Math.max(maxX, x+r);
          minY = Math.min(minY, y-r); maxY = Math.max(maxY, y+r);
        } else if (tag === 'line') {
          const x1 = parseFloat(p.getAttribute('x1')||0), y1 = parseFloat(p.getAttribute('y1')||0);
          const x2 = parseFloat(p.getAttribute('x2')||0), y2 = parseFloat(p.getAttribute('y2')||0);
          minX = Math.min(minX, x1, x2); maxX = Math.max(maxX, x1, x2);
          minY = Math.min(minY, y1, y2); maxY = Math.max(maxY, y1, y2);
        } else {
          let d = p.getAttribute('d') || p.getAttribute('points') || '';
          // Strip out Arc radii and flags to prevent massive false bounding boxes
          d = d.replace(/[Aa]\s*[-+]?[\d.]+\s*[, ]?\s*[-+]?[\d.]+\s*[, ]?\s*[-+]?[\d.]+\s*[, ]?\s*[01]\s*[, ]?\s*[01]\s*[, ]?/g, '');
          let m, nums = [];
          while ((m = re.exec(d)) !== null) nums.push(parseFloat(m[1]));
          for (let i = 0; i < nums.length - 1; i += 2) {
            if (!isNaN(nums[i])) {
              minX = Math.min(minX, nums[i]); maxX = Math.max(maxX, nums[i]);
              minY = Math.min(minY, nums[i+1]); maxY = Math.max(maxY, nums[i+1]);
            }
          }
        }

        if (isFinite(minX)) {
          const layerW = maxX - minX;
          const layerH = maxY - minY;
          
          const fitScale = Math.min(baseBBox.w / (precBBox.w || 1), baseBBox.h / (precBBox.h || 1));
          const finalScale = fitScale * (item.transform.scale || 1.0);
          
          let finalW = layerW * finalScale;
          let finalH = layerH * finalScale;
          
          if (Math.abs(item.transform.rot) === 90 || Math.abs(item.transform.rot) === 270) {
            finalW = layerH * finalScale;
            finalH = layerW * finalScale;
          }
          
          const dx = (minX + layerW / 2) - (precBBox.x + precBBox.w / 2);
          const dy = (minY + layerH / 2) - (precBBox.y + precBBox.h / 2);
          const itemCx = cx + item.transform.x + (dx * finalScale);
          const itemCy = cy + item.transform.y + (dy * finalScale);
          
          const overlapW = Math.max(0, Math.min(itemCx + finalW/2, baseBBox.x + baseBBox.w) - Math.max(itemCx - finalW/2, baseBBox.x));
          const overlapH = Math.max(0, Math.min(itemCy + finalH/2, baseBBox.y + baseBBox.h) - Math.max(itemCy - finalH/2, baseBBox.y));
          const area = overlapW * overlapH;
          
          if (type !== 'HARD') {
            totals[type] += area;
            occupiedArea += area;
          }
        }
      });
    });

    totals.HARD = Math.max(0, siteArea - occupiedArea);
    
    return {
      SOFT: Math.min(100, (totals.SOFT / siteArea) * 100),
      HARD: Math.min(100, (totals.HARD / siteArea) * 100),
      PROG: Math.min(100, (totals.PROG / siteArea) * 100),
      BLUE: Math.min(100, (totals.BLUE / siteArea) * 100)
    };
  },

  /**
   * Resets the entire application state.
   */
  clear() {
    this.stack = [];
    this.editingId = null;
    this.lastGeneration = { narrative: "", geometries: [], diagram: "" };
    this.baseCleared = true;
  }
};

// ── 7. EXPORT FOR GLOBAL ACCESS ─────────────────────────────────────────────
window.MemoryState = MemoryState;

// ── 8. UI STATUS MESSENGER ────────────────────────────────────────────────
window.setStatus = (text, type = 'info') => {
  const statusText = document.getElementById('status-text');
  const statusDot = document.getElementById('status-dot');
  if (statusText) statusText.textContent = text.toUpperCase();
  if (statusDot) {
    statusDot.className = ''; // Clear previous
    statusDot.classList.add(type); // 'running', 'success', 'error'
  }
};