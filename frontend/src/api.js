// Thin wrapper around the two Pershing endpoints (app.py + logic/pershing_api.py).
// Vite's dev-server proxy (vite.config.js) forwards /api/* to the FastAPI
// backend on :8000, so these are same-origin fetches in dev.

export async function getConfig() {
  const res = await fetch('/api/pershing/config');
  if (!res.ok) throw new Error(`config fetch failed: ${res.status}`);
  return res.json();
}

export async function rebuild(params) {
  const res = await fetch('/api/pershing/rebuild', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(params),
  });
  if (!res.ok) throw new Error(`rebuild failed: ${res.status}`);
  return res.json();
}

export async function getSketchInfo() {
  const res = await fetch('/api/pershing/sketch');
  if (!res.ok) throw new Error(`sketch info fetch failed: ${res.status}`);
  return res.json();
}

export async function uploadSketch(file) {
  const body = new FormData();
  body.append('file', file);
  const res = await fetch('/api/pershing/sketch/upload', { method: 'POST', body });
  if (!res.ok) throw new Error(`sketch upload failed: ${res.status}`);
  return res.json();
}

export async function bakePaint(grids) {
  const res = await fetch('/api/pershing/bake', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(grids),
  });
  if (!res.ok) throw new Error(`bake failed: ${res.status}`);
  return res.json();
}

// Kicks off the headless-Blender "build" tier (logic/pershing_blender.py)
// on whatever rebuild result is currently on screen -- pass the exact
// object /rebuild returned, not a re-derived copy, so the built OBJ can't
// drift from what the user is actually looking at.
//
// viewDir/includeRealContext (2026-07-11, Viewport.jsx's "Export Current
// View" vector-linework trigger): only meaningful alongside lineart=true
// (see logic/pershing_blender.py's start_build_job docstring) -- viewDir
// is a [x,y,z] array in the backend's Z-up site-local frame (Viewport.jsx
// derives this from the live OrbitControls camera direction).
export async function startBlenderBuild(rebuildResult, lineart = false, viewDir = null, includeRealContext = false) {
  const params = new URLSearchParams();
  if (lineart) params.set('lineart', 'true');
  if (viewDir) params.set('view_dir', viewDir.join(','));
  if (includeRealContext) params.set('include_real_context', 'true');
  const qs = params.toString();
  const url = qs ? `/api/pershing/blender-build?${qs}` : '/api/pershing/blender-build';
  const res = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(rebuildResult),
  });
  if (!res.ok) throw new Error(`blender build start failed: ${res.status}`);
  return res.json();
}

export async function getBlenderBuildStatus(jobId) {
  const res = await fetch(`/api/pershing/blender-build/${jobId}`);
  if (!res.ok) throw new Error(`blender build status fetch failed: ${res.status}`);
  return res.json();
}

// Grows the Space Colonization pedestrian circulation network against the
// given terrain params -- synchronous (see logic/pershing_api.py's
// grow_network() docstring for why this doesn't need the blender-build
// tier's async job-polling pattern).
export async function growNetwork(rebuildParams, networkParams) {
  const res = await fetch('/api/pershing/grow-network', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ rebuild: rebuildParams, network: networkParams }),
  });
  if (!res.ok) throw new Error(`grow network failed: ${res.status}`);
  return res.json();
}

// Grounded Q&A for the live juror chat -- context is whatever live design
// state (params/network params/last rebuild+network summaries) the caller
// already has client-side, forwarded as grounding for the prompt.
export async function jurorChat(message, context) {
  const res = await fetch('/api/pershing/juror-chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message, context }),
  });
  if (!res.ok) throw new Error(`juror chat failed: ${res.status}`);
  return res.json();
}

// Diagram Input mode (see DiagramInputPanel.jsx) -- a separate design-input
// mechanism from PaintOverlay's freehand painting, reading colors off an
// existing legacy-diagram export instead. listLegacyDiagrams/previewLegacyImport
// are read-only; committing a previewed diagram reuses bakePaint() above
// unchanged, so there's no separate "confirm" wrapper here.
export async function listLegacyDiagrams() {
  const res = await fetch('/api/pershing/legacy-diagrams');
  if (!res.ok) throw new Error(`legacy diagram list fetch failed: ${res.status}`);
  return res.json();
}

export async function previewLegacyImport(filename) {
  const res = await fetch('/api/pershing/legacy-diagrams/preview', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ filename }),
  });
  if (!res.ok) throw new Error(`legacy diagram preview failed: ${res.status}`);
  return res.json();
}

// Bay-grid program placement (logic/program_placement.py): which 27ft bays
// each NEEDED/Suggested program from data/program_requirements.json claimed,
// against whatever masks are currently painted/imported. Recomputed server-
// side on every call -- no params needed, unlike rebuild()'s slider state.
export async function getProgramZones() {
  const res = await fetch('/api/pershing/program-zones');
  if (!res.ok) throw new Error(`program zones fetch failed: ${res.status}`);
  return res.json();
}

// ARCHIVE tab -- server-side persisted build snapshots (outputs/pershing_archive/),
// distinct from App.jsx's client-side-only "Save Build" file download. Same
// memory-machine-build-v1 snapshot shape either way.
export async function saveToArchive(snapshot, label) {
  const res = await fetch('/api/pershing/archive', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ label, snapshot }),
  });
  if (!res.ok) throw new Error(`archive save failed: ${res.status}`);
  return res.json();
}

export async function listArchive() {
  const res = await fetch('/api/pershing/archive');
  if (!res.ok) throw new Error(`archive list fetch failed: ${res.status}`);
  return res.json();
}

export async function getArchivedBuild(filename) {
  const res = await fetch(`/api/pershing/archive/${encodeURIComponent(filename)}`);
  if (!res.ok) throw new Error(`archived build fetch failed: ${res.status}`);
  return res.json();
}

export async function deleteArchivedBuild(filename) {
  const res = await fetch(`/api/pershing/archive/${encodeURIComponent(filename)}`, { method: 'DELETE' });
  if (!res.ok) throw new Error(`archived build delete failed: ${res.status}`);
  return res.json();
}
