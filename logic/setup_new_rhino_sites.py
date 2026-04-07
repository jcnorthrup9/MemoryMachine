# -*- coding: utf-8 -*-
"""
setup_new_rhino_sites.py
------------------------
Run inside Rhino 8 via: Tools > Python Script > Run...

IMPORTANT: PrecedentDiagrams.3dm must be the currently active document.

Creates new .3dm files for four sites that don't yet have Rhino files:
  - The High Line
  - Federation Square
  - Pioneer Courthouse Square
  - Superkilen

For each site:
  1. Reads the full layer tree + Schouwburgplein layout spec from the
     open PrecedentDiagrams.3dm reference document.
  2. Creates a new Rhino document set to Feet.
  3. Computes the real-world footprint of the satellite image from its
     latitude and zoom level, then inserts it as a PictureFrame at the
     world origin (0,0,0) = bottom-left corner of the image.
  4. Copies the full layer system from PrecedentDiagrams.3dm (same as
     sync_rhino_layouts.py, preserving colours, linetypes, and weights).
  5. Adds a layout page matching the Schouwburgplein paper size with a
     single full-page detail view zoomed to the image geometry.
  6. Saves as <stem>.3dm into the ParkDiagrams folder, then reopens
     PrecedentDiagrams.3dm so the reference doc is always the active one.

Scale formula:
  meters_per_pixel = 156543.03392 * cos(lat) / 2^zoom
  (standard Web Mercator / Google Maps tile formula for a 256-px tile base)
  Image is 1100 x 660 px.  Output units are feet (x 3.28084).
"""

import rhinoscriptsyntax as rs
import scriptcontext as sc
import Rhino
import Rhino.DocObjects as DO
import Rhino.Geometry as RG
import System
import os
import time
import math

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
BASE_DIR      = r"C:\Users\jcnor\MemoryMachine"
SATELLITE_DIR = os.path.join(BASE_DIR, "assets", "precedents")
PARK_DIR      = r"C:\Users\jcnor\OneDrive - SCI-Arc\2026_3GB_Spring\SP26-Studio\Rhino\ParkDiagrams"
REFERENCE_DOC    = r"C:\Users\jcnor\OneDrive - SCI-Arc\2026_3GB_Spring\SP26-Studio\Rhino\PrecedentDiagrams.3dm"
REFERENCE_LAYOUT = "Schouwburgplein"

IMG_W_PX       = 1100
IMG_H_PX       = 660
FEET_PER_METER = 3.28084

NEW_SITES = [
    {
        "stem": "TheHighLine",
        "name": "The High Line",
        "slug": "the_high_line",
        "lat":  40.7475,
        "zoom": 18.0,
    },
    {
        "stem": "FederationSquare",
        "name": "Federation Square",
        "slug": "federation_square",
        "lat":  -37.8179,
        "zoom": 18.5,
    },
    {
        "stem": "PioneerCourthouseSquare",
        "name": "Pioneer Courthouse Square",
        "slug": "pioneer_courthouse_square",
        "lat":  45.5191,
        "zoom": 19.0,
    },
    {
        "stem": "Superkilen",
        "name": "Superkilen",
        "slug": "superkilen",
        "lat":  55.6964,
        "zoom": 16.5,
    },
]

# ---------------------------------------------------------------------------
# Scale helper
# ---------------------------------------------------------------------------

def calc_image_size_ft(lat, zoom):
    """
    Return (width_ft, height_ft) for the satellite image at the given
    latitude and zoom level using the Web Mercator tile formula.
    """
    meters_per_px = (156543.03392 * math.cos(math.radians(lat))) / (2.0 ** zoom)
    width_ft  = IMG_W_PX * meters_per_px * FEET_PER_METER
    height_ft = IMG_H_PX * meters_per_px * FEET_PER_METER
    return width_ft, height_ft


# ---------------------------------------------------------------------------
# File helpers
# ---------------------------------------------------------------------------

def open_file(path):
    Rhino.RhinoApp.RunScript('_-Open "{}" _Enter'.format(path), False)
    Rhino.RhinoApp.Wait()
    time.sleep(2.0)


def new_file():
    """Open a blank new document (no template)."""
    Rhino.RhinoApp.RunScript("_-New _None _Enter", False)
    Rhino.RhinoApp.Wait()
    time.sleep(1.5)


def save_as(path):
    safe = path.replace("\\", "/")
    Rhino.RhinoApp.RunScript('_-SaveAs "{}" _Enter'.format(safe), False)
    Rhino.RhinoApp.Wait()
    time.sleep(1.5)


# ---------------------------------------------------------------------------
# Layer helpers  (identical logic to sync_rhino_layouts.py)
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
        lt_name = "Continuous"
        lt_idx  = layer.LinetypeIndex
        if 0 <= lt_idx < doc.Linetypes.Count:
            lt_name = doc.Linetypes[lt_idx].Name
        layers.append({
            "full_path":      layer.FullPath,
            "name":           layer.Name,
            "parent_path":    parent_path,
            "color":          layer.Color,
            "line_type_name": lt_name,
            "print_width":    layer.PlotWeight,
            "print_color":    layer.PlotColor,
            "visible":        layer.IsVisible,
            "locked":         layer.IsLocked,
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
        lt_name = lyr.get("line_type_name", "Continuous")
        lt_idx  = target_doc.Linetypes.Find(lt_name, True)
        if lt_idx >= 0:
            new_layer.LinetypeIndex = lt_idx
        if target_doc.Layers.Add(new_layer) >= 0:
            added += 1
        else:
            print("  [WARN] Could not add layer: {}".format(fp))
    return added


# ---------------------------------------------------------------------------
# Layout helpers  (identical logic to sync_rhino_layouts.py)
# ---------------------------------------------------------------------------

def get_named_layout_info(doc, layout_name):
    page_views = doc.Views.GetPageViews()
    if not page_views:
        return None
    for pv in page_views:
        if pv.MainViewport.Name.lower() == layout_name.lower():
            return {"paper_width": pv.PageWidth, "paper_height": pv.PageHeight}
    print("[WARN] Layout '{}' not found in reference.".format(layout_name))
    return None


def add_layout(target_doc, layout_name, layout_info):
    pw, ph = layout_info["paper_width"], layout_info["paper_height"]
    MARGIN = 8.0

    # Find or create layout page
    page_view = None
    for pv in target_doc.Views.GetPageViews():
        if pv.MainViewport.Name.lower() == layout_name.lower():
            page_view = pv
            break

    if page_view is None:
        page_view = target_doc.Views.AddPageView(layout_name, pw, ph)
        if page_view is None:
            print("  [ERROR] AddPageView failed.")
            return False

    # Skip if a detail already exists
    vp_id = page_view.MainViewport.Id
    existing = [o for o in target_doc.Objects
                if o.ObjectType == DO.ObjectType.Detail
                and o.Attributes.ViewportId == vp_id]
    if existing:
        print("  Detail already present -- skipping.")
        return False

    # Add full-page detail view
    pt0 = RG.Point2d(MARGIN,      MARGIN)
    pt1 = RG.Point2d(pw - MARGIN, ph - MARGIN)
    det = page_view.AddDetailView(pt0, pt1,
                                  Rhino.Display.DefinedViewportProjection.Top)
    if det is None:
        print("  [ERROR] AddDetailView returned None.")
        return False

    # Configure camera
    det.IsActiveInPageView = True
    vp = det.Viewport
    vp.ChangeToParallelProjection(True)
    vp.SetCameraDirection(RG.Vector3d(0.0, 0.0, -1.0), False)
    vp.CameraUp = RG.Vector3d(0.0, 1.0, 0.0)

    # Zoom to geometry
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
        print("  Zoomed to geometry: {}".format(bbox))
    else:
        vp.ZoomExtents()
        print("  No geometry -- ZoomExtents() fallback.")

    det.IsActiveInPageView = False
    target_doc.Views.Redraw()
    return True


# ---------------------------------------------------------------------------
# Picture frame insertion
# ---------------------------------------------------------------------------

def insert_picture_frame(doc, img_path, width_ft, height_ft):
    """
    Insert the satellite image as a PictureFrame at the world origin.
    Plane.WorldXY places the image with its bottom-left corner at (0,0,0),
    extending in +X (width) and +Y (height) -- matching the DIAGRAM_RULES
    convention that (0,0,0) is the bottom-left of the drawing surface.
    """
    plane  = RG.Plane.WorldXY
    obj_id = doc.Objects.AddPictureFrame(plane, img_path,
                                          width_ft, height_ft,
                                          False,    # selfIllumination
                                          False)    # embed
    if obj_id == System.Guid.Empty:
        print("  [ERROR] AddPictureFrame returned empty GUID for: {}".format(img_path))
        return False

    # Place the picture frame on the referenceImages layer
    ref_idx = doc.Layers.FindByFullPath("referenceImages", -1)
    if ref_idx >= 0:
        obj  = doc.Objects.Find(obj_id)
        if obj is not None:
            attr = obj.Attributes.Duplicate()
            attr.LayerIndex = ref_idx
            doc.Objects.ModifyAttributes(obj, attr, True)

    print("  PictureFrame inserted: {:.1f} x {:.1f} ft".format(width_ft, height_ft))
    return True


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("=" * 60)
    print("setup_new_rhino_sites.py")
    print("Reference : PrecedentDiagrams.3dm (must be active)")
    print("=" * 60)

    # Confirm correct reference doc is open
    current_name = sc.doc.Name or ""
    if "PrecedentDiagrams" not in current_name:
        print("\n[ERROR] PrecedentDiagrams.3dm is not the active document.")
        print("        Active document: '{}'".format(current_name))
        print("        Open PrecedentDiagrams.3dm and run this script again.")
        return

    # -- 1. Read reference -------------------------------------------------
    print("\nReading layer tree and layout from reference...")
    ref_layers = get_layer_tree(sc.doc)
    ref_layout = get_named_layout_info(sc.doc, REFERENCE_LAYOUT)

    print("  {} layers read.".format(len(ref_layers)))
    if not ref_layout:
        print("[ERROR] Cannot continue -- reference layout not found.")
        return
    print("  Layout '{}': {:.0f} x {:.0f} mm".format(
        REFERENCE_LAYOUT, ref_layout["paper_width"], ref_layout["paper_height"]))

    if not os.path.isdir(PARK_DIR):
        print("[ERROR] ParkDiagrams folder not found:\n  {}".format(PARK_DIR))
        return

    # -- 2. Process each site ---------------------------------------------
    results = []
    for site in NEW_SITES:
        out_path = os.path.join(PARK_DIR, "{}.3dm".format(site["stem"]))
        img_path = os.path.join(SATELLITE_DIR, "{}_satellite.jpg".format(site["slug"]))

        print("\n[{}]".format(site["name"]))

        if not os.path.exists(img_path):
            print("  [SKIP] Satellite image not found: {}".format(img_path))
            results.append((site["stem"], "SKIP -- satellite image missing"))
            continue

        if os.path.exists(out_path):
            print("  [SKIP] .3dm already exists: {}".format(out_path))
            results.append((site["stem"], "SKIP -- file already exists"))
            continue

        # ── New document ──────────────────────────────────────────────────
        print("  Creating new document...")
        new_file()

        # Set document units to Feet
        Rhino.RhinoApp.RunScript(
            "_-DocumentProperties _Units _UnitSystem _Feet _Enter _Enter", False)
        Rhino.RhinoApp.Wait()

        # ── Satellite image ───────────────────────────────────────────────
        width_ft, height_ft = calc_image_size_ft(site["lat"], site["zoom"])
        print("  Scale: lat={:+.4f}  zoom={}  =>  {:.1f} x {:.1f} ft".format(
            site["lat"], site["zoom"], width_ft, height_ft))
        ok_img = insert_picture_frame(sc.doc, img_path, width_ft, height_ft)

        # ── Layers ────────────────────────────────────────────────────────
        n_added = ensure_layers(ref_layers, sc.doc)
        print("  Layers added: {}".format(n_added))

        # ── Layout ────────────────────────────────────────────────────────
        layout_ok = add_layout(sc.doc, site["stem"], ref_layout)
        print("  Layout: {}".format("created" if layout_ok else "already existed"))

        sc.doc.Views.Redraw()

        # ── Save ──────────────────────────────────────────────────────────
        print("  Saving to: {}".format(out_path))
        save_as(out_path)

        status = "OK  img:{}  layers:+{}  layout:{}".format(
            "yes" if ok_img else "FAIL",
            n_added,
            "created" if layout_ok else "exists",
        )
        results.append((site["stem"], status))

    # -- 3. Reopen reference -----------------------------------------------
    print("\nReopening PrecedentDiagrams.3dm...")
    open_file(REFERENCE_DOC)

    # -- 4. Summary --------------------------------------------------------
    print("\n" + "=" * 60)
    print("DONE")
    print("=" * 60)
    for name, msg in results:
        print("  {:30s}  {}".format(name, msg))


main()
