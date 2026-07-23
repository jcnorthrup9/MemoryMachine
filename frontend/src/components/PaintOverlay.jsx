import { useCallback, useEffect, useRef, useState } from 'react';
import {
  getSketchInfo, uploadSketch, bakePaint, listLegacyDiagrams, previewLegacyImport,
  list2DGenerations, preview2DGeneration,
} from '../api.js';
import { PAINT_CATEGORIES as CATEGORIES } from '../paintCategories.js';

// Unified "Paint" dialog (2026-07-16, merging what used to be two separate
// entry points -- this component's own freehand sketch-painting, and the
// former DiagramInputPanel.jsx's "import an exported diagram's colors
// instead" mode). One button opens this; a Source tab inside picks which
// input mechanism feeds the same live paint-mask grids. Both modes still
// commit through the exact same bakePaint() endpoint (bake() doesn't care
// about a grid's source, only its shape), so there's still no parallel
// commit path to keep in sync -- only the UI entry point is unified now.
//
// Mirrors blender_cockpit.py's image-paint mechanism: a sketch photo as
// canvas background, seven paintable category layers (see ../paintCategories.js)
// baked into the same weight/mask grids TerracingEngine/CanopyEngine consume.
// canyon and canopy are continuous weights (alpha IS the weight); the other
// five are boolean zone masks (thresholded at bake time), each with its own
// tint so overlapping strokes stay visually distinguishable.
const BOOLEAN_THRESHOLD = 0.4;
const PREVIEW_CELL_PX = 6;

// X is NOT flipped (real_x = col/w * W) -- Y still is (real_y = (1 - row/h) * L).
// Fixed 2026-07-10: this previously mirrored X the same way sketch_weight_mapper.py's
// flip_x=True does (inherited from that module's photo-labeling convention, which
// applies to a different ingestion path), but that's inconsistent with how
// Viewport.jsx's toThree() places real x on screen (it doesn't mirror X at all) --
// confirmed empirically by tracing a mark drawn near the canvas's left edge through
// to its rendered 3D position: with the old flip it landed on the 3D view's RIGHT
// side, exactly the "flipped along the long axis" symptom reported. Y's own
// round-trip was independently confirmed already consistent, so only X changes here.
function sampleGrid(imageData, w, h, nx, nz, siteWidthFt, siteLengthFt) {
  const cellWpx = w / nx;
  const cellHpx = h / nz;
  const grid = [];
  for (let gx = 0; gx < nx; gx++) {
    const row = [];
    const realX = (gx + 0.5) * (siteWidthFt / nx);
    const colCenter = w * (realX / siteWidthFt);
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

// Ported from DiagramInputPanel.jsx unchanged.
function drawDiagramPreview(canvas, grids) {
  if (!canvas || !grids) return;
  const nx = grids.hardscape.length;
  const nz = grids.hardscape[0].length;
  canvas.width = nx * PREVIEW_CELL_PX;
  canvas.height = nz * PREVIEW_CELL_PX;
  const ctx = canvas.getContext('2d');
  ctx.fillStyle = '#000000';
  ctx.fillRect(0, 0, canvas.width, canvas.height);
  // Same category order as the sketch canvas's own composite() below --
  // later entries draw on top, matching how overlapping painted strokes
  // already resolve there.
  for (const cat of CATEGORIES) {
    if (cat.key === 'canyon' || cat.key === 'canopy') continue; // continuous weights, not boolean regions -- no fill color to preview here
    const grid = grids[cat.key];
    if (!grid) continue;
    ctx.fillStyle = cat.color;
    for (let gx = 0; gx < nx; gx++) {
      for (let gy = 0; gy < nz; gy++) {
        if (!grid[gx][gy]) continue;
        // row 0 at top = ymax (5th St), matching vector_export.py's
        // STREET_LABELS convention and ingest_legacy_diagram.py's own
        // render_debug_preview.
        const py = nz - 1 - gy;
        ctx.fillRect(gx * PREVIEW_CELL_PX, py * PREVIEW_CELL_PX, PREVIEW_CELL_PX, PREVIEW_CELL_PX);
      }
    }
  }
}

const SOURCE_TABS = [
  { key: 'sketch', label: 'Sketch' },
  { key: 'diagram', label: 'Diagram' },
  { key: '2d-gen', label: '2D Generations' },
];

export default function PaintOverlay({ config, initialCategory, onClose, onBaked, log }) {
  const [source, setSource] = useState('sketch');

  // ---- Sketch mode state ----
  const [category, setCategory] = useState(initialCategory ?? 'canyon');
  const [sketchUrl, setSketchUrl] = useState(null);
  const [brushSize, setBrushSize] = useState(24);
  const [erase, setErase] = useState(false);
  const [baking, setBaking] = useState(false);
  const [imgSize, setImgSize] = useState(null);
  // Mirrors whatever's sent to log(), but rendered inside this modal too --
  // the modal is a fullscreen fixed inset-0 z-50 overlay, so App.jsx's
  // LogPanel (rendered underneath it in <main>) is invisible while this is
  // open. Without this, upload/bake/load errors fired silently as far as
  // the user could tell.
  const [modalError, setModalError] = useState(null);

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
      .catch((err) => {
        log?.(String(err), 'error');
        setModalError(String(err));
      });
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
    img.onerror = () => {
      log?.('failed to load sketch image', 'error');
      setModalError('failed to load sketch image');
    };
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

  // closeAfterBake: the explicit "Bake Painted Sketch" button closes the
  // overlay afterward (original behavior); auto-bake-while-painting (see
  // scheduleAutoBake / handlePointerUp below) must NOT close it -- the user
  // is still actively painting, closing mid-stroke would be disruptive.
  // onBaked itself only triggers the parent rebuild now (App.jsx no longer
  // closes the overlay there), so this function fully owns whether the
  // overlay closes.
  const handleBake = useCallback(async (closeAfterBake = false) => {
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
        grids[c.key] = (c.key === 'canyon' || c.key === 'canopy')
          ? grid
          : grid.map((row) => row.map((v) => v > BOOLEAN_THRESHOLD));
      }
      const result = await bakePaint(grids);
      log?.(`baked: ${JSON.stringify(result.counts)}`);
      setModalError(null);
      await onBaked?.();
      if (closeAfterBake) onClose?.();
    } catch (err) {
      log?.(String(err), 'error');
      setModalError(String(err));
    } finally {
      setBaking(false);
    }
  }, [imgSize, config, log, onBaked, onClose]);

  // Auto-bake while painting (2026-07-10): the canyon-excavation real-slab
  // removal previously only updated on an explicit "Bake Painted Sketch"
  // click, which read as "painting doesn't do anything by default" --
  // debounce a bake 600ms after the last stroke ends (handlePointerUp),
  // canceling if a new stroke starts first (handlePointerDown), so it fires
  // once per pause in painting rather than on every pointer-move.
  const autoBakeTimerRef = useRef(null);
  const cancelAutoBake = useCallback(() => {
    if (autoBakeTimerRef.current) {
      clearTimeout(autoBakeTimerRef.current);
      autoBakeTimerRef.current = null;
    }
  }, []);
  const scheduleAutoBake = useCallback(() => {
    cancelAutoBake();
    autoBakeTimerRef.current = setTimeout(() => {
      autoBakeTimerRef.current = null;
      handleBake(false);
    }, 600);
  }, [cancelAutoBake, handleBake]);
  useEffect(() => cancelAutoBake, [cancelAutoBake]); // clear pending timer on unmount

  const handlePointerDown = useCallback(
    (e) => {
      cancelAutoBake(); // still actively painting -- don't bake mid-stroke
      paintingRef.current = true;
      const p = canvasPoint(e);
      lastPtRef.current = p;
      stamp(p.x, p.y);
      composite();
    },
    [canvasPoint, stamp, composite, cancelAutoBake],
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
    if (!paintingRef.current) return;
    paintingRef.current = false;
    lastPtRef.current = null;
    scheduleAutoBake();
  }, [scheduleAutoBake]);

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
        setModalError(null);
        // New photo -> old painted marks no longer correspond to anything.
        for (const c of CATEGORIES) {
          const layer = layersRef.current[c.key];
          if (layer) layer.getContext('2d').clearRect(0, 0, layer.width, layer.height);
        }
        setSketchUrl(`${info.url}?t=${Date.now()}`);
      } catch (err) {
        log?.(String(err), 'error');
        setModalError(String(err));
      }
    },
    [log],
  );

  // ---- Diagram mode state (ported from the former DiagramInputPanel.jsx) ----
  const [diagrams, setDiagrams] = useState([]);
  const [loadingList, setLoadingList] = useState(true);
  const [selectedDiagram, setSelectedDiagram] = useState(null);
  const [diagramPreview, setDiagramPreview] = useState(null); // { filename, grids, counts }
  const [loadingDiagramPreview, setLoadingDiagramPreview] = useState(false);
  const [diagramBaking, setDiagramBaking] = useState(false);
  const diagramCanvasRef = useRef(null);

  useEffect(() => {
    if (source !== 'diagram') return;
    let cancelled = false;
    setLoadingList(true);
    listLegacyDiagrams()
      .then((list) => {
        if (!cancelled) setDiagrams(list);
      })
      .catch((err) => log?.(String(err), 'error'))
      .finally(() => {
        if (!cancelled) setLoadingList(false);
      });
    return () => {
      cancelled = true;
    };
  }, [source, log]);

  useEffect(() => {
    drawDiagramPreview(diagramCanvasRef.current, diagramPreview?.grids);
  }, [diagramPreview]);

  const handleSelectDiagram = useCallback(
    async (filename) => {
      setSelectedDiagram(filename);
      setDiagramPreview(null);
      setLoadingDiagramPreview(true);
      try {
        const result = await previewLegacyImport(filename);
        setDiagramPreview(result);
      } catch (err) {
        log?.(String(err), 'error');
      } finally {
        setLoadingDiagramPreview(false);
      }
    },
    [log],
  );

  const handleBakeDiagram = useCallback(async () => {
    if (!diagramPreview) return;
    setDiagramBaking(true);
    try {
      const result = await bakePaint(diagramPreview.grids, diagramPreview.attractor_points);
      log?.(`baked from diagram ${diagramPreview.filename}: ${JSON.stringify(result.counts)}`);
      await onBaked?.();
      onClose?.();
    } catch (err) {
      log?.(String(err), 'error');
    } finally {
      setDiagramBaking(false);
    }
  }, [diagramPreview, log, onBaked, onClose]);

  // ---- 2D Generations mode state ----
  // Imports a saved root-app (port 8000) /api/generate call -- structured
  // site/layerId/transform data, not a rasterized image, so the backend
  // (logic/pershing_api.py's preview_2d_generation()) reuses the exact same
  // rasterization pipeline remix_precedent() already uses, no SVG/pixel
  // parsing involved. Same list/preview/bake shape as Diagram mode above,
  // just no thumbnail image (there isn't one) -- the prompt text stands in.
  const [generations, setGenerations] = useState([]);
  const [loadingGenList, setLoadingGenList] = useState(true);
  const [selectedGeneration, setSelectedGeneration] = useState(null);
  const [generationPreview, setGenerationPreview] = useState(null); // { filename, prompt, narrative, grids, counts, attractor_points }
  const [loadingGenerationPreview, setLoadingGenerationPreview] = useState(false);
  const [generationBaking, setGenerationBaking] = useState(false);
  const generationCanvasRef = useRef(null);

  useEffect(() => {
    if (source !== '2d-gen') return;
    let cancelled = false;
    setLoadingGenList(true);
    list2DGenerations()
      .then((list) => {
        if (!cancelled) setGenerations(list);
      })
      .catch((err) => log?.(String(err), 'error'))
      .finally(() => {
        if (!cancelled) setLoadingGenList(false);
      });
    return () => {
      cancelled = true;
    };
  }, [source, log]);

  useEffect(() => {
    drawDiagramPreview(generationCanvasRef.current, generationPreview?.grids);
  }, [generationPreview]);

  const handleSelectGeneration = useCallback(
    async (filename) => {
      setSelectedGeneration(filename);
      setGenerationPreview(null);
      setLoadingGenerationPreview(true);
      try {
        const result = await preview2DGeneration(filename);
        setGenerationPreview(result);
      } catch (err) {
        log?.(String(err), 'error');
      } finally {
        setLoadingGenerationPreview(false);
      }
    },
    [log],
  );

  const handleBakeGeneration = useCallback(async () => {
    if (!generationPreview) return;
    setGenerationBaking(true);
    try {
      const result = await bakePaint(generationPreview.grids, generationPreview.attractor_points);
      log?.(`baked from 2D generation ${generationPreview.filename}: ${JSON.stringify(result.counts)}`);
      await onBaked?.();
      onClose?.();
    } catch (err) {
      log?.(String(err), 'error');
    } finally {
      setGenerationBaking(false);
    }
  }, [generationPreview, log, onBaked, onClose]);

  return (
    <div className="fixed inset-0 z-50 bg-black/80 flex items-center justify-center p-6">
      <div className="bg-surface border border-border max-w-[90vw] max-h-[90vh] flex flex-col overflow-hidden">
        <div className="flex items-center justify-between p-container border-b border-border">
          <h3 className="font-headline-md text-headline-md text-primary">PAINT</h3>
          <button
            onClick={onClose}
            className="px-3 py-1 border border-border font-mono-sm text-mono-sm uppercase text-on-surface-variant hover:text-on-surface"
          >
            Close
          </button>
        </div>

        <div className="flex border-b border-border">
          {SOURCE_TABS.map((t) => (
            <button
              key={t.key}
              onClick={() => setSource(t.key)}
              className={`px-4 py-2 font-mono-sm text-mono-sm uppercase tracking-widest border-b-2 ${
                source === t.key
                  ? 'border-accent text-accent'
                  : 'border-transparent text-on-surface-variant hover:text-on-surface'
              }`}
            >
              {t.label}
            </button>
          ))}
        </div>

        {modalError && (
          <div className="flex items-center justify-between gap-3 px-container py-2 bg-error/10 border-b border-error text-error font-mono-sm text-mono-sm">
            <span>{modalError}</span>
            <button onClick={() => setModalError(null)} className="uppercase hover:opacity-70 shrink-0">
              Dismiss
            </button>
          </div>
        )}

        {source === 'sketch' ? (
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
                onClick={() => handleBake(true)}
                disabled={baking || !imgSize}
                className="w-full py-3 bg-accent text-background font-mono-sm text-mono-sm font-bold uppercase tracking-widest hover:brightness-110 transition-all active:scale-[0.98] disabled:opacity-50"
              >
                {baking ? 'BAKING...' : 'BAKE + REBUILD'}
              </button>
            </aside>
          </div>
        ) : source === 'diagram' ? (
          <>
            <div className="flex flex-1 overflow-hidden">
              <aside className="w-64 border-r border-border p-container space-y-2 overflow-y-auto shrink-0">
                <label className="font-mono-sm text-mono-sm text-on-surface-variant uppercase block">
                  Recent Diagrams
                </label>
                {loadingList ? (
                  <p className="font-mono-sm text-[11px] text-on-surface-variant">Loading...</p>
                ) : diagrams.length === 0 ? (
                  <p className="font-mono-sm text-[11px] text-on-surface-variant">
                    No exported diagrams found -- generate one in the legacy diagram tool first.
                  </p>
                ) : (
                  diagrams.map((d) => (
                    <button
                      key={d.filename}
                      onClick={() => handleSelectDiagram(d.filename)}
                      className={`w-full text-left border p-1 flex items-center gap-2 ${
                        selectedDiagram === d.filename
                          ? 'border-accent'
                          : 'border-border hover:border-on-surface-variant'
                      }`}
                    >
                      <img
                        src={`/legacy-diagrams/${d.filename}`}
                        alt={d.filename}
                        className="w-12 h-12 object-cover shrink-0 bg-background"
                      />
                      <span className="font-mono-sm text-[10px] text-on-surface-variant truncate">
                        {d.filename}
                      </span>
                    </button>
                  ))
                )}
              </aside>

              <div className="flex-1 overflow-auto flex flex-col items-center justify-center bg-background p-4 gap-4">
                {loadingDiagramPreview ? (
                  <p className="font-mono-sm text-mono-sm text-on-surface-variant">Converting...</p>
                ) : diagramPreview ? (
                  <>
                    <canvas ref={diagramCanvasRef} className="border border-border max-w-full max-h-full" />
                    <div className="font-mono-sm text-[11px] text-on-surface-variant">
                      {Object.entries(diagramPreview.counts)
                        .filter(([k]) => k !== 'canyon')
                        .map(([k, v]) => `${k}=${v}`)
                        .join('  ')}
                    </div>
                  </>
                ) : (
                  <p className="font-mono-sm text-mono-sm text-on-surface-variant">
                    Select a diagram to preview its converted regions.
                  </p>
                )}
              </div>
            </div>

            <div className="p-container border-t border-border">
              <button
                onClick={handleBakeDiagram}
                disabled={!diagramPreview || diagramBaking}
                className="w-full py-3 bg-accent text-background font-mono-sm text-mono-sm font-bold uppercase tracking-widest hover:brightness-110 transition-all active:scale-[0.98] disabled:opacity-50"
              >
                {diagramBaking ? 'BAKING...' : 'BAKE THIS DIAGRAM + REBUILD'}
              </button>
            </div>
          </>
        ) : (
          <>
            <div className="flex flex-1 overflow-hidden">
              <aside className="w-64 border-r border-border p-container space-y-2 overflow-y-auto shrink-0">
                <label className="font-mono-sm text-mono-sm text-on-surface-variant uppercase block">
                  Recent 2D Generations
                </label>
                {loadingGenList ? (
                  <p className="font-mono-sm text-[11px] text-on-surface-variant">Loading...</p>
                ) : generations.length === 0 ? (
                  <p className="font-mono-sm text-[11px] text-on-surface-variant">
                    No 2D generations found -- hit GEN in the Digital Palimpsest app (port 8000) first.
                  </p>
                ) : (
                  generations.map((g) => (
                    <button
                      key={g.filename}
                      onClick={() => handleSelectGeneration(g.filename)}
                      className={`w-full text-left border p-2 ${
                        selectedGeneration === g.filename
                          ? 'border-accent'
                          : 'border-border hover:border-on-surface-variant'
                      }`}
                    >
                      <span className="font-mono-sm text-[10px] text-on-surface-variant block line-clamp-2">
                        {g.prompt || '(empty prompt)'}
                      </span>
                      <span className="font-mono-sm text-[9px] text-on-surface-variant/60 block mt-1">
                        {new Date(g.mtime * 1000).toLocaleString()}
                      </span>
                    </button>
                  ))
                )}
              </aside>

              <div className="flex-1 overflow-auto flex flex-col items-center justify-center bg-background p-4 gap-4">
                {loadingGenerationPreview ? (
                  <p className="font-mono-sm text-mono-sm text-on-surface-variant">Converting...</p>
                ) : generationPreview ? (
                  <>
                    <canvas ref={generationCanvasRef} className="border border-border max-w-full max-h-full" />
                    <p className="font-mono-sm text-[11px] text-on-surface-variant max-w-md text-center">
                      {generationPreview.narrative}
                    </p>
                    <div className="font-mono-sm text-[11px] text-on-surface-variant">
                      {Object.entries(generationPreview.counts)
                        .filter(([k]) => k !== 'canyon')
                        .map(([k, v]) => `${k}=${v}`)
                        .join('  ')}
                    </div>
                    <div className="font-mono-sm text-[10px] text-on-surface-variant/60">
                      {generationPreview.resolved_layers}/{generationPreview.requested_layers} layers resolved
                    </div>
                  </>
                ) : (
                  <p className="font-mono-sm text-mono-sm text-on-surface-variant">
                    Select a generation to preview its converted regions.
                  </p>
                )}
              </div>
            </div>

            <div className="p-container border-t border-border">
              <button
                onClick={handleBakeGeneration}
                disabled={!generationPreview || generationBaking}
                className="w-full py-3 bg-accent text-background font-mono-sm text-mono-sm font-bold uppercase tracking-widest hover:brightness-110 transition-all active:scale-[0.98] disabled:opacity-50"
              >
                {generationBaking ? 'BAKING...' : 'BAKE THIS GENERATION + REBUILD'}
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
