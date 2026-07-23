import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { fetchSiteSVG, generateSpatialSeed, spatializePreview, getDeficitWeights, bakePaint } from '../api.js';
import { render, getProgramStats, fracToPixel, getLayerColor } from '../spatializerEngine.js';

// SPATIALIZE tab (2026-07-23) -- 2D diagram authoring ported natively into
// the 3D Pershing Metabolizer app, replacing the earlier cross-app flow
// (generate in the root 8000 app -> save -> switch here -> import via
// PaintOverlay's "2D Generations" tab -> bake) with a single native tab:
// compose/GEN here, BAKE commits straight into the live 3D paint masks via
// logic/pershing_api.py's spatialize_preview() (occlusion-aware -- see its
// docstring) + the existing bakePaint(). Rendering/HUD math is ported from
// static/js/engine2D.js + static/js/state.js into spatializerEngine.js
// (framework-agnostic, called imperatively from a ref+effect, same pattern
// PaintOverlay.jsx already uses for its freehand sketch canvas).

const HUD_ROWS = [
  { key: 'SOFT', label: 'Softscape' },
  { key: 'HARD', label: 'Hardscape' },
  { key: 'PROG', label: 'Activators' },
  { key: 'BLUE', label: 'Water' },
  { key: 'SHADE', label: 'Shade' },
];

const HUD_BAR_COLOR = {
  SOFT: '#4CAF50', HARD: '#9E9E9E', PROG: '#FF9800', BLUE: '#03A9F4', SHADE: '#FFEB3B',
};

export default function SpatializerPanel({ onBaked, log }) {
  const [prompt, setPrompt] = useState('');
  const [generating, setGenerating] = useState(false);
  const [baking, setBaking] = useState(false);
  const [stack, setStack] = useState([]);
  const [baseCleared, setBaseCleared] = useState(false);
  const [narrative, setNarrative] = useState('');
  const [deficitWeights, setDeficitWeights] = useState(null);
  const [svgVersion, setSvgVersion] = useState(0);

  const containerRef = useRef(null);
  const svgCacheRef = useRef({});
  const pathCacheRef = useRef(new Map());

  const ensureSiteSVG = useCallback(async (site) => {
    if (svgCacheRef.current[site]) return svgCacheRef.current[site];
    const svg = await fetchSiteSVG(site);
    svgCacheRef.current[site] = svg;
    setSvgVersion((v) => v + 1);
    return svg;
  }, []);

  // Load the base site + the live deficit-hotspot overlay on mount.
  useEffect(() => {
    let cancelled = false;
    ensureSiteSVG('PershingSquare').catch((err) => !cancelled && log?.(String(err), 'error'));
    getDeficitWeights()
      .then((w) => !cancelled && setDeficitWeights(w))
      .catch((err) => !cancelled && log?.(String(err), 'error'));
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    render(containerRef.current, {
      svgCache: svgCacheRef.current,
      stack,
      baseCleared,
      deficitWeights,
    });
    // svgVersion is a synthetic dep -- svgCacheRef's contents changed even
    // though the ref identity didn't, so it has to be listed to re-render.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [svgVersion, stack, baseCleared, deficitWeights]);

  const stats = useMemo(
    () => getProgramStats({ svgCache: svgCacheRef.current, stack, pathCache: pathCacheRef.current }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [svgVersion, stack],
  );

  const handleGenerate = useCallback(async () => {
    setGenerating(true);
    try {
      const data = await generateSpatialSeed(prompt.trim());
      if (data.status === 'error') throw new Error(data.narrative || 'generation failed');
      setNarrative(data.narrative || '');

      const seed = (data.spatial_seed || []).filter((s) => s.layerId !== 'BOUNDARY');
      const missingSites = [...new Set(seed.map((s) => s.site || 'PershingSquare'))]
        .filter((site) => !svgCacheRef.current[site]);
      await Promise.all(missingSites.map((site) =>
        ensureSiteSVG(site).catch((err) => log?.(`could not load SVG for ${site}: ${err.message}`, 'error'))
      ));

      const newStack = seed.map((s, idx) => {
        const t = s.transform || {};
        const { x, y } = ('x_frac' in t || 'y_frac' in t)
          ? fracToPixel(svgCacheRef.current, t.x_frac, t.y_frac)
          : { x: t.x ?? 0, y: t.y ?? 0 };
        return {
          id: Date.now() + idx,
          site: s.site || 'PershingSquare',
          layerId: s.layerId || 'GREEN_SPACE',
          label: s.label || s.layerId,
          color: getLayerColor(s.layerId),
          visible: true,
          transform: { x, y, scale: t.scale ?? 1.0, rot: t.rot ?? 0 },
        };
      });
      setStack(newStack);
      setBaseCleared(true);
      log?.(`spatialize: generated ${newStack.length} layer(s)`);
    } catch (err) {
      log?.(String(err), 'error');
    } finally {
      setGenerating(false);
    }
  }, [prompt, ensureSiteSVG, log]);

  const handleClear = useCallback(() => {
    setStack([]);
    setBaseCleared(false);
    setNarrative('');
  }, []);

  const handleBake = useCallback(async () => {
    if (stack.length === 0) return;
    setBaking(true);
    try {
      const spatialSeed = stack.map((item) => ({
        site: item.site, layerId: item.layerId, transform: item.transform,
      }));
      const preview = await spatializePreview(spatialSeed);
      log?.(`spatialize preview: ${preview.resolved_layers}/${preview.requested_layers} layers resolved, ${JSON.stringify(preview.counts)}`);
      const bakeResult = await bakePaint(preview.grids, preview.attractor_points);
      log?.(`baked from spatializer: ${JSON.stringify(bakeResult.counts)}`);
      await onBaked?.();
    } catch (err) {
      log?.(String(err), 'error');
    } finally {
      setBaking(false);
    }
  }, [stack, onBaked, log]);

  return (
    <div className="flex flex-1 overflow-hidden">
      <main className="flex-1 flex flex-col overflow-hidden">
        <div ref={containerRef} className="flex-1 bg-background" />
      </main>

      <aside className="w-80 border-l border-border p-container space-y-4 overflow-y-auto shrink-0">
        <h3 className="font-headline-md text-headline-md text-primary">SPATIALIZE</h3>
        <p className="font-mono-sm text-[11px] text-on-surface-variant leading-relaxed">
          Compose a 2D layout, then bake it straight into the live 3D paint masks. The red overlay
          shows the 3D side's real amenity-deficit hotspots -- darker means more underserved.
          Overlapping layers resolve by stack order: whichever you generate/place later wins the cell.
        </p>

        <textarea
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          placeholder="e.g. a quiet shady park with water features -- or leave blank to randomize"
          rows={3}
          className="w-full bg-background border border-border p-2 font-mono-sm text-mono-sm text-on-surface resize-none"
        />
        <div className="flex gap-2">
          <button
            onClick={handleGenerate}
            disabled={generating}
            className="flex-1 py-3 border border-accent text-accent font-mono-sm text-mono-sm font-bold uppercase tracking-widest hover:bg-accent hover:text-background transition-all active:scale-[0.98] disabled:opacity-50"
          >
            {generating ? 'Generating...' : 'GEN'}
          </button>
          <button
            onClick={handleClear}
            disabled={stack.length === 0}
            className="px-4 py-3 border border-border font-mono-sm text-mono-sm uppercase text-on-surface-variant hover:text-on-surface disabled:opacity-50"
          >
            CLR
          </button>
        </div>

        {narrative && (
          <p className="font-mono-sm text-[11px] text-on-surface-variant italic leading-relaxed border-t border-border pt-3">
            {narrative}
          </p>
        )}

        <div className="space-y-2 border-t border-border pt-3">
          <div className="font-mono-sm text-[10px] uppercase tracking-widest text-on-surface-variant/60">
            Zonal Mix
          </div>
          {HUD_ROWS.map(({ key, label }) => (
            <div key={key} className="flex items-center gap-2">
              <span className="font-mono-sm text-[10px] text-on-surface-variant w-20 shrink-0">{label}</span>
              <div className="flex-1 h-1 bg-border/40">
                <div
                  className="h-1"
                  style={{ width: `${Math.min(100, stats[key] || 0)}%`, backgroundColor: HUD_BAR_COLOR[key] }}
                />
              </div>
              <span className="font-mono-sm text-[10px] text-accent w-10 text-right shrink-0">
                {(stats[key] || 0).toFixed(0)}%
              </span>
            </div>
          ))}
        </div>

        <button
          onClick={handleBake}
          disabled={baking || stack.length === 0}
          className="w-full py-3 bg-accent text-background font-mono-sm text-mono-sm font-bold uppercase tracking-widest hover:brightness-110 transition-all active:scale-[0.98] disabled:opacity-50"
        >
          {baking ? 'Baking...' : 'Bake + Rebuild'}
        </button>
      </aside>
    </div>
  );
}
