import { useMemo, useRef, useLayoutEffect, useState, useCallback } from 'react';
import { Canvas, useThree } from '@react-three/fiber';
import { OrbitControls, Instances, Instance, PerspectiveCamera, OrthographicCamera, Text, Billboard, Line } from '@react-three/drei';
import * as THREE from 'three';
import StaticContext from './StaticContext.jsx';
import BlenderBuild from './BlenderBuild.jsx';
import { exportViewPng } from '../api.js';
import { materialProps, outlineMaterialProps, OUTLINE_SCALE, SHADING_MODES, showsOutline, castsShadows } from '../shading.js';
import KIND_REGISTRY from '../kindRegistry.json';
import PROGRAM_COLORS from '../programColors.json';
import { computeZones, pointInZone, clipStructuralSpec, clipRectBounds } from '../siteZones.js';

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
// 2026-07-16 Canopy Redesign -- flat individually-oriented panels
// (canopy_panel). Single-point like hex, but needs a full per-instance
// tilt (normal_x/y/z) that HEX_KINDS' single Y-axis rotation can't
// express -- see CanopyPanelInstances below.
const PANEL_KINDS = new Set(
  Object.entries(KIND_REGISTRY.kinds).filter(([, v]) => v.shape === 'panel').map(([k]) => k),
);
// Per-kind tint -- roughly matches the paint-category tints already
// established for Water/Trees (cyan) and Amenity/Resting (orange) so the
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

// Direction-only counterpart to toThree() (2026-07-16, Canopy Redesign) --
// for transforming a vector with no translation term (a surface normal),
// not a position. This is the exact coefficient-only reduction of
// toThree()'s formula: [x,y,z] -> [x, z, L-y] has a constant term (L) only
// in the z-slot; dropping that constant and keeping just the coefficients
// on (dx,dy,dz) gives [dx, dz, -dy]. Verified against toThree()'s own
// handedness bug history before use -- do not skip that verification if
// this is ever touched again, a normal transform is exactly the kind of
// position-vs-direction mismatch that bug class already hit once.
function toThreeDir(nx, ny, nz) {
  return [nx, nz, -ny];
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

// Thin colored cap on top of each matching voxel's own terrain height
// (v.z_ft, the same top-surface value TerraceLevelGroup builds its block up
// to) -- NOT a flat plane at z=0, since the terrain isn't flat once
// excavated; sitting the cap at v.z_ft keeps it following the cut terrace
// surface instead of floating above pits or clipping through them. One
// InstancedMesh of filtered voxels, same pattern TerraceLevelGroup uses.
// Extracted 2026-07-11 (was three near-identical copies -- greenscape grass,
// circulation surface, and this session's new trees ground cap -- the exact
// kind of duplication that already drove the PAINT_CATEGORIES/
// paintCategories.js extraction once this session).
//
// Risk note (carried over from the pre-extraction version, still applies):
// earlier this session RealSlabFragments had a real bug where a
// useLayoutEffect's dependency array didn't include a mode flag that
// changes which JSX element TYPE gets rendered (instancedMesh vs
// lineSegments for wireframe mode), causing a remount that silently failed
// to repopulate instance matrices. This component's effect already
// correctly lists every prop it reads (items/voxelFt/siteLengthFt/ghosted)
// and never swaps the primary mesh's element type based on shadingMode
// (only ghosted adds a SECOND outline mesh, it doesn't replace the first)
// -- if this component ever grows a wireframe-style branch that changes
// the primary element's JSX type, the mode flag driving that branch MUST
// be added to this dependency array, or it will silently break exactly the
// way RealSlabFragments did.
// 2026-07-12 fix ("voxel grid gets too cluttered"): CategoryGroundCap draws
// one box per matching voxel cell -- painted greenscape/trees/circulation
// cells can number in the hundreds, so this is the densest per-voxel
// tessellation in the scene. Ghosted mode's per-box outline pass added a
// fringe clutter around every cell, so that pass is dropped entirely below
// (not conditionally gated) for this layer only.
//
// 2026-07-17 (user report, "wireframe view isn't just wireframe"): this
// component used to also swap Wireframe's true-line style for a plain solid
// fill, on the same "too cluttered" reasoning -- but that meant ground caps
// silently rendered as SHADED even while the toggle read WIREFRAME. Wireframe
// mode is now real per-mode material like every other layer (materialProps
// below, no fillMode override); a busy grid of true wireframe boxes is the
// correct trade for a wireframe view actually being all-wireframe.
function CategoryGroundCap({ voxels, voxelFt, siteLengthFt, shadingMode, filterFn, color, thicknessFt }) {
  const meshRef = useRef();
  const items = useMemo(() => voxels.filter(filterFn), [voxels, filterFn]);

  useLayoutEffect(() => {
    if (!meshRef.current) return;
    const dummy = new THREE.Object3D();
    items.forEach((v, i) => {
      const cx = v.gx * voxelFt + voxelFt / 2;
      const cy = v.gy * voxelFt + voxelFt / 2;
      const cz = v.z_ft + thicknessFt / 2;
      const [x, y, z] = toThree(cx, cy, cz, siteLengthFt);
      dummy.position.set(x, y, z);
      dummy.scale.set(voxelFt, thicknessFt, voxelFt);
      dummy.updateMatrix();
      meshRef.current.setMatrixAt(i, dummy.matrix);
    });
    meshRef.current.instanceMatrix.needsUpdate = true;
  }, [items, voxelFt, siteLengthFt, thicknessFt]);

  if (items.length === 0) return null;

  const mat = materialProps(shadingMode, color);
  const shadows = castsShadows(shadingMode);
  return (
    <instancedMesh ref={meshRef} args={[undefined, undefined, items.length]} castShadow={shadows} receiveShadow={shadows}>
      <boxGeometry args={[1, 1, 1]} />
      <meshStandardMaterial {...mat} />
    </instancedMesh>
  );
}

// Placeholder solid colors for now (hybrid asset strategy: cheap now, swap
// for real grass/paving textures later without touching data plumbing --
// is_greenscape/is_tree are already real per-voxel data from the paint
// masks, not derived here).
const GREENSCAPE_COLOR = '#3d9142';
const GREENSCAPE_THICKNESS_FT = 0.5;
const greenscapeFilter = (v) => v.is_greenscape;

function GreenscapeGround(props) {
  return <CategoryGroundCap {...props} filterFn={greenscapeFilter} color={GREENSCAPE_COLOR} thicknessFt={GREENSCAPE_THICKNESS_FT} />;
}

// Trees ground cap (2026-07-11, new; category renamed from "shade" to
// "trees" 2026-07-16) -- tan/beige, matches the paint brush's trees tint
// (paintCategories.js) and the legacy diagram tool's ZONE_MATERIALS.SHADE.
// is_tree (was is_shade) is what drives actual tree placement too
// (TypologyAssetEngine.tree_specs, moved off is_greenscape) -- this ground
// cap is the "trees paint has a visible footprint even before the trees
// themselves render" counterpart, same role GreenscapeGround already
// plays for grass.
const TREE_COLOR = '#bcaaa4';
const TREE_THICKNESS_FT = 0.5;
const treeFilter = (v) => v.is_tree;

function TreeGround(props) {
  return <CategoryGroundCap {...props} filterFn={treeFilter} color={TREE_COLOR} thicknessFt={TREE_THICKNESS_FT} />;
}

// Filtered by v.typology === 'CIRCULATION' (server-classified: hardscape
// cells where the foot-traffic influence field crosses circulation_threshold
// -- see terracing_engine.py's _classify_typology) instead of a raw boolean
// mask. Gives HARDSCAPE_MASK its first visual identity in this viewport --
// previously invisible, only ever an excavation veto.
const CIRCULATION_COLOR = '#8a8378';
const CIRCULATION_THICKNESS_FT = 0.5;
const circulationFilter = (v) => v.typology === 'CIRCULATION';

function CirculationSurface(props) {
  return <CategoryGroundCap {...props} filterFn={circulationFilter} color={CIRCULATION_COLOR} thicknessFt={CIRCULATION_THICKNESS_FT} />;
}

// Canopy Engine glass overlay (2026-07-13) -- SUPERSEDED, kept for
// reference only, not currently mounted anywhere in this file (disabled
// 2026-07-13 for occluding Program Zone labels; the 2026-07-16 Canopy
// Redesign replaced this whole feature with CanopyPanelInstances' faceted
// panels + branching supports, which was the explicit design goal --
// individually-oriented panels, not a smooth continuous surface -- so this
// isn't "pending re-enable," just preserved as the right technique
// precedent for a possible future smooth-glass variant. If ever revived,
// read canopyResult.canopy_height_matrix (the explicit-action response),
// NOT data.canopy_height_matrix -- canopy no longer runs inside rebuild()
// at all, see App.jsx's handleGenerateCanopy. Still a continuous nx x nz
// heightfield technique, NOT a per-voxel box like CategoryGroundCap above:
// one BufferGeometry vertex per grid point, triangulated as a regular
// grid, same technique RealSlabPlate uses (position attribute + explicit
// index array + computeVertexNormals), generalized from one quad's 8
// verts to a full nx*nz surface. Punctures (punctureMask[gx][gy]) skip
// both triangles for that cell -- a real hole, not a post-hoc deletion pass.
function CanopyOverlay({ heightMatrix, punctureMask, voxelFt, siteLengthFt }) {
  const geometry = useMemo(() => {
    const nx = heightMatrix.length;
    const nz = nx > 0 ? heightMatrix[0].length : 0;

    const positions = new Array(nx * nz * 3);
    for (let gx = 0; gx < nx; gx++) {
      for (let gy = 0; gy < nz; gy++) {
        const cx = gx * voxelFt + voxelFt / 2;
        const cy = gy * voxelFt + voxelFt / 2;
        const [x, y, z] = toThree(cx, cy, heightMatrix[gx][gy], siteLengthFt);
        const i = (gx * nz + gy) * 3;
        positions[i] = x;
        positions[i + 1] = y;
        positions[i + 2] = z;
      }
    }

    const indices = [];
    for (let gx = 0; gx < nx - 1; gx++) {
      for (let gy = 0; gy < nz - 1; gy++) {
        if (punctureMask?.[gx]?.[gy]) continue;
        const a = gx * nz + gy;
        const b = (gx + 1) * nz + gy;
        const c = (gx + 1) * nz + (gy + 1);
        const d = gx * nz + (gy + 1);
        indices.push(a, b, c, a, c, d);
      }
    }

    const geo = new THREE.BufferGeometry();
    geo.setAttribute('position', new THREE.Float32BufferAttribute(positions, 3));
    geo.setIndex(indices);
    geo.computeVertexNormals();
    return geo;
  }, [heightMatrix, punctureMask, voxelFt, siteLengthFt]);

  // First use of meshPhysicalMaterial/transmission in this codebase --
  // deliberately NOT routed through shading.js's materialProps() (which only
  // targets meshStandardMaterial's roughness/metalness/color/transparent
  // shape); this is a fixed "architectural glass" treatment, not wired into
  // the wireframe/ghosted/arctic shading-mode branching yet (follow-up).
  return (
    <mesh geometry={geometry}>
      <meshPhysicalMaterial
        color="#dfeff2"
        roughness={0.05}
        transmission={0.9}
        thickness={0.5}
        transparent
        side={THREE.DoubleSide}
      />
    </mesh>
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

  const ghosted = showsOutline(shadingMode);
  const shadows = castsShadows(shadingMode);
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
      <Instances
        key={paddedCapacity(frames.length)}
        limit={paddedCapacity(frames.length)}
        range={frames.length}
        castShadow={shadows}
        receiveShadow={shadows}
      >
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
  const ghosted = showsOutline(shadingMode);
  const wireframe = shadingMode === 'wireframe';

  const { geometry, outlineGeometry, edgesGeometry } = useMemo(() => {
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
    // Wireframe mode (2026-07-10 fix): a plain `wireframe: true` material
    // draws EVERY triangle edge, including the internal diagonal each flat
    // quad face gets split by for rendering (top/bottom/every side face
    // here is a quad, per SLAB_PLATE_INDICES) -- reads as a spurious extra
    // line cutting across every face, not a real edge of the slab.
    // THREE.EdgesGeometry only keeps edges where adjacent faces meet at a
    // real angle (default threshold 1deg) -- a flat quad's two triangles
    // are coplanar at their shared diagonal, so it's correctly dropped,
    // leaving just the slab's true outline.
    const edgesGeo = wireframe ? new THREE.EdgesGeometry(geo) : null;
    return { geometry: geo, outlineGeometry: outlineGeo, edgesGeometry: edgesGeo };
  }, [slab, siteLengthFt, ghosted, wireframe]);

  const mat = materialProps(shadingMode, SLAB_KIND_COLOR[slab.kind] || '#aaaaaa');
  const shadows = castsShadows(shadingMode);

  if (wireframe && edgesGeometry) {
    return (
      <lineSegments geometry={edgesGeometry}>
        <lineBasicMaterial color={SLAB_KIND_COLOR[slab.kind] || '#aaaaaa'} />
      </lineSegments>
    );
  }

  return (
    <>
      <mesh geometry={geometry} castShadow={shadows} receiveShadow={shadows}>
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

// 2026-07-12 fix ("voxel grid gets too cluttered"): like CategoryGroundCap
// above, this is a dense per-voxel tessellation (one box per surviving real
// slab cell, potentially thousands before the canyon cuts through). Ghosted
// mode's per-box outline pass is dropped entirely for this layer (same
// clutter reasoning as CategoryGroundCap).
//
// 2026-07-17 (user report, "wireframe view isn't just wireframe"): this used
// to also swap Wireframe's true-line style for a solid fill, same as
// CategoryGroundCap -- meaning real slab remnants silently rendered SHADED
// under the WIREFRAME toggle. Reverted to real per-mode material
// (materialProps below, no fillMode override) so Wireframe mode is actually
// all wireframe; see CategoryGroundCap's comment for the same fix.
function RealSlabFragments({ slab, remaining, voxelFt, siteLengthFt, shadingMode }) {
  const meshRef = useRef();

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
    });
    meshRef.current.instanceMatrix.needsUpdate = true;
  }, [remaining, voxelFt, slab, siteLengthFt]);

  if (remaining.length === 0) return null;

  const mat = materialProps(shadingMode, SLAB_KIND_COLOR[slab.kind] || '#aaaaaa');
  const shadows = castsShadows(shadingMode);
  return (
    <instancedMesh ref={meshRef} args={[undefined, undefined, remaining.length]} castShadow={shadows} receiveShadow={shadows}>
      <boxGeometry args={[1, 1, 1]} />
      <meshStandardMaterial {...mat} />
    </instancedMesh>
  );
}

// Top-slab toggle (2026-07-12, user request): "the top slab" is just
// whichever real slab sits at the highest z_top_ft -- in the current
// real_geometry.json that's "new_grade_slab" (z_top_ft=0.25, the new plaza-
// grade deck), sitting above every L1/L2/L3 parking-structure slab below it
// (all z_top_ft <= 0). Computed generically off the live data (max
// z_top_ft) rather than hardcoding the "new_grade_slab" parent name, so it
// still tracks correctly if the Rhino source ever renames/re-levels it.
// Hiding it is what lets the terracing/voxel cuts underneath actually be
// seen instead of being capped by the intact surface slab.
function RealSlabs({ slabs, fragments, voxelFt, siteLengthFt, shadingMode, showTopSlab }) {
  if (!slabs || slabs.length === 0) return null;
  const topZ = Math.max(...slabs.map((s) => s.z_top_ft));
  return (
    <>
      {slabs.map((slab) => {
        if (!showTopSlab && slab.z_top_ft === topZ) return null;
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

// Salvaged material (harvested_block_specs() re-instancing removed real
// slab area) -- see showSalvage's own comment in the main Viewport
// component for why this is filterable/off by default.
const SALVAGE_KINDS = new Set(['concrete_floor_block', 'concrete_retaining_block']);

function BoxInstances({ specs, siteLengthFt, shadingMode, showSalvage }) {
  const ghosted = showsOutline(shadingMode);
  const shadows = castsShadows(shadingMode);
  // Grouping key (2026-07-16 program_boxes per-program coloring): boxes
  // tagged with a program_item (rebuild()'s program_box_specs -- one
  // building_mass box per claimed bay) group and color per PROGRAM (same
  // PROGRAM_COLOR map ProgramZoneFootprint already uses below), not per
  // kind -- every program box shares the one building_mass kind, so
  // grouping by kind alone would still paint them all one shared color.
  // Every other BoxInstances consumer (salvage, etc.) has no program_item
  // and keeps the original per-kind grouping/coloring.
  const byGroup = useMemo(() => {
    const map = {};
    for (const s of specs) {
      if (s.x2_ft !== null || HEX_KINDS.has(s.kind) || VERTICAL_CYLINDER_KINDS.has(s.kind)) continue;
      if (!showSalvage && SALVAGE_KINDS.has(s.kind)) continue;
      const groupKey = s.program_item ? `program:${s.program_item}` : s.kind;
      (map[groupKey] ||= { kind: s.kind, programItem: s.program_item, items: [] }).items.push(s);
    }
    return map;
  }, [specs, showSalvage]);

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
      {Object.entries(byGroup).map(([groupKey, group]) => {
        const color = group.programItem
          ? (PROGRAM_COLOR[group.programItem] || PROGRAM_FALLBACK_COLOR)
          : (KIND_COLOR[group.kind] || '#888888');
        return (
          <Instances
            key={`${groupKey}-${paddedCapacity(group.items.length)}`}
            limit={paddedCapacity(group.items.length)}
            range={group.items.length}
            castShadow={shadows}
            receiveShadow={shadows}
          >
            <boxGeometry args={[1, 1, 1]} />
            <meshStandardMaterial {...materialProps(shadingMode, color)} />
            {group.items.map((s, i) => {
              const f = frameFor(group.kind, s);
              return <Instance key={i} position={f.position} rotation={f.rotation} scale={[f.sx, f.sz, f.sy]} />;
            })}
          </Instances>
        );
      })}
      {ghosted && Object.entries(byGroup).map(([groupKey, group]) => (
        <Instances key={`${groupKey}-outline-${paddedCapacity(group.items.length)}`} limit={paddedCapacity(group.items.length)} range={group.items.length}>
          <boxGeometry args={[1, 1, 1]} />
          <meshStandardMaterial {...outlineMaterialProps()} />
          {group.items.map((s, i) => {
            const f = frameFor(group.kind, s);
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

// Circulation path kinds (2026-07-13) -- footpath/ramp/escalator and their
// _bridge variants render as flat, slightly-thickened ribbons (RibbonInstances
// below) instead of round cylinders: these are walkable path surfaces, not
// structural rods, so a round "tree branch" cross-section read wrong. Kept
// as an explicit kind set (not e.g. "everything with x2_ft"), since
// steel_strut/steel_tie_rod/knee_brace/timber_beam are also two-point but
// ARE genuinely round members and should stay cylinders.
const CIRCULATION_PATH_KINDS = new Set([
  'footpath', 'ramp', 'escalator', 'footpath_bridge', 'ramp_bridge', 'escalator_bridge',
]);
// Ribbon cross-section thickness (vertical) -- "slightly thickened" per
// design request, not a paper-thin plane. Width comes from each spec's own
// radius_ft (flow-scaled path width, same field CylinderInstances used for
// tube radius before this split), just applied as a flat rectangle instead.
const PATH_THICKNESS_FT = 0.5;

// Round cylinders: two-point specs (steel_strut, steel_tie_rod,
// knee_brace, timber_beam -- anything with x2_ft set, matching Python's
// "if spec.x2_ft is not None" check, not a kind-name allowlist -- EXCEPT
// CIRCULATION_PATH_KINDS, see RibbonInstances below) plus the single-point
// "vertical cylinder" kinds (steel_bolt, bolt_flange_plate), whose
// endpoints Python derives as (x,y,z_top-height) -> (x,y,z_top). One unit
// cylinder (radius=1, height=1) scaled/rotated per instance -- same trick
// TerraceVoxels/BoxInstances use for boxes.
function CylinderInstances({ specs, siteLengthFt, shadingMode }) {
  const ghosted = showsOutline(shadingMode);
  const shadows = castsShadows(shadingMode);
  const grouped = useMemo(() => {
    const map = {};
    for (const s of specs) {
      let p0, p1;
      if (s.x2_ft !== null) {
        if (CIRCULATION_PATH_KINDS.has(s.kind)) continue; // rendered as a flat ribbon instead
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
        <Instances
          key={`${kind}-${paddedCapacity(items.length)}`}
          limit={paddedCapacity(items.length)}
          range={items.length}
          castShadow={shadows}
          receiveShadow={shadows}
        >
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

// Flat, slightly-thickened ribbons for CIRCULATION_PATH_KINDS (footpath/
// ramp/escalator + _bridge variants) -- same two-point grouping as
// CylinderInstances above, but builds a proper (right, thickness, forward)
// orthonormal basis instead of a single quaternion-from-vectors trick
// (which only fixes a cylinder's symmetric long axis, not a box's twist/
// roll around it). `ref` mirrors blender/pershing_headless_build.py's
// _add_cylinder basis choice exactly (world-up unless the segment is
// nearly vertical, then fall back to world-X) so a live-viewport ramp and
// its Blender-exported twin tilt the same way. Width comes from radius_ft
// (the same flow-scaled field CylinderInstances used for tube radius);
// thickness is the fixed PATH_THICKNESS_FT constant above.
function RibbonInstances({ specs, siteLengthFt, shadingMode }) {
  const ghosted = showsOutline(shadingMode);
  const shadows = castsShadows(shadingMode);
  const grouped = useMemo(() => {
    const map = {};
    for (const s of specs) {
      if (s.x2_ft === null || !CIRCULATION_PATH_KINDS.has(s.kind)) continue;
      const p0 = toThree(s.x_ft, s.y_ft, s.z_top_ft, siteLengthFt);
      const p1 = toThree(s.x2_ft, s.y2_ft, s.z2_ft, siteLengthFt);
      (map[s.kind] ||= []).push({ p0, p1, width: (s.radius_ft || 0.2) * 2 });
    }
    return map;
  }, [specs, siteLengthFt]);

  const framesFor = (items) => items.map(({ p0, p1, width }) => {
    const a = new THREE.Vector3(...p0);
    const b = new THREE.Vector3(...p1);
    const mid = a.clone().add(b).multiplyScalar(0.5);
    const forward = b.clone().sub(a);
    const length = forward.length();
    if (length < 1e-6) return null;
    forward.normalize();
    const worldUp = new THREE.Vector3(0, 1, 0);
    const ref = Math.abs(forward.y) < 0.9 ? worldUp : new THREE.Vector3(1, 0, 0);
    const u = new THREE.Vector3().crossVectors(ref, forward).normalize();
    const v = new THREE.Vector3().crossVectors(forward, u).normalize();
    const basis = new THREE.Matrix4().makeBasis(u, v, forward);
    const quat = new THREE.Quaternion().setFromRotationMatrix(basis);
    return { position: mid.toArray(), quaternion: quat.toArray(), width, length };
  }).filter(Boolean);

  return (
    <>
      {Object.entries(grouped).map(([kind, items]) => (
        <Instances
          key={`${kind}-ribbon-${paddedCapacity(items.length)}`}
          limit={paddedCapacity(items.length)}
          range={items.length}
          castShadow={shadows}
          receiveShadow={shadows}
        >
          <boxGeometry args={[1, 1, 1]} />
          <meshStandardMaterial {...materialProps(shadingMode, KIND_COLOR[kind] || '#888888')} />
          {framesFor(items).map(({ position, quaternion, width, length }, i) => (
            <Instance key={i} position={position} quaternion={quaternion} scale={[width, PATH_THICKNESS_FT, length]} />
          ))}
        </Instances>
      ))}
      {ghosted && Object.entries(grouped).map(([kind, items]) => (
        <Instances key={`${kind}-ribbon-outline-${paddedCapacity(items.length)}`} limit={paddedCapacity(items.length)} range={items.length}>
          <boxGeometry args={[1, 1, 1]} />
          <meshStandardMaterial {...outlineMaterialProps()} />
          {framesFor(items).map(({ position, quaternion, width, length }, i) => (
            <Instance
              key={i}
              position={position}
              quaternion={quaternion}
              scale={[width * OUTLINE_SCALE, PATH_THICKNESS_FT * OUTLINE_SCALE, length * OUTLINE_SCALE]}
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
  // Grouped by kind (2026-07-13 fix, mirrors BoxInstances' byKind pattern
  // above) -- previously ALL hex kinds shared one <Instances> block with a
  // single hardcoded KIND_COLOR.steel_turnbuckle material, so tree_canopy
  // (the only other hex kind) silently rendered in steel_turnbuckle's grey
  // instead of its own color, old or new.
  const byKind = useMemo(() => {
    const map = {};
    for (const s of specs) {
      if (!HEX_KINDS.has(s.kind) || s.x2_ft !== null) continue;
      (map[s.kind] ||= []).push(s);
    }
    return map;
  }, [specs]);
  const items = useMemo(
    () => specs.filter((s) => HEX_KINDS.has(s.kind) && s.x2_ft === null),
    [specs],
  );
  if (items.length === 0) return null;

  const ghosted = showsOutline(shadingMode);
  const shadows = castsShadows(shadingMode);
  const frameFor = (s) => {
    const [x, y, z] = toThree(s.x_ft, s.y_ft, s.z_top_ft, siteLengthFt);
    return { position: [x, y, z], rotation: [0, -(s.rotation_deg * Math.PI) / 180, 0], radius: s.radius_ft || 0.3 };
  };

  return (
    <>
      {Object.entries(byKind).map(([kind, kindItems]) => (
        <Instances
          key={`${kind}-${paddedCapacity(kindItems.length)}`}
          limit={paddedCapacity(kindItems.length)}
          range={kindItems.length}
          castShadow={shadows}
          receiveShadow={shadows}
        >
          <cylinderGeometry args={[1, 1, 1, 6]} />
          <meshStandardMaterial {...materialProps(shadingMode, KIND_COLOR[kind])} />
          {kindItems.map((s, i) => {
            const f = frameFor(s);
            return <Instance key={i} position={f.position} rotation={f.rotation} scale={[f.radius, s.height_ft, f.radius]} />;
          })}
        </Instances>
      ))}
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

// Individually-oriented flat panels (canopy_panel) -- 2026-07-16 Canopy
// Redesign. Modeled on RibbonInstances' basis-construction above (a
// panel's orientation needs a full 3D basis pinned to its surface normal,
// not just a single-axis rotation like HexInstances) -- same worldUp/
// worldX fallback rule (0.9 dot-product threshold), so a live-viewport
// panel and its Blender-exported twin tilt the same way (see
// blender_cockpit.py's _add_panel). makeBasis(u, v, normal) puts the
// normal on the box's local Z axis, so scale=[width, depth, thickness]
// (scale/scale_y/height_ft) lines up with (u, v, normal) exactly. Box
// geometry, not a plane, so panels get real thickness and a correct
// outline pass in Ghosted mode like every other kind. NOT part of
// StructuralInstances below -- panels come from their own explicit-action
// response (canopyResult), not data.structural, see Viewport's main
// render tree.
function CanopyPanelInstances({ specs, siteLengthFt, shadingMode }) {
  const items = useMemo(
    () => specs.filter((s) => PANEL_KINDS.has(s.kind)),
    [specs],
  );

  const frames = useMemo(() => items.map((s) => {
    const position = toThree(s.x_ft, s.y_ft, s.z_top_ft, siteLengthFt);
    const [nx_, ny_, nz_] = toThreeDir(s.normal_x, s.normal_y, s.normal_z);
    const normal = new THREE.Vector3(nx_, ny_, nz_).normalize();
    const worldUp = new THREE.Vector3(0, 1, 0);
    const ref = Math.abs(normal.y) < 0.9 ? worldUp : new THREE.Vector3(1, 0, 0);
    const u = new THREE.Vector3().crossVectors(ref, normal).normalize();
    // In-plane spin around the normal (2026-07-24, site_grid panel
    // faceting) -- rotation_deg is otherwise unused by panel-shape kinds
    // (only the tilt from normal_x/y/z mattered before), so this is the one
    // place the panel-grid rotation dialed in on the ParamPanel slider
    // actually reorients the visible seams, not just the tilt. Mirrors
    // blender_cockpit.py/pershing_headless_build.py's _add_panel.
    if (s.rotation_deg) {
      u.applyAxisAngle(normal, (s.rotation_deg * Math.PI) / 180);
    }
    const v = new THREE.Vector3().crossVectors(normal, u).normalize();
    const basis = new THREE.Matrix4().makeBasis(u, v, normal);
    const quaternion = new THREE.Quaternion().setFromRotationMatrix(basis).toArray();
    const scale = [s.scale, s.scale_y ?? s.scale, s.height_ft];
    return { position, quaternion, scale };
  }), [items, siteLengthFt]);

  if (items.length === 0) return null;

  const ghosted = showsOutline(shadingMode);
  const shadows = castsShadows(shadingMode);

  return (
    <>
      <Instances
        key={`canopy_panel-${paddedCapacity(items.length)}`}
        limit={paddedCapacity(items.length)}
        range={items.length}
        castShadow={shadows}
        receiveShadow={shadows}
      >
        <boxGeometry args={[1, 1, 1]} />
        <meshStandardMaterial {...materialProps(shadingMode, KIND_COLOR.canopy_panel)} />
        {frames.map(({ position, quaternion, scale }, i) => (
          <Instance key={i} position={position} quaternion={quaternion} scale={scale} />
        ))}
      </Instances>
      {ghosted && (
        <Instances
          key={`canopy_panel-outline-${paddedCapacity(items.length)}`}
          limit={paddedCapacity(items.length)}
          range={items.length}
        >
          <boxGeometry args={[1, 1, 1]} />
          <meshStandardMaterial {...outlineMaterialProps()} />
          {frames.map(({ position, quaternion, scale }, i) => (
            <Instance
              key={i}
              position={position}
              quaternion={quaternion}
              scale={[scale[0] * OUTLINE_SCALE, scale[1] * OUTLINE_SCALE, scale[2] * OUTLINE_SCALE]}
            />
          ))}
        </Instances>
      )}
    </>
  );
}

function StructuralInstances({ specs, siteLengthFt, shadingMode, showSalvage }) {
  return (
    <>
      <BoxInstances specs={specs} siteLengthFt={siteLengthFt} shadingMode={shadingMode} showSalvage={showSalvage} />
      <CylinderInstances specs={specs} siteLengthFt={siteLengthFt} shadingMode={shadingMode} />
      <RibbonInstances specs={specs} siteLengthFt={siteLengthFt} shadingMode={shadingMode} />
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

// Bay-grid program placement (logic/program_placement.py, via
// GET /api/pershing/program-zones) -- one translucent footprint per claimed
// bay plus a billboard label per program, same instancedMesh-per-group
// pattern as CategoryGroundCap above, just keyed on bay (gx, gy) at
// STRUCTURAL_BAY_FT resolution instead of voxel (gx, gy). Placeholder solid
// colors per category, same "cheap now, swap for real assets later" posture
// as GREENSCAPE_COLOR above -- these categories don't (yet) exist in
// kindRegistry.json since they're program zones, not structural/typology
// kinds.
const PROGRAM_ZONE_THICKNESS_FT = 1.0;
const PROGRAM_ZONE_LABEL_HEIGHT_FT = 12;
// Per-PROGRAM colors (2026-07-13), replacing the old 5-entry per-CATEGORY
// map -- with only 5 colors for 13-14 individual programs, every
// sports_recreation zone (Soccer Field/Public Gym/Skatepark/Volleyball
// Court) rendered in the exact same orange, indistinguishable from each
// other except by (often overlapping) text labels. Keyed by program_item
// (the label string place_programs() returns and ProgramZones already uses
// as its React key -- no new identifier needed).
//
// Moved into programColors.json 2026-07-28: this map had been hand-copied
// into drawing_styles.py and DiagnosticsPanel.jsx, three copies to keep in
// sync by hand. Same consolidation kindRegistry.json already did for
// structural kinds -- see that file's _palette_rationale for the hue-family
// grouping and the orange/amber/beige colors it deliberately avoids.
const PROGRAM_COLOR = PROGRAM_COLORS.programs;
const PROGRAM_FALLBACK_COLOR = PROGRAM_COLORS.fallback;

function ProgramZoneFootprint({ bays, bayFt, color, siteLengthFt, shadingMode }) {
  const meshRef = useRef();

  useLayoutEffect(() => {
    if (!meshRef.current) return;
    const dummy = new THREE.Object3D();
    bays.forEach(([gx, gy, elevFt], i) => {
      // gx/gy here are BAY indices (STRUCTURAL_BAY_FT-wide cells), not voxel
      // indices -- do not reuse voxelFt here despite the visual similarity
      // to CategoryGroundCap above.
      const cx = (gx + 0.5) * bayFt;
      const cy = (gy + 0.5) * bayFt;
      // Per-bay floor elevation (2026-07-13 "use all available space"
      // update): a zone can now legitimately span more than one real
      // elevation (see logic/program_placement.py's place_programs()
      // docstring), so each bay renders at ITS OWN floor_elev_ft instead
      // of one shared value for the whole zone. `?? 0` covers a bay entry
      // that predates this field ([gx, gy] only).
      const [x, y, z] = toThree(cx, cy, (elevFt ?? 0) + PROGRAM_ZONE_THICKNESS_FT / 2, siteLengthFt);
      dummy.position.set(x, y, z);
      dummy.scale.set(bayFt, PROGRAM_ZONE_THICKNESS_FT, bayFt);
      dummy.updateMatrix();
      meshRef.current.setMatrixAt(i, dummy.matrix);
    });
    meshRef.current.instanceMatrix.needsUpdate = true;
  }, [bays, bayFt, siteLengthFt]);

  if (bays.length === 0) return null;

  const mat = materialProps(shadingMode, color);
  const shadows = castsShadows(shadingMode);
  return (
    <instancedMesh ref={meshRef} args={[undefined, undefined, bays.length]} castShadow={shadows} receiveShadow={shadows}>
      <boxGeometry args={[1, 1, 1]} />
      <meshStandardMaterial {...mat} />
    </instancedMesh>
  );
}

// Major/minor attractor markers (2026-07-16 program-placement correlation
// logic) -- small spheres at data.attractor_points' positions, purely a
// debug/verification visualization for the new proximity scoring in
// logic/program_placement.py (see CATEGORY_ATTRACTOR_AFFINITY there), NOT
// the future discrete-3D-asset-library feature the original 2026-07-14
// design comment scoped separately (a pavilion/tennis-court model swap is
// out of scope here). No z_ft on these points (2D-SVG-derived plan
// positions only) -- rests each sphere on grade at its own radius, same
// "cheap now, swap for a real asset later" posture as GREENSCAPE_COLOR
// above. amphitheatre points are persisted but not rendered here (not
// scored either, see _bay_grid_from_engine()'s docstring).
const ATTRACTOR_MARKER_COLOR = { major_attractor: '#ffd54f', minor_attractor: '#b0bec5' };
const ATTRACTOR_MARKER_RADIUS_FT = { major_attractor: 6, minor_attractor: 4 };

function AttractorMarkers({ points, siteLengthFt, shadingMode }) {
  const shadows = castsShadows(shadingMode);
  return (
    <>
      {['major_attractor', 'minor_attractor'].map((cat) => {
        const pts = points?.[cat] || [];
        if (pts.length === 0) return null;
        const radius = ATTRACTOR_MARKER_RADIUS_FT[cat];
        return (
          <Instances
            key={`${cat}-${paddedCapacity(pts.length)}`}
            limit={paddedCapacity(pts.length)}
            range={pts.length}
            castShadow={shadows}
            receiveShadow={shadows}
          >
            <sphereGeometry args={[radius, 12, 12]} />
            <meshStandardMaterial {...materialProps(shadingMode, ATTRACTOR_MARKER_COLOR[cat])} />
            {pts.map((p, i) => {
              const [x, y, z] = toThree(p.x_ft, p.y_ft, radius, siteLengthFt);
              return <Instance key={i} position={[x, y, z]} />;
            })}
          </Instances>
        );
      })}
    </>
  );
}

// showFootprint (2026-07-16): the flat-plane footprint and the "Program
// Boxes" extrusion (BoxInstances over data.program_boxes, rendered as a
// sibling in the main tree below) are the SAME program-zone data in two
// mutually-exclusive render modes, not two independently-stackable layers
// -- the "Program Boxes" toggle just swaps which one shows, same zones
// either way. Labels stay on regardless of which geometry mode is active.
function ProgramZones({ zones, bayFt, siteLengthFt, shadingMode, showLabels = true, showFootprint = true }) {
  if (!zones || !bayFt) return null;
  const placedZones = zones.filter((z) => z.bays.length > 0);
  return (
    <>
      {placedZones.map((zone) => {
        const color = PROGRAM_COLOR[zone.program_item] || PROGRAM_FALLBACK_COLOR;
        const centroidGx = zone.bays.reduce((sum, [gx]) => sum + gx, 0) / zone.bays.length;
        const centroidGy = zone.bays.reduce((sum, [, gy]) => sum + gy, 0) / zone.bays.length;
        const labelX = (centroidGx + 0.5) * bayFt;
        const labelY = (centroidGy + 0.5) * bayFt;
        // floor_elev_ft (2026-07-13 "remove top slab" feature): the real
        // surface this zone sits on -- 0 (grade) if the API response
        // predates this field. Label floats the same fixed height above
        // whatever that floor actually is, not above absolute 0.
        const floorElevFt = zone.floor_elev_ft ?? 0;
        const [px, py, pz] = toThree(labelX, labelY, floorElevFt + PROGRAM_ZONE_LABEL_HEIGHT_FT, siteLengthFt);
        return (
          <group key={zone.program_item}>
            {showFootprint && (
              <ProgramZoneFootprint
                bays={zone.bays} bayFt={bayFt} color={color}
                siteLengthFt={siteLengthFt} shadingMode={shadingMode}
              />
            )}
            {showLabels && (
              <Billboard position={[px, py, pz]}>
                <Text fontSize={10} color={color} anchorX="center" anchorY="middle" outlineWidth={0.4} outlineColor="#000000">
                  {zone.program_item}{zone.fulfilled ? '' : ' (partial)'}
                </Text>
              </Billboard>
            )}
          </group>
        );
      })}
    </>
  );
}

// Plain HTML/CSS overlay (2026-07-13), NOT inside <Canvas> -- the 3D
// billboard labels ProgramZones already draws stay useful for spatial
// reference, but visibly overlap/clip in a dense layout (confirmed live),
// so program names aren't reliably readable from the viewport alone. This
// is the guaranteed-legible list: every currently-placed program's name
// with its actual PROGRAM_COLOR swatch, same corner-panel visual style as
// the VIEW/SHADING/TOP SLAB HUD panels below.
function ProgramLegend({ zones }) {
  // Collapsed by default state is local/UI-only (2026-07-17) -- purely a
  // display convenience, not design data, so it doesn't need to be lifted
  // to App.jsx/visibleLayers like the real layer toggles.
  const [collapsed, setCollapsed] = useState(false);
  if (!zones) return null;
  const placedZones = zones.filter((z) => z.bays.length > 0);
  if (placedZones.length === 0) return null;
  return (
    <div className="bg-surface/80 backdrop-blur-sm border border-border rounded-lg flex flex-col max-h-[70vh] overflow-y-auto">
      <button
        onClick={() => setCollapsed((c) => !c)}
        className="flex items-center justify-between gap-3 px-3 pt-2 pb-1 text-on-surface-variant hover:text-on-surface"
      >
        <span className="text-[10px] font-mono-sm">PROGRAMS</span>
        <span className="text-[10px] font-mono-sm">{collapsed ? '+' : '−'}</span>
      </button>
      {!collapsed && (
        <div className="flex flex-col px-3 pb-2 gap-1">
          {placedZones.map((zone) => (
            <div key={zone.program_item} className="flex items-center gap-2">
              <span
                className="w-3 h-3 shrink-0 border border-border"
                style={{ backgroundColor: PROGRAM_COLOR[zone.program_item] || PROGRAM_FALLBACK_COLOR }}
              />
              <span className="font-mono-sm text-[11px] text-on-surface-variant whitespace-nowrap">
                {zone.program_item}{zone.fulfilled ? '' : ' (partial)'}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// Site-chunk export overlay (2026-07-23) -- 9 zones (3x3, see siteZones.js)
// drawn as a hoverable/clickable red-outlined grid over the
// ground plane. Each zone is a flat hit-plane (for pointer events) plus a
// closed red line loop (the actual visible boundary) -- kept as two
// separate meshes rather than one, since a transparent fill mesh alone
// reads too subtly as "a grid" until you're already hovering it.
function ZoneGrid({ zones, siteLengthFt, hoveredZone, selectedZone, onHover, onSelect }) {
  return (
    <group>
      {zones.map((zone) => {
        const isSelected = selectedZone === zone.id;
        const isHovered = hoveredZone === zone.id;
        const cx = (zone.xMin + zone.xMax) / 2;
        const cy = (zone.yMin + zone.yMax) / 2;
        const w = zone.xMax - zone.xMin;
        const h = zone.yMax - zone.yMin;
        const [x, y, z] = toThree(cx, cy, 0.5, siteLengthFt);
        const corners = [
          toThree(zone.xMin, zone.yMin, 0.6, siteLengthFt),
          toThree(zone.xMax, zone.yMin, 0.6, siteLengthFt),
          toThree(zone.xMax, zone.yMax, 0.6, siteLengthFt),
          toThree(zone.xMin, zone.yMax, 0.6, siteLengthFt),
          toThree(zone.xMin, zone.yMin, 0.6, siteLengthFt),
        ];
        return (
          <group key={zone.id}>
            <mesh
              position={[x, y, z]}
              scale={[w, 1, h]}
              onPointerOver={(e) => { e.stopPropagation(); onHover(zone.id); }}
              onPointerOut={(e) => { e.stopPropagation(); onHover((cur) => (cur === zone.id ? null : cur)); }}
              onClick={(e) => { e.stopPropagation(); onSelect(isSelected ? null : zone.id); }}
            >
              <boxGeometry args={[1, 1, 1]} />
              <meshBasicMaterial
                color="#ff3b30"
                transparent
                opacity={isSelected ? 0.3 : isHovered ? 0.18 : 0.02}
                depthWrite={false}
              />
            </mesh>
            <Line points={corners} color="#ff3b30" lineWidth={isSelected || isHovered ? 3 : 1.5} />
          </group>
        );
      })}
    </group>
  );
}

export default function Viewport({
  data, programZones, bayFt, networkSpecs, canopyResult, siteWidthFt, siteLengthFt, voxelFt, blenderObjUrl,
  blenderSvgUrl, onShowLineArt, onExportVectorView, exportingVectorView, onSaveBuild, onLoadBuild, canSaveBuild,
  savingBuild, removeTopSlab, onToggleRemoveTopSlab, visibleLayers,
  zonesEnabled, onToggleZones, selectedZoneId, onSelectZone, onExportZone, exportingZone,
}) {
  const loadBuildInputRef = useRef(null);
  const [shadingMode, setShadingMode] = useState('colored');
  // Default OFF (2026-07-10 fix): concrete_floor_block/concrete_retaining_
  // block ("salvage" -- harvested_block_specs() re-instancing removed real
  // slab material) render in a near-identical grey to the real floor_slab/
  // ramp_slab they replace, so an excavated area used to look like nothing
  // was removed at all -- a same-toned block immediately backfilled the
  // hole. Off by default so excavation reads as a true void; the underlying
  // data/tonnage math (slab_harvest_tons, the cut sheet) is unaffected
  // either way, this only filters what BoxInstances actually draws.
  const [showSalvage, setShowSalvage] = useState(false);
  // Program-zone 3D billboard labels toggle (2026-07-13) -- on by default;
  // ProgramLegend (bottom-right HUD panel) already covers "show program
  // names clearly" as a guaranteed-legible fallback, so turning these off
  // is purely about decluttering the viewport in a dense layout, not
  // losing the ability to identify zones.
  const [showLabels, setShowLabels] = useState(true);
  // Top (surface) slab toggle (2026-07-13: promoted from a pure client-side
  // render filter to the real RebuildParams.remove_top_slab control -- see
  // App.jsx/ParamPanel -- "off" now actually excavates the SURFACE slab
  // away server-side, not just hides its mesh). Driven by the parent's
  // params state (removeTopSlab/onToggleRemoveTopSlab), not local state, so
  // toggling here and toggling from ParamPanel (if ever added) stay in
  // sync. showTopSlab keeps its old meaning below (still filters
  // RealSlabs' mesh) -- it's just `!removeTopSlab` now instead of an
  // independent boolean.
  const showTopSlab = !removeTopSlab;
  const [viewMode, setViewMode] = useState('perspective');
  const [showBlenderBuild, setShowBlenderBuild] = useState(false);
  const [hoveredZone, setHoveredZone] = useState(null);
  const canvasRef = useRef(null);
  const controlsRef = useRef(null);
  // toThree()'s Z range is now [0, siteLengthFt] (fixed 2026-07-09, see
  // toThree's own comment) -- center must sit at the midpoint of THAT
  // range, not the old (buggy) [-siteLengthFt, 0] range's midpoint.
  const center = [siteWidthFt / 2, 0, siteLengthFt / 2];

  // Site-chunk zones (2026-07-23, true per-object clipping 2026-07-24) --
  // when a zone is selected, every real geometry source (voxels, structural
  // framing/canopy/network, program_boxes, real slabs/columns/fragments) is
  // clipped down to that zone's footprint -- not just filtered by a single
  // anchor point -- so a strut, canopy branch, or circulation path crossing
  // the boundary gets cut cleanly at the edge instead of sticking out past
  // it or vanishing wholesale. See siteZones.js's clipStructuralSpec/
  // clipRectBounds for the actual line/box/point clip logic. What's
  // isolated on screen now matches exactly what "Export Zone" (App.jsx's
  // handleExportZone) sends to the Blender build -- ramp_meshes (real
  // imported Rhino triangle meshes, not parametric specs) are the one
  // exception, excluded from the export entirely rather than left unclipped
  // (see handleExportZone's own comment).
  const zones = useMemo(() => computeZones(siteWidthFt, siteLengthFt), [siteWidthFt, siteLengthFt]);
  const activeZone = zones.find((z) => z.id === selectedZoneId) || null;
  const isolatedData = useMemo(() => {
    if (!data || !activeZone) return data;
    const clipSpecs = (specs) => (specs || [])
      .map((s) => clipStructuralSpec(s, activeZone))
      .filter(Boolean);
    return {
      ...data,
      voxels: data.voxels.filter((v) =>
        pointInZone(v.gx * voxelFt + voxelFt / 2, v.gy * voxelFt + voxelFt / 2, activeZone)),
      structural: clipSpecs(data.structural),
      program_boxes: clipSpecs(data.program_boxes),
      real_columns: (data.real_columns || []).filter((c) => pointInZone(c.x, c.z, activeZone)),
      real_slabs: (data.real_slabs || [])
        .map((slab) => {
          const xs = slab.top_corners_ft.map((c) => c[0]);
          const ys = slab.top_corners_ft.map((c) => c[1]);
          const clipped = clipRectBounds(Math.min(...xs), Math.max(...xs), Math.min(...ys), Math.max(...ys), activeZone);
          if (!clipped) return null;
          const z = slab.top_corners_ft[0][2];
          return {
            ...slab,
            top_corners_ft: [
              [clipped.xMin, clipped.yMin, z], [clipped.xMax, clipped.yMin, z],
              [clipped.xMax, clipped.yMax, z], [clipped.xMin, clipped.yMax, z],
            ],
            area_ft2: (clipped.xMax - clipped.xMin) * (clipped.yMax - clipped.yMin),
          };
        })
        .filter(Boolean),
      real_slab_fragments: Object.fromEntries(
        Object.entries(data.real_slab_fragments || {}).map(([key, entry]) => [
          key,
          { ...entry, remaining: entry.remaining.filter(([wx, wy]) => pointInZone(wx, wy, activeZone)) },
        ]),
      ),
      // attractor_points is a viewport-only visualization aid (Blender's
      // export never reads it, see blender/pershing_headless_build.py) --
      // filtered here purely so the isolated preview doesn't show marker
      // spheres floating outside the visible chunk, not because it affects
      // what actually gets exported.
      attractor_points: Object.fromEntries(
        Object.entries(data.attractor_points || {}).map(([cat, pts]) => [
          cat, pts.filter((p) => pointInZone(p.x_ft, p.y_ft, activeZone)),
        ]),
      ),
    };
  }, [data, activeZone, voxelFt]);
  const isolatedNetworkSpecs = useMemo(() => {
    if (!activeZone || !networkSpecs) return networkSpecs;
    return networkSpecs.map((s) => clipStructuralSpec(s, activeZone)).filter(Boolean);
  }, [networkSpecs, activeZone]);
  // canopyResult is its own top-level response (Generate Canopy's explicit
  // action), not part of `data` -- clipped separately here so panels/branch
  // supports crossing the boundary get cut the same way structural framing
  // does, instead of the isolation preview leaving canopy untouched.
  const isolatedCanopyResult = useMemo(() => {
    if (!activeZone || !canopyResult) return canopyResult;
    return {
      ...canopyResult,
      canopy_panels: (canopyResult.canopy_panels || []).map((s) => clipStructuralSpec(s, activeZone)).filter(Boolean),
      canopy_columns: (canopyResult.canopy_columns || []).map((s) => clipStructuralSpec(s, activeZone)).filter(Boolean),
    };
  }, [canopyResult, activeZone]);
  // Toggle only actually swaps the layer once a build exists -- with no
  // blenderObjUrl yet, always fall back to the live instanced view rather
  // than rendering nothing.
  const renderBlenderBuild = showBlenderBuild && !!blenderObjUrl;

  // "Export Current View" (2026-07-11, renamed from "Export PNG") --
  // whatever the camera is framing right now (any preset, or wherever the
  // user has orbited to) becomes a PNG (unchanged, same toDataURL()
  // technique + preserveDrawingBuffer/alpha combo the metabolizer
  // prototype used for its transparent-bg export), and ADDITIONALLY, in
  // orthographic view modes, triggers a real vector-linework export via
  // the headless-Blender Line Art pipeline (App.jsx's
  // handleExportVectorView, which reuses the same job/poll infrastructure
  // handleBuildInBlender already established).
  //
  // Scoped to orthographic modes only (viewMode !== 'perspective') -- a
  // free-orbit perspective camera has a vanishing point that doesn't map
  // onto the backend's orthographic Line Art projection the same way (see
  // the plan doc's Feature 3 scoping decision); PNG export still works in
  // any mode, since it's just a screenshot.
  //
  // Uses the LIVE camera direction (wherever the user has actually
  // orbited to within the current orthographic preset), not just that
  // preset's nominal starting direction -- read directly off the
  // OrbitControls ref (controls.object = the active camera, controls.target
  // = the current orbit pivot) rather than via useThree(), since
  // handleExport lives outside the <Canvas> tree.
  const handleExport = useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    // Posted straight to the backend (data/PershingMetabolizer/parkSVG/
    // remixedGeneratedPNGs/) instead of a browser <a download> -- user
    // asked (2026-07-17) for these to land next to the vector-export SVGs
    // automatically, no Downloads folder, no save dialog.
    const dataUrl = canvas.toDataURL('image/png');
    const filename = `pershing-${viewMode}-${Date.now()}.png`;
    exportViewPng(dataUrl, filename).catch((err) => console.error('view PNG export failed:', err));

    const isOrthographic = viewMode !== 'perspective';
    if (isOrthographic && controlsRef.current && onExportVectorView) {
      const controls = controlsRef.current;
      const camThreeDir = controls.object.position.clone().sub(controls.target).normalize();
      // THREE.js (X, Y-up, Z) -> backend's Z-up site-local frame -- exact
      // inverse of toThree()'s own (x,y,z) -> (x,z,siteLengthFt-y) mapping
      // (direction vectors only need the linear part, not the
      // siteLengthFt offset): site_x=three_X, site_y=-three_Z, site_z=
      // three_Y. Verified against every VIEW_PRESETS entry: e.g. axo's
      // three dir=(1,1,1) maps to (1,-1,1), exactly vector_export.py's own
      // AXO_VIEW_DIR.
      const viewDirSite = [camThreeDir.x, -camThreeDir.z, camThreeDir.y];
      onExportVectorView(viewDirSite);
    }
  }, [viewMode, onExportVectorView]);

  // Real cast shadows (2026-07-11 fix, "flat" viewport report): every mode
  // before this rendered lit purely by surface-normal angle to the sun, with
  // no occlusion/contact-shadow cue between terrace steps, columns, and
  // framing -- combined with a fairly strong ambient+hemisphere fill
  // relative to the sun, that washed out what little directional contrast
  // existed. Fix is two-part: (1) enable real shadow-mapping on the main
  // "sun" light + castShadow/receiveShadow on every real mesh (below), (2)
  // lower the fill lights so the new shadow contrast actually reads instead
  // of being flooded back out.
  //
  // The sun's shadow camera needs an explicit target pinned to the site's
  // real center, not three.js's implicit default (world origin) -- this
  // scene's real geometry spans roughly (0..siteWidthFt, 0..~100ft,
  // 0..siteLengthFt), entirely in the positive octant, nowhere near the
  // origin the light would otherwise aim its shadow frustum at. A plain
  // `target-position` prop on <directionalLight> does NOT work reliably in
  // r3f (three.js requires the light's `target` Object3D to be part of the
  // scene graph for its world matrix to update) -- rendering it as an
  // explicit <primitive> (which r3f DOES add to the scene) and passing that
  // object via `target=` is the correct, standard fix.
  const shadowHalfExtent = Math.max(siteWidthFt, siteLengthFt) * 0.65;
  const sunPosition = [center[0] + 300, 420, center[2] + 220];
  const sunTarget = useMemo(() => new THREE.Object3D(), []);

  return (
    <div className="flex-1 relative bg-background">
      <Canvas
        ref={canvasRef}
        shadows="soft"
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
        <OrbitControls ref={controlsRef} key={viewMode} target={center} makeDefault />
        {/* Lowered from 0.7/0.9 (2026-07-11) so the sun's new cast-shadow
            contrast actually shows instead of being flooded back out by fill. */}
        <ambientLight intensity={0.4} />
        <hemisphereLight args={['#cfe0f2', '#2a2f36', 0.55]} />
        <primitive object={sunTarget} position={center} />
        <directionalLight
          position={sunPosition}
          target={sunTarget}
          intensity={1.8}
          castShadow
          shadow-mapSize-width={2048}
          shadow-mapSize-height={2048}
          shadow-camera-left={-shadowHalfExtent}
          shadow-camera-right={shadowHalfExtent}
          shadow-camera-top={shadowHalfExtent}
          shadow-camera-bottom={-shadowHalfExtent}
          shadow-camera-near={10}
          shadow-camera-far={1200}
          shadow-bias={-0.0004}
        />
        <directionalLight position={[-200, 200, -300]} intensity={0.5} color="#dde8ff" />
        {renderBlenderBuild ? (
          <BlenderBuild objUrl={blenderObjUrl} siteLengthFt={siteLengthFt} shadingMode={shadingMode} />
        ) : (
          <>
            {visibleLayers.realContext && isolatedData && (
              <RealSlabs
                slabs={isolatedData.real_slabs}
                fragments={isolatedData.real_slab_fragments}
                voxelFt={voxelFt}
                siteLengthFt={siteLengthFt}
                shadingMode={shadingMode}
                showTopSlab={showTopSlab}
              />
            )}
            {visibleLayers.realContext && isolatedData && (
              <RealColumns columns={isolatedData.real_columns} siteLengthFt={siteLengthFt} shadingMode={shadingMode} />
            )}
            {visibleLayers.structural && isolatedData && (
              <StructuralInstances
                specs={isolatedData.structural}
                siteLengthFt={siteLengthFt}
                shadingMode={shadingMode}
                showSalvage={showSalvage}
              />
            )}
            {visibleLayers.greenscape && isolatedData && (
              <GreenscapeGround
                voxels={isolatedData.voxels}
                voxelFt={voxelFt}
                siteLengthFt={siteLengthFt}
                shadingMode={shadingMode}
              />
            )}
            {visibleLayers.trees && isolatedData && (
              <TreeGround
                voxels={isolatedData.voxels}
                voxelFt={voxelFt}
                siteLengthFt={siteLengthFt}
                shadingMode={shadingMode}
              />
            )}
            {visibleLayers.circulation && isolatedData && (
              <CirculationSurface
                voxels={isolatedData.voxels}
                voxelFt={voxelFt}
                siteLengthFt={siteLengthFt}
                shadingMode={shadingMode}
              />
            )}
            {/* Organic panelized canopy + branching supports (2026-07-16
                Canopy Redesign) -- from canopyResult, the "Generate Canopy"
                explicit action's OWN response, not data.structural (see
                App.jsx's handleGenerateCanopy). "Canopy" toggle repurposed
                a third time (previously: the disabled glass mesh below,
                then the old canopy_beam/Structural split) to gate this
                instead. Glass CanopyOverlay mesh stays disabled (2026-07-13
                -- it was occluding Program Zone text labels) -- if ever
                revived, gate it on visibleLayers.canopy too and read
                canopyResult.canopy_height_matrix, not data.canopy_height_matrix
                (removed, canopy no longer runs inside rebuild()). */}
            {visibleLayers.canopy && isolatedCanopyResult && (
              <>
                <CanopyPanelInstances
                  specs={isolatedCanopyResult.canopy_panels}
                  siteLengthFt={siteLengthFt}
                  shadingMode={shadingMode}
                />
                <CylinderInstances
                  specs={isolatedCanopyResult.canopy_columns}
                  siteLengthFt={siteLengthFt}
                  shadingMode={shadingMode}
                />
              </>
            )}
            {visibleLayers.structural && isolatedNetworkSpecs && (
              <StructuralInstances
                specs={isolatedNetworkSpecs}
                siteLengthFt={siteLengthFt}
                shadingMode={shadingMode}
                showSalvage={showSalvage}
              />
            )}
          </>
        )}
        {visibleLayers.staticContext && (
          <StaticContext siteLengthFt={siteLengthFt} shadingMode={shadingMode} />
        )}
        {/* Gated on the same LABELS toggle as program-zone labels (2026-07-24)
            -- previously rendered unconditionally regardless of that toggle. */}
        {showLabels && <StreetLabels siteWidthFt={siteWidthFt} siteLengthFt={siteLengthFt} />}
        {/* Program Zones + Program Boxes (2026-07-16 rework) -- the SAME
            program-zone data in two mutually-exclusive render modes, not
            two independently-stackable layers: "Program Zones" is the
            master visibility switch (off hides both geometry and labels
            entirely), "Program Boxes" just swaps flat footprint plates for
            extruded placeholder massing (sized to each zone's real claimed
            bay footprint, every category now, not just the civic/
            health_care ones that used to always render as real structural
            mass under "Structural" -- see logic/pershing_api.py's
            rebuild() docstring). Labels stay on in either mode. Boxes
            reuse BoxInstances directly rather than the full
            StructuralInstances wrapper since data.program_boxes only ever
            contains the box-shape building_mass kind. */}
        {visibleLayers.programZones && (
          <ProgramZones
            zones={programZones} bayFt={bayFt} siteLengthFt={siteLengthFt} shadingMode={shadingMode}
            showLabels={showLabels}
            showFootprint={!visibleLayers.programBoxes}
          />
        )}
        {visibleLayers.programZones && visibleLayers.programBoxes && isolatedData?.program_boxes && (
          <BoxInstances specs={isolatedData.program_boxes} siteLengthFt={siteLengthFt} shadingMode={shadingMode} showSalvage={false} />
        )}
        {visibleLayers.attractors && isolatedData?.attractor_points && (
          <AttractorMarkers points={isolatedData.attractor_points} siteLengthFt={siteLengthFt} shadingMode={shadingMode} />
        )}
        {zonesEnabled && (
          <ZoneGrid
            zones={zones}
            siteLengthFt={siteLengthFt}
            hoveredZone={hoveredZone}
            selectedZone={selectedZoneId}
            onHover={setHoveredZone}
            onSelect={onSelectZone}
          />
        )}
      </Canvas>
      <div className="absolute top-4 left-4 flex gap-4">
        <div className="bg-surface/80 backdrop-blur-sm border border-border rounded-lg flex flex-col">
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
        <div className="bg-surface/80 backdrop-blur-sm border border-border rounded-lg flex flex-col">
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
        <div className="bg-surface/80 backdrop-blur-sm border border-border rounded-lg flex flex-col">
          <span className="text-on-surface-variant text-[10px] font-mono-sm px-3 pt-2">SALVAGE</span>
          <div className="flex">
            {[{ key: false, label: 'OFF' }, { key: true, label: 'ON' }].map((opt) => (
              <button
                key={String(opt.key)}
                onClick={() => setShowSalvage(opt.key)}
                className={`px-3 py-2 font-mono-sm text-mono-sm uppercase border-t border-border ${
                  showSalvage === opt.key ? 'text-accent bg-surface-container-high' : 'text-on-surface-variant hover:text-primary'
                }`}
              >
                {opt.label}
              </button>
            ))}
          </div>
        </div>
        <div className="bg-surface/80 backdrop-blur-sm border border-border rounded-lg flex flex-col">
          <span className="text-on-surface-variant text-[10px] font-mono-sm px-3 pt-2">TOP SLAB</span>
          <div className="flex">
            {[{ key: true, label: 'ON' }, { key: false, label: 'OFF' }].map((opt) => (
              <button
                key={String(opt.key)}
                onClick={() => onToggleRemoveTopSlab?.(!opt.key)}
                className={`px-3 py-2 font-mono-sm text-mono-sm uppercase border-t border-border ${
                  showTopSlab === opt.key ? 'text-accent bg-surface-container-high' : 'text-on-surface-variant hover:text-primary'
                }`}
              >
                {opt.label}
              </button>
            ))}
          </div>
        </div>
        <div className="bg-surface/80 backdrop-blur-sm border border-border rounded-lg flex flex-col">
          <span className="text-on-surface-variant text-[10px] font-mono-sm px-3 pt-2">LABELS</span>
          <div className="flex">
            {[{ key: true, label: 'ON' }, { key: false, label: 'OFF' }].map((opt) => (
              <button
                key={String(opt.key)}
                onClick={() => setShowLabels(opt.key)}
                className={`px-3 py-2 font-mono-sm text-mono-sm uppercase border-t border-border ${
                  showLabels === opt.key ? 'text-accent bg-surface-container-high' : 'text-on-surface-variant hover:text-primary'
                }`}
              >
                {opt.label}
              </button>
            ))}
          </div>
        </div>
        <div className="bg-surface/80 backdrop-blur-sm border border-border rounded-lg flex flex-col">
          <span className="text-on-surface-variant text-[10px] font-mono-sm px-3 pt-2">ZONES</span>
          <div className="flex">
            {[{ key: false, label: 'OFF' }, { key: true, label: 'ON' }].map((opt) => (
              <button
                key={String(opt.key)}
                onClick={() => onToggleZones?.(opt.key)}
                className={`px-3 py-2 font-mono-sm text-mono-sm uppercase border-t border-border ${
                  zonesEnabled === opt.key ? 'text-accent bg-surface-container-high' : 'text-on-surface-variant hover:text-primary'
                }`}
              >
                {opt.label}
              </button>
            ))}
          </div>
        </div>
        {zonesEnabled && activeZone && (
          <button
            onClick={() => onExportZone?.(activeZone)}
            disabled={exportingZone}
            title={`Builds an OBJ in Blender containing only ${activeZone.label}'s voxels/structure/program boxes.`}
            className="bg-accent text-background px-4 py-2 font-mono-sm text-mono-sm font-bold uppercase tracking-widest rounded self-start hover:brightness-110 transition-all active:scale-[0.98] disabled:opacity-50"
          >
            {exportingZone ? 'Exporting...' : `Export ${activeZone.label}`}
          </button>
        )}
        <button
          onClick={handleExport}
          disabled={exportingVectorView}
          title={
            viewMode === 'perspective'
              ? 'Downloads a PNG screenshot. Vector linework export needs an orthographic view mode (Axo/Plan/Front/Side).'
              : 'Downloads a PNG screenshot and a vector linework SVG (Blender Line Art, real geometry, depth-layered).'
          }
          className="bg-accent text-background px-4 py-2 font-mono-sm text-mono-sm font-bold uppercase tracking-widest rounded self-start hover:brightness-110 transition-all active:scale-[0.98] disabled:opacity-50"
        >
          {exportingVectorView ? 'Exporting Linework...' : 'Export Current View'}
        </button>
        <button
          onClick={onSaveBuild}
          disabled={!canSaveBuild || savingBuild}
          title="Saves the current build (params, geometry, network, program zones) into the repo's build archive (outputs/pershing_archive/) -- browse or recall it from the ARCHIVE tab."
          className="bg-surface-container-high text-primary border border-border px-4 py-2 font-mono-sm text-mono-sm font-bold uppercase tracking-widest rounded self-start hover:brightness-110 transition-all active:scale-[0.98] disabled:opacity-50"
        >
          {savingBuild ? 'Saving...' : 'Save Build'}
        </button>
        <button
          onClick={() => loadBuildInputRef.current?.click()}
          title="Load a previously saved build JSON file to recall that exact iteration."
          className="bg-surface-container-high text-primary border border-border px-4 py-2 font-mono-sm text-mono-sm font-bold uppercase tracking-widest rounded self-start hover:brightness-110 transition-all active:scale-[0.98]"
        >
          Load Build
        </button>
        <input
          ref={loadBuildInputRef}
          type="file"
          accept="application/json,.json"
          className="hidden"
          onChange={(e) => {
            const file = e.target.files?.[0];
            if (file) onLoadBuild?.(file);
            e.target.value = ''; // allow re-selecting the same file next time
          }}
        />
        {blenderObjUrl && (
          <button
            onClick={() => setShowBlenderBuild((v) => !v)}
            className={`px-4 py-2 font-mono-sm text-mono-sm font-bold uppercase tracking-widest rounded self-start border transition-all active:scale-[0.98] ${
              showBlenderBuild ? 'bg-accent text-background border-accent' : 'border-accent text-accent hover:bg-accent hover:text-background'
            }`}
          >
            {showBlenderBuild ? 'Live View' : 'Blender Build'}
          </button>
        )}
        {blenderSvgUrl && (
          <button
            onClick={onShowLineArt}
            className="px-4 py-2 font-mono-sm text-mono-sm font-bold uppercase tracking-widest rounded self-start border border-accent text-accent hover:bg-accent hover:text-background transition-all active:scale-[0.98]"
          >
            View Line Art
          </button>
        )}
      </div>
      <div className="absolute bottom-4 right-4">
        <ProgramLegend zones={programZones} />
      </div>
    </div>
  );
}
