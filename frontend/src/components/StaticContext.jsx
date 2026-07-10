import { Suspense, useMemo } from 'react';
import { useLoader } from '@react-three/fiber';
import { OBJLoader } from 'three/examples/jsm/loaders/OBJLoader.js';
import * as THREE from 'three';
import { materialProps } from '../shading.js';

const CONTEXT_OBJ_URL = 'http://127.0.0.1:8000/pershing-context/site_named.obj';
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
function StaticContextGroup({ siteLengthFt, shadingMode }) {
  const obj = useLoader(OBJLoader, CONTEXT_OBJ_URL);

  const filtered = useMemo(() => {
    const group = new THREE.Group();
    const material = new THREE.MeshStandardMaterial(materialProps(shadingMode, CONTEXT_COLOR));
    for (const child of [...obj.children]) {
      if (child.name === 'terrace') continue;
      child.traverse((n) => {
        if (n.isMesh) n.material = material;
      });
      group.add(child);
    }
    // Real (x, y, z_up) -> Three (X, Y_up, L-y) -- same transform as
    // Viewport.jsx's toThree(x, y, z, L) = [x, z, L - y] applied per-point
    // (fixed 2026-07-09 alongside toThree -- this matrix had the same
    // shift-instead-of-mirror bug: swapping Rhino's Y/Z axes to build a
    // Y-up Three.js frame reverses handedness, and a plain shift doesn't
    // restore it, so every static-context object was a left-handed mirror
    // image of the real Rhino layout along this one axis. See toThree's
    // own comment for the full derivation), expressed as one whole-group
    // matrix instead of per-vertex to avoid re-deriving rotation+
    // translation composition by hand -- built explicitly and verified
    // against the live render rather than assumed.
    const m = new THREE.Matrix4();
    m.set(
      1, 0, 0, 0,
      0, 0, 1, 0,
      0, -1, 0, siteLengthFt,
      0, 0, 0, 1,
    );
    group.matrixAutoUpdate = false;
    group.matrix.copy(m);
    return group;
  }, [obj, siteLengthFt, shadingMode]);

  return <primitive object={filtered} />;
}

export default function StaticContext({ siteLengthFt, shadingMode }) {
  return (
    <Suspense fallback={null}>
      <StaticContextGroup siteLengthFt={siteLengthFt} shadingMode={shadingMode} />
    </Suspense>
  );
}
