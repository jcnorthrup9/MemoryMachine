/**
 * SPATIALIZE tab -- 2D diagram rendering + HUD math, ported from the root
 * 2D app's static/js/engine2D.js + static/js/state.js (2026-07-23).
 *
 * Framework-agnostic on purpose (plain functions, no React) -- same pattern
 * PaintOverlay.jsx already uses for its freehand sketch canvas: an
 * imperative draw function called from a useEffect+ref, not a declarative
 * JSX re-derivation of SVG DOM. Callers pass in whatever state they own
 * (stack array, svgCache object) instead of reading a global MemoryState,
 * since this now lives inside React component state, not a vanilla-JS
 * global.
 *
 * Ported behavior includes this session's two HUD accuracy fixes:
 * - _hasRealFill(): stroke-only linework (e.g. PEDESTRIAN_PATH's 583 dash
 *   segments in the real site SVG) no longer counts as filled area.
 * - Boundary-polygon area mask: percentages are computed against the real
 *   (possibly rotated) BOUNDARY polygon's own pixel count, not the full
 *   stats canvas -- Pershing Square's boundary is only ~48% of its own
 *   axis-aligned bbox, so the naive denominator silently deflated every
 *   percentage by ~2x.
 */

const STATS_CANVAS_W = 300;
const STATS_CANVAS_H = 200;

const STATS_CATEGORY_COLORS = {
  SOFT:  [76, 175, 80],
  SHADE: [255, 235, 59],
  HARD:  [158, 158, 158],
  PROG:  [255, 152, 0],
  BLUE:  [3, 169, 244],
};

const SITE_MASK_COLOR = [1, 1, 1];

export function parseSVG(svgText) {
  return new DOMParser().parseFromString(svgText, 'image/svg+xml').documentElement;
}

export function getBoundaryBBox(svgEl) {
  const g = svgEl.querySelector('g[id*="BOUNDARY"]') || svgEl.querySelector('g[id="BOUNDARY"]');

  if (!g) {
    const vb = svgEl.getAttribute('viewBox')?.split(/\s+|,/) || [0, 0, 1224, 792];
    return { x: parseFloat(vb[0]), y: parseFloat(vb[1]), w: parseFloat(vb[2]), h: parseFloat(vb[3]) };
  }

  let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
  const re = /(-?\d+\.?\d*)/g;

  g.querySelectorAll('path, polyline, polygon').forEach((p) => {
    let d = p.getAttribute('d') || p.getAttribute('points') || '';
    d = d.replace(/[Aa]\s*[-+]?[\d.]+\s*[, ]?\s*[-+]?[\d.]+\s*[, ]?\s*[-+]?[\d.]+\s*[, ]?\s*[01]\s*[, ]?\s*[01]\s*[, ]?/g, '');
    let m, nums = [];
    while ((m = re.exec(d)) !== null) nums.push(parseFloat(m[1]));
    for (let i = 0; i < nums.length - 1; i += 2) {
      if (!isNaN(nums[i])) {
        minX = Math.min(minX, nums[i]); maxX = Math.max(maxX, nums[i]);
        minY = Math.min(minY, nums[i + 1]); maxY = Math.max(maxY, nums[i + 1]);
      }
    }
  });

  return isFinite(minX) ? { x: minX, y: minY, w: maxX - minX, h: maxY - minY } : { x: 0, y: 0, w: 1224, h: 792 };
}

export function buildBoundaryClipPath(svgEl, ns, clipId) {
  const g = svgEl.querySelector('g[id*="BOUNDARY"]') || svgEl.querySelector('g[id="BOUNDARY"]');
  const cp = document.createElementNS(ns, 'clipPath');
  cp.setAttribute('id', clipId);
  if (!g) return cp;

  const poly = document.createElementNS(ns, 'polygon');
  const pts = [];
  const re = /(-?\d+\.?\d*)/g;
  g.querySelectorAll('path').forEach((pathEl) => {
    const d = pathEl.getAttribute('d') || '';
    let m;
    while ((m = re.exec(d)) !== null) pts.push(m[0]);
  });
  poly.setAttribute('points', pts.join(','));
  cp.appendChild(poly);
  return cp;
}

// urban_engine.py's remix_layers() emits transform.x_frac/y_frac (fraction
// of the base boundary's own size) -- everything below expects absolute
// transform.x/y in that SVG's native units. See static/main.js's
// _fracToPixel() for the original (this session's HUD-fix commit).
export function fracToPixel(svgCache, xFrac, yFrac) {
  const baseSVG = svgCache['PershingSquare'];
  if (!baseSVG) return { x: 0, y: 0 };
  const bbox = getBoundaryBBox(parseSVG(baseSVG));
  return { x: (xFrac || 0) * bbox.w, y: (yFrac || 0) * bbox.h };
}

/**
 * Renders the 2D canvas into `container` (a DOM node, e.g. from a React
 * ref) from the given state. Mirrors engine2D.js's render() minus the
 * site-grid overlay (removed from the root app's UI per user request) and
 * the light/dark theme branch (this app is dark-only).
 */
export function render(container, { svgCache, stack, baseCleared }) {
  const baseSVG = svgCache['PershingSquare'];
  if (!baseSVG || !container) return;

  const ns = 'http://www.w3.org/2000/svg';
  const baseSVGEl = parseSVG(baseSVG);
  const bbox = getBoundaryBBox(baseSVGEl);
  if (!bbox) return;

  const bgFill = '#050505';
  const bndStroke = '#ffffff';

  const svg = document.createElementNS(ns, 'svg');
  const pad = bbox.w * 0.20;
  svg.setAttribute('viewBox', `${bbox.x - pad} ${bbox.y - pad} ${bbox.w + pad * 2} ${bbox.h + pad * 2}`);
  svg.style.cssText = `width:100%;height:100%;display:block;background:${bgFill};`;

  const defs = document.createElementNS(ns, 'defs');
  defs.appendChild(buildBoundaryClipPath(baseSVGEl, ns, 'spatializer-clip-boundary'));
  svg.appendChild(defs);

  // 1. DYNAMIC CONTEXT
  const contextGroup = document.createElementNS(ns, 'g');
  contextGroup.setAttribute('class', 'context-group');
  let contextKeywords = ['STREET', 'BUILDING', 'PARKING', 'PEDESTRIAN', 'GREEN_SPACE', 'WATER', 'SHADE', 'FURNITURE'];
  if (baseCleared) contextKeywords = ['STREET', 'BUILDING'];

  baseSVGEl.querySelectorAll('g').forEach((g) => {
    const id = g.getAttribute('id') || '';
    const upperId = id.toUpperCase();
    if (baseCleared && (upperId.includes('FURNITURE') || upperId.includes('WATER') || upperId.includes('HARD'))) return;

    if (contextKeywords.some((key) => upperId.includes(key))) {
      const c = g.cloneNode(true);
      let darkCol;
      if (upperId.includes('GREEN') || upperId.includes('SHADE')) darkCol = '#4CAF50';
      else if (upperId.includes('WATER')) darkCol = '#03A9F4';
      else if (upperId.includes('ATTRACTOR') || upperId.includes('UNIQUE')) darkCol = '#FF9800';
      else if (upperId.includes('STREET') && !upperId.includes('FURNITURE')) darkCol = '#aaaaaa';
      else if (upperId.includes('PEDESTRIAN')) darkCol = '#888888';
      else darkCol = '#666666';

      c.querySelectorAll('path, polyline, line, polygon, rect, circle').forEach((p) => {
        p.setAttribute('stroke', darkCol);
        p.style.stroke = darkCol;
        p.setAttribute('fill', 'none');
        p.style.fill = 'none';
        const sw = parseFloat(p.getAttribute('stroke-width') || '1');
        if (sw > 0.8) { p.setAttribute('stroke-width', '0.8'); p.style.strokeWidth = '0.8'; }
      });
      contextGroup.appendChild(c);
    }
  });
  svg.appendChild(contextGroup);

  if (baseCleared) {
    const bndG = baseSVGEl.querySelector('g[id*="BOUNDARY"]') || baseSVGEl.querySelector('g[id="BOUNDARY"]');
    if (bndG) {
      const blackout = bndG.cloneNode(true);
      blackout.setAttribute('class', 'blackout-mask');
      blackout.querySelectorAll('path, polygon, polyline, rect, circle').forEach((p) => {
        p.setAttribute('fill', bgFill);
        p.style.fill = bgFill;
        p.setAttribute('stroke', 'none');
        p.style.stroke = 'none';
      });
      svg.appendChild(blackout);
    }
  }

  // 2. THE INTERVENTION STACK
  if (stack && stack.length > 0) {
    const cx = bbox.x + bbox.w / 2;
    const cy = bbox.y + bbox.h / 2;

    stack.forEach((item) => {
      if (!item.visible) return;
      if (item.contextLayer) return;
      const siteSVG = svgCache[item.site];
      if (!siteSVG) return;

      const precEl = parseSVG(siteSVG);
      const layerG = precEl.querySelector(`g[id*="${item.layerId}"]`) || precEl.querySelector(`g[id="${item.layerId}"]`);
      if (!layerG) return;

      const wrapper = document.createElementNS(ns, 'g');
      wrapper.setAttribute('clip-path', 'url(#spatializer-clip-boundary)');
      wrapper.setAttribute('class', 'intervention-group');

      const xformed = layerG.cloneNode(true);
      const t = item.transform;

      const precBBox = getBoundaryBBox(precEl);
      const pcx = precBBox.x + precBBox.w / 2;
      const pcy = precBBox.y + precBBox.h / 2;
      const fitScale = Math.min(bbox.w / (precBBox.w || 1), bbox.h / (precBBox.h || 1));
      const finalScale = fitScale * (t.scale || 1.0);

      xformed.setAttribute('transform', `translate(${cx + t.x}, ${cy + t.y}) scale(${finalScale}) rotate(${t.rot || 0}) translate(${-pcx}, ${-pcy})`);

      xformed.querySelectorAll('path, polyline, line, polygon, rect, circle').forEach((el) => {
        const finalCol = item.color;
        const origFill = el.getAttribute('fill') || el.style.fill;
        const hadFill = origFill && origFill !== 'none' && origFill !== '';
        if (hadFill) {
          el.setAttribute('fill', finalCol);
          el.style.fill = finalCol;
          el.setAttribute('fill-opacity', '0.3');
          el.style.fillOpacity = '0.3';
        } else {
          el.setAttribute('fill', 'none');
          el.style.fill = 'none';
        }
        el.setAttribute('stroke', finalCol);
        el.style.stroke = finalCol;
      });

      wrapper.appendChild(xformed);
      svg.appendChild(wrapper);
    });
  }

  // 3. BOUNDARY
  const bndG = baseSVGEl.querySelector('g[id*="BOUNDARY"]');
  if (bndG) {
    const bClone = bndG.cloneNode(true);
    bClone.setAttribute('class', 'boundary-group');
    bClone.querySelectorAll('path, polyline, polygon, line, rect').forEach((p) => {
      p.setAttribute('fill', 'none');
      p.style.fill = 'none';
      p.setAttribute('stroke', bndStroke);
      p.style.stroke = bndStroke;
      p.setAttribute('stroke-width', '1');
      p.style.strokeWidth = '1';
    });
    svg.appendChild(bClone);
  }

  container.innerHTML = '';
  container.appendChild(svg);
}

function extractVertices(el) {
  const tag = el.tagName.toLowerCase();

  if (tag === 'rect') {
    const x = parseFloat(el.getAttribute('x') || 0);
    const y = parseFloat(el.getAttribute('y') || 0);
    const w = parseFloat(el.getAttribute('width') || 0);
    const h = parseFloat(el.getAttribute('height') || 0);
    if (w === 0 || h === 0) return null;
    return new Float32Array([x, y, x + w, y, x + w, y + h, x, y + h]);
  }

  if (tag === 'circle') {
    const cx = parseFloat(el.getAttribute('cx') || 0);
    const cy = parseFloat(el.getAttribute('cy') || 0);
    const r = parseFloat(el.getAttribute('r') || 0);
    if (r === 0) return null;
    const pts = [];
    for (let i = 0; i < 16; i++) {
      const a = (i / 16) * Math.PI * 2;
      pts.push(cx + Math.cos(a) * r, cy + Math.sin(a) * r);
    }
    return new Float32Array(pts);
  }

  if (tag === 'line') return null;

  let d = el.getAttribute('d') || el.getAttribute('points') || '';
  if (!d) return null;
  d = d.replace(/[Aa]\s*[-+]?[\d.]+\s*[,\s]+[-+]?[\d.]+\s*[,\s]+[-+]?[\d.]+\s*[,\s]+[01]\s*[,\s]+[01]\s*[,\s]*/g, '');

  const nums = [];
  const matches = d.matchAll(/(-?\d+\.?\d*(?:e[-+]?\d+)?)/gi);
  for (const m of matches) {
    const v = parseFloat(m[0]);
    if (!isNaN(v)) nums.push(v);
  }
  if (nums.length < 4) return null;
  const len = nums.length % 2 === 0 ? nums.length : nums.length - 1;
  return new Float32Array(nums.slice(0, len));
}

function hasRealFill(el) {
  let fill = el.getAttribute('fill') || '';
  const style = el.getAttribute('style') || '';
  const m = /fill\s*:\s*([^;]+)/.exec(style);
  if (m) fill = m[1].trim();
  return fill !== '' && fill !== 'none';
}

function getLayerGeometry(svgCache, pathCache, siteId, layerId) {
  const key = `${siteId}::${layerId}`;
  if (pathCache.has(key)) return pathCache.get(key);

  const svgText = svgCache[siteId];
  if (!svgText) return null;

  const el = parseSVG(svgText);
  const precBBox = getBoundaryBBox(el);
  const layerG = el.querySelector(`g[id*="${layerId}"]`) || el.querySelector(`g[id="${layerId}"]`);
  if (!layerG) {
    pathCache.set(key, null);
    return null;
  }

  const polys = [];
  layerG.querySelectorAll('path, polyline, polygon, rect, circle, line').forEach((p) => {
    if (!hasRealFill(p)) return;
    const verts = extractVertices(p);
    if (verts) polys.push(verts);
  });

  const result = { polys, precBBox };
  pathCache.set(key, result);
  return result;
}

/**
 * ZONAL CONSTRAINTS HUD math -- ported from state.js's getProgramStats(),
 * including this session's fill-check and boundary-mask-area fixes.
 * `pathCache` is caller-owned (e.g. a useRef(new Map()) in the component)
 * so repeated calls across renders stay cheap.
 */
export function getProgramStats({ svgCache, stack, pathCache }) {
  const empty = { SOFT: 0, SHADE: 0, HARD: 0, PROG: 0, BLUE: 0 };
  if (!stack || stack.length === 0) return empty;

  const baseSVG = svgCache['PershingSquare'];
  if (!baseSVG) return empty;

  const baseEl = parseSVG(baseSVG);
  const baseBBox = getBoundaryBBox(baseEl);
  if (baseBBox.w === 0 || baseBBox.h === 0) return empty;

  const cx = baseBBox.x + baseBBox.w / 2;
  const cy = baseBBox.y + baseBBox.h / 2;

  const canvas = document.createElement('canvas');
  canvas.width = STATS_CANVAS_W;
  canvas.height = STATS_CANVAS_H;
  const ctx = canvas.getContext('2d', { willReadFrequently: true });
  const px = (wx) => ((wx - baseBBox.x) / baseBBox.w) * STATS_CANVAS_W;
  const py = (wy) => ((wy - baseBBox.y) / baseBBox.h) * STATS_CANVAS_H;

  const boundaryG = baseEl.querySelector('g[id*="BOUNDARY"]') || baseEl.querySelector('g[id="BOUNDARY"]');
  if (boundaryG) {
    const bPts = [];
    boundaryG.querySelectorAll('path').forEach((p) => {
      const d = p.getAttribute('d') || '';
      const matches = d.matchAll(/(-?\d+\.?\d*(?:e[-+]?\d+)?)/gi);
      for (const m of matches) bPts.push(parseFloat(m[0]));
    });
    if (bPts.length >= 6) {
      const [sr, sg, sb] = SITE_MASK_COLOR;
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

  stack.forEach((item) => {
    if (item.visible === false) return;
    const lId = item.layerId || '';

    let type = 'HARD';
    if (lId.includes('SHADE')) type = 'SHADE';
    else if (lId.includes('GREEN')) type = 'SOFT';
    else if (lId.includes('WATER')) type = 'BLUE';
    else if (lId.includes('ATTRACTOR') || lId.includes('UNIQUE')) type = 'PROG';

    const geom = getLayerGeometry(svgCache, pathCache, item.site, item.layerId);
    if (!geom || geom.polys.length === 0) return;

    const { polys, precBBox } = geom;
    const fitScale = Math.min(baseBBox.w / (precBBox.w || 1), baseBBox.h / (precBBox.h || 1));
    const finalScale = fitScale * (item.transform.scale || 1.0);
    const pcx = precBBox.x + precBBox.w / 2;
    const pcy = precBBox.y + precBBox.h / 2;
    const rot = ((item.transform.rot || 0) * Math.PI) / 180;
    const cosR = Math.cos(rot), sinR = Math.sin(rot);
    const [r, g, b] = STATS_CATEGORY_COLORS[type];
    ctx.fillStyle = `rgb(${r},${g},${b})`;

    polys.forEach((verts) => {
      if (verts.length < 6) return;
      ctx.beginPath();
      for (let i = 0; i < verts.length; i += 2) {
        const dx = verts[i] - pcx;
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
  let siteMaskPixels = 0;
  for (let i = 0; i < data.length; i += 4) {
    if (data[i + 3] === 0) continue;
    siteMaskPixels++;
    for (const type in STATS_CATEGORY_COLORS) {
      const [cr, cg, cb] = STATS_CATEGORY_COLORS[type];
      if (data[i] === cr && data[i + 1] === cg && data[i + 2] === cb) {
        pixelCounts[type]++;
        break;
      }
    }
  }

  const totalPixels = siteMaskPixels || STATS_CANVAS_W * STATS_CANVAS_H;
  return {
    SOFT: (pixelCounts.SOFT / totalPixels) * 100,
    SHADE: (pixelCounts.SHADE / totalPixels) * 100,
    HARD: (pixelCounts.HARD / totalPixels) * 100,
    PROG: (pixelCounts.PROG / totalPixels) * 100,
    BLUE: (pixelCounts.BLUE / totalPixels) * 100,
  };
}

export function getLayerColor(layerId) {
  const id = (layerId || '').toUpperCase();
  if (id.includes('SHADE')) return '#FFEB3B';
  if (id.includes('GREEN')) return '#4CAF50';
  if (id.includes('WATER')) return '#03A9F4';
  if (id.includes('ATTRACTOR') || id.includes('UNIQUE')) return '#FF9800';
  return '#9E9E9E';
}
