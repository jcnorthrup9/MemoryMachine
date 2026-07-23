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

// attractorPoints (2026-07-16 program-placement correlation logic):
// optional -- only logic/legacy_diagram_bridge.py's diagram-preview flow has
// an equivalent signal (freehand painting has no discrete-point concept).
// Spreading `undefined` here is dropped by JSON.stringify, so the backend's
// BakeGrids default (empty per-category lists) applies unchanged when omitted.
export async function bakePaint(grids, attractorPoints) {
  const res = await fetch('/api/pershing/bake', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ ...grids, attractor_points: attractorPoints }),
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

// "Export Current View" PNG (Viewport.jsx) -- posts the canvas's own
// toDataURL() output straight to the backend so it lands in
// data/PershingMetabolizer/parkSVG/remixedGeneratedPNGs/ (same home as the
// vector-export SVGs), not the browser's Downloads folder. No client-side
// download/dialog at all -- see app.py's pershing_export_view_png().
export async function exportViewPng(dataUrl, filename) {
  const res = await fetch('/api/pershing/export-view-png', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ filename, data: dataUrl }),
  });
  if (!res.ok) throw new Error(`view PNG export failed: ${res.status}`);
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

// Generates the organic panelized canopy roof + branching supports against
// the given terrain params -- synchronous explicit action, same reasoning
// as growNetwork() above (see logic/pershing_api.py's generate_canopy()
// docstring).
export async function generateCanopy(rebuildParams, canopyParams) {
  const res = await fetch('/api/pershing/generate-canopy', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ rebuild: rebuildParams, canopy: canopyParams }),
  });
  if (!res.ok) throw new Error(`generate canopy failed: ${res.status}`);
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

// "The Metabolist" -- on-demand qualitative critique. spatialSummary is the
// list[str] rebuild() already returns as data.spatial_summary -- forwarded
// verbatim, not recomputed here, same as jurorChat()'s context above.
export async function critiqueDesign(spatialSummary) {
  const res = await fetch('/api/pershing/critique', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ spatial_summary: spatialSummary }),
  });
  if (!res.ok) throw new Error(`critique failed: ${res.status}`);
  return res.json();
}

// Diagram Input mode (2026-07-16: the "Diagram" tab inside PaintOverlay.jsx's
// unified Paint dialog, folded in from the former standalone
// DiagramInputPanel.jsx) -- reads colors off an existing legacy-diagram
// export instead of freehand strokes. listLegacyDiagrams/previewLegacyImport
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

// SPATIALIZE tab (2026-07-23) -- 2D authoring ported natively into this
// app. generateSpatialSeed() hits the root app's own /api/generate
// (reachable here too since it's the same FastAPI process the /api proxy
// prefix already covers) -- same AI-curated layer-pick endpoint
// static/main.js's GEN button calls, now also driving this app's live
// canvas. spatializePreview()/getDeficitWeights() are new
// logic/pershing_api.py endpoints: the former previews a live (in-memory,
// not yet saved) spatial_seed through the same role-inference +
// occlusion-aware rasterization pipeline preview_2d_generation() uses for
// a saved one; the latter exposes the real amenity-deficit-hotspot signal
// directly for a live overlay while composing.
// Same endpoint static/main.js's fetchSVG() uses -- returns the raw
// precedent-site SVG text (BOUNDARY/GREEN_SPACE/HARDSCAPE/etc. groups) that
// spatializerEngine.js's render()/getProgramStats() parse directly.
export async function fetchSiteSVG(siteId) {
  const res = await fetch(`/api/diagram-data/${siteId}`);
  const data = await res.json();
  if (data.error) throw new Error(data.error);
  return data.svg;
}

export async function generateSpatialSeed(prompt) {
  const res = await fetch('/api/generate', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ prompt }),
  });
  if (!res.ok) throw new Error(`generate failed: ${res.status}`);
  return res.json();
}

export async function spatializePreview(spatialSeed) {
  const res = await fetch('/api/pershing/spatialize-preview', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ spatial_seed: spatialSeed }),
  });
  if (!res.ok) throw new Error(`spatialize preview failed: ${res.status}`);
  return res.json();
}

export async function getDeficitWeights() {
  const res = await fetch('/api/pershing/deficit-weights');
  if (!res.ok) throw new Error(`deficit weights fetch failed: ${res.status}`);
  return res.json();
}

// Import a saved 2D-app ("Digital Palimpsest", port 8000) generation
// (2026-07-22) -- same read-only list/preview shape as the Diagram Input
// mode above, but the source is a structured spatial_seed record
// (site/layerId/transform per layer), not a rasterized/vector diagram
// export, so no color-classification step happens server-side at all (see
// logic/pershing_api.py's preview_2d_generation() docstring). Committing a
// previewed generation reuses bakePaint() above unchanged.
export async function list2DGenerations() {
  const res = await fetch('/api/pershing/2d-generations');
  if (!res.ok) throw new Error(`2D generation list fetch failed: ${res.status}`);
  return res.json();
}

export async function preview2DGeneration(filename) {
  const res = await fetch('/api/pershing/2d-generations/preview', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ filename }),
  });
  if (!res.ok) throw new Error(`2D generation preview failed: ${res.status}`);
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

// Server-side persisted build snapshots (outputs/pershing_archive/) -- used
// by both the ARCHIVE tab's "Save Current Build" (with a user label) and
// App.jsx's toolbar "Save Build" (no label prompt, passes ''). Same
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
