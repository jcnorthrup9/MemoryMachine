import { useCallback, useEffect, useRef, useState } from 'react';
import { list2DGenerations, preview2DGeneration, bakePaint } from '../api.js';
import { drawDiagramPreview } from '../diagramGridPreview.js';

// Persistent right-side comparison panel (2026-07-23) -- previously the only
// way to browse a past root-app (port 8000) /api/generate record was
// PaintOverlay.jsx's "2D Generations" tab, buried inside a fullscreen modal
// that covered SpatializerPanel's own live canvas entirely. Moved out here so
// a selected past generation's converted preview sits right next to the live
// SPATIALIZE diagram, both visible at once -- the whole point being visual
// comparison, not just baking. Lifted verbatim from PaintOverlay's own
// 2d-gen mode (list/preview/bake logic unchanged), see that file's git
// history for the pre-extraction version.
export default function Recent2DGenerationsPanel({ onBaked, onLoad, log, refreshKey }) {
  const [generations, setGenerations] = useState([]);
  const [loadingGenList, setLoadingGenList] = useState(true);
  const [selectedGeneration, setSelectedGeneration] = useState(null);
  const [generationPreview, setGenerationPreview] = useState(null); // { filename, prompt, narrative, grids, counts, attractor_points }
  const [loadingGenerationPreview, setLoadingGenerationPreview] = useState(false);
  const [generationBaking, setGenerationBaking] = useState(false);
  const generationCanvasRef = useRef(null);

  // refreshKey (2026-07-24): bumped by SpatializerPanel right after a
  // successful GEN -- the backend's own /api/generate route (app.py) always
  // archives a new memory_machine_generation_*.json file regardless of
  // which frontend called it, so a fresh generation already exists on disk
  // the moment GEN finishes; this list just had no signal to know to
  // re-fetch, since it previously only loaded once on mount.
  useEffect(() => {
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
  }, [log, refreshKey]);

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
      const result = await bakePaint(generationPreview.grids, generationPreview.attractor_points, generationPreview.path_hints);
      log?.(`baked from 2D generation ${generationPreview.filename}: ${JSON.stringify(result.counts)}`);
      // Also loads this generation into the live SPATIALIZE canvas (2026-07-23)
      // -- this panel doubles as a "load" feature, not just a silent
      // background bake, so the diagram you just committed is visible.
      await onLoad?.(generationPreview);
      await onBaked?.();
    } catch (err) {
      log?.(String(err), 'error');
    } finally {
      setGenerationBaking(false);
    }
  }, [generationPreview, log, onBaked, onLoad]);

  return (
    <aside className="w-72 border-l border-border flex flex-col overflow-hidden shrink-0">
      <div className="p-container border-b border-border">
        <h3 className="font-headline-md text-headline-md text-primary">Recent 2D Generations</h3>
        <p className="font-mono-sm text-[11px] text-on-surface-variant mt-1">
          Compare a past generation's converted regions against the live diagram to the left, then load
          it in -- baking replaces the live canvas with this generation's diagram, same as pressing GEN.
        </p>
      </div>

      <div className="overflow-y-auto border-b border-border p-container space-y-2 max-h-[40%] shrink-0">
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
      </div>

      <div className="flex-1 overflow-y-auto p-container flex flex-col items-center gap-3">
        {loadingGenerationPreview ? (
          <p className="font-mono-sm text-mono-sm text-on-surface-variant">Converting...</p>
        ) : generationPreview ? (
          <>
            <canvas ref={generationCanvasRef} className="border border-border max-w-full" />
            <p className="font-mono-sm text-[11px] text-on-surface-variant text-center">
              {generationPreview.narrative}
            </p>
            <div className="font-mono-sm text-[10px] text-on-surface-variant text-center">
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
          <p className="font-mono-sm text-mono-sm text-on-surface-variant text-center">
            Select a generation to preview its converted regions.
          </p>
        )}
      </div>

      <div className="p-container border-t border-border">
        <button
          onClick={handleBakeGeneration}
          disabled={!generationPreview || generationBaking}
          title="Bakes into the live 3D paint masks AND loads this generation's diagram into the SPATIALIZE canvas to the left."
          className="w-full py-3 bg-accent text-background font-mono-sm text-mono-sm font-bold uppercase tracking-widest hover:brightness-110 transition-all active:scale-[0.98] disabled:opacity-50"
        >
          {generationBaking ? 'BAKING...' : 'LOAD + BAKE THIS GENERATION'}
        </button>
      </div>
    </aside>
  );
}
