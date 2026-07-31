import { Suspense, useMemo } from 'react';
import { useLoader } from '@react-three/fiber';
import { OBJLoader } from 'three/examples/jsm/loaders/OBJLoader.js';
import * as THREE from 'three';
import { materialProps } from '../shading.js';

const BUILD_COLOR = '#c9a35a'; // distinct from the live view's own palette -- makes it obvious which layer is on screen

// Displays the OBJ produced by the headless-Blender "build" tier (see
// logic/pershing_blender.py / blender/pershing_headless_build.py) --
// concatenated real bmesh geometry (terrace + every structural kind),
// as opposed to the live view's GPU-instanced boxes/cylinders. Same
// load-and-transform pattern as StaticContext.jsx (useLoader(OBJLoader),
// per-mesh material override, one whole-group matrix instead of a
// per-vertex transform), but WITHOUT StaticContext's terrace-name filter
// or axo-mirror: this OBJ was deliberately exported in the same raw
// real-feet, Z-up convention the live JSON already uses (see
// pershing_headless_build.py's module docstring), so it needs exactly the
// same real->Three axis remap toThree() applies elsewhere and nothing
// more.
//
// objUrl is used as-is (relative, same-origin) -- previously prefixed with
// a hardcoded BLENDER_HOST absolute URL, removed 2026-07-11 after it was
// found stale (pointed at :8000, the backend has been on :8001 all
// session) and silently broken; vite.config.js's proxy now covers
// /blender-headless-output directly, so a plain relative URL just works,
// consistent with how /api and /pershing-sketch already do.
function BlenderBuildGroup({ objUrl, siteLengthFt, shadingMode }) {
  const obj = useLoader(OBJLoader, objUrl);

  const group = useMemo(() => {
    const g = new THREE.Group();
    const material = new THREE.MeshStandardMaterial(materialProps(shadingMode, BUILD_COLOR));
    for (const child of [...obj.children]) {
      child.traverse((n) => {
        if (n.isMesh) n.material = material;
      });
      g.add(child);
    }
    // real (x, y, z_up) -> Three (X, Y_up=z, Z=L-y) -- identical to
    // StaticContext.jsx's matrix and Viewport.jsx's toThree() (fixed
    // 2026-07-09 alongside both, same shift-instead-of-mirror handedness
    // bug -- see toThree's own comment for the full derivation), expressed
    // as one whole-group matrix for the same reason StaticContext.jsx
    // does: avoids re-deriving rotation+translation composition by hand.
    const m = new THREE.Matrix4();
    m.set(
      1, 0, 0, 0,
      0, 0, 1, 0,
      0, -1, 0, siteLengthFt,
      0, 0, 0, 1,
    );
    g.matrixAutoUpdate = false;
    g.matrix.copy(m);
    return g;
  }, [obj, siteLengthFt, shadingMode]);

  return <primitive object={group} />;
}

export default function BlenderBuild({ objUrl, siteLengthFt, shadingMode }) {
  if (!objUrl) return null;
  return (
    <Suspense fallback={null}>
      <BlenderBuildGroup objUrl={objUrl} siteLengthFt={siteLengthFt} shadingMode={shadingMode} />
    </Suspense>
  );
}
