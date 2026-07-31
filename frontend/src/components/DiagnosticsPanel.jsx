import PROGRAM_COLORS from '../programColors.json';

function Section({ title, children }) {
  return (
    <div className="p-container border-b border-border space-y-4">
      <h4 className="font-mono-label text-mono-label text-on-surface-variant uppercase tracking-widest rounded">
        {title}
      </h4>
      {children}
    </div>
  );
}

function StatRow({ label, value }) {
  return (
    <div className="flex justify-between font-mono-sm text-mono-sm">
      <span className="text-on-surface-variant uppercase">{label}</span>
      <span className="text-accent">{value}</span>
    </div>
  );
}

function Empty({ children }) {
  return <p className="font-mono-sm text-mono-sm text-on-surface-variant opacity-60">{children}</p>;
}

// Shared per-program colors (2026-07-28) -- this was a third hand-copied
// duplicate of the same map (Viewport.jsx and drawing_styles.py held the
// other two); all three now read programColors.json. Used by the Program
// Distribution bars below, which are the DRAWINGS page's former "DIAGRAM"
// style rendered natively in this tab instead.
const PROGRAM_COLOR = PROGRAM_COLORS.programs;
const PROGRAM_FALLBACK_COLOR = PROGRAM_COLORS.fallback;

// Bar width is proportional to claimed bay count (same "space claimed"
// meaning as drawing_styles.py's _diagram_rows band_width), not achieved_sf
// -- bay count is what's directly comparable across programs regardless of
// each program's own target/achieved sf scale.
function ProgramBar({ item, bayCount, maxBayCount, color }) {
  const pct = maxBayCount > 0 ? (bayCount / maxBayCount) * 100 : 0;
  return (
    <div className="flex items-center gap-2">
      <span className="font-mono-sm text-[10px] text-on-surface-variant w-40 truncate shrink-0">{item}</span>
      <div className="flex-1 h-2 bg-border/40">
        <div className="h-2" style={{ width: `${pct}%`, backgroundColor: color }} />
      </div>
      <span className="font-mono-sm text-[10px] text-accent w-10 text-right shrink-0">{bayCount}</span>
    </div>
  );
}

// DIAGNOSTICS tab: surfaces data already computed server-side (config,
// rebuild(), grow_network(), get_program_zones()) but previously only used
// as grounding context for the juror chat or not shown at all -- a
// dedicated read-only status/health dashboard, no new backend calls of its
// own.
export default function DiagnosticsPanel({ config, data, networkData, programZones }) {
  const kindCounts = data?.kind_counts ?? {};
  const totalInstances = Object.values(kindCounts).reduce((a, b) => a + b, 0);
  const networkKindCounts = networkData?.kind_counts ?? {};
  const zones = programZones?.zones ?? [];
  const placedZones = zones.filter((z) => z.bays.length > 0);
  const maxBays = Math.max(1, ...placedZones.map((z) => z.bays.length));

  return (
    <div className="flex-1 flex flex-col overflow-y-auto">
      <div className="p-container border-b border-border">
        <h3 className="font-headline-md text-headline-md text-primary">DIAGNOSTICS</h3>
      </div>

      <Section title="Site Configuration">
        {config ? (
          <>
            <StatRow label="Site Dimensions" value={`${config.site_width_ft.toFixed(0)} × ${config.site_length_ft.toFixed(0)} ft`} />
            <StatRow label="Voxel Grid" value={`${config.nx} × ${config.nz} @ ${config.voxel_ft}ft`} />
            <StatRow label="Structural Bays (X)" value={config.nx_bays} />
            <StatRow label="Column Height" value={`${config.column_height_ft} ft`} />
            <StatRow label="Amenity Deficit CSV" value={config.amenity_csv || 'none (using placeholder)'} />
            <StatRow label="Foot Traffic CSV" value={config.foot_traffic_csv || 'none (using placeholder)'} />
          </>
        ) : (
          <Empty>config not loaded yet.</Empty>
        )}
      </Section>

      <Section title="Last Rebuild">
        {data ? (
          <>
            <StatRow label="Total Instances" value={totalInstances} />
            <StatRow label="Voxel Count" value={data.voxels?.length ?? 0} />
            <StatRow label="Slab Material Harvested" value={`${data.slab_harvest_tons?.toFixed(0) ?? 0} tons`} />
            <StatRow label="Max Canyon Depth" value={`${data.max_canyon_depth_ft?.toFixed(1) ?? 0} ft`} />
            <StatRow label="Real Amenity Data Used" value={data.used_real_amenity_data ? 'yes' : 'no'} />
            <StatRow label="Real Foot Traffic Data Used" value={data.used_real_foot_traffic_data ? 'yes' : 'no'} />
            <div className="pt-2 space-y-1">
              <span className="font-mono-label text-[10px] text-on-surface-variant uppercase">Instance kinds</span>
              {Object.entries(kindCounts).sort((a, b) => b[1] - a[1]).map(([kind, count]) => (
                <div key={kind} className="flex justify-between font-mono-sm text-mono-sm">
                  <span className="text-on-surface-variant">{kind}</span>
                  <span className="text-primary">{count}</span>
                </div>
              ))}
            </div>
          </>
        ) : (
          <Empty>no rebuild has completed yet.</Empty>
        )}
      </Section>

      <Section title="Circulation Growth Network">
        {networkData ? (
          <>
            <StatRow label="Nodes" value={networkData.node_count} />
            <StatRow label="Attractors" value={networkData.attractor_count} />
            <StatRow label="Attractors Unconsumed" value={networkData.attractors_unconsumed} />
            {Object.entries(networkKindCounts).map(([kind, count]) => (
              <StatRow key={kind} label={kind} value={count} />
            ))}
          </>
        ) : (
          <Empty>network hasn't been grown yet -- use "Grow Network" in RECONSTRUCT.</Empty>
        )}
      </Section>

      <Section title="Program Placement">
        {zones.length > 0 ? (
          <>
            <StatRow label="Bay Size" value={`${programZones.bay_ft} ft`} />
            <StatRow label="Programs Placed" value={`${placedZones.length} / ${zones.length}`} />
            <div className="pt-2 space-y-2">
              {zones.map((z) => (
                <div key={z.program_item} className="flex justify-between font-mono-sm text-mono-sm gap-2">
                  <span className="text-on-surface-variant truncate">
                    {z.program_item} <span className="opacity-50">({z.need_level})</span>
                  </span>
                  <span className={z.fulfilled ? 'text-accent' : 'text-warning'}>
                    {z.achieved_sf.toFixed(0)} / {z.target_sf.toFixed(0)} sf{z.fulfilled ? '' : ' (partial)'}
                  </span>
                </div>
              ))}
            </div>
          </>
        ) : (
          <Empty>program zones not loaded yet.</Empty>
        )}
      </Section>

      <Section title="Program Distribution">
        {placedZones.length > 0 ? (
          <div className="space-y-2">
            {[...placedZones]
              .sort((a, b) => b.bays.length - a.bays.length)
              .map((z) => (
                <ProgramBar
                  key={z.program_item}
                  item={z.program_item}
                  bayCount={z.bays.length}
                  maxBayCount={maxBays}
                  color={PROGRAM_COLOR[z.program_item] || PROGRAM_FALLBACK_COLOR}
                />
              ))}
          </div>
        ) : (
          <Empty>program zones not loaded yet.</Empty>
        )}
      </Section>
    </div>
  );
}
