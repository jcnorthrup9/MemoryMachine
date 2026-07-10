import { useEffect, useRef, useState, useCallback } from 'react';
import Header from './components/Header.jsx';
import Sidebar from './components/Sidebar.jsx';
import Viewport from './components/Viewport.jsx';
import ParamPanel from './components/ParamPanel.jsx';
import LogPanel from './components/LogPanel.jsx';
import PaintOverlay from './components/PaintOverlay.jsx';
import LineArtOverlay from './components/LineArtOverlay.jsx';
import {
  getConfig, rebuild as rebuildApi, startBlenderBuild, getBlenderBuildStatus, growNetwork as growNetworkApi,
} from './api.js';

const BLENDER_POLL_MS = 1500;

const DEFAULT_PARAMS = {
  sketch_alpha: 0.75,
  canyon_width: 3,
  canyon_depth: 1,
  material_mode: 'STEEL',
  shoring_density: 1.0,
  use_real_amenity_data: false,
  use_real_foot_traffic_data: false,
  buildings: [],
};

const DEFAULT_NETWORK_PARAMS = {
  motivator_weights: { shade: 1.0, water: 1.0, rest: 1.0, foot_traffic: 1.0, deficit: 1.0 },
  step_ft: 15.0,
  max_iterations: 300,
};

function timeNow() {
  return new Date().toTimeString().split(' ')[0];
}

export default function App() {
  const [config, setConfig] = useState(null);
  const [params, setParams] = useState(DEFAULT_PARAMS);
  const [data, setData] = useState(null);
  const [rebuilding, setRebuilding] = useState(false);
  const [logs, setLogs] = useState([]);
  const [paintCategory, setPaintCategory] = useState(null);
  const [blenderBuild, setBlenderBuild] = useState({ status: 'idle', objUrl: null, svgUrl: null, error: null, durationS: null });
  const [lineartEnabled, setLineartEnabled] = useState(false);
  const [showLineArt, setShowLineArt] = useState(false);
  const [networkParams, setNetworkParams] = useState(DEFAULT_NETWORK_PARAMS);
  const [networkData, setNetworkData] = useState(null);
  const [growingNetwork, setGrowingNetwork] = useState(false);
  const blenderPollRef = useRef(null);

  const log = useCallback((text, level = 'info') => {
    setLogs((prev) => [...prev.slice(-49), { time: timeNow(), text, level }]);
  }, []);

  const doRebuild = useCallback(
    async (nextParams) => {
      setRebuilding(true);
      try {
        const result = await rebuildApi(nextParams ?? params);
        setData(result);
        log(
          `faces=${result.voxels.length} structural=${result.structural.length} slab=${result.slab_harvest_tons.toFixed(0)}t`,
        );
      } catch (err) {
        log(String(err), 'error');
      } finally {
        setRebuilding(false);
      }
    },
    [params, log],
  );

  useEffect(() => {
    getConfig()
      .then((c) => {
        setConfig(c);
        log(`config loaded: ${c.nx}x${c.nz} grid, ${c.voxel_ft}ft voxels`);
        // Mirrors the Blender cockpit panel's default (auto-on once a CSV
        // exists) -- only flips the toggle on first load, same reasoning
        // as blender_cockpit.py's mm_use_real_amenity_data default.
        if (c.amenity_csv) {
          setParams((prev) => ({ ...prev, use_real_amenity_data: true }));
        }
        if (c.foot_traffic_csv) {
          setParams((prev) => ({ ...prev, use_real_foot_traffic_data: true }));
        }
      })
      .catch((err) => log(String(err), 'error'));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Headless-Blender "build" tier (logic/pershing_blender.py) -- explicit,
  // occasional action, NOT part of the live rebuild loop above (spawning a
  // Blender process has real, multi-second startup cost that would kill
  // the debounced-slider responsiveness that loop exists for). Sends
  // exactly the current rebuild result so the built OBJ can't drift from
  // what's on screen, then polls the job-status route since the FastAPI
  // route returns immediately rather than blocking on the subprocess.
  const stopBlenderPoll = useCallback(() => {
    if (blenderPollRef.current) {
      clearInterval(blenderPollRef.current);
      blenderPollRef.current = null;
    }
  }, []);

  const handleBuildInBlender = useCallback(async () => {
    if (!data) return;
    stopBlenderPoll();
    setBlenderBuild({ status: 'queued', objUrl: null, svgUrl: null, error: null, durationS: null });
    try {
      const { job_id } = await startBlenderBuild(data, lineartEnabled);
      log(`blender build queued: ${job_id}${lineartEnabled ? ' (+ line art)' : ''}`);
      blenderPollRef.current = setInterval(async () => {
        try {
          const job = await getBlenderBuildStatus(job_id);
          // Normalize the API's snake_case job shape (status/obj_url/
          // svg_url/error/duration_s) to the camelCase shape this
          // component's state uses everywhere else.
          setBlenderBuild({
            status: job.status, objUrl: job.obj_url, svgUrl: job.svg_url,
            error: job.error, durationS: job.duration_s,
          });
          if (job.status === 'done') {
            stopBlenderPoll();
            log(`blender build done in ${job.duration_s}s`);
          } else if (job.status === 'error') {
            stopBlenderPoll();
            log(`blender build failed: ${job.error}`, 'error');
          }
        } catch (err) {
          stopBlenderPoll();
          log(String(err), 'error');
          setBlenderBuild((prev) => ({ ...prev, status: 'error', error: String(err) }));
        }
      }, BLENDER_POLL_MS);
    } catch (err) {
      log(String(err), 'error');
      setBlenderBuild({ status: 'error', objUrl: null, svgUrl: null, error: String(err), durationS: null });
    }
  }, [data, lineartEnabled, log, stopBlenderPoll]);

  useEffect(() => stopBlenderPoll, [stopBlenderPoll]);

  // Space Colonization circulation network -- explicit action, NOT part of
  // the live rebuild loop below (a real iterative growth simulation, even
  // though it runs well under a second at this grid size, has no reason to
  // regrow on every trivial slider tweak the way voxel terracing does).
  // Grows against whatever terrain params are currently set, synchronous
  // (see logic/pershing_api.py's grow_network() docstring) -- no polling
  // needed, unlike the Blender build tier above.
  const handleGrowNetwork = useCallback(async () => {
    setGrowingNetwork(true);
    try {
      const result = await growNetworkApi(params, networkParams);
      setNetworkData(result);
      log(
        `network grown: nodes=${result.node_count} edges=${result.network.length - (result.kind_counts.lookout_point ?? 0)} lookouts=${result.kind_counts.lookout_point ?? 0} unconsumed=${result.attractors_unconsumed}`,
      );
    } catch (err) {
      log(String(err), 'error');
    } finally {
      setGrowingNetwork(false);
    }
  }, [params, networkParams, log]);

  // Live rebuild, debounced -- mirrors Blender's update=_on_X_update
  // callbacks (every param change triggers a rebuild), but batched behind
  // a short delay since each change here is a network round-trip to the
  // FastAPI backend, not an in-process call. This is the ONLY rebuild
  // trigger (including the very first one, once config loads) -- the
  // debounce's own cleanup (clearTimeout) is what makes this safe under
  // React 18 StrictMode's double-invoke-on-mount in dev, unlike an
  // earlier version of this effect that used a manual "skip first run"
  // ref flag and fired 3 rebuilds on mount instead of 1.
  useEffect(() => {
    if (!config) return;
    const t = setTimeout(() => doRebuild(params), 200);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [params, config]);

  return (
    <div className="h-screen flex flex-col overflow-hidden">
      <Header />
      <div className="flex flex-1 overflow-hidden">
        <Sidebar />
        <main className="flex-1 flex flex-col overflow-hidden">
          {config ? (
            <Viewport
              data={data}
              networkSpecs={networkData?.network}
              siteWidthFt={config.site_width_ft}
              siteLengthFt={config.site_length_ft}
              voxelFt={config.voxel_ft}
              blenderObjUrl={blenderBuild.status === 'done' ? blenderBuild.objUrl : null}
              blenderSvgUrl={blenderBuild.status === 'done' ? blenderBuild.svgUrl : null}
              onShowLineArt={() => setShowLineArt(true)}
            />
          ) : (
            <div className="flex-1 flex items-center justify-center font-mono-sm text-on-surface-variant">
              loading config...
            </div>
          )}
          <LogPanel entries={logs} />
        </main>
        <ParamPanel
          config={config}
          params={params}
          onParamsChange={setParams}
          onPaint={(category) => setPaintCategory(category)}
          onRebuild={() => doRebuild(params)}
          slabHarvestTons={data?.slab_harvest_tons}
          kindCounts={data?.kind_counts}
          usedRealAmenityData={data?.used_real_amenity_data}
          usedRealFootTrafficData={data?.used_real_foot_traffic_data}
          circulationVoxelCount={data?.voxels?.filter((v) => v.typology === 'CIRCULATION').length ?? 0}
          rebuilding={rebuilding}
          blenderBuild={blenderBuild}
          onBuildInBlender={handleBuildInBlender}
          lineartEnabled={lineartEnabled}
          onLineartEnabledChange={setLineartEnabled}
          networkParams={networkParams}
          onNetworkParamsChange={setNetworkParams}
          onGrowNetwork={handleGrowNetwork}
          growingNetwork={growingNetwork}
          networkResult={networkData}
        />
      </div>
      {paintCategory && (
        <PaintOverlay
          config={config}
          initialCategory={paintCategory}
          onClose={() => setPaintCategory(null)}
          // Just triggers the rebuild -- closing the overlay is now
          // PaintOverlay's own call (closeAfterBake), since auto-bake while
          // painting (2026-07-10) must rebuild WITHOUT closing, and this
          // single onBaked prop is shared by both the explicit Bake button
          // and the auto-bake path.
          onBaked={async () => {
            await doRebuild(params);
          }}
          log={log}
        />
      )}
      {showLineArt && (
        <LineArtOverlay svgUrl={blenderBuild.svgUrl} onClose={() => setShowLineArt(false)} />
      )}
    </div>
  );
}
