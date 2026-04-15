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
let _cameraMode   = 'orbit';

// ── RENDER LOOP ──────────────────────────────────────────────────────────────
function _startRenderLoop() {
  if (threeAnimId) cancelAnimationFrame(threeAnimId);
  function _frame() {
    threeAnimId = requestAnimationFrame(_frame);
    if (_cameraMode === 'orbit') {
      threeCamera.position.x = _orbitSph.r * Math.sin(_orbitSph.phi) * Math.sin(_orbitSph.theta);
      threeCamera.position.y = _orbitSph.r * Math.cos(_orbitSph.phi);
      threeCamera.position.z = _orbitSph.r * Math.sin(_orbitSph.phi) * Math.cos(_orbitSph.theta);
      threeCamera.lookAt(0, 0, 0);
    }
    threeRenderer.render(threeScene, threeCamera);
  }
  _frame();
}

function _initOrbitControls(canvas) {
  if (_orbitBound === canvas) return;
  _orbitBound = canvas;
  let dragging = false, px = 0, py = 0;
  canvas.addEventListener('mousedown', e => { 
    dragging = true; px = e.clientX; py = e.clientY; 
    if (_cameraMode === 'human') {
      _cameraMode = 'orbit';
      const btn = document.getElementById('btn-human-view');
      if (btn) btn.textContent = '🧍 Human View';
    }
  });
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
  const cameraControls = document.getElementById('camera-controls');
  if (placeholder) placeholder.style.display = 'none';
  if (cameraControls) cameraControls.style.display = 'flex';

  // Reuse renderer if already initialized
  if (threeRenderer) {
    if (threeAnimId) cancelAnimationFrame(threeAnimId);
    threeScene.clear();
    _addSceneLights();
    _addGroundPlane();
    _loadBaseModel();
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

  threeRenderer = new THREE.WebGLRenderer({ canvas, antialias: true, preserveDrawingBuffer: true });
  threeRenderer.setSize(w, h);
  threeRenderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  threeRenderer.shadowMap.enabled = true;

  _addSceneLights();
  _addGroundPlane();
  _loadBaseModel();
  _initOrbitControls(canvas);
  _startRenderLoop();
}

function _addSceneLights() {
  threeScene.add(new THREE.AmbientLight(0x303030, 0.95));
  const key = new THREE.DirectionalLight(0xfff4ca, 1.25);
  key.position.set(30, 60, 40);
  key.castShadow = true;
  threeScene.add(key);
  const fill = new THREE.DirectionalLight(0x4488ff, 0.65);
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

// ── LOAD BASE OBJ MODEL ──────────────────────────────────────────────────────
function _loadBaseModel() {
  if (typeof THREE.OBJLoader === 'undefined') return;

  function _fitAndAdd(object) {
    const box    = new THREE.Box3().setFromObject(object);
    const center = box.getCenter(new THREE.Vector3());
    const size   = box.getSize(new THREE.Vector3());
    // Scale entire model (park + context) so the max footprint dimension = 100 units
    const scale  = 100 / Math.max(size.x, size.z);

    object.position.sub(center.multiplyScalar(scale));
    object.scale.setScalar(scale);
    const boxAfter = new THREE.Box3().setFromObject(object);
    object.position.y -= boxAfter.min.y;

    // Auto-detect hardscape boundary: find all flat Y≈0 meshes (park surface)
    // that are not the full ground plane (area < 1500 sq units).
    // These are the park hardscape tiles - take their union.
    // Detect hardscape surface using geometry directly (no visibility dependency)
    let hsMinX = Infinity, hsMaxX = -Infinity;
    let hsMinZ = Infinity, hsMaxZ = -Infinity;
    let hsMaxY = -Infinity;
    let found = 0;
    object.traverse(child => {
      if (!child.isMesh || !child.geometry) return;
      // Compute bounds from geometry attribute directly — ignores visibility
      child.geometry.computeBoundingBox();
      const lb = child.geometry.boundingBox.clone();
      // Apply child world matrix
      child.updateWorldMatrix(true, false);
      lb.applyMatrix4(child.matrixWorld);
      const sz = lb.getSize(new THREE.Vector3());
      const midY = (lb.min.y + lb.max.y) / 2;
      const area = sz.x * sz.z;
      if (sz.y < 1.5 && midY > -1.2 && midY < 0.5 && area > 80 && area < 800) {
        hsMinX = Math.min(hsMinX, lb.min.x);
        hsMaxX = Math.max(hsMaxX, lb.max.x);
        hsMinZ = Math.min(hsMinZ, lb.min.z);
        hsMaxZ = Math.max(hsMaxZ, lb.max.z);
        hsMaxY = Math.max(hsMaxY, lb.max.y);
        found++;
      }
    });
    if (found > 0) {
      _hardscapeMinX = hsMinX; _hardscapeMaxX = hsMaxX;
      _hardscapeMinZ = hsMinZ; _hardscapeMaxZ = hsMaxZ;
      _hardscapeSurfaceY = hsMaxY;
    }
    console.log(`[Park] Hardscape detected from ${found} meshes: x=${_hardscapeMinX.toFixed(1)}..${_hardscapeMaxX.toFixed(1)}  z=${_hardscapeMinZ.toFixed(1)}..${_hardscapeMaxZ.toFixed(1)}  center=(${((_hardscapeMinX+_hardscapeMaxX)/2).toFixed(1)}, ${((_hardscapeMinZ+_hardscapeMaxZ)/2).toFixed(1)})`);

    object.userData.isBaseModel = true;
    threeScene.add(object);
    _drawHardscapeDebugBox();
  }

  if (typeof THREE.MTLLoader !== 'undefined') {
    const mtlLoader = new THREE.MTLLoader();
    const cb = Date.now();
    mtlLoader.load(`/models/PershingSQforApp.mtl?v=${cb}`, function (materials) {
      materials.preload();
      const objLoader = new THREE.OBJLoader();
      objLoader.setMaterials(materials);
      objLoader.load(`/models/PershingSQforApp.obj?v=${cb}`, _fitAndAdd,
        undefined, e => console.error('OBJ load error:', e));
    }, undefined, () => {
      new THREE.OBJLoader().load(`/models/PershingSQforApp.obj?v=${cb}`, _fitAndAdd,
        undefined, e => console.error('OBJ load error:', e));
    });
  } else {
    new THREE.OBJLoader().load('/models/PershingSQforApp.obj', _fitAndAdd,
      undefined, e => console.error('OBJ load error:', e));
  }
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

// ── COORDINATE SYSTEM ────────────────────────────────────────────────────────
// Authority: SVG HARDSCAPE layer (Pershing Square park boundary)
//   SVG viewBox:        1224 × 792
//   HARDSCAPE bounds:   x=297.5..728.6, y=138.9..598.7  (431 × 460 SVG units)
//   HARDSCAPE center:   (513, 369) in SVG space
//
// LOCATION_OFFSETS in urban_engine.py are *relative to park center* (not SVG origin):
//   East  = +160 SVG units  (74% of half-width  215.5)
//   North = -140 SVG units  (61% of half-depth  229.9)
//
// OBJ → Three.js: entire model scaled so max(x,z) span = 100 units
//   OBJ model center = (278, -386) in OBJ space → Three.js (0, y, 0)
//   HARDSCAPE in OBJ ≈ object_45: x=-152..221, z=-616..-153
//   After scale (÷2174×100) + center: x≈-19.8..-2.6, z≈-10.6..10.7
//   Half-extents: halfX≈8.6, halfZ≈10.65
//
// User confirmed: hardscape top surface = Y=0 (everything sits on this plane)

// Set dynamically by _fitAndAdd via mesh traversal — fallback from vertex analysis
// Park center is at Three.js (-5.0, 5.0), not (0,0) — OBJ was centered on city block
let _hardscapeMinX = -19.8;
let _hardscapeMaxX =   9.8;
let _hardscapeMinZ = -10.6;
let _hardscapeMaxZ =  20.6;
let _hardscapeSurfaceY = 2.07;  // Y of park top surface; set dynamically from mesh

// SVG offset range that maps to the full hardscape extent
const SVG_OFFSET_MAX_X = 160;  // East/West max
const SVG_OFFSET_MAX_Z = 140;  // North/South max

// ── CALIBRATION WIREFRAME ─────────────────────────────────────────────────────
// True park rectangle derived from SVG HARDSCAPE corner analysis:
//   SVG corners: TL(526.6,156.8) TR(727.9,276.4) BR(481.5,598.7) BL(303.9,471.9)
//   Rotation TL→TR: -0.5361 rad (-30.7°) around Three.js Y axis
//   True rect in Three.js: 16.79 × 27.67 units
//   Center: (-5.0, 0, 5.0)
const PARK_ROTATION_Y  = -0.6807;   // radians (-38.7°)
const PARK_RECT_WIDTH  = 16.79;     // Three.js units (SVG TL→TR direction)
const PARK_RECT_DEPTH  = 27.67;     // Three.js units (SVG TL→BL direction)
const PARK_CENTER_X    = -5.0;
const PARK_CENTER_Z    =  5.0;

function _drawHardscapeDebugBox() {
  if (!threeScene) return;

  // Remove previous debug objects
  const toRemove = [];
  threeScene.traverse(o => { if (o.userData.debugMarker) toRemove.push(o); });
  toRemove.forEach(o => threeScene.remove(o));

  const Y = _hardscapeSurfaceY + 0.1;
  const cos = Math.cos(PARK_ROTATION_Y);
  const sin = Math.sin(PARK_ROTATION_Y);
  const hw = PARK_RECT_WIDTH / 2;
  const hd = PARK_RECT_DEPTH / 2;

  // Orange boundary box
  const geo = new THREE.BoxGeometry(PARK_RECT_WIDTH, 0.05, PARK_RECT_DEPTH);
  const mat = new THREE.MeshBasicMaterial({ color: 0xFF9800, wireframe: true, transparent: true, opacity: 0.7 });
  const box = new THREE.Mesh(geo, mat);
  box.position.set(PARK_CENTER_X, Y, PARK_CENTER_Z);
  box.rotation.y = PARK_ROTATION_Y;
  box.userData.debugMarker = true;
  box.visible = false;
  threeScene.add(box);

  // Cardinal markers — small spheres at N/S/E/W edges of the rotated rect
  // Each cardinal maps to a park-local offset, rotated into world space
  const cardinals = [
    { label: 'N', lx:  0, lz: -1, color: 0x2196F3 },  // North: blue
    { label: 'S', lx:  0, lz:  1, color: 0xF44336 },  // South: red
    { label: 'E', lx:  1, lz:  0, color: 0x4CAF50 },  // East: green
    { label: 'W', lx: -1, lz:  0, color: 0xFFEB3B },  // West: yellow
  ];

  cardinals.forEach(({ label, lx, lz, color }) => {
    // Rotate park-local edge midpoint into world space (Three.js Y-rotation matrix)
    const wx = PARK_CENTER_X + (lx * hw * cos + lz * hd * sin);
    const wz = PARK_CENTER_Z + (-lx * hw * sin + lz * hd * cos);

    const sphere = new THREE.Mesh(
      new THREE.SphereGeometry(0.4, 8, 8),
      new THREE.MeshBasicMaterial({ color })
    );
    sphere.position.set(wx, Y + 0.5, wz);
    sphere.userData.debugMarker = true;
    sphere.visible = false;
    sphere.name = `cardinal-${label}`;
    threeScene.add(sphere);
  });
}

// Zone → PBR material properties
const ZONE_MATERIALS = {
  GREEN_SPACE:     { color: 0x4CAF50, roughness: 0.9, metalness: 0.0 },
  WATER_FEATURES:  { color: 0x03A9F4, roughness: 0.1, metalness: 0.1 },
  UNIQUE_ELEMENTS: { color: 0xFF9800, roughness: 0.6, metalness: 0.3 },
  SHADE:           { color: 0xBCAAA4, roughness: 0.8, metalness: 0.1 },
  HARDSCAPE:       { color: 0x9E9E9E, roughness: 0.95, metalness: 0.0 },
};

// ── GLB LOADER ────────────────────────────────────────────────────────────────
function loadGLBIntoScene(glbUrl, svgX, svgZ, zoneType = '') {
  if (!threeScene) return;
  if (typeof THREE.GLTFLoader === 'undefined') {
    console.warn('[GLB] GLTFLoader not available');
    return;
  }

  // Map SVG offsets (±160 X, ±140 Z) to the rotated park rectangle.
  // SVG offset axes align with the park's local axes (along/across the diagonal).
  // Rotate the offset into Three.js world space using PARK_ROTATION_Y.
  const halfW = PARK_RECT_WIDTH  / 2;
  const halfD = PARK_RECT_DEPTH  / 2;

  // Normalise SVG offsets to [-1, 1] in park-local space, capped at 85% of edge
  const localX = Math.max(-0.85, Math.min(0.85, svgX / SVG_OFFSET_MAX_X));
  const localZ = Math.max(-0.85, Math.min(0.85, svgZ / SVG_OFFSET_MAX_Z));

  // Rotate park-local coords into world space using Three.js Y-rotation matrix:
  // worldX = localX*cos + localZ*sin
  // worldZ = -localX*sin + localZ*cos
  const cos = Math.cos(PARK_ROTATION_Y);
  const sin = Math.sin(PARK_ROTATION_Y);
  const clampedX = PARK_CENTER_X + (localX * halfW * cos + localZ * halfD * sin);
  const clampedZ = PARK_CENTER_Z + (-localX * halfW * sin + localZ * halfD * cos);

  const loader = new THREE.GLTFLoader();
  loader.load(glbUrl, (gltf) => {
    const obj = gltf.scene;

    // Scale to ~10% of hardscape width (reasonable element size)
    const box  = new THREE.Box3().setFromObject(obj);
    const size = box.getSize(new THREE.Vector3());
    const targetHeight = halfW * 0.25;  // ~2 Three.js units tall, readable at park scale
    const scale = targetHeight / Math.max(size.x, size.y, size.z);
    obj.scale.setScalar(scale);

    // Seat on hardscape surface
    const boxAfter = new THREE.Box3().setFromObject(obj);
    obj.position.y = _hardscapeSurfaceY - boxAfter.min.y;

    obj.position.x = clampedX;
    obj.position.z = clampedZ;

    const zoneMat = ZONE_MATERIALS[zoneType];
    obj.userData.isIntervention = true;
    obj.traverse(child => {
      if (child.isMesh) {
        child.castShadow = true;
        child.userData.isIntervention = true;
        if (zoneMat) {
          child.material = new THREE.MeshStandardMaterial({
            color: zoneMat.color,
            roughness: zoneMat.roughness,
            metalness: zoneMat.metalness,
          });
        }
      }
    });

    threeScene.add(obj);
    switchToTab('3d');
    const b2 = new THREE.Box3().setFromObject(obj);
    const sz2 = b2.getSize(new THREE.Vector3());
    console.log(`[GLB] ${glbUrl} → pos(${obj.position.x.toFixed(2)}, ${obj.position.y.toFixed(2)}, ${obj.position.z.toFixed(2)})  size(${sz2.x.toFixed(2)}, ${sz2.y.toFixed(2)}, ${sz2.z.toFixed(2)})`);
  }, undefined, (err) => {
    console.error('[GLB] Load error:', err);
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
  
  // Soft reset: keep locked base-context layers, discard prior interventions
  MemoryState.stack = MemoryState.stack.filter(i => i.locked);
  MemoryState.pathCache.clear();
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

      const newLayers = data.spatial_seed.map((seed, idx) => {
        const lId = seed.layerId || 'GREEN_SPACE';
        return {
          id: Date.now() + idx,
          site: seed.site || 'PershingSquare',
          layerId: lId,
          color: _getLayerColor(lId),
          label: seed.label || lId,
          visible: true,
          locked: false,
          contextLayer: false,
          base_area_px:   seed.base_area_px   ?? 1,
          solved_area_px: seed.solved_area_px ?? 1,
          transform: seed.transform || { x: 0, y: 0, scale: 1.0, rot: 0 }
        };
      });
      MemoryState.stack.push(...newLayers);
      window.renderRemixSVG?.();
      refreshStackUI();
    }

    // 3. Mermaid diagram
    if (data.diagram) renderDiagram(data.diagram);

    // 4. Always update the 2D diagram; prime the 3D scene.
    // Primitives from renderGeometries() are replaced by ComfyUI GLBs — skip them.
    setStatus('Synthesis complete.', 'success');
    initThreeScene();

    // 4b. Always fire ComfyUI for every intervention layer.
    // GLBs load asynchronously — they appear in the 3D viewer as they finish.
    if (data.spatial_seed?.length > 0) {
      const interventionLayers = data.spatial_seed.filter(
        s => s.layerId !== 'STREET' && s.layerId !== 'BUILDING'
      );
      if (interventionLayers.length > 0) {
        setStatus(`Generating ${interventionLayers.length} 3D element(s)…`, 'running');
        let doneCount = 0;
        interventionLayers.forEach(seed => {
          const tx = seed.transform?.x ?? 0;
          const ty = seed.transform?.y ?? 0;
          const zonePrompt = `${prompt}. ${seed.label || seed.layerId} element, urban park, architectural scale model`;
          fetch('/api/comfy-text-to-3d', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              prompt: zonePrompt,
              zone_type: seed.layerId,
              position_x: tx,
              position_z: ty,
            }),
          })
          .then(r => r.json())
          .then(result => {
            if (result.status === 'success') {
              loadGLBIntoScene(result.glb_url, result.position.x, result.position.z, seed.layerId);
              appendToTerminal(`✓ 3D: ${seed.label || seed.layerId} → (${result.position.x.toFixed(0)}, ${result.position.z.toFixed(0)})`, 'line-muted');
            }
            doneCount++;
            if (doneCount === interventionLayers.length) {
              setStatus('2D + 3D synthesis complete.', 'success');
            }
          })
          .catch(err => console.warn('[GLB pipeline]', err));
        });
      }
    }

    // 5. Trigger Auto-Export Pipeline
    // NOTE: captureDashboardUI now uses the Playwright backend to safely capture without OOMs.
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
        await delay(300);
        await captureDashboardUI();
        setStatus('Synthesis, Auto-Exports & UI Capture complete.', 'success');
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

  list.innerHTML = visibleItems.map(item => {
    const siteName  = SITE_LABELS[item.site] || item.site;
    const eyeIcon   = item.visible !== false ? '👁' : '◌';
    const dimClass  = item.visible !== false ? '' : ' hidden-layer';
    const lockClass = item.locked ? ' locked-layer' : '';
    const rightEl   = item.locked
      ? `<span class="stack-lock-icon" title="Identity seed — locked">⬡</span>`
      : `<button class="stack-eye-btn" data-id="${item.id}" title="Toggle visibility">${eyeIcon}</button>`;
    return `
    <div class="stack-item${MemoryState.editingId === item.id ? ' selected' : ''}${dimClass}${lockClass}"
         data-id="${item.id}">
      <span class="stack-swatch" style="background:${item.color}"></span>
      <span class="stack-item-label">${siteName} — ${item.layerId}</span>
      ${rightEl}
    </div>`;
  }).join('');

  list.querySelectorAll('.stack-item').forEach(el => {
    el.addEventListener('click', e => {
      // Don't open xform panel when clicking the eye toggle or on locked items
      if (e.target.classList.contains('stack-eye-btn')) return;
      const id   = parseInt(el.dataset.id);
      const item = MemoryState.stack.find(i => i.id === id);
      if (item?.locked) return;

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
  setStatus('Capturing Dashboard UI via Backend...', 'running');
  try {
    const prompt = document.getElementById('prompt-input').value.trim() || "Memory Machine Synthesis";
    const isLightMode = document.body.classList.contains('light-mode');
    const activeTab = document.querySelector('.tab-pane.active')?.id.replace('tab-', '') || '2d';

    const res = await fetch('/api/capture-dashboard', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        prompt: prompt,
        spatial_seed: MemoryState.stack,
        geometries: MemoryState.lastGeneration.geometries || [],
        narrative: MemoryState.lastGeneration.narrative || '',
        isLightMode: isLightMode,
        activeTab: activeTab
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
  const intLine = isGrey ? '#222222' : '#ffffff'; // color mode uses white stroke

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

// ── LAYER COLOR UTILITY ──────────────────────────────────────────────────────
/** Single source of truth for Rhino layer colors across generation and picker. */
function _getLayerColor(layerId) {
  const id = (layerId || '').toUpperCase();
  if (id.includes('GREEN') || id.includes('SHADE'))               return '#4CAF50';
  if (id.includes('WATER'))                                        return '#03A9F4';
  if (id.includes('ATTRACTOR') || id.includes('UNIQUE'))          return '#FF9800';
  return '#9E9E9E'; // STREET, PATH, BOUNDARY, PARKING, FURNITURE, etc.
}

// ── BASE CONTEXT INJECTION ────────────────────────────────────────────────────
/**
 * Injects locked base Pershing Square layers as "identity seed" items.
 * These items are rendered by engine2D as context (not as interventions)
 * and give the HUD a real HARD baseline even before any generation.
 */
function _injectBaseContext() {
  // Infrastructure from Pershing Square (rendered via context-group, not intervention loop)
  const BASE_LAYERS = [
    'BOUNDARY', 'STREET', 'PARKING', 'PEDESTRIAN_PATH', 'STREET_FURNITURE'
  ];
  // Remove any existing context items (idempotent re-injection)
  MemoryState.stack = MemoryState.stack.filter(i => !i.contextLayer);
  MemoryState.baseCleared = false; // ensure context group renders full park infrastructure

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
      base_area_px: 1,
      solved_area_px: 1,
      transform: { x: 0, y: 0, scale: 1.0, rot: 0 }
    });
  });

  window.renderRemixSVG?.();
  refreshStackUI();
}

// ── MANUAL LAYER PICKER ───────────────────────────────────────────────────────
const KNOWN_LAYERS = [
  'BOUNDARY', 'GREEN_SPACE', 'SHADE', 'WATER_FEATURES',
  'STREET', 'PEDESTRIAN_PATH', 'MAJOR_ATTRACTORS',
  'MINOR_ATTRACTORS', 'UNIQUE_ELEMENTS', 'STREET_FURNITURE', 'PARKING'
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
      // Match any known layer (case-insensitive partial match)
      const match = KNOWN_LAYERS.find(l => gId.toUpperCase().includes(l));
      if (match && !found.includes(match)) found.push(match);
    });

    // Fall back to full list if SVG has no matching groups
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

  // Populate layers when site changes
  siteSelect.addEventListener('change', () => {
    _populateLayerPicker(siteSelect.value);
  });

  // Enable ADD button only when a layer is selected
  layerSelect.addEventListener('change', () => {
    addBtn.disabled = !layerSelect.value;
  });

  // ADD button: push item to stack
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
      base_area_px:  1,
      solved_area_px: 1,
      transform:     { x: 0, y: 0, scale: 1.0, rot: 0 }
    });

    // Ensure SVG is cached for the chosen site
    fetchSVG(siteId).then(() => {
      window.renderRemixSVG?.();
      refreshStackUI();
      setStatus(`Added ${layerId} from ${siteId}`, 'success');
    }).catch(err => setStatus('SVG load failed: ' + err.message, 'error'));

    // Reset picker
    layerSelect.value = '';
    addBtn.disabled = true;
  });

  // Populate layers for the default (first) site on load
  _populateLayerPicker(siteSelect.value);
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

  // Load Pershing Square SVG as default base, then inject identity seed
  try {
    await fetchSVG('PershingSquare');
    _injectBaseContext();
    setStatus('Site loaded — Pershing Square, DTLA', 'success');
  } catch (e) {
    setStatus('SVG load error: ' + e.message, 'error');
  }

  // Wire layer picker (populates layer dropdown for default site)
  _wireLayerPicker();

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
    exportToggle.classList.toggle('export-toggle-on',  autoExportEnabled);
    exportToggle.classList.toggle('export-toggle-off', !autoExportEnabled);
    exportToggle.title = autoExportEnabled
      ? 'Auto-export ON — click to disable'
      : 'Auto-export OFF — click to enable';
  });

  // ── Event: Manual Export ─────────────────────────────────────────────────
  document.getElementById('manual-export-btn')?.addEventListener('click', async () => {
    const btn = document.getElementById('manual-export-btn');
    btn.textContent = '⏳';
    await handleExport('jpg-color');
    await new Promise(r => setTimeout(r, 300));
    await handleExport('svg-color');
    btn.textContent = '📷';
  });

  // ── Event: Diagram Snapshot (Direct Download) ────────────────────────────
  document.getElementById('diagram-snapshot-btn')?.addEventListener('click', async () => {
    const svgEl = document.querySelector('#remix-svg-container svg');
    if (!svgEl) {
      setStatus('No SVG to capture', 'error');
      return;
    }
    const btn = document.getElementById('diagram-snapshot-btn');
    btn.textContent = '⏳';
    
    const clone = svgEl.cloneNode(true);
    clone.setAttribute('viewBox', '0 0 1224 792');
    clone.setAttribute('width', '1224');
    clone.setAttribute('height', '792');
    
    const isLightMode = document.body.classList.contains('light-mode');
    const bgFill = isLightMode ? '#f5f3ef' : '#050505';
    const ctxLine = isLightMode ? '#c0bdb7' : '#444444';
    const bndLine = isLightMode ? '#1a1a1a' : '#ffffff';
    
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
      const origCol = p.getAttribute('data-orig-color');
      if (origCol) {
        p.setAttribute('stroke', origCol); p.style.stroke = origCol;
        const currentFill = p.getAttribute('fill');
        if (currentFill && currentFill !== 'none') p.setAttribute('fill', origCol); p.style.fill = origCol;
      }
    });
    
    const svgData = new XMLSerializer().serializeToString(clone);
    const blob = new Blob([svgData], { type: 'image/svg+xml;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const img = new Image();
    img.onload = () => {
      const canvas = document.createElement('canvas');
      canvas.width = 1224; canvas.height = 792;
      const ctx = canvas.getContext('2d');
      ctx.fillStyle = bgFill;
      ctx.fillRect(0, 0, canvas.width, canvas.height);
      ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
      
      const link = document.createElement('a');
      link.download = `MemoryMachine_Diagram_Snapshot_${Date.now()}.jpg`;
      link.href = canvas.toDataURL('image/jpeg', 0.95);
      link.click();
      
      URL.revokeObjectURL(url);
      btn.textContent = '•';
      setStatus('Diagram Snapshot saved!', 'success');
    };
    img.onerror = () => {
      URL.revokeObjectURL(url);
      btn.textContent = '•';
      setStatus('Failed to capture snapshot', 'error');
    };
    img.src = url;
  });

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

  // ── Event: 3D Camera Controls ────────────────────────────────────────────
  document.getElementById('btn-human-view')?.addEventListener('click', () => {
    if (!threeCamera) return;
    _cameraMode = _cameraMode === 'orbit' ? 'human' : 'orbit';
    const btn = document.getElementById('btn-human-view');
    if (_cameraMode === 'human') {
      btn.textContent = '🚁 Bird\'s Eye';
      // South edge of park looking north — good street-level preview angle
      threeCamera.position.set(PARK_CENTER_X + 12, _hardscapeSurfaceY + 1.7, PARK_CENTER_Z + 18);
      threeCamera.lookAt(PARK_CENTER_X, _hardscapeSurfaceY + 1.0, PARK_CENTER_Z);
    } else {
      btn.textContent = '🧍 Human View';
    }
  });

  document.getElementById('btn-3d-snapshot')?.addEventListener('click', () => {
    if (!threeRenderer || !threeCamera || !threeScene) return;
    threeRenderer.render(threeScene, threeCamera);
    const dataURL = threeRenderer.domElement.toDataURL('image/jpeg', 0.95);
    const link = document.createElement('a');
    link.download = `MemoryMachine_3D_Snapshot_${Date.now()}.jpg`;
    link.href = dataURL;
    link.click();
    setStatus('3D Snapshot saved!', 'success');
  });

  // ── Event: Clear stack ───────────────────────────────────────────────────
  // (Already wired in index.html inline script, but guard for safety)
  document.getElementById('clear-stack-btn')?.addEventListener('click', () => {
    MemoryState.clear();
    clearSceneGeometries();
    _injectBaseContext();
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

// Expose for inline tab-switch script
window.initThreeScene = initThreeScene;

// ── BOOT ─────────────────────────────────────────────────────────────────────
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', init);
} else {
  init();
}
