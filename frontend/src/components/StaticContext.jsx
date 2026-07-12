import { Suspense, useMemo } from 'react';
import { useLoader } from '@react-three/fiber';
import { OBJLoader } from 'three/examples/jsm/loaders/OBJLoader.js';
import * as THREE from 'three';
import { materialProps, outlineMaterialProps, OUTLINE_SCALE } from '../shading.js';

// Relative, same-origin (2026-07-11 fix) -- previously a hardcoded
// absolute 'http://127.0.0.1:8000/...' URL, found stale (backend has been
// on :8001 all session) and silently broken; vite.config.js's proxy now
// covers /pershing-context directly, consistent with /api/
// /pershing-sketch/etc.
const CONTEXT_OBJ_URL = '/pershing-context/site_named.obj';
const CONTEXT_COLOR = '#5a6570'; // muted grey-blue -- real existing structure, distinct from the colorful live excavation result

// Mirrors blender_cockpit.py's import_static_context(): the real existing
// columns/tunnel/secondary_entrance/ramps, imported once from the same
// site_named.obj Blender loads (up_axis='Z', forward_axis='Y' there --
// i.e. the file's raw (x, y, z) is already real feet, Z-up, matching
// REAL_GEOMETRY's convention with no axis swap needed). Static reference
// only -- does not participate in the live TerracingEngine rebuild, so
// this loads once on mount, not on every param change. Skips the file's
// own "terrace" group the same way Blender's import does (the cockpit
// builds its own live terrace instead).
// Shared by the main and outline groups -- real (x, y, z_up) -> Three
// (X, Y_up, L-y), same transform as Viewport.jsx's toThree(x, y, z, L) =
// [x, z, L - y] applied per-point (fixed 2026-07-09 alongside toThree --
// this matrix had the same shift-instead-of-mirror bug: swapping Rhino's
// Y/Z axes to build a Y-up Three.js frame reverses handedness, and a plain
// shift doesn't restore it, so every static-context object was a left-
// handed mirror image of the real Rhino layout along this one axis. See
// toThree's own comment for the full derivation), expressed as one whole-
// group matrix instead of per-vertex to avoid re-deriving rotation+
// translation composition by hand -- built explicitly and verified against
// the live render rather than assumed.
function siteMatrix(siteLengthFt) {
  const m = new THREE.Matrix4();
  m.set(
    1, 0, 0, 0,
    0, 0, 1, 0,
    0, -1, 0, siteLengthFt,
    0, 0, 0, 1,
  );
  return m;
}

function StaticContextGroup({ siteLengthFt, shadingMode }) {
  const obj = useLoader(OBJLoader, CONTEXT_OBJ_URL);
  const ghosted = shadingMode === 'ghosted';

  const filtered = useMemo(() => {
    const group = new THREE.Group();
    const material = new THREE.MeshStandardMaterial(materialProps(shadingMode, CONTEXT_COLOR));
    for (const child of [...obj.children]) {
      if (child.name === 'terrace') continue;
      child.traverse((n) => {
        if (n.isMesh) {
          n.material = material;
          // Real existing structure (columns/tunnel/entrance/ramps) should
          // cast onto and receive from the live excavation result just like
          // every procedural mesh in Viewport.jsx does (2026-07-11 fix).
          n.castShadow = true;
          n.receiveShadow = true;
        }
      });
      group.add(child);
    }
    group.matrixAutoUpdate = false;
    group.matrix.copy(siteMatrix(siteLengthFt));
    return group;
  }, [obj, siteLengthFt, shadingMode]);

  // Ghosted outline: a second, cloned copy of the same geometry, scaled up
  // a few percent per-mesh (around each mesh's own local origin, not the
  // group's -- these are arbitrary loaded parts, not primitives centered
  // at their own pivot by construction the way the unit box/cylinder
  // instances elsewhere in this file are, so this is a reasonable
  // approximation rather than an exact per-centroid scale like
  // RealSlabPlate's outline does -- acceptable here since this is
  // secondary reference geometry, not the primary real structure), BackSide
  // material so only the silhouette fringe shows.
  const outlineGroup = useMemo(() => {
    if (!ghosted) return null;
    const group = new THREE.Group();
    const material = new THREE.MeshStandardMaterial(outlineMaterialProps());
    for (const child of [...obj.children]) {
      if (child.name === 'terrace') continue;
      const clone = child.clone(true);
      clone.traverse((n) => {
        if (n.isMesh) {
          n.material = material;
          n.scale.multiplyScalar(OUTLINE_SCALE);
        }
      });
      group.add(clone);
    }
    group.matrixAutoUpdate = false;
    group.matrix.copy(siteMatrix(siteLengthFt));
    return group;
  }, [obj, siteLengthFt, ghosted]);

  return (
    <>
      <primitive object={filtered} />
      {outlineGroup && <primitive object={outlineGroup} />}
    </>
  );
}

export default function StaticContext({ siteLengthFt, shadingMode }) {
  return (
    <Suspense fallback={null}>
      <StaticContextGroup siteLengthFt={siteLengthFt} shadingMode={shadingMode} />
    </Suspense>
  );
}
