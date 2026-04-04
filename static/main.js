// ─────────────────────────────────────────────────────────────────────────────
// Task 11: MemoryState — single source of truth
// ─────────────────────────────────────────────────────────────────────────────
const SITES = ['PershingSquare', 'ParcdelaVillette', 'ZaryadyePark', 'Schouwburgplein'];

const SITE_LABELS = {
  PershingSquare:   'Pershing Square',
  ParcdelaVillette: 'Parc de la Villette',
  ZaryadyePark:     'Zaryadye Park',
  Schouwburgplein:  'Schouwburgplein',
};

// Layers to expose for toggling, with display colors.
// `splitFrom` + `splitSW` mark a virtual layer extracted from another by stroke-width.
// `excludeSW`  tells the source layer to drop those same paths when it renders.
const TARGET_LAYERS = [
  { id: 'BOUNDARY',        label: 'Boundary',    color: '#ffffff' },
  { id: 'GREEN_SPACE',     label: 'Green Space', color: '#00cc66' },
  { id: 'SHADE',           label: 'Shade',       color: '#88bb44' },
  { id: 'WATER_FEATURES',  label: 'Water',       color: '#4488ff' },
  { id: 'STREET',          label: 'Streets',     color: '#888888' },
  { id: 'PEDESTRIAN_PATH', label: 'Paths',       color: '#ccaa66' },
  { id: 'MAJOR_ATTRACTORS',label: 'Attractors',  color: '#ff8833' },
  { id: 'MINOR_ATTRACTORS',label: 'Minor Attr.', color: '#ff6666' },
  { id: 'UNIQUE_ELEMENTS', label: 'Unique',      color: '#cc88ff' },
  { id: 'STREET_FURNITURE',label: 'Hardscape',   color: '#aaaaaa' },
  { id: 'PARKING',         label: 'Parking',     color: '#666688' },
];

// Layer extrusion heights (in Three.js units ~= feet)
// Base site context layers rendered behind the stack in both live view and export.
// Keep this list as the single source of truth — never add to one function without the other.
const SITE_CONTEXT_LAYERS = ['BUILDINGS', 'BUILDINGS::hatch', 'STREET', 'PARKING', 'INFRASTRUCTURE_CONNECTIONS'];

const LAYER_HEIGHT = {
  BOUNDARY:        0.2,
  GREEN_SPACE:     0.5,
  SHADE:           0.1,
  WATER_FEATURES:  0.3,
  STREET:          0.1,
  PEDESTRIAN_PATH: 0.15,
  MAJOR_ATTRACTORS:3.0,
  MINOR_ATTRACTORS:1.5,
  UNIQUE_ELEMENTS: 4.0,
  STREET_FURNITURE:1.0,
  PARKING:         0.1,
};

const MemoryState = {
  activeView:     '2d',
  lastGeneration: null,
  svgCache:       {},          // site → raw SVG string
  stack:          [],          // [{ id, site, layerId, color, label, visible, transform }]
  editingId:      null,        // which stack item's transform we're currently editing
  transform:      { x: 0, y: 0, scale: 1.0, rot: 0 },  // staging transform for next add / live edit
  dreamMode:      false,       // false = Draft (fast extrusion), true = Dream (ComfyUI AI mesh)
};

// ── Status helper ────────────────────────────────────────────────────────────
function setStatus(msg, state) {
  const bar = document.getElementById('status-bar');
  bar.className = state || '';
  document.getElementById('status-text').textContent = msg;
}

// ── Light / dark mode ────────────────────────────────────────────────────────
function toggleTheme() {
  const light = document.body.classList.toggle('light-mode');
  document.getElementById('theme-toggle').textContent = light ? '☾' : '☀';
  if (threeScene)   threeScene.background = new THREE.Color(light ? 0xffffff : 0x050505);
  // Re-render the 2D SVG so its inline bg rect picks up the new colour
  renderRemixSVG();
}

// ── Global Portal Switching ──────────────────────────────────────────────────
function switchGlobalView(target, btn) {
  document.querySelectorAll('.global-tab').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  
  const appDiv = document.getElementById('app');
  const frame = document.getElementById('portal-frame');
  
  if (target === 'app') {
    frame.style.display = 'none';
    appDiv.style.display = 'grid';
    frame.src = '';
  } else {
    appDiv.style.display = 'none';
    frame.style.display = 'block';
    if (!frame.src.endsWith(target)) frame.src = target;
  }
}

// ── Shared 3D line builder — converts SVG path d to THREE.Line at elevation y ─
// cx/cy are the SVG-space center to place at world origin. scale = SVG_SCALE * ts.
function pathTo3DLines(gEl, cx, cy, scale, elevation, color, scene) {
  if (!gEl) return 0;
  const mat = new THREE.LineBasicMaterial({ color });
  let count = 0;
  gEl.querySelectorAll('path,line,polyline').forEach(el => {
    const d = el.getAttribute('d');
    if (!d) return;
    // Extract all coordinate pairs — works for Rhino's M x,y L x,y segments
    const nums = [];
    const re = /(-?\d+\.?\d*(?:[eE][+-]?\d+)?)/g;
    let m;
    while ((m = re.exec(d)) !== null) nums.push(parseFloat(m[1]));
    const pts = [];
    for (let i = 0; i + 1 < nums.length; i += 2) {
      pts.push(new THREE.Vector3(
        (nums[i]   - cx) * scale,
        elevation,
        (nums[i+1] - cy) * scale
      ));
    }
    if (pts.length < 2) return;
    scene.add(new THREE.Line(new THREE.BufferGeometry().setFromPoints(pts), mat));
    count++;
  });
  return count;
}

// ── Tab switching ────────────────────────────────────────────────────────────
function switchTab(name, btn) {
  document.querySelectorAll('.tab-pane').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
  document.getElementById('tab-' + name).classList.add('active');
  btn.classList.add('active');
  if (name === 'canvas') {
    if (!threeRenderer) {
      // Defer so the tab pane is visible and the canvas has real layout dimensions
      setTimeout(() => {
        initSceneShell();
        buildPershingContext();
      }, 100);
    } else {
      const canvas = document.getElementById('three-canvas');
      threeRenderer.setSize(canvas.offsetWidth, canvas.offsetHeight);
    }
  }
}

// Task 11: view toggle
function setView(view) {
  MemoryState.activeView = view;
  document.getElementById('btn-view-2d').classList.toggle('active', view === '2d');
  const btn = document.getElementById('generate-btn');
  btn.textContent = view === '2d' ? 'Bake Diagram ▾' : 'Generate Intervention';
  const tabs = document.querySelectorAll('.tab-btn');
  if (view === '2d') { tabs[0].click(); } else { tabs[1].click(); }
}


function setDreamMode(on) {
  MemoryState.dreamMode = on;
  document.getElementById('btn-mode-draft').classList.toggle('active', !on);
  document.getElementById('btn-mode-dream').classList.toggle('active',  on);
  document.getElementById('deploy-btn').textContent = on
    ? '\u2726 Dream to 3D'
    : '\u25C6 Deploy to 3D';
}

// Task 16 — compute real-world footprint for each visible stack item.
// Returns an array ready to POST to /api/generate-3d.
function extractFootprints() {
  const baseSVGEl = parseSVG(MemoryState.svgCache['PershingSquare'] || '');
  const bbox      = getBoundaryBBox(baseSVGEl);
  if (!bbox) return [];

  const footprints = [];
  MemoryState.stack.forEach(item => {
    if (!item.visible) return;
    const siteSVG = MemoryState.svgCache[item.site];
    if (!siteSVG) return;
    const precEl = parseSVG(siteSVG);
    const precVB = getViewBox(precEl);

    const t        = item.transform;
    const fitScale = Math.min(bbox.w / precVB.w, bbox.h / precVB.h);
    const ts       = fitScale * t.scale;

    // Center of this layer in Three.js world coords (mirrors deployTo3D transform)
    const bboxCx3d = (bbox.x + bbox.w / 2) * SVG_SCALE;
    const bboxCy3d = (bbox.y + bbox.h / 2) * SVG_SCALE;
    const cx       = bboxCx3d + t.x * SVG_SCALE;
    const cz       = bboxCy3d + t.y * SVG_SCALE;

    // Approximate footprint from scaled viewBox dimensions
    const width  = precVB.w * ts * SVG_SCALE;
    const depth  = precVB.h * ts * SVG_SCALE;
    const rotRad = t.rot * Math.PI / 180;

    footprints.push({
      site:    item.site,
      layerId: item.layerId,
      label:   item.label,
      color:   item.color,
      footprint: { cx, cz, width, depth, rotRad },
    });
  });
  return footprints;
}

// ── Export dropdown ──────────────────────────────────────────────────────────
function handlePrimaryAction() {
  if (MemoryState.activeView === '2d') {
    const dd = document.getElementById('export-dropdown');
    dd.classList.toggle('open');
  } else {
    generate();
  }
}
function closeExportDropdown() {
  document.getElementById('export-dropdown')?.classList.remove('open');
}
// (export dropdown close handled by closeAllDropdowns in save/load section)

function timestamp() {
  const d = new Date();
  return `${d.getFullYear()}${String(d.getMonth()+1).padStart(2,'0')}${String(d.getDate()).padStart(2,'0')}_${String(d.getHours()).padStart(2,'0')}${String(d.getMinutes()).padStart(2,'0')}`;
}

// Build a clean export SVG — either color (dark bg) or linework (white bg, original strokes)
function buildExportSVG(mode) {
  const baseSVG = MemoryState.svgCache['PershingSquare'];
  if (!baseSVG) return null;
  const ns = 'http://www.w3.org/2000/svg';
  const baseSVGEl = parseSVG(baseSVG);
  const baseVB    = getViewBox(baseSVGEl);
  const bbox      = getBoundaryBBox(baseSVGEl);
  if (!bbox) return null;

  const isDark = mode === 'color';
  const bgColor      = isDark ? '#050505' : '#ffffff';
  const contextColor = isDark ? '#333333' : '#cccccc';
  const contextStroke= isDark ? '#444444' : '#aaaaaa';
  const boundaryStroke = isDark ? '#ffffff' : '#000000';
  const bboxCx = bbox.x + bbox.w / 2;
  const bboxCy = bbox.y + bbox.h / 2;

  const svg = document.createElementNS(ns, 'svg');
  svg.setAttribute('viewBox', `0 0 ${baseVB.w} ${baseVB.h}`);
  svg.setAttribute('xmlns', ns);
  svg.setAttribute('width', `${baseVB.w}pt`);
  svg.setAttribute('height', `${baseVB.h}pt`);

  const defs = document.createElementNS(ns, 'defs');
  defs.appendChild(buildBoundaryClipPath(baseSVGEl, ns, 'exp-clip'));
  svg.appendChild(defs);

  // Full background
  const bg = document.createElementNS(ns, 'rect');
  bg.setAttribute('x', '0'); bg.setAttribute('y', '0');
  bg.setAttribute('width', baseVB.w); bg.setAttribute('height', baseVB.h);
  bg.setAttribute('fill', bgColor);
  svg.appendChild(bg);

  // Site context: buildings + streets
  SITE_CONTEXT_LAYERS.forEach(lid => {
    const g = baseSVGEl.querySelector(`[id="${lid}"]`);
    if (!g) return;
    const c = g.cloneNode(true);
    c.querySelectorAll('[id*="entrances"], [id*="Entrances"]').forEach(el => el.remove());
    c.querySelectorAll('[stroke]:not([stroke="none"])').forEach(el => el.setAttribute('stroke', '#888888'));
    c.querySelectorAll('[fill]:not([fill="none"])').forEach(el => el.setAttribute('fill', '#aaaaaa'));
    c.style.opacity = '0.75';
    svg.appendChild(c);
  });

  // Stack layers
  MemoryState.stack.forEach(item => {
    if (!item.visible) return;
    const siteSVG = MemoryState.svgCache[item.site];
    if (!siteSVG) return;
    const precEl  = parseSVG(siteSVG);
    const precVB  = getViewBox(precEl);
    const layerDef = TARGET_LAYERS.find(l => l.id === item.layerId) || { color: item.color };
    const resolved = resolveLayerGroup(layerDef, precEl, ns);
    if (!resolved) return;

    const t = item.transform;
    const fitScale   = Math.min(bbox.w / precVB.w, bbox.h / precVB.h);
    const ts         = fitScale * t.scale;
    const precCx     = precVB.x + precVB.w / 2;
    const precCy     = precVB.y + precVB.h / 2;
    const xformStr   = [
      `translate(${bboxCx + t.x},${bboxCy + t.y})`,
      `rotate(${t.rot})`,`scale(${ts})`,`translate(${-precCx},${-precCy})`,
    ].join(' ');

    const wrapper = document.createElementNS(ns, 'g');
    wrapper.setAttribute('clip-path', 'url(#exp-clip)');
    const xformed = document.createElementNS(ns, 'g');
    xformed.setAttribute('transform', xformStr);

    if (isDark) {
      // Color mode: override strokes with layer color
      resolved.querySelectorAll('[stroke]:not([stroke="none"])').forEach(el => el.setAttribute('stroke', item.color));
      resolved.querySelectorAll('[fill]:not([fill="none"])').forEach(el => el.setAttribute('fill', item.color));
    }
    // Linework mode: keep original Rhino strokes/lineweights

    xformed.appendChild(resolved);
    wrapper.appendChild(xformed);
    svg.appendChild(wrapper);
  });

  // BOUNDARY on top
  const bndG = baseSVGEl.querySelector('g[id="BOUNDARY"]');
  if (bndG) {
    const bClone = bndG.cloneNode(true);
    const sw = Math.max(0.3, bbox.w * 0.001);
    bClone.querySelectorAll('path').forEach(p => {
      p.setAttribute('stroke', boundaryStroke);
      p.setAttribute('stroke-width', sw);
      p.setAttribute('fill', 'none');
    });
    svg.appendChild(bClone);
  }

  return svg;
}

function exportSVG(mode) {
  closeExportDropdown();
  const svg = buildExportSVG(mode);
  if (!svg) { setStatus('Nothing to export yet.', 'error'); return; }
  const str = '<?xml version="1.0" encoding="utf-8"?>\n' + new XMLSerializer().serializeToString(svg);
  const blob = new Blob([str], { type: 'image/svg+xml' });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = `pershing_remix_${mode}_${timestamp()}.svg`;
  a.click();
  URL.revokeObjectURL(a.href);
  setStatus(`SVG exported (${mode})`, 'success');
}

function exportJPEG(mode) {
  closeExportDropdown();
  const svg = buildExportSVG(mode);
  if (!svg) { setStatus('Nothing to export yet.', 'error'); return; }
  setStatus('Rendering JPEG...', 'running');

  // 17"×11" @ 200dpi
  const W = 3400, H = 2200;
  const svgStr = new XMLSerializer().serializeToString(svg);
  const blob   = new Blob([svgStr], { type: 'image/svg+xml;charset=utf-8' });
  const url    = URL.createObjectURL(blob);
  const img    = new Image();
  img.onload = () => {
    const canvas = document.createElement('canvas');
    canvas.width = W; canvas.height = H;
    const ctx = canvas.getContext('2d');
    ctx.fillStyle = mode === 'color' ? '#050505' : '#ffffff';
    ctx.fillRect(0, 0, W, H);
    ctx.drawImage(img, 0, 0, W, H);
    canvas.toBlob(b => {
      const a = document.createElement('a');
      a.href = URL.createObjectURL(b);
      a.download = `pershing_remix_${mode}_${timestamp()}.jpg`;
      a.click();
      URL.revokeObjectURL(a.href);
      setStatus(`JPEG exported (${mode}, 3400×2200)`, 'success');
    }, 'image/jpeg', 0.95);
    URL.revokeObjectURL(url);
  };
  img.onerror = () => setStatus('JPEG render failed — try SVG export', 'error');
  img.src = url;
}

// ─────────────────────────────────────────────────────────────────────────────
// Layer select + transform controls
// ─────────────────────────────────────────────────────────────────────────────
function buildLayerSelect() {
  const sel = document.getElementById('layer-select');
  sel.innerHTML = TARGET_LAYERS.map(l =>
    `<option value="${l.id}" style="color:${l.color}">${l.label}</option>`
  ).join('');
}

function bindXform(id, valId, prop, fmt) {
  document.getElementById(id).addEventListener('input', function () {
    MemoryState.transform[prop] = parseFloat(this.value) / (prop === 'scale' ? 100 : 1);
    document.getElementById(valId).textContent = fmt(MemoryState.transform[prop]);
    // If editing an existing stack item, update it live
    if (MemoryState.editingId !== null) {
      const item = MemoryState.stack.find(i => i.id === MemoryState.editingId);
      if (item) { item.transform = { ...MemoryState.transform }; renderRemixSVG(); }
    }
  });
}
bindXform('xform-x',     'xform-x-val',     'x',     v => Math.round(v));
bindXform('xform-y',     'xform-y-val',     'y',     v => Math.round(v));
bindXform('xform-scale', 'xform-scale-val', 'scale', v => v.toFixed(2) + '×');
bindXform('xform-rot',   'xform-rot-val',   'rot',   v => Math.round(v) + '°');

function setTransformUI(t) {
  document.getElementById('xform-x').value     = t.x;
  document.getElementById('xform-y').value     = t.y;
  document.getElementById('xform-scale').value = Math.round(t.scale * 100);
  document.getElementById('xform-rot').value   = t.rot;
  document.getElementById('xform-x-val').textContent     = Math.round(t.x);
  document.getElementById('xform-y-val').textContent     = Math.round(t.y);
  document.getElementById('xform-scale-val').textContent = t.scale.toFixed(2) + '×';
  document.getElementById('xform-rot-val').textContent   = Math.round(t.rot) + '°';
}

function resetTransform() {
  MemoryState.transform = { x: 0, y: 0, scale: 1.0, rot: 0 };
  MemoryState.editingId = null;
  setTransformUI(MemoryState.transform);
  renderStackUI();
}

function resetAll() {
  MemoryState.stack     = [];
  MemoryState.editingId = null;
  MemoryState.currentCompositionName = null;
  MemoryState.transform = { x: 0, y: 0, scale: 1.0, rot: 0 };
  setTransformUI(MemoryState.transform);
  renderStackUI();
  renderRemixSVG();
  updateInfoTabs();
  autosave();
  setStatus('Stack cleared — Pershing Square base ready.', 'success');
}

// ─────────────────────────────────────────────────────────────────────────────
// Stack management
// ─────────────────────────────────────────────────────────────────────────────
async function addToStack() {
  const site    = document.getElementById('site-select').value;
  const layerId = document.getElementById('layer-select').value;
  const layerDef = TARGET_LAYERS.find(l => l.id === layerId);

  if (!MemoryState.svgCache[site]) {
    setStatus('Fetching SVG...', 'running');
    try {
      MemoryState.svgCache[site] = await fetchSVG(site);
    } catch(e) { setStatus('Fetch error: ' + e.message, 'error'); return; }
  }

  // Verify the layer actually exists in this site's SVG
  const precEl = parseSVG(MemoryState.svgCache[site]);
  if (!precEl.querySelector(`g[id="${layerId}"]`)) {
    setStatus(`Layer ${layerId} not found in ${SITE_LABELS[site]}`, 'error');
    return;
  }

  const item = {
    id:        Date.now(),
    site,
    layerId,
    color:     layerDef.color,
    label:     `${SITE_LABELS[site].replace(' ','\\00a0')} / ${layerDef.label}`,
    visible:   true,
    opacity:   0.85,
    transform: { ...MemoryState.transform },
  };

  MemoryState.stack.push(item);
  MemoryState.editingId = item.id;
  renderStackUI();
  renderRemixSVG();
  updateInfoTabs();
  autosave();
  setStatus(`Added: ${SITE_LABELS[site]} / ${layerDef.label}`, 'success');
}

function removeFromStack(id) {
  MemoryState.stack = MemoryState.stack.filter(i => i.id !== id);
  if (MemoryState.editingId === id) { MemoryState.editingId = null; resetTransform(); }
  renderStackUI();
  renderRemixSVG();
  updateInfoTabs();
  autosave();
}

function toggleVisibility(id) {
  const item = MemoryState.stack.find(i => i.id === id);
  if (item) { item.visible = !item.visible; renderStackUI(); renderRemixSVG(); updateInfoTabs(); autosave(); }
}

function changeOpacity(id, val) {
  const item = MemoryState.stack.find(i => i.id === id);
  if (item) { item.opacity = parseFloat(val); renderRemixSVG(); autosave(); }
}

function selectForEdit(id) {
  const item = MemoryState.stack.find(i => i.id === id);
  if (!item) return;
  MemoryState.editingId = id;
  MemoryState.transform = { ...item.transform };
  setTransformUI(item.transform);
  renderStackUI();
}

function renderStackUI() {
  const list = document.getElementById('stack-list');
  if (MemoryState.stack.length === 0) { list.innerHTML = ''; return; }
  list.innerHTML = MemoryState.stack.map(item => `
    <div class="stack-item${item.id === MemoryState.editingId ? ' active-edit' : ''}"
         onclick="selectForEdit(${item.id})">
      <span class="stack-swatch" style="background:${item.color}"></span>
      <span class="stack-label">${item.label}</span>
      <input class="stack-opacity" type="range" min="0" max="1" step="0.05"
             value="${item.opacity ?? 0.85}"
             title="Opacity"
             onclick="event.stopPropagation()"
             oninput="event.stopPropagation();changeOpacity(${item.id}, this.value)">
      <span class="stack-vis${item.visible ? '' : ' hidden'}"
            onclick="event.stopPropagation();toggleVisibility(${item.id})">&#9679;</span>
      <span class="stack-remove"
            onclick="event.stopPropagation();removeFromStack(${item.id})">&#215;</span>
    </div>`).join('');
}

// ─────────────────────────────────────────────────────────────────────────────
// SVG fetch + cache
// ─────────────────────────────────────────────────────────────────────────────
async function fetchSVG(site) {
  const res = await fetch(`/api/diagram-data/${site}`, { cache: 'no-store' });
  const data = await res.json();
  if (data.error) throw new Error(data.error);
  return data.svg;
}

async function ensureBaseSVG() {
  if (!MemoryState.svgCache['PershingSquare']) {
    MemoryState.svgCache['PershingSquare'] = await fetchSVG('PershingSquare');
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// SVG helpers
// ─────────────────────────────────────────────────────────────────────────────

function parseSVG(svgText) {
  return new DOMParser().parseFromString(svgText, 'image/svg+xml').documentElement;
}

// Scan all numeric tokens in a path `d` attribute to find coordinate extremes.
// Fast approximation — accurate for rectilinear/diagonal paths like these SVGs.
function pathCoordBBox(d) {
  let minX=Infinity, minY=Infinity, maxX=-Infinity, maxY=-Infinity;
  const re = /(-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)/g;
  const nums = []; let m;
  while ((m = re.exec(d)) !== null) nums.push(parseFloat(m[1]));
  for (let i = 0; i < nums.length - 1; i += 2) {
    if (nums[i] < minX) minX = nums[i];   if (nums[i] > maxX) maxX = nums[i];
    if (nums[i+1] < minY) minY = nums[i+1]; if (nums[i+1] > maxY) maxY = nums[i+1];
  }
  return isFinite(minX) ? { minX, minY, maxX, maxY } : null;
}

// Compute the bounding box of the BOUNDARY layer from raw path coordinates.
function getBoundaryBBox(svgEl) {
  const g = svgEl.querySelector('g[id="BOUNDARY"]');
  if (!g) return null;
  let minX=Infinity, minY=Infinity, maxX=-Infinity, maxY=-Infinity;
  g.querySelectorAll('path').forEach(p => {
    const b = pathCoordBBox(p.getAttribute('d') || '');
    if (!b) return;
    if (b.minX < minX) minX = b.minX;  if (b.minY < minY) minY = b.minY;
    if (b.maxX > maxX) maxX = b.maxX;  if (b.maxY > maxY) maxY = b.maxY;
  });
  return isFinite(minX) ? { x: minX, y: minY, w: maxX - minX, h: maxY - minY } : null;
}

// Build a <polygon> that traces the actual BOUNDARY outline for use in a clipPath.
// Collects the first coordinate pair from each path segment in document order —
// since Rhino exports boundary segments sequentially around the perimeter, this
// produces a correctly-ordered polygon that matches the real park shape.
function buildBoundaryClipPath(svgEl, ns, clipId) {
  const g = svgEl.querySelector('g[id="BOUNDARY"]');
  const cp = document.createElementNS(ns, 'clipPath');
  cp.setAttribute('id', clipId);

  if (!g) {
    // Fallback: invisible clip so nothing shows if BOUNDARY is missing
    return cp;
  }

  const re = /(-?\d+\.?\d*(?:[eE][+-]?\d+)?)/g;
  const pts = [];
  g.querySelectorAll('path').forEach(pathEl => {
    const d = pathEl.getAttribute('d') || '';
    const nums = [];
    let m;
    re.lastIndex = 0;
    while ((m = re.exec(d)) !== null) nums.push(parseFloat(m[1]));
    // Take only the first coordinate pair from each segment (the M point)
    if (nums.length >= 2) pts.push([nums[0], nums[1]]);
  });

  if (pts.length < 3) {
    // Too few points — fall back to bbox rect
    const bbox = getBoundaryBBox(svgEl);
    if (bbox) {
      const r = document.createElementNS(ns, 'rect');
      r.setAttribute('x', bbox.x); r.setAttribute('y', bbox.y);
      r.setAttribute('width', bbox.w); r.setAttribute('height', bbox.h);
      cp.appendChild(r);
    }
    return cp;
  }

  const poly = document.createElementNS(ns, 'polygon');
  poly.setAttribute('points', pts.map(p => p.join(',')).join(' '));
  cp.appendChild(poly);
  return cp;
}

// Extract layer <g> elements matching our target layer IDs
function extractLayers(svgEl) {
  const result = {};
  TARGET_LAYERS.forEach(l => {
    const g = svgEl.querySelector(`g[id="${l.id}"]`);
    if (g) result[l.id] = g;
  });
  return result;
}

// Returns a cloned <g> of the paths that belong to this layer definition,
// respecting splitFrom/splitSW and excludeSW rules.
function resolveLayerGroup(layerDef, svgEl, ns) {
  const group = document.createElementNS(ns, 'g');

  if (layerDef.splitFrom) {
    // Virtual layer: pull matching stroke-width paths from the source group
    const srcG = svgEl.querySelector(`g[id="${layerDef.splitFrom}"]`);
    if (!srcG) return null;
    let found = 0;
    srcG.querySelectorAll('path,line,polyline,rect,circle,ellipse').forEach(el => {
      if (el.getAttribute('stroke-width') === layerDef.splitSW) {
        group.appendChild(el.cloneNode(true));
        found++;
      }
    });
    return found ? group : null;
  }

  // Normal layer: clone the <g> but strip excluded stroke-widths
  const srcG = svgEl.querySelector(`g[id="${layerDef.id}"]`);
  if (!srcG) return null;
  const clone = srcG.cloneNode(true);
  if (layerDef.excludeSW) {
    clone.querySelectorAll(`[stroke-width="${layerDef.excludeSW}"]`).forEach(el => el.remove());
  }
  group.appendChild(clone);
  return group;
}

// Get the viewBox from a parsed SVG element
function getViewBox(svgEl) {
  const vb = svgEl.getAttribute('viewBox');
  if (vb) {
    const parts = vb.trim().split(/[\s,]+/).map(Number);
    return { x: parts[0], y: parts[1], w: parts[2], h: parts[3] };
  }
  return {
    x: 0, y: 0,
    w: parseFloat(svgEl.getAttribute('width')) || 1224,
    h: parseFloat(svgEl.getAttribute('height')) || 792,
  };
}


function renderRemixSVG() {
  const baseSVG = MemoryState.svgCache['PershingSquare'];
  if (!baseSVG) return;
  const container = document.getElementById('remix-svg-container');
  const ns = 'http://www.w3.org/2000/svg';

  const baseSVGEl = parseSVG(baseSVG);

  // ── Boundary bbox from PershingSquare BOUNDARY paths ─────────────────────
  const bbox = getBoundaryBBox(baseSVGEl);
  if (!bbox) {
    container.innerHTML = '<p style="color:#ff4444;padding:1rem">BOUNDARY layer not found</p>';
    return;
  }

  const baseVB  = getViewBox(baseSVGEl);
  const bboxCx  = bbox.x + bbox.w / 2;
  const bboxCy  = bbox.y + bbox.h / 2;

  const svg = document.createElementNS(ns, 'svg');
  // Use full original viewBox so buildings/streets show at correct scale
  svg.setAttribute('viewBox', `0 0 ${baseVB.w} ${baseVB.h}`);
  svg.style.cssText = 'width:100%;height:100%;display:block';

  const defs = document.createElementNS(ns, 'defs');
  const clipId = 'clip-boundary';
  defs.appendChild(buildBoundaryClipPath(baseSVGEl, ns, clipId));
  svg.appendChild(defs);

  // Full SVG background
  const bg = document.createElementNS(ns, 'rect');
  bg.setAttribute('x', '0'); bg.setAttribute('y', '0');
  bg.setAttribute('width', baseVB.w); bg.setAttribute('height', baseVB.h);
  bg.setAttribute('fill', document.body.classList.contains('light-mode') ? '#ffffff' : '#050505');
  svg.appendChild(bg);

  // Site context: Pershing Square buildings + streets + parking (minus entrances) + infrastructure
  SITE_CONTEXT_LAYERS.forEach(lid => {
    const g = baseSVGEl.querySelector(`[id="${lid}"]`);
    if (!g) return;
    const c = g.cloneNode(true);
    c.querySelectorAll('[id*="entrances"], [id*="Entrances"]').forEach(el => el.remove());
    c.querySelectorAll('[stroke]:not([stroke="none"])').forEach(el => el.setAttribute('stroke', '#888888'));
    c.querySelectorAll('[fill]:not([fill="none"])').forEach(el => el.setAttribute('fill', '#aaaaaa'));
    c.style.opacity = '0.75';
    svg.appendChild(c);
  });


  // ── Stack items — each clipped to boundary, independent transform ─────────
  MemoryState.stack.forEach(item => {
    if (!item.visible) return;
    const siteSVG = MemoryState.svgCache[item.site];
    if (!siteSVG) return;
    const precEl = parseSVG(siteSVG);
    const precVB = getViewBox(precEl);

    const layerDef = TARGET_LAYERS.find(l => l.id === item.layerId) || { color: item.color };
    const resolved = resolveLayerGroup(layerDef, precEl, ns);
    if (!resolved) return;

    const t        = item.transform;
    const fitScale = Math.min(bbox.w / precVB.w, bbox.h / precVB.h);
    const ts       = fitScale * t.scale;
    const precCx   = precVB.x + precVB.w / 2;
    const precCy   = precVB.y + precVB.h / 2;

    const xformStr = [
      `translate(${bboxCx + t.x},${bboxCy + t.y})`,
      `rotate(${t.rot})`,
      `scale(${ts})`,
      `translate(${-precCx},${-precCy})`,
    ].join(' ');

    const isEditing = item.id === MemoryState.editingId;

    const wrapper = document.createElementNS(ns, 'g');
    wrapper.setAttribute('clip-path', `url(#${clipId})`);
    wrapper.style.opacity = isEditing ? '1' : String(item.opacity ?? 0.85);

    const xformed = document.createElementNS(ns, 'g');
    xformed.setAttribute('transform', xformStr);

    const clone = resolved;
    clone.querySelectorAll('[stroke]').forEach(el => {
      if (el.getAttribute('stroke') !== 'none') el.setAttribute('stroke', item.color);
    });
    clone.querySelectorAll('[fill]').forEach(el => {
      if (el.getAttribute('fill') !== 'none') el.setAttribute('fill', item.color);
    });

    xformed.appendChild(clone);
    wrapper.appendChild(xformed);
    svg.appendChild(wrapper);

    // Highlight bounding box for the item being edited
    if (isEditing) {
      const hl = document.createElementNS(ns, 'rect');
      hl.setAttribute('x', precVB.x); hl.setAttribute('y', precVB.y);
      hl.setAttribute('width', precVB.w); hl.setAttribute('height', precVB.h);
      hl.setAttribute('fill', 'none');
      hl.setAttribute('stroke', item.color);
      hl.setAttribute('stroke-width', `${1.5 / ts}`);
      hl.setAttribute('stroke-dasharray', `${6 / ts},${4 / ts}`);
      const hlWrap = document.createElementNS(ns, 'g');
      hlWrap.setAttribute('transform', xformStr);
      hlWrap.appendChild(hl);
      svg.appendChild(hlWrap);
    }
  });

  // ── BOUNDARY on top — white outline ──────────────────────────────────────
  const bndG = baseSVGEl.querySelector('g[id="BOUNDARY"]');
  if (bndG) {
    const bClone = bndG.cloneNode(true);
    const sw = Math.max(0.3, bbox.w * 0.001);
    bClone.querySelectorAll('path').forEach(p => {
      p.setAttribute('stroke', '#ffffff');
      p.setAttribute('stroke-width', sw);
      p.setAttribute('fill', 'none');
    });
    svg.appendChild(bClone);
  }

  container.innerHTML = '';
  container.appendChild(svg);
}

// ─────────────────────────────────────────────────────────────────────────────
// ─────────────────────────────────────────────────────────────────────────────
function updateRemixInset() { /* lofi inset retired */ }
// ─────────────────────────────────────────────────────────────────────────────
// Task 13: Deploy to 3D — SVG paths → THREE.ExtrudeGeometry
// ─────────────────────────────────────────────────────────────────────────────

let threeRenderer = null, threeScene = null, threeCamera = null, threeAnimId = null;
let cachedSiteContext = null;

// Simple SVG path parser: converts "M x y L x y ... Z" segments to THREE.Shape
function svgPathToShape(dAttr) {
  const shape = new THREE.Shape();
  // tokenize
  const tokens = dAttr.replace(/([MmLlHhVvCcSsQqTtAaZz])/g, ' $1 ').trim().split(/\s+/);
  let i = 0, cx = 0, cy = 0, started = false;
  while (i < tokens.length) {
    const cmd = tokens[i++];
    if (cmd === 'M' || cmd === 'm') {
      let x = parseFloat(tokens[i++]), y = parseFloat(tokens[i++]);
      if (cmd === 'm') { x += cx; y += cy; }
      shape.moveTo(x, -y);
      cx = x; cy = y; started = true;
      // subsequent coords after M are implicit L
      while (i < tokens.length && !isNaN(parseFloat(tokens[i]))) {
        let lx = parseFloat(tokens[i++]), ly = parseFloat(tokens[i++]);
        if (cmd === 'm') { lx += cx; ly += cy; }
        shape.lineTo(lx, -ly);
        cx = lx; cy = ly;
      }
    } else if (cmd === 'L' || cmd === 'l') {
      while (i < tokens.length && !isNaN(parseFloat(tokens[i]))) {
        let x = parseFloat(tokens[i++]), y = parseFloat(tokens[i++]);
        if (cmd === 'l') { x += cx; y += cy; }
        shape.lineTo(x, -y);
        cx = x; cy = y;
      }
    } else if (cmd === 'H' || cmd === 'h') {
      while (i < tokens.length && !isNaN(parseFloat(tokens[i]))) {
        let x = parseFloat(tokens[i++]);
        if (cmd === 'h') x += cx;
        shape.lineTo(x, -cy);
        cx = x;
      }
    } else if (cmd === 'V' || cmd === 'v') {
      while (i < tokens.length && !isNaN(parseFloat(tokens[i]))) {
        let y = parseFloat(tokens[i++]);
        if (cmd === 'v') y += cy;
        shape.lineTo(cx, -y);
        cy = y;
      }
    } else if (cmd === 'C' || cmd === 'c') {
      while (i < tokens.length && !isNaN(parseFloat(tokens[i]))) {
        let x1=parseFloat(tokens[i++]), y1=parseFloat(tokens[i++]);
        let x2=parseFloat(tokens[i++]), y2=parseFloat(tokens[i++]);
        let x =parseFloat(tokens[i++]), y =parseFloat(tokens[i++]);
        if (cmd === 'c') { x1+=cx;y1+=cy; x2+=cx;y2+=cy; x+=cx;y+=cy; }
        shape.bezierCurveTo(x1,-y1, x2,-y2, x,-y);
        cx=x; cy=y;
      }
    } else if (cmd === 'Z' || cmd === 'z') {
      shape.closePath();
    }
    // Skip unsupported commands
  }
  return shape;
}

// SVG coordinate space → Three.js units (1 SVG unit ≈ 1pt ≈ 1/72 inch)
// Pershing Square viewBox is 1224×792 pts. Real site ~500ft wide.
// Scale: 500ft / 1224pt ≈ 0.408 ft/pt. We use 0.04 to keep scene compact.
const SVG_SCALE = 0.04;

async function deployTo3D() {
  if (MemoryState.stack.length === 0) {
    setStatus('Add layers to the stack first.', 'error');
    return;
  }

  // Dream Mode: extract footprints, send to backend, load .glb responses
  if (MemoryState.dreamMode) {
    const footprints = extractFootprints();
    if (footprints.length === 0) { setStatus('No visible layers to process.', 'error'); return; }
    setStatus('Sending footprints to AI sculptor...', 'running');
    document.getElementById('deploy-btn').disabled = true;
    try {
      const res  = await fetch('/api/generate-3d', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ footprints }),
      });
      const data = await res.json();
      if (data.status === 'error') {
        setStatus('Dream Mode error: ' + data.message, 'error');
        return;
      }
      setStatus(data.message || 'Dream meshes received — loading...', 'running');
      initSceneShell();  // set up scene/camera/renderer
      setView('3d');
      // Load each .glb response and fit it to its footprint
      const loader = new window.GLTFLoader();
      let loaded = 0;
      for (const item of (data.meshes || [])) {
        const fp = item.footprint;
        if (!item.glb_url) continue;
        loader.load(item.glb_url, gltf => {
          const obj = gltf.scene;
          // Fit bounding box to footprint
          const box = new THREE.Box3().setFromObject(obj);
          const size = box.getSize(new THREE.Vector3());
          const scaleX = fp.width  / (size.x || 1);
          const scaleZ = fp.depth  / (size.z || 1);
          const s = Math.min(scaleX, scaleZ);
          obj.scale.setScalar(s);
          obj.rotation.y = -fp.rotRad;
          obj.position.set(fp.cx, 0, fp.cz);
          threeScene.add(obj);
          loaded++;
          setStatus(`Dream Mode — ${loaded}/${data.meshes.length} meshes placed.`, loaded === data.meshes.length ? 'success' : 'running');
        }, undefined, err => console.warn('GLB load error', err));
      }
      if (!data.meshes || data.meshes.length === 0) {
        setStatus('AI returned no meshes — falling back to Draft mode.', 'error');
        // fall through to draft extrusion below after re-enabling button
      }
    } catch(err) {
      setStatus('Dream Mode connection error: ' + err.message, 'error');
    } finally {
      document.getElementById('deploy-btn').disabled = false;
    }
    return;
  }

  setStatus('Extruding remix stack to 3D...', 'running');

  setView('3d');
  if (!threeRenderer) {
    setTimeout(() => {
      initSceneShell();
      buildPershingContext();
    }, 100);
    // Give the OBJ time to start loading before we draw stack lines on top
    setTimeout(() => _drawStackLines(), 300);
    return;
  }
  _drawStackLines();
}

function _drawStackLines() {
  if (!threeScene) return;
  const baseSVGText = MemoryState.svgCache['PershingSquare'];
  if (!baseSVGText) { setStatus('PershingSquare SVG not loaded.', 'error'); return; }
  const baseSVGEl = parseSVG(baseSVGText);
  const bbox      = getBoundaryBBox(baseSVGEl);
  if (!bbox) { setStatus('BOUNDARY layer not found in PershingSquare.', 'error'); return; }

  let meshCount = 0;
  const ns = 'http://www.w3.org/2000/svg';

  MemoryState.stack.forEach(item => {
    if (!item.visible) return;
    const siteSVGText = MemoryState.svgCache[item.site];
    if (!siteSVGText) return;

    const precEl  = parseSVG(siteSVGText);
    const precVB  = getViewBox(precEl);
    const precCx  = precVB.x + precVB.w / 2;
    const precCy  = precVB.y + precVB.h / 2;

    const layerDef = TARGET_LAYERS.find(l => l.id === item.layerId) || { id: item.layerId };
    const resolved = resolveLayerGroup(layerDef, precEl, ns);
    if (!resolved) return;

    const t        = item.transform;
    const fitScale = Math.min(bbox.w / precVB.w, bbox.h / precVB.h);
    const ts       = fitScale * t.scale;
    const S        = SVG_SCALE * ts;
    const elevation = LAYER_HEIGHT[item.layerId] || 1.0;
    const colorInt  = parseInt(item.color.replace('#',''), 16);
    const opacity   = item.opacity ?? 0.85;
    const mat = new THREE.LineBasicMaterial({ color: colorInt, opacity, transparent: opacity < 1 });

    resolved.querySelectorAll('path').forEach(pathEl => {
      const d = pathEl.getAttribute('d');
      if (!d) return;
      const nums = [];
      const re2 = /(-?\d+\.?\d*(?:[eE][+-]?\d+)?)/g;
      let m2;
      while ((m2 = re2.exec(d)) !== null) nums.push(parseFloat(m2[1]));
      const pts = [];
      for (let i = 0; i + 1 < nums.length; i += 2) {
        pts.push(new THREE.Vector3(
          (nums[i]   - precCx) * S + t.x * SVG_SCALE,
          elevation,
          (nums[i+1] - precCy) * S + t.y * SVG_SCALE
        ));
      }
      if (pts.length < 2) return;
      threeScene.add(new THREE.Line(new THREE.BufferGeometry().setFromPoints(pts), mat));
      meshCount++;
    });
  });

  if (meshCount > 0) setStatus(`3D lines drawn — ${meshCount} segments.`, 'success');

  // Also render cached site context (box geometry from /api/site-context)
  (cachedSiteContext || []).forEach(geo => {
    const mat2 = new THREE.MeshStandardMaterial({ color: new THREE.Color(geo.color || '#111111'), roughness: 0.9, opacity: geo.opacity ?? 0.9, transparent: (geo.opacity ?? 0.9) < 1 });
    let geom2;
    if      (geo.type === 'box')      geom2 = new THREE.BoxGeometry(...geo.args);
    else if (geo.type === 'cylinder') geom2 = new THREE.CylinderGeometry(...geo.args, 32);
    else if (geo.type === 'sphere')   geom2 = new THREE.SphereGeometry(geo.args[0], 16, 16);
    if (geom2) {
      const m = new THREE.Mesh(geom2, mat2);
      if (geo.position) m.position.set(...geo.position);
      if (geo.rotation) m.rotation.set(...geo.rotation);
      threeScene.add(m);
    }
  });
}

// ── Shared scene initializer — sets up renderer, camera, lights, orbit controls ──
let _threeOrbitSph = { theta: 0.5, phi: 0.5, r: 120 };
function initSceneShell() {
  const canvas = document.getElementById('three-canvas');
  document.getElementById('canvas-placeholder').style.display = 'none';
  canvas.style.display = 'block';

  if (threeRenderer) { cancelAnimationFrame(threeAnimId); threeRenderer.dispose(); }

  const w = canvas.offsetWidth || canvas.parentElement.offsetWidth;
  const h = canvas.offsetHeight || canvas.parentElement.offsetHeight;

  threeScene  = new THREE.Scene();
  const _bgCol = document.body.classList.contains('light-mode') ? 0xffffff : 0x050505;
  threeScene.background = new THREE.Color(_bgCol);
  threeScene.fog = new THREE.FogExp2(_bgCol, 0.008);

  threeCamera = new THREE.PerspectiveCamera(45, w / h, 0.1, 2000);
  threeCamera.position.set(0, 60, 80);
  threeCamera.lookAt(0, 0, 0);

  threeRenderer = new THREE.WebGLRenderer({ canvas, antialias: true });
  threeRenderer.setSize(w, h);
  threeRenderer.setPixelRatio(window.devicePixelRatio);

  threeScene.add(new THREE.AmbientLight(0x404040, 3));
  const dir = new THREE.DirectionalLight(0xfff4ca, 2);
  dir.position.set(30, 60, 40);
  threeScene.add(dir);

  // Ground
  const ground = new THREE.Mesh(
    new THREE.PlaneGeometry(300, 300),
    new THREE.MeshStandardMaterial({ color: 0x0a0a0a, roughness: 0.9 })
  );
  ground.rotation.x = -Math.PI / 2;
  threeScene.add(ground);

  // Orbit controls
  _threeOrbitSph = { theta: 0.5, phi: 0.5, r: 120 };
  let isDragging = false, prevX = 0, prevY = 0;
  canvas.addEventListener('mousedown', e => { isDragging = true; prevX = e.clientX; prevY = e.clientY; });
  window.addEventListener('mouseup',   ()  => { isDragging = false; });
  window.addEventListener('mousemove', e  => {
    if (!isDragging) return;
    _threeOrbitSph.theta -= (e.clientX - prevX) * 0.005;
    _threeOrbitSph.phi    = Math.max(0.05, Math.min(Math.PI/2 - 0.05, _threeOrbitSph.phi - (e.clientY - prevY) * 0.005));
    prevX = e.clientX; prevY = e.clientY;
  });
  canvas.addEventListener('wheel', e => { _threeOrbitSph.r = Math.max(10, Math.min(400, _threeOrbitSph.r + e.deltaY * 0.1)); });

  function animate() {
    threeAnimId = requestAnimationFrame(animate);
    threeCamera.position.x = _threeOrbitSph.r * Math.sin(_threeOrbitSph.phi) * Math.sin(_threeOrbitSph.theta);
    threeCamera.position.y = _threeOrbitSph.r * Math.cos(_threeOrbitSph.phi);
    threeCamera.position.z = _threeOrbitSph.r * Math.sin(_threeOrbitSph.phi) * Math.cos(_threeOrbitSph.theta);
    threeCamera.lookAt(0, 0, 0);
    threeRenderer.render(threeScene, threeCamera);
  }
  animate();

  window.addEventListener('resize', () => {
    threeCamera.aspect = canvas.offsetWidth / canvas.offsetHeight;
    threeCamera.updateProjectionMatrix();
    threeRenderer.setSize(canvas.offsetWidth, canvas.offsetHeight);
  });
}

// Load PershingSQCurrent.obj as the permanent 3D base model.
// Called once when the 3D tab first opens.
function buildPershingContext() {
  setStatus('Loading Pershing Square 3D model...', 'running');

  // Temporary wide-angle until OBJ loads and gets rescaled to SVG world space
  _threeOrbitSph.r   = 80;
  _threeOrbitSph.phi = 0.7;
  _threeOrbitSph.theta = 0.6;
  threeCamera.far = 5000;
  threeCamera.updateProjectionMatrix();
  if (threeScene.fog) threeScene.fog.density = 0.0005;

  const isLight = document.body.classList.contains('light-mode');

  const mtlLoader = new window.MTLLoader();
  mtlLoader.setPath('/models/rhino/');
  mtlLoader.load('PershingSQCurrent.mtl', materials => {
    materials.preload();

    // Override all materials to a clean architectural tone
    Object.values(materials.materials).forEach(mat => {
      mat.color.set(isLight ? 0xdddddd : 0x334455);
      mat.side = THREE.DoubleSide;
    });

    const objLoader = new window.OBJLoader();
    objLoader.setMaterials(materials);
    objLoader.setPath('/models/rhino/');
    objLoader.load(
      'PershingSQCurrent.obj',
      obj => {
        // Compute bounding box in original Rhino units
        const box    = new THREE.Box3().setFromObject(obj);
        const center = box.getCenter(new THREE.Vector3());
        const size   = box.getSize(new THREE.Vector3());

        // Scale OBJ to match SVG world space (Pershing viewBox 1224pt × SVG_SCALE 0.04 ≈ 49 units)
        const targetSpan = 1224 * SVG_SCALE;
        const objSpan    = Math.max(size.x, size.z);
        const objScale   = targetSpan / objSpan;
        obj.scale.setScalar(objScale);

        // Center XZ at world origin; sit bottom on ground (scale-aware)
        obj.position.x = -center.x * objScale;
        obj.position.z = -center.z * objScale;
        obj.position.y = -box.min.y * objScale;

        threeScene.add(obj);
        _threeOrbitSph.r = targetSpan * 2.0;
        setStatus('Pershing Square 3D model loaded.', 'success');
      },
      xhr => {
        const pct = xhr.total ? Math.round(xhr.loaded / xhr.total * 100) : '...';
        setStatus(`Loading model — ${pct}%`, 'running');
      },
      err => {
        console.error('OBJ load error', err);
        setStatus('Model load failed — check console.', 'error');
      }
    );
  },
  undefined,
  err => {
    // MTL failed — load OBJ with a plain fallback material
    console.warn('MTL load failed, using fallback material', err);
    const objLoader = new window.OBJLoader();
    objLoader.setPath('/models/rhino/');
    objLoader.load(
      'PershingSQCurrent.obj',
      obj => {
        const fallbackMat = new THREE.MeshStandardMaterial({
          color: isLight ? 0xcccccc : 0x445566,
          roughness: 0.8, side: THREE.DoubleSide,
        });
        obj.traverse(child => { if (child.isMesh) child.material = fallbackMat; });

        const box    = new THREE.Box3().setFromObject(obj);
        const center = box.getCenter(new THREE.Vector3());
        const size   = box.getSize(new THREE.Vector3());

        const targetSpan = 1224 * SVG_SCALE;
        const objSpan    = Math.max(size.x, size.z);
        const objScale   = targetSpan / objSpan;
        obj.scale.setScalar(objScale);

        obj.position.x = -center.x * objScale;
        obj.position.z = -center.z * objScale;
        obj.position.y = -box.min.y * objScale;

        threeScene.add(obj);
        _threeOrbitSph.r = targetSpan * 2.0;
        setStatus('Pershing Square 3D model loaded (fallback material).', 'success');
      },
      undefined,
      e2 => { setStatus('OBJ load failed: ' + e2.message, 'error'); }
    );
  });
}

// ─────────────────────────────────────────────────────────────────────────────
// Existing: Three.js for AI-generated geometry (preserve original flow)
// ─────────────────────────────────────────────────────────────────────────────
function buildMesh(geo, mat, wireMat) {
  let geom;
  if      (geo.type === 'box')      geom = new THREE.BoxGeometry(...geo.args);
  else if (geo.type === 'cylinder') geom = new THREE.CylinderGeometry(...geo.args, 32);
  else if (geo.type === 'sphere')   geom = new THREE.SphereGeometry(geo.args[0], 16, 16);
  else return;
  const mesh = new THREE.Mesh(geom, mat);
  if (geo.position) mesh.position.set(...geo.position);
  if (geo.rotation) mesh.rotation.set(...geo.rotation);
  threeScene.add(mesh);
  if (wireMat) {
    const wire = new THREE.Mesh(geom, wireMat);
    if (geo.position) wire.position.set(...geo.position);
    if (geo.rotation) wire.rotation.set(...geo.rotation);
    threeScene.add(wire);
  }
}

function initThree(geometries, siteContext) {
  const canvas = document.getElementById('three-canvas');
  document.getElementById('canvas-placeholder').style.display = 'none';
  canvas.style.display = 'block';
  if (threeRenderer) { cancelAnimationFrame(threeAnimId); threeRenderer.dispose(); }

  const w = canvas.offsetWidth || canvas.parentElement.offsetWidth;
  const h = canvas.offsetHeight || canvas.parentElement.offsetHeight;

  threeScene  = new THREE.Scene();
  threeScene.background = new THREE.Color(0x050505);
  threeCamera = new THREE.PerspectiveCamera(45, w / h, 0.1, 1000);
  threeCamera.position.set(40, 32, 55);
  threeCamera.lookAt(0, 0, 0);
  threeRenderer = new THREE.WebGLRenderer({ canvas, antialias: true });
  threeRenderer.setSize(w, h);
  threeRenderer.setPixelRatio(window.devicePixelRatio);
  threeRenderer.sortObjects = true;
  threeScene.add(new THREE.AmbientLight(0x404040, 2));
  const dir = new THREE.DirectionalLight(0xfff4ca, 1.5);
  dir.position.set(20, 40, 20); threeScene.add(dir);

  const ctx = siteContext || cachedSiteContext || [];
  ctx.forEach(geo => {
    const mat = new THREE.MeshStandardMaterial({
      color: new THREE.Color(geo.color || '#111111'), roughness: 0.9, metalness: 0.05,
      transparent: (geo.opacity ?? 1) < 1, opacity: geo.opacity ?? 1,
      depthWrite: (geo.opacity ?? 1) >= 0.99,
    });
    buildMesh(geo, mat, null);
  });

  const wireMat = new THREE.MeshBasicMaterial({ color: 0xfff4ca, wireframe: true, opacity: 0.18, transparent: true });
  geometries.forEach(geo => {
    buildMesh(geo, new THREE.MeshStandardMaterial({ color: new THREE.Color(geo.color || '#888888'), roughness: 0.75, metalness: 0.1 }), wireMat);
  });

  let isDragging = false, prevX = 0, prevY = 0, spherical = { theta: 0.6, phi: 0.6, r: 80 };
  canvas.addEventListener('mousedown', e => { isDragging = true; prevX = e.clientX; prevY = e.clientY; });
  window.addEventListener('mouseup',   ()  => { isDragging = false; });
  window.addEventListener('mousemove', e  => {
    if (!isDragging) return;
    spherical.theta -= (e.clientX - prevX) * 0.005;
    spherical.phi    = Math.max(0.1, Math.min(Math.PI/2 - 0.05, spherical.phi - (e.clientY - prevY) * 0.005));
    prevX = e.clientX; prevY = e.clientY;
  });
  canvas.addEventListener('wheel', e => { spherical.r = Math.max(10, Math.min(150, spherical.r + e.deltaY * 0.05)); });

  function animate() {
    threeAnimId = requestAnimationFrame(animate);
    threeCamera.position.x = spherical.r * Math.sin(spherical.phi) * Math.sin(spherical.theta);
    threeCamera.position.y = spherical.r * Math.cos(spherical.phi);
    threeCamera.position.z = spherical.r * Math.sin(spherical.phi) * Math.cos(spherical.theta);
    threeCamera.lookAt(0, 0, 0);
    threeRenderer.render(threeScene, threeCamera);
  }
  animate();
  window.addEventListener('resize', () => {
    threeCamera.aspect = canvas.offsetWidth / canvas.offsetHeight;
    threeCamera.updateProjectionMatrix();
    threeRenderer.setSize(canvas.offsetWidth, canvas.offsetHeight);
  });
}

// ── Mermaid diagram ──────────────────────────────────────────────────────────
mermaid.initialize({ startOnLoad: false, theme: 'dark', flowchart: { curve: 'basis' } });
async function renderDiagram(diagramSrc) {
  const container = document.getElementById('diagram-render');
  document.getElementById('diagram-placeholder').style.display = 'none';
  container.innerHTML = '';
  try {
    const { svg } = await mermaid.render('mmd-' + Date.now(), diagramSrc);
    container.innerHTML = svg;
  } catch (e) {
    container.innerHTML = `<pre style="color:#ff4444;font-size:0.75rem">${e.message}</pre>`;
  }
}

// ── Auto-populate info tabs from stack state ────────────────────────────────
// Called after every stack mutation. Builds a local Mermaid diagram and
// lightweight precedent cards from the stack — no API call required.
// Full ChromaDB cards still come from "Generate Intervention".
async function updateInfoTabs() {
  const visible = MemoryState.stack.filter(i => i.visible);

  // ── Precedents tab: one card per visible layer ─────────────────────────────
  const precPlaceholder = document.getElementById('precedents-placeholder');
  const precRender      = document.getElementById('precedents-render');

  if (visible.length === 0) {
    precPlaceholder.style.display = '';
    precPlaceholder.textContent   = 'Precedent sources will appear here after synthesis.';
    precRender.innerHTML = '';
  } else {
    precPlaceholder.style.display = 'none';
    // Only regenerate if we haven't run Generate yet (no ChromaDB cards present)
    const hasChromaCards = precRender.querySelector('.prec-notes') !== null;
    if (!hasChromaCards) {
      const LAYER_DESCRIPTIONS = {
        GREEN_SPACE:     'Vegetated ground plane — lawns, meadows, planted areas.',
        SHADE:           'Canopy and overhead shade structures.',
        WATER_FEATURES:  'Pools, fountains, rills, and water edges.',
        STREET:          'Roadway and circulation networks.',
        PEDESTRIAN_PATH: 'Pedestrian routes and promenades.',
        MAJOR_ATTRACTORS:'Primary programmatic anchors and destination points.',
        MINOR_ATTRACTORS:'Secondary activity nodes and casual gathering spots.',
        UNIQUE_ELEMENTS: 'Site-specific elements and bespoke installations.',
        STREET_FURNITURE:'Seating, lighting, kiosks, and hardscape accessories.',
        PARKING:         'Vehicular parking areas and access.',
        BOUNDARY:        'Site perimeter and edge definition.',
      };
      precRender.innerHTML = visible.map(item => `
        <div class="precedent-card">
          <div class="prec-header">
            <div class="prec-name" style="color:${item.color}">${SITE_LABELS[item.site] || item.site}</div>
            <div class="prec-badge">${item.layerId.replace(/_/g,' ')}</div>
          </div>
          <div class="prec-location">Layer · ${item.label}</div>
          <div class="prec-notes">${LAYER_DESCRIPTIONS[item.layerId] || 'Site diagram layer.'}</div>
          <div class="prec-review-label">Stack transform</div>
          <blockquote>offset (${Math.round(item.transform.x)}, ${Math.round(item.transform.y)}) &nbsp;·&nbsp;
            scale ${(item.transform.scale * 100).toFixed(0)}% &nbsp;·&nbsp;
            rotate ${Math.round(item.transform.rot)}° &nbsp;·&nbsp;
            opacity ${Math.round((item.opacity ?? 0.85) * 100)}%
          </blockquote>
        </div>`).join('');
    } else {
      // ChromaDB cards already shown — just update transform info via data attributes
      // (leave cards alone to not clobber generate results)
    }
  }

  // ── Logic Diagram tab: Mermaid flowchart from stack ─────────────────────────
  if (visible.length === 0) {
    document.getElementById('diagram-placeholder').style.display = '';
    document.getElementById('diagram-render').innerHTML = '';
    return;
  }

  // Group by site, then show layers. Build a graph: Pershing ← each layer ← site
  const lines = ['flowchart LR', '  PS([Pershing Square])'];
  const siteNodes = {};
  visible.forEach(item => {
    const sKey = item.site.replace(/[^a-zA-Z0-9]/g,'');
    if (!siteNodes[sKey]) {
      siteNodes[sKey] = true;
      lines.push(`  ${sKey}([${SITE_LABELS[item.site] || item.site}])`);
    }
    const lKey = sKey + '_' + item.layerId.replace(/[^a-zA-Z0-9]/g,'');
    const lLabel = item.layerId.replace(/_/g,' ');
    lines.push(`  ${sKey} -->|"${lLabel}"| ${lKey}["${lLabel}"]`);
    lines.push(`  ${lKey} --> PS`);
  });
  await renderDiagram(lines.join('\n'));
}

// ── Main generate call ───────────────────────────────────────────────────────
async function generate() {
  const prompt = document.getElementById('prompt-input').value.trim();
  if (!prompt) return;
  document.getElementById('generate-btn').disabled = true;
  document.getElementById('narrative-text').className = 'placeholder';
  document.getElementById('narrative-text').textContent = 'Processing...';
  setStatus('Querying memory archive and synthesizing...', 'running');
  try {
    // Build remix context from the current layer stack
    const stackSummary = MemoryState.stack.filter(i => i.visible).map(i => {
      const t = i.transform;
      return `${i.label} (offset ${Math.round(t.x)},${Math.round(t.y)} scale ${t.scale.toFixed(1)}× rot ${Math.round(t.rot)}°)`;
    });
    const remixContext = stackSummary.length
      ? `\n\n[REMIX CONTEXT] Active layer stack within Pershing Square boundary:\n${stackSummary.map(s=>'- '+s).join('\n')}`
      : '';

    const res  = await fetch('/api/generate', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ prompt: prompt + remixContext }) });
    const data = await res.json();
    if (data.status === 'error') {
      setStatus('Error: ' + data.narrative, 'error');
      document.getElementById('narrative-text').className = '';
      document.getElementById('narrative-text').textContent = data.narrative;
    } else {
      setStatus('Synthesis complete — ' + (data.name || 'Intervention generated.'), 'success');
      document.getElementById('narrative-text').className = '';
      document.getElementById('narrative-text').textContent = data.narrative;
      if (data.sources && data.sources.length > 0) {
        document.getElementById('precedents-placeholder').style.display = 'none';
        document.getElementById('precedents-render').innerHTML = data.sources.map(s => `
          <div class="precedent-card">
            <div class="prec-header"><div class="prec-name">${s.name}</div><div class="prec-badge">${s.source_type}</div></div>
            <div class="prec-location">${s.location}</div>
            <div class="prec-notes">${s.notes}</div>
            <hr class="prec-divider">
            <div class="prec-review-label">Retrieved memory fragment</div>
            <blockquote>${s.excerpt}</blockquote>
          </div>`).join('');
      }
      if (data.site_context) cachedSiteContext = data.site_context;
      if (data.geometries && data.geometries.length > 0) initThree(data.geometries, data.site_context);
      if (data.diagram) await renderDiagram(data.diagram);
      MemoryState.lastGeneration = data;
      const bakeBtn = document.getElementById('bake-btn');
      bakeBtn.style.display = 'block';
      bakeBtn.disabled = false;
      bakeBtn.textContent = '\u25C6 Bake to Rhino';
    }
  } catch (err) {
    setStatus('Connection error — is the server running?', 'error');
    document.getElementById('narrative-text').className = '';
    document.getElementById('narrative-text').textContent = err.message;
  } finally {
    document.getElementById('generate-btn').disabled = false;
  }
}

// ── Bake to Rhino ────────────────────────────────────────────────────────────
async function bakeToRhino() {
  if (!MemoryState.lastGeneration || !MemoryState.lastGeneration.geometries) return;
  const btn = document.getElementById('bake-btn');
  btn.disabled = true; btn.textContent = '\u25C6 Baking...';
  setStatus('Sending geometry to Rhino...', 'running');
  try {
    // Include SVG_SCALE and per-layer footprint data so the Python bake script
    // can place geometry at the correct world coordinates in Rhino model space.
    // svg_scale converts SVG pts → Three.js world units (0.04).
    // stack_footprints mirrors the deployTo3D transform math: each item has
    //   cx, cz (world-space center), width, depth (world-space extents), rotRad,
    //   site, layerId, color — enough for bake_to_rhino.py to reconstruct placement.
    const payload = {
      name:             MemoryState.lastGeneration.name || 'Unnamed Intervention',
      geometries:       MemoryState.lastGeneration.geometries || [],
      svg_scale:        SVG_SCALE,
      stack_footprints: extractFootprints(),
    };
    const res  = await fetch('/api/bake', { method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload) });
    const data = await res.json();
    if (data.status === 'success') {
      setStatus('Bake complete — geometry sent to MEM_GENERATED layer.', 'success');
      btn.textContent = '\u25C6 Baked to Rhino';
    } else {
      setStatus('Bake failed: ' + (data.message || 'Unknown error'), 'error');
      btn.disabled = false; btn.textContent = '\u25C6 Bake to Rhino';
    }
  } catch (err) {
    setStatus('Bake error — is the server running?', 'error');
    btn.disabled = false; btn.textContent = '\u25C6 Bake to Rhino';
  }
}

// ── Init ─────────────────────────────────────────────────────────────────────
document.getElementById('prompt-input').addEventListener('keydown', e => {
  if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) generate();
});

// ─────────────────────────────────────────────────────────────────────────────
// Save / Load compositions (localStorage)
// ─────────────────────────────────────────────────────────────────────────────
const STORAGE_KEY = 'mm_compositions';

function getCompositions() {
  try { return JSON.parse(localStorage.getItem(STORAGE_KEY) || '{}'); } catch(e) { return {}; }
}
function putCompositions(obj) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(obj));
}

MemoryState.currentCompositionName = null;

function saveComposition(asNew) {
  const comps = getCompositions();
  let name;
  if (asNew || !MemoryState.currentCompositionName) {
    name = prompt('Name this composition:', `Remix ${timestamp()}`);
    if (!name) return;
  } else {
    name = MemoryState.currentCompositionName;
  }
  comps[name] = {
    savedAt: new Date().toISOString(),
    stack: MemoryState.stack.map(item => ({ ...item })),
  };
  putCompositions(comps);
  MemoryState.currentCompositionName = name;
  closeAllDropdowns();
  setStatus(`Saved: "${name}"`, 'success');
  refreshLoadDropdown();
}

function loadComposition(name) {
  const comps = getCompositions();
  const comp  = comps[name];
  if (!comp) return;
  MemoryState.stack = comp.stack.map(item => ({ ...item }));
  MemoryState.currentCompositionName = name;
  MemoryState.editingId = null;
  resetTransform();
  // Pre-fetch any SVGs not yet cached
  const missing = [...new Set(MemoryState.stack.map(i => i.site))].filter(s => !MemoryState.svgCache[s]);
  Promise.all(missing.map(s => fetchSVG(s).then(svg => { MemoryState.svgCache[s] = svg; }))).then(() => {
    renderStackUI();
    renderRemixSVG();
    updateInfoTabs();
    setStatus(`Loaded: "${name}"`, 'success');
  });
  closeAllDropdowns();
}

function deleteComposition(name) {
  if (!confirm(`Delete "${name}"?`)) return;
  const comps = getCompositions();
  delete comps[name];
  putCompositions(comps);
  if (MemoryState.currentCompositionName === name) MemoryState.currentCompositionName = null;
  refreshLoadDropdown();
}

function refreshLoadDropdown() {
  const dd    = document.getElementById('load-dropdown');
  const comps = getCompositions();
  const names = Object.keys(comps).reverse();
  const svgEntry = `<button class="export-opt ai" onclick="document.getElementById('svg-file-input').click();closeAllDropdowns()">&#8599; Load SVG file…</button>`;
  const divider  = names.length ? '<div class="export-opt divider" style="cursor:default;font-size:0.55rem">Saved compositions</div>' : '';
  const slots    = names.length
    ? names.map(n => `
        <button class="export-opt composition-slot" onclick="loadComposition('${n.replace(/'/g,"\\'")}')">
          <span>${n}</span>
          <span class="slot-del" onclick="event.stopPropagation();deleteComposition('${n.replace(/'/g,"\\'")}')">✕</span>
        </button>`).join('')
    : '<span class="export-opt" style="color:var(--muted);cursor:default">No saved compositions</span>';
  dd.innerHTML = svgEntry + divider + slots;
}

function loadSVGFile(event) {
  const file = event.target.files[0];
  if (!file) return;
  // Derive a site key from the filename (strip extension, trim whitespace)
  const siteName = file.name.replace(/\.svg$/i, '').trim();
  const reader = new FileReader();
  reader.onload = e => {
    const svgText = e.target.result;
    // Register in svgCache so it's available to the stack selectors
    MemoryState.svgCache[siteName] = svgText;
    // Add it as an option in the site select if not already present
    const sel = document.getElementById('site-select');
    if (sel && !Array.from(sel.options).some(o => o.value === siteName)) {
      const opt = document.createElement('option');
      opt.value = siteName;
      opt.textContent = siteName;
      sel.appendChild(opt);
      sel.value = siteName;  // auto-select the newly loaded site
    }
    setStatus(`SVG loaded: ${siteName} — select it from the site dropdown to add layers.`, 'success');
  };
  reader.onerror = () => setStatus('Failed to read SVG file.', 'error');
  reader.readAsText(file);
  // Reset input so the same file can be re-loaded if needed
  event.target.value = '';
}

function toggleSaveDropdown() {
  document.getElementById('load-dropdown').classList.remove('open');
  document.getElementById('save-dropdown').classList.toggle('open');
}
function toggleLoadDropdown() {
  document.getElementById('save-dropdown').classList.remove('open');
  refreshLoadDropdown();
  document.getElementById('load-dropdown').classList.toggle('open');
}
function closeAllDropdowns() {
  ['export-dropdown','save-dropdown','load-dropdown'].forEach(id => {
    document.getElementById(id)?.classList.remove('open');
  });
}
document.addEventListener('click', e => {
  if (!e.target.closest('.export-wrap') && !e.target.closest('.save-load-row')) closeAllDropdowns();
});

// Auto-save to a rolling autosave slot on every stack change
function autosave() {
  const comps = getCompositions();
  comps['__autosave__'] = { savedAt: new Date().toISOString(), stack: MemoryState.stack.map(i => ({ ...i })) };
  putCompositions(comps);
}

buildLayerSelect();

// Restore autosave if it exists
(function restoreAutosave() {
  const comps = getCompositions();
  if (comps['__autosave__'] && comps['__autosave__'].stack?.length) {
    const restore = confirm('Restore last session?');
    if (restore) {
      MemoryState.stack = comps['__autosave__'].stack.map(i => ({ ...i }));
      MemoryState.currentCompositionName = null;
    }
  }
})();

// Load Pershing Square boundary SVG immediately so canvas shows on open
(async () => {
  try {
    setStatus('Loading site boundary...', 'running');
    await ensureBaseSVG();
    renderRemixSVG();
    setStatus('Site loaded — Pershing Square, DTLA', 'success');
  } catch(e) { setStatus('SVG load error: ' + e.message, 'error'); }
})();

// Load 3D site context in background
(async () => {
  try {
    const res  = await fetch('/api/site-context');
    const data = await res.json();
    if (data.geometries && data.geometries.length > 0) cachedSiteContext = data.geometries;
  } catch (e) { /* server not ready */ }
})();
