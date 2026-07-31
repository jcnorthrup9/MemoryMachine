// Shading modes -- adopted from the two Blender viewport looks the user
// specifically liked: plain SOLID shading (flat, muted, single-material
// "massing model" read) and WIREFRAME. "Ghosted" additionally makes it
// semi-transparent (depthWrite off, standard for X-ray/ghost massing
// renders in CAD tools) so the framing/typology detail nested INSIDE the
// solid base slab -- normally hidden -- becomes visible, which is also a
// direct answer to "more objects/more detail" raised earlier.
//
// Shared by Viewport.jsx and StaticContext.jsx -- kept in its own module
// (not exported from Viewport.jsx) specifically to avoid a circular
// import between the two.
import * as THREE from 'three';

export const GHOST_COLOR = '#8f9aa6';

// "Arctic" mode -- Rhino's flat white/matte massing display, adopted per
// user request. Deliberately discards baseColor entirely (unlike every
// other mode here, which tints per-kind) so the whole scene reads as one
// continuous white form, differentiated only by the existing lights'
// falloff -- that discarding-of-color is the whole point of Rhino's Arctic
// mode, not an oversight. High roughness/no metalness keeps it matte
// (clay-like) rather than glossy/plastic.
export const ARCTIC_COLOR = '#f2f1ee';

// Ghosted-mode outline (2026-07-10): a thin grey/black fringe around every
// shape so translucent geometry stays legible instead of dissolving into an
// indistinct gray haze. Standard "inverted hull" technique -- a second copy
// of the same geometry/instance data, scaled up a few percent, BackSide
// only (so just the silhouette fringe shows, not a solid duplicate), flat
// unlit color. Works uniformly across every rendering shape in this scene
// (raw instancedMesh, drei Instances, custom BufferGeometry, a loaded OBJ
// scene graph) since it only needs "the same shape again, slightly bigger" --
// there's no single generic "outline any child" primitive to lean on
// instead, so each component adds its own outline pass using these shared
// constants/helper rather than reinventing the color/scale per call site.
export const OUTLINE_COLOR = '#2a2e33';
export const OUTLINE_SCALE = 1.04;

export function outlineMaterialProps() {
  return {
    color: OUTLINE_COLOR, side: THREE.BackSide, roughness: 1, metalness: 0,
    transparent: false, depthWrite: true,
  };
}

// Which modes get the outline pass above -- Ghosted needs it for legibility
// (translucent geometry otherwise dissolves into a haze); Arctic (2026-07-12,
// per user request) wants it too, purely for aesthetics -- a slight black
// line keeps individual forms readable against Arctic's single flat-white
// material, which otherwise has zero color/shading contrast between
// adjacent objects. Every OTHER mode (Colored, Wireframe) already has enough
// contrast (per-kind tint, or the wireframe lines themselves) and doesn't
// use this pass. Centralized here (not duplicated as `=== 'ghosted' ||
// === 'arctic'` at each of the ~8 call sites) so which modes outline is a
// single source of truth.
export function showsOutline(shadingMode) {
  return shadingMode === 'ghosted' || shadingMode === 'arctic';
}

// Which modes cast/receive real shadows (2026-07-12 fix, two real bugs
// reported after shadow-mapping was added): only opaque, non-line materials
// should participate at all.
//   - Wireframe: three.js renders the shadow-map depth pass with a plain
//     opaque depth material by default, completely ignoring the visible
//     material's `wireframe: true` flag -- a wireframe object was therefore
//     still throwing a solid, filled-silhouette shadow, which read as "a
//     solid object is here" even though nothing solid was actually drawn.
//   - Ghosted: semi-transparent instancedMesh/Instances have no reliable
//     per-instance depth sort in three.js/WebGL (sorting happens per
//     top-level object, not per-instance within one instancedMesh) --
//     layering a shadow pass on top of hundreds of overlapping translucent
//     instances added visible, orbit-dependent artifacting on top of that
//     already-fragile transparency blending. Turning shadows off for this
//     mode removes shadow-mapping specifically as a contributing factor;
//     the underlying instanced-transparency depth-sort limitation is a
//     separate, harder problem this does not fully solve on its own.
// Shaded (the renamed 'colored' key) and Arctic are both opaque, normal
// materials -- shadows work correctly and look intentional on both.
export function castsShadows(shadingMode) {
  return shadingMode === 'colored' || shadingMode === 'arctic';
}

// key stays 'colored' internally (not user-visible, avoids touching every
// `=== 'colored'` check across Viewport.jsx/StaticContext.jsx for a pure
// rename) -- only the displayed label changed to "SHADED" per user request.
export const SHADING_MODES = [
  { key: 'colored', label: 'SHADED' },
  { key: 'ghosted', label: 'GHOSTED' },
  { key: 'wireframe', label: 'WIREFRAME' },
  { key: 'arctic', label: 'ARCTIC' },
];

// DoubleSide on every mode -- discovered 2026-07-06 adding true Front/Side
// orthographic elevations: axis-aligned instanced boxes viewed exactly
// along one of their own local axes hit a degenerate backface-culling
// case (front faces reporting as back-facing to the GPU at that exact
// angle) that Perspective/Axo never exposed, since those always view the
// boxes at an oblique angle where the "wrong" face just isn't the
// dominant one on screen. Cheap for this scene's low instance counts.
export function materialProps(shadingMode, baseColor) {
  if (shadingMode === 'wireframe') {
    return { color: baseColor, wireframe: true, roughness: 1, metalness: 0, side: THREE.DoubleSide };
  }
  if (shadingMode === 'ghosted') {
    return {
      color: GHOST_COLOR, transparent: true, opacity: 0.42, depthWrite: false,
      roughness: 0.9, metalness: 0, side: THREE.DoubleSide,
    };
  }
  if (shadingMode === 'arctic') {
    return { color: ARCTIC_COLOR, roughness: 0.95, metalness: 0, side: THREE.DoubleSide };
  }
  return { color: baseColor, side: THREE.DoubleSide };
}
