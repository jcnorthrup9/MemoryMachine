# -*- coding: utf-8 -*-
"""
fix_layout_detail.py
--------------------
Run inside Rhino 8 via: Tools > Python Script > Run...

Open any ParkDiagrams .3dm file that is missing a detail view in its layout,
then run this script.  It will find every layout page, and for any that has
no detail view rectangle it will add one that fills the paper (8 mm margin),
set a parallel top-down projection, and zoom to the file's existing geometry.
"""

import scriptcontext as sc
import Rhino
import Rhino.DocObjects as DO
import Rhino.Geometry as RG

MARGIN = 8.0  # mm from each paper edge


def add_detail_to_layout(pv):
    """
    Add a full-page detail view to the given RhinoPageView using direct
    RhinoCommon APIs.  Sets a parallel top-down projection and zooms to
    the file's own geometry.  Returns True if a detail was added.
    """
    doc         = sc.doc
    layout_name = pv.MainViewport.Name
    pw          = pv.PageWidth
    ph          = pv.PageHeight

    print("  Paper size: {:.1f} x {:.1f} mm".format(pw, ph))
    print("  Adding detail view...")

    pt0 = RG.Point2d(MARGIN,      MARGIN)
    pt1 = RG.Point2d(pw - MARGIN, ph - MARGIN)
    det = pv.AddDetailView(
        pt0, pt1,
        Rhino.Display.DefinedViewportProjection.Top,
    )
    if det is None:
        print("  [ERROR] AddDetailView returned None.")
        return False

    print("  Detail view created (id={}).".format(det.Id))
    print("  Setting camera and zooming to extents...")

    det.IsActiveInPageView = True

    vp = det.Viewport
    vp.ChangeToParallelProjection(True)
    vp.SetCameraDirection(RG.Vector3d(0.0, 0.0, -1.0), False)
    vp.CameraUp = RG.Vector3d(0.0, 1.0, 0.0)

    # Compute bounding box of all geometry in the file
    bbox = RG.BoundingBox.Empty
    for obj in doc.Objects:
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
        print("  Zoomed to bounding box {}.".format(bbox))
    else:
        vp.ZoomExtents()
        print("  No geometry -- called ZoomExtents().")

    det.IsActiveInPageView = False
    doc.Views.Redraw()
    print("  [OK] Detail view ready.")
    return True


def fix_current_doc():
    doc  = sc.doc
    name = doc.Name or "(untitled)"
    print("=" * 60)
    print("fix_layout_detail")
    print("File: {}".format(name))
    print("=" * 60)

    page_views = doc.Views.GetPageViews()
    if not page_views:
        print("[INFO] No layout pages found in this file.")
        return

    fixed = 0
    for pv in page_views:
        layout_name = pv.MainViewport.Name
        print("\nLayout: '{}'".format(layout_name))

        existing = [
            obj for obj in doc.Objects
            if obj.ObjectType == DO.ObjectType.Detail
            and obj.Attributes.ViewportId == pv.MainViewport.Id
        ]

        if existing:
            print("  [SKIP] {} detail view(s) already present.".format(
                len(existing)))
            continue

        ok = add_detail_to_layout(pv)
        if ok:
            fixed += 1

    print("\n" + "=" * 60)
    if fixed:
        print("Fixed {} layout(s). Saving...".format(fixed))
        Rhino.RhinoApp.RunScript("_-Save _Enter", False)
        Rhino.RhinoApp.Wait()
        print("Saved.")
    else:
        print("Nothing changed.")
    print("=" * 60)


fix_current_doc()
