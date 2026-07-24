// 9-zone site split (3x3, 2026-07-24) -- shared by Viewport.jsx (the
// zone-toggle hover/select/isolate UI) and App.jsx (export-zone filtering)
// so the grid definition can never drift between what's drawn on screen and
// what actually gets exported.
const ZONE_COLS = 3;
const ZONE_ROWS = 3;

export function computeZones(siteWidthFt, siteLengthFt) {
  const colW = siteWidthFt / ZONE_COLS;
  const rowH = siteLengthFt / ZONE_ROWS;
  const zones = [];
  for (let row = 0; row < ZONE_ROWS; row++) {
    for (let col = 0; col < ZONE_COLS; col++) {
      const id = row * ZONE_COLS + col;
      zones.push({
        id,
        label: `Zone ${id + 1}`,
        xMin: col * colW,
        xMax: (col + 1) * colW,
        yMin: row * rowH,
        yMax: (row + 1) * rowH,
      });
    }
  }
  return zones;
}

// Inclusive on both edges -- a point sitting exactly on a shared internal
// boundary line can match two adjacent zones (double-counted at the seam),
// which is fine for this tool's purpose (visual isolation + OBJ export of a
// "roughly this area" chunk, not a precise non-overlapping partition).
export function pointInZone(xFt, yFt, zone) {
  if (!zone) return true;
  return xFt >= zone.xMin && xFt <= zone.xMax && yFt >= zone.yMin && yFt <= zone.yMax;
}

// True per-object clipping (2026-07-24) -- previously every zone-isolation/
// export consumer filtered whole objects in/out by a single anchor point,
// which left line-shaped elements (structural struts, canopy trunk/branch,
// circulation paths) and building/panel boxes sticking out past a zone's
// edge whenever they crossed it, instead of being cut cleanly at the
// boundary. These three functions replace that point-only filtering
// wherever an object's true footprint can straddle a cut.

// Axis-aligned rectangle intersection -- shared by clipBoxSpec below and
// App.jsx's real_slabs bbox clip (a real slab's top_corners_ft footprint is
// axis-aligned or very close to it at this site's ramp tilt angles, same
// simplification blender/pershing_headless_build.py's _add_slab_plate
// already relies on -- see its docstring). Returns null if the rectangles
// don't overlap at all.
export function clipRectBounds(xMin, xMax, yMin, yMax, zone) {
  const nxMin = Math.max(xMin, zone.xMin);
  const nxMax = Math.min(xMax, zone.xMax);
  const nyMin = Math.max(yMin, zone.yMin);
  const nyMax = Math.min(yMax, zone.yMax);
  if (nxMin >= nxMax || nyMin >= nyMax) return null;
  return { xMin: nxMin, xMax: nxMax, yMin: nyMin, yMax: nyMax };
}

// Liang-Barsky segment-vs-rectangle clip in the spec's own XY plane, then
// linearly re-interpolates z at the same clipped t range -- a true 3D
// segment truncation (a strut/path cut at the zone edge lands exactly on
// the boundary at its real height there), not an XY-only clip with the
// full original Z span left dangling.
export function clipLineSpec(spec, zone) {
  const x1 = spec.x_ft, y1 = spec.y_ft, x2 = spec.x2_ft, y2 = spec.y2_ft;
  const dx = x2 - x1, dy = y2 - y1;
  let t0 = 0, t1 = 1;
  const clip = (p, q) => {
    if (p === 0) return q >= 0;
    const r = q / p;
    if (p < 0) {
      if (r > t1) return false;
      if (r > t0) t0 = r;
    } else {
      if (r < t0) return false;
      if (r < t1) t1 = r;
    }
    return true;
  };
  if (!clip(-dx, x1 - zone.xMin)) return null;
  if (!clip(dx, zone.xMax - x1)) return null;
  if (!clip(-dy, y1 - zone.yMin)) return null;
  if (!clip(dy, zone.yMax - y1)) return null;
  if (t0 >= t1) return null;

  const lerp = (a, b, t) => a + (b - a) * t;
  return {
    ...spec,
    x_ft: lerp(x1, x2, t0), y_ft: lerp(y1, y2, t0),
    z_top_ft: lerp(spec.z_top_ft, spec.z2_ft, t0),
    x2_ft: lerp(x1, x2, t1), y2_ft: lerp(y1, y2, t1),
    z2_ft: lerp(spec.z_top_ft, spec.z2_ft, t1),
  };
}

// Kinds whose scale/scale_y ARE literal center-anchored footprint width/
// depth, per frontend/src/kindRegistry.json's own shape notes ("panel...
// width/depth come from the spec's own scale/scale_y like building_mass").
// Every OTHER box-shaped kind (bolts, plates, collars, gusset plates, etc)
// uses a small FIXED prototype size from kindRegistry regardless of scale
// (scale means something unrelated there -- e.g. steel_collar_sleeve's
// scale is shoring_density) -- those stay point-filtered as atomic small
// items below, never box-clipped.
const BOX_CLIP_KINDS = new Set(['building_mass', 'canopy_panel']);

// rotation_deg is ignored -- both BOX_CLIP_KINDS are always grid-aligned in
// practice (logic/terracing_engine.py's BuildingMassEngine and
// logic/canopy_engine.py's _panel_specs() never set it), so treating this
// as an honest axis-aligned clip isn't an approximation of a rotated case
// that doesn't occur.
export function clipBoxSpec(spec, zone) {
  const halfW = spec.scale / 2;
  const halfH = (spec.scale_y ?? spec.scale) / 2;
  const clipped = clipRectBounds(
    spec.x_ft - halfW, spec.x_ft + halfW, spec.y_ft - halfH, spec.y_ft + halfH, zone,
  );
  if (!clipped) return null;
  return {
    ...spec,
    x_ft: (clipped.xMin + clipped.xMax) / 2,
    y_ft: (clipped.yMin + clipped.yMax) / 2,
    scale: clipped.xMax - clipped.xMin,
    scale_y: clipped.yMax - clipped.yMin,
  };
}

// Single dispatcher for a StructuralElement-shaped spec (steel/timber
// framing, canopy, circulation network, program_boxes all share this exact
// field shape, see logic/pershing_api.py's _serialize_specs) -- line-shaped
// (x2_ft set, kindRegistry's own "two_point" shape-detection rule) gets a
// true segment clip, building_mass/canopy_panel get a true box clip,
// everything else (bolts, plates, collars, real columns, etc -- small FIXED-
// size items) stays a simple point-in-zone atomic include/exclude on its
// own anchor -- clipping a 1.5ft gusset plate at a boundary would be
// meaningless work for an invisible result.
export function clipStructuralSpec(spec, zone) {
  if (!zone) return spec;
  if (spec.x2_ft !== null && spec.x2_ft !== undefined) return clipLineSpec(spec, zone);
  if (BOX_CLIP_KINDS.has(spec.kind)) return clipBoxSpec(spec, zone);
  return pointInZone(spec.x_ft, spec.y_ft, zone) ? spec : null;
}
