"""
Pershing Square Park Intervention — 3D Model Generator
=======================================================
Self-contained Blender Python script.
Run inside Blender (Text Editor > Run Script) or from command line:
    blender --background --python pershing_square_generator.py

SVG INPUT:
    Set SVG_PATH below to any of the memory_machine_svg-color_*.svg files.
    The script parses GREEN / WATER / HARDSCAPE layers and drives geometry.

OUTPUT:
    Blender collection containing a single watertight mesh ready for
    FDM PLA printing at 193.26 x 112.175mm site dimensions.
"""

import bpy, bmesh, math, random, re
from collections import defaultdict
from mathutils import Vector, Matrix

# ── CONFIGURATION ─────────────────────────────────────────────────────
SVG_PATH    = ""
OPTION_NAME = "PershingSquare_Output"
EXPORT_STL  = False
EXPORT_PATH = ""

# ── SITE CONSTANTS ────────────────────────────────────────────────────
W  = 193.26
H  = 112.175
BZ = 0.4
MARGIN = 0.8

SITE_POLY = [(0,110.175),(0,2),(2,0),(191.26,0),(193.26,2),
             (193.26,110.175),(191.26,112.175),(2,112.175)]

BLDG_ZONES = [
    (0.0,24.2,42.8,111.8),(186.7,193.3,100.8,112.2),
    (167.5,193.3,87.2,112.2),(0.0,15.4,0.0,31.1),
    (120.8,186.8,102.4,112.2),(102.5,192.3,0.0,33.8),
    (0.0,67.9,0.0,17.4),(0.0,90.7,78.7,112.2),
]

COLOR_MAP = {
    'rgb(3, 169, 244)':   'WATER',
    'rgb(76, 175, 80)':   'GREEN',
    'rgb(158, 158, 158)': 'HARDSCAPE',
    'rgb(255, 255, 255)': 'BOUNDARY',
    'rgb(68, 68, 68)':    'BUILDINGS',
}

def parse_svg(svg_path):
    with open(svg_path, 'r') as f:
        svg = f.read()
    clip = re.search(r'<clipPath[^>]*><polygon[^>]*points="([^"]+)"', svg)
    if not clip:
        raise ValueError("No clipPath found in SVG")
    pts = [(float(x),float(y)) for x,y in re.findall(r'([\d.]+),([\d.]+)', clip.group(1))]
    clip_x0 = min(p[0] for p in pts); clip_y0 = min(p[1] for p in pts)
    clip_w  = max(p[0] for p in pts) - clip_x0
    clip_h  = max(p[1] for p in pts) - clip_y0
    bsx = W / clip_w; bsy = H / clip_h
    def to_b(x, y):
        return (x - clip_x0) * bsx, (clip_y0 + clip_h - y) * bsy
    COLS, ROWS = 8, 5
    grids = {l: [[0]*COLS for _ in range(ROWS)] for l in COLOR_MAP.values()}
    layer_counts = defaultdict(int)
    for el in re.findall(r'<path\b([^>]+)/?>', svg):
        style = re.search(r'style="([^"]*)"', el)
        d_attr = re.search(r'\bd="([^"]+)"', el)
        if not style or not d_attr: continue
        s = style.group(1); layer = None
        for col, name in COLOR_MAP.items():
            if col in s: layer = name; break
        if not layer: continue
        coords = [(float(x),float(y)) for x,y in
                  re.findall(r'([\d]+\.[\d]+),([\d]+\.[\d]+)', d_attr.group(1))]
        if not coords: continue
        cx = sum(c[0] for c in coords)/len(coords)
        cy = sum(c[1] for c in coords)/len(coords)
        if not (clip_x0 <= cx <= clip_x0+clip_w and clip_y0 <= cy <= clip_y0+clip_h):
            continue
        layer_counts[layer] += 1
        bx, by = to_b(cx, cy)
        ci = min(COLS-1, int(bx / (W/COLS)))
        ri = min(ROWS-1, int(by / (H/ROWS)))
        grids[layer][ri][ci] += 1
    return grids, layer_counts

def detect_water_type(water_grid):
    total = sum(water_grid[r][c] for r in range(5) for c in range(8))
    if total < 100: return 'none'
    north = sum(water_grid[r][c] for r in range(3,5) for c in range(8))
    if north / total > 0.75: return 'north_band'
    return 'diagonal'

def detect_water_edge(water_grid):
    ch = H / 5
    for row in range(5):
        if sum(water_grid[row]) > 100:
            return row * ch
    return H * 0.6

def scene_setup(name):
    for col in list(bpy.data.collections):
        for ob in list(col.objects): bpy.data.objects.remove(ob, do_unlink=True)
        bpy.data.collections.remove(col)
    for ob in list(bpy.data.objects): bpy.data.objects.remove(ob, do_unlink=True)
    for me in list(bpy.data.meshes): bpy.data.meshes.remove(me)
    col = bpy.data.collections.new(name)
    bpy.context.scene.collection.children.link(col)
    return col

def finalize_mesh(bm, name, col):
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=0.005)
    bm.edges.ensure_lookup_table()
    oe = [e for e in bm.edges if len(e.link_faces) == 1]
    if oe: bmesh.ops.holes_fill(bm, edges=oe, sides=0)
    me = bpy.data.meshes.new(name); bm.to_mesh(me); bm.free(); me.validate()
    ob = bpy.data.objects.new(name, me)
    for c in ob.users_collection: c.objects.unlink(ob)
    col.objects.link(ob)
    return ob

def post_process(ob):
    mesh = ob.data
    for v in mesh.vertices:
        if v.co.z < 0: v.co.z = 0.0
        v.co.x = max(MARGIN, min(W-MARGIN, v.co.x))
        v.co.y = max(MARGIN, min(H-MARGIN, v.co.y))
    mesh.update()
    bm = bmesh.new(); bm.from_mesh(mesh)
    bm.faces.ensure_lookup_table(); bm.edges.ensure_lookup_table()
    tiny = [f for f in bm.faces if f.calc_area() < 0.05
            and sum(v.co.z for v in f.verts)/len(f.verts) > 3.0]
    if tiny: bmesh.ops.delete(bm, geom=tiny, context='FACES')
    bm.edges.ensure_lookup_table()
    oe = [e for e in bm.edges if len(e.link_faces) == 1]
    if oe: bmesh.ops.holes_fill(bm, edges=oe, sides=0)
    bm.to_mesh(mesh); bm.free(); mesh.update()

def print_audit(ob):
    mesh = ob.data
    bm = bmesh.new(); bm.from_mesh(mesh)
    bm.verts.ensure_lookup_table(); bm.edges.ensure_lookup_table(); bm.faces.ensure_lookup_table()
    min_z = min(v.co.z for v in bm.verts)
    max_z = max(v.co.z for v in bm.verts)
    real_oh = [f for f in bm.faces if -0.95 < f.normal.z < -0.01
               and sum(v.co.z for v in f.verts)/len(f.verts) > 0.1]
    open_e = sum(1 for e in bm.edges if len(e.link_faces) == 1)
    bm.free()
    ok = min_z >= 0 and len(real_oh) == 0 and open_e == 0
    print(f"AUDIT: {'PASS' if ok else 'FAIL'} | {W:.0f}x{H:.0f}x{max_z:.1f}mm | oh={len(real_oh)} holes={open_e}")
    return ok

def box(bm, x, y, z, sx, sy, sz):
    x2=max(MARGIN,x); y2=max(MARGIN,y)
    sx2=min(sx,W-MARGIN-x2); sy2=min(sy,H-MARGIN-y2)
    if sx2<0.1 or sy2<0.1: return
    mat = (Matrix.Translation((x2+sx2/2, y2+sy2/2, z+sz/2)) @
           Matrix.Diagonal((sx2, sy2, sz, 1)).to_4x4())
    r = bmesh.ops.create_cube(bm, size=1)
    bmesh.ops.transform(bm, matrix=mat, verts=r['verts'])

def rbox(bm, cx, cy, z, sx, sy, sz, adeg):
    if cx<MARGIN+sx/2 or cx>W-MARGIN-sx/2: return
    if cy<MARGIN+sy/2 or cy>H-MARGIN-sy/2: return
    a = math.radians(adeg)
    mat = (Matrix.Translation((cx, cy, z+sz/2)) @
           Matrix.Rotation(a, 4, 'Z') @
           Matrix.Diagonal((sx, sy, sz, 1)).to_4x4())
    r = bmesh.ops.create_cube(bm, size=1)
    bmesh.ops.transform(bm, matrix=mat, verts=r['verts'])

def cyl(bm, cx, cy, bz, r, h, segs=12):
    if cx<MARGIN or cx>W-MARGIN or cy<MARGIN or cy>H-MARGIN: return
    res = bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=False,
                                segments=segs, radius1=r, radius2=r, depth=h)
    bmesh.ops.translate(bm, vec=Vector((cx, cy, bz+h/2)), verts=res['verts'])

def site_base(bm):
    bot = [bm.verts.new((p[0],p[1],0.0)) for p in SITE_POLY]
    top = [bm.verts.new((p[0],p[1],BZ)) for p in SITE_POLY]
    n = len(bot)
    bm.faces.new(bot[::-1]); bm.faces.new(top)
    for i in range(n):
        bm.faces.new([bot[i], bot[(i+1)%n], top[(i+1)%n], top[i]])

def water_basin(bm, x, y, bz, sx, sy, rw=2.2, ind=0.28):
    x2=max(MARGIN,x); y2=max(MARGIN,y)
    sx2=min(sx,W-MARGIN-x2); sy2=min(sy,H-MARGIN-y2)
    if sx2<rw*3 or sy2<rw*3: return
    box(bm,x2,y2,bz,sx2,rw,0.18); box(bm,x2,y2+sy2-rw,bz,sx2,rw,0.18)
    box(bm,x2,y2+rw,bz,rw,sy2-rw*2,0.18); box(bm,x2+sx2-rw,y2+rw,bz,rw,sy2-rw*2,0.18)
    mat = (Matrix.Translation((x2+sx2/2, y2+sy2/2, bz-ind+0.075)) @
           Matrix.Diagonal((sx2-rw*2, sy2-rw*2, 0.15, 1)).to_4x4())
    r = bmesh.ops.create_cube(bm, size=1)
    bmesh.ops.transform(bm, matrix=mat, verts=r['verts'])

def organic_mound(bm, cx, cy, bz, m):
    n  = len(m['radii']); br = m['radii']
    ns = m['n_steps'];    th = m['total_h']
    sh = th / ns;         rot = m.get('rot', 0.0);  sk = sh * 0.82
    for si in range(ns):
        rb = [max(0.4, br[i]*(1-si/ns)+0.3) for i in range(n)]
        rt = [max(0.2, r-sk) for r in rb]
        zb = bz+si*sh; zt = bz+(si+1)*sh
        bvs = []; tvs = []
        for i in range(n):
            a = 2*math.pi*i/n + rot
            bvs.append(bm.verts.new((
                max(MARGIN+0.1, min(W-MARGIN-0.1, cx+rb[i]*math.cos(a))),
                max(MARGIN+0.1, min(H-MARGIN-0.1, cy+rb[i]*math.sin(a))), zb)))
            tvs.append(bm.verts.new((
                max(MARGIN+0.1, min(W-MARGIN-0.1, cx+rt[i]*math.cos(a))),
                max(MARGIN+0.1, min(H-MARGIN-0.1, cy+rt[i]*math.sin(a))), zt)))
        try: bm.faces.new(tvs)
        except: pass
        if si == 0:
            try: bm.faces.new(list(reversed(bvs)))
            except: pass
        for i in range(n):
            try: bm.faces.new([bvs[i],bvs[(i+1)%n],tvs[(i+1)%n],tvs[i]])
            except: pass

def low_poly_tree(bm, cx, cy, base_z, trunk_r=0.65, trunk_h=2.8, crown_r=4.0, seed=0):
    if cx<MARGIN+crown_r*1.4 or cx>W-MARGIN-crown_r*1.4: return
    if cy<MARGIN+crown_r*1.4 or cy>H-MARGIN-crown_r*1.4: return
    if any(cx+crown_r*1.5>x0 and cx-crown_r*1.5<x1 and
           cy+crown_r*1.5>y0 and cy-crown_r*1.5<y1
           for x0,x1,y0,y1 in BLDG_ZONES): return
    rng = random.Random(seed)
    res = bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=False,
                                segments=8, radius1=trunk_r,
                                radius2=trunk_r*0.78, depth=trunk_h)
    bmesh.ops.translate(bm, vec=Vector((cx, cy, base_z+trunk_h/2)), verts=res['verts'])
    cbz = base_z + trunk_h
    N   = rng.randint(6, 8); rot = rng.uniform(0, 2*math.pi/N)
    spk = [rng.uniform(0.84, 1.16) for _ in range(N)]
    N_RINGS = 7; ts = math.radians(20); te = math.radians(178)
    scz = cbz + crown_r * 0.55
    thetas = [ts + (te-ts)*i/(N_RINGS-1) for i in range(N_RINGS)]
    rings = []
    for theta in thetas:
        rs = crown_r * math.sin(theta); zs = scz - crown_r * math.cos(theta)
        ring = []
        for i in range(N):
            a = 2*math.pi*i/N + rot; r2 = max(0.1, rs*spk[i])
            vx = max(MARGIN+0.05, min(W-MARGIN-0.05, cx+r2*math.cos(a)))
            vy = max(MARGIN+0.05, min(H-MARGIN-0.05, cy+r2*math.sin(a)))
            ring.append(bm.verts.new((vx, vy, zs)))
        rings.append((rs, zs, ring))
    try: bm.faces.new(list(reversed(rings[0][2])))
    except: pass
    for k in range(len(rings)-1):
        r0v = rings[k][2]; r1v = rings[k+1][2]
        out = rings[k+1][0] > rings[k][0]
        for i in range(N):
            ni = (i+1)%N
            if out:
                try: bm.faces.new([r0v[i],r1v[i],r1v[ni],r0v[ni]])
                except: pass
            else:
                try: bm.faces.new([r0v[i],r0v[ni],r1v[ni],r1v[i]])
                except: pass
    try: bm.faces.new(rings[-1][2])
    except: pass

def amph_grounded(bm, cx, cy, tiers=4, r0=6.0, tw=3.0, th=0.52, span=math.pi):
    mr = min(cx-MARGIN, cy-MARGIN, W-cx-MARGIN, H-cy-MARGIN); segs = 20
    for t in range(tiers):
        ri = r0 + t*(tw+0.1); ro = min(ri+tw, mr-0.5)
        if ri >= mr-0.5: break
        tt = BZ + (tiers-t)*th
        avb=[Vector((cx+ri*math.cos(span*i/segs),cy+ri*math.sin(span*i/segs),0.0)) for i in range(segs+1)]
        bvb=[Vector((cx+ro*math.cos(span*i/segs),cy+ro*math.sin(span*i/segs),0.0)) for i in range(segs+1)]
        avt=[Vector((cx+ri*math.cos(span*i/segs),cy+ri*math.sin(span*i/segs),tt)) for i in range(segs+1)]
        bvt=[Vector((cx+ro*math.cos(span*i/segs),cy+ro*math.sin(span*i/segs),tt)) for i in range(segs+1)]
        avbv=[bm.verts.new(v) for v in avb]; bvbv=[bm.verts.new(v) for v in bvb]
        avtv=[bm.verts.new(v) for v in avt]; bvtv=[bm.verts.new(v) for v in bvt]
        for i in range(segs): bm.faces.new([avtv[i],avtv[i+1],bvtv[i+1],bvtv[i]])
        for i in range(segs): bm.faces.new([bvbv[i],bvbv[i+1],bvtv[i+1],bvtv[i]])
        for i in range(segs): bm.faces.new([avtv[i+1],avtv[i],avbv[i],avbv[i+1]])
        for i in range(segs): bm.faces.new([bvbv[i+1],bvbv[i],avbv[i],avbv[i+1]])
        bm.faces.new([avbv[0],bvbv[0],bvtv[0],avtv[0]])
        bm.faces.new([avtv[-1],bvtv[-1],bvbv[-1],avbv[-1]])

def alcove(bm, ax, ay, w=8, d=7, wt=0.45, h=3.8, rt=0.35):
    box(bm,ax,ay,BZ,w,wt,h); box(bm,ax,ay,BZ,wt,d,h-0.7)
    box(bm,ax+w-wt,ay,BZ,wt,d,h-0.7); box(bm,ax,ay,BZ+h,w,d+wt,rt)

def generate_mounds(green_grid, terrace_heights, density_cutoff=50,
                    height_scale=1.0, dense=False, seed=113):
    MAX_G = max(green_grid[r][c] for r in range(5) for c in range(8))
    if MAX_G == 0: MAX_G = 1
    rng = random.Random(seed); mounds = []
    for row in range(5):
        for ci in range(8):
            den = green_grid[row][ci]
            if den < density_cutoff: continue
            cx = ci*(W/8)+(W/8)/2; cy = row*(H/5)+(H/5)/2
            if cx>W-MARGIN-3 or cy>H-MARGIN-3: continue
            t = den/MAX_G; base_r = 3.2+t*5.5
            radii = [base_r*(0.76+0.48*rng.random()) for _ in range(16)]
            ns = max(4, int(t*7)); sh = (0.42+t*0.45)*height_scale
            dat = BZ+terrace_heights[row]
            mounds.append({'cx':round(cx,1),'cy':round(cy,1),
                           'total_h':round(ns*sh,3),'n_steps':ns,
                           'radii':[round(r,2) for r in radii],
                           'rot':round(rng.uniform(0,0.5),3),'dat':dat})
    if dense:
        rng2 = random.Random(seed+88)
        for row in range(5):
            for ci in range(7):
                d1=green_grid[row][ci]; d2=green_grid[row][ci+1]
                if d1<200 or d2<200: continue
                cx=(ci+1)*(W/8); cy=row*(H/5)+(H/5)/2
                if cx>W-MARGIN-3 or cy>H-MARGIN-3: continue
                if any(cx+5>x0 and cx-5<x1 and cy+5>y0 and cy-5<y1
                       for x0,x1,y0,y1 in BLDG_ZONES): continue
                t=((d1+d2)/2)/MAX_G; base_r=2.5+t*4.0
                radii=[base_r*(0.78+0.44*rng2.random()) for _ in range(16)]
                ns=max(3,int(t*6)); sh=(0.35+t*0.38)*height_scale
                dat=BZ+terrace_heights[row]
                mounds.append({'cx':round(cx,1),'cy':round(cy,1),
                               'total_h':round(ns*sh,3),'n_steps':ns,
                               'radii':[round(r,2) for r in radii],
                               'rot':round(rng2.uniform(0,0.6),3),'dat':dat})
    return mounds

def generate_trees(green_grid, mounds, terrace_heights,
                   trunk_r=0.65, spacing=13, seed=117):
    MAX_G = max(green_grid[r][c] for r in range(5) for c in range(8))
    if MAX_G == 0: MAX_G = 1
    rng = random.Random(seed); trees = []
    for tx in range(14, 193, spacing):
        for ty in range(5, int(H-7), spacing-1):
            jx = max(5, min(W-5, tx+rng.uniform(-3,3)))
            jy = max(5, min(H-7, ty+rng.uniform(-2.5,2.5)))
            ci_l = min(7, int(jx/(W/8))); ri_l = min(4, int(jy/(H/5)))
            den = green_grid[ri_l][ci_l]
            if den < 80: continue
            t_d = den/MAX_G; cr = 3.2+t_d*2.5
            if any(jx+cr*1.4>x0 and jx-cr*1.4<x1 and jy+cr*1.4>y0 and jy-cr*1.4<y1
                   for x0,x1,y0,y1 in BLDG_ZONES): continue
            if any(math.sqrt((jx-m['cx'])**2+(jy-m['cy'])**2)<max(m['radii'])*0.70
                   for m in mounds): continue
            if any(math.sqrt((jx-t[0])**2+(jy-t[1])**2)<(cr+t[2])*0.72
                   for t in trees): continue
            ri_tree = min(4, int(jy/(H/5)))
            trees.append((round(jx,1), round(jy,1), round(cr,2),
                          rng.randint(0,999), ri_tree))
    return trees

def build_park(option_name=OPTION_NAME, svg_path=SVG_PATH,
               dense_hills=True, height_scale=1.0,
               trunk_r=0.65, water_edge=66.5):
    print(f"\n=== Building {option_name} ===")
    if svg_path and os.path.exists(svg_path):
        grids, counts = parse_svg(svg_path)
        green_grid  = grids['GREEN']
        water_grid  = grids['WATER']
        water_type  = detect_water_type(water_grid)
        if water_type == 'north_band':
            water_edge = detect_water_edge(water_grid)
        print(f"  SVG: {os.path.basename(svg_path)}  water={water_type}  edge_y={water_edge:.1f}")
    else:
        print("  No SVG — using built-in diagonal green wedge")
        green_grid = [
            [0,290,627,617,608,519,74,0],[0,0,294,637,640,627,586,354],
            [0,0,0,387,633,646,646,646],[0,0,0,57,605,608,608,601],
            [0,0,0,0,396,316,189,75],
        ]
        water_type = 'none'

    TERRACE_H = [0.15, 0.27, 0.39, 0.51, 0.63]
    mounds = generate_mounds(green_grid, TERRACE_H,
                             density_cutoff=50 if dense_hills else 200,
                             height_scale=height_scale, dense=dense_hills)
    trees  = generate_trees(green_grid, mounds, TERRACE_H,
                            trunk_r=trunk_r,
                            spacing=13 if dense_hills else 11)
    print(f"  Mounds: {len(mounds)}  Trees: {len(trees)}")

    col = scene_setup(option_name)
    bm  = bmesh.new()
    site_base(bm)

    for row in range(5):
        y0=max(MARGIN,row*(H/5)); y1=min(H-MARGIN,(row+1)*(H/5)); sy=y1-y0
        if sy<0.5: continue
        box(bm,MARGIN,y0,BZ,W-MARGIN*2,sy,TERRACE_H[row]+0.10)
        if row>0:
            rh=TERRACE_H[row]-TERRACE_H[row-1]
            box(bm,MARGIN,y0,BZ+TERRACE_H[row-1]+0.10,W-MARGIN*2,0.55,rh)

    if water_type == 'north_band':
        wh=H-water_edge-MARGIN; ww=W-MARGIN*2
        box(bm,MARGIN,water_edge,BZ+0.10,ww,wh,0.22)
        water_basin(bm,MARGIN,water_edge+1.5,BZ+0.22,ww,wh-1.5,rw=2.5,ind=0.30)
        for ci in range(3):
            sy2=water_edge-(ci+1)*3.5; sz=BZ+0.10-ci*0.08
            if sy2<MARGIN: continue
            box(bm,MARGIN,sy2,sz,ww,3.2,0.10); box(bm,MARGIN,sy2+3.2,sz,ww,0.5,0.10)
        for ji in range(6):
            fx=MARGIN+(ww/7)*(ji+1); fy=water_edge+wh*0.45
            if fx>W-MARGIN or fy>H-MARGIN: continue
            cyl(bm,fx,fy,BZ+0.22,2.0,0.25,segs=12); cyl(bm,fx,fy,BZ+0.47,0.18,3.5)

    for pi in range(6):
        off=(pi-2.5)*24; px=W/2+off*math.cos(math.radians(105)); py=H/2+off*math.sin(math.radians(105))
        mat=(Matrix.Translation((px,py,BZ+0.11))@Matrix.Rotation(math.radians(15),4,'Z')
             @Matrix.Diagonal((W*0.95,3.2,0.10,1)).to_4x4())
        rp=bmesh.ops.create_cube(bm,size=1); bmesh.ops.transform(bm,matrix=mat,verts=rp['verts'])
    for row in range(1,5): box(bm,MARGIN,row*(H/5)-2,BZ+TERRACE_H[row]+0.12,W-MARGIN*2,4,0.10)
    box(bm,W/2-2,MARGIN,BZ+0.11,4,H-MARGIN*2,0.10)

    for m in mounds:
        if any(m['cx']+max(m['radii'])*0.6>x0 and m['cx']-max(m['radii'])*0.6<x1 and
               m['cy']+max(m['radii'])*0.6>y0 and m['cy']-max(m['radii'])*0.6<y1
               for x0,x1,y0,y1 in BLDG_ZONES): continue
        organic_mound(bm,m['cx'],m['cy'],m['dat'],m)

    for tx,ty,cr,sd,ri_tree in trees:
        tree_z = BZ+TERRACE_H[ri_tree]+0.10
        low_poly_tree(bm,tx,ty,tree_z,trunk_r=trunk_r,trunk_h=2.8,crown_r=cr,seed=sd)

    amph_grounded(bm,16,H/2,tiers=4,r0=6.0,tw=3.0,th=0.52,span=math.pi)

    for px2,py2,rot in [(3*(W/8)+(W/8)/2,(H/5)+(H/5)/2,15),(5*(W/8)+(W/8)/2,(H/5)+(H/5)/2,15)]:
        if px2<W-MARGIN-8 and py2<H-MARGIN-8:
            rbox(bm,px2,py2,BZ+TERRACE_H[1]+0.10,11,11,0.40,rot)
            for a in [0,math.pi/2,math.pi,3*math.pi/2]:
                cyl(bm,px2+4.5*math.cos(a+math.pi/4),py2+4.5*math.sin(a+math.pi/4),BZ+TERRACE_H[1]+0.50,0.35,7.0)
            rbox(bm,px2,py2,BZ+TERRACE_H[1]+7.5,13,13,0.28,rot)

    alcove(bm,MARGIN,MARGIN); alcove(bm,W-14,MARGIN); alcove(bm,W-14,H*0.45)

    ob = finalize_mesh(bm, option_name+"_Mesh", col)
    post_process(ob)
    ok = print_audit(ob)

    if EXPORT_STL and EXPORT_PATH:
        os.makedirs(os.path.dirname(EXPORT_PATH), exist_ok=True)
        bpy.ops.export_mesh.stl(filepath=EXPORT_PATH, use_selection=False)
        print(f"  STL -> {EXPORT_PATH}")

    return ob

import os
if __name__ == "__main__":
    build_park(dense_hills=True, height_scale=1.0, trunk_r=0.65)
