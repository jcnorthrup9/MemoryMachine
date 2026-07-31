import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { fetchSiteSVG, generateSpatialSeed, spatializePreview, bakePaint } from '../api.js';
import { render, getProgramStats, fracToPixel, getLayerColor } from '../spatializerEngine.js';
import Recent2DGenerationsPanel from './Recent2DGenerationsPanel.jsx';

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

export default function SpatializerPanel({ onBaked, onPaint, log, onStackChange, restoreSeed }) {
  const [prompt, setPrompt] = useState('');
  const [generating, setGenerating] = useState(false);
  const [baking, setBaking] = useState(false);
  const [stack, setStack] = useState([]);
  const [baseCleared, setBaseCleared] = useState(false);
  const [narrative, setNarrative] = useState('');
  const [svgVersion, setSvgVersion] = useState(0);
  // Bumped after a successful GEN (2026-07-24) so Recent2DGenerationsPanel
  // knows to re-fetch its list -- app.py's /api/generate route already
  // archives every generation to disk unconditionally, this just tells that
  // panel a new one exists instead of it only ever loading once on mount.
  const [generationsRefreshKey, setGenerationsRefreshKey] = useState(0);

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

  // Load the base site on mount.
  useEffect(() => {
    let cancelled = false;
    ensureSiteSVG('PershingSquare').catch((err) => !cancelled && log?.(String(err), 'error'));
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    render(containerRef.current, {
      svgCache: svgCacheRef.current,
      stack,
      baseCleared,
    });
    // svgVersion is a synthetic dep -- svgCacheRef's contents changed even
    // though the ref identity didn't, so it has to be listed to re-render.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [svgVersion, stack, baseCleared]);

  const stats = useMemo(
    () => getProgramStats({ svgCache: svgCacheRef.current, stack, pathCache: pathCacheRef.current }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [svgVersion, stack],
  );

  // Shared by handleGenerate (a fresh AI-curated seed) and handleLoadGeneration
  // below (a past generation's already-resolved `layers`, same site/layerId/
  // transform shape a spatial_seed already has -- the extra `role` field
  // preview_2d_generation() tags each item with is simply ignored here).
  // Factored out 2026-07-23 so "load a past generation into the live canvas"
  // doesn't duplicate this exact site-SVG-fetch + frac-to-pixel conversion.
  const loadSeedIntoStack = useCallback(async (seed, narrativeText = '') => {
    const filtered = (seed || []).filter((s) => s.layerId !== 'BOUNDARY');
    const missingSites = [...new Set(filtered.map((s) => s.site || 'PershingSquare'))]
      .filter((site) => !svgCacheRef.current[site]);
    await Promise.all(missingSites.map((site) =>
      ensureSiteSVG(site).catch((err) => log?.(`could not load SVG for ${site}: ${err.message}`, 'error'))
    ));

    const newStack = filtered.map((s, idx) => {
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
    setNarrative(narrativeText);
    return newStack;
  }, [ensureSiteSVG, log]);

  // Reports the live diagram up to App.jsx (2026-07-24) -- "Save Build" in
  // RECONSTRUCT needs whatever diagram is currently live here so a saved
  // build stays connected back to the 2D side (see App.jsx's buildSnapshot/
  // handleSaveBuild). Same resolved-seed shape handleBake below already
  // sends to spatializePreview() -- SpatializerPanel stays the source of
  // truth for the live editing session, this is just a read-only mirror.
  useEffect(() => {
    const seed = stack.map((item) => ({ site: item.site, layerId: item.layerId, transform: item.transform }));
    onStackChange?.({ seed, narrative, prompt });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [stack, narrative, prompt]);

  // Consumes a restored build's diagram (2026-07-24) -- App.jsx's
  // restoreSnapshot sets a fresh `restoreSeed` (with a nonce so loading the
  // same build twice in a row still re-triggers this) whenever a loaded
  // build/archive entry carries a spatial_seed, so the diagram that
  // produced that build reappears here too, not just the 3D side.
  useEffect(() => {
    if (!restoreSeed?.seed?.length) return;
    loadSeedIntoStack(restoreSeed.seed, restoreSeed.narrative || '')
      .then((newStack) => log?.(`spatialize: restored ${newStack.length} layer(s) from saved build`))
      .catch((err) => log?.(String(err), 'error'));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [restoreSeed?.nonce]);

  const handleGenerate = useCallback(async () => {
    setGenerating(true);
    try {
      const data = await generateSpatialSeed(prompt.trim());
      if (data.status === 'error') throw new Error(data.narrative || 'generation failed');
      const newStack = await loadSeedIntoStack(data.spatial_seed, data.narrative || '');
      log?.(`spatialize: generated ${newStack.length} layer(s)`);
      setGenerationsRefreshKey((k) => k + 1);
    } catch (err) {
      log?.(String(err), 'error');
    } finally {
      setGenerating(false);
    }
  }, [prompt, loadSeedIntoStack, log]);

  // Recent2DGenerationsPanel's "Bake This Generation" (2026-07-23) -- that
  // panel now doubles as a load feature: baking a past generation also
  // brings its diagram into this live, editable canvas (previously it only
  // baked the already-rasterized grids into the 3D masks in the background,
  // leaving the SPATIALIZE canvas showing something unrelated).
  const handleLoadGeneration = useCallback(async (generationPreview) => {
    if (!generationPreview) return;
    try {
      const newStack = await loadSeedIntoStack(generationPreview.layers, generationPreview.narrative || '');
      log?.(`spatialize: loaded ${newStack.length} layer(s) from ${generationPreview.filename}`);
    } catch (err) {
      log?.(String(err), 'error');
    }
  }, [loadSeedIntoStack, log]);

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
      const bakeResult = await bakePaint(preview.grids, preview.attractor_points, preview.path_hints);
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
        <div ref={containerRef} className="flex-1 min-h-0 bg-background" />
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
          className="w-full bg-background border border-border p-2 font-mono-sm text-mono-sm text-on-surface resize-none rounded"
        />
        <div className="flex gap-2">
          <button
            onClick={handleGenerate}
            disabled={generating}
            className="flex-1 py-3 border border-accent text-accent font-mono-sm text-mono-sm font-bold uppercase tracking-widest rounded hover:bg-accent hover:text-background transition-all active:scale-[0.98] disabled:opacity-50"
          >
            {generating ? 'Generating...' : 'GEN'}
          </button>
          <button
            onClick={handleClear}
            disabled={stack.length === 0}
            className="px-4 py-3 border border-border font-mono-sm text-mono-sm uppercase text-on-surface-variant hover:text-on-surface rounded disabled:opacity-50"
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
          <div className="font-mono-sm text-[10px] uppercase tracking-widest rounded text-on-surface-variant/60">
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
          className="w-full py-3 bg-accent text-background font-mono-sm text-mono-sm font-bold uppercase tracking-widest rounded hover:brightness-110 transition-all active:scale-[0.98] disabled:opacity-50"
        >
          {baking ? 'Baking...' : 'Bake + Rebuild'}
        </button>

        <div className="space-y-3 pt-4 border-t border-border">
          <h4 className="font-mono-label text-mono-label text-on-surface-variant uppercase tracking-widest rounded">
            Design Input
          </h4>
          <p className="font-mono-sm text-[11px] text-on-surface-variant">
            Paint freehand on the sketch photo, or import colors from an exported legacy diagram or a
            saved 2D generation -- all feed the same live design masks, pick the source inside the dialog.
          </p>
          <button
            onClick={() => onPaint?.()}
            className="w-full px-4 py-2 border border-border text-on-surface-variant font-mono-sm text-mono-sm uppercase hover:border-accent hover:text-accent transition-colors rounded"
          >
            Paint
          </button>
        </div>
      </aside>

      <Recent2DGenerationsPanel
        onBaked={onBaked}
        onLoad={handleLoadGeneration}
        log={log}
        refreshKey={generationsRefreshKey}
      />
    </div>
  );
}
