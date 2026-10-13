"""New Leaf 3D bug models in place of the GameCube bug cards.

Every GC bug frame display list is replaced by the matching New Leaf species model, fitted into the GC model's
own local frame: the NL axes are matched to the GC axes by extent (longest to longest, thinnest to thinnest) and
the model is scaled to the GC model's size, so the native placement, rotation and flight code stay unchanged.
For the GC "wings moving" frames the New Leaf wing bones are rotated, so wings still flap.
Writes pc_insects.c_inc -> pc_insect_dl(native) and review sheets of GC vs NL for orientation checks.
"""
import json, re, sys
from pathlib import Path
import numpy as np
from PIL import Image
import native_models as nm
from recolor import recolor, needs_recolor
RECOLORED = []

ROOT = Path(__file__).resolve().parent
SRC = ROOT/'insect_source'
DATA = (ROOT/'ACGC-PC-Port/src/actor/ac_insect_data.c_inc').read_text()
MATCH = {'ohmurasaki': 'ageha', 'kuma': 'mitsu', 'shiokara': 'akane', 'matumushi': 'suzu', 'kanabun': 'kogane', 'hirata': 'hosokwa',
         'monshiro': 'monsiro', 'monki': 'monki', 'kiageha': 'ageha', 'minmin': 'minmin', 'tukutuku': 'tsuku',
         'higurashi': 'higu', 'abura': 'abura', 'danna': 'goki', 'akiakane': 'akane', 'ginyanma': 'ginyan',
         'oniyanma': 'oniyan', 'syouryou': 'syouryou', 'tonosama': 'tonosama', 'koorogi': 'koorogi',
         'kirigirisu': 'kirigiri', 'suzumushi': 'suzu', 'kabuto': 'kbt', 'tamamushi': 'tama', 'gomadara': 'kamikiri',
         'tentou': 'tentou', 'nanahoshi': 'tentou', 'kamakiri': 'kama', 'nokogiri': 'nokokwa', 'miyama': 'miyakwa',
         'okuwa': 'ookwa', 'kera': 'okera', 'amenbo': 'amembo', 'mino': 'mino', 'dango': 'dango', 'kumo': 'kumo',
         'ari': 'ari', 'ka': 'ka'}
FLIP = json.loads((ROOT/'insect_flip.json').read_text()) if (ROOT/'insect_flip.json').exists() else {}

def gc_frames(species):
    body = re.search(rf'static Gfx\* aINS_{species}_dl\[\] = \{{(.*?)\}};', DATA, re.S)[1]
    return [x.strip() for x in body.split(',') if x.strip()]

_files = {}
_dlfile = {}
def dl_file(dl):
    if dl not in _dlfile:
        stem = re.match(r'act_m_([a-z]+)', dl)[1]
        f = ROOT/f'ACGC-PC-Port/src/data/model/act_m_{stem}.c'
        if not f.exists() or f'Gfx {dl}[]' not in f.read_text():
            f = next(x for x in (ROOT/'ACGC-PC-Port/src/data/model').glob('act_m_*.c') if f'Gfx {dl}[]' in x.read_text())
        _dlfile[dl] = f
    return _dlfile[dl]
def gc_model(dl):
    f = dl_file(dl)
    if f not in _files: _files[f] = nm.parse_model_file(f)
    return _files[f].get(dl, [])

def nl_model(name):
    m = json.load(open(SRC/f'ins_{name}/ins_{name}.json'))['meshes']
    seen = []; meshes = []
    for mm in m:                                  # duplicate meshes (second skin copy) are dropped
        key = (len(mm['vertices']), round(sum(v['position'][0] for v in mm['vertices']), 2))
        if key in seen: continue
        seen.append(key); meshes.append(mm)
    return meshes

def axis_map(gpts, npts, flip):
    ge = gpts.max(0)-gpts.min(0); ne = npts.max(0)-npts.min(0)
    gorder = np.argsort(ge); norder = np.argsort(ne)
    M = np.zeros((3, 3))
    for gi, ni in zip(gorder, norder): M[gi, ni] = 1.0
    for ax, s in enumerate(flip): M[ax] *= s
    scale = ge.max()/max(ne.max(), 1e-6)
    return M, scale


import itertools
def _raster(tris2d, res=48):
    """tris2d: list of (3x2 points in 0..1, 3x2 uv, texture RGBA array) -> coverage mask res x res"""
    m = np.zeros((res, res), bool)
    ys, xs = np.mgrid[0:res, 0:res]; X = (xs+0.5)/res; Y = (ys+0.5)/res
    for P, UV, T in tris2d:
        (x0, y0), (x1, y1), (x2, y2) = P
        d = (y1-y2)*(x0-x2)+(x2-x1)*(y0-y2)
        if abs(d) < 1e-12: continue
        a = ((y1-y2)*(X-x2)+(x2-x1)*(Y-y2))/d; b = ((y2-y0)*(X-x2)+(x0-x2)*(Y-y2))/d; c = 1-a-b
        inside = (a >= 0) & (b >= 0) & (c >= 0)
        if not inside.any(): continue
        u = a*UV[0][0]+b*UV[1][0]+c*UV[2][0]; v = a*UV[0][1]+b*UV[1][1]+c*UV[2][1]
        u = np.abs(np.mod(u, 2.0)); u = np.where(u > 1, 2-u, u); v = np.abs(np.mod(v, 2.0)); v = np.where(v > 1, 2-v, v)
        th, tw = T.shape[:2]
        al = T[np.clip((v*th).astype(int), 0, th-1), np.clip((u*tw).astype(int), 0, tw-1), 3] > 100
        m |= inside & al
    return m

def _project(pts3, axes, lo, hi):
    a, b = axes
    return np.stack([(pts3[:, a]-lo[a])/max(hi[a]-lo[a], 1e-6), (pts3[:, b]-lo[b])/max(hi[b]-lo[b], 1e-6)], -1)

def best_orientation(gtris, gtex_of, nverts, ntex):
    """Pick the axis permutation/sign that makes the New Leaf silhouette match the GC model's silhouette, seen
    along each GC axis (cards show their picture face-on, so head/tail and top/side get matched)."""
    gpts = np.array([v[:3] for t in gtris for v in t[5]], float); glo, ghi = gpts.min(0), gpts.max(0)
    gsil = {}
    for view in range(3):
        axes = [a for a in range(3) if a != view]
        tr = []
        for t in gtris:
            P = np.array([v[:3] for v in t[5]], float); T = gtex_of(t)
            if T is None: continue
            tr.append((_project(P, axes, glo, ghi), [(v[3]/t[3], v[4]/t[4]) for v in t[5]], T))
        gsil[view] = _raster(tr)
    NP = np.array([v['position'] for v in nverts], float); nuv = [(v['uv'][0], 1-v['uv'][1]) for v in nverts]
    best = None
    # GC bugs and New Leaf bugs share the convention y = up, z = body length: only the facing (a half turn
    # about y) can differ, and the top-down silhouette decides it (head vs tail)
    for perm in [(0, 1, 2)]:
        for signs in [(1, 1, 1), (-1, 1, -1)]:
            M = np.zeros((3, 3))
            for gi in range(3): M[gi, perm[gi]] = signs[gi]
            Q = NP @ M.T; lo, hi = Q.min(0), Q.max(0)
            ge = ghi-glo; ne = hi-lo
            # extents must roughly agree in proportion
            ratio = np.sort(ge/max(ge.max(), 1e-6)) - np.sort(ne/max(ne.max(), 1e-6))
            score = 0.0
            for view in (1,):
                axes = [a for a in range(3) if a != view]
                tr = [(_project(Q[i:i+3], axes, lo, hi), nuv[i:i+3], ntex) for i in range(0, len(Q), 3)]
                ns = _raster(tr); g = gsil[view]
                inter = (ns & g).sum(); uni = (ns | g).sum()
                score += (inter/uni if uni else 0)*(1.0 if g.sum() > 20 else 0.2)
            score -= 2.0*np.abs(np.array([ne[i]/max(ne.max(), 1e-6)-ge[i]/max(ge.max(), 1e-6) for i in range(3)])).sum()
            if best is None or score > best[0]: best = (score, M)
    M = best[1]; Q = NP @ M.T
    ge = ghi-glo; ne = Q.max(0)-Q.min(0)
    scale = max(ge[0], ge[2])/max(max(ne[0], ne[2]), 1e-6)      # footprint size (the GC height is a flat card)
    return M, scale

def wing_pose(verts, bones, angle):
    """rotate wing bones (every bone except the body bone 1) about the body's long axis"""
    out = []
    P = np.array([v['position'] for v in verts]); long_ax = int(np.argmax(P.max(0)-P.min(0)))
    for v in verts:
        p = np.array(v['position'], float); b = v['nodes'][0] if v['nodes'] else 1
        if b in bones:
            side = np.sign(p[0] if long_ax != 0 else p[2]) or 1.0
            a = np.radians(angle)*side
            if long_ax == 2:   # rotate about z: x,y
                x, y = p[0], p[1]; p[0], p[1] = x*np.cos(a)-y*np.sin(a)*0, x*np.cos(a); p[1] = y+abs(x)*np.sin(abs(a))
            else:
                z, y = p[2], p[1]; p[2] = z*np.cos(a); p[1] = y+abs(z)*np.sin(abs(a))
        out.append((p, v['uv'], v['normal']))
    return out

ORIENT = {}
_gtex_cache = {}
def gc_tex_of(dl):
    src = dl_file(dl).read_text()
    pals = re.findall(r'LoadTLUT_Dolphin\(15, 16, 1, (\w+)\)', src)
    def f(t):
        key = (t[0], t[3], t[4])
        if key not in _gtex_cache:
            im = None
            for pal in pals:
                try: im = np.asarray(nm.decode_ci(nm.blob_first(t[0]), t[3], t[4], nm.palette_first(pal), 4).convert('RGBA')); break
                except Exception: pass
            _gtex_cache[key] = im
        return _gtex_cache[key]
    return f

out = ['/* Generated by generate_insects.py: New Leaf 3D bugs fitted to the GC bug frames. */', 'int g_pc_insects = 1;']
swaps = []; review = []
sys.path.insert(0, str((ROOT/'_review')))
try:
    import rend
except Exception:
    rend = None
def rgba8(name, im):
    im = im.convert('RGBA'); w, h = im.size; data = bytearray()
    for ty in range(0, h, 4):
        for tx in range(0, w, 4):
            tile = [im.getpixel((tx+x, ty+y)) for y in range(4) for x in range(4)]
            data.extend(c for r, g, b, a in tile for c in (a, r)); data.extend(c for r, g, b, a in tile for c in (g, b))
    out.append(f'static u8 {name}[] ATTRIBUTE_ALIGN(32) = {{'); out.extend(','.join(map(str, data[i:i+32]))+',' for i in range(0, len(data), 32)); out.append('};')

for species, nl in MATCH.items():
    if not (SRC/f'ins_{nl}/ins_{nl}.json').exists(): print('missing', nl); continue
    frames = gc_frames(species); distinct = list(dict.fromkeys(frames))
    meshes = nl_model(nl)
    allv = [v for mm in meshes for v in mm['vertices']]
    if species == 'mino':
        # the GC bagworm is authored lying along z (the game hangs it); the New Leaf one stands along y
        allv = [dict(v, position=[v['position'][0], v['position'][2], -v['position'][1]],
                     normal=[v['normal'][0], v['normal'][2], -v['normal'][1]]) for v in allv]
    npts = np.array([v['position'] for v in allv])
    texname = meshes[0]['texture']
    tp = SRC/f'ins_{nl}/{texname}.png'
    if not tp.exists(): tp = sorted((SRC/f'ins_{nl}').glob('*.png'))[0]
    tex = Image.open(tp).convert('RGBA'); tw, th = tex.size
    # colour-match to the GameCube bug when they differ (also turns a related New Leaf bug into the GC species)
    _g0 = gc_model(distinct[0])
    _gt = gc_tex_of(distinct[0])(_g0[0]) if _g0 else None
    if _gt is not None:
        _na = np.asarray(tex)
        if needs_recolor(_na, _gt, 35.0) or species in ('ohmurasaki', 'kuma', 'shiokara', 'matumushi', 'kanabun', 'hirata'):
            tex = Image.fromarray(recolor(_na, _gt), 'RGBA'); RECOLORED.append(species)
    rgba8(f'pc_ins_{species}_tex', tex)
    bones = sorted({v['nodes'][0] for v in allv if v['nodes']})
    wing_bones = [b for b in bones if b != 1] if len(bones) > 1 else []
    for fi, dl in enumerate(distinct):
        gtris = gc_model(dl)
        if not gtris: continue
        gpts = np.array([v[:3] for t in gtris for v in t[5]], float)
        if fi == 0 or species not in ORIENT:
            ORIENT[species] = best_orientation(gtris, gc_tex_of(dl), allv, np.asarray(tex))
        M, sc = ORIENT[species]
        gc_c = (gpts.max(0)+gpts.min(0))/2; nl_c = (npts.max(0)+npts.min(0))/2
        pose = [(np.array(v['position'], float), v['uv'], v['normal']) for v in allv] if fi == 0 or not wing_bones else wing_pose(allv, wing_bones, 50)
        name = f'pc_ins_{species}_{fi}'
        out.append(f'static Vtx {name}_v[] ATTRIBUTE_ALIGN(32) = {{')
        tri3 = []
        for i in range(0, len(pose), 3):
            tri = pose[i:i+3]
            su = 2*np.floor(min(v[1][0] for v in tri)/2); sv = 2*np.floor(min(v[1][1] for v in tri)/2)
            t3 = []
            for p, uv, n in tri:
                q = M @ ((p-nl_c)*sc)+gc_c; nn = M @ np.array(n, float); nn /= max(np.linalg.norm(nn), 1e-9)
                out.append('{{{%d,%d,%d},0,{%d,%d},{255,255,255,255}}},' % (round(q[0]), round(q[1]), round(q[2]),
                           round((uv[0]-su)*tw*32), round((1-(uv[1]-sv))*th*32)))
                t3.append((q, (uv[0], 1-uv[1]), nn))
            tri3.append(t3)
        out.append('};')
        dlc = [f'static Gfx {name}[] = {{', 'gsDPPipeSync(),', 'gsSPTexture(0,0,0,G_TX_RENDERTILE,G_ON),', 'gsDPSetPrimColor(0,128,255,255,255,255),',
               'gsDPSetCombineLERP(TEXEL0,0,PRIMITIVE,0,TEXEL0,0,PRIMITIVE,0,0,0,0,COMBINED,0,0,0,COMBINED),',
               'gsDPSetRenderMode(G_RM_FOG_SHADE_A,G_RM_AA_ZB_TEX_EDGE2),',
               f'gsDPSetTextureImage_Dolphin(G_IM_FMT_RGBA,G_IM_SIZ_32b,{tw},{th},pc_ins_{species}_tex),',
               'gsDPSetTile_Dolphin(G_DOLPHIN_TLUT_DEFAULT_MODE,0,0,GX_MIRROR,GX_MIRROR,0,0),',
               'gsSPLoadGeometryMode(G_ZBUFFER|G_SHADE|G_FOG|G_SHADING_SMOOTH),']
        for base in range(0, len(pose), 30):
            k = min(30, len(pose)-base); dlc.append(f'gsSPVertex(&{name}_v[{base}],{k},0),')
            dlc += [f'gsSP1Triangle({j},{j+1},{j+2},0),' for j in range(0, k, 3)]
        out += dlc+['gsSPEndDisplayList(),', '};']
        out.insert(2, f'extern Gfx {dl}[];')
        swaps.append((dl, name))
        if fi == 0 and rend is not None:
            # review: GC model (flat-shaded, its own texture) next to the fitted NL model, same camera
            gt = gtris[0]; gw, gh = gt[3], gt[4]
            try:
                pal = re.search(r'LoadTLUT_Dolphin\(15, 16, 1, (\w+)\)', (ROOT/f'ACGC-PC-Port/src/data/model/act_m_{re.match(r"act_m_([a-z]+)", dl)[1]}.c').read_text())[1]
                gim = nm.decode_ci(nm.blob(gt[0]), gw, gh, nm.palette(pal), 4)
            except Exception:
                gim = Image.new('RGBA', (16, 16), (200, 200, 200, 255))
            gtr = [[((v[0], v[1], v[2]), (v[3]/gw, 1-v[4]/gh), (0, 0, 1)) for v in t[5]] for t in gtris]
            a = (ROOT/'_review')
            rend.render(gtr, gim, str(a/'g.png'), yaw=0, pitch=0, size=160)
            rend.render([[(q.tolist(), uv, n.tolist()) for q, uv, n in t] for t in tri3], tex, str(a/'n.png'), yaw=0, pitch=0, size=160)
            review.append((species, Image.open(a/'g.png').copy(), Image.open(a/'n.png').copy()))
out += ['Gfx* pc_insect_dl(Gfx* native) {', '    if (!g_pc_insects || native == NULL) return NULL;']
out += [f'    if (native == {a}) return {b};' for a, b in swaps] + ['    return NULL;', '}']
(ROOT/'ACGC-PC-Port/pc/src/pc_insects.c_inc').write_text('\n'.join(out)+'\n')
if review:
    from PIL import ImageDraw
    cols = 4; W = 330
    sheet = Image.new('RGB', (cols*W, ((len(review)+cols-1)//cols)*175), 'white')
    for i, (sp, g, n) in enumerate(review):
        x, y = (i % cols)*W, (i//cols)*175
        sheet.paste(g, (x, y)); sheet.paste(n, (x+165, y)); ImageDraw.Draw(sheet).text((x+3, y+3), sp, fill=(0, 0, 0))
    sheet.save(ROOT/'screens/insects_review.png')
print('species', len({s for s, _, _ in review}), 'frames', len(swaps), 'recoloured', RECOLORED)
