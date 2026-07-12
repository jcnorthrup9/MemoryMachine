import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: {
    host: '127.0.0.1', // this PC's "localhost" DNS resolution is broken -- bind the literal loopback address, not the hostname
    port: 5173,
    proxy: {
      // FastAPI backend (app.py, logic/pershing_api.py) normally runs on
      // :8000 -- temporarily repointed to :8001 (2026-07-11) because :8000
      // has a stale OS-level TCP listener (PID 59028) that answers
      // requests with pre-restart data but has no matching process Windows
      // can find or kill (confirmed via Get-Process/taskkill/PowerShell
      // Stop-Process, all no-ops) -- a reboot should clear it. Revert this
      // back to :8000 once that's confirmed fixed.
      '/api': 'http://127.0.0.1:8001',
      // Sketch photo the paint canvas loads as its background -- proxied
      // same-origin (rather than the absolute-URL pattern StaticContext.jsx
      // uses for the OBJ) so canvas.drawImage()+getImageData() sampling in
      // PaintOverlay.jsx never hits a cross-origin "tainted canvas" error.
      '/pershing-sketch': 'http://127.0.0.1:8001',
      // Every other static mount app.py exposes (2026-07-11 fix): this list
      // was previously incomplete (only /api and /pershing-sketch were
      // proxied), which silently broke anything that fetched one of these
      // paths as a relative URL through the Vite dev server -- confirmed
      // via a real browser test: fetch('/blender-headless-output/...svg')
      // returned this app's own index.html (Vite's SPA fallback), not the
      // SVG, since the dev server has no route for that path itself.
      // BlenderBuild.jsx/LineArtOverlay.jsx worked around the SAME gap by
      // hardcoding an absolute 'http://127.0.0.1:8000' BLENDER_HOST
      // constant instead of relying on the proxy -- but that's now ALSO
      // stale (backend has been on :8001 all session, see the /api entry's
      // own comment above), meaning those two components were silently
      // broken too, just never exercised in a way that surfaced it. Fixed
      // properly here (route everything through the proxy) rather than
      // patching a second/third hardcoded port constant -- see this
      // session's paintCategories.js extraction for the same "duplicated
      // constant causes drift" lesson already learned once.
      '/blender-headless-output': 'http://127.0.0.1:8001',
      '/legacy-diagrams': 'http://127.0.0.1:8001',
      '/comfy-output': 'http://127.0.0.1:8001',
      '/pershing-context': 'http://127.0.0.1:8001',
      '/models': 'http://127.0.0.1:8001',
      '/static': 'http://127.0.0.1:8001',
      '/archive': 'http://127.0.0.1:8001',
    },
  },
});
