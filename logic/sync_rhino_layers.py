"""
sync_rhino_layers.py
--------------------
Run this inside Rhino 8 via:  Tools > Python Script > Run...  (or RunPythonScript command)

What it does:
  1. Opens Schouwburgplein.3dm to read the reference layer tree.
  2. Iterates every other .3dm file in the ParkDiagrams folder.
  3. Opens each file, adds any missing layers (preserving parent/child hierarchy
     and colors), then saves and closes.
  4. Reopens Schouwburgplein.3dm so you end up back where you started.

No geometry is touched — only the layer table is modified.
"""

import rhinoscriptsyntax as rs
import scriptcontext as sc
import Rhino
import System.Drawing

PARK_DIAGRAMS_DIR = r"C:\Users\jcnor\OneDrive - SCI-Arc\2026_3GB_Spring\SP26-Studio\Rhino\ParkDiagrams"
REFERENCE_FILE    = PARK_DIAGRAMS_DIR + r"\Schouwburgplein.3dm"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def open_file(path):
    """Open a .3dm file (replaces current document)."""
    # Use Rhino's Open command; the string must be quoted if it has spaces
    safe = '"{}"'.format(path)
    Rhino.RhinoApp.RunScript("_-Open {} _Enter".format(safe), False)
    Rhino.RhinoApp.Wait()


def save_file():
    """Save the current document in place."""
    Rhino.RhinoApp.RunScript("_-Save _Enter", False)
    Rhino.RhinoApp.Wait()


def get_layer_tree(doc=None):
    """
    Returns an ordered list of dicts describing every layer in the document:
        { 'full_path': 'Parent::Child', 'name': 'Child',
          'parent_path': 'Parent' or None,
          'color': System.Drawing.Color }
    Ordered so parents always come before their children.
    """
    if doc is None:
        doc = sc.doc
    layers = []
    for layer in doc.Layers:
        if layer.IsDeleted:
            continue
        full_path  = layer.FullPath          # e.g. "Streets::Primary"
        name       = layer.Name              # e.g. "Primary"
        parent_idx = layer.ParentLayerId
        parent_path = None
        if parent_idx != System.Guid.Empty:
            parent_layer = doc.Layers.FindId(parent_idx)
            if parent_layer is not None:
                parent_path = parent_layer.FullPath
        layers.append({
            'full_path':   full_path,
            'name':        name,
            'parent_path': parent_path,
            'color':       layer.Color,
        })
    return layers


def ensure_layers(reference_layers, target_doc=None):
    """
    Add any layers from reference_layers that are missing in target_doc.
    Returns a count of layers added.
    """
    if target_doc is None:
        target_doc = sc.doc
    added = 0
    for lyr in reference_layers:
        full_path = lyr['full_path']
        # Check if layer already exists by full path
        existing = target_doc.Layers.FindByFullPath(full_path, -1)
        if existing >= 0:
            continue  # already there

        new_layer = Rhino.DocObjects.Layer()
        new_layer.Name  = lyr['name']
        new_layer.Color = lyr['color']

        # Attach to parent if needed
        if lyr['parent_path']:
            parent_idx = target_doc.Layers.FindByFullPath(lyr['parent_path'], -1)
            if parent_idx >= 0:
                new_layer.ParentLayerId = target_doc.Layers[parent_idx].Id

        idx = target_doc.Layers.Add(new_layer)
        if idx >= 0:
            added += 1
        else:
            print("  [WARN] Could not add layer: {}".format(full_path))
    return added


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

import os

def main():
    print("=" * 60)
    print("sync_rhino_layers — starting")
    print("Reference: {}".format(REFERENCE_FILE))
    print("=" * 60)

    # ── 1. Open reference file and capture its layer tree ──────────────────
    open_file(REFERENCE_FILE)
    reference_layers = get_layer_tree(sc.doc)
    print("\nReference layers ({} total):".format(len(reference_layers)))
    for lyr in reference_layers:
        indent = "  " if lyr['parent_path'] else ""
        print("  {}{}".format(indent, lyr['full_path']))

    # ── 2. Collect all other .3dm files ────────────────────────────────────
    all_files = [
        os.path.join(PARK_DIAGRAMS_DIR, f)
        for f in os.listdir(PARK_DIAGRAMS_DIR)
        if f.lower().endswith('.3dm') and f != 'Schouwburgplein.3dm'
    ]

    if not all_files:
        print("\n[INFO] No other .3dm files found. Done.")
        return

    print("\nFiles to process ({} total):".format(len(all_files)))
    for f in all_files:
        print("  " + os.path.basename(f))

    # ── 3. Process each file ───────────────────────────────────────────────
    results = []
    for fpath in sorted(all_files):
        basename = os.path.basename(fpath)
        print("\n[{}] Opening...".format(basename))
        open_file(fpath)

        added = ensure_layers(reference_layers, sc.doc)
        if added:
            save_file()
            msg = "Added {} layer(s) — saved.".format(added)
        else:
            msg = "Already up to date — no changes."
        print("  -> {}".format(msg))
        results.append((basename, msg))

    # ── 4. Reopen reference so user ends where they started ─────────────────
    print("\nReopening Schouwburgplein.3dm...")
    open_file(REFERENCE_FILE)

    # ── 5. Summary ────────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("DONE — Summary")
    print("=" * 60)
    for name, msg in results:
        print("  {:40s}  {}".format(name, msg))
    print("\nAll files now share the Schouwburgplein layer structure.")


main()
