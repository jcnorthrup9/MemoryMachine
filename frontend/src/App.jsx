import { useEffect, useRef, useState, useCallback } from 'react';
import Header from './components/Header.jsx';
import Viewport from './components/Viewport.jsx';
import ParamPanel from './components/ParamPanel.jsx';
import LogPanel from './components/LogPanel.jsx';
import PaintOverlay from './components/PaintOverlay.jsx';
import LineArtOverlay from './components/LineArtOverlay.jsx';
import DiagramInputPanel from './components/DiagramInputPanel.jsx';
import JurorChatBar from './components/JurorChatBar.jsx';
import ArchivePanel from './components/ArchivePanel.jsx';
import DiagnosticsPanel from './components/DiagnosticsPanel.jsx';
import {
  getConfig, rebuild as rebuildApi, startBlenderBuild, getBlenderBuildStatus, growNetwork as growNetworkApi,
  jurorChat as jurorChatApi, getProgramZones,
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
  const [activeTab, setActiveTab] = useState('RECONSTRUCT');
  const [config, setConfig] = useState(null);
  const [programZones, setProgramZones] = useState(null);
  const [params, setParams] = useState(DEFAULT_PARAMS);
  const [data, setData] = useState(null);
  const [rebuilding, setRebuilding] = useState(false);
  const [logs, setLogs] = useState([]);
  const [paintCategory, setPaintCategory] = useState(null);
  const [showDiagramInput, setShowDiagramInput] = useState(false);
  const [blenderBuild, setBlenderBuild] = useState({ status: 'idle', objUrl: null, svgUrl: null, error: null, durationS: null });
  const [lineartEnabled, setLineartEnabled] = useState(false);
  const [showLineArt, setShowLineArt] = useState(false);
  const [networkParams, setNetworkParams] = useState(DEFAULT_NETWORK_PARAMS);
  const [networkData, setNetworkData] = useState(null);
  const [growingNetwork, setGrowingNetwork] = useState(false);
  const [exportingVectorView, setExportingVectorView] = useState(false);
  const vectorExportPollRef = useRef(null);
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

  // Bay-grid program placement -- fetched once on load, same as config.
  // Recomputes server-side against whatever masks are currently painted/
  // imported (see get_program_zones()'s docstring); re-fetching after every
  // bake()/rebuild() so it always reflects the latest paint state is a
  // natural follow-up, not done here to keep this pass's scope to "does the
  // pipeline work end-to-end at all."
  useEffect(() => {
    getProgramZones()
      .then((z) => {
        setProgramZones(z);
        log(`program zones loaded: ${z.zones.length} programs placed`);
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

  // "Export Current View" vector linework (2026-07-11) -- Viewport.jsx's
  // handleExport computes the live camera direction (already converted to
  // the backend's Z-up site-local frame) and calls this; reuses the SAME
  // headless-Blender build tier handleBuildInBlender above already relies
  // on (the backend's own single-build lock already serializes the two, so
  // no separate coordination is needed here), just with lineart=true,
  // include_real_context=true, and the live view_dir instead of the
  // default isometric constant. Own status state (not blenderBuild) so
  // this doesn't visually clobber the separate "Build in Blender" button's
  // own status display in ParamPanel -- the two are independent user
  // actions that happen to share one backend job slot.
  //
  // Auto-downloads the resulting SVG directly (fetch + blob URL) rather
  // than requiring a second "View Line Art" click -- matches the PNG half
  // of this same button, which already downloads immediately.
  const stopVectorExportPoll = useCallback(() => {
    if (vectorExportPollRef.current) {
      clearInterval(vectorExportPollRef.current);
      vectorExportPollRef.current = null;
    }
  }, []);

  const downloadSvgUrl = useCallback(async (svgUrl, filename) => {
    const res = await fetch(svgUrl);
    if (!res.ok) throw new Error(`svg fetch failed: ${res.status}`);
    const blob = await res.blob();
    const blobUrl = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = blobUrl;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(blobUrl);
  }, []);

  const handleExportVectorView = useCallback(
    async (viewDirSite) => {
      if (!data) return;
      stopVectorExportPoll();
      setExportingVectorView(true);
      try {
        const { job_id } = await startBlenderBuild(data, true, viewDirSite, true);
        log(`vector export queued: ${job_id} (view_dir=${viewDirSite.map((v) => v.toFixed(2)).join(',')})`);
        vectorExportPollRef.current = setInterval(async () => {
          try {
            const job = await getBlenderBuildStatus(job_id);
            if (job.status === 'done') {
              stopVectorExportPoll();
              log(`vector export done in ${job.duration_s}s`);
              try {
                await downloadSvgUrl(job.svg_url, `pershing-lineart-${Date.now()}.svg`);
              } catch (err) {
                log(String(err), 'error');
              }
              setExportingVectorView(false);
            } else if (job.status === 'error') {
              stopVectorExportPoll();
              log(`vector export failed: ${job.error}`, 'error');
              setExportingVectorView(false);
            }
          } catch (err) {
            stopVectorExportPoll();
            log(String(err), 'error');
            setExportingVectorView(false);
          }
        }, BLENDER_POLL_MS);
      } catch (err) {
        log(String(err), 'error');
        setExportingVectorView(false);
      }
    },
    [data, log, stopVectorExportPoll, downloadSvgUrl],
  );

  useEffect(() => stopVectorExportPoll, [stopVectorExportPoll]);

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

  // Juror chat live control (2026-07-10) -- dispatches the model's returned
  // action through the EXACT SAME state setters the matching UI control
  // already uses (a motivator slider drag, a canyon slider drag, the "Grow
  // Network" button, a data toggle), so a chat-driven change is
  // indistinguishable downstream from a manual one: canyon width/depth and
  // the data toggles flow into the existing debounced auto-rebuild effect
  // below, motivator weights just update state (mirroring the slider,
  // which also doesn't auto-regrow), and grow_network calls the same
  // handler the button does. logic/juror_chat.py's _validate_action already
  // clamped/sanitized this server-side -- this switch only needs to handle
  // the known-good shapes, not defend against malformed input again.
  const applyJurorAction = useCallback(
    (action) => {
      if (!action) return;
      switch (action.type) {
        case 'adjust_motivator':
          setNetworkParams((prev) => ({
            ...prev,
            motivator_weights: { ...prev.motivator_weights, [action.motivator]: action.value },
          }));
          break;
        case 'set_canyon_width':
          setParams((prev) => ({ ...prev, canyon_width: action.value }));
          break;
        case 'set_canyon_depth':
          setParams((prev) => ({ ...prev, canyon_depth: action.value }));
          break;
        case 'toggle_real_amenity_data':
          setParams((prev) => ({ ...prev, use_real_amenity_data: action.value }));
          break;
        case 'toggle_real_foot_traffic_data':
          setParams((prev) => ({ ...prev, use_real_foot_traffic_data: action.value }));
          break;
        case 'grow_network':
          handleGrowNetwork();
          break;
        default:
          log(`juror chat returned an unrecognized action type: ${action.type}`, 'error');
      }
    },
    [handleGrowNetwork, log],
  );

  // Juror chat -- persistent bar (not a modal), replies logged into the same
  // rebuild-log stream everything else already writes to. Grounding context
  // is built fresh from state this component already holds
  // (config/params/networkParams/data/networkData), not re-derived
  // server-side, so the model always sees exactly what's currently on screen.
  const handleJurorChat = useCallback(
    async (message) => {
      log(`Juror: ${message}`);
      const context = {
        site_width_ft: config?.site_width_ft,
        site_length_ft: config?.site_length_ft,
        column_height_ft: config?.column_height_ft,
        nx_bays: config?.nx_bays,
        params,
        network_params: networkParams,
        last_rebuild: data && {
          kind_counts: data.kind_counts,
          slab_harvest_tons: data.slab_harvest_tons,
          max_canyon_depth_ft: data.max_canyon_depth_ft,
          used_real_amenity_data: data.used_real_amenity_data,
          used_real_foot_traffic_data: data.used_real_foot_traffic_data,
        },
        last_network: networkData && {
          node_count: networkData.node_count,
          attractor_count: networkData.attractor_count,
          attractors_unconsumed: networkData.attractors_unconsumed,
          kind_counts: networkData.kind_counts,
        },
      };
      try {
        const result = await jurorChatApi(message, context);
        log(`Assistant: ${result.reply}`);
        applyJurorAction(result.action);
      } catch (err) {
        log(String(err), 'error');
      }
    },
    [config, params, networkParams, data, networkData, log, applyJurorAction],
  );

  // Save/recall a build iteration -- shared by two surfaces: RECONSTRUCT's
  // toolbar (a client-side-only JSON file download/upload) and the ARCHIVE
  // tab (the same snapshot persisted server-side so it survives a reload).
  // Both work the same way: everything needed to restore the exact
  // on-screen state (params/buildings, the full rebuild result, network
  // result, program zones) is already sitting in this component's own
  // state, so this is a snapshot-and-restore of that state, not a re-run of
  // the generation pipeline against saved inputs. That matters because
  // painted masks (GREENSCAPE_MASK etc., live server-side state) can drift
  // between save and load -- restoring by re-running rebuild() against
  // saved params could silently produce a DIFFERENT build if the masks
  // have since changed, defeating the point of "recall exactly what I saved."
  const buildSnapshot = useCallback(() => {
    if (!data) return null;
    return {
      schema: 'memory-machine-build-v1',
      saved_at: new Date().toISOString(),
      config: config && {
        site_width_ft: config.site_width_ft, site_length_ft: config.site_length_ft, voxel_ft: config.voxel_ft,
      },
      params,
      network_params: networkParams,
      data,
      network_data: networkData,
      program_zones: programZones,
    };
  }, [config, params, networkParams, data, networkData, programZones]);

  const restoreSnapshot = useCallback(
    (snapshot) => {
      if (!snapshot.data) throw new Error("missing 'data' field -- not a valid build snapshot");
      if (snapshot.params) setParams(snapshot.params);
      if (snapshot.network_params) setNetworkParams(snapshot.network_params);
      setData(snapshot.data);
      setNetworkData(snapshot.network_data ?? null);
      setProgramZones(snapshot.program_zones ?? null);
    },
    [],
  );

  const handleSaveBuild = useCallback(() => {
    const snapshot = buildSnapshot();
    if (!snapshot) return;
    const blob = new Blob([JSON.stringify(snapshot, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `memory-machine-build-${Date.now()}.json`;
    a.click();
    URL.revokeObjectURL(url);
    log(`build saved: ${a.download}`);
  }, [buildSnapshot, log]);

  const handleLoadBuild = useCallback(
    (file) => {
      const reader = new FileReader();
      reader.onload = () => {
        try {
          const snapshot = JSON.parse(reader.result);
          restoreSnapshot(snapshot);
          log(`build loaded: saved ${snapshot.saved_at || 'unknown time'}`);
        } catch (err) {
          log(`build load failed: ${String(err)}`, 'error');
        }
      };
      reader.onerror = () => log(`build load failed: could not read file`, 'error');
      reader.readAsText(file);
    },
    [log, restoreSnapshot],
  );

  return (
    <div className="h-screen flex flex-col overflow-hidden">
      <Header activeTab={activeTab} onSelectTab={setActiveTab} />
      <div className="flex flex-1 overflow-hidden">
        {activeTab === 'RECONSTRUCT' && (
          <>
            <main className="flex-1 flex flex-col overflow-hidden">
              {config ? (
                <Viewport
                  data={data}
                  programZones={programZones?.zones}
                  bayFt={programZones?.bay_ft}
                  networkSpecs={networkData?.network}
                  siteWidthFt={config.site_width_ft}
                  siteLengthFt={config.site_length_ft}
                  voxelFt={config.voxel_ft}
                  blenderObjUrl={blenderBuild.status === 'done' ? blenderBuild.objUrl : null}
                  blenderSvgUrl={blenderBuild.status === 'done' ? blenderBuild.svgUrl : null}
                  onShowLineArt={() => setShowLineArt(true)}
                  onExportVectorView={handleExportVectorView}
                  exportingVectorView={exportingVectorView}
                  onSaveBuild={handleSaveBuild}
                  onLoadBuild={handleLoadBuild}
                  canSaveBuild={!!data}
                />
              ) : (
                <div className="flex-1 flex items-center justify-center font-mono-sm text-on-surface-variant">
                  loading config...
                </div>
              )}
              <JurorChatBar onSend={handleJurorChat} />
              <LogPanel entries={logs} />
            </main>
            <ParamPanel
              config={config}
              params={params}
              onParamsChange={setParams}
              onPaint={(category) => setPaintCategory(category)}
              onOpenDiagramInput={() => setShowDiagramInput(true)}
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
          </>
        )}
        {activeTab === 'ARCHIVE' && (
          <ArchivePanel getSnapshot={buildSnapshot} onRestoreSnapshot={restoreSnapshot} canSave={!!data} log={log} />
        )}
        {activeTab === 'DIAGNOSTICS' && (
          <DiagnosticsPanel config={config} data={data} networkData={networkData} programZones={programZones} />
        )}
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
      {showDiagramInput && (
        <DiagramInputPanel
          onClose={() => setShowDiagramInput(false)}
          onBaked={async () => {
            await doRebuild(params);
          }}
          log={log}
        />
      )}
    </div>
  );
}
