import { useEffect, useState, useCallback, useRef } from 'react';
import { saveToArchive, listArchive, getArchivedBuild, deleteArchivedBuild, spatializePreview } from '../api.js';
import { drawDiagramPreview } from '../diagramGridPreview.js';

function formatSavedAt(iso) {
  if (!iso) return 'unknown time';
  try {
    return new Date(iso).toLocaleString();
  } catch {
    return iso;
  }
}

// Card thumbnail of the SPATIALIZE diagram that produced this build, if any
// -- listArchive() now carries each entry's spatial_seed (small: a handful
// of stamp entries, see list_archived_builds()'s docstring) alongside its
// other lightweight summary fields, so this resolves it to grids the same
// way Recent2DGenerationsPanel.jsx does for a live generation record,
// just from the seed directly rather than a filename lookup. Builds
// produced by painting directly (no SPATIALIZE diagram, the common case
// today) have an empty spatial_seed and get a plain placeholder instead --
// there's no diagram to show, painted masks are live server-side state
// never captured in the snapshot (see App.jsx's buildSnapshot comment).
function ArchiveThumbnail({ spatialSeed }) {
  const canvasRef = useRef(null);
  const [grids, setGrids] = useState(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    if (!spatialSeed?.length) return;
    let cancelled = false;
    spatializePreview(spatialSeed)
      .then((result) => { if (!cancelled) setGrids(result.grids); })
      .catch(() => { if (!cancelled) setFailed(true); });
    return () => { cancelled = true; };
  }, [spatialSeed]);

  useEffect(() => {
    drawDiagramPreview(canvasRef.current, grids);
  }, [grids]);

  if (!spatialSeed?.length || failed) {
    return (
      <div className="h-32 rounded bg-surface-container-low border border-dashed border-border flex items-center justify-center">
        <span className="font-mono-label text-[10px] text-on-surface-variant/60 uppercase">
          {failed ? 'preview failed' : 'no diagram (painted)'}
        </span>
      </div>
    );
  }

  return (
    <div className="h-32 rounded bg-surface-container-low border border-border overflow-hidden">
      {!grids && (
        <div className="h-full flex items-center justify-center">
          <span className="font-mono-label text-[10px] text-on-surface-variant/60 uppercase">loading...</span>
        </div>
      )}
      <canvas ref={canvasRef} className={`w-full h-full object-contain ${grids ? '' : 'hidden'}`} />
    </div>
  );
}

// ARCHIVE tab: a real gallery for build iterations, server-persisted
// (outputs/pershing_archive/ via logic/pershing_api.py's save/list/get/delete
// endpoints). The RECONSTRUCT toolbar's "Save Build" button writes into the
// same folder via the same saveToArchive() call, just without a label
// prompt -- so a build saved from either place shows up here, and loads the
// same way through App.jsx's restoreSnapshot().
export default function ArchivePanel({ getSnapshot, onRestoreSnapshot, canSave, log }) {
  const [entries, setEntries] = useState([]);
  const [loadingList, setLoadingList] = useState(true);
  const [label, setLabel] = useState('');
  const [saving, setSaving] = useState(false);

  const refresh = useCallback(() => {
    setLoadingList(true);
    listArchive()
      .then(setEntries)
      .catch((err) => log(String(err), 'error'))
      .finally(() => setLoadingList(false));
  }, [log]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const handleSave = async () => {
    const snapshot = getSnapshot();
    if (!snapshot) return;
    setSaving(true);
    try {
      const result = await saveToArchive(snapshot, label);
      log(`archived: ${result.label || result.filename}`);
      setLabel('');
      refresh();
    } catch (err) {
      log(String(err), 'error');
    } finally {
      setSaving(false);
    }
  };

  const handleLoad = async (filename) => {
    try {
      const snapshot = await getArchivedBuild(filename);
      onRestoreSnapshot(snapshot);
      log(`build loaded from archive: ${snapshot.label || filename}`);
    } catch (err) {
      log(String(err), 'error');
    }
  };

  const handleDelete = async (filename, entryLabel) => {
    if (!window.confirm(`Delete archived build "${entryLabel || filename}"? This can't be undone.`)) return;
    try {
      await deleteArchivedBuild(filename);
      log(`archived build deleted: ${entryLabel || filename}`);
      refresh();
    } catch (err) {
      log(String(err), 'error');
    }
  };

  return (
    <div className="flex-1 flex flex-col overflow-hidden">
      <div className="p-container border-b border-border space-y-4">
        <h3 className="font-headline-md text-headline-md text-primary">ARCHIVE</h3>
        <p className="font-mono-sm text-mono-sm text-on-surface-variant">
          Save the current build iteration, or recall a previously saved one. Recalling restores the exact
          on-screen state (geometry, network, program placement) as it was when saved -- it does not re-run
          generation, so it can't drift even if painted masks have since changed.
        </p>
        <div className="flex gap-3 items-center">
          <input
            type="text"
            value={label}
            onChange={(e) => setLabel(e.target.value)}
            placeholder="Label this build (optional)"
            className="flex-1 bg-surface-container-high border border-border px-3 py-2 font-mono-sm text-mono-sm text-primary placeholder:text-on-surface-variant/60 rounded"
          />
          <button
            onClick={handleSave}
            disabled={!canSave || saving}
            className="bg-accent text-background px-4 py-2 font-mono-sm text-mono-sm font-bold uppercase tracking-widest rounded hover:brightness-110 transition-all active:scale-[0.98] disabled:opacity-50"
          >
            {saving ? 'Saving...' : 'Save Current Build'}
          </button>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto p-container">
        {loadingList && (
          <div className="font-mono-sm text-mono-sm text-on-surface-variant">loading archive...</div>
        )}
        {!loadingList && entries.length === 0 && (
          <div className="font-mono-sm text-mono-sm text-on-surface-variant opacity-60">
            no archived builds yet -- save one above.
          </div>
        )}
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-card-gap">
          {entries.map((entry) => (
            <div
              key={entry.filename}
              className="bg-surface border border-border rounded-lg p-5 hover:shadow-lg transition-all flex flex-col gap-3"
            >
              <ArchiveThumbnail spatialSeed={entry.spatial_seed} />
              <div className="flex flex-col gap-1 min-w-0">
                <span className="font-mono-sm text-mono-sm font-bold text-primary truncate">
                  {entry.label || '(untitled)'}
                </span>
                <span className="font-mono-label text-[10px] text-on-surface-variant">
                  {formatSavedAt(entry.saved_at)}
                </span>
                <span className="font-mono-label text-[10px] text-on-surface-variant">
                  {entry.material_mode ?? '?'} &middot; {entry.instance_count ?? 0} instances &middot;{' '}
                  {entry.slab_harvest_tons != null ? `${entry.slab_harvest_tons.toFixed(0)}t slab` : 'no slab data'}
                  {entry.program_zone_count ? ` · ${entry.program_zone_count} program zones` : ''}
                </span>
                {/* Which commit produced this geometry (2026-07-28) -- see
                    logic/version.py. Absent on anything archived before that,
                    so this row simply doesn't render for older builds rather
                    than showing a misleading placeholder. The dirty marker
                    matters: it means uncommitted work was in the tree, so the
                    commit alone won't fully reproduce the build. */}
                {entry.commit_short && (
                  <span className="font-mono-label text-[10px] text-on-surface-variant opacity-60">
                    {entry.commit_short.slice(0, 7)}
                    {entry.commit_dirty ? ' (dirty)' : ''}
                  </span>
                )}
              </div>
              <div className="flex gap-2 mt-auto">
                <button
                  onClick={() => handleLoad(entry.filename)}
                  className="flex-1 bg-surface-container-high text-primary border border-border px-3 py-2 font-mono-sm text-mono-sm font-bold uppercase tracking-widest rounded hover:brightness-110 transition-all active:scale-[0.98]"
                >
                  Load
                </button>
                <button
                  onClick={() => handleDelete(entry.filename, entry.label)}
                  className="bg-surface-container-high text-error border border-border px-3 py-2 font-mono-sm text-mono-sm font-bold uppercase tracking-widest rounded hover:brightness-110 transition-all active:scale-[0.98]"
                >
                  Delete
                </button>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
