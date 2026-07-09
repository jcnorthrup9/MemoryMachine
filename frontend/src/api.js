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
export async function startBlenderBuild(rebuildResult, lineart = false) {
  const url = lineart ? '/api/pershing/blender-build?lineart=true' : '/api/pershing/blender-build';
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
