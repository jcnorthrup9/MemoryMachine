import { useCallback, useState } from 'react';
import { remixPrecedent, bakePaint } from '../api.js';

// "Precedent Remixer" (2026-07-12, finished 2026-07-16) -- AI-curated
// selection of layers from the canonical precedent library
// (data/PershingMetabolizer/parkSVG/PrecedentSVG/) for a text prompt,
// reusing the OLD app's already-working generate_spatial_seed()/
// remix_layers() (see logic/pershing_api.py's remix_precedent()
// docstring). Preview-then-bake, same pattern DiagramInputPanel.jsx
// already established: remix_precedent() now also rasterizes the curated
// layers into real paint-mask grids server-side (ingest_diagram_svg.
// rasterize_precedent_layers()), this component just calls bakePaint()
// with those grids directly once the user confirms -- no separate "apply"
// endpoint needed, same as DiagramInputPanel's handleBake().

const ROLE_LABELS = {
  hardscape: 'Hardscape', water: 'Water', shade: 'Shade',
  greenscape: 'Greenscape', amenity_resting: 'Amenity / Rest',
};

export default function PrecedentRemixerPanel({ onClose, onBaked, log }) {
  const [prompt, setPrompt] = useState('');
  const [generating, setGenerating] = useState(false);
  const [baking, setBaking] = useState(false);
  const [result, setResult] = useState(null); // { narrative, layers, grids, counts, resolved_layers, requested_layers }

  const handleGenerate = useCallback(async () => {
    if (!prompt.trim()) return;
    setGenerating(true);
    try {
      const res = await remixPrecedent(prompt.trim());
      setResult(res);
      log?.(`precedent remix: ${res.resolved_layers}/${res.requested_layers} layers resolved, ${JSON.stringify(res.counts)}`);
    } catch (err) {
      log?.(String(err), 'error');
    } finally {
      setGenerating(false);
    }
  }, [prompt, log]);

  const handleBake = useCallback(async () => {
    if (!result?.grids) return;
    setBaking(true);
    try {
      const bakeResult = await bakePaint(result.grids);
      log?.(`baked from precedent remix: ${JSON.stringify(bakeResult.counts)}`);
      await onBaked?.();
      onClose?.();
    } catch (err) {
      log?.(String(err), 'error');
    } finally {
      setBaking(false);
    }
  }, [result, log, onBaked, onClose]);

  return (
    <div className="fixed inset-0 z-50 bg-black/80 flex items-center justify-center p-6">
      <div className="bg-surface border border-border max-w-[90vw] max-h-[90vh] w-[640px] flex flex-col overflow-hidden">
        <div className="flex items-center justify-between p-container border-b border-border">
          <h3 className="font-headline-md text-headline-md text-primary">PRECEDENT REMIXER</h3>
          <button
            onClick={onClose}
            className="px-3 py-1 border border-border font-mono-sm text-mono-sm uppercase text-on-surface-variant hover:text-on-surface"
          >
            Close
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-container space-y-4">
          <p className="font-mono-sm text-[11px] text-on-surface-variant">
            Describe the atmosphere you want and an AI curator selects layers from the precedent
            library (Parc de la Villette, Zaryadye Park, Schouwburgplein, Gardens by the Bay, ...) to
            match, rasterized directly onto the real paint masks -- review below, then bake to apply.
          </p>
          <textarea
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            placeholder="e.g. a quiet shady park with water features for reflection"
            rows={3}
            className="w-full bg-background border border-border p-2 font-mono-sm text-mono-sm text-on-surface resize-none"
          />
          <button
            onClick={handleGenerate}
            disabled={generating || !prompt.trim()}
            className="w-full py-3 border border-accent text-accent font-mono-sm text-mono-sm font-bold uppercase tracking-widest hover:bg-accent hover:text-background transition-all active:scale-[0.98] disabled:opacity-50"
          >
            {generating ? 'Curating...' : 'Generate'}
          </button>

          {result && (
            <div className="space-y-3 pt-2 border-t border-border">
              <p className="font-mono-sm text-[11px] text-on-surface-variant italic leading-relaxed">
                {result.narrative}
              </p>
              <div className="space-y-1">
                {result.layers.map((l, i) => (
                  <div
                    key={i}
                    className="flex justify-between font-mono-sm text-[11px] text-on-surface-variant border-b border-border/50 py-1"
                  >
                    <span>{l.site} / {l.layerId}</span>
                    <span className="text-accent">{ROLE_LABELS[l.role] ?? l.role}</span>
                  </div>
                ))}
              </div>
              <div className="font-mono-sm text-[11px] text-on-surface-variant">
                resolved: <span className="text-accent">{result.resolved_layers}/{result.requested_layers}</span> layers
                {result.resolved_layers < result.requested_layers && (
                  <span> -- one or more picks didn't match real geometry and were skipped</span>
                )}
              </div>
              <div className="grid grid-cols-2 gap-x-4 gap-y-1 font-mono-sm text-[11px] text-on-surface-variant">
                {Object.entries(result.counts).map(([key, count]) => (
                  <div key={key} className="flex justify-between">
                    <span className="uppercase">{ROLE_LABELS[key] ?? key}</span>
                    <span className="text-accent">{count} cells</span>
                  </div>
                ))}
              </div>
              <button
                onClick={handleBake}
                disabled={baking || Object.values(result.counts).every((c) => c === 0)}
                className="w-full py-3 bg-accent text-background font-mono-sm text-mono-sm font-bold uppercase tracking-widest hover:brightness-110 transition-all active:scale-[0.98] disabled:opacity-50"
              >
                {baking ? 'Baking...' : 'Bake + Rebuild'}
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
