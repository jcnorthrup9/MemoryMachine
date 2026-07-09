import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      // FastAPI backend (app.py, logic/pershing_api.py) runs on :8000
      '/api': 'http://127.0.0.1:8000',
      // Sketch photo the paint canvas loads as its background -- proxied
      // same-origin (rather than the absolute-URL pattern StaticContext.jsx
      // uses for the OBJ) so canvas.drawImage()+getImageData() sampling in
      // PaintOverlay.jsx never hits a cross-origin "tainted canvas" error.
      '/pershing-sketch': 'http://127.0.0.1:8000',
    },
  },
});
