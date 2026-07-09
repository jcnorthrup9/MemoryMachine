import { useState } from 'react';

const NEW_BUILDING_DEFAULTS = { x_ft: 0, y_ft: 0, width_ft: 40, depth_ft: 30, height_ft: 20, setback_ft: 0 };

const PAINT_CATEGORIES = [
  { key: 'canyon', label: 'Canyon' },
  { key: 'hardscape', label: 'Hardscape' },
  { key: 'water_shade', label: 'Water/Shade' },
  { key: 'greenscape', label: 'Greenscape' },
  { key: 'amenity_resting', label: 'Amenity/Resting' },
];

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

export default function ParamPanel({
  config, params, onParamsChange, onPaint, onRebuild, slabHarvestTons, kindCounts, usedRealAmenityData,
  rebuilding, blenderBuild, onBuildInBlender, lineartEnabled, onLineartEnabledChange,
}) {
  const set = (key) => (value) => onParamsChange({ ...params, [key]: value });
  const blenderBusy = blenderBuild?.status === 'queued' || blenderBuild?.status === 'running';
  const [newBuilding, setNewBuilding] = useState(NEW_BUILDING_DEFAULTS);

  const addBuilding = () => {
    onParamsChange({ ...params, buildings: [...params.buildings, newBuilding] });
  };
  const removeBuilding = (i) => {
    onParamsChange({ ...params, buildings: params.buildings.filter((_, idx) => idx !== i) });
  };

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
          Building Massing
        </h4>
        <p className="font-mono-sm text-[11px] text-on-surface-variant">
          v1: single-box massing per footprint, user-parameterized (not read from real-world context
          data) -- swap for real building form later.
        </p>
        <div className="grid grid-cols-2 gap-2">
          {[
            ['x_ft', 'X (ft)'], ['y_ft', 'Y (ft)'],
            ['width_ft', 'Width (ft)'], ['depth_ft', 'Depth (ft)'],
            ['height_ft', 'Height (ft)'], ['setback_ft', 'Setback (ft)'],
          ].map(([key, label]) => (
            <label key={key} className="space-y-1 block">
              <span className="font-mono-sm text-[11px] text-on-surface-variant uppercase">{label}</span>
              <input
                type="number"
                value={newBuilding[key]}
                onChange={(e) => setNewBuilding({ ...newBuilding, [key]: parseFloat(e.target.value) || 0 })}
                className="w-full bg-background border border-border font-mono-sm text-mono-sm p-2 focus:ring-0 focus:border-accent text-on-surface outline-none"
              />
            </label>
          ))}
        </div>
        <button
          onClick={addBuilding}
          className="w-full py-2 border border-accent text-accent font-mono-sm text-mono-sm font-bold uppercase tracking-widest hover:bg-accent hover:text-background transition-all active:scale-[0.98]"
        >
          Add Building
        </button>
        {params.buildings.length > 0 && (
          <div className="space-y-1">
            {params.buildings.map((b, i) => (
              <div key={i} className="flex justify-between items-center font-mono-sm text-[11px] text-on-surface-variant">
                <span>
                  {b.width_ft}x{b.depth_ft}x{b.height_ft}ft @ ({b.x_ft}, {b.y_ft})
                </span>
                <button onClick={() => removeBuilding(i)} className="text-error hover:brightness-125 px-2">
                  remove
                </button>
              </div>
            ))}
          </div>
        )}
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
          Live Sketch (Paint on Photo)
        </h4>
        <div className="grid grid-cols-1 gap-2">
          {PAINT_CATEGORIES.map((c) => (
            <button
              key={c.key}
              onClick={() => onPaint?.(c.key)}
              className="px-4 py-2 border border-border text-on-surface-variant font-mono-sm text-mono-sm uppercase hover:border-accent hover:text-accent transition-colors"
            >
              Paint {c.label}
            </button>
          ))}
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
