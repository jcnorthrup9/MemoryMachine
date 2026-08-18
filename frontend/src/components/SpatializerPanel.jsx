import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  fetchSiteSVG, generateSpatialSeed, spatializePreview, bakePaint,
  list2DGenerations, preview2DGeneration,
} from '../api.js';
import { render, getProgramStats, fracToPixel, getLayerColor } from '../spatializerEngine.js';
import { drawDiagramPreview } from '../diagramGridPreview.js';
import SpatializeChatBar from './SpatializeChatBar.jsx';

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
//
// 2026-08-03: the right side was two separate columns (this file's own
// aside + a standalone Recent2DGenerationsPanel.jsx) with a textarea+GEN/CLR
// generate control at the top. Consolidated into one sidebar (Zonal Mix ->
// Bake+Rebuild -> Recent 2D Generations -> Paint -> Load+Bake) with
// generation now driven by SpatializeChatBar, positioned like RECONSTRUCT's
// JurorChatBar (bottom of the main column, not the sidebar). See that
// standalone file's git history for the pre-merge version of the recent-
// generations list/preview/bake logic, lifted verbatim here.

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

// 2026-08-17: 25 real past generations' resolved spatial_seed arrays (each
// {site, layerId, transform}[], same shape buildStackFromSeed already
// expects), pre-picked for richness (8-10 layers each) and bundled as a
// static file at frontend/public/loading-frames.json -- see the GENERATE
// loading-animation effect further down. Fetched once at mount and cached
// here; deliberately a plain array (not state) since it never changes
// after that first load and none of its consumers need a re-render when
// it arrives (the effect below reads the ref at tick time).
const loadingFramesPromise = fetch('/loading-frames.json').then((r) => r.json()).catch(() => []);

export default function SpatializerPanel({ onBaked, onPaint, log, onStackChange, restoreSeed }) {
  const [prompt, setPrompt] = useState('');
  const [generating, setGenerating] = useState(false);
  const [baking, setBaking] = useState(false);
  const [stack, setStack] = useState([]);
  const [baseCleared, setBaseCleared] = useState(false);
  const [narrative, setNarrative] = useState('');
  const [svgVersion, setSvgVersion] = useState(0);
  // Bumped after a successful GEN (2026-07-24) so the Recent 2D Generations
  // list knows to re-fetch -- app.py's /api/generate route already archives
  // every generation to disk unconditionally, this just tells that list a
  // fresh one exists instead of it only ever loading once on mount.
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

  // 2026-08-17: pre-warm every precedent site the 25 baked loading-frames
  // reference (buildStackFromSeed's ensureSiteSVG call is otherwise lazy --
  // first use fetches on demand), so the GENERATE loading animation never
  // has to make a network request while it's actually running. Without
  // this, a frame referencing a site nobody's viewed yet this session
  // would hang mid-tick waiting on the backend -- exactly the dependency
  // the baked-frame approach was meant to avoid, and worse during a real
  // generate call, when that same backend is already busy/blocked.
  useEffect(() => {
    let cancelled = false;
    loadingFramesPromise.then((frames) => {
      if (cancelled) return;
      const sites = new Set();
      frames.forEach((seed) => seed.forEach((item) => sites.add(item.site)));
      sites.forEach((site) => {
        ensureSiteSVG(site).catch(() => {}); // best-effort warm; a miss just means that one frame's tick falls back to on-demand fetch
      });
    });
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
  // Pure conversion (no state writes) so the loading-animation effect below
  // can build throwaway stacks to render directly, without disturbing the
  // real `stack` state that the actual generation result will land in.
  const buildStackFromSeed = useCallback(async (seed) => {
    const filtered = (seed || []).filter((s) => s.layerId !== 'BOUNDARY');
    const missingSites = [...new Set(filtered.map((s) => s.site || 'PershingSquare'))]
      .filter((site) => !svgCacheRef.current[site]);
    await Promise.all(missingSites.map((site) =>
      ensureSiteSVG(site).catch((err) => log?.(`could not load SVG for ${site}: ${err.message}`, 'error'))
    ));

    return filtered.map((s, idx) => {
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
  }, [ensureSiteSVG, log]);

  const loadSeedIntoStack = useCallback(async (seed, narrativeText = '') => {
    const newStack = await buildStackFromSeed(seed);
    setStack(newStack);
    setBaseCleared(true);
    setNarrative(narrativeText);
    return newStack;
  }, [buildStackFromSeed]);

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

  const handleGenerate = useCallback(async (promptText) => {
    setPrompt(promptText);
    setGenerating(true);
    // 2026-08-17: some /api/generate calls resolve in well under a second
    // (a warm connection + a short/empty prompt can come back near-
    // instantly) -- too fast for the loading-animation cycle above to be
    // perceptible at all, even though it's technically playing for a tick
    // or two. Floor the visible "generating" window so the animation
    // always gets a fair chance to actually be seen, without slowing down
    // the (already-fast) real work itself.
    const minDurationMs = 1800;
    const startedAt = Date.now();
    try {
      const data = await generateSpatialSeed(promptText.trim());
      if (data.status === 'error') throw new Error(data.narrative || 'generation failed');
      const newStack = await loadSeedIntoStack(data.spatial_seed, data.narrative || '');
      const elapsed = Date.now() - startedAt;
      if (elapsed < minDurationMs) {
        await new Promise((resolve) => setTimeout(resolve, minDurationMs - elapsed));
      }
      log?.(`spatialize: generated ${newStack.length} layer(s)`);
      setGenerationsRefreshKey((k) => k + 1);
    } catch (err) {
      log?.(String(err), 'error');
    } finally {
      setGenerating(false);
    }
  }, [loadSeedIntoStack, log]);

  // Recent-generations bake ("LOAD + BAKE THIS GENERATION" below) doubles
  // as a load feature: baking a past generation also brings its diagram
  // into this live, editable canvas.
  const handleLoadGeneration = useCallback(async (generationPreview) => {
    if (!generationPreview) return;
    try {
      const newStack = await loadSeedIntoStack(generationPreview.layers, generationPreview.narrative || '');
      log?.(`spatialize: loaded ${newStack.length} layer(s) from ${generationPreview.filename}`);
    } catch (err) {
      log?.(String(err), 'error');
    }
  }, [loadSeedIntoStack, log]);

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

  // --- Recent 2D Generations (merged in from the former standalone panel) ---
  const [generations, setGenerations] = useState([]);
  const [loadingGenList, setLoadingGenList] = useState(true);
  const [selectedGeneration, setSelectedGeneration] = useState(null);
  const [generationPreview, setGenerationPreview] = useState(null);
  const [loadingGenerationPreview, setLoadingGenerationPreview] = useState(false);
  const [generationBaking, setGenerationBaking] = useState(false);
  const generationCanvasRef = useRef(null);

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
  }, [log, generationsRefreshKey]);

  useEffect(() => {
    drawDiagramPreview(generationCanvasRef.current, generationPreview?.grids);
  }, [generationPreview]);

  // 2026-08-17: while GENERATE is in flight, cycle the live canvas through
  // the 25 baked loading-frames (loadingFramesPromise above) using the
  // SAME render()/buildStackFromSeed() pipeline that draws the real
  // result -- correct diagonal Pershing Square boundary, correct color
  // scheme, always in sync with either if they ever change again, no
  // separate asset format to keep matching. Renders directly into
  // containerRef, bypassing `stack` state entirely, so it can never race
  // with or clobber the real result: once handleGenerate's
  // loadSeedIntoStack call lands, `generating` flips false in the same
  // commit as the real `stack` update, this effect's cleanup stops the
  // interval, and the normal stack-driven render effect above takes over.
  // Tried two earlier versions this session, both reverted: (1) live
  // "Recent 2D Generations" previews -- some of that session's own sparse
  // test generations flashed the canvas back to a near-blank site: (2) a
  // static PNG batch export -- right idea (decoupled from the backend,
  // which does go fully unresponsive to everything, static files
  // included, during a synchronous generate call) but the wrong site
  // shape and palette entirely, a different precedent's export. This
  // combines what worked from both: pre-baked (so no live fetch races the
  // backend) but real Pershing-shaped, real-palette content.
  useEffect(() => {
    if (!generating) return;
    let cancelled = false;
    let idx = 0;
    let interval = null;

    loadingFramesPromise.then((frames) => {
      if (cancelled || !frames.length) return;
      idx = Math.floor(Math.random() * frames.length);

      const tick = async () => {
        const seed = frames[idx % frames.length];
        idx += 1;
        try {
          const tempStack = await buildStackFromSeed(seed);
          if (cancelled) return;
          render(containerRef.current, { svgCache: svgCacheRef.current, stack: tempStack, baseCleared: true });
        } catch {
          // Best-effort visual filler -- one bad frame shouldn't stop the loop.
        }
      };

      tick();
      interval = setInterval(tick, 450); // 2026-08-18: doubled speed (was 900ms) per user request
    });

    return () => { cancelled = true; if (interval) clearInterval(interval); };
  }, [generating, buildStackFromSeed]);

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
      // Also loads this generation into the live SPATIALIZE canvas -- this
      // doubles as a "load" feature, not just a silent background bake, so
      // the diagram you just committed is visible.
      await handleLoadGeneration(generationPreview);
      await onBaked?.();
    } catch (err) {
      log?.(String(err), 'error');
    } finally {
      setGenerationBaking(false);
    }
  }, [generationPreview, log, onBaked, handleLoadGeneration]);

  return (
    <div className="flex flex-1 overflow-hidden">
      <main className="flex-1 flex flex-col overflow-hidden">
        <div className="flex-1 min-h-0 relative bg-background">
          <div ref={containerRef} className="absolute inset-0" />
          {stack.length === 0 && !generating && (
            // 2026-08-18: static reference diagram (archive/diagrams/
            // PershingDiagram.jpg, copied to frontend/public/ -- same
            // zero-backend-dependency pattern as loading-frames.json) shown
            // in place of the live boundary-only render() output before the
            // first GENERATE/load. Once `generating` flips true the loading-
            // animation effect below takes over the same containerRef div,
            // and once `stack` gets real content this image simply stops
            // being rendered -- no explicit teardown needed.
            <img
              src="/pershing-default.jpg"
              alt="Pershing Square site diagram"
              className="absolute inset-0 w-full h-full object-contain bg-white"
            />
          )}
        </div>
        <SpatializeChatBar onGenerate={handleGenerate} generating={generating} />
      </main>

      <aside className="w-80 border-l border-border flex flex-col overflow-hidden shrink-0">
        <div className="p-container border-b border-border space-y-3 shrink-0">
          {narrative && (
            <p className="font-mono-sm text-[11px] text-on-surface-variant italic leading-relaxed">
              {narrative}
            </p>
          )}
          <div className="space-y-2">
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
        </div>

        <div className="overflow-y-auto border-b border-border p-container space-y-2 max-h-[35%] shrink-0">
          <h4 className="font-mono-label text-mono-label text-on-surface-variant uppercase tracking-widest rounded">
            Recent 2D Generations
          </h4>
          {loadingGenList ? (
            <p className="font-mono-sm text-[11px] text-on-surface-variant">Loading...</p>
          ) : generations.length === 0 ? (
            <p className="font-mono-sm text-[11px] text-on-surface-variant">
              No 2D generations found -- generate one above first.
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

        <div className="p-container border-t border-border space-y-2 shrink-0">
          <button
            onClick={() => onPaint?.()}
            className="w-full px-4 py-2 border border-border text-on-surface-variant font-mono-sm text-mono-sm uppercase hover:border-accent hover:text-accent transition-colors rounded"
          >
            Paint
          </button>
          <button
            onClick={handleBakeGeneration}
            disabled={!generationPreview || generationBaking}
            title="Bakes into the live 3D paint masks AND loads this generation's diagram into the SPATIALIZE canvas to the left."
            className="w-full py-3 bg-accent text-background font-mono-sm text-mono-sm font-bold uppercase tracking-widest rounded hover:brightness-110 transition-all active:scale-[0.98] disabled:opacity-50"
          >
            {generationBaking ? 'BAKING...' : 'LOAD + BAKE THIS GENERATION'}
          </button>
        </div>
      </aside>
    </div>
  );
}
