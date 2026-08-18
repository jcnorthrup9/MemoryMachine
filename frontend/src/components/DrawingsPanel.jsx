import { useEffect, useState, useCallback } from 'react';
import { generateDrawings, saveDrawing, listArchive, getArchivedBuild } from '../api';

// Mirrors Viewport.jsx's SHADING bar exactly (bg-surface/80 backdrop-blur
// chip, caps label, button row with the same active/inactive ternary) --
// see Viewport.jsx's SHADING_MODES bar for the pattern this was copied from.
// DIAGRAM (abstract stacked program bands) moved to DIAGNOSTICS' "Program
// Distribution" section (2026-07-25) -- native bars matching that tab's own
// formatting instead of a separate style toggle here.
const DRAWING_STYLES = [
  { key: 'lineweight', label: 'LINEWEIGHT' },
  { key: 'color', label: 'COLOR' },
];

// Only style="lineweight" has real 3D mesh geometry behind it (COLOR is
// flat categorized site data, DIAGRAM is a fully abstract program-band
// chart) -- VIEW/LEVEL only apply there.
//
// AXO ("axonometric") was hidden here from 2026-07-24 to 2026-08-12 after
// its hidden-line-removal pass (axonometric_projection() in
// vector_export.py) was confirmed to crash the whole shared FastAPI
// process outright (an OS-level kill under memory pressure, not a
// catchable Python exception) on a real, pre-existing trimesh/rtree
// ray-candidate-search pathology. Root-caused and fixed 2026-08-12: (1)
// trimesh was falling back to its slow rtree-based ray intersector because
// the fast Embree backend wasn't installed -- `embreex` (requirements.txt)
// fixes that; (2) vector_export._batch_visible() now chunks its ray batch
// with a bounded-memory, fail-open fallback regardless of which backend is
// active, so a still-pathological case degrades (partial hidden-line
// removal) instead of crashing.
const DRAWING_VIEWS = [
  { key: 'plan', label: 'PLAN' },
  { key: 'section', label: 'SECTION' },
  { key: 'axo', label: 'AXO' },
];

const CURRENT_PROJECT = '__current__';

// 2026-08-03: PLAN is now a whole-site flattened aerial projection (see
// drawing_styles.py::lineweight_layers), not a single-elevation cut, so
// there's no LEVEL to pick anymore -- the backend's `level` field keeps its
// own "SURFACE" default and is simply unused for view="plan".
const DEFAULT_DRAWING_PARAMS = { style: 'color', view: 'plan', show_labels: false };

export default function DrawingsPanel({ params, log }) {
  const [drawingParams, setDrawingParams] = useState(DEFAULT_DRAWING_PARAMS);
  const [svg, setSvg] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [saving, setSaving] = useState(false);

  // Which project's params to draw from -- CURRENT_PROJECT (the live "in
  // view" site) or an archived build's filename (see ArchivePanel.jsx --
  // same server-persisted outputs/pershing_archive/ store, reused here
  // rather than inventing a second "saved drawings" concept).
  const [projectSource, setProjectSource] = useState(CURRENT_PROJECT);
  const [archivedEntries, setArchivedEntries] = useState([]);
  const [archivedParams, setArchivedParams] = useState(null);

  useEffect(() => {
    listArchive()
      .then(setArchivedEntries)
      .catch((err) => log?.(`Drawings: archive list failed: ${err.message}`, 'error'));
  }, [log]);

  const activeParams = projectSource === CURRENT_PROJECT ? params : archivedParams;

  const generate = useCallback(
    async (rebuildParams, nextDrawingParams) => {
      if (!rebuildParams) return;
      setLoading(true);
      setError(null);
      try {
        const result = await generateDrawings(rebuildParams, nextDrawingParams);
        setSvg(result.svg);
      } catch (err) {
        setError(err.message);
        log?.(`Drawings generation failed: ${err.message}`, 'error');
      } finally {
        setLoading(false);
      }
    },
    [log]
  );

  // Auto-generates once when the tab is first opened (this component only
  // mounts while the DRAWINGS tab is active), always against whatever
  // `params` the frontend currently holds -- "current in view site" by
  // construction, same contract generate_canopy/grow_network already use.
  useEffect(() => {
    generate(params, drawingParams);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const updateDrawingParams = (patch) => {
    const next = { ...drawingParams, ...patch };
    setDrawingParams(next);
    generate(activeParams, next);
  };

  const handleStyleSelect = (style) => updateDrawingParams({ style });
  const handleViewSelect = (view) => updateDrawingParams({ view });
  const handleLabelsToggle = (show_labels) => updateDrawingParams({ show_labels });

  const handleProjectSelect = async (value) => {
    setProjectSource(value);
    if (value === CURRENT_PROJECT) {
      setArchivedParams(null);
      generate(params, drawingParams);
      return;
    }
    try {
      const snapshot = await getArchivedBuild(value);
      if (!snapshot.params) throw new Error('archived build has no saved params');
      setArchivedParams(snapshot.params);
      log?.(`Drawings: loaded project "${snapshot.label || value}"`);
      generate(snapshot.params, drawingParams);
    } catch (err) {
      setError(err.message);
      log?.(`Drawings: loading project failed: ${err.message}`, 'error');
    }
  };

  const handleSave = async () => {
    if (!activeParams) return;
    setSaving(true);
    try {
      const result = await saveDrawing(activeParams, drawingParams);
      log?.(`Drawings saved to ${result.dir}: ${result.files.join(', ')}`);
    } catch (err) {
      log?.(`Drawings save failed: ${err.message}`, 'error');
    } finally {
      setSaving(false);
    }
  };

  const isLineweight = drawingParams.style === 'lineweight';

  return (
    <div className="flex-1 flex flex-col overflow-hidden relative bg-background">
      <div className="absolute top-4 left-4 flex flex-wrap items-start gap-2 z-10">
        <div className="bg-surface/80 backdrop-blur-sm border border-border rounded-lg flex flex-col">
          <span className="text-on-surface-variant text-[8px] font-mono-sm px-2 pt-0.5">STYLE</span>
          <div className="flex">
            {DRAWING_STYLES.map((s) => (
              <button
                key={s.key}
                onClick={() => handleStyleSelect(s.key)}
                className={`px-2 py-0.5 font-mono-sm text-[9px] uppercase border-t border-border ${
                  drawingParams.style === s.key
                    ? 'text-accent bg-surface-container-high'
                    : 'text-on-surface-variant hover:text-primary'
                }`}
              >
                {s.label}
              </button>
            ))}
          </div>
        </div>

        {isLineweight && (
          <div className="bg-surface/80 backdrop-blur-sm border border-border rounded-lg flex flex-col">
            <span className="text-on-surface-variant text-[8px] font-mono-sm px-2 pt-0.5">VIEW</span>
            <div className="flex">
              {DRAWING_VIEWS.map((v) => (
                <button
                  key={v.key}
                  onClick={() => handleViewSelect(v.key)}
                  className={`px-2 py-0.5 font-mono-sm text-[9px] uppercase border-t border-border ${
                    drawingParams.view === v.key
                      ? 'text-accent bg-surface-container-high'
                      : 'text-on-surface-variant hover:text-primary'
                  }`}
                >
                  {v.label}
                </button>
              ))}
            </div>
          </div>
        )}

        <div className="bg-surface/80 backdrop-blur-sm border border-border rounded-lg flex flex-col">
          <span className="text-on-surface-variant text-[8px] font-mono-sm px-2 pt-0.5">PROJECT</span>
          <select
            value={projectSource}
            onChange={(e) => handleProjectSelect(e.target.value)}
            className="bg-transparent px-2 py-0.5 font-mono-sm text-[9px] uppercase text-on-surface-variant border-t border-border focus:text-primary outline-none"
          >
            <option value={CURRENT_PROJECT}>CURRENT (live)</option>
            {archivedEntries.map((entry) => (
              <option key={entry.filename} value={entry.filename}>
                {entry.label || entry.filename}
              </option>
            ))}
          </select>
        </div>

        <div className="bg-surface/80 backdrop-blur-sm border border-border rounded-lg flex flex-col">
          <span className="text-on-surface-variant text-[8px] font-mono-sm px-2 pt-0.5">LABELS</span>
          <div className="flex">
            {[
              { value: true, label: 'ON' },
              { value: false, label: 'OFF' },
            ].map((opt) => (
              <button
                key={String(opt.value)}
                onClick={() => handleLabelsToggle(opt.value)}
                className={`px-2 py-0.5 font-mono-sm text-[9px] uppercase border-t border-border ${
                  drawingParams.show_labels === opt.value
                    ? 'text-accent bg-surface-container-high'
                    : 'text-on-surface-variant hover:text-primary'
                }`}
              >
                {opt.label}
              </button>
            ))}
          </div>
        </div>

        <button
          onClick={() => generate(activeParams, drawingParams)}
          disabled={loading}
          className="bg-surface/80 backdrop-blur-sm border border-border px-2 py-1 font-mono-sm text-[9px] uppercase text-on-surface-variant hover:text-primary disabled:opacity-50 self-start rounded"
        >
          {loading ? 'GENERATING...' : 'REFRESH'}
        </button>

        <button
          onClick={handleSave}
          disabled={saving || !svg}
          className="bg-surface/80 backdrop-blur-sm border border-border px-2 py-1 font-mono-sm text-[9px] uppercase text-on-surface-variant hover:text-accent disabled:opacity-50 self-start rounded"
        >
          {saving ? 'SAVING...' : 'SAVE / EXPORT'}
        </button>
      </div>

      <div className="flex-1 overflow-auto flex items-center justify-center p-8">
        {error ? (
          <span className="font-mono-sm text-mono-sm text-red-400">{error}</span>
        ) : svg ? (
          <div
            // The raw SVG strings from vector_export.py/stylized_pattern_export.py/
            // drawing_styles.py only set viewBox, not width/height -- give the
            // child <svg> a definite size to scale into (otherwise it collapses
            // to its CSS-default 0/auto size inside this flex container).
            className="w-full h-full [&>svg]:w-full [&>svg]:h-full [&>svg]:object-contain"
            // eslint-disable-next-line react/no-danger
            dangerouslySetInnerHTML={{ __html: svg }}
          />
        ) : (
          <span className="font-mono-sm text-mono-sm text-on-surface-variant">
            {loading ? 'generating...' : 'no drawing yet'}
          </span>
        )}
      </div>
    </div>
  );
}
