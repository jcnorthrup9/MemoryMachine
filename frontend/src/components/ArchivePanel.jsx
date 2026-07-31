import { useEffect, useState, useCallback } from 'react';
import { saveToArchive, listArchive, getArchivedBuild, deleteArchivedBuild } from '../api.js';

function formatSavedAt(iso) {
  if (!iso) return 'unknown time';
  try {
    return new Date(iso).toLocaleString();
  } catch {
    return iso;
  }
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
            className="flex-1 bg-surface-container-high border border-border px-3 py-2 font-mono-sm text-mono-sm text-primary placeholder:text-on-surface-variant/60"
          />
          <button
            onClick={handleSave}
            disabled={!canSave || saving}
            className="bg-accent text-background px-4 py-2 font-mono-sm text-mono-sm font-bold uppercase tracking-widest hover:brightness-110 transition-all active:scale-[0.98] disabled:opacity-50"
          >
            {saving ? 'Saving...' : 'Save Current Build'}
          </button>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto">
        {loadingList && (
          <div className="p-container font-mono-sm text-mono-sm text-on-surface-variant">loading archive...</div>
        )}
        {!loadingList && entries.length === 0 && (
          <div className="p-container font-mono-sm text-mono-sm text-on-surface-variant opacity-60">
            no archived builds yet -- save one above.
          </div>
        )}
        {entries.map((entry) => (
          <div
            key={entry.filename}
            className="px-container py-4 border-b border-border flex items-center justify-between gap-4"
          >
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
            <div className="flex gap-2 shrink-0">
              <button
                onClick={() => handleLoad(entry.filename)}
                className="bg-surface-container-high text-primary border border-border px-3 py-2 font-mono-sm text-mono-sm font-bold uppercase tracking-widest hover:brightness-110 transition-all active:scale-[0.98]"
              >
                Load
              </button>
              <button
                onClick={() => handleDelete(entry.filename, entry.label)}
                className="bg-surface-container-high text-error border border-border px-3 py-2 font-mono-sm text-mono-sm font-bold uppercase tracking-widest hover:brightness-110 transition-all active:scale-[0.98]"
              >
                Delete
              </button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
