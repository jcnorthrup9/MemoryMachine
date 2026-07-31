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
// AXO ("axonometric") is deliberately NOT exposed here (2026-07-24), even
// though logic/drawing_styles.py's render_lineweight_svg/_png/backend
// support view="axo" -- confirmed live that requesting it actually crashes
// the whole shared FastAPI process, not just returns the intended graceful
// "unavailable" message. Root cause: a real, pre-existing trimesh/rtree
// pathology (already documented in vector_export.py's own comments) in the
// ray-candidate search for axonometric_projection's hidden-line removal,
// triggered by this site's many touching/coplanar terrace boxes -- NOT a
// simple "mesh too big" problem (the real site mesh here is only ~33k
// faces), so a face-count guard can't reliably predict or prevent it. The
// Python-level `except MemoryError` in lineweight_layers() doesn't help
// either, since the actual failure mode observed was the OS killing the
// process outright before Python's own exception handling ever ran.
// Re-enable only once that call is isolated in a subprocess (so a crash
// there can't take the main server down with it) or the underlying
// trimesh issue is fixed -- don't just remove this comment and add "axo"
// back to the list below without one of those two things being true.
const DRAWING_VIEWS = [
  { key: 'plan', label: 'PLAN' },
  { key: 'section', label: 'SECTION' },
];

const CURRENT_PROJECT = '__current__';

// Same 4 named elevations vector_export.py's GARAGE_LEVEL_ELEVATIONS_FT
// already establishes -- only meaningful for view="plan" (a single fixed
// cut height can't show a meaningful plan once the design has excavated
// the whole site to varying depths; see
// drawing_styles.py::lineweight_layers's own docstring).
const LEVEL_NAMES = ['SURFACE', 'LEVEL 1', 'LEVEL 2', 'LEVEL 3 / METRO'];

const DEFAULT_DRAWING_PARAMS = { style: 'lineweight', view: 'plan', level: 'SURFACE', show_labels: true };

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
  const handleLevelSelect = (level) => updateDrawingParams({ level });
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
      <div className="absolute top-4 left-4 flex gap-4 z-10">
        <div className="bg-surface/80 backdrop-blur-sm border border-border flex flex-col">
          <span className="text-on-surface-variant text-[10px] font-mono-sm px-3 pt-2">STYLE</span>
          <div className="flex">
            {DRAWING_STYLES.map((s) => (
              <button
                key={s.key}
                onClick={() => handleStyleSelect(s.key)}
                className={`px-3 py-2 font-mono-sm text-mono-sm uppercase border-t border-border ${
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
          <div className="bg-surface/80 backdrop-blur-sm border border-border flex flex-col">
            <span className="text-on-surface-variant text-[10px] font-mono-sm px-3 pt-2">VIEW</span>
            <div className="flex">
              {DRAWING_VIEWS.map((v) => (
                <button
                  key={v.key}
                  onClick={() => handleViewSelect(v.key)}
                  className={`px-3 py-2 font-mono-sm text-mono-sm uppercase border-t border-border ${
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

        {isLineweight && drawingParams.view === 'plan' && (
          <div className="bg-surface/80 backdrop-blur-sm border border-border flex flex-col">
            <span className="text-on-surface-variant text-[10px] font-mono-sm px-3 pt-2">LEVEL</span>
            <select
              value={drawingParams.level}
              onChange={(e) => handleLevelSelect(e.target.value)}
              className="bg-transparent px-3 py-2 font-mono-sm text-mono-sm uppercase text-on-surface-variant border-t border-border focus:text-primary outline-none"
            >
              {LEVEL_NAMES.map((name) => (
                <option key={name} value={name}>{name}</option>
              ))}
            </select>
          </div>
        )}

        <div className="bg-surface/80 backdrop-blur-sm border border-border flex flex-col">
          <span className="text-on-surface-variant text-[10px] font-mono-sm px-3 pt-2">PROJECT</span>
          <select
            value={projectSource}
            onChange={(e) => handleProjectSelect(e.target.value)}
            className="bg-transparent px-3 py-2 font-mono-sm text-mono-sm uppercase text-on-surface-variant border-t border-border focus:text-primary outline-none"
          >
            <option value={CURRENT_PROJECT}>CURRENT (live)</option>
            {archivedEntries.map((entry) => (
              <option key={entry.filename} value={entry.filename}>
                {entry.label || entry.filename}
              </option>
            ))}
          </select>
        </div>

        <div className="bg-surface/80 backdrop-blur-sm border border-border flex flex-col">
          <span className="text-on-surface-variant text-[10px] font-mono-sm px-3 pt-2">LABELS</span>
          <div className="flex">
            {[
              { value: true, label: 'ON' },
              { value: false, label: 'OFF' },
            ].map((opt) => (
              <button
                key={String(opt.value)}
                onClick={() => handleLabelsToggle(opt.value)}
                className={`px-3 py-2 font-mono-sm text-mono-sm uppercase border-t border-border ${
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
          className="bg-surface/80 backdrop-blur-sm border border-border px-3 py-2 font-mono-sm text-mono-sm uppercase text-on-surface-variant hover:text-primary disabled:opacity-50 self-start"
        >
          {loading ? 'GENERATING...' : 'REFRESH'}
        </button>

        <button
          onClick={handleSave}
          disabled={saving || !svg}
          className="bg-surface/80 backdrop-blur-sm border border-border px-3 py-2 font-mono-sm text-mono-sm uppercase text-on-surface-variant hover:text-accent disabled:opacity-50 self-start"
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
