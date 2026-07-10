import { useMemo, useRef, useLayoutEffect, useState, useCallback } from 'react';
import { Canvas, useThree } from '@react-three/fiber';
import { OrbitControls, Instances, Instance, PerspectiveCamera, OrthographicCamera, Text, Billboard } from '@react-three/drei';
import * as THREE from 'three';
import StaticContext from './StaticContext.jsx';
import BlenderBuild from './BlenderBuild.jsx';
import { materialProps, SHADING_MODES } from '../shading.js';

// Plan-footprint dims (feet) per box-shaped StructuralElement.kind --
// mirrors blender_cockpit.py's _PROTOTYPE_DIMS_FT exactly. Cylinder/hex
// kinds don't use this map -- their geometry comes from spec.radius_ft
// (and, for two-point kinds, x2/y2/z2_ft) instead; see
// CylinderInstances/HexInstances below, which mirror
// blender_cockpit.py's _add_cylinder/_add_hex_prism and the
// x2_ft-is-not-None / _HEX_KINDS / _VERTICAL_CYLINDER_KINDS branching in
// build_structural_meshes.
const PROTOTYPE_DIMS_FT = {
  concrete_floor_block: [9.0, 9.0],
  concrete_retaining_block: [3.0, 3.0],
  steel_collar_sleeve: [2.0, 2.0],
  gusset_plate: [1.5, 0.1],
  steel_strap_band: [2.2, 0.15],
  footing_shoe: [1.3, 1.3],
  glulam_post: [1.0, 1.0],
  water_plane: [8.0, 8.0],
  water_cascade_block: [4.0, 1.5],
  misting_line: [0.15, 0.15],
  bench_assembly: [6.0, 2.0],
  restroom_pod: [10.0, 8.0],
  fountain: [4.0, 4.0],
  // Unit footprint -- BuildingMassEngine passes real width/depth directly
  // via scale/scale_y rather than a fixed prototype size like every other
  // box kind here, since building footprints vary per instance.
  building_mass: [1.0, 1.0],
};

const VERTICAL_CYLINDER_KINDS = new Set(['steel_bolt', 'bolt_flange_plate', 'tree_trunk']);
const HEX_KINDS = new Set(['steel_turnbuckle', 'tree_canopy']);

// Per-kind tint -- roughly matches the paint-category tints already
// established for Water/Shade (cyan) and Amenity/Resting (orange) so the
// same semantic colors carry through from painting to rendered assets.
const KIND_COLOR = {
  concrete_floor_block: '#8a8580',
  concrete_retaining_block: '#8a8580',
  steel_collar_sleeve: '#9aa3ad',
  gusset_plate: '#9aa3ad',
  steel_strap_band: '#9aa3ad',
  footing_shoe: '#9aa3ad',
  steel_bolt: '#9aa3ad',
  bolt_flange_plate: '#9aa3ad',
  steel_strut: '#9aa3ad',
  steel_tie_rod: '#9aa3ad',
  steel_turnbuckle: '#c4cdd6',
  glulam_post: '#8a6d4a',
  knee_brace: '#8a6d4a',
  timber_beam: '#8a6d4a',
  water_plane: '#26d9ff',
  water_cascade_block: '#26d9ff',
  misting_line: '#26d9ff',
  bench_assembly: '#ff8c26',
  restroom_pod: '#ff8c26',
  fountain: '#ff8c26',
  tree_trunk: '#5a4530',
  tree_canopy: '#3a8a3f',
  building_mass: '#b8b0a3',
};

const LEVEL_COLOR = ['#c2bdb4', '#7d9bb0', '#4d6b80', '#2a3f4d']; // grade -> deeper

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

// One instancedMesh PER LEVEL, each with a plain uniform material color --
// NOT a single instancedMesh using setColorAt()/instanceColor (which is
// what this originally used). instanceColor reliably renders solid black
// specifically when viewed through a true OrthographicCamera aligned
// exactly along an axis (confirmed empirically 2026-07-06 while building
// the Front/Side elevation presets: reproduced with old and new lighting,
// with and without tone mapping, with MeshBasicMaterial instead of
// MeshStandardMaterial, and with side:DoubleSide -- the ONLY change that
// fixed it was dropping instanceColor for a plain material.color, which
// is exactly the pattern BoxInstances/CylinderInstances/StructuralInstances
// below already use and which never showed this bug). Grouping by level
// (max 4 distinct values, LEVEL_COLOR.length) keeps this just as cheap as
// the single-mesh version.
function TerraceVoxels({ voxels, voxelFt, siteLengthFt, maxCanyonDepthFt, shadingMode }) {
  // Mirrors blender_cockpit.py's build_terrace_mesh: floor_z = -(max_canyon_depth_ft + 10.0),
  // NOT a fixed constant -- every voxel, excavated or not, gets a solid
  // block from this floor up to its own top, so the unexcavated majority
  // of the site reads as a real base slab the canyon cuts into.
  const floorZ = -(maxCanyonDepthFt + 10.0);
  const useLevelColors = shadingMode === 'colored' || !shadingMode;

  const byLevel = useMemo(() => {
    const map = {};
    for (const v of voxels) {
      const levelIdx = useLevelColors ? Math.min(-v.level, LEVEL_COLOR.length - 1) : 0;
      (map[levelIdx] ||= []).push(v);
    }
    return map;
  }, [voxels, useLevelColors]);

  if (voxels.length === 0) return null;

  return (
    <>
      {Object.entries(byLevel).map(([levelIdx, items]) => (
        <TerraceLevelGroup
          key={levelIdx}
          items={items}
          voxelFt={voxelFt}
          siteLengthFt={siteLengthFt}
          floorZ={floorZ}
          shadingMode={shadingMode}
          color={useLevelColors ? LEVEL_COLOR[levelIdx] : '#c2bdb4'}
        />
      ))}
    </>
  );
}

function TerraceLevelGroup({ items, voxelFt, siteLengthFt, floorZ, shadingMode, color }) {
  const meshRef = useRef();

  useLayoutEffect(() => {
    if (!meshRef.current) return;
    const dummy = new THREE.Object3D();
    items.forEach((v, i) => {
      const height = v.z_ft - floorZ;
      const cx = v.gx * voxelFt + voxelFt / 2;
      const cy = v.gy * voxelFt + voxelFt / 2;
      const cz = v.z_ft - height / 2;
      const [x, y, z] = toThree(cx, cy, cz, siteLengthFt);
      dummy.position.set(x, y, z);
      dummy.scale.set(voxelFt, height, voxelFt);
      dummy.updateMatrix();
      meshRef.current.setMatrixAt(i, dummy.matrix);
    });
    meshRef.current.instanceMatrix.needsUpdate = true;
  }, [items, voxelFt, siteLengthFt, floorZ]);

  const mat = materialProps(shadingMode, color);
  return (
    <instancedMesh ref={meshRef} args={[undefined, undefined, items.length]}>
      <boxGeometry args={[1, 1, 1]} />
      <meshStandardMaterial {...mat} />
    </instancedMesh>
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
    });
    meshRef.current.instanceMatrix.needsUpdate = true;
  }, [items, voxelFt, siteLengthFt]);

  if (items.length === 0) return null;

  const mat = materialProps(shadingMode, GREENSCAPE_COLOR);
  return (
    <instancedMesh ref={meshRef} args={[undefined, undefined, items.length]}>
      <boxGeometry args={[1, 1, 1]} />
      <meshStandardMaterial {...mat} />
    </instancedMesh>
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
    });
    meshRef.current.instanceMatrix.needsUpdate = true;
  }, [items, voxelFt, siteLengthFt]);

  if (items.length === 0) return null;

  const mat = materialProps(shadingMode, CIRCULATION_COLOR);
  return (
    <instancedMesh ref={meshRef} args={[undefined, undefined, items.length]}>
      <boxGeometry args={[1, 1, 1]} />
      <meshStandardMaterial {...mat} />
    </instancedMesh>
  );
}

function BoxInstances({ specs, siteLengthFt, shadingMode }) {
  const byKind = useMemo(() => {
    const map = {};
    for (const s of specs) {
      if (s.x2_ft !== null || HEX_KINDS.has(s.kind) || VERTICAL_CYLINDER_KINDS.has(s.kind)) continue;
      (map[s.kind] ||= []).push(s);
    }
    return map;
  }, [specs]);

  return (
    <>
      {Object.entries(byKind).map(([kind, items]) => (
        <Instances key={kind} limit={items.length} range={items.length}>
          <boxGeometry args={[1, 1, 1]} />
          <meshStandardMaterial {...materialProps(shadingMode, KIND_COLOR[kind] || '#888888')} />
          {items.map((s, i) => {
            // Fallback footprint (1,1) matches blender_cockpit.py's
            // _PROTOTYPE_DIMS_FT.get(kind, (1.0, 1.0, 1.0)) for any kind
            // not in the map.
            const [sx, sy] = PROTOTYPE_DIMS_FT[kind] || [1.0, 1.0];
            const [x, y, z] = toThree(s.x_ft, s.y_ft, s.z_top_ft - s.height_ft / 2, siteLengthFt);
            // Only gusset_plate still gets a rotated-box treatment
            // (faced along the strut's bearing angle, about the vertical
            // axis) -- mirrors blender_cockpit.py's _rotation_for. Sign
            // flipped because toThree's y -> L-y mirror (matching
            // Blender's own axo mirror) is a genuine reflection, and a
            // reflection reverses in-plane rotational handedness around
            // the vertical axis.
            const rotY = kind === 'gusset_plate' ? -(s.rotation_deg * Math.PI) / 180 : 0;
            // scale_y is only set for kinds needing an independent width vs.
            // depth (currently just building_mass) -- null everywhere else,
            // falling back to the original uniform `scale` behavior.
            return (
              <Instance
                key={i}
                position={[x, y, z]}
                rotation={[0, rotY, 0]}
                scale={[sx * s.scale, s.height_ft, sy * (s.scale_y ?? s.scale)]}
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

  return (
    <>
      {Object.entries(grouped).map(([kind, items]) => (
        <Instances key={kind} limit={items.length} range={items.length}>
          <cylinderGeometry args={[1, 1, 1, 8]} />
          <meshStandardMaterial {...materialProps(shadingMode, KIND_COLOR[kind] || '#888888')} />
          {items.map(({ p0, p1, radius }, i) => {
            const a = new THREE.Vector3(...p0);
            const b = new THREE.Vector3(...p1);
            const mid = a.clone().add(b).multiplyScalar(0.5);
            const dir = b.clone().sub(a);
            const length = dir.length();
            if (length < 1e-6) return null;
            const quat = new THREE.Quaternion().setFromUnitVectors(
              new THREE.Vector3(0, 1, 0),
              dir.normalize(),
            );
            return (
              <Instance
                key={i}
                position={mid.toArray()}
                quaternion={quat.toArray()}
                scale={[radius, length, radius]}
              />
            );
          })}
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
  return (
    <Instances limit={items.length} range={items.length}>
      <cylinderGeometry args={[1, 1, 1, 6]} />
      <meshStandardMaterial {...materialProps(shadingMode, KIND_COLOR.steel_turnbuckle)} />
      {items.map((s, i) => {
        const [x, y, z] = toThree(s.x_ft, s.y_ft, s.z_top_ft, siteLengthFt);
        const radius = s.radius_ft || 0.3;
        return (
          <Instance
            key={i}
            position={[x, y, z]}
            rotation={[0, -(s.rotation_deg * Math.PI) / 180, 0]}
            scale={[radius, s.height_ft, radius]}
          />
        );
      })}
    </Instances>
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

export default function Viewport({ data, siteWidthFt, siteLengthFt, voxelFt, blenderObjUrl, blenderSvgUrl, onShowLineArt }) {
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
    <div className="flex-1 relative rigid-grid-bg bg-background">
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
              <TerraceVoxels
                voxels={data.voxels}
                voxelFt={voxelFt}
                siteLengthFt={siteLengthFt}
                maxCanyonDepthFt={data.max_canyon_depth_ft}
                shadingMode={shadingMode}
              />
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
          </>
        )}
        <StaticContext siteLengthFt={siteLengthFt} shadingMode={shadingMode} />
        <StreetLabels siteWidthFt={siteWidthFt} siteLengthFt={siteLengthFt} />
        <gridHelper args={[Math.max(siteWidthFt, siteLengthFt) * 1.4, 40, '#3a3a3a', '#262626']} />
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
