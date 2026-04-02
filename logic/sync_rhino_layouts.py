# -*- coding: utf-8 -*-
"""
sync_rhino_layouts.py
---------------------
Run inside Rhino 8 via:  Tools > Python Script > Run...  (or RunPythonScript command)

IMPORTANT: PrecedentDiagrams.3dm must be the currently active document when
this script is run.  The script reads the "Schouwburgplein" layout from that
file as the reference, then opens each ParkDiagrams target file in turn.

What it does:
  1. Reads the layer tree and the layout named "Schouwburgplein" from the
     currently open PrecedentDiagrams.3dm.
  2. Opens each TARGET file in turn.
  3. Adds any missing layers -- NEVER modifies geometry or existing layers.
  4. Adds ONE layout page if the file has none, copying paper size and detail
     proportions from the Schouwburgplein layout.  The detail fits to the
     file's own geometry.  Layout is named after the file (e.g. "GardensbytheBay").
  5. Saves each file, then reopens PrecedentDiagrams.3dm.

TARGET files (Villette and Pershing are intentionally excluded):
  GardensbytheBay, GrandParkLA, MaggieDaleyPark, ZaryadyePark
"""

import rhinoscriptsyntax as rs
import scriptcontext as sc
import Rhino
import Rhino.DocObjects as DO
import Rhino.Geometry as RG
import System
import os, time

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
PARK_DIR         = r"C:\Users\jcnor\OneDrive - SCI-Arc\2026_3GB_Spring\SP26-Studio\Rhino\ParkDiagrams"
REFERENCE_DOC    = r"C:\Users\jcnor\OneDrive - SCI-Arc\2026_3GB_Spring\SP26-Studio\Rhino\PrecedentDiagrams.3dm"
REFERENCE_LAYOUT = "Schouwburgplein"

TARGETS = [
    "GardensbytheBay.3dm",
    "GrandParkLA.3dm",
    "MaggieDaleyPark.3dm",
    "ZaryadyePark.3dm",
]

# ---------------------------------------------------------------------------
# File helpers
# ---------------------------------------------------------------------------

def open_file(path):
    Rhino.RhinoApp.RunScript('_-Open "{}" _Enter'.format(path), False)
    Rhino.RhinoApp.Wait()
    time.sleep(2.0)

def save_file():
    Rhino.RhinoApp.RunScript("_-Save _Enter", False)
    Rhino.RhinoApp.Wait()

# ---------------------------------------------------------------------------
# Layer helpers
# ---------------------------------------------------------------------------

def get_layer_tree(doc):
    layers = []
    for layer in doc.Layers:
        if layer.IsDeleted:
            continue
        parent_path = None
        if layer.ParentLayerId != System.Guid.Empty:
            pl = doc.Layers.FindId(layer.ParentLayerId)
            if pl is not None:
                parent_path = pl.FullPath
        # Resolve linetype name so it can be matched by name in the target
        # document (index-based matching breaks when linetype tables differ).
        lt_name = "Continuous"
        lt_idx  = layer.LinetypeIndex
        if 0 <= lt_idx < doc.Linetypes.Count:
            lt_name = doc.Linetypes[lt_idx].Name

        layers.append({
            "full_path":        layer.FullPath,
            "name":             layer.Name,
            "parent_path":      parent_path,
            "color":            layer.Color,
            "line_type_name":   lt_name,
            "print_width":      layer.PlotWeight,
            "print_color":      layer.PlotColor,
            "visible":          layer.IsVisible,
            "locked":           layer.IsLocked,
        })
    return layers


def ensure_layers(ref_layers, target_doc):
    added = 0
    for lyr in ref_layers:
        fp = lyr["full_path"]
        if target_doc.Layers.FindByFullPath(fp, -1) >= 0:
            continue

        new_layer            = DO.Layer()
        new_layer.Name       = lyr["name"]
        new_layer.Color      = lyr["color"]
        new_layer.PlotWeight = lyr["print_width"]
        new_layer.PlotColor  = lyr["print_color"]
        new_layer.IsVisible  = lyr["visible"]
        new_layer.IsLocked   = lyr["locked"]

        if lyr["parent_path"]:
            pidx = target_doc.Layers.FindByFullPath(lyr["parent_path"], -1)
            if pidx >= 0:
                new_layer.ParentLayerId = target_doc.Layers[pidx].Id

        # Match linetype by name so index differences between files don't matter.
        lt_name = lyr.get("line_type_name", "Continuous")
        lt_idx  = target_doc.Linetypes.Find(lt_name, True)
        if lt_idx >= 0:
            new_layer.LinetypeIndex = lt_idx
        # If the linetype doesn't exist in the target yet, leave it as Continuous
        # (Rhino will use the default).  A future improvement could copy the
        # linetype definition itself across documents.

        if target_doc.Layers.Add(new_layer) >= 0:
            added += 1
        else:
            print("  [WARN] Could not add layer: {}".format(fp))
    return added

# ---------------------------------------------------------------------------
# Layout helpers
# ---------------------------------------------------------------------------

def get_named_layout_info(doc, layout_name):
    """
    Find a layout by name in doc and return its paper size.
    Returns None if the layout is not found.
    NOTE: We intentionally do NOT copy detail-view rectangles from the
    reference.  GetBoundingBox on a DetailViewObject can return model-space
    coordinates instead of paper-space mm, yielding invisible or zero-size
    detail views in the target file.  A full-page detail is always created
    instead (see add_layout).
    """
    page_views = doc.Views.GetPageViews()
    if not page_views:
        print("[WARN] No layouts found in reference document.")
        return None

    target_pv = None
    for pv in page_views:
        if pv.MainViewport.Name.lower() == layout_name.lower():
            target_pv = pv
            break

    if target_pv is None:
        print("[WARN] Layout '{}' not found. Available layouts:".format(layout_name))
        for pv in page_views:
            print("         - {}".format(pv.MainViewport.Name))
        return None

    pw = target_pv.PageWidth
    ph = target_pv.PageHeight
    print("  Layout '{}': {:.1f} x {:.1f} mm".format(layout_name, pw, ph))
    return {"paper_width": pw, "paper_height": ph}


def add_layout(target_doc, layout_name, layout_info):
    """
    Ensure target_doc has one layout page named layout_name with a single
    full-page detail view set to a parallel top-down projection zoomed to
    the file's own geometry.

    Uses direct RhinoCommon APIs throughout -- no rhinoscriptsyntax wrappers.
    Returns True if anything was changed (layout or detail was created).
    """
    pw     = layout_info["paper_width"]
    ph     = layout_info["paper_height"]
    MARGIN = 8.0   # mm from each paper edge

    # ------------------------------------------------------------------
    # Step 1: Find or create the layout page
    # ------------------------------------------------------------------
    page_view = None
    for pv in target_doc.Views.GetPageViews():
        if pv.MainViewport.Name.lower() == layout_name.lower():
            page_view = pv
            break

    if page_view is None:
        print("  Creating new layout '{}' ({:.0f} x {:.0f} mm)...".format(
            layout_name, pw, ph))
        page_view = target_doc.Views.AddPageView(layout_name, pw, ph)
        if page_view is None:
            print("  [ERROR] AddPageView failed -- cannot continue.")
            return False
        print("  Layout page created.")
    else:
        print("  Layout '{}' already exists.".format(
            page_view.MainViewport.Name))

    # ------------------------------------------------------------------
    # Step 2: Check whether a detail view already exists
    # ------------------------------------------------------------------
    vp_id = page_view.MainViewport.Id
    existing_details = [
        obj for obj in target_doc.Objects
        if obj.ObjectType == DO.ObjectType.Detail
        and obj.Attributes.ViewportId == vp_id
    ]
    if existing_details:
        print("  Detail view already present ({} found) -- skipping.".format(
            len(existing_details)))
        return False

    # ------------------------------------------------------------------
    # Step 3: Add a full-page detail view (Point2d is the correct overload)
    # ------------------------------------------------------------------
    print("  Adding detail view...")
    pt0 = RG.Point2d(MARGIN,      MARGIN)
    pt1 = RG.Point2d(pw - MARGIN, ph - MARGIN)
    det = page_view.AddDetailView(
        pt0, pt1,
        Rhino.Display.DefinedViewportProjection.Top,
    )
    if det is None:
        print("  [ERROR] AddDetailView returned None -- detail not created.")
        return False
    print("  Detail view created (id={}).".format(det.Id))

    # ------------------------------------------------------------------
    # Step 4: Configure the detail viewport camera and zoom to extents
    # ------------------------------------------------------------------
    print("  Setting camera and zooming to extents...")
    det.IsActiveInPageView = True

    vp = det.Viewport

    # Parallel projection (not perspective)
    vp.ChangeToParallelProjection(True)

    # Top-down camera: looking along -Z, Y is up
    vp.SetCameraDirection(RG.Vector3d(0.0, 0.0, -1.0), False)
    vp.CameraUp = RG.Vector3d(0.0, 1.0, 0.0)

    # Compute bounding box of all non-deleted geometry in the document
    bbox = RG.BoundingBox.Empty
    for obj in target_doc.Objects:
        if obj.IsDeleted:
            continue
        try:
            b = obj.Geometry.GetBoundingBox(True)
            if b.IsValid:
                bbox = RG.BoundingBox.Union(bbox, b)
        except Exception:
            pass

    if bbox.IsValid:
        vp.ZoomBoundingBox(bbox)
        print("  Zoomed to geometry bounding box {}.".format(bbox))
    else:
        # No geometry -- fall back to the full paper area in model units
        vp.ZoomExtents()
        print("  No geometry found -- called ZoomExtents().")

    det.IsActiveInPageView = False

    target_doc.Views.Redraw()
    print("  Layout complete.")
    return True

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("=" * 60)
    print("sync_rhino_layouts")
    print("Reference : PrecedentDiagrams.3dm (currently open)")
    print("Layout    : {}".format(REFERENCE_LAYOUT))
    print("=" * 60)

    # Confirm the right doc is open
    current_name = sc.doc.Name or ""
    if "PrecedentDiagrams" not in current_name:
        print("\n[ERROR] PrecedentDiagrams.3dm is not the active document.")
        print("        Active document: '{}'".format(current_name))
        print("        Please open PrecedentDiagrams.3dm and run again.")
        return

    # -- 1. Read reference -------------------------------------------------
    print("\nReading layers and layout from reference...")
    ref_layers = get_layer_tree(sc.doc)
    ref_layout = get_named_layout_info(sc.doc, REFERENCE_LAYOUT)

    print("\nReference layers ({} total):".format(len(ref_layers)))
    for lyr in ref_layers:
        indent = "    " if lyr["parent_path"] else "  "
        print("{}{}".format(indent, lyr["full_path"]))

    if not ref_layout:
        print("\n[ERROR] Cannot continue -- layout '{}' not found.".format(REFERENCE_LAYOUT))
        return

    # -- 2. Process each target --------------------------------------------
    results = []
    for filename in TARGETS:
        fpath    = os.path.join(PARK_DIR, filename)
        sitename = os.path.splitext(filename)[0]

        if not os.path.exists(fpath):
            print("\n[SKIP] File not found: {}".format(fpath))
            results.append((sitename, "FILE_NOT_FOUND"))
            continue

        print("\n[{}] Opening...".format(sitename))
        open_file(fpath)

        layers_added = ensure_layers(ref_layers, sc.doc)

        ok = add_layout(sc.doc, sitename, ref_layout)
        layout_status = "added" if ok else "already existed"

        save_file()

        msg = "Layers +{}  |  Layout: {}".format(layers_added, layout_status)
        print("  -> {}".format(msg))
        results.append((sitename, msg))

    # -- 3. Reopen PrecedentDiagrams.3dm -----------------------------------
    print("\nReopening PrecedentDiagrams.3dm...")
    open_file(REFERENCE_DOC)

    # -- 4. Summary --------------------------------------------------------
    print("\n" + "=" * 60)
    print("DONE -- Summary")
    print("=" * 60)
    for name, msg in results:
        print("  {:30s}  {}".format(name, msg))


main()
