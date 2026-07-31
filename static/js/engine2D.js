/**
 * MEMORY MACHINE // 2D GEOMETRY ENGINE
 * Handles SVG parsing, boundary clipping, and layer rendering.
 * Optimized for Rhino-exported architectural diagrams.
 */
const Engine2D = {
  /**
   * Converts raw SVG text into a virtual DOM element for processing.
   */
  parseSVG(svgText) {
    return new DOMParser().parseFromString(svgText, 'image/svg+xml').documentElement;
  },

  /**
   * Robust BBox calculation for virtual elements.
   * Standard getBBox() fails on elements not attached to the live DOM.
   */
  getBoundaryBBox(svgEl) {
    const g = svgEl.querySelector('g[id*="BOUNDARY"]') || svgEl.querySelector('g[id="BOUNDARY"]');
    
    if (!g) {
      const vb = svgEl.getAttribute('viewBox')?.split(/\s+|,/) || [0, 0, 1224, 792];
      return { x: parseFloat(vb[0]), y: parseFloat(vb[1]), w: parseFloat(vb[2]), h: parseFloat(vb[3]) };
    }

    let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
    const re = /(-?\d+\.?\d*)/g;
    
    g.querySelectorAll('path, polyline, polygon').forEach(p => {
      let d = p.getAttribute('d') || p.getAttribute('points') || '';
      // Strip Arc radii and flags to prevent massive false bounding boxes
      d = d.replace(/[Aa]\s*[-+]?[\d.]+\s*[, ]?\s*[-+]?[\d.]+\s*[, ]?\s*[-+]?[\d.]+\s*[, ]?\s*[01]\s*[, ]?\s*[01]\s*[, ]?/g, '');
      let m, nums = [];
      while ((m = re.exec(d)) !== null) nums.push(parseFloat(m[1]));
      
      for (let i = 0; i < nums.length - 1; i += 2) {
        if (!isNaN(nums[i])) {
          minX = Math.min(minX, nums[i]); maxX = Math.max(maxX, nums[i]);
          minY = Math.min(minY, nums[i+1]); maxY = Math.max(maxY, nums[i+1]);
        }
      }
    });

    return isFinite(minX) ? { x: minX, y: minY, w: maxX - minX, h: maxY - minY } : { x: 0, y: 0, w: 1224, h: 792 };
  },

  /**
   * Creates a <clipPath> based on the site boundary to mask the intervention stack.
   */
  buildBoundaryClipPath(svgEl, ns, clipId) {
    const g = svgEl.querySelector('g[id*="BOUNDARY"]') || svgEl.querySelector('g[id="BOUNDARY"]');
    const cp = document.createElementNS(ns, 'clipPath');
    cp.setAttribute('id', clipId);
    
    if (!g) return cp;

    const poly = document.createElementNS(ns, 'polygon');
    const pts = [];
    const re = /(-?\d+\.?\d*)/g;
    
    g.querySelectorAll('path').forEach(pathEl => {
      const d = pathEl.getAttribute('d') || '';
      let m;
      while ((m = re.exec(d)) !== null) pts.push(m[0]);
    });
    
    poly.setAttribute('points', pts.join(','));
    cp.appendChild(poly);
    return cp;
  },

  /**
   * Main Render Loop
   * Clears the container and draws the context + intervention stack.
   */
  render() {
    const baseSVG = MemoryState.svgCache['PershingSquare'];
    if (!baseSVG) return;

    const container = document.getElementById('remix-svg-container');
    const ns = 'http://www.w3.org/2000/svg';
    const baseSVGEl = this.parseSVG(baseSVG);
    const bbox = this.getBoundaryBBox(baseSVGEl);
    if (!bbox) return;

    // Apply Theme Stylings 
    const isLightMode = document.body.classList.contains('light-mode');
    const bgFill = isLightMode ? '#ffffff' : '#050505';
    const bndStroke = isLightMode ? '#000000' : '#ffffff';

    const svg = document.createElementNS(ns, 'svg');
    // Apply 20% padding to ensure the street network is visible
    const pad = bbox.w * 0.20;
    svg.setAttribute('viewBox', `${bbox.x - pad} ${bbox.y - pad} ${bbox.w + (pad*2)} ${bbox.h + (pad*2)}`);
    svg.style.cssText = `width:100%;height:100%;display:block;background:${bgFill};`;

    // DEFS — clip-boundary must exist before any layer references it
    const defs = document.createElementNS(ns, 'defs');
    defs.appendChild(this.buildBoundaryClipPath(baseSVGEl, ns, 'clip-boundary'));
    svg.appendChild(defs);

    // 1. DYNAMIC CONTEXT: Streets & Buildings
    const contextGroup = document.createElementNS(ns, 'g');
    contextGroup.setAttribute('class', 'context-group');
    let contextKeywords = ['STREET', 'BUILDING', 'PARKING', 'PEDESTRIAN', 'GREEN_SPACE', 'WATER', 'SHADE', 'FURNITURE'];

    // If base is cleared, keep only urban fabric outside the park boundary
    if (MemoryState.baseCleared) {
      contextKeywords = ['STREET', 'BUILDING'];
    }

    baseSVGEl.querySelectorAll('g').forEach(g => {
      const id = g.getAttribute('id') || "";
      const upperId = id.toUpperCase();
      
      // Prevent loose matching of interior park features when the base is cleared
      if (MemoryState.baseCleared && (upperId.includes('FURNITURE') || upperId.includes('WATER') || upperId.includes('HARD'))) {
        return;
      }

      if (contextKeywords.some(key => upperId.includes(key))) {
        const c = g.cloneNode(true);
        // Remap Rhino layer colours to the app colour system.
        // Preserve native stroke-widths — they encode Rhino lineweight hierarchy.
        // Assign color by layer type for dark mode (app color system)
        let darkCol;
        if (upperId.includes('GREEN') || upperId.includes('SHADE'))          darkCol = '#4CAF50';
        else if (upperId.includes('WATER'))                                   darkCol = '#03A9F4';
        else if (upperId.includes('ATTRACTOR') || upperId.includes('UNIQUE')) darkCol = '#FF9800';
        else if (upperId.includes('STREET') && !upperId.includes('FURNITURE')) darkCol = '#aaaaaa';
        else if (upperId.includes('PEDESTRIAN'))                              darkCol = '#888888';
        else                                                                  darkCol = '#666666';

        // Greyscale tone for light mode
        let lightCol;
        if (upperId.includes('STREET') && !upperId.includes('FURNITURE')) lightCol = '#000000';
        else if (upperId.includes('PEDESTRIAN'))                           lightCol = '#333333';
        else                                                               lightCol = '#555555';

        c.querySelectorAll('path, polyline, line, polygon, rect, circle').forEach(p => {
          if (isLightMode) {
            // Light mode: clean greyscale technical drawing — remap all strokes to black/grey, strip fills
            p.setAttribute('stroke', lightCol);
            p.style.stroke = lightCol;
            p.setAttribute('fill', 'none');
            p.style.fill = 'none';
            // Cap heavy Rhino lineweights (STREET at 2.55 → 1.5)
            const sw = parseFloat(p.getAttribute('stroke-width') || '1');
            if (sw > 1.5) { p.setAttribute('stroke-width', '1.5'); p.style.strokeWidth = '1.5'; }
          } else {
            // Dark mode: apply app color system (greens, blues, oranges, greys)
            p.setAttribute('stroke', darkCol);
            p.style.stroke = darkCol;
            p.setAttribute('fill', 'none');
            p.style.fill = 'none';
            const sw = parseFloat(p.getAttribute('stroke-width') || '1');
            if (sw > 0.8) { p.setAttribute('stroke-width', '0.8'); p.style.strokeWidth = '0.8'; }
          }
        });
        contextGroup.appendChild(c);
      }
    });
    svg.appendChild(contextGroup);

    // 1.5 BLACKOUT MASK: Hide anything else inside the park boundary
    if (MemoryState.baseCleared) {
      const bndG = baseSVGEl.querySelector('g[id*="BOUNDARY"]') || baseSVGEl.querySelector('g[id="BOUNDARY"]');
      if (bndG) {
        const blackout = bndG.cloneNode(true);
        blackout.setAttribute('class', 'blackout-mask');
        blackout.querySelectorAll('path, polygon, polyline, rect, circle').forEach(p => {
          p.setAttribute('fill', bgFill);
          p.style.fill = bgFill; // Force override inline SVG styles
          p.setAttribute('stroke', 'none');
          p.style.stroke = 'none';
        });
        svg.appendChild(blackout);
      }
    }

    // 2. THE INTERVENTION: Draw AI Generated Stack from MemoryState
    if (MemoryState.stack && MemoryState.stack.length > 0) {
      const cx = bbox.x + bbox.w / 2;
      const cy = bbox.y + bbox.h / 2;
      
      MemoryState.stack.forEach(item => {
        if (!item.visible) return;
        if (item.contextLayer) return; // drawn by context-group; skip here
        const siteSVG = MemoryState.svgCache[item.site];
        if (!siteSVG) return;
        
        const precEl = this.parseSVG(siteSVG);
        // Fuzzy layer matching to handle Rhino layer nesting (e.g., 'Layer::SOFT_01')
        const layerG = precEl.querySelector(`g[id*="${item.layerId}"]`) || precEl.querySelector(`g[id="${item.layerId}"]`);

        if (layerG) {
          const wrapper = document.createElementNS(ns, 'g');
          wrapper.setAttribute('clip-path', 'url(#clip-boundary)');
          wrapper.setAttribute('class', 'intervention-group');
          
          const xformed = layerG.cloneNode(true);
          const t = item.transform;
          
          // Calculate centering and normalization for the imported layer
          const precBBox = this.getBoundaryBBox(precEl);
          const pcx = precBBox.x + precBBox.w / 2;
          const pcy = precBBox.y + precBBox.h / 2;
          const fitScale = Math.min(bbox.w / (precBBox.w || 1), bbox.h / (precBBox.h || 1));
          const finalScale = fitScale * (t.scale || 1.0);
          
          // Apply transformation: Base Center + Offset -> Final Scale -> Rotation -> Center Origin
          xformed.setAttribute('transform', `translate(${cx + t.x}, ${cy + t.y}) scale(${finalScale}) rotate(${t.rot || 0}) translate(${-pcx}, ${-pcy})`);
          
          xformed.querySelectorAll('path, polyline, line, polygon, rect, circle').forEach(el => {
            const finalCol = isLightMode ? '#222222' : item.color;
            const finalFill = isLightMode ? '#888888' : item.color;

            // Preserve lineweights/dashes from Rhino, but override colors
            const origFill = el.getAttribute('fill') || el.style.fill;
            const hadFill = (origFill && origFill !== 'none' && origFill !== '');

            if (hadFill) {
              el.setAttribute('fill', finalFill);
              el.style.fill = finalFill;
              el.setAttribute('fill-opacity', '0.3');
              el.style.fillOpacity = '0.3';
            } else {
              el.setAttribute('fill', 'none');
              el.style.fill = 'none';
            }

            el.setAttribute('stroke', finalCol);
            el.style.stroke = finalCol;
            el.setAttribute('data-orig-color', item.color); // Store for colored exports
          });
          
          wrapper.appendChild(xformed);
          svg.appendChild(wrapper);
        }
      });
    }

    // 3. BOUNDARY: High-Contrast Park Edge
    const bndG = baseSVGEl.querySelector('g[id*="BOUNDARY"]');
    if (bndG) {
      const bClone = bndG.cloneNode(true);
      bClone.setAttribute('class', 'boundary-group');
      bClone.querySelectorAll('path, polyline, polygon, line, rect').forEach(p => {
        p.setAttribute('fill', 'none');
        p.style.fill = 'none';
        p.setAttribute('stroke', bndStroke);
        p.style.stroke = bndStroke;
        p.setAttribute('stroke-width', '1'); // Make boundary thinner
        p.style.strokeWidth = '1';
      });
      svg.appendChild(bClone);
    }

    // 4. SITE GRID: spatial-organizer overlay (see logic/site_grid.py) --
    // drawn last so it's visible on top; clipped to the boundary and kept
    // out of MemoryState.stack so it never reaches getProgramStats()'s tally.
    if (MemoryState.siteGrid) {
      this.renderGrid(svg, ns, bbox, MemoryState.siteGrid, isLightMode);
    }

    container.innerHTML = '';
    container.appendChild(svg);
  },

  /**
   * Draws each site-grid cell (from GET /api/site-grid) as a rotated quad,
   * converting each corner's x_frac/y_frac (fraction of the site's own real
   * width/length, 0.0 at center -- same convention _fracToPixel() in
   * main.js uses for stack-item placement) into this SVG's world space via
   * the live boundary bbox, exactly like a stack item's transform would.
   */
  renderGrid(svg, ns, bbox, grid, isLightMode) {
    const cx = bbox.x + bbox.w / 2;
    const cy = bbox.y + bbox.h / 2;
    const gridColor = isLightMode ? '#0066cc' : '#00e5ff';

    const g = document.createElementNS(ns, 'g');
    g.setAttribute('class', 'site-grid-overlay');
    g.setAttribute('clip-path', 'url(#clip-boundary)');
    g.setAttribute('stroke', gridColor);
    g.setAttribute('stroke-width', '0.5');
    g.setAttribute('fill', 'none');
    g.setAttribute('opacity', '0.6');

    (grid.cells || []).forEach(cell => {
      const pts = cell.corners_frac.map(([xf, yf]) =>
        `${cx + xf * bbox.w},${cy + yf * bbox.h}`
      ).join(' ');
      const poly = document.createElementNS(ns, 'polygon');
      poly.setAttribute('points', pts);
      g.appendChild(poly);
    });

    svg.appendChild(g);
  }
};

// Bind to window for global access from main.js
window.Engine2D = Engine2D;
window.renderRemixSVG = () => Engine2D.render();