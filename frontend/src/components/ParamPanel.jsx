function Slider({ label, value, min, max, step, onChange, format }) {
  return (
    <div className="space-y-2">
      <div className="flex justify-between font-mono-sm text-mono-sm">
        <span className="text-on-surface-variant uppercase">{label}</span>
        <span className="text-accent">{format ? format(value) : value}</span>
      </div>
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(e) => onChange(parseFloat(e.target.value))}
        className="w-full h-[1px] bg-border appearance-none cursor-pointer accent-accent"
      />
    </div>
  );
}

const BLENDER_BUILD_LABEL = {
  idle: 'Build in Blender',
  queued: 'Queued...',
  running: 'Building...',
  done: 'Rebuild in Blender',
  error: 'Retry Blender Build',
};

const AMENITY_KINDS = ['water_plane', 'water_cascade_block', 'misting_line', 'bench_assembly', 'restroom_pod', 'fountain'];

const MOTIVATOR_LABELS = [
  ['trees', 'Trees'], ['water', 'Water'], ['rest', 'Rest'],
  ['foot_traffic', 'Foot Traffic'], ['deficit', 'Deficit'], ['program', 'Program Zones'],
];

// Layer visibility toggle list (2026-07-13, moved from Viewport's own HUD
// panel into this sidebar) -- keys match App.jsx's visibleLayers state.
const LAYER_TOGGLES = [
  { key: 'realContext', label: 'Real Slabs/Cols' },
  { key: 'structural', label: 'Structural' },
  { key: 'greenscape', label: 'Greenscape' },
  { key: 'trees', label: 'Trees' },
  { key: 'circulation', label: 'Circulation' },
  { key: 'canopy', label: 'Canopy' },
  { key: 'programZones', label: 'Program Zones' },
  // Sub-option of Program Zones, not an independent layer (2026-07-16) --
  // same zone data, just swaps flat footprint plates for extruded
  // placeholder massing. Indented + disabled when Program Zones itself is
  // off, per ParamPanel's own render loop below.
  { key: 'programBoxes', label: 'Extrude as Boxes', indent: true },
  // Independent of Program Zones (2026-07-16 program-placement correlation
  // logic) -- major/minor attractor markers from a baked diagram import,
  // now an input to WHERE programs place, not just a debug overlay of the
  // zones themselves. See logic/program_placement.py's
  // CATEGORY_ATTRACTOR_AFFINITY.
  { key: 'attractors', label: 'Attractors' },
  { key: 'staticContext', label: 'Static Context' },
];

export default function ParamPanel({
  config, params, onParamsChange, onRebuild, slabHarvestTons, kindCounts,
  usedRealAmenityData, usedRealFootTrafficData, usedRealNoiseData, circulationVoxelCount, sanctuaryVoxelCount,
  rebuilding, visibleLayers, onToggleLayer, blenderBuild,
  onBuildInBlender, lineartEnabled, onLineartEnabledChange, networkParams, onNetworkParamsChange,
  networkResult, onCarveCanyon, carvingCanyon,
  canopyParams, onCanopyParamsChange, onGenerateCanopy, generatingCanopy, canopyResult,
}) {
  const set = (key) => (value) => onParamsChange({ ...params, [key]: value });
  const blenderBusy = blenderBuild?.status === 'queued' || blenderBuild?.status === 'running';

  const setNetworkWeight = (key) => (value) =>
    onNetworkParamsChange({
      ...networkParams,
      motivator_weights: { ...networkParams.motivator_weights, [key]: value },
    });
  const setNetworkField = (key) => (value) => onNetworkParamsChange({ ...networkParams, [key]: value });
  const setCanopyField = (key) => (value) => onCanopyParamsChange({ ...canopyParams, [key]: value });

  return (
    <aside className="w-80 border-l border-border bg-surface flex flex-col shrink-0 overflow-y-auto">
      <div className="p-container border-b border-border space-y-6">
        <div className="flex items-center gap-2">
          <h3 className="font-headline-md text-headline-md text-primary">PARAMETERS</h3>
        </div>

        <Slider
          label="Sketch Alpha"
          value={params.sketch_alpha}
          min={0}
          max={1}
          step={0.01}
          onChange={set('sketch_alpha')}
          format={(v) => `${Math.round(v * 100)}%`}
        />
      </div>

      <div className="p-container border-b border-border space-y-2">
        <h4 className="font-mono-label text-mono-label text-on-surface-variant uppercase tracking-widest">
          Layers
        </h4>
        {LAYER_TOGGLES.map(({ key, label, indent }) => (
          <label
            key={key}
            className={`flex items-center gap-2 font-mono-sm text-mono-sm text-on-surface-variant cursor-pointer ${
              indent ? 'pl-5' : ''
            } ${indent && !visibleLayers.programZones ? 'opacity-40' : ''}`}
          >
            <input
              type="checkbox"
              checked={visibleLayers[key]}
              disabled={indent && !visibleLayers.programZones}
              onChange={() => onToggleLayer(key)}
              className="accent-accent"
            />
            {label}
          </label>
        ))}
      </div>

      <div className="p-container border-b border-border space-y-6">
        <h4 className="font-mono-label text-mono-label text-on-surface-variant uppercase tracking-widest">
          Structural Framing Engine
        </h4>
        <Slider
          label="Canyon Width (bays)"
          value={params.canyon_width}
          min={1}
          max={config?.nx_bays ?? 13}
          step={1}
          onChange={set('canyon_width')}
        />
        <Slider
          label="Canyon Depth (levels)"
          value={params.canyon_depth}
          min={1}
          max={4}
          step={1}
          onChange={set('canyon_depth')}
        />
        <div className="space-y-2">
          <label className="font-mono-sm text-mono-sm text-on-surface-variant uppercase block">
            Material Mode
          </label>
          <select
            value={params.material_mode}
            onChange={(e) => set('material_mode')(e.target.value)}
            className="w-full bg-background border border-border font-mono-sm text-mono-sm p-3 focus:ring-0 focus:border-accent text-on-surface outline-none appearance-none cursor-pointer"
          >
            <option value="STEEL">STEEL</option>
            <option value="WOOD">WOOD</option>
          </select>
        </div>
        <Slider
          label="Shoring Density"
          value={params.shoring_density}
          min={0.5}
          max={2.0}
          step={0.01}
          onChange={set('shoring_density')}
        />
        <div className="font-mono-sm text-mono-sm text-on-surface-variant">
          Slab Material Harvested:{' '}
          <span className="text-accent">{slabHarvestTons?.toFixed(0) ?? 0} Tons</span>
        </div>
      </div>

      <div className="p-container border-b border-border space-y-3">
        <h4 className="font-mono-label text-mono-label text-on-surface-variant uppercase tracking-widest">
          Canopy Engine
        </h4>
        <p className="font-mono-sm text-[11px] text-on-surface-variant">
          Panels auto-cover green space, sports/recreation, and outdoor program zones (real shade-relevant
          categories) a few moments after program placement changes -- the "Canopy" paint brush still works
          as an additional override, it's just no longer required. These sliders control the wave/crest
          shape and support columns, not where it exists -- tweak them, then click below to regenerate now.
        </p>
        <Slider
          label="Base Height (ft)"
          value={canopyParams.base_height_ft}
          min={8}
          max={40}
          step={0.5}
          onChange={setCanopyField('base_height_ft')}
        />
        <Slider
          label="Wave Amplitude (ft)"
          value={canopyParams.wave_amplitude_ft}
          min={0}
          max={20}
          step={0.5}
          onChange={setCanopyField('wave_amplitude_ft')}
        />
        <Slider
          label="Wave Length X (ft)"
          value={canopyParams.wave_length_x_ft}
          min={20}
          max={300}
          step={5}
          onChange={setCanopyField('wave_length_x_ft')}
        />
        <Slider
          label="Wave Length Y (ft)"
          value={canopyParams.wave_length_y_ft}
          min={20}
          max={300}
          step={5}
          onChange={setCanopyField('wave_length_y_ft')}
        />
        <Slider
          label="Wave Phase X"
          value={canopyParams.wave_phase_x}
          min={0}
          max={6.283}
          step={0.05}
          onChange={setCanopyField('wave_phase_x')}
        />
        <Slider
          label="Wave Phase Y"
          value={canopyParams.wave_phase_y}
          min={0}
          max={6.283}
          step={0.05}
          onChange={setCanopyField('wave_phase_y')}
        />
        <Slider
          label="Excavation Dip (ft)"
          value={canopyParams.dip_weight_ft}
          min={0}
          max={20}
          step={0.5}
          onChange={setCanopyField('dip_weight_ft')}
        />
        <Slider
          label="Program Zone Crest (ft)"
          value={canopyParams.program_boost_ft}
          min={0}
          max={20}
          step={0.5}
          onChange={setCanopyField('program_boost_ft')}
        />
        <Slider
          label="Panel Pitch (ft)"
          value={canopyParams.panel_pitch_ft}
          min={4.5}
          max={18}
          step={0.5}
          onChange={setCanopyField('panel_pitch_ft')}
        />
        <Slider
          label="Panel Grid Rotation (deg)"
          value={canopyParams.panel_grid_rotation_deg}
          min={0}
          max={90}
          step={1}
          onChange={setCanopyField('panel_grid_rotation_deg')}
        />
        <Slider
          label="Support Tie-Back Tolerance (ft)"
          value={canopyParams.support_tie_back_tolerance_ft}
          min={0}
          max={40}
          step={1}
          onChange={setCanopyField('support_tie_back_tolerance_ft')}
        />
        <button
          onClick={onGenerateCanopy}
          disabled={generatingCanopy || !onGenerateCanopy}
          title="Canopy also regenerates automatically a few moments after program zones change -- this forces it now, e.g. after tweaking the shape sliders above."
          className="w-full py-3 border border-accent text-accent font-mono-sm text-mono-sm font-bold uppercase tracking-widest hover:bg-accent hover:text-background transition-all active:scale-[0.98] disabled:opacity-50"
        >
          {generatingCanopy ? 'Generating...' : 'Regenerate Canopy Now'}
        </button>
        {canopyResult && (
          <div className="font-mono-sm text-[11px] text-on-surface-variant space-y-1">
            <div>panels: <span className="text-accent">{canopyResult.kind_counts.canopy_panel ?? 0}</span></div>
            <div>
              support columns: <span className="text-accent">
                {(canopyResult.kind_counts.canopy_column_trunk ?? 0) + (canopyResult.kind_counts.canopy_column_branch ?? 0)}
              </span>
            </div>
            {(canopyResult.kind_counts.canopy_panel ?? 0) === 0 && (
              <div className="text-error">
                no green_space/sports_recreation/outdoor zones placed yet, and nothing painted -- place
                program or paint the Canopy brush to give it something to cover
              </div>
            )}
          </div>
        )}
      </div>

      <div className="p-container border-b border-border space-y-3">
        <h4 className="font-mono-label text-mono-label text-on-surface-variant uppercase tracking-widest">
          Programs
        </h4>
        <p className="font-mono-sm text-[11px] text-on-surface-variant">
          Uncheck a program to exclude it entirely from this rebuild's placement pass (e.g. turn off
          Soccer Field if it's claiming more of the site than you want).
        </p>
        {(config?.all_programs ?? []).map((program) => {
          const disabled = params.disabled_programs.includes(program.id);
          const toggle = (e) => {
            const next = e.target.checked
              ? params.disabled_programs.filter((id) => id !== program.id)
              : [...params.disabled_programs, program.id];
            onParamsChange({ ...params, disabled_programs: next });
          };
          return (
            <label
              key={program.id}
              className="flex items-center gap-2 font-mono-sm text-mono-sm text-on-surface-variant cursor-pointer"
            >
              <input type="checkbox" checked={!disabled} onChange={toggle} className="accent-accent" />
              {program.label}
            </label>
          );
        })}
      </div>

      <div className="p-container border-b border-border space-y-3">
        <h4 className="font-mono-label text-mono-label text-on-surface-variant uppercase tracking-widest">
          Amenity Deficit
        </h4>
        <label className="flex items-center gap-2 font-mono-sm text-mono-sm text-on-surface-variant cursor-pointer">
          <input
            type="checkbox"
            checked={params.use_real_amenity_data}
            disabled={!config?.amenity_csv}
            onChange={(e) => set('use_real_amenity_data')(e.target.checked)}
            className="accent-accent"
          />
          Use Real Amenity Data
        </label>
        <div className="font-mono-sm text-[11px] text-on-surface-variant">
          {config?.amenity_csv ? `csv: ${config.amenity_csv}` : 'no amenity CSV found -- using placeholder'}
        </div>
        <div className="font-mono-sm text-[11px] text-on-surface-variant">
          {usedRealAmenityData === false && params.use_real_amenity_data
            ? 'placeholder in use (no CSV)'
            : usedRealAmenityData === true
              ? 'real survey data in use'
              : null}
        </div>
        <div className="font-mono-sm text-mono-sm text-on-surface-variant">
          Amenities placed:{' '}
          <span className="text-accent">
            {AMENITY_KINDS.reduce((sum, k) => sum + (kindCounts?.[k] ?? 0), 0)}
          </span>
        </div>
      </div>

      <div className="p-container border-b border-border space-y-3">
        <h4 className="font-mono-label text-mono-label text-on-surface-variant uppercase tracking-widest">
          Foot Traffic / Circulation
        </h4>
        <p className="font-mono-sm text-[11px] text-on-surface-variant">
          Stage 1: classifies painted Hardscape cells as Circulation where foot-traffic influence is
          high enough -- no path/bridge network yet, that's a separate later pass.
        </p>
        <label className="flex items-center gap-2 font-mono-sm text-mono-sm text-on-surface-variant cursor-pointer">
          <input
            type="checkbox"
            checked={params.use_real_foot_traffic_data}
            disabled={!config?.foot_traffic_csv}
            onChange={(e) => set('use_real_foot_traffic_data')(e.target.checked)}
            className="accent-accent"
          />
          Use Real Foot Traffic Data
        </label>
        <div className="font-mono-sm text-[11px] text-on-surface-variant">
          {config?.foot_traffic_csv ? `csv: ${config.foot_traffic_csv}` : 'no foot traffic CSV found -- using placeholder'}
        </div>
        <div className="font-mono-sm text-[11px] text-on-surface-variant">
          {usedRealFootTrafficData === false && params.use_real_foot_traffic_data
            ? 'placeholder in use (no CSV)'
            : usedRealFootTrafficData === true
              ? 'real foot traffic data in use'
              : null}
        </div>
        <div className="font-mono-sm text-mono-sm text-on-surface-variant">
          Circulation cells:{' '}
          <span className="text-accent">{circulationVoxelCount ?? 0}</span>
        </div>
      </div>

      <div className="p-container border-b border-border space-y-3">
        <h4 className="font-mono-label text-mono-label text-on-surface-variant uppercase tracking-widest">
          Noise / Sanctuary Quiet
        </h4>
        <p className="font-mono-sm text-[11px] text-on-surface-variant">
          A cell painted Greenscape+Amenity/Resting only keeps Sanctuary status if it's quiet enough --
          Data Alpha controls how strongly real (or placeholder) noise data can override that painted
          intent. 0 = noise data never disqualifies a painted Sanctuary; 1 = full effect.
        </p>
        <Slider
          label="Data Alpha"
          value={params.data_alpha}
          min={0}
          max={1}
          step={0.01}
          onChange={set('data_alpha')}
          format={(v) => `${Math.round(v * 100)}%`}
        />
        <label className="flex items-center gap-2 font-mono-sm text-mono-sm text-on-surface-variant cursor-pointer">
          <input
            type="checkbox"
            checked={params.use_real_noise_data}
            disabled={!config?.noise_csv}
            onChange={(e) => set('use_real_noise_data')(e.target.checked)}
            className="accent-accent"
          />
          Use Real Noise Data
        </label>
        <div className="font-mono-sm text-[11px] text-on-surface-variant">
          {config?.noise_csv ? `csv: ${config.noise_csv}` : 'no noise CSV found -- using placeholder'}
        </div>
        <div className="font-mono-sm text-[11px] text-on-surface-variant">
          {usedRealNoiseData === false && params.use_real_noise_data
            ? 'placeholder in use (no CSV)'
            : usedRealNoiseData === true
              ? 'real noise data in use'
              : null}
        </div>
        <div className="font-mono-sm text-mono-sm text-on-surface-variant">
          Sanctuary cells:{' '}
          <span className="text-accent">{sanctuaryVoxelCount ?? 0}</span>
        </div>
      </div>

      <div className="p-container border-b border-border space-y-3">
        <h4 className="font-mono-label text-mono-label text-on-surface-variant uppercase tracking-widest">
          Full-Fidelity Build (Headless Blender)
        </h4>
        <p className="font-mono-sm text-[11px] text-on-surface-variant">
          Sends the current voxel/structural result to headless Blender for a real concatenated mesh
          export -- separate from the live view, not part of the rebuild loop above.
        </p>
        <label className="flex items-center gap-2 font-mono-sm text-mono-sm text-on-surface-variant cursor-pointer">
          <input
            type="checkbox"
            checked={lineartEnabled}
            onChange={(e) => onLineartEnabledChange?.(e.target.checked)}
            className="accent-accent"
          />
          Include Line Art SVG
        </label>
        <button
          onClick={onBuildInBlender}
          disabled={blenderBusy || !onBuildInBlender}
          className="w-full py-3 border border-accent text-accent font-mono-sm text-mono-sm font-bold uppercase tracking-widest hover:bg-accent hover:text-background transition-all active:scale-[0.98] disabled:opacity-50"
        >
          {BLENDER_BUILD_LABEL[blenderBuild?.status ?? 'idle']}
        </button>
        {blenderBuild?.status === 'done' && (
          <div className="font-mono-sm text-mono-sm text-accent">done in {blenderBuild.durationS}s</div>
        )}
        {blenderBuild?.status === 'error' && (
          <div className="font-mono-sm text-[11px] text-error break-words">{blenderBuild.error}</div>
        )}
      </div>

      <div className="p-container border-b border-border space-y-3">
        <h4 className="font-mono-label text-mono-label text-on-surface-variant uppercase tracking-widest">
          Circulation Growth Network
        </h4>
        <p className="font-mono-sm text-[11px] text-on-surface-variant">
          Grows a real pedestrian network outward from the site's entrances toward weighted motivators --
          regrows automatically with every rebuild, including whenever a motivator weight below changes.
        </p>
        {MOTIVATOR_LABELS.map(([key, label]) => (
          <Slider
            key={key}
            label={label}
            value={networkParams.motivator_weights[key]}
            min={0}
            max={2}
            step={0.1}
            onChange={setNetworkWeight(key)}
          />
        ))}
        <Slider
          label="Step (ft)"
          value={networkParams.step_ft}
          min={6}
          max={30}
          step={1}
          onChange={setNetworkField('step_ft')}
        />
        {networkResult && (
          <div className="font-mono-sm text-[11px] text-on-surface-variant space-y-1">
            <div>nodes: <span className="text-accent">{networkResult.node_count}</span></div>
            <div>
              edges: <span className="text-accent">
                {networkResult.network.length - (networkResult.kind_counts.lookout_point ?? 0)}
              </span>
            </div>
            <div>lookouts: <span className="text-accent">{networkResult.kind_counts.lookout_point ?? 0}</span></div>
            <div>attractors unconsumed: <span className="text-accent">{networkResult.attractors_unconsumed}</span></div>
          </div>
        )}
        <p className="font-mono-sm text-[11px] text-on-surface-variant pt-1">
          Carve a canyon along the network's primary trunk only (not every twig) -- deliberate, explicit
          action, unlike growth above: it reshapes the terrain, so it doesn't auto-run on every rebuild.
        </p>
        <button
          onClick={onCarveCanyon}
          disabled={carvingCanyon || !onCarveCanyon || !networkResult}
          className="w-full py-3 border border-accent text-accent font-mono-sm text-mono-sm font-bold uppercase tracking-widest hover:bg-accent hover:text-background transition-all active:scale-[0.98] disabled:opacity-50"
        >
          {carvingCanyon ? 'Carving...' : 'Carve Canyon Along Path'}
        </button>
      </div>

      <div className="p-container mt-auto">
        <button
          onClick={onRebuild}
          disabled={rebuilding}
          className="w-full py-3 bg-accent text-background font-mono-sm text-mono-sm font-bold uppercase tracking-widest hover:brightness-110 transition-all active:scale-[0.98] disabled:opacity-50"
        >
          {rebuilding ? 'REBUILDING...' : 'REBUILD'}
        </button>
      </div>
    </aside>
  );
}
