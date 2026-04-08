/**
 * MEMORY MACHINE // MAIN CONTROLLER
 * Orchestrates 2D render, 3D scene, AI generation, and UI state.
 * Depends on: constants.js, state.js, engine2D.js (loaded before this module)
 */

let autoExportEnabled = true;

// ── THREE.JS SCENE STATE ─────────────────────────────────────────────────────
let threeRenderer = null;
let threeScene    = null;
let threeCamera   = null;
let threeAnimId   = null;
let _orbitSph     = { theta: 0.6, phi: 0.5, r: 80 };
let _orbitBound   = false;

// ── RENDER LOOP ──────────────────────────────────────────────────────────────
function _startRenderLoop() {
  if (threeAnimId) cancelAnimationFrame(threeAnimId);
  function _frame() {
    threeAnimId = requestAnimationFrame(_frame);
    threeCamera.position.x = _orbitSph.r * Math.sin(_orbitSph.phi) * Math.sin(_orbitSph.theta);
    threeCamera.position.y = _orbitSph.r * Math.cos(_orbitSph.phi);
    threeCamera.position.z = _orbitSph.r * Math.sin(_orbitSph.phi) * Math.cos(_orbitSph.theta);
    threeCamera.lookAt(0, 0, 0);
    threeRenderer.render(threeScene, threeCamera);
  }
  _frame();
}

function _initOrbitControls(canvas) {
  if (_orbitBound === canvas) return;
  _orbitBound = canvas;
  let dragging = false, px = 0, py = 0;
  canvas.addEventListener('mousedown', e => { dragging = true; px = e.clientX; py = e.clientY; });
  window.addEventListener('mouseup',   () => { dragging = false; });
  window.addEventListener('mousemove', e => {
    if (!dragging) return;
    _orbitSph.theta -= (e.clientX - px) * 0.005;
    _orbitSph.phi    = Math.max(0.05, Math.min(Math.PI / 2 - 0.05, _orbitSph.phi - (e.clientY - py) * 0.005));
    px = e.clientX; py = e.clientY;
  });
  canvas.addEventListener('wheel', e => {
    _orbitSph.r = Math.max(10, Math.min(400, _orbitSph.r + e.deltaY * 0.1));
    e.preventDefault();
  }, { passive: false });
  window.addEventListener('resize', () => {
    if (!threeCamera || !threeRenderer) return;
    const c = document.getElementById('canvas-container');
    threeCamera.aspect = c.offsetWidth / c.offsetHeight;
    threeCamera.updateProjectionMatrix();
    threeRenderer.setSize(c.offsetWidth, c.offsetHeight);
  });
}

// ── THREE.JS SCENE INIT ──────────────────────────────────────────────────────
function initThreeScene() {
  const container = document.getElementById('canvas-container');
  const placeholder = document.getElementById('canvas-placeholder');
  if (placeholder) placeholder.style.display = 'none';

  // Reuse renderer if already initialized
  if (threeRenderer) {
    if (threeAnimId) cancelAnimationFrame(threeAnimId);
    threeScene.clear();
    _addSceneLights();
    _startRenderLoop();
    return;
  }

  let canvas = container.querySelector('canvas');
  if (!canvas) {
    canvas = document.createElement('canvas');
    container.appendChild(canvas);
  }

  const w = container.offsetWidth  || 800;
  const h = container.offsetHeight || 600;

  threeScene    = new THREE.Scene();
  threeScene.background = new THREE.Color(0x020202);
  threeScene.fog = new THREE.FogExp2(0x020202, 0.006);

  threeCamera = new THREE.PerspectiveCamera(45, w / h, 0.1, 2000);
  threeCamera.position.set(0, 50, 80);
  threeCamera.lookAt(0, 0, 0);

  threeRenderer = new THREE.WebGLRenderer({ canvas, antialias: true });
  threeRenderer.setSize(w, h);
  threeRenderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  threeRenderer.shadowMap.enabled = true;

  _addSceneLights();
  _addGroundPlane();
  _initOrbitControls(canvas);
  _startRenderLoop();
}

function _addSceneLights() {
  threeScene.add(new THREE.AmbientLight(0x202020, 3));
  const key = new THREE.DirectionalLight(0xfff4ca, 2.5);
  key.position.set(30, 60, 40);
  key.castShadow = true;
  threeScene.add(key);
  const fill = new THREE.DirectionalLight(0x4488ff, 0.5);
  fill.position.set(-40, 20, -30);
  threeScene.add(fill);
}

function _addGroundPlane() {
  const geo = new THREE.PlaneGeometry(300, 300, 20, 20);
  const mat = new THREE.MeshStandardMaterial({
    color: 0x080808, roughness: 1, metalness: 0,
    wireframe: false,
  });
  const plane = new THREE.Mesh(geo, mat);
  plane.rotation.x = -Math.PI / 2;
  plane.receiveShadow = true;
  threeScene.add(plane);

  // Grid overlay
  const grid = new THREE.GridHelper(200, 40, 0x1a1a1a, 0x111111);
  threeScene.add(grid);
}

// ── GEOMETRY RENDERING ───────────────────────────────────────────────────────
function clearSceneGeometries() {
  if (!threeScene) return;
  const toRemove = [];
  threeScene.traverse(obj => {
    if (obj.userData.isIntervention) toRemove.push(obj);
  });
  toRemove.forEach(obj => {
    if (obj.geometry) obj.geometry.dispose();
    if (obj.material) obj.material.dispose();
    threeScene.remove(obj);
  });
}

function renderGeometries(geometries) {
  if (!threeScene) return;
  clearSceneGeometries();

  geometries.forEach(geo => {
    let geom;
    if      (geo.type === 'box')      geom = new THREE.BoxGeometry(...geo.args);
    else if (geo.type === 'cylinder') geom = new THREE.CylinderGeometry(...geo.args, 32);
    else if (geo.type === 'sphere')   geom = new THREE.SphereGeometry(geo.args[0], 16, 12);
    else return;

    const color = new THREE.Color(geo.color || '#888888');
    const mat = new THREE.MeshStandardMaterial({
      color,
      roughness: 0.75,
      metalness: 0.15,
      transparent: (geo.opacity ?? 1) < 1,
      opacity: geo.opacity ?? 1,
      depthWrite: (geo.opacity ?? 1) >= 0.99,
    });
    const mesh = new THREE.Mesh(geom, mat);
    if (geo.position) mesh.position.set(...geo.position);
    if (geo.rotation) mesh.rotation.set(...geo.rotation);
    mesh.castShadow = true;
    mesh.userData.isIntervention = true;
    threeScene.add(mesh);

    // Wireframe shell
    const wireMat = new THREE.MeshBasicMaterial({
      color: 0xfff4ca, wireframe: true, transparent: true, opacity: 0.12,
    });
    const wire = new THREE.Mesh(geom, wireMat);
    wire.position.copy(mesh.position);
    wire.userData.isIntervention = true;
    threeScene.add(wire);
  });
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

// ── AI GENERATION ────────────────────────────────────────────────────────────
async function generate() {
  const input  = document.getElementById('prompt-input');
  let prompt = input.value.trim();
  
  // Provide a default prompt if the user just hits 'GEN' with an empty box
  if (!prompt) {
    prompt = "A peaceful, quiet space with lush greenery, shaded seating, and a calming water feature.";
    input.value = prompt;
  }

  const btn = document.getElementById('generate-btn');
  if (btn) btn.disabled = true;
  
  // Immediately clear the stack and board for a clean visual slate
  MemoryState.clear();
  clearSceneGeometries();
  if (window.renderRemixSVG) window.renderRemixSVG();
  refreshStackUI();

  setStatus('Synthesising memory node...', 'running');
  appendToTerminal(`> ${prompt}`, 'line-accent');

  try {
    const res  = await fetch('/api/generate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ prompt }),
    });
    const data = await res.json();

    if (data.status === 'error') {
      appendToTerminal(`ERROR: ${data.narrative}`, 'line-error');
      setStatus('AI Core Offline.', 'error');
      return;
    }

    // 1. Narrative
    if (data.narrative) {
      appendToTerminal('─'.repeat(40), 'line-muted');
      appendToTerminal(data.narrative);
      appendToTerminal('─'.repeat(40), 'line-muted');
    }

    // 2. Store result
    MemoryState.lastGeneration = {
      narrative:  data.narrative  || '',
      geometries: data.geometries || [],
      diagram:    data.diagram    || '',
    };

    // 2.5 Update 2D Stack automatically
    if (data.spatial_seed && data.spatial_seed.length > 0) {
      // Automatically clear the base park context to make room for the new layout
      MemoryState.baseCleared = true;
      
      // Pre-fetch any SVGs not yet in cache so engine2D never silently skips layers
      const missingSites = [...new Set(
        data.spatial_seed
          .map(s => s.site || 'PershingSquare')
          .filter(site => !MemoryState.svgCache[site])
      )];
      if (missingSites.length > 0) {
        setStatus(`Fetching ${missingSites.length} precedent site(s)…`, 'running');
        await Promise.all(missingSites.map(site => fetchSVG(site).catch(err => {
          appendToTerminal(`⚠ Could not load SVG for ${site}: ${err.message}`, 'line-muted');
        })));
      }

      MemoryState.stack = data.spatial_seed.map((seed, idx) => {
        const lId = seed.layerId || 'GREEN_SPACE';
        let c = '#888888';
        if (lId.includes('GREEN') || lId.includes('SHADE')) c = '#4CAF50';
        else if (lId.includes('WATER')) c = '#03A9F4';
        else if (lId.includes('ATTRACTOR') || lId.includes('UNIQUE')) c = '#FF9800';
        else if (lId.includes('STREET') || lId.includes('PATH') || lId.includes('BOUNDARY') || lId.includes('FURNITURE')) c = '#9E9E9E';
        
        return {
          id: Date.now() + idx,
          site: seed.site || 'PershingSquare',
          layerId: lId,
          color: c,
          label: seed.label || lId,
          visible: true,
          transform: seed.transform || {x: 0, y: 0, scale: 1.0, rot: 0}
        };
      });
      window.renderRemixSVG?.();
      refreshStackUI();
    }

    // 3. Mermaid diagram
    if (data.diagram) renderDiagram(data.diagram);

    // 4. Update view based on mode
    if (MemoryState.dreamMode && data.geometries?.length > 0) {
      switchToTab('3d');
      initThreeScene();
      renderGeometries(data.geometries);
      setStatus(`Dream rendered — ${data.geometries.length} forms.`, 'success');
    } else {
      // Update live if user is already watching the 3D tab
      if (document.getElementById('tab-3d')?.classList.contains('active')) {
        initThreeScene();
        renderGeometries(data.geometries);
      }
      setStatus('Synthesis complete.', 'success');
    }

    // 5. Trigger Auto-Export Pipeline
    // NOTE: captureDashboardUI is manual-only (html2canvas at scale:2 OOMs the tab).
    if (autoExportEnabled && data.spatial_seed && data.spatial_seed.length > 0) {
      setTimeout(async () => {
        const delay = ms => new Promise(res => setTimeout(res, ms));
        await handleExport('svg-color');
        await delay(300);
        await handleExport('svg-grey');
        await delay(300);
        await handleExport('jpg-color');
        await delay(300);
        await handleExport('jpg-grey');
        setStatus('Synthesis & Auto-Exports complete.', 'success');
      }, 500); // 500ms delay ensures DOM is fully painted with new SVG first
    }

    input.value = '';
  } catch (e) {
    appendToTerminal(`FATAL: ${e.message}`, 'line-error');
    setStatus('Connection error.', 'error');
  } finally {
    if (btn) btn.disabled = false;
  }
}

// ── STACK EDITOR ─────────────────────────────────────────────────────────────
// Guidelines fetched from /api/guidelines on boot.
// Shape: { SOFT: {min,max}, HARD: {min,max}, PROG: {min,max}, BLUE: {min,max} }
let _guidelines = {
  SOFT: { min: 30, max: 50 },
  HARD: { min: 40, max: 60 },
  PROG: { min: 10, max: 20 },
  BLUE: { min:  2, max: 10 },
};

/** Re-render the stack list and refresh HUD after any mutation. */
function refreshStackUI() {
  const list    = document.getElementById('stack-list');
  const counter = document.getElementById('stack-count');
  if (!list) return;

  const stack = MemoryState.stack;
  counter.textContent = `${stack.length} LAYER${stack.length !== 1 ? 'S' : ''}`;

  if (stack.length === 0) {
    list.innerHTML = '<div class="stack-empty">No layers generated yet.</div>';
    document.getElementById('xform-panel').style.display = 'none';
    updateHUD();
    return;
  }

  const SITE_LABELS = {
    PershingSquare:    'Pershing Square',
    ParcdelaVillette:  'Parc de la Villette',
    ZaryadyePark:      'Zaryadye Park',
    Schouwburgplein:   'Schouwburgplein',
  };

  list.innerHTML = stack.map(item => {
    const siteName  = SITE_LABELS[item.site] || item.site;
    const eyeIcon   = item.visible !== false ? '👁' : '◌';
    const dimClass  = item.visible !== false ? '' : ' hidden-layer';
    return `
    <div class="stack-item${MemoryState.editingId === item.id ? ' selected' : ''}${dimClass}"
         data-id="${item.id}">
      <span class="stack-swatch" style="background:${item.color}"></span>
      <span class="stack-item-label">${siteName} — ${item.layerId}</span>
      <button class="stack-eye-btn" data-id="${item.id}" title="Toggle visibility">${eyeIcon}</button>
    </div>`;
  }).join('');

  list.querySelectorAll('.stack-item').forEach(el => {
    el.addEventListener('click', e => {
      // Don't open xform panel when clicking the eye toggle
      if (e.target.classList.contains('stack-eye-btn')) return;
      const id   = parseInt(el.dataset.id);
      
      if (MemoryState.editingId === id) {
        MemoryState.editingId = null;
        document.getElementById('xform-panel').style.display = 'none';
      } else {
        const item = MemoryState.stack.find(i => i.id === id);
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
function updateHUD() {
  const stats = MemoryState.getProgramStats();
  (['SOFT', 'HARD', 'PROG', 'BLUE']).forEach(key => {
    const pct  = stats[key] ?? 0;
    const g    = _guidelines[key];
    const row  = document.getElementById(`hud-${key}`);
    const bar  = document.getElementById(`hud-bar-${key}`);
    const pctEl = document.getElementById(`hud-pct-${key}`);
    const tgtEl = document.getElementById(`hud-tgt-${key}`);
    if (!row) return;

    if (pctEl) pctEl.textContent = `${Math.round(pct)}%`;
    if (tgtEl && g) tgtEl.textContent = `${g.min}–${g.max}%`;
    if (bar)  bar.style.width = Math.min(pct, 100) + '%';

    // Compliance class
    row.classList.remove('hud-ok', 'hud-warn', 'hud-over');
    if (pct === 0) { /* no class — idle */ }
    else if (pct > (g?.max ?? 100)) row.classList.add('hud-over');
    else if (pct < (g?.min ?? 0))   row.classList.add('hud-warn');
    else                             row.classList.add('hud-ok');
  });
}

// ── TERMINAL OUTPUT ──────────────────────────────────────────────────────────
function appendToTerminal(text, cls) {
  const out = document.getElementById('narrative-output');
  if (!out) return;
  const pre = document.createElement('pre');
  pre.textContent = text;
  if (cls) pre.className = cls;
  out.appendChild(pre);
  out.scrollTop = out.scrollHeight;
}

// ── UI CAPTURE ───────────────────────────────────────────────────────────────
async function captureDashboardUI() {
  setStatus('Capturing Dashboard UI...', 'running');
  try {
    const grid = document.querySelector('.main-grid');
    const canvas = await html2canvas(grid, {
      backgroundColor: document.body.classList.contains('light-mode') ? '#f4f4f4' : '#050505',
      scale: 2, // High-res capture
      logging: false
    });
    
    const dataUrl = canvas.toDataURL('image/jpeg', 0.95);
    const timestamp = Date.now();
    
    const res = await fetch('/api/export-diagram', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        filename: `dashboard_capture_${timestamp}.jpg`,
        data: dataUrl,
        type: 'ui-capture'
      })
    });
    if (res.ok) setStatus('UI Capture saved to appTests archive', 'success');
    else throw new Error('Backend capture failed');
  } catch (e) {
    setStatus('UI Capture failed: ' + e.message, 'error');
  }
}

// ── EXPORT LOGIC ─────────────────────────────────────────────────────────────
async function handleExport(mode) {
  const svgEl = document.querySelector('#remix-svg-container svg');
  if (!svgEl) {
    setStatus('No SVG to export', 'error');
    return;
  }
  
  setStatus('Exporting to server...', 'running');
  const clone = svgEl.cloneNode(true);
  
  // Lock dimensions to standard 17x11 sheet at 72 DPI (1224x792)
  clone.setAttribute('viewBox', '0 0 1224 792');
  clone.setAttribute('width', '1224');
  clone.setAttribute('height', '792');
  
  // Force absolute export themes regardless of current UI viewer
  const isGrey = mode.includes('grey');
  const bgFill = isGrey ? '#ffffff' : '#050505';
  const ctxLine = isGrey ? '#dddddd' : '#444444';
  const bndLine = isGrey ? '#000000' : '#ffffff';
  const intLine = isGrey ? '#222222' : null; // null keeps original layer color

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
    if (isGrey) {
      p.setAttribute('stroke', intLine); p.style.stroke = intLine;
      p.setAttribute('fill', 'none'); p.style.fill = 'none'; // Strip hatches for pure linework
    } else {
      // Restore HUD color if we cloned a light-mode DOM but want a color export
      const origCol = p.getAttribute('data-orig-color');
      if (origCol) {
        p.setAttribute('stroke', origCol); p.style.stroke = origCol;
        const currentFill = p.getAttribute('fill');
        if (currentFill && currentFill !== 'none') {
          p.setAttribute('fill', origCol); p.style.fill = origCol;
        }
      }
    }
  });
  
  const svgData = new XMLSerializer().serializeToString(clone);
  const timestamp = Date.now();
  
  if (mode.startsWith('svg')) {
    // SVG Export to Backend
    try {
      const res = await fetch('/api/export-diagram', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          filename: `memory_machine_${mode}_${timestamp}.svg`,
          data: svgData,
          type: 'svg'
        })
      });
      if (res.ok) setStatus('Exported SVG successfully to archive', 'success');
      else throw new Error('Backend export failed');
    } catch (e) {
      setStatus('Export failed: ' + e.message, 'error');
    }
  } else if (mode.startsWith('jpg')) {
    // JPG High-Res Canvas Render & Export to Backend
    await new Promise((resolve) => {
      const blob = new Blob([svgData], { type: 'image/svg+xml;charset=utf-8' });
      const url = URL.createObjectURL(blob);
      const img = new Image();
      img.onload = async () => {
        const canvas = document.createElement('canvas');
        canvas.width  = 1224; // 1× — sufficient for archive; 2× OOMs on complex SVGs
        canvas.height = 792;
        const ctx = canvas.getContext('2d');
        ctx.fillStyle = isGrey ? '#ffffff' : '#050505';
        ctx.fillRect(0, 0, canvas.width, canvas.height);
        ctx.drawImage(img, 0, 0, canvas.width, canvas.height);

        const dataUrl = canvas.toDataURL('image/jpeg', 0.92);
        // Release bitmap memory immediately
        URL.revokeObjectURL(url);
        canvas.width = 0; canvas.height = 0;

        try {
          const res = await fetch('/api/export-diagram', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              filename: `memory_machine_${mode}_${timestamp}.jpg`,
              data: dataUrl,
              type: 'jpg'
            })
          });
          if (res.ok) setStatus('Exported JPG successfully to archive', 'success');
          else throw new Error('Backend export failed');
        } catch (e) {
          setStatus('Export failed: ' + e.message, 'error');
        }
        resolve();
      };
      img.onerror = () => { URL.revokeObjectURL(url); resolve(); };
      img.src = url;
    });
  }
}

// ── MERMAID DIAGRAM ──────────────────────────────────────────────────────────
function renderDiagram(src) {
  const el = document.getElementById('mermaid-graph');
  if (!el) return;
  el.innerHTML = src;
  el.removeAttribute('data-processed');
  try { mermaid.run({ nodes: [el] }); } catch (e) { /* silent */ }
}

// ── TAB SWITCHING ────────────────────────────────────────────────────────────
function switchToTab(name) {
  document.querySelectorAll('.tab-pane').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
  const pane = document.getElementById('tab-' + name);
  const btn  = document.querySelector(`.tab-btn[data-tab="${name}"]`);
  if (pane) pane.classList.add('active');
  if (btn)  btn.classList.add('active');
  if (name === '3d') window.dispatchEvent(new Event('resize'));
}

// ── INIT ─────────────────────────────────────────────────────────────────────
async function init() {
  mermaid.initialize({ startOnLoad: false, theme: 'dark', flowchart: { curve: 'basis' } });

  // ── Fetch urban design guidelines ────────────────────────────────────────
  try {
    const res  = await fetch('/api/guidelines');
    const data = await res.json();
    // Backend returns { guidelines: {Softscape,Hardscape,Active,Blue_Space}, ... }
    // or flat { SOFT, HARD, PROG, BLUE } — handle both shapes
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

  // ── Auto-Discover Available SVG Sites ────────────────────────────────────
  try {
    const sitesRes = await fetch('/api/available-sites');
    const sitesData = await sitesRes.json();
    const dropdown = document.getElementById('load-svg-dropdown');
    if (dropdown && sitesData.sites) {
      dropdown.innerHTML = '<option value="">Load SVG file...</option>';
      sitesData.sites.forEach(site => {
        window.SITES[site.id] = {
          id: site.id,
          label: site.name,
          origin: { x: 0, y: 0 },
          bounds: site.bounds
        };
        const opt = document.createElement('option');
        opt.value = site.id;
        opt.textContent = site.name;
        if (site.id.toLowerCase() === 'pershingsquare') opt.selected = true;
        dropdown.appendChild(opt);
      });
    }
  } catch (err) {
    console.error('Failed to auto-discover sites:', err);
  }

  // Load Pershing Square SVG as default base
  try {
    await fetchSVG('PershingSquare');
    window.renderRemixSVG?.();
    setStatus('Site loaded — Pershing Square, DTLA', 'success');
  } catch (e) {
    setStatus('SVG load error: ' + e.message, 'error');
  }

  // ── Event: prompt submit on Enter ────────────────────────────────────────
  document.getElementById('prompt-input')?.addEventListener('keydown', e => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); generate(); }
  });

  // ── Event: Generate button ───────────────────────────────────────────────
  document.getElementById('generate-btn')?.addEventListener('click', generate);

  // ── Event: Site selector ─────────────────────────────────────────────────
  document.getElementById('load-svg-dropdown')?.addEventListener('change', async e => {
    const siteId = e.target.value;
    if (!siteId) return;
    try {
      await fetchSVG(siteId);
      setStatus('Loaded: ' + siteId, 'success');
      window.renderRemixSVG?.();
    } catch (err) {
      setStatus('Load failed: ' + err.message, 'error');
    }
  });

  // ── Event: Auto-Export Toggle ────────────────────────────────────────────
  const exportToggle = document.getElementById('auto-export-toggle');
  exportToggle?.addEventListener('click', () => {
    autoExportEnabled = !autoExportEnabled;
    if (autoExportEnabled) {
      exportToggle.textContent = 'Auto-Export: ON';
      exportToggle.style.color = 'var(--green)';
      exportToggle.style.borderColor = 'var(--green)';
    } else {
      exportToggle.textContent = 'Auto-Export: OFF';
      exportToggle.style.color = 'var(--muted)';
      exportToggle.style.borderColor = 'var(--border2)';
    }
  });

  // ── Event: Capture UI ────────────────────────────────────────────────────
  document.getElementById('capture-ui-btn')?.addEventListener('click', captureDashboardUI);

  // ── Event: Deploy to 3D ──────────────────────────────────────────────────
  document.getElementById('deploy-3d-btn')?.addEventListener('click', () => {
    switchToTab('3d');
    initThreeScene();
    const geos = MemoryState.lastGeneration.geometries;
    if (geos?.length > 0) {
      renderGeometries(geos);
      setStatus(`3D scene deployed — ${geos.length} forms.`, 'success');
    } else {
      setStatus('Generate an intervention first.', 'error');
    }
  });

  // ── Event: Dream mode toggle ─────────────────────────────────────────────
  document.getElementById('dream-mode-toggle')?.addEventListener('change', e => {
    MemoryState.dreamMode = e.target.checked;
    const btn = document.getElementById('generate-btn');
    if (btn) btn.classList.toggle('dream-active', MemoryState.dreamMode);
    setStatus(MemoryState.dreamMode ? 'Dream mode active.' : 'Draft mode active.', 'success');
  });

  // ── Event: Clear stack ───────────────────────────────────────────────────
  // (Already wired in index.html inline script, but guard for safety)
  document.getElementById('clear-stack-btn')?.addEventListener('click', () => {
    MemoryState.clear();
    clearSceneGeometries();
    window.renderRemixSVG?.();
    refreshStackUI();
    setStatus('Stack cleared.', 'success');
  });

  // ── Event: Panel Resizer ─────────────────────────────────────────────────
  const resizer = document.getElementById('panel-resizer');
  const narrativePanel = document.getElementById('narrative-output');
  let isResizing = false;
  let startY = 0;
  let startHeight = 0;

  resizer?.addEventListener('mousedown', (e) => {
    isResizing = true;
    startY = e.clientY;
    startHeight = narrativePanel.getBoundingClientRect().height;
    resizer.classList.add('dragging');
    document.body.style.cursor = 'ns-resize';
    e.preventDefault();
  });

  window.addEventListener('mousemove', (e) => {
    if (!isResizing) return;
    const dy = e.clientY - startY;
    const newHeight = startHeight + dy;
    // Constrain height to keep UI usable (min 50px, max ~70% of screen)
    if (newHeight > 50 && newHeight < window.innerHeight * 0.7) {
      narrativePanel.style.flex = `0 0 ${newHeight}px`;
    }
  });

  window.addEventListener('mouseup', () => {
    if (isResizing) {
      isResizing = false;
      resizer.classList.remove('dragging');
      document.body.style.cursor = '';
    }
  });
}

// ── BOOT ─────────────────────────────────────────────────────────────────────
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', init);
} else {
  init();
}
