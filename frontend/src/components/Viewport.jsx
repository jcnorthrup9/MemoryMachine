import { useMemo, useRef, useLayoutEffect, useState, useCallback } from 'react';
import { Canvas, useThree } from '@react-three/fiber';
import { OrbitControls, Instances, Instance, PerspectiveCamera, OrthographicCamera, Text, Billboard } from '@react-three/drei';
import * as THREE from 'three';
import StaticContext from './StaticContext.jsx';
import BlenderBuild from './BlenderBuild.jsx';
import { materialProps, outlineMaterialProps, OUTLINE_SCALE, SHADING_MODES } from '../shading.js';
import KIND_REGISTRY from '../kindRegistry.json';

// Rounds an instance count up to the next power of 2 (min 8) -- 2026-07-10,
// paired with the count-in-key remount fix above each <Instances> block.
// Keying strictly on the raw count (the correctness fix) means EVERY
// change in a kind's instance count forces a full remount (fresh GPU
// buffer allocation) even for a change of 1 -- correct, but means dragging
// a slider that grows a kind by one instance per tick remounts every tick.
// Keying on this padded capacity instead only remounts when the count
// crosses a power-of-2 boundary (O(log n) remounts as a count grows, same
// standard growth strategy dynamic arrays use), while `range` (passed
// separately, always the exact count) keeps the rendered instance count
// exact regardless of the padded buffer size -- never over-renders.
function paddedCapacity(count) {
  if (count <= 0) return 0;
  return Math.max(8, 2 ** Math.ceil(Math.log2(count)));
}

// Derived from the shared kind registry (2026-07-10 consolidation pass --
// see kindRegistry.json's own _meta for why this replaced independently
// hand-maintained copies of these same tables here, in terracing_engine.py,
// and in blender_cockpit.py). Cylinder/hex kinds don't use PROTOTYPE_DIMS_FT
// -- their geometry comes from spec.radius_ft (and, for two-point kinds,
// x2/y2/z2_ft) instead; see CylinderInstances/HexInstances below, which
// mirror blender_cockpit.py's _add_cylinder/_add_hex_prism and the
// x2_ft-is-not-None / HEX_KINDS / VERTICAL_CYLINDER_KINDS branching in its
// build_structural_meshes.
const PROTOTYPE_DIMS_FT = Object.fromEntries(
  Object.entries(KIND_REGISTRY.kinds).filter(([, v]) => v.shape === 'box').map(([k, v]) => [k, v.dims_ft]),
);
const VERTICAL_CYLINDER_KINDS = new Set(
  Object.entries(KIND_REGISTRY.kinds).filter(([, v]) => v.shape === 'vertical_cylinder').map(([k]) => k),
);
const HEX_KINDS = new Set(
  Object.entries(KIND_REGISTRY.kinds).filter(([, v]) => v.shape === 'hex').map(([k]) => k),
);
// Per-kind tint -- roughly matches the paint-category tints already
// established for Water/Shade (cyan) and Amenity/Resting (orange) so the
// same semantic colors carry through from painting to rendered assets.
const KIND_COLOR = Object.fromEntries(Object.entries(KIND_REGISTRY.kinds).map(([k, v]) => [k, v.color]));

// Site (x, y_ft, z_ft) -> Three.js (X, Y-up, Z). Real-feet Z (up) maps
// straight to Three Y; real site "y" (length axis) needs a mirror
// (y -> siteLengthFt - y), NOT a plain shift -- fixed 2026-07-09, this
// function's own code previously read `y - siteLengthFt` (a shift, order-
// preserving) despite this very comment already documenting the intended
// formula as `siteLengthFt - y` (a mirror) and blender_cockpit.py's
// setup_axo_view already correctly implementing that same mirror
// (`mathutils.Matrix(((1,0,0,0),(0,-1,0,L),...))`, note the -1). The
// mismatch was a real bug, not just a stale comment: swapping Rhino's Y
// (length) and Z (vertical) axes to build a Y-up Three.js frame reverses
// handedness (a single-axis transposition is an odd permutation), and
// restoring right-handedness requires negating exactly one of the two
// swapped axes -- a plain shift doesn't do that, so every object in this
// scene was a left-handed mirror image of the real Rhino layout along
// this one axis. Confirmed against live Rhino data: the metroConnection
// entrance (2026-07-09 Z-axis-sign-bug fix) sits near Rhino's own Y-max,
// which a native Rhino Top view renders near the TOP of screen -- the old
// shift put it near the BOTTOM instead, exactly the "looks mirrored/
// upside-down" symptom reported after adding the Plan-view street labels.
function toThree(x, y, z, siteLengthFt) {
  return [x, z, siteLengthFt - y];
}

// Generous vertical extent estimate for framing Front/Side elevations --
// columns run up to ~30ft (column_height_ft) and the canyon can cut down
// to floor_z = -(max_canyon_depth_ft + 10), max_canyon_depth_ft itself
// capped at column_height_ft in pershing_api.py -- so ~70ft of real
// vertical range, plus padding. Not passed as a prop since it only needs
// to be roughly right (OrbitControls scroll-zoom covers the rest).
const HEIGHT_SPAN_FT = 100;

// Mirrors the standard architectural view set (plan/front/side/axo) plus
// free perspective orbit -- "orthographic" presets use a true
// THREE.OrthographicCamera (no vanishing-point distortion), matching
// what an architect expects from a plan or elevation export, per project
// decision 2026-07-06. dir is the camera's offset direction from `center`
// (site-plan units, will be scaled by a large distance); up avoids the
// degenerate straight-down case by giving OrbitControls' spherical math a
// non-parallel reference axis (the standard three.js top-down-orbit
// technique).
const VIEW_PRESETS = {
  perspective: { label: 'Perspective', type: 'perspective' },
  axo: {
    label: 'Axo / Iso',
    type: 'orthographic',
    dir: [1, 1, 1],
    up: [0, 1, 0],
    extent: (w, l, h) => [Math.max(w, l) * 1.3, Math.max(w, l, h) * 1.1],
  },
  plan: {
    label: 'Plan',
    type: 'orthographic',
    dir: [0, 1, 0],
    up: [0, 0, -1],
    extent: (w, l) => [w, l],
  },
  front: {
    label: 'Front',
    type: 'orthographic',
    dir: [0, 0, 1],
    up: [0, 1, 0],
    extent: (w, l, h) => [w, h],
  },
  side: {
    label: 'Side',
    type: 'orthographic',
    dir: [1, 0, 0],
    up: [0, 1, 0],
    extent: (w, l, h) => [l, h],
  },
};

// Picks the active camera per viewMode -- a true PerspectiveCamera for
// free orbit (today's original default), a true OrthographicCamera for
// every preset drawing view. zoom is derived from the live canvas pixel
// size (useThree's `size`) so each preset frames the whole site on
// first click instead of requiring a manual scroll-zoom every time.
function ViewCamera({ view, center, siteWidthFt, siteLengthFt }) {
  const { size } = useThree();
  const preset = VIEW_PRESETS[view] || VIEW_PRESETS.perspective;

  if (preset.type === 'perspective') {
    return (
      <PerspectiveCamera
        makeDefault
        position={[center[0] + 250, 250, center[2] + 250]}
        fov={45}
        near={1}
        far={4000}
      />
    );
  }

  const dist = Math.max(siteWidthFt, siteLengthFt, HEIGHT_SPAN_FT) * 2.5;
  const [dx, dy, dz] = preset.dir;
  const position = [center[0] + dx * dist, dy * dist, center[2] + dz * dist];
  const [worldW, worldH] = preset.extent(siteWidthFt, siteLengthFt, HEIGHT_SPAN_FT);
  const pad = 1.25;
  const zoom = Math.max(0.01, Math.min(size.width / (worldW * pad), size.height / (worldH * pad)));

  return (
    <OrthographicCamera makeDefault position={position} up={preset.up} zoom={zoom} near={1} far={dist * 3} />
  );
}

// Thin colored cap on top of each greenscape-painted voxel's own terrain
// height (v.z_ft, the same top-surface value TerraceLevelGroup builds its
// block up to) -- NOT a flat plane at z=0, since the terrain isn't flat
// once excavated; sitting the cap at v.z_ft keeps grass following the cut
// terrace surface instead of floating above pits or clipping through
// them. Same one-InstancedMesh-of-filtered-voxels pattern as
// TerraceLevelGroup. Placeholder solid color for now (hybrid asset
// strategy: cheap now, swap for a real grass texture/material later
// without touching data plumbing -- is_greenscape is already real
// per-voxel data from the paint mask, not derived here).
const GREENSCAPE_COLOR = '#3d9142';
const GREENSCAPE_THICKNESS_FT = 0.5;

function GreenscapeGround({ voxels, voxelFt, siteLengthFt, shadingMode }) {
  const meshRef = useRef();
  const outlineRef = useRef();
  const ghosted = shadingMode === 'ghosted';
  const items = useMemo(() => voxels.filter((v) => v.is_greenscape), [voxels]);

  useLayoutEffect(() => {
    if (!meshRef.current) return;
    const dummy = new THREE.Object3D();
    items.forEach((v, i) => {
      const cx = v.gx * voxelFt + voxelFt / 2;
      const cy = v.gy * voxelFt + voxelFt / 2;
      const cz = v.z_ft + GREENSCAPE_THICKNESS_FT / 2;
      const [x, y, z] = toThree(cx, cy, cz, siteLengthFt);
      dummy.position.set(x, y, z);
      dummy.scale.set(voxelFt, GREENSCAPE_THICKNESS_FT, voxelFt);
      dummy.updateMatrix();
      meshRef.current.setMatrixAt(i, dummy.matrix);
      if (outlineRef.current) {
        dummy.scale.set(voxelFt * OUTLINE_SCALE, GREENSCAPE_THICKNESS_FT * OUTLINE_SCALE, voxelFt * OUTLINE_SCALE);
        dummy.updateMatrix();
        outlineRef.current.setMatrixAt(i, dummy.matrix);
      }
    });
    meshRef.current.instanceMatrix.needsUpdate = true;
    if (outlineRef.current) outlineRef.current.instanceMatrix.needsUpdate = true;
  }, [items, voxelFt, siteLengthFt, ghosted]);

  if (items.length === 0) return null;

  const mat = materialProps(shadingMode, GREENSCAPE_COLOR);
  return (
    <>
      <instancedMesh ref={meshRef} args={[undefined, undefined, items.length]}>
        <boxGeometry args={[1, 1, 1]} />
        <meshStandardMaterial {...mat} />
      </instancedMesh>
      {ghosted && (
        <instancedMesh ref={outlineRef} args={[undefined, undefined, items.length]}>
          <boxGeometry args={[1, 1, 1]} />
          <meshStandardMaterial {...outlineMaterialProps()} />
        </instancedMesh>
      )}
    </>
  );
}

// Same one-InstancedMesh-of-filtered-voxels pattern as GreenscapeGround,
// filtered by v.typology === 'CIRCULATION' (server-classified: hardscape
// cells where the foot-traffic influence field crosses circulation_threshold
// -- see terracing_engine.py's _classify_typology) instead of a raw boolean
// mask. Gives HARDSCAPE_MASK its first visual identity in this viewport --
// previously invisible, only ever an excavation veto.
const CIRCULATION_COLOR = '#8a8378';
const CIRCULATION_THICKNESS_FT = 0.5;

function CirculationSurface({ voxels, voxelFt, siteLengthFt, shadingMode }) {
  const meshRef = useRef();
  const outlineRef = useRef();
  const ghosted = shadingMode === 'ghosted';
  const items = useMemo(() => voxels.filter((v) => v.typology === 'CIRCULATION'), [voxels]);

  useLayoutEffect(() => {
    if (!meshRef.current) return;
    const dummy = new THREE.Object3D();
    items.forEach((v, i) => {
      const cx = v.gx * voxelFt + voxelFt / 2;
      const cy = v.gy * voxelFt + voxelFt / 2;
      const cz = v.z_ft + CIRCULATION_THICKNESS_FT / 2;
      const [x, y, z] = toThree(cx, cy, cz, siteLengthFt);
      dummy.position.set(x, y, z);
      dummy.scale.set(voxelFt, CIRCULATION_THICKNESS_FT, voxelFt);
      dummy.updateMatrix();
      meshRef.current.setMatrixAt(i, dummy.matrix);
      if (outlineRef.current) {
        dummy.scale.set(voxelFt * OUTLINE_SCALE, CIRCULATION_THICKNESS_FT * OUTLINE_SCALE, voxelFt * OUTLINE_SCALE);
        dummy.updateMatrix();
        outlineRef.current.setMatrixAt(i, dummy.matrix);
      }
    });
    meshRef.current.instanceMatrix.needsUpdate = true;
    if (outlineRef.current) outlineRef.current.instanceMatrix.needsUpdate = true;
  }, [items, voxelFt, siteLengthFt, ghosted]);

  if (items.length === 0) return null;

  const mat = materialProps(shadingMode, CIRCULATION_COLOR);
  return (
    <>
      <instancedMesh ref={meshRef} args={[undefined, undefined, items.length]}>
        <boxGeometry args={[1, 1, 1]} />
        <meshStandardMaterial {...mat} />
      </instancedMesh>
      {ghosted && (
        <instancedMesh ref={outlineRef} args={[undefined, undefined, items.length]}>
          <boxGeometry args={[1, 1, 1]} />
          <meshStandardMaterial {...outlineMaterialProps()} />
        </instancedMesh>
      )}
    </>
  );
}

// Real column solids, extracted directly from the live Rhino STRUC__Columns
// Breps (2026-07-09 real-slab-graph supplement) -- NOT a procedural
// placeholder, real per-column position/diameter/top/bottom. Same two-point
// cylinder construction as CylinderInstances' strut/tie-rod path, kept as
// its own component (rather than folding into that one) since real_columns
// is a distinct data source (data.real_columns, not data.structural) with
// its own fixed color so it reads as "real structure" against the
// procedural framing.
const REAL_COLUMN_COLOR = KIND_REGISTRY.kinds.real_column.color;

// key={<count>} on every drei <Instances> block below (2026-07-10 fix): drei
// allocates the underlying InstancedMesh's GPU buffer ONCE, sized for
// whatever `limit` was at first mount. Unlike a raw <instancedMesh
// args={[,,count]}> (R3F specially reconstructs the object whenever `args`
// changes), `limit` is just a regular prop to drei's component -- if a
// LATER render passes a bigger `limit` without the component actually
// remounting, the buffer does NOT grow, and instances beyond the original
// allocation corrupt whatever GPU memory follows it (reproduced: increasing
// Canyon Depth while staying in STEEL mode grew steel_collar_sleeve's count
// without changing its `key={kind}`, producing huge garbled triangles in
// the live render -- switching material_mode "fixed" it only because it
// changes the whole kind-set, forcing every block to remount anyway).
// Keying on the count forces a real remount (fresh, correctly-sized buffer)
// every time an already-mounted kind's instance count changes at all.
function RealColumns({ columns, siteLengthFt, shadingMode }) {
  const items = useMemo(
    () => columns.map((c) => ({
      p0: toThree(c.x, c.z, c.bottom_ft, siteLengthFt),
      p1: toThree(c.x, c.z, c.top_ft, siteLengthFt),
      radius: c.diameter_ft / 2,
    })),
    [columns, siteLengthFt],
  );

  if (items.length === 0) return null;

  const ghosted = shadingMode === 'ghosted';
  const mat = materialProps(shadingMode, REAL_COLUMN_COLOR);
  const frames = items.map(({ p0, p1, radius }, i) => {
    const a = new THREE.Vector3(...p0);
    const b = new THREE.Vector3(...p1);
    const mid = a.clone().add(b).multiplyScalar(0.5);
    const dir = b.clone().sub(a);
    const length = dir.length();
    if (length < 1e-6) return null;
    const quat = new THREE.Quaternion().setFromUnitVectors(new THREE.Vector3(0, 1, 0), dir.normalize());
    return { key: i, position: mid.toArray(), quaternion: quat.toArray(), radius, length };
  }).filter(Boolean);

  return (
    <>
      <Instances key={paddedCapacity(frames.length)} limit={paddedCapacity(frames.length)} range={frames.length}>
        <cylinderGeometry args={[1, 1, 1, 12]} />
        <meshStandardMaterial {...mat} />
        {frames.map(({ key, position, quaternion, radius, length }) => (
          <Instance key={key} position={position} quaternion={quaternion} scale={[radius, length, radius]} />
        ))}
      </Instances>
      {ghosted && (
        <Instances key={`outline-${paddedCapacity(frames.length)}`} limit={paddedCapacity(frames.length)} range={frames.length}>
          <cylinderGeometry args={[1, 1, 1, 12]} />
          <meshStandardMaterial {...outlineMaterialProps()} />
          {frames.map(({ key, position, quaternion, radius, length }) => (
            <Instance
              key={key}
              position={position}
              quaternion={quaternion}
              scale={[radius * OUTLINE_SCALE, length * OUTLINE_SCALE, radius * OUTLINE_SCALE]}
            />
          ))}
        </Instances>
      )}
    </>
  );
}

// Real slab/ramp plates, extracted directly from the live Rhino
// STRUC__Slabs Breps (2026-07-09 real-slab-graph supplement) -- each entry
// is one real planar top face (real_slab_plates.json's per-face-pair
// extraction, NOT a bounding-box guess -- see plan doc for why bounding
// boxes mis-measured these as one fake 11ft-thick block). top_corners_ft
// carries the TRUE per-corner 3D position (real elevation per corner), so
// ramp_slab's ~1.7deg tilt renders as a real sloped plate, not a flat
// approximation -- the bottom face is offset straight down in world Z by
// thickness_ft (not along the tilted normal), a deliberate simplification:
// at this tilt (cos(1.7deg) > 0.9995) the difference is sub-1/8" over a
// 1ft-thick plate, not worth a full oriented-normal extrusion.
const SLAB_KIND_COLOR = { floor_slab: KIND_REGISTRY.kinds.floor_slab.color, ramp_slab: KIND_REGISTRY.kinds.ramp_slab.color };

// Rhino's Brep.Vertices order for a planar face is NOT guaranteed to trace
// a boundary loop (empirically a raster/grid order for these box faces --
// e.g. (xmin,ymin),(xmin,ymax),(xmax,ymin),(xmax,ymax) -- which would
// triangulate into a crossed/bowtie quad if used directly). Sorting by
// angle around the quad's own centroid (in plan x/y; z tags along per-corner
// unchanged) produces a correct non-crossing loop regardless of source
// order, since these are always simple convex rectangles in plan.
function orderQuadCorners(corners) {
  const cx = corners.reduce((s, c) => s + c[0], 0) / corners.length;
  const cy = corners.reduce((s, c) => s + c[1], 0) / corners.length;
  return [...corners].sort(
    (a, b) => Math.atan2(a[1] - cy, a[0] - cx) - Math.atan2(b[1] - cy, b[0] - cx),
  );
}

// top(0,1,2,3) / bottom(4,5,6,7), matching the same corner order on both
// faces (bottom is just top shifted down), so side faces simply connect
// corresponding index pairs -- both diagonals of the top/bottom quads are
// triangulated the same consistent way. Shared by RealSlabPlate's main and
// outline geometry (the outline is a separate BufferGeometry with its own
// pre-scaled vertices, not a `scale` prop on the mesh -- these verts are
// already in real Three.js world coordinates far from the origin, so a
// naive object-level `scale` would expand away from world (0,0,0) instead
// of around the slab's own center, visibly shifting the outline off the
// real slab instead of growing around it).
const SLAB_PLATE_INDICES = [
  0, 1, 2, 0, 2, 3,       // top
  4, 6, 5, 4, 7, 6,       // bottom (reversed winding)
  0, 4, 1, 1, 4, 5,       // side 0-1
  1, 5, 2, 2, 5, 6,       // side 1-2
  2, 6, 3, 3, 6, 7,       // side 2-3
  3, 7, 0, 0, 7, 4,       // side 3-0
];

function RealSlabPlate({ slab, siteLengthFt, shadingMode }) {
  const ghosted = shadingMode === 'ghosted';

  const { geometry, outlineGeometry } = useMemo(() => {
    const ordered = orderQuadCorners(slab.top_corners_ft);
    const top = ordered.map(([x, y, z]) => toThree(x, y, z, siteLengthFt));
    const bottom = top.map(([x, y, z]) => [x, y - slab.thickness_ft, z]);
    const corners = [...top, ...bottom];

    const geo = new THREE.BufferGeometry();
    geo.setAttribute('position', new THREE.Float32BufferAttribute(corners.flat(), 3));
    geo.setIndex(SLAB_PLATE_INDICES);
    geo.computeVertexNormals();

    let outlineGeo = null;
    if (ghosted) {
      const cx = corners.reduce((s, c) => s + c[0], 0) / corners.length;
      const cy = corners.reduce((s, c) => s + c[1], 0) / corners.length;
      const cz = corners.reduce((s, c) => s + c[2], 0) / corners.length;
      const scaled = corners.map(([x, y, z]) => [
        cx + (x - cx) * OUTLINE_SCALE,
        cy + (y - cy) * OUTLINE_SCALE,
        cz + (z - cz) * OUTLINE_SCALE,
      ]);
      outlineGeo = new THREE.BufferGeometry();
      outlineGeo.setAttribute('position', new THREE.Float32BufferAttribute(scaled.flat(), 3));
      outlineGeo.setIndex(SLAB_PLATE_INDICES);
      outlineGeo.computeVertexNormals();
    }
    return { geometry: geo, outlineGeometry: outlineGeo };
  }, [slab, siteLengthFt, ghosted]);

  const mat = materialProps(shadingMode, SLAB_KIND_COLOR[slab.kind] || '#aaaaaa');
  return (
    <>
      <mesh geometry={geometry}>
        <meshStandardMaterial {...mat} side={THREE.DoubleSide} />
      </mesh>
      {ghosted && outlineGeometry && (
        <mesh geometry={outlineGeometry}>
          <meshStandardMaterial {...outlineMaterialProps()} />
        </mesh>
      )}
    </>
  );
}

// One small box per real slab cell that hasn't been excavated away yet
// (2026-07-09 real-slab-driven harvest supplement) -- the "hole" a real
// floor_slab shows once the dig reaches it is just the gap where a fragment
// stopped being instanced, same box-instancing pattern TerraceVoxels/
// GreenscapeGround already use elsewhere in this file. Only floor_slab uses
// this (flat, so every fragment shares one z_top_ft) -- ramp_slab keeps
// rendering as the single intact tilted RealSlabPlate below; fragmenting a
// tilted plate needs per-fragment elevation interpolation along its slope,
// deferred (see plan doc).
function RealSlabFragments({ slab, remaining, voxelFt, siteLengthFt, shadingMode }) {
  const meshRef = useRef();
  const outlineRef = useRef();
  const ghosted = shadingMode === 'ghosted';

  useLayoutEffect(() => {
    if (!meshRef.current || remaining.length === 0) return;
    const dummy = new THREE.Object3D();
    const cz = slab.z_top_ft - slab.thickness_ft / 2;
    remaining.forEach(([wx, wy], i) => {
      const [x, y, z] = toThree(wx, wy, cz, siteLengthFt);
      dummy.position.set(x, y, z);
      dummy.scale.set(voxelFt, slab.thickness_ft, voxelFt);
      dummy.updateMatrix();
      meshRef.current.setMatrixAt(i, dummy.matrix);
      if (outlineRef.current) {
        dummy.scale.set(voxelFt * OUTLINE_SCALE, slab.thickness_ft * OUTLINE_SCALE, voxelFt * OUTLINE_SCALE);
        dummy.updateMatrix();
        outlineRef.current.setMatrixAt(i, dummy.matrix);
      }
    });
    meshRef.current.instanceMatrix.needsUpdate = true;
    if (outlineRef.current) outlineRef.current.instanceMatrix.needsUpdate = true;
  }, [remaining, voxelFt, slab, siteLengthFt, ghosted]);

  if (remaining.length === 0) return null;

  const mat = materialProps(shadingMode, SLAB_KIND_COLOR[slab.kind] || '#aaaaaa');
  return (
    <>
      <instancedMesh ref={meshRef} args={[undefined, undefined, remaining.length]}>
        <boxGeometry args={[1, 1, 1]} />
        <meshStandardMaterial {...mat} />
      </instancedMesh>
      {ghosted && (
        <instancedMesh ref={outlineRef} args={[undefined, undefined, remaining.length]}>
          <boxGeometry args={[1, 1, 1]} />
          <meshStandardMaterial {...outlineMaterialProps()} />
        </instancedMesh>
      )}
    </>
  );
}

function RealSlabs({ slabs, fragments, voxelFt, siteLengthFt, shadingMode }) {
  if (!slabs || slabs.length === 0) return null;
  return (
    <>
      {slabs.map((slab) => {
        if (slab.kind === 'floor_slab') {
          const remaining = fragments?.[slab.key]?.remaining ?? [];
          return (
            <RealSlabFragments
              key={slab.key}
              slab={slab}
              remaining={remaining}
              voxelFt={voxelFt}
              siteLengthFt={siteLengthFt}
              shadingMode={shadingMode}
            />
          );
        }
        return (
          <RealSlabPlate
            key={slab.key}
            slab={slab}
            siteLengthFt={siteLengthFt}
            shadingMode={shadingMode}
          />
        );
      })}
    </>
  );
}

function BoxInstances({ specs, siteLengthFt, shadingMode }) {
  const ghosted = shadingMode === 'ghosted';
  const byKind = useMemo(() => {
    const map = {};
    for (const s of specs) {
      if (s.x2_ft !== null || HEX_KINDS.has(s.kind) || VERTICAL_CYLINDER_KINDS.has(s.kind)) continue;
      (map[s.kind] ||= []).push(s);
    }
    return map;
  }, [specs]);

  // Fallback footprint (1,1) matches blender_cockpit.py's
  // _PROTOTYPE_DIMS_FT.get(kind, (1.0, 1.0, 1.0)) for any kind not in the map.
  const frameFor = (kind, s) => {
    const [sx, sy] = PROTOTYPE_DIMS_FT[kind] || [1.0, 1.0];
    const [x, y, z] = toThree(s.x_ft, s.y_ft, s.z_top_ft - s.height_ft / 2, siteLengthFt);
    // Only gusset_plate still gets a rotated-box treatment (faced along the
    // strut's bearing angle, about the vertical axis) -- mirrors
    // blender_cockpit.py's _rotation_for. Sign flipped because toThree's
    // y -> L-y mirror (matching Blender's own axo mirror) is a genuine
    // reflection, and a reflection reverses in-plane rotational handedness
    // around the vertical axis.
    const rotY = kind === 'gusset_plate' ? -(s.rotation_deg * Math.PI) / 180 : 0;
    // scale_y is only set for kinds needing an independent width vs. depth
    // (currently just building_mass) -- null everywhere else, falling back
    // to the original uniform `scale` behavior.
    return { position: [x, y, z], rotation: [0, rotY, 0], sx: sx * s.scale, sy: sy * (s.scale_y ?? s.scale), sz: s.height_ft };
  };

  return (
    <>
      {Object.entries(byKind).map(([kind, items]) => (
        <Instances key={`${kind}-${paddedCapacity(items.length)}`} limit={paddedCapacity(items.length)} range={items.length}>
          <boxGeometry args={[1, 1, 1]} />
          <meshStandardMaterial {...materialProps(shadingMode, KIND_COLOR[kind] || '#888888')} />
          {items.map((s, i) => {
            const f = frameFor(kind, s);
            return <Instance key={i} position={f.position} rotation={f.rotation} scale={[f.sx, f.sz, f.sy]} />;
          })}
        </Instances>
      ))}
      {ghosted && Object.entries(byKind).map(([kind, items]) => (
        <Instances key={`${kind}-outline-${paddedCapacity(items.length)}`} limit={paddedCapacity(items.length)} range={items.length}>
          <boxGeometry args={[1, 1, 1]} />
          <meshStandardMaterial {...outlineMaterialProps()} />
          {items.map((s, i) => {
            const f = frameFor(kind, s);
            return (
              <Instance
                key={i}
                position={f.position}
                rotation={f.rotation}
                scale={[f.sx * OUTLINE_SCALE, f.sz * OUTLINE_SCALE, f.sy * OUTLINE_SCALE]}
              />
            );
          })}
        </Instances>
      ))}
    </>
  );
}

// Round cylinders: two-point specs (steel_strut, steel_tie_rod,
// knee_brace, timber_beam -- anything with x2_ft set, matching Python's
// "if spec.x2_ft is not None" check, not a kind-name allowlist) plus the
// single-point "vertical cylinder" kinds (steel_bolt, bolt_flange_plate),
// whose endpoints Python derives as (x,y,z_top-height) -> (x,y,z_top).
// One unit cylinder (radius=1, height=1) scaled/rotated per instance --
// same trick TerraceVoxels/BoxInstances use for boxes.
function CylinderInstances({ specs, siteLengthFt, shadingMode }) {
  const ghosted = shadingMode === 'ghosted';
  const grouped = useMemo(() => {
    const map = {};
    for (const s of specs) {
      let p0, p1;
      if (s.x2_ft !== null) {
        p0 = toThree(s.x_ft, s.y_ft, s.z_top_ft, siteLengthFt);
        p1 = toThree(s.x2_ft, s.y2_ft, s.z2_ft, siteLengthFt);
      } else if (VERTICAL_CYLINDER_KINDS.has(s.kind)) {
        p0 = toThree(s.x_ft, s.y_ft, s.z_top_ft - s.height_ft, siteLengthFt);
        p1 = toThree(s.x_ft, s.y_ft, s.z_top_ft, siteLengthFt);
      } else {
        continue;
      }
      (map[s.kind] ||= []).push({ p0, p1, radius: s.radius_ft || 0.2 });
    }
    return map;
  }, [specs, siteLengthFt]);

  const framesFor = (items) => items.map(({ p0, p1, radius }) => {
    const a = new THREE.Vector3(...p0);
    const b = new THREE.Vector3(...p1);
    const mid = a.clone().add(b).multiplyScalar(0.5);
    const dir = b.clone().sub(a);
    const length = dir.length();
    if (length < 1e-6) return null;
    const quat = new THREE.Quaternion().setFromUnitVectors(new THREE.Vector3(0, 1, 0), dir.normalize());
    return { position: mid.toArray(), quaternion: quat.toArray(), radius, length };
  }).filter(Boolean);

  return (
    <>
      {Object.entries(grouped).map(([kind, items]) => (
        <Instances key={`${kind}-${paddedCapacity(items.length)}`} limit={paddedCapacity(items.length)} range={items.length}>
          <cylinderGeometry args={[1, 1, 1, 8]} />
          <meshStandardMaterial {...materialProps(shadingMode, KIND_COLOR[kind] || '#888888')} />
          {framesFor(items).map(({ position, quaternion, radius, length }, i) => (
            <Instance key={i} position={position} quaternion={quaternion} scale={[radius, length, radius]} />
          ))}
        </Instances>
      ))}
      {ghosted && Object.entries(grouped).map(([kind, items]) => (
        <Instances key={`${kind}-outline-${paddedCapacity(items.length)}`} limit={paddedCapacity(items.length)} range={items.length}>
          <cylinderGeometry args={[1, 1, 1, 8]} />
          <meshStandardMaterial {...outlineMaterialProps()} />
          {framesFor(items).map(({ position, quaternion, radius, length }, i) => (
            <Instance
              key={i}
              position={position}
              quaternion={quaternion}
              scale={[radius * OUTLINE_SCALE, length * OUTLINE_SCALE, radius * OUTLINE_SCALE]}
            />
          ))}
        </Instances>
      ))}
    </>
  );
}

// Hexagonal prism -- steel_turnbuckle at the dead center of each STEEL
// X-brace. Mirrors _add_hex_prism: center = (x_ft, y_ft, z_top_ft)
// directly (z_top_ft is genuinely the vertical CENTER here, not a
// top-referenced value like the box path -- a real inconsistency in the
// Python field naming across spec kinds, not a bug in this port).
function HexInstances({ specs, siteLengthFt, shadingMode }) {
  const items = useMemo(
    () => specs.filter((s) => HEX_KINDS.has(s.kind) && s.x2_ft === null),
    [specs],
  );
  if (items.length === 0) return null;

  const ghosted = shadingMode === 'ghosted';
  const frameFor = (s) => {
    const [x, y, z] = toThree(s.x_ft, s.y_ft, s.z_top_ft, siteLengthFt);
    return { position: [x, y, z], rotation: [0, -(s.rotation_deg * Math.PI) / 180, 0], radius: s.radius_ft || 0.3 };
  };

  return (
    <>
      <Instances key={paddedCapacity(items.length)} limit={paddedCapacity(items.length)} range={items.length}>
        <cylinderGeometry args={[1, 1, 1, 6]} />
        <meshStandardMaterial {...materialProps(shadingMode, KIND_COLOR.steel_turnbuckle)} />
        {items.map((s, i) => {
          const f = frameFor(s);
          return <Instance key={i} position={f.position} rotation={f.rotation} scale={[f.radius, s.height_ft, f.radius]} />;
        })}
      </Instances>
      {ghosted && (
        <Instances key={`outline-${paddedCapacity(items.length)}`} limit={paddedCapacity(items.length)} range={items.length}>
          <cylinderGeometry args={[1, 1, 1, 6]} />
          <meshStandardMaterial {...outlineMaterialProps()} />
          {items.map((s, i) => {
            const f = frameFor(s);
            return (
              <Instance
                key={i}
                position={f.position}
                rotation={f.rotation}
                scale={[f.radius * OUTLINE_SCALE, s.height_ft * OUTLINE_SCALE, f.radius * OUTLINE_SCALE]}
              />
            );
          })}
        </Instances>
      )}
    </>
  );
}

function StructuralInstances({ specs, siteLengthFt, shadingMode }) {
  return (
    <>
      <BoxInstances specs={specs} siteLengthFt={siteLengthFt} shadingMode={shadingMode} />
      <CylinderInstances specs={specs} siteLengthFt={siteLengthFt} shadingMode={shadingMode} />
      <HexInstances specs={specs} siteLengthFt={siteLengthFt} shadingMode={shadingMode} />
    </>
  );
}

// TEMPORARY orientation-verification aid (2026-07-09) -- not a permanent
// feature, remove once orientation is confirmed against real Rhino/street
// data. Mirrors vector_export.py's STREET_LABELS/street_label_points()
// (OLIVE ST=x0, HILL ST=xmax, 5TH ST=ymax, 6TH ST=y0 in that module's
// site-local plan convention, whose "y" is this project's length axis --
// re-corrected 2026-07-09, see that module's own comment for why the
// 07-03 assignment had 5TH/6TH backwards) -- same edge-midpoint
// positions, just rendered in the live viewport instead of the offline
// DXF/SVG export. Billboard-wrapped so each label stays readable from
// every view mode (perspective/axo/plan/front/side), not just a top-down
// read.
const STREET_LABEL_MARGIN_FT = 30;
const STREET_LABEL_HEIGHT_FT = 8;

function StreetLabels({ siteWidthFt, siteLengthFt }) {
  const labels = [
    { text: 'OLIVE ST', x: -STREET_LABEL_MARGIN_FT, len: siteLengthFt / 2 },
    { text: 'HILL ST', x: siteWidthFt + STREET_LABEL_MARGIN_FT, len: siteLengthFt / 2 },
    { text: '6TH ST', x: siteWidthFt / 2, len: -STREET_LABEL_MARGIN_FT },
    { text: '5TH ST', x: siteWidthFt / 2, len: siteLengthFt + STREET_LABEL_MARGIN_FT },
  ];
  return (
    <>
      {labels.map(({ text, x, len }) => {
        const [px, py, pz] = toThree(x, len, STREET_LABEL_HEIGHT_FT, siteLengthFt);
        return (
          <Billboard key={text} position={[px, py, pz]}>
            <Text fontSize={16} color="#39ff88" anchorX="center" anchorY="middle" outlineWidth={0.6} outlineColor="#000000">
              {text}
            </Text>
          </Billboard>
        );
      })}
    </>
  );
}

export default function Viewport({
  data, networkSpecs, siteWidthFt, siteLengthFt, voxelFt, blenderObjUrl, blenderSvgUrl, onShowLineArt,
}) {
  const [shadingMode, setShadingMode] = useState('colored');
  const [viewMode, setViewMode] = useState('perspective');
  const [showBlenderBuild, setShowBlenderBuild] = useState(false);
  const canvasRef = useRef(null);
  // toThree()'s Z range is now [0, siteLengthFt] (fixed 2026-07-09, see
  // toThree's own comment) -- center must sit at the midpoint of THAT
  // range, not the old (buggy) [-siteLengthFt, 0] range's midpoint.
  const center = [siteWidthFt / 2, 0, siteLengthFt / 2];
  // Toggle only actually swaps the layer once a build exists -- with no
  // blenderObjUrl yet, always fall back to the live instanced view rather
  // than rendering nothing.
  const renderBlenderBuild = showBlenderBuild && !!blenderObjUrl;

  // Simple "export current view" -- whatever the camera is framing right
  // now (any preset, or wherever the user has orbited to) becomes a PNG,
  // same toDataURL() technique + preserveDrawingBuffer/alpha combo the
  // metabolizer prototype used for its transparent-bg export.
  const handleExport = useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const url = canvas.toDataURL('image/png');
    const a = document.createElement('a');
    a.href = url;
    a.download = `pershing-${viewMode}-${Date.now()}.png`;
    document.body.appendChild(a);
    a.click();
    a.remove();
  }, [viewMode]);

  return (
    <div className="flex-1 relative bg-background">
      <Canvas
        ref={canvasRef}
        gl={{ preserveDrawingBuffer: true, antialias: true, alpha: true }}
        onCreated={({ gl }) => {
          // Matches PershingMetabolizer_Prototype's renderer setup --
          // ACES tone mapping reads noticeably less flat/dark than the
          // default linear mapping, especially on the muted concrete/
          // steel tints this scene uses.
          gl.toneMapping = THREE.ACESFilmicToneMapping;
          gl.toneMappingExposure = 1.15;
        }}
      >
        <ViewCamera view={viewMode} center={center} siteWidthFt={siteWidthFt} siteLengthFt={siteLengthFt} />
        <OrbitControls key={viewMode} target={center} makeDefault />
        <ambientLight intensity={0.7} />
        <hemisphereLight args={['#cfe0f2', '#2a2f36', 0.9]} />
        <directionalLight position={[300, 400, 200]} intensity={1.8} />
        <directionalLight position={[-200, 200, -300]} intensity={0.7} color="#dde8ff" />
        {renderBlenderBuild ? (
          <BlenderBuild objUrl={blenderObjUrl} siteLengthFt={siteLengthFt} shadingMode={shadingMode} />
        ) : (
          <>
            {data && (
              <RealSlabs
                slabs={data.real_slabs}
                fragments={data.real_slab_fragments}
                voxelFt={voxelFt}
                siteLengthFt={siteLengthFt}
                shadingMode={shadingMode}
              />
            )}
            {data && (
              <RealColumns columns={data.real_columns} siteLengthFt={siteLengthFt} shadingMode={shadingMode} />
            )}
            {data && (
              <StructuralInstances specs={data.structural} siteLengthFt={siteLengthFt} shadingMode={shadingMode} />
            )}
            {data && (
              <GreenscapeGround
                voxels={data.voxels}
                voxelFt={voxelFt}
                siteLengthFt={siteLengthFt}
                shadingMode={shadingMode}
              />
            )}
            {data && (
              <CirculationSurface
                voxels={data.voxels}
                voxelFt={voxelFt}
                siteLengthFt={siteLengthFt}
                shadingMode={shadingMode}
              />
            )}
            {networkSpecs && (
              <StructuralInstances specs={networkSpecs} siteLengthFt={siteLengthFt} shadingMode={shadingMode} />
            )}
          </>
        )}
        <StaticContext siteLengthFt={siteLengthFt} shadingMode={shadingMode} />
        <StreetLabels siteWidthFt={siteWidthFt} siteLengthFt={siteLengthFt} />
      </Canvas>
      <div className="absolute top-4 left-4 flex gap-4">
        <div className="bg-surface/80 backdrop-blur-sm border border-border flex flex-col">
          <span className="text-on-surface-variant text-[10px] font-mono-sm px-3 pt-2">VIEW</span>
          <div className="flex">
            {Object.entries(VIEW_PRESETS).map(([key, p]) => (
              <button
                key={key}
                onClick={() => setViewMode(key)}
                className={`px-3 py-2 font-mono-sm text-mono-sm uppercase border-t border-border ${
                  viewMode === key ? 'text-accent bg-surface-container-high' : 'text-on-surface-variant hover:text-primary'
                }`}
              >
                {p.label}
              </button>
            ))}
          </div>
        </div>
        <div className="bg-surface/80 backdrop-blur-sm border border-border flex flex-col">
          <span className="text-on-surface-variant text-[10px] font-mono-sm px-3 pt-2">SHADING</span>
          <div className="flex">
            {SHADING_MODES.map((m) => (
              <button
                key={m.key}
                onClick={() => setShadingMode(m.key)}
                className={`px-3 py-2 font-mono-sm text-mono-sm uppercase border-t border-border ${
                  shadingMode === m.key ? 'text-accent bg-surface-container-high' : 'text-on-surface-variant hover:text-primary'
                }`}
              >
                {m.label}
              </button>
            ))}
          </div>
        </div>
        <button
          onClick={handleExport}
          className="bg-accent text-background px-4 py-2 font-mono-sm text-mono-sm font-bold uppercase tracking-widest self-start hover:brightness-110 transition-all active:scale-[0.98]"
        >
          Export PNG
        </button>
        {blenderObjUrl && (
          <button
            onClick={() => setShowBlenderBuild((v) => !v)}
            className={`px-4 py-2 font-mono-sm text-mono-sm font-bold uppercase tracking-widest self-start border transition-all active:scale-[0.98] ${
              showBlenderBuild ? 'bg-accent text-background border-accent' : 'border-accent text-accent hover:bg-accent hover:text-background'
            }`}
          >
            {showBlenderBuild ? 'Live View' : 'Blender Build'}
          </button>
        )}
        {blenderSvgUrl && (
          <button
            onClick={onShowLineArt}
            className="px-4 py-2 font-mono-sm text-mono-sm font-bold uppercase tracking-widest self-start border border-accent text-accent hover:bg-accent hover:text-background transition-all active:scale-[0.98]"
          >
            View Line Art
          </button>
        )}
      </div>
    </div>
  );
}
