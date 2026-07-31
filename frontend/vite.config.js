import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// FastAPI backend (app.py, logic/pershing_api.py). History: :8001 (temp,
// 2026-07-11) -> :8000 (2026-07-13) -> :8002 -> :8004 -> :8005 (2026-07-13/14,
// chased a recurring Windows ghost-listener bug: `Stop-Process -Force` on
// overlapping `uvicorn --reload` processes left stale "LISTENING" socket
// entries for PIDs that no longer existed, intercepting requests ahead of
// the real freshly-started process). Reverted back to :8000 on 2026-07-16
// after a Windows update forced a reboot -- verified clean post-reboot
// (POST /api/pershing/rebuild returns fresh fields, e.g. exactly 607
// canopy_beam elements matching the known-good 07-13 count). If the ghost
// listener ever recurs, hop to an unused port again as before; :8001 is
// app_blender.py's own dedicated port, :8006 is diagram_tool/'s own
// dedicated port (see diagram_tool/app.py) -- don't reuse either here.
//
// Shared between `server.proxy` (npm run dev) and `preview.proxy` (npm run
// preview, serving the `vite build` output) -- vite preview doesn't inherit
// the dev server's proxy config at all, so without this a production build
// would 404 on every one of these paths.
const API_PROXY = {
  '/api': 'http://127.0.0.1:8000',
  // Sketch photo the paint canvas loads as its background -- proxied
  // same-origin (rather than the absolute-URL pattern StaticContext.jsx
  // uses for the OBJ) so canvas.drawImage()+getImageData() sampling in
  // PaintOverlay.jsx never hits a cross-origin "tainted canvas" error.
  '/pershing-sketch': 'http://127.0.0.1:8000',
  // Every other static mount app.py exposes.
  '/blender-headless-output': 'http://127.0.0.1:8000',
  '/legacy-diagrams': 'http://127.0.0.1:8000',
  '/comfy-output': 'http://127.0.0.1:8000',
  '/pershing-context': 'http://127.0.0.1:8000',
  '/models': 'http://127.0.0.1:8000',
  '/static': 'http://127.0.0.1:8000',
  '/archive': 'http://127.0.0.1:8000',
};

export default defineConfig({
  plugins: [react()],
  server: {
    host: '127.0.0.1', // this PC's "localhost" DNS resolution is broken -- bind the literal loopback address, not the hostname
    port: 5174, // moved off 5173 2026-07-30 -- see start_metabolizer.bat
    proxy: API_PROXY,
  },
  preview: {
    host: '127.0.0.1',
    port: 4173,
    proxy: API_PROXY,
  },
});
