import { useCallback, useEffect, useRef, useState } from 'react';
import { listLegacyDiagrams, previewLegacyImport, bakePaint } from '../api.js';
import { PAINT_CATEGORIES } from '../paintCategories.js';

// Diagram Input mode (2026-07-11) -- a separate design-input mechanism from
// PaintOverlay.jsx's freehand painting: reads colors (patterns later) off
// an existing legacy-diagram export via ingest_legacy_diagram.py (wrapped
// for HTTP by logic/legacy_diagram_bridge.py) instead of brush strokes.
// Sibling to PaintOverlay in the UI, not nested inside it -- painting
// remains available as the "sketch input" option, this is not routed
// through it. Commits via the SAME bakePaint() endpoint PaintOverlay uses
// (bake() doesn't care about a grid's source, only its shape), so there's
// no parallel commit path to keep in sync.

const PREVIEW_CELL_PX = 6;

function drawPreview(canvas, grids) {
  if (!canvas || !grids) return;
  const nx = grids.hardscape.length;
  const nz = grids.hardscape[0].length;
  canvas.width = nx * PREVIEW_CELL_PX;
  canvas.height = nz * PREVIEW_CELL_PX;
  const ctx = canvas.getContext('2d');
  ctx.fillStyle = '#000000';
  ctx.fillRect(0, 0, canvas.width, canvas.height);
  // Same category order as PaintOverlay's composite -- later entries draw
  // on top, matching how overlapping painted strokes already resolve there.
  for (const cat of PAINT_CATEGORIES) {
    if (cat.key === 'canyon') continue; // continuous weight, not a boolean region -- no fill color to preview here
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

export default function DiagramInputPanel({ onClose, onBaked, log }) {
  const [diagrams, setDiagrams] = useState([]);
  const [loadingList, setLoadingList] = useState(true);
  const [selected, setSelected] = useState(null);
  const [preview, setPreview] = useState(null); // { filename, grids, counts }
  const [loadingPreview, setLoadingPreview] = useState(false);
  const [baking, setBaking] = useState(false);
  const canvasRef = useRef(null);

  useEffect(() => {
    let cancelled = false;
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
  }, [log]);

  useEffect(() => {
    drawPreview(canvasRef.current, preview?.grids);
  }, [preview]);

  const handleSelect = useCallback(
    async (filename) => {
      setSelected(filename);
      setPreview(null);
      setLoadingPreview(true);
      try {
        const result = await previewLegacyImport(filename);
        setPreview(result);
      } catch (err) {
        log?.(String(err), 'error');
      } finally {
        setLoadingPreview(false);
      }
    },
    [log],
  );

  const handleBake = useCallback(async () => {
    if (!preview) return;
    setBaking(true);
    try {
      const result = await bakePaint(preview.grids);
      log?.(`baked from diagram ${preview.filename}: ${JSON.stringify(result.counts)}`);
      await onBaked?.();
      onClose?.();
    } catch (err) {
      log?.(String(err), 'error');
    } finally {
      setBaking(false);
    }
  }, [preview, log, onBaked, onClose]);

  return (
    <div className="fixed inset-0 z-50 bg-black/80 flex items-center justify-center p-6">
      <div className="bg-surface border border-border max-w-[90vw] max-h-[90vh] flex flex-col overflow-hidden">
        <div className="flex items-center justify-between p-container border-b border-border">
          <h3 className="font-headline-md text-headline-md text-primary">DIAGRAM INPUT</h3>
          <button
            onClick={onClose}
            className="px-3 py-1 border border-border font-mono-sm text-mono-sm uppercase text-on-surface-variant hover:text-on-surface"
          >
            Close
          </button>
        </div>

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
                  onClick={() => handleSelect(d.filename)}
                  className={`w-full text-left border p-1 flex items-center gap-2 ${
                    selected === d.filename
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
            {loadingPreview ? (
              <p className="font-mono-sm text-mono-sm text-on-surface-variant">Converting...</p>
            ) : preview ? (
              <>
                <canvas ref={canvasRef} className="border border-border max-w-full max-h-full" />
                <div className="font-mono-sm text-[11px] text-on-surface-variant">
                  {Object.entries(preview.counts)
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
            onClick={handleBake}
            disabled={!preview || baking}
            className="w-full py-3 bg-accent text-background font-mono-sm text-mono-sm font-bold uppercase tracking-widest hover:brightness-110 transition-all active:scale-[0.98] disabled:opacity-50"
          >
            {baking ? 'BAKING...' : 'BAKE THIS DIAGRAM + REBUILD'}
          </button>
        </div>
      </div>
    </div>
  );
}
