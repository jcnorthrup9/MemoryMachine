import { useEffect, useRef, useState, useCallback } from 'react';
import Header from './components/Header.jsx';
import Viewport from './components/Viewport.jsx';
import ParamPanel from './components/ParamPanel.jsx';
import LogPanel from './components/LogPanel.jsx';
import PaintOverlay from './components/PaintOverlay.jsx';
import LineArtOverlay from './components/LineArtOverlay.jsx';
import PrecedentRemixerPanel from './components/PrecedentRemixerPanel.jsx';
import JurorChatBar from './components/JurorChatBar.jsx';
import ArchivePanel from './components/ArchivePanel.jsx';
import DiagnosticsPanel from './components/DiagnosticsPanel.jsx';
import {
  getConfig, rebuild as rebuildApi, startBlenderBuild, getBlenderBuildStatus, growNetwork as growNetworkApi,
  generateCanopy as generateCanopyApi,
  jurorChat as jurorChatApi, getProgramZones, saveToArchive,
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
  data_alpha: 1.0,
  use_real_noise_data: false,
  remove_top_slab: true,
  buildings: [],
  disabled_programs: [],
};

const DEFAULT_NETWORK_PARAMS = {
  motivator_weights: { shade: 1.0, water: 1.0, rest: 1.0, foot_traffic: 1.0, deficit: 1.0, program: 1.0 },
  step_ft: 15.0,
  max_iterations: 300,
};

// 2026-07-16 Canopy Redesign -- mirrors logic/pershing_api.py's
// CanopyParams defaults exactly; canopy generation is an explicit action
// (see handleGenerateCanopy below), not part of DEFAULT_PARAMS/doRebuild's
// live loop.
const DEFAULT_CANOPY_PARAMS = {
  base_height_ft: 20.0,
  wave_amplitude_ft: 8.0,
  wave_length_x_ft: 120.0,
  wave_length_y_ft: 90.0,
  wave_phase_x: 0.0,
  wave_phase_y: 0.0,
  dip_weight_ft: 6.0,
  program_boost_ft: 6.0,
  sculpt_radius_scale: 1.3,
  smoothing_iterations: 4,
  puncture_threshold: 0.5,
  panel_pitch_ft: 9.0,
  panel_thickness_ft: 0.15,
  fork_height_fraction: 0.6,
  fork_spread_ft: 4.0,
  column_search_radius_ft: 40.0,
  footprint_paint_threshold: 0.05,
  support_tie_back_tolerance_ft: 15.0,
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
  // Unified "Paint" dialog (2026-07-16) -- one trigger, PaintOverlay's own
  // Source tab picks sketch-painting vs. diagram-import internally (used
  // to be two separate buttons/dialogs, paintCategory + showDiagramInput).
  const [showPaint, setShowPaint] = useState(false);
  const [showPrecedentRemixer, setShowPrecedentRemixer] = useState(false);
  const [blenderBuild, setBlenderBuild] = useState({ status: 'idle', objUrl: null, svgUrl: null, error: null, durationS: null });
  const [lineartEnabled, setLineartEnabled] = useState(false);
  const [showLineArt, setShowLineArt] = useState(false);
  // Layer visibility toggles (2026-07-13, moved to ParamPanel's sidebar
  // 2026-07-13) -- lifted here (like removeTopSlab below) since both
  // ParamPanel (renders the checkboxes) and Viewport (filters what it
  // renders) need to share this state.
  const [visibleLayers, setVisibleLayers] = useState({
    realContext: true, structural: true, greenscape: true, shade: true,
    circulation: true, canopy: true, programZones: true, staticContext: true,
    // 2026-07-16: off by default -- the existing flat-plane ProgramZones
    // footprint stays the default visual for every program category, this
    // is an opt-in placeholder-massing preview (see logic/pershing_api.py's
    // rebuild() docstring for why it's a separate toggle from both
    // "Program Zones" and "Structural").
    programBoxes: false,
  });
  const [networkParams, setNetworkParams] = useState(DEFAULT_NETWORK_PARAMS);
  const [networkData, setNetworkData] = useState(null);
  const [growingNetwork, setGrowingNetwork] = useState(false);
  const [canopyParams, setCanopyParams] = useState(DEFAULT_CANOPY_PARAMS);
  const [canopyResult, setCanopyResult] = useState(null);
  const [generatingCanopy, setGeneratingCanopy] = useState(false);
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
        // 2026-07-12: rebuild() now computes program zones itself (needed
        // to feed programmatic buildings into the pipeline), so refresh
        // this on every rebuild instead of relying solely on the mount-time
        // getProgramZones() fetch below, which otherwise goes stale the
        // moment a paint/bake changes which bays are claimed. bay_ft is a
        // fixed constant (STRUCTURAL_BAY_FT), not per-response, so carry
        // forward whatever the initial getProgramZones() mount fetch set.
        if (result.program_zones) {
          setProgramZones((prev) => ({ bay_ft: prev?.bay_ft, zones: result.program_zones }));
        }
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
        if (c.noise_csv) {
          setParams((prev) => ({ ...prev, use_real_noise_data: true }));
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

  // Canopy panels/columns (2026-07-16) live in their OWN response
  // (canopyResult, from the explicit "Generate Canopy" action), not in
  // data.structural -- headless Blender exports still need them, so merge
  // them into the structural list right before sending, the same shape
  // every other procedural element already uses (kind-based dispatch, see
  // blender/pershing_headless_build.py's build_structural_meshes). Falls
  // back to `data` unchanged if canopy hasn't been generated yet.
  const dataForBlenderExport = useCallback(() => {
    if (!data) return data;
    if (!canopyResult) return data;
    return {
      ...data,
      structural: [
        ...data.structural,
        ...(canopyResult.canopy_panels || []),
        ...(canopyResult.canopy_columns || []),
      ],
    };
  }, [data, canopyResult]);

  const handleBuildInBlender = useCallback(async () => {
    if (!data) return;
    stopBlenderPoll();
    setBlenderBuild({ status: 'queued', objUrl: null, svgUrl: null, error: null, durationS: null });
    try {
      const { job_id } = await startBlenderBuild(dataForBlenderExport(), lineartEnabled);
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
  }, [data, dataForBlenderExport, lineartEnabled, log, stopBlenderPoll]);

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
        const { job_id } = await startBlenderBuild(dataForBlenderExport(), true, viewDirSite, true);
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
    [data, dataForBlenderExport, log, stopVectorExportPoll, downloadSvgUrl],
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

  // Organic panelized canopy + branching supports (2026-07-16 Canopy
  // Redesign) -- explicit action, NOT part of the live rebuild loop, same
  // reasoning as handleGrowNetwork above: real per-cell panel/support
  // generation (up to a few thousand panels) has no reason to rerun on
  // every trivial slider tweak. Panels/supports only appear where the
  // "canopy" brush has been painted -- see logic/canopy_engine.py's module
  // docstring for the full paint-as-footprint design.
  const handleGenerateCanopy = useCallback(async () => {
    setGeneratingCanopy(true);
    try {
      const result = await generateCanopyApi(params, canopyParams);
      setCanopyResult(result);
      log(
        `canopy generated: panels=${result.kind_counts.canopy_panel ?? 0} ` +
        `columns=${(result.kind_counts.canopy_column_trunk ?? 0) + (result.kind_counts.canopy_column_branch ?? 0)}`,
      );
    } catch (err) {
      log(String(err), 'error');
    } finally {
      setGeneratingCanopy(false);
    }
  }, [params, canopyParams, log]);

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
  // toolbar and the ARCHIVE tab. Both now persist the same snapshot
  // server-side (outputs/pershing_archive/, via saveToArchive()) so a build
  // saved from either place survives a reload and shows up in the ARCHIVE
  // tab's gallery; the toolbar button just skips the label prompt. Loading
  // stays split: the toolbar's "Load Build" still reads a locally-downloaded
  // file client-side, while the ARCHIVE tab loads by filename from the
  // server. Everything needed to restore the exact
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
      canopy_params: canopyParams,
      data,
      network_data: networkData,
      canopy_data: canopyResult,
      program_zones: programZones,
    };
  }, [config, params, networkParams, canopyParams, data, networkData, canopyResult, programZones]);

  const restoreSnapshot = useCallback(
    (snapshot) => {
      if (!snapshot.data) throw new Error("missing 'data' field -- not a valid build snapshot");
      if (snapshot.params) setParams(snapshot.params);
      if (snapshot.network_params) setNetworkParams(snapshot.network_params);
      if (snapshot.canopy_params) setCanopyParams(snapshot.canopy_params);
      setData(snapshot.data);
      setNetworkData(snapshot.network_data ?? null);
      setCanopyResult(snapshot.canopy_data ?? null);
      setProgramZones(snapshot.program_zones ?? null);
    },
    [],
  );

  const [savingBuild, setSavingBuild] = useState(false);

  const handleSaveBuild = useCallback(async () => {
    const snapshot = buildSnapshot();
    if (!snapshot) return;
    setSavingBuild(true);
    try {
      const result = await saveToArchive(snapshot, '');
      log(`build saved: ${result.label || result.filename}`);
    } catch (err) {
      log(String(err), 'error');
    } finally {
      setSavingBuild(false);
    }
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
                  canopyResult={canopyResult}
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
                  savingBuild={savingBuild}
                  removeTopSlab={params.remove_top_slab}
                  onToggleRemoveTopSlab={(value) =>
                    setParams((prev) => ({ ...prev, remove_top_slab: value }))
                  }
                  visibleLayers={visibleLayers}
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
              onPaint={() => setShowPaint(true)}
              onRebuild={() => doRebuild(params)}
              slabHarvestTons={data?.slab_harvest_tons}
              kindCounts={data?.kind_counts}
              usedRealAmenityData={data?.used_real_amenity_data}
              usedRealFootTrafficData={data?.used_real_foot_traffic_data}
              usedRealNoiseData={data?.used_real_noise_data}
              circulationVoxelCount={data?.voxels?.filter((v) => v.typology === 'CIRCULATION').length ?? 0}
              sanctuaryVoxelCount={data?.voxels?.filter((v) => v.typology === 'SANCTUARY').length ?? 0}
              rebuilding={rebuilding}
              visibleLayers={visibleLayers}
              onToggleLayer={(key) => setVisibleLayers((prev) => ({ ...prev, [key]: !prev[key] }))}
              blenderBuild={blenderBuild}
              onBuildInBlender={handleBuildInBlender}
              lineartEnabled={lineartEnabled}
              onLineartEnabledChange={setLineartEnabled}
              networkParams={networkParams}
              onNetworkParamsChange={setNetworkParams}
              onGrowNetwork={handleGrowNetwork}
              growingNetwork={growingNetwork}
              networkResult={networkData}
              canopyParams={canopyParams}
              onCanopyParamsChange={setCanopyParams}
              onGenerateCanopy={handleGenerateCanopy}
              generatingCanopy={generatingCanopy}
              canopyResult={canopyResult}
              onOpenPrecedentRemixer={() => setShowPrecedentRemixer(true)}
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
      {showPaint && (
        <PaintOverlay
          config={config}
          onClose={() => setShowPaint(false)}
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
      {showPrecedentRemixer && (
        <PrecedentRemixerPanel
          onClose={() => setShowPrecedentRemixer(false)}
          onBaked={async () => {
            await doRebuild(params);
          }}
          log={log}
        />
      )}
    </div>
  );
}
