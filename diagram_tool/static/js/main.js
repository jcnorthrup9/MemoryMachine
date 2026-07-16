/**
 * MEMORY MACHINE // DIAGRAM TOOL // MAIN CONTROLLER
 *
 * Forked 2026-07-14 from static/main.js (the original Digital Palimpsest
 * app) into a standalone, 2D-only diagram-authoring tool. Pershing
 * Metabolizer already owns all 3D work, so the entire Three.js scene, the
 * AI-hallucinate/ComfyUI/Blender generate() pipeline, and the Mermaid
 * narrative diagram were dropped -- this tool only does: pick a
 * Rhino-exported zone layer, arrange it via sliders, see the HUD stats,
 * export the result as a solid-fill SVG. No freehand drawing (the original
 * app never had any either -- "drawing" always meant placing/transforming
 * a pre-made Rhino layer).
 *
 * Also dropped: /api/available-sites + its dropdown wiring -- the site
 * picker (#picker-site) is a fixed 4-option <select> in index.html and was
 * never actually populated from that endpoint in the live app either
 * (that endpoint only fed a #load-svg-dropdown element that doesn't exist
 * in the current index.html).
 */

// ── STACK EDITOR ─────────────────────────────────────────────────────────────
// Guidelines fetched from /api/guidelines on boot.
// Shape: { SOFT: {min,max}, HARD: {min,max}, PROG: {min,max}, BLUE: {min,max} }
let _guidelines = {
  SOFT:  { min: 30, max: 50 },
  SHADE: { min: 10, max: 25 },
  HARD:  { min: 40, max: 60 },
  PROG:  { min: 10, max: 20 },
  BLUE:  { min:  2, max: 10 },
};

/** Re-render the stack list and refresh HUD after any mutation. */
function refreshStackUI() {
  const list    = document.getElementById('stack-list');
  const counter = document.getElementById('stack-count');
  if (!list) return;

  const stack = MemoryState.stack;
  const visibleItems = stack.filter(i => !i.locked);
  counter.textContent = `${visibleItems.length} LAYER${visibleItems.length !== 1 ? 'S' : ''}`;

  if (visibleItems.length === 0) {
    list.innerHTML = '<div class="stack-empty">No layers placed yet.</div>';
    document.getElementById('xform-panel').style.display = 'none';
    updateHUD();
    return;
  }

  const SITE_LABELS = {
    PershingSquare:    'Pershing Square',
    GardensBytheBay:   'Gardens by the Bay',
    ParcVillette:      'Parc de la Villette',
    ZaryadyePark:      'Zaryadye Park',
    Schouwburgplein:   'Schouwburgplein',
  };

  list.innerHTML = visibleItems.map(item => {
    const siteName  = SITE_LABELS[item.site] || item.site;
    const eyeIcon   = item.visible !== false ? '👁' : '◌';
    const dimClass  = item.visible !== false ? '' : ' hidden-layer';
    const lockClass = item.locked ? ' locked-layer' : '';
    const rightEl   = item.locked
      ? `<span class="stack-lock-icon" title="Base context — locked">⬡</span>`
      : `<button class="stack-eye-btn" data-id="${item.id}" title="Toggle visibility">${eyeIcon}</button>`;
    return `
    <div class="stack-item${MemoryState.editingId === item.id ? ' selected' : ''}${dimClass}${lockClass}"
         data-id="${item.id}">
      <span class="stack-swatch" style="background:${item.color}"></span>
      <div class="label-wrap" style="display:flex; flex-direction:column; flex-grow:1; margin-left: 8px;">
          <span class="stack-item-label" style="margin-left:0;">${siteName} — ${item.layerId}</span>
      </div>
      ${rightEl}
    </div>`;
  }).join('');

  list.querySelectorAll('.stack-item').forEach(el => {
    el.addEventListener('click', e => {
      // Don't open xform panel when clicking the eye toggle or on locked items
      if (e.target.classList.contains('stack-eye-btn')) return;
      const id   = parseInt(el.dataset.id);
      const item = MemoryState.stack.find(i => i.id === id);

      if (item?.locked) {
        setStatus(`${item.layerId} is locked as base context.`, 'info');
        return;
      }

      if (MemoryState.editingId === id) {
        MemoryState.editingId = null;
        document.getElementById('xform-panel').style.display = 'none';
      } else {
        if (!item) return;
        MemoryState.editingId = id;
        openXformPanel(item);
      }
      refreshStackUI(); // re-render to update .selected class
    });
  });

  list.querySelectorAll('.stack-eye-btn').forEach(btn => {
    btn.addEventListener('click', e => {
      e.stopPropagation();
      const id   = parseInt(btn.dataset.id);
      const item = MemoryState.stack.find(i => i.id === id);
      if (!item) return;
      item.visible = item.visible === false ? true : false;
      window.renderRemixSVG?.();
      refreshStackUI();
    });
  });

  updateHUD();
}

/** Populate and show the transform slider panel for a given stack item. */
function openXformPanel(item) {
  const panel = document.getElementById('xform-panel');
  panel.style.display = 'block';
  document.getElementById('xform-title').textContent =
    `${item.layerId} / ${item.site}`;

  const t = item.transform;
  _setSlider('xform-x',     'xform-x-val',     t.x,           v => Math.round(v));
  _setSlider('xform-y',     'xform-y-val',     t.y,           v => Math.round(v));
  _setSlider('xform-scale', 'xform-scale-val', t.scale * 100, v => (v / 100).toFixed(2));
  _setSlider('xform-rot',   'xform-rot-val',   t.rot,         v => Math.round(v) + '°');
}

function _setSlider(sliderId, valId, value, fmt) {
  const el = document.getElementById(sliderId);
  const inputEl = document.getElementById(valId);
  if (el)  el.value = value;
  if (inputEl) inputEl.value = fmt(value);
}

/** Wire all four sliders to mutate the editing item and re-render. */
function _wireSliders() {
  function bind(sliderId, valId, prop, parseFromSlider, parseFromInput, fmtSlider, fmtInput) {
    const slider = document.getElementById(sliderId);
    const inputBox = document.getElementById(valId);
    if (!slider || !inputBox) return;

    slider.addEventListener('input', () => {
      const item = MemoryState.stack.find(i => i.id === MemoryState.editingId);
      if (!item) return;
      item.transform[prop] = parseFromSlider(slider.value);
      inputBox.value = fmtInput(item.transform[prop]);
      window.renderRemixSVG?.();
      updateHUD();
    });

    inputBox.addEventListener('change', () => {
      const item = MemoryState.stack.find(i => i.id === MemoryState.editingId);
      if (!item) return;
      let val = parseFromInput(inputBox.value);
      if (isNaN(val)) return;
      item.transform[prop] = val;
      slider.value = fmtSlider(val);
      window.renderRemixSVG?.();
      updateHUD();
    });
  }
  bind('xform-x',     'xform-x-val',     'x',     v => parseFloat(v),       v => parseFloat(v), v => Math.round(v),       v => Math.round(v));
  bind('xform-y',     'xform-y-val',     'y',     v => parseFloat(v),       v => parseFloat(v), v => Math.round(v),       v => Math.round(v));
  bind('xform-scale', 'xform-scale-val', 'scale', v => parseFloat(v) / 100, v => parseFloat(v), v => v * 100,             v => v.toFixed(2));
  bind('xform-rot',   'xform-rot-val',   'rot',   v => parseFloat(v),       v => parseFloat(v), v => Math.round(v),       v => Math.round(v));
}

// ── ZONAL CONSTRAINTS HUD ────────────────────────────────────────────────────
// RAF handle — ensures HUD DOM writes are batched to one per display frame
// even if updateHUD() is called many times during a single slider drag.
let _hudRafId = null;

function updateHUD() {
  if (_hudRafId) return; // already scheduled for this frame
  _hudRafId = requestAnimationFrame(() => {
    _hudRafId = null;
    _flushHUD();
  });
}

function _flushHUD() {
  const stats = MemoryState.getProgramStats();
  (['SOFT', 'HARD', 'PROG', 'BLUE']).forEach(key => {
    const pct   = stats[key] ?? 0;
    const g     = _guidelines[key];
    const row   = document.getElementById(`hud-${key}`);
    const bar   = document.getElementById(`hud-bar-${key}`);
    const pctEl = document.getElementById(`hud-pct-${key}`);
    const tgtEl = document.getElementById(`hud-tgt-${key}`);
    if (!row) return;

    if (pctEl) pctEl.textContent = `${Math.round(pct)}%`;
    if (tgtEl && g) tgtEl.textContent = `${g.min}–${g.max}%`;
    if (bar)  bar.style.width = Math.min(pct, 100) + '%';

    row.classList.remove('hud-ok', 'hud-warn', 'hud-over');
    if (pct === 0) { /* idle — no class */ }
    else if (pct > (g?.max ?? 100)) row.classList.add('hud-over');
    else if (pct < (g?.min ?? 0))   row.classList.add('hud-warn');
    else                             row.classList.add('hud-ok');
  });
}

// ── EXPORT LOGIC ─────────────────────────────────────────────────────────────
// SVG only -- the original app's JPG export (canvas rasterization of the
// SVG) is exactly what caused Pershing Metabolizer's color-classification
// bug (see engine2D.js's 2026-07-14 comment): rasterizing a small canvas
// dilutes/anti-aliases exact fill colors into something a pixel-color
// classifier can no longer reliably match. Metabolizer now parses this
// tool's SVG output directly (exact fill attributes + coordinates), so
// there's no reason to ever rasterize again.
async function handleExport() {
  const svgEl = document.querySelector('#remix-svg-container svg');
  if (!svgEl) {
    setStatus('No SVG to export', 'error');
    return;
  }

  setStatus('Exporting to server...', 'running');
  const clone = svgEl.cloneNode(true);

  // Keep the live viewBox Engine2D.render() already computed correctly
  // (boundary bbox + 20% padding) -- previously this was overwritten with
  // a hardcoded "0 0 1224 792" on the wrong assumption that it matched the
  // site SVG's native coordinate space. Confirmed 2026-07-16 it doesn't:
  // the real precedent SVGs use a 0 0 2592 1728 canvas, and Pershing
  // Square's BOUNDARY spans x:624-1548, y:314-1305 -- nowhere near fitting
  // inside 1224x792, so every export was silently cropping most of the
  // site (verified by rendering an actual exported file standalone).
  // ingest_diagram_svg.py's rectification math is unaffected either way --
  // it reads raw path/d coordinates directly, never the viewBox -- but any
  // real SVG viewer (browser, Illustrator, Rhino import) clips to it, so
  // the exported file needs a viewBox that actually contains its content.
  // Explicit width/height (1:1 with viewBox units) give the file a sane
  // physical size when opened standalone, without a second bbox pass.
  const vb = (clone.getAttribute('viewBox') || '').trim().split(/\s+/).map(Number);
  if (vb.length === 4 && vb.every(n => !isNaN(n))) {
    clone.setAttribute('width', String(vb[2]));
    clone.setAttribute('height', String(vb[3]));
  }

  const bgFill = '#050505';
  const ctxLine = '#444444';
  const bndLine = '#ffffff';

  clone.style.background = bgFill;

  clone.querySelectorAll('.blackout-mask path, .blackout-mask polygon, .blackout-mask rect, .blackout-mask circle').forEach(p => {
    p.setAttribute('fill', bgFill); p.style.fill = bgFill;
  });

  clone.querySelectorAll('.context-group path, .context-group polyline, .context-group line, .context-group polygon, .context-group rect, .context-group circle').forEach(p => {
    p.setAttribute('stroke', ctxLine); p.style.stroke = ctxLine;
  });

  clone.querySelectorAll('.boundary-group path, .boundary-group polyline, .boundary-group polygon, .boundary-group line, .boundary-group rect').forEach(p => {
    p.setAttribute('stroke', bndLine); p.style.stroke = bndLine;
  });

  clone.querySelectorAll('.intervention-group path, .intervention-group polyline, .intervention-group line, .intervention-group polygon, .intervention-group rect, .intervention-group circle').forEach(p => {
    // Restore the true zone color (engine2D.js already leaves this solid,
    // no fill-opacity, but re-assert here in case a light-mode preview was
    // active when exporting).
    const origCol = p.getAttribute('data-orig-color');
    if (origCol) {
      p.setAttribute('stroke', origCol); p.style.stroke = origCol;
      const currentFill = p.getAttribute('fill');
      if (currentFill && currentFill !== 'none') {
        p.setAttribute('fill', origCol); p.style.fill = origCol;
      }
    }
    p.removeAttribute('fill-opacity');
    p.style.fillOpacity = '';
  });

  const svgData = new XMLSerializer().serializeToString(clone);
  const timestamp = Date.now();

  try {
    const res = await fetch('/api/export-diagram', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        filename: `site_diagram_${timestamp}.svg`,
        data: svgData,
      })
    });
    if (res.ok) setStatus('Exported SVG successfully', 'success');
    else throw new Error('Backend export failed');
  } catch (e) {
    setStatus('Export failed: ' + e.message, 'error');
  }
}

// ── LAYER COLOR UTILITY ──────────────────────────────────────────────────────
/**
 * Single source of truth for Rhino layer colors, both for the on-screen
 * stack/HUD and for the exported SVG's fill attributes. These are also
 * Pershing Metabolizer's canonical zone colors (paintCategories.js) --
 * hardscape gray in particular was reconciled 2026-07-14 to match this
 * exact value, replacing paintCategories.js's previous unrelated blue.
 */
function _getLayerColor(layerId) {
  const id = (layerId || '').toUpperCase();
  // SHADE must be checked BEFORE the GREEN branch below: id.includes('SHADE')
  // would otherwise piggyback on the GREEN branch and render identically to
  // GREEN_SPACE.
  //
  // MAJOR_ATTRACTOR/MINOR_ATTRACTOR checked as their own full substrings
  // (2026-07-14) -- previously both fell into one combined 'ATTRACTOR'
  // branch and rendered identically, but the real Rhino data uses two
  // distinct, deliberate colors for them (confirmed via direct inspection
  // of data/PershingMetabolizer/parkSVG/PrecedentSVG/*.svg). UNIQUE_ELEMENTS
  // keeps the old shared orange now that MAJOR/MINOR have their own.
  if (id.includes('SHADE'))           return '#BCAAA4';
  if (id.includes('AMPHITHEATRE'))    return '#BFBFFF';
  if (id.includes('MAJOR_ATTRACTOR')) return '#FA6D6D';
  if (id.includes('MINOR_ATTRACTOR')) return '#FAB16A';
  if (id.includes('UNIQUE'))          return '#FF9800';
  if (id.includes('GREEN'))           return '#4CAF50';
  if (id.includes('WATER'))           return '#03A9F4';
  if (id.includes('BUILDING'))        return '#696969';
  if (id.includes('HARDSCAPE'))       return '#9E9E9E';
  return '#9E9E9E'; // STREET, PATH, BOUNDARY, PARKING, FURNITURE, INFRASTRUCTURE_CONNECTIONS, etc.
}

// ── BASE CONTEXT INJECTION ────────────────────────────────────────────────────
/**
 * Injects locked base Pershing Square layers as "identity seed" items.
 * These items are rendered by engine2D as context (not as interventions)
 * and give the HUD a real HARD baseline even before any layer is placed.
 */
function _injectBaseContext() {
  const BASE_LAYERS = [
    'BOUNDARY', 'STREET', 'PARKING', 'PEDESTRIAN_PATH', 'STREET_FURNITURE'
  ];
  MemoryState.stack = MemoryState.stack.filter(i => !i.contextLayer);
  MemoryState.baseCleared = false;

  const now = Date.now();
  BASE_LAYERS.forEach((layerId, idx) => {
    MemoryState.stack.unshift({
      id: now + idx,
      site: 'PershingSquare',
      layerId,
      color: _getLayerColor(layerId),
      label: layerId,
      visible: true,
      locked: true,
      contextLayer: true,
      transform: { x: 0, y: 0, scale: 1.0, rot: 0 }
    });
  });

  window.renderRemixSVG?.();
  refreshStackUI();
}

// ── MANUAL LAYER PICKER ───────────────────────────────────────────────────────
// 2026-07-14: added AMPHITHEATRE/BUILDINGS/HARDSCAPE/INFRASTRUCTURE_CONNECTIONS
// after inspecting the real Rhino SVG exports at data/PershingMetabolizer/
// parkSVG/PrecedentSVG/ -- these are real layer ids present in that data
// that the original 11-entry list (inherited from the old Digital
// Palimpsest app) never recognized, silently making that content
// unpickable. AMPHITHEATRE in particular is the real name for the violet
// circle category (not "outdoor auditorium", an invented placeholder from
// earlier discussion -- the source data already had a name for it).
const KNOWN_LAYERS = [
  'BOUNDARY', 'GREEN_SPACE', 'SHADE', 'WATER_FEATURES',
  'STREET', 'PEDESTRIAN_PATH', 'MAJOR_ATTRACTORS',
  'MINOR_ATTRACTORS', 'UNIQUE_ELEMENTS', 'STREET_FURNITURE', 'PARKING',
  'AMPHITHEATRE', 'BUILDINGS', 'HARDSCAPE', 'INFRASTRUCTURE_CONNECTIONS',
];

/**
 * Fetches SVG for siteId, scans g[id] elements for known layer IDs,
 * and populates the picker-layer dropdown.
 */
async function _populateLayerPicker(siteId) {
  const layerSelect = document.getElementById('picker-layer');
  const addBtn      = document.getElementById('picker-add-btn');
  if (!layerSelect || !addBtn) return;

  layerSelect.innerHTML = '<option value="">— loading… —</option>';
  layerSelect.disabled = true;
  addBtn.disabled = true;

  try {
    const svgText = await fetchSVG(siteId);
    const parser  = new DOMParser();
    const doc     = parser.parseFromString(svgText, 'image/svg+xml');
    const found   = [];

    doc.querySelectorAll('g[id]').forEach(g => {
      const gId = g.getAttribute('id') || '';
      const match = KNOWN_LAYERS.find(l => gId.toUpperCase().includes(l));
      if (match && !found.includes(match)) found.push(match);
    });

    const options = found.length > 0 ? found : KNOWN_LAYERS;
    layerSelect.innerHTML = '<option value="">— layer —</option>' +
      options.map(l => `<option value="${l}">${l.replace(/_/g,' ')}</option>`).join('');
    layerSelect.disabled = false;
  } catch (e) {
    layerSelect.innerHTML = '<option value="">— error —</option>';
  }
}

function _wireLayerPicker() {
  const siteSelect  = document.getElementById('picker-site');
  const layerSelect = document.getElementById('picker-layer');
  const addBtn      = document.getElementById('picker-add-btn');
  if (!siteSelect || !layerSelect || !addBtn) return;

  siteSelect.addEventListener('change', () => {
    _populateLayerPicker(siteSelect.value);
  });

  layerSelect.addEventListener('change', () => {
    addBtn.disabled = !layerSelect.value;
  });

  addBtn.addEventListener('click', () => {
    const siteId  = siteSelect.value;
    const layerId = layerSelect.value;
    if (!siteId || !layerId) return;

    MemoryState.stack.push({
      id:            Date.now(),
      site:          siteId,
      layerId,
      color:         _getLayerColor(layerId),
      label:         layerId,
      visible:       true,
      locked:        false,
      contextLayer:  false,
      transform:     { x: 0, y: 0, scale: 1.0, rot: 0 }
    });

    fetchSVG(siteId).then(() => {
      window.renderRemixSVG?.();
      refreshStackUI();
      setStatus(`Added ${layerId} from ${siteId}`, 'success');
    }).catch(err => setStatus('SVG load failed: ' + err.message, 'error'));

    layerSelect.value = '';
    addBtn.disabled = true;
  });

  _populateLayerPicker(siteSelect.value);
}

// ── SVG LOADING ──────────────────────────────────────────────────────────────
async function fetchSVG(siteId) {
  if (MemoryState.svgCache[siteId]) return MemoryState.svgCache[siteId];
  setStatus('Fetching ' + siteId + '...', 'running');
  const res  = await fetch(`/api/diagram-data/${siteId}`);
  const data = await res.json();
  if (data.error) throw new Error(data.error);
  MemoryState.svgCache[siteId] = data.svg;
  return data.svg;
}

// ── INIT ─────────────────────────────────────────────────────────────────────
async function init() {
  // ── Fetch urban design guidelines ────────────────────────────────────────
  try {
    const res  = await fetch('/api/guidelines');
    const data = await res.json();
    const g = data.guidelines || data;
    const remap = {
      Softscape:  'SOFT',
      Hardscape:  'HARD',
      Active:     'PROG',
      Blue_Space: 'BLUE',
      SOFT: 'SOFT', HARD: 'HARD', PROG: 'PROG', BLUE: 'BLUE',
    };
    Object.entries(g).forEach(([k, v]) => {
      const key = remap[k];
      if (key && v?.min !== undefined) _guidelines[key] = { min: v.min, max: v.max };
    });
    updateHUD();
  } catch (e) {
    console.warn('Could not load guidelines — using defaults.', e);
  }

  _wireSliders();

  // Load Pershing Square SVG as default base, then inject identity seed
  try {
    await fetchSVG('PershingSquare');
    _injectBaseContext();
    setStatus('Site loaded — Pershing Square, DTLA', 'success');
  } catch (e) {
    setStatus('SVG load error: ' + e.message, 'error');
  }

  _wireLayerPicker();

  document.getElementById('export-btn')?.addEventListener('click', handleExport);

  document.getElementById('clear-stack-btn')?.addEventListener('click', () => {
    MemoryState.clear();
    _injectBaseContext();
    refreshStackUI();
    window.renderRemixSVG?.();
    setStatus('Stack cleared.', 'success');
  });

  document.getElementById('theme-toggle')?.addEventListener('click', () => {
    document.body.classList.toggle('light-mode');
    window.renderRemixSVG?.();
  });
}

document.addEventListener('DOMContentLoaded', init);
