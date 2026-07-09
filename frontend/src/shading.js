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

export const SHADING_MODES = [
  { key: 'colored', label: 'COLORED' },
  { key: 'ghosted', label: 'GHOSTED' },
  { key: 'wireframe', label: 'WIREFRAME' },
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
  return { color: baseColor, side: THREE.DoubleSide };
}
