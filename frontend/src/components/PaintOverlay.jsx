import { useCallback, useEffect, useRef, useState } from 'react';
import { getSketchInfo, uploadSketch, bakePaint } from '../api.js';

// Mirrors blender_cockpit.py's image-paint mechanism: a sketch photo as
// canvas background, five paintable category layers baked into the same
// weight/mask grids TerracingEngine consumes. canyon is a continuous
// weight (black tint, alpha IS the weight); the other four are boolean
// zone masks (thresholded at bake time), each with its own tint so
// overlapping strokes stay visually distinguishable.
const CATEGORIES = [
  { key: 'canyon', label: 'Canyon', color: '#111111' },
  { key: 'hardscape', label: 'Hardscape', color: '#2f6fd6' },
  { key: 'water_shade', label: 'Water/Shade', color: '#22b8c8' },
  { key: 'greenscape', label: 'Greenscape', color: '#2fae4a' },
  { key: 'amenity_resting', label: 'Amenity/Resting', color: '#e08a2f' },
];
const BOOLEAN_THRESHOLD = 0.4;

// sketch_weight_mapper.py's calibrated convention (verified 2026-07-04
// against a real hand-labeled sketch): flip_x=True, flip_y=True, standard
// top-down row order -- real_x = (1 - col/w) * W, real_y = (1 - row/h) * L.
// Inverted here (real feet -> pixel) to sample the painted canvas per
// engine grid-cell instead of per-pixel.
function sampleGrid(imageData, w, h, nx, nz, siteWidthFt, siteLengthFt) {
  const cellWpx = w / nx;
  const cellHpx = h / nz;
  const grid = [];
  for (let gx = 0; gx < nx; gx++) {
    const row = [];
    const realX = (gx + 0.5) * (siteWidthFt / nx);
    const colCenter = w * (1 - realX / siteWidthFt);
    const c0 = Math.max(0, Math.floor(colCenter - cellWpx / 2));
    const c1 = Math.min(w, Math.ceil(colCenter + cellWpx / 2));
    for (let gy = 0; gy < nz; gy++) {
      const realY = (gy + 0.5) * (siteLengthFt / nz);
      const rowCenter = h * (1 - realY / siteLengthFt);
      const r0 = Math.max(0, Math.floor(rowCenter - cellHpx / 2));
      const r1 = Math.min(h, Math.ceil(rowCenter + cellHpx / 2));
      let sum = 0;
      let n = 0;
      for (let r = r0; r < r1; r++) {
        for (let c = c0; c < c1; c++) {
          sum += imageData.data[(r * w + c) * 4 + 3];
          n++;
        }
      }
      row.push(n > 0 ? sum / n / 255 : 0);
    }
    grid.push(row);
  }
  return grid;
}

export default function PaintOverlay({ config, initialCategory, onClose, onBaked, log }) {
  const [category, setCategory] = useState(initialCategory ?? 'canyon');
  const [sketchUrl, setSketchUrl] = useState(null);
  const [brushSize, setBrushSize] = useState(24);
  const [erase, setErase] = useState(false);
  const [baking, setBaking] = useState(false);
  const [imgSize, setImgSize] = useState(null);

  const canvasRef = useRef(null); // visible, composited
  const imgRef = useRef(null);
  const layersRef = useRef({}); // category -> offscreen canvas
  const paintingRef = useRef(false);
  const lastPtRef = useRef(null);

  const ensureLayers = useCallback((w, h) => {
    for (const c of CATEGORIES) {
      let layer = layersRef.current[c.key];
      if (!layer || layer.width !== w || layer.height !== h) {
        layer = document.createElement('canvas');
        layer.width = w;
        layer.height = h;
        layersRef.current[c.key] = layer;
      }
    }
  }, []);

  const composite = useCallback(() => {
    const canvas = canvasRef.current;
    const img = imgRef.current;
    if (!canvas || !img || !imgSize) return;
    const ctx = canvas.getContext('2d');
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
    for (const c of CATEGORIES) {
      const layer = layersRef.current[c.key];
      if (!layer) continue;
      ctx.globalAlpha = 0.65;
      ctx.drawImage(layer, 0, 0, canvas.width, canvas.height);
    }
    ctx.globalAlpha = 1;
  }, [imgSize]);

  // Load current sketch info + image on mount.
  useEffect(() => {
    let cancelled = false;
    getSketchInfo()
      .then((info) => {
        if (cancelled || !info.url) return;
        setSketchUrl(`${info.url}?t=${Date.now()}`);
      })
      .catch((err) => log?.(String(err), 'error'));
    return () => {
      cancelled = true;
    };
  }, [log]);

  useEffect(() => {
    if (!sketchUrl) return;
    const img = new Image();
    img.onload = () => {
      imgRef.current = img;
      const w = img.naturalWidth;
      const h = img.naturalHeight;
      ensureLayers(w, h);
      setImgSize({ w, h });
    };
    img.onerror = () => log?.('failed to load sketch image', 'error');
    img.src = sketchUrl;
  }, [sketchUrl, ensureLayers, log]);

  useEffect(() => {
    if (!imgSize) return;
    const canvas = canvasRef.current;
    canvas.width = imgSize.w;
    canvas.height = imgSize.h;
    composite();
  }, [imgSize, composite]);

  const stamp = useCallback(
    (x, y) => {
      const layer = layersRef.current[category];
      if (!layer) return;
      const ctx = layer.getContext('2d');
      ctx.globalCompositeOperation = erase ? 'destination-out' : 'source-over';
      const tint = CATEGORIES.find((c) => c.key === category)?.color ?? '#000000';
      const grad = ctx.createRadialGradient(x, y, 0, x, y, brushSize);
      grad.addColorStop(0, erase ? 'rgba(0,0,0,0.9)' : `${tint}dd`);
      grad.addColorStop(1, erase ? 'rgba(0,0,0,0)' : `${tint}00`);
      ctx.fillStyle = grad;
      ctx.beginPath();
      ctx.arc(x, y, brushSize, 0, Math.PI * 2);
      ctx.fill();
    },
    [category, brushSize, erase],
  );

  const canvasPoint = useCallback((e) => {
    const canvas = canvasRef.current;
    const rect = canvas.getBoundingClientRect();
    const scaleX = canvas.width / rect.width;
    const scaleY = canvas.height / rect.height;
    return { x: (e.clientX - rect.left) * scaleX, y: (e.clientY - rect.top) * scaleY };
  }, []);

  const handlePointerDown = useCallback(
    (e) => {
      paintingRef.current = true;
      const p = canvasPoint(e);
      lastPtRef.current = p;
      stamp(p.x, p.y);
      composite();
    },
    [canvasPoint, stamp, composite],
  );

  const handlePointerMove = useCallback(
    (e) => {
      if (!paintingRef.current) return;
      const p = canvasPoint(e);
      const last = lastPtRef.current ?? p;
      const dist = Math.hypot(p.x - last.x, p.y - last.y);
      const steps = Math.max(1, Math.ceil(dist / (brushSize / 3)));
      for (let i = 1; i <= steps; i++) {
        const t = i / steps;
        stamp(last.x + (p.x - last.x) * t, last.y + (p.y - last.y) * t);
      }
      lastPtRef.current = p;
      composite();
    },
    [canvasPoint, stamp, composite, brushSize],
  );

  const handlePointerUp = useCallback(() => {
    paintingRef.current = false;
    lastPtRef.current = null;
  }, []);

  const handleClear = useCallback(() => {
    const layer = layersRef.current[category];
    if (!layer) return;
    layer.getContext('2d').clearRect(0, 0, layer.width, layer.height);
    composite();
  }, [category, composite]);

  const handleUpload = useCallback(
    async (e) => {
      const file = e.target.files?.[0];
      e.target.value = '';
      if (!file) return;
      try {
        const info = await uploadSketch(file);
        log?.(`sketch uploaded: ${info.filename}`);
        // New photo -> old painted marks no longer correspond to anything.
        for (const c of CATEGORIES) {
          const layer = layersRef.current[c.key];
          if (layer) layer.getContext('2d').clearRect(0, 0, layer.width, layer.height);
        }
        setSketchUrl(`${info.url}?t=${Date.now()}`);
      } catch (err) {
        log?.(String(err), 'error');
      }
    },
    [log],
  );

  const handleBake = useCallback(async () => {
    if (!imgSize) return;
    setBaking(true);
    try {
      const { w, h } = imgSize;
      const { nx, nz, site_width_ft: W, site_length_ft: L } = config;
      const grids = {};
      for (const c of CATEGORIES) {
        const layer = layersRef.current[c.key];
        const data = layer.getContext('2d').getImageData(0, 0, w, h);
        const grid = sampleGrid(data, w, h, nx, nz, W, L);
        grids[c.key] = c.key === 'canyon' ? grid : grid.map((row) => row.map((v) => v > BOOLEAN_THRESHOLD));
      }
      const result = await bakePaint(grids);
      log?.(`baked: ${JSON.stringify(result.counts)}`);
      await onBaked?.();
    } catch (err) {
      log?.(String(err), 'error');
    } finally {
      setBaking(false);
    }
  }, [imgSize, config, log, onBaked]);

  return (
    <div className="fixed inset-0 z-50 bg-black/80 flex items-center justify-center p-6">
      <div className="bg-surface border border-border max-w-[90vw] max-h-[90vh] flex flex-col overflow-hidden">
        <div className="flex items-center justify-between p-container border-b border-border">
          <h3 className="font-headline-md text-headline-md text-primary">PAINT SKETCH</h3>
          <button
            onClick={onClose}
            className="px-3 py-1 border border-border font-mono-sm text-mono-sm uppercase text-on-surface-variant hover:text-on-surface"
          >
            Close
          </button>
        </div>

        <div className="flex flex-1 overflow-hidden">
          <div className="flex-1 overflow-auto flex items-center justify-center bg-background p-4">
            {sketchUrl ? (
              <canvas
                ref={canvasRef}
                className="max-w-full max-h-full cursor-crosshair border border-border"
                onPointerDown={handlePointerDown}
                onPointerMove={handlePointerMove}
                onPointerUp={handlePointerUp}
                onPointerLeave={handlePointerUp}
              />
            ) : (
              <p className="font-mono-sm text-mono-sm text-on-surface-variant">
                No sketch loaded -- upload one to begin painting.
              </p>
            )}
          </div>

          <aside className="w-64 border-l border-border p-container space-y-4 overflow-y-auto shrink-0">
            <div className="space-y-2">
              <label className="font-mono-sm text-mono-sm text-on-surface-variant uppercase block">
                Upload Sketch Photo
              </label>
              <input
                type="file"
                accept="image/*"
                onChange={handleUpload}
                className="font-mono-sm text-[11px] text-on-surface-variant w-full"
              />
            </div>

            <div className="space-y-2">
              <label className="font-mono-sm text-mono-sm text-on-surface-variant uppercase block">
                Category
              </label>
              <div className="grid grid-cols-1 gap-1">
                {CATEGORIES.map((c) => (
                  <button
                    key={c.key}
                    onClick={() => setCategory(c.key)}
                    className={`px-3 py-2 border font-mono-sm text-mono-sm uppercase text-left flex items-center gap-2 ${
                      category === c.key
                        ? 'border-accent text-accent'
                        : 'border-border text-on-surface-variant hover:text-on-surface'
                    }`}
                  >
                    <span className="inline-block w-3 h-3" style={{ backgroundColor: c.color }} />
                    {c.label}
                  </button>
                ))}
              </div>
            </div>

            <div className="space-y-2">
              <div className="flex justify-between font-mono-sm text-mono-sm">
                <span className="text-on-surface-variant uppercase">Brush Size</span>
                <span className="text-accent">{brushSize}px</span>
              </div>
              <input
                type="range"
                min={4}
                max={80}
                step={1}
                value={brushSize}
                onChange={(e) => setBrushSize(parseInt(e.target.value, 10))}
                className="w-full h-[1px] bg-border appearance-none cursor-pointer accent-accent"
              />
            </div>

            <label className="flex items-center gap-2 font-mono-sm text-mono-sm text-on-surface-variant uppercase cursor-pointer">
              <input type="checkbox" checked={erase} onChange={(e) => setErase(e.target.checked)} />
              Erase
            </label>

            <button
              onClick={handleClear}
              className="w-full px-3 py-2 border border-border font-mono-sm text-mono-sm uppercase text-on-surface-variant hover:text-on-surface"
            >
              Clear {CATEGORIES.find((c) => c.key === category)?.label}
            </button>

            <button
              onClick={handleBake}
              disabled={baking || !imgSize}
              className="w-full py-3 bg-accent text-background font-mono-sm text-mono-sm font-bold uppercase tracking-widest hover:brightness-110 transition-all active:scale-[0.98] disabled:opacity-50"
            >
              {baking ? 'BAKING...' : 'BAKE + REBUILD'}
            </button>
          </aside>
        </div>
      </div>
    </div>
  );
}
