import { useEffect, useRef, useState, useCallback } from 'react';
import Header from './components/Header.jsx';
import Viewport from './components/Viewport.jsx';
import ParamPanel from './components/ParamPanel.jsx';
import LogPanel from './components/LogPanel.jsx';
import PaintOverlay from './components/PaintOverlay.jsx';
import LineArtOverlay from './components/LineArtOverlay.jsx';
import SpatializerPanel from './components/SpatializerPanel.jsx';
import JurorChatBar from './components/JurorChatBar.jsx';
import DrawingsPanel from './components/DrawingsPanel.jsx';
import ArchivePanel from './components/ArchivePanel.jsx';
import DiagnosticsPanel from './components/DiagnosticsPanel.jsx';
import {
  getConfig, rebuild as rebuildApi, startBlenderBuild, getBlenderBuildStatus,
  carveNetworkCanyon as carveNetworkCanyonApi,
  generateCanopy as generateCanopyApi,
  jurorChat as jurorChatApi, getProgramZones, saveToArchive,
  archiveGeneration as archiveGenerationApi,
  getComfyStatus, startComfyRender, getComfyRenderStatus,
} from './api.js';
import { pointInZone, clipStructuralSpec, clipRectBounds } from './siteZones.js';

const BLENDER_POLL_MS = 1500;

const DEFAULT_PARAMS = {
  sketch_alpha: 0.75,
  canyon_width: 3,
  // 2026-07-17 demand-driven excavation: bumped from 1 -> 4 (36ft raw,
  // clamped to the real 30ft column-height cap) so the full real slab
  // depth range (-10/-20/-30ft) is reachable out of the box, not just a
  // single 9ft step -- see logic/pershing_api.py's excavation_scale.
  canyon_depth: 4,
  material_mode: 'STEEL',
  shoring_density: 1.0,
  use_real_amenity_data: false,
  use_real_foot_traffic_data: false,
  data_alpha: 1.0,
  use_real_noise_data: false,
  remove_top_slab: true,
  disabled_programs: [],
};

const DEFAULT_NETWORK_PARAMS = {
  motivator_weights: { trees: 1.0, water: 1.0, rest: 1.0, foot_traffic: 1.0, deficit: 1.0, program: 1.0 },
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
  panel_grid_rotation_deg: 0.0,
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
  const [activeTab, setActiveTab] = useState('SPATIALIZE');
  const [config, setConfig] = useState(null);
  const [programZones, setProgramZones] = useState(null);
  // Mirrors SpatializerPanel's live diagram (2026-07-24) -- reported up via
  // onStackChange so "Save Build" can carry the diagram that produced the
  // current 3D state along with it (see buildSnapshot/handleSaveBuild
  // below). SpatializerPanel stays the source of truth for the live
  // editing session; this is read-only here.
  const [spatializeState, setSpatializeState] = useState({ seed: [], narrative: '', prompt: '' });
  // Set by restoreSnapshot when a loaded build/archive entry carries a
  // spatial_seed -- SpatializerPanel watches this and loads it back into
  // its own live stack. nonce forces the effect to re-fire even when
  // restoring the exact same build twice in a row.
  const [restoreSpatializeSeed, setRestoreSpatializeSeed] = useState(null);
  const [params, setParams] = useState(DEFAULT_PARAMS);
  const [data, setData] = useState(null);
  const [rebuilding, setRebuilding] = useState(false);
  const [logs, setLogs] = useState([]);
  // Unified "Paint" dialog (2026-07-16) -- one trigger, PaintOverlay's own
  // Source tab picks sketch-painting vs. diagram-import internally (used
  // to be two separate buttons/dialogs, paintCategory + showDiagramInput).
  const [showPaint, setShowPaint] = useState(false);
  const [blenderBuild, setBlenderBuild] = useState({ status: 'idle', objUrl: null, svgUrl: null, error: null, durationS: null });
  const [lineartEnabled, setLineartEnabled] = useState(false);
  const [showLineArt, setShowLineArt] = useState(false);
  // Layer visibility toggles (2026-07-13, moved to ParamPanel's sidebar
  // 2026-07-13) -- lifted here (like removeTopSlab below) since both
  // ParamPanel (renders the checkboxes) and Viewport (filters what it
  // renders) need to share this state.
  const [visibleLayers, setVisibleLayers] = useState({
    realContext: true, structural: true, greenscape: true, trees: true,
    // 2026-08-17: canopy off by default -- opt-in via ParamPanel's layer
    // checkboxes instead of cluttering the initial RECONSTRUCT view.
    circulation: true, canopy: false, programZones: true, staticContext: true,
    // 2026-07-24: on by default -- extruded placeholder massing is now the
    // default view (previously opt-in, see logic/pershing_api.py's
    // rebuild() docstring for why this is a separate toggle from both
    // "Program Zones" and "Structural").
    programBoxes: true,
    // 2026-07-16 program-placement correlation logic: on by default -- these
    // markers now actively steer program placement (not just a passive
    // debug overlay), so a designer should see them without an extra click.
    attractors: true,
  });
  const [networkParams, setNetworkParams] = useState(DEFAULT_NETWORK_PARAMS);
  // 2026-07-23: no longer a separately-fetched result -- derived from the
  // regular rebuild response's network_* fields (see doRebuild below).
  // Growth now runs automatically on every debounced rebuild instead of
  // behind an explicit "Grow Network" button.
  const [networkData, setNetworkData] = useState(null);
  const [carvingCanyon, setCarvingCanyon] = useState(false);
  const [canopyParams, setCanopyParams] = useState(DEFAULT_CANOPY_PARAMS);
  const [canopyResult, setCanopyResult] = useState(null);
  const [generatingCanopy, setGeneratingCanopy] = useState(false);
  const [exportingVectorView, setExportingVectorView] = useState(false);
  const [comfyRender, setComfyRender] = useState({ status: 'idle', imageUrl: null, error: null });
  // Site-chunk export (2026-07-23) -- selectedZoneId resets to null whenever
  // zonesEnabled goes off, so re-enabling the toggle never silently resumes
  // isolating a stale zone from a previous session.
  const [zonesEnabled, setZonesEnabled] = useState(false);
  const [selectedZoneId, setSelectedZoneId] = useState(null);
  const [exportingZone, setExportingZone] = useState(false);
  const vectorExportPollRef = useRef(null);
  const zoneExportPollRef = useRef(null);
  const blenderPollRef = useRef(null);
  const comfyPollRef = useRef(null);
  // 2026-07-30: one-shot guard so restoreSnapshot's setParams call doesn't
  // trigger the debounced rebuild effect below into silently overwriting
  // the just-restored snapshot with a fresh live recompute -- see
  // restoreSnapshot's own comment for the full race.
  const skipNextRebuildRef = useRef(false);
  // 2026-08-17: bumped by doRebuild after a bake-triggered rebuild commits
  // -- see the autosave effect further down for why this indirection
  // exists instead of saving directly from doRebuild.
  const [autoSaveNonce, setAutoSaveNonce] = useState(0);

  const log = useCallback((text, level = 'info') => {
    setLogs((prev) => [...prev.slice(-49), { time: timeNow(), text, level }]);
  }, []);

  // 2026-08-17: optional 3rd arg so callers that represent an actual
  // bake+rebuild (SpatializerPanel/PaintOverlay's onBaked) can opt into
  // autosaving the result to the Archive -- see the autoSaveNonce effect
  // below for why this bumps a counter instead of calling handleSaveBuild
  // directly (avoids saving a stale pre-rebuild snapshot). ParamPanel's
  // plain "Rebuild" (slider tweaks) deliberately does NOT pass this --
  // archive entries are multi-MB and a bake is a much rarer, more
  // deliberate action than dragging a slider.
  const doRebuild = useCallback(
    async (nextParams, nextNetworkParams, options) => {
      const { autoSaveArchive = false } = options ?? {};
      setRebuilding(true);
      try {
        const payload = { ...(nextParams ?? params), network: nextNetworkParams ?? networkParams };
        const result = await rebuildApi(payload);
        setData(result);
        // 2026-07-23: network growth now runs inline as part of every
        // rebuild (see logic/pershing_api.py's RebuildParams.network) --
        // derive networkData from this same response instead of a separate
        // grow-network round-trip. result.network is only present when the
        // backend actually grew a network (it always will here, since
        // payload.network is always supplied above).
        if (result.network) {
          setNetworkData({
            network: result.network,
            kind_counts: result.network_kind_counts,
            node_count: result.network_node_count,
            attractor_count: result.network_attractor_count,
            attractors_unconsumed: result.network_attractors_unconsumed,
          });
        }
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
        // Bump instead of calling handleSaveBuild() here directly: this
        // closure's buildSnapshot/handleSaveBuild were captured at the last
        // render and would still see the PRE-rebuild `data` state (setData
        // above hasn't been committed/re-rendered yet at this point in the
        // async flow). The effect below fires after React commits the new
        // data/network/programZones state, so buildSnapshot() there is
        // guaranteed fresh.
        if (autoSaveArchive) setAutoSaveNonce((n) => n + 1);
      } catch (err) {
        log(String(err), 'error');
      } finally {
        setRebuilding(false);
      }
    },
    [params, networkParams, log],
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
  // blender/pershing_headless_build.py's build_structural_meshes).
  //
  // 2026-07-24 (accuracy fix, "programmed buildings are not shown"):
  // program_boxes (the per-bay building_mass massing boxes -- see
  // logic/pershing_api.py's rebuild() docstring) live in their own
  // top-level data.program_boxes field too, same reason as canopy --
  // build_structural_meshes never reads that field at all, so program
  // buildings silently never made it into any Blender export. Merged in
  // here unconditionally now (not gated on canopyResult existing, unlike
  // the earlier version of this function which early-returned `data`
  // unchanged whenever canopy hadn't been generated yet -- that
  // accidentally skipped program_boxes too on every export before a
  // canopy generation had run).
  //
  // remove_top_slab (2026-07-24, same "slabs are not the same" accuracy
  // fix) -- the live viewport's own remove_top_slab param, needed by
  // blender/pershing_headless_build.py's build_real_context_meshes() to
  // decide whether to skip the topmost real slab, matching the live view's
  // own RealSlabs() rule. Not part of `data` itself (that's the rebuild()
  // response, not the request params that produced it).
  const dataForBlenderExport = useCallback(() => {
    if (!data) return data;
    return {
      ...data,
      structural: [
        ...data.structural,
        ...(data.program_boxes || []),
        ...(canopyResult?.canopy_panels || []),
        ...(canopyResult?.canopy_columns || []),
      ],
      remove_top_slab: params.remove_top_slab,
    };
  }, [data, canopyResult, params.remove_top_slab]);

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
              // Backend already copied the SVG into data/PershingMetabolizer/
              // parkSVG/remixedGeneratedSVGs/ as part of the build job (see
              // logic/pershing_blender.py) -- no client-side download needed.
              log(`vector export done in ${job.duration_s}s -> remixedGeneratedSVGs/`);
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
    [data, dataForBlenderExport, log, stopVectorExportPoll],
  );

  useEffect(() => stopVectorExportPoll, [stopVectorExportPoll]);

  // "Send to ComfyUI" (Viewport.jsx, perspective mode only) -- same job/
  // poll shape as handleBuildInBlender/handleExportVectorView above, but
  // against /api/comfy-render (logic/comfy_render_job.py) instead of the
  // Blender build pipeline. Checks /api/comfy-status first so a cold/absent
  // ComfyUI instance fails fast with a clear log line instead of queuing a
  // job that will only discover that 300s later.
  const stopComfyPoll = useCallback(() => {
    if (comfyPollRef.current) {
      clearInterval(comfyPollRef.current);
      comfyPollRef.current = null;
    }
  }, []);

  const handleSendToComfy = useCallback(
    async (dataUrl, narrative) => {
      stopComfyPoll();
      setComfyRender({ status: 'queued', imageUrl: null, error: null });
      try {
        const { online } = await getComfyStatus();
        if (!online) {
          log('ComfyUI not reachable at 127.0.0.1:8188', 'error');
          setComfyRender({ status: 'error', imageUrl: null, error: 'ComfyUI not reachable' });
          return;
        }
        const { job_id } = await startComfyRender(dataUrl, narrative);
        log(`comfy render queued: ${job_id}`);
        comfyPollRef.current = setInterval(async () => {
          try {
            const job = await getComfyRenderStatus(job_id);
            setComfyRender({ status: job.status, imageUrl: job.image_url, error: job.error });
            if (job.status === 'done') {
              stopComfyPoll();
              log('comfy render done');
            } else if (job.status === 'error') {
              stopComfyPoll();
              log(`comfy render failed: ${job.error}`, 'error');
            }
          } catch (err) {
            stopComfyPoll();
            log(String(err), 'error');
            setComfyRender((prev) => ({ ...prev, status: 'error', error: String(err) }));
          }
        }, BLENDER_POLL_MS);
      } catch (err) {
        log(String(err), 'error');
        setComfyRender({ status: 'error', imageUrl: null, error: String(err) });
      }
    },
    [log, stopComfyPoll],
  );

  useEffect(() => stopComfyPoll, [stopComfyPoll]);

  const handleToggleZones = useCallback((enabled) => {
    setZonesEnabled(enabled);
    if (!enabled) setSelectedZoneId(null);
  }, []);

  const stopZoneExportPoll = useCallback(() => {
    if (zoneExportPollRef.current) {
      clearInterval(zoneExportPollRef.current);
      zoneExportPollRef.current = null;
    }
  }, []);

  // Site-chunk export (2026-07-23, true per-object clipping + full geometry
  // coverage 2026-07-24) -- reuses the exact same headless-Blender OBJ
  // pipeline "Build in Blender" does (shares blenderBuild/BLENDER_POLL_MS so
  // the two can't run two builds at once, same as vector-export already
  // does above), with every real geometry source clipped to the selected
  // zone's footprint via siteZones.js's clipStructuralSpec/clipRectBounds --
  // see Viewport.jsx's isolatedData (same clip functions) for what the user
  // is actually looking at on screen when they click this; the two are kept
  // in sync by sharing that module rather than duplicating the math.
  //
  // Network paths (previously excluded entirely from exports) are now
  // merged into `structural` before clipping, same as canopy panels/columns
  // already are via dataForBlenderExport(). ramp_meshes (real imported Rhino
  // triangle meshes, not parametric specs -- see build_ramp_meshes in
  // blender/pershing_headless_build.py) has no cheap true-clip path, so it's
  // dropped from the zone payload entirely rather than left unclipped and
  // spanning past the cut.
  const handleExportZone = useCallback(
    async (zone) => {
      if (!data || !config) return;
      stopZoneExportPoll();
      setExportingZone(true);
      const voxelFt = config.voxel_ft;
      const base = dataForBlenderExport();
      const allStructural = [...base.structural, ...(networkData?.network || [])];
      const clipSpecs = (specs) => (specs || []).map((s) => clipStructuralSpec(s, zone)).filter(Boolean);
      const clippedSlabs = (base.real_slabs || [])
        .map((slab) => {
          const xs = slab.top_corners_ft.map((c) => c[0]);
          const ys = slab.top_corners_ft.map((c) => c[1]);
          const clipped = clipRectBounds(Math.min(...xs), Math.max(...xs), Math.min(...ys), Math.max(...ys), zone);
          if (!clipped) return null;
          const z = slab.top_corners_ft[0][2];
          return {
            ...slab,
            top_corners_ft: [
              [clipped.xMin, clipped.yMin, z], [clipped.xMax, clipped.yMin, z],
              [clipped.xMax, clipped.yMax, z], [clipped.xMin, clipped.yMax, z],
            ],
            area_ft2: (clipped.xMax - clipped.xMin) * (clipped.yMax - clipped.yMin),
          };
        })
        .filter(Boolean);
      const zoneData = {
        ...base,
        voxels: base.voxels.filter((v) =>
          pointInZone(v.gx * voxelFt + voxelFt / 2, v.gy * voxelFt + voxelFt / 2, zone)),
        // program_boxes is already folded into base.structural by
        // dataForBlenderExport() (2026-07-24) and clipped there via
        // allStructural above -- no separate clip needed here (the
        // top-level program_boxes field itself is never read by the
        // Blender script, only "structural" is).
        structural: clipSpecs(allStructural),
        real_slabs: clippedSlabs,
        real_columns: (base.real_columns || []).filter((c) => pointInZone(c.x, c.z, zone)),
        // real_slab_fragments (2026-07-24, same accuracy fix
        // build_real_context_meshes() now relies on) -- clipped the same
        // way Viewport.jsx's isolatedData already does, so a partially-
        // excavated real slab's surviving fragments only appear inside the
        // exported zone, not the slab's full original footprint.
        real_slab_fragments: Object.fromEntries(
          Object.entries(base.real_slab_fragments || {}).map(([key, entry]) => [
            key,
            { ...entry, remaining: entry.remaining.filter(([wx, wy]) => pointInZone(wx, wy, zone)) },
          ]),
        ),
        ramp_meshes: {},
      };
      const tag = `zone${zone.id + 1}`;
      try {
        const { job_id } = await startBlenderBuild(zoneData, false, null, false, tag);
        log(`${zone.label} export queued: ${job_id} (${zoneData.voxels.length} voxels, ${zoneData.structural.length} structural, ${zoneData.real_slabs.length} real slabs)`);
        zoneExportPollRef.current = setInterval(async () => {
          try {
            const job = await getBlenderBuildStatus(job_id);
            if (job.status === 'done') {
              stopZoneExportPoll();
              setBlenderBuild({
                status: job.status, objUrl: job.obj_url, svgUrl: job.svg_url,
                error: job.error, durationS: job.duration_s,
              });
              log(`${zone.label} export done in ${job.duration_s}s`);
              setExportingZone(false);
            } else if (job.status === 'error') {
              stopZoneExportPoll();
              log(`${zone.label} export failed: ${job.error}`, 'error');
              setExportingZone(false);
            }
          } catch (err) {
            stopZoneExportPoll();
            log(String(err), 'error');
            setExportingZone(false);
          }
        }, BLENDER_POLL_MS);
      } catch (err) {
        log(String(err), 'error');
        setExportingZone(false);
      }
    },
    [data, config, dataForBlenderExport, networkData, log, stopZoneExportPoll],
  );

  useEffect(() => stopZoneExportPoll, [stopZoneExportPoll]);

  // Carve a canyon along the grown network's primary trunk (2026-07-23) --
  // explicit action, deliberately NOT folded into the automatic rebuild
  // loop the way network growth itself now is: carving reshapes terrain,
  // and terrain feeds back into where growth happens next, so auto-carving
  // on every debounced rebuild would risk a drift loop (see
  // logic/pershing_api.py's carve_network_canyon() docstring). Commits into
  // the live paint state server-side, then rebuilds to show the result --
  // same "compose then commit" pattern as bake().
  const handleCarveCanyon = useCallback(async () => {
    setCarvingCanyon(true);
    try {
      const result = await carveNetworkCanyonApi(params, networkParams);
      log(`canyon carved: ${result.carved_cells} cell(s), ${result.canyon_cells} total canyon cells`);
      await doRebuild(params, networkParams);
    } catch (err) {
      log(String(err), 'error');
    } finally {
      setCarvingCanyon(false);
    }
  }, [params, networkParams, log, doRebuild]);

  // Organic panelized canopy + branching supports (2026-07-16 Canopy
  // Redesign). Real per-cell panel/support generation (up to a few thousand
  // panels) has no reason to rerun on every trivial slider tweak, so this
  // stays its own callback rather than folding into the fast 200ms rebuild
  // loop (same reasoning circulation-network growth outgrew 2026-07-23, but
  // canopy's per-request cost is real enough that it still doesn't apply
  // here) -- see the slower auto-trigger effect below instead, plus this
  // button for an explicit "regenerate now."
  //
  // 2026-07-23: footprint existence no longer requires painting first --
  // logic/canopy_engine.py's _auto_coverage_mask() now seeds coverage
  // automatically around green_space/sports_recreation/outdoor program
  // zones (real shade-relevant categories, see
  // data/program_requirements.json's _shade_meta), max-merged against
  // whatever's painted. Painting remains a supported additive override.
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

  // Auto-regenerate canopy (2026-07-23) -- fires whenever program zones
  // change (rebuild's own response refreshes programZones every time, see
  // doRebuild above), on its own slower debounce than the 200ms rebuild
  // loop: canopy generation is real per-cell work, not worth re-running on
  // every intermediate rebuild in a burst of rapid slider drags, only once
  // things settle. Deliberately does NOT depend on canopyParams -- those
  // are cosmetic shape sliders (wave height/pitch/etc.), not footprint
  // inputs, so tweaking them stays a manual "Generate Canopy" click, same
  // "heavy compute -> explicit" instinct the button itself already
  // documents above.
  useEffect(() => {
    if (!programZones?.zones?.length || generatingCanopy) return;
    const t = setTimeout(() => { handleGenerateCanopy(); }, 900);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [programZones]);

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
    // 2026-07-30: restoreSnapshot sets this synchronously right before its
    // own setParams/setNetworkParams calls, which otherwise change this
    // effect's own deps and would fire a rebuild ~200ms after a restore,
    // clobbering the just-restored data with a fresh live recompute.
    // React 18 batches restoreSnapshot's several setState calls into one
    // re-render, so this effect only runs (and is skipped) once per
    // restore -- normal param changes afterward are never affected.
    if (skipNextRebuildRef.current) {
      skipNextRebuildRef.current = false;
      return;
    }
    // 2026-07-23: also fires on networkParams changes now that growth runs
    // inline with every rebuild (see doRebuild/RebuildParams.network) --
    // widened from [params, config] so a motivator-weight/step_ft tweak
    // regrows the network the same way a terrain slider re-excavates,
    // without a separate manual "Grow Network" click.
    const t = setTimeout(() => doRebuild(params, networkParams), 200);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [params, networkParams, config]);

  // Juror chat live control (2026-07-10) -- dispatches the model's returned
  // action through the EXACT SAME state setters the matching UI control
  // already uses (a motivator slider drag, a canyon slider drag, a data
  // toggle), so a chat-driven change is indistinguishable downstream from a
  // manual one: canyon width/depth, the data toggles, AND motivator weights
  // now all flow into the same debounced auto-rebuild effect above (network
  // growth stopped being a separate manual step 2026-07-23 -- see
  // RebuildParams.network). logic/juror_chat.py's _validate_action already
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
          // 2026-07-23: network growth is automatic now (every rebuild) --
          // nothing left for this action to explicitly trigger. Kept as a
          // recognized no-op rather than removed, since
          // logic/juror_chat.py's _validate_action can still emit it and
          // falling through to the default case below would log it as an
          // error, which it no longer is.
          log('network already grows automatically with every rebuild');
          break;
        default:
          log(`juror chat returned an unrecognized action type: ${action.type}`, 'error');
      }
    },
    [log],
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
  // on-screen state (params, the full rebuild result, network
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
      // 2026-07-24: whatever SPATIALIZE diagram is currently live, if any
      // (empty seed when the build came from painting only, or was never
      // touched via SPATIALIZE) -- see restoreSnapshot below for the other
      // half of this round-trip.
      spatial_seed: spatializeState.seed,
      spatialize_narrative: spatializeState.narrative,
      spatialize_prompt: spatializeState.prompt,
    };
  }, [config, params, networkParams, canopyParams, data, networkData, canopyResult, programZones, spatializeState]);

  const restoreSnapshot = useCallback(
    (snapshot) => {
      if (!snapshot.data) throw new Error("missing 'data' field -- not a valid build snapshot");
      // 2026-07-30: setParams below changes the debounced rebuild effect's
      // own dependency, which used to fire ~200ms later and silently
      // overwrite the setData(snapshot.data) below with a fresh live
      // recompute against CURRENT server-side paint masks/sliders --
      // defeating the whole point of this function (see its own comment
      // above: recall exactly what was saved, not a re-run of the
      // pipeline). Concretely: a slab the snapshot had marked removed
      // could silently reappear if the live masks no longer excavated it.
      // Setting this ref synchronously, before the state updates below,
      // skips exactly that one auto-triggered rebuild.
      skipNextRebuildRef.current = true;
      if (snapshot.params) setParams(snapshot.params);
      if (snapshot.network_params) setNetworkParams(snapshot.network_params);
      if (snapshot.canopy_params) setCanopyParams(snapshot.canopy_params);
      setData(snapshot.data);
      setNetworkData(snapshot.network_data ?? null);
      setCanopyResult(snapshot.canopy_data ?? null);
      setProgramZones(snapshot.program_zones ?? null);
      // 2026-07-24: hand the saved diagram (if any) back to SpatializerPanel
      // so the 2D side reflects a restored build too, not just the 3D one.
      if (snapshot.spatial_seed?.length) {
        setRestoreSpatializeSeed({
          seed: snapshot.spatial_seed,
          narrative: snapshot.spatialize_narrative || '',
          nonce: Date.now(),
        });
      }
    },
    [],
  );

  const [savingBuild, setSavingBuild] = useState(false);

  const handleSaveBuild = useCallback(async (options) => {
    const { auto = false } = options ?? {};
    const snapshot = buildSnapshot();
    if (!snapshot) return;
    setSavingBuild(true);
    try {
      const result = await saveToArchive(snapshot, '');
      log(`${auto ? 'autosaved after bake' : 'build saved'}: ${result.label || result.filename}`);
      // 2026-07-24: also archives as a "2D generation" record (same shape/
      // dir list2DGenerations() already reads) so the diagram that produced
      // this build shows up in SPATIALIZE's "Recent 2D Generations" panel
      // too -- see app.py's archive_generation_record(). No-op when the
      // build wasn't produced via SPATIALIZE (empty seed).
      if (spatializeState.seed.length) {
        const genResult = await archiveGenerationApi(
          spatializeState.prompt, spatializeState.narrative, spatializeState.seed);
        if (genResult.filename) log(`diagram archived as generation: ${genResult.filename}`);
      }
    } catch (err) {
      log(String(err), 'error');
    } finally {
      setSavingBuild(false);
    }
  }, [buildSnapshot, spatializeState, log]);

  // 2026-08-17: fires after a bake-triggered rebuild's state (data/
  // network/programZones) has actually committed -- see doRebuild's
  // autoSaveArchive branch above, which only bumps the nonce, not save
  // directly, to avoid archiving a stale pre-rebuild snapshot. Guarded by
  // buildSnapshot's own `if (!data) return null` for the mount-time fire
  // every useEffect gets for free, so no extra "skip first run" ref needed.
  useEffect(() => {
    if (autoSaveNonce === 0) return;
    handleSaveBuild({ auto: true });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [autoSaveNonce]);

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
        {/* Stays mounted across tab switches (display:none, not unmounted) so
            the composed stack/narrative/SVG cache survive leaving the tab --
            previously conditional rendering unmounted it on every switch,
            silently discarding an in-progress generation. */}
        <div className={`flex flex-1 overflow-hidden ${activeTab === 'SPATIALIZE' ? '' : 'hidden'}`}>
          <SpatializerPanel
            onBaked={async () => {
              // Both of SpatializerPanel's own bake actions (Bake+Rebuild,
              // Load+Bake This Generation) are deliberate clicks, not a
              // debounced auto-trigger, so always autosave here.
              await doRebuild(params, undefined, { autoSaveArchive: true });
            }}
            onPaint={() => setShowPaint(true)}
            log={log}
            onStackChange={setSpatializeState}
            restoreSeed={restoreSpatializeSeed}
          />
        </div>
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
                  zonesEnabled={zonesEnabled}
                  onToggleZones={handleToggleZones}
                  selectedZoneId={selectedZoneId}
                  onSelectZone={setSelectedZoneId}
                  onExportZone={handleExportZone}
                  exportingZone={exportingZone}
                  onShowLineArt={() => setShowLineArt(true)}
                  onExportVectorView={handleExportVectorView}
                  exportingVectorView={exportingVectorView}
                  comfyNarrative={spatializeState.narrative}
                  comfyRender={comfyRender}
                  onSendToComfy={handleSendToComfy}
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
              networkResult={networkData}
              onCarveCanyon={handleCarveCanyon}
              carvingCanyon={carvingCanyon}
              canopyParams={canopyParams}
              onCanopyParamsChange={setCanopyParams}
              onGenerateCanopy={handleGenerateCanopy}
              generatingCanopy={generatingCanopy}
              canopyResult={canopyResult}
              programZones={programZones?.zones}
            />
          </>
        )}
        {activeTab === 'DRAWINGS' && <DrawingsPanel params={params} log={log} />}
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
          // and the auto-bake path. explicit (PaintOverlay's closeAfterBake)
          // gates the Archive autosave: only the deliberate "Bake Painted
          // Sketch" click qualifies, not the 600ms debounced auto-bake that
          // fires on every pause mid-stroke -- that would spam the Archive
          // with a multi-MB snapshot several times a minute while painting.
          onBaked={async (explicit) => {
            await doRebuild(params, undefined, { autoSaveArchive: !!explicit });
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
