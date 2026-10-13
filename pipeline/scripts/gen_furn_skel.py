"""New Leaf model swap for jointed GC furniture (wardrobes, dressers, clocks, toys) that keeps the GC animation.
The GC skeleton keeps moving its joints; each joint's display list is replaced by the NL triangles that belong to it,
expressed in that joint's rest-pose local space.
  - rest pose = first key / fixed value of the GC animation (doors closed), matrices M = parent * T * Rz * Ry * Rx
  - NL model is fitted (uniform scale) into the GC rest-pose bounds, like gen_furn.py
  - NL triangles on the body bone go to the GC joint with the most geometry; triangles on other NL bones go to the
    nearest moving GC joint (by rest-pose centroid). GC joints that get nothing draw an empty list.
usage: python gen_furn_skel.py gc_item nl_item [yaw_deg]
Writes ACGC-PC-Port/src/furniture/pc_furn_<gc>.c_inc and registers {'nl', 'yaw', 'skel': True} in furn_registry.json."""
import sys, json, math, re
from pathlib import Path
import numpy as np
from PIL import Image
import native_models as nm
import furn_color
import gen_furn

ROOT = Path(__file__).resolve().parent
SRC = ROOT/'ACGC-PC-Port'
MODELS = SRC/'src/data/model'
_gfx_index = None

def gfx_file(name):
    """data/model file that defines Gfx <name>[]"""
    global _gfx_index
    if _gfx_index is None:
        _gfx_index = {}
        for f in MODELS.glob('int_*.c'):
            for m in re.finditer(r'\bGfx\s+(\w+)\[\]\s*=', f.read_text(errors='ignore')): _gfx_index[m.group(1)] = f
    return _gfx_index.get(name)

SKEL_OVERRIDE = {}   # gc -> skeleton base when one profile serves many items (gyroids: hnw_commonNNN -> int_hnwNNN+1)
def skel_base(gc):
    """skeleton symbol base used by the item's profile, e.g. int_sum_clchest01 for sum_classicchest01"""
    if gc in SKEL_OVERRIDE: return SKEL_OVERRIDE[gc]
    if gc.startswith('hnw_common'): return f'int_hnw{int(gc[10:])+1:03d}'
    m = re.search(r'cKF_bs_r_(\w+)', (SRC/f'src/furniture/ac_{gc}.c').read_text())
    return m.group(1) if m else None

def parse_skeleton(gc):
    base = skel_base(gc)
    f = MODELS/f'{base}.c' if base else None
    if f is None or not f.exists(): return None
    src = f.read_text()
    m = re.search(r'cKF_Joint_R_c\s+cKF_je_r_' + base + r'_tbl\[\]\s*=\s*\{(.*?)\};', src, re.S)
    if not m: return None
    joints = []
    for jm in re.finditer(r'\{\s*(\w+)\s*,\s*(\d+)\s*,\s*(\w+)\s*,\s*\{\s*(-?\d+)\s*,\s*(-?\d+)\s*,\s*(-?\d+)\s*\}\s*\}', m.group(1)):
        joints.append({'model': None if jm.group(1) == 'NULL' else jm.group(1), 'child': int(jm.group(2)), 'flags': jm.group(3),
                       't': np.array([(int(jm.group(k))+32768) % 65536-32768 for k in (4, 5, 6)], float)})   # s16 written unsigned
    def tbl(kind, typ):
        mm = re.search(typ + r'\s+cKF_' + kind + r'_(?:r_)?' + base + r'_tbl\[\]\s*(?:ATTRIBUTE_ALIGN\(\d+\)\s*)?=\s*\{(.*?)\};', src, re.S)
        return [int(x) for x in re.findall(r'-?\d+', mm.group(1))] if mm else []
    anim = {'flags': tbl('ckcb', 'u8'), 'keys': tbl('kn', 's16'), 'fixed': tbl('c', 's16'), 'data': tbl('ds', 's16')}
    return joints, anim

def rest_values(joints, anim):
    """root translation + per-joint rotation (degrees) at the first key"""
    fl, kn, fx, ds = anim['flags'], anim['keys'], anim['fixed'], anim['data']
    ki = fi = di = 0
    def take(animated):
        nonlocal ki, fi, di
        if animated:
            v = ds[di*3+1]; di += kn[ki]; ki += 1   # first key's value
        else:
            v = fx[fi]; fi += 1
        return v
    root = [take(fl[0] & (0x20 >> j)) for j in range(3)]
    rots = [[take(fl[i] & (4 >> j))*0.1 for j in range(3)] for i in range(len(joints))]
    return np.array(root, float), rots

def moving_joints(joints, anim):
    """joints whose rotation keys actually change during the animation (flags alone also mark constant keys)"""
    fl, kn, ds = anim['flags'], anim['keys'], anim['data']
    ki = di = 0; out = set()
    for j in range(3):
        if fl[0] & (0x20 >> j): di += kn[ki]; ki += 1
    for i in range(len(joints)):
        for j in range(3):
            if fl[i] & (4 >> j):
                vals = [ds[(di+q)*3+1] for q in range(kn[ki])]
                if max(vals)-min(vals) > 5: out.add(i)
                di += kn[ki]; ki += 1
    return out

def clock_hands(gc):
    """{joint: (kind, gfx)}: kind 'hour'/'min'; gfx = the Gfx the profile draws itself for that hand (None = drawn by the joint)"""
    pf = SRC/f'src/furniture/ac_{gc}.c'
    if not pf.exists(): return {}
    t = pf.read_text()
    out = {}
    for m in re.finditer(r'rad_(hour|min)', t):
        pre = t[:m.start()]
        j = [int(x) for x in re.findall(r'(?:joint_idx|jointNum|joint_num)\s*==\s*(\d+)', pre)]
        if not j: continue
        nxt = re.search(r'gSPDisplayList\(\s*\w+\s*,\s*(\w+)\s*\)|\}\s*else|return', t[m.end():])
        g = nxt.group(1) if nxt and nxt.group(1) else None
        out[j[-1]] = (m.group(1), g)
    return out

def own_drawn(gc):
    """extra Gfx the profile draws directly in its draw callbacks (e.g. clock glass), {joint: gfx}"""
    pf = SRC/f'src/furniture/ac_{gc}.c'
    if not pf.exists(): return {}
    t = pf.read_text()
    out = {}
    for m in re.finditer(r'(?:joint_idx|jointNum|joint_num)\s*==\s*(\d+)\)\s*\{(.*?)(?=\}\s*else|\n\s*\}\n)', t, re.S):
        g = re.search(r'gSPDisplayList\(\s*\w+\s*,\s*(\w+)\s*\)', m.group(2))
        if g: out[int(m.group(1))] = g.group(1)
    return out

def mat_TR(t, r):
    rx, ry, rz = [math.radians(a) for a in r]
    cz, sz, cy, sy, cx, sx = math.cos(rz), math.sin(rz), math.cos(ry), math.sin(ry), math.cos(rx), math.sin(rx)
    Rz = np.array([[cz, -sz, 0], [sz, cz, 0], [0, 0, 1]]); Ry = np.array([[cy, 0, sy], [0, 1, 0], [-sy, 0, cy]])
    Rx = np.array([[1, 0, 0], [0, cx, -sx], [0, sx, cx]])
    M = np.eye(4); M[:3, :3] = Rz@Ry@Rx; M[:3, 3] = t
    return M

def rest_matrices(joints, anim):
    root, rots = rest_values(joints, anim)
    mats = [None]*len(joints)
    idx = [0]
    def walk(parent):
        k = idx[0]; idx[0] += 1
        t = root if k == 0 else joints[k]['t']
        mats[k] = parent@mat_TR(t, rots[k])
        for _ in range(joints[k]['child']): walk(mats[k])
    walk(np.eye(4))
    return mats

def joint_geometry(model):
    f = gfx_file(model)
    if f is None: return np.zeros((0, 3))
    tris = nm.parse_model_file(f).get(model, [])
    return np.array([p[:3] for t in tris for p in t[5]], float).reshape(-1, 3)

_POSES = None
def game_pose(gc):
    """furniture-local joint matrices (column convention) recorded in game with PC_DUMP_POSE (fixes_test/poses/*.txt):
    {joint index: 4x4} for the joints that carry a model, or None"""
    global _POSES
    if _POSES is None:
        _POSES = {}
        idx = json.load(open(ROOT/'furn_work/ftr_index.json'))['items']
        names = {}; W = {}; J = {}
        for f in sorted((ROOT.parent/'fixes_test/poses').glob('*.txt')):
            for l in open(f):
                t = l.split()
                if not t: continue
                if t[0] == 'S' and t[1].startswith('ftr_'): names.setdefault(t[2], int(t[1][4:], 16))
                elif t[0] == 'W': W.setdefault(t[1], np.array([float(x) for x in t[2:18]]).reshape(4, 4))
                elif t[0] == 'J': J.setdefault(t[1], {}).setdefault(int(t[2]), np.array([float(x) for x in t[3:19]]).reshape(4, 4))
        for ptr, item in names.items():
            if ptr in W and ptr in J:
                if 0 <= item < len(idx): _POSES[idx[item][4:].lower()] = (W[ptr], J[ptr])   # name = ftr index
    if gc not in _POSES: return None
    W, J = _POSES[gc]; Wi = np.linalg.inv(W)
    return {k: (J[k]@Wi).T for k in J}

def main(gc, nl, yaw=0.0, tint=None):
    sk = parse_skeleton(gc)
    if sk is None: raise RuntimeError('no skeleton')
    joints, anim = sk
    mats = rest_matrices(joints, anim)
    gp = game_pose(gc)
    if gp is not None:   # the real in-game pose beats the first-key estimate
        mj = [k for k, j in enumerate(joints) if j['model']]
        if len(gp) >= len(mj):
            for m_i, k in enumerate(mj): mats[k] = gp[m_i]
    geo = {}
    for k, j in enumerate(joints):
        if j['model']:
            g = joint_geometry(j['model'])
            if len(g): geo[k] = (mats[k]@np.c_[g, np.ones(len(g))].T).T[:, :3]
    allp = np.concatenate(list(geo.values()))
    lo, hi = allp.min(0), allp.max(0)
    mv = moving_joints(joints, anim)
    still = [kk for kk in geo if kk not in mv]
    body = max(still or list(geo), key=lambda kk: len(geo[kk]))   # the biggest joint the animation never rotates
    hands = clock_hands(gc)
    drawn = own_drawn(gc)
    movers = [k for k in geo if k != body and k not in hands and k not in drawn]
    movers = [k for k in movers if joints[k]['flags'] == 'cKF_JOINT_FLAG_DISP_OPA'] or movers   # never put solid parts on glass / water joints
    cent = {k: geo[k].mean(0) for k in geo}

    d = json.load(open(next(furn_color.nl_dir(nl).glob('*.json'))))
    meshes = d['meshes']
    def see_through(m):   # blended NL glass (no alpha test, translucent texture) or water surface
        if m['texture'] == 'wt' or str(m['texture']).startswith('aqua_glass'): return True
        if m.get('alphaTest', {}).get('isTestEnabled'): return False
        return Image.open(furn_color.nl_tex_path(nl, m['texture'])).convert('RGBA').getextrema()[3][1] < 250
    glass = {mi for mi, m in enumerate(meshes) if see_through(m)} if nl.startswith(('fsh_', 'ins_')) else set()   # tanks and cages only
    if sum(len(meshes[mi]['vertices']) for mi in glass)*2 >= sum(len(m['vertices']) for m in meshes): glass = set()   # mostly "translucent": NL alpha carries other data
    tank = bool(glass) or any(str(m['texture']).startswith('aqua_') for m in meshes)
    gnodes = {v['nodes'][0] if v['nodes'] else 0 for mi in glass for v in meshes[mi]['vertices']}
    critter = lambda v: bool(gnodes) and (v['nodes'][0] if v['nodes'] else 0) not in gnodes   # the fish / insect inside a tank or cage
    P = np.array([v['position'] for m in meshes for v in m['vertices'] if not critter(v)], float)
    if not len(P): critter = lambda v: False; P = np.array([v['position'] for m in meshes for v in m['vertices']], float)
    ang = math.radians(yaw); c, s = math.cos(ang), math.sin(ang)
    R = lambda p: np.array([p[0]*c+p[2]*s, p[1], -p[0]*s+p[2]*c])
    Pr = np.array([R(p) for p in P]); nlo, nhi = Pr.min(0), Pr.max(0)
    base = 0.0 if lo[1] <= 300 else lo[1]
    gs = hi-lo; gs[1] = hi[1]-base; ns = nhi-nlo
    k = min(gs[0]/ns[0], gs[1]/ns[1], gs[2]/ns[2])
    if gc.startswith('hnw_common'): k = gs[1]/ns[1]   # gyroids: match the height (the GC rest pose leans, which inflates its width)
    cx, cz = (lo[0]+hi[0])/2, (lo[2]+hi[2])/2
    kv = np.full(3, k)
    if gnodes and max(gs[0]/ns[0], gs[2]/ns[2])/k > 1.3: kv = gs/ns   # NL tank of another footprint (2x2 vs 2x1): stretch the box to the GC glass
    off = np.array([cx-kv[0]*(nlo[0]+nhi[0])/2, base-kv[1]*nlo[1], cz-kv[2]*(nlo[2]+nhi[2])/2])
    # NL bone groups: body = most-used node
    from collections import Counter
    nodes = Counter(v['nodes'][0] if v['nodes'] else 0 for m in meshes for v in m['vertices'])
    nl_body = nodes.most_common(1)[0][0]

    # tank / cage creature: one rigid NL fish or insect fitted onto the GC creature joint(s)
    crit_jk = None; crit_xf = None; crit_hide = []
    C = np.array([R(v['position']) for m in meshes for v in m['vertices'] if critter(v)], float)
    cj = [kk for kk in geo if kk != body and kk in mv and kk not in hands]
    if len(C) and cj:
        T = np.concatenate([geo[kk] for kk in cj]); tlo, thi = T.min(0), T.max(0)
        clo, chi = C.min(0), C.max(0)
        tax = 0 if thi[0]-tlo[0] >= thi[2]-tlo[2] else 2; cax = 0 if chi[0]-clo[0] >= chi[2]-clo[2] else 2
        def thick_end(Q, ax, lo, hi):   # +1 when the thicker (head) end is at the high end of the axis
            t = (Q[:, ax]-lo[ax])/max(hi[ax]-lo[ax], 1e-9)
            h = lambda sel: np.ptp(Q[sel, 1]) if sel.sum() > 2 else 0.0
            return 1 if h(t > 0.6) >= h(t < 0.4) else -1
        # rotation about Y taking the NL long axis onto the GC long axis, head to head
        sc = thick_end(C, cax, clo, chi); st = thick_end(T, tax, tlo, thi)
        e = np.eye(3)
        src = e[cax]*sc; dst = e[tax]*st
        th = math.atan2(src[0], src[2])-math.atan2(dst[0], dst[2])
        Ry = np.array([[math.cos(th), 0, math.sin(th)], [0, 1, 0], [-math.sin(th), 0, math.cos(th)]])
        Cr = C@Ry.T; rlo, rhi = Cr.min(0), Cr.max(0)
        kc = (thi[tax]-tlo[tax])/max(rhi[tax]-rlo[tax], 1e-9)
        kc = min(kc, k*1.2)   # never bigger than New Leaf proportions
        tc = (tlo+thi)/2; cc = (rlo+rhi)/2
        crit_xf = lambda p: tc+kc*(Ry@np.asarray(p)-cc)
        opa = [kk for kk in cj if joints[kk]['flags'] == 'cKF_JOINT_FLAG_DISP_OPA']
        if opa: crit_jk = max(opa, key=lambda kk: len(geo[kk]))   # swims with the GC fish joint
        else: crit_jk = body; crit_hide = cj                          # GC sprite insects: NL insect sits still, sprites hidden

    # clock hands: the two small NL bone groups nearest the GC hand pivot (longer one = minute hand)
    hand_node = {}
    if hands:
        groups = {}
        for m in meshes:
            for v in m['vertices']:
                nd = v['nodes'][0] if v['nodes'] else 0
                if nd != nl_body: groups.setdefault(nd, []).append(off+kv*R(v['position']))
        piv = np.mean([mats[j][:3, 3] for j in hands], axis=0)
        near = sorted(groups, key=lambda nd: np.linalg.norm(np.mean(groups[nd], 0)[:2]-piv[:2]))[:2]
        if len(near) == 2:
            ln = {nd: max(np.linalg.norm(np.array(p)[:2]-piv[:2]) for p in groups[nd]) for nd in near}
            short, long_ = sorted(near, key=lambda nd: ln[nd])
            for j, (kind, g) in hands.items(): hand_node[short if kind == 'hour' else long_] = j

    # triangles in furniture space, with smooth normals welded by position
    acc = {}; tris = []
    key = lambda p: tuple(np.round(p*50).astype(int))
    for mi, m in enumerate(meshes):
        vs = m['vertices']
        if mi in glass: continue   # GC glass / water stay (translucent)
        for i in range(0, len(vs)-2, 3):
            cr = crit_xf is not None and critter(vs[i])
            q = [crit_xf(R(vs[i+j]['position'])) if cr else off+kv*R(vs[i+j]['position']) for j in range(3)]
            n = np.cross(q[1]-q[0], q[2]-q[0]); l = np.linalg.norm(n)
            if l < 1e-9: continue
            n /= l
            node = vs[i]['nodes'][0] if vs[i]['nodes'] else 0
            if cr: jk = crit_jk
            elif gc.startswith('hnw_common'): jk = body   # gyroids: one rigid New Leaf figure (its parts drifted apart on the GC sway joints)
            elif node in hand_node: jk = hand_node[node]
            elif node == nl_body or not movers or crit_xf is not None: jk = body   # a tank / cage is one rigid body around its creature
            else:
                cen = (q[0]+q[1]+q[2])/3
                jk = min(movers, key=lambda kk: np.linalg.norm(cent[kk]-cen))
            for j in range(3): acc.setdefault((jk, key(q[j])), []).append(n)
            tris.append((mi, jk, q, [vs[i+j]['uv'] for j in range(3)]))
    inv = {kk: np.linalg.inv(mats[kk]) for kk in geo}
    targets = {}   # joint -> 4x4 furniture-space -> drawn-space
    for jk in set(list(geo)+list(hands)):
        jt = [t for t in tris if t[1] == jk]
        if jk in hands and hands[jk][1]:
            # profile draws this hand itself: frame = joint position, x right / y up, hand pointing +x at 12 o'clock
            piv = mats[jk][:3, 3]
            cen = np.mean([p for t in jt for p in t[2]], 0) if jt else piv+np.array([1, 0, 0])
            th = math.atan2(cen[1]-piv[1], cen[0]-piv[0])
            M = np.eye(4); M[:3, :3] = mat_TR([0, 0, 0], [0, 0, -math.degrees(th)])[:3, :3]; M[:3, 3] = -(M[:3, :3]@piv)
            targets[jk] = M
        elif jk in geo:
            M = inv[jk].copy()
            if jk in hands and jt and len(joint_geometry(joints[jk]['model'])):
                # turn the NL hand about the joint axis so it points where the GC hand points at rest
                g = joint_geometry(joints[jk]['model']).mean(0)
                c2 = (M@np.r_[np.mean([p for t in jt for p in t[2]], 0), 1])[:3]
                d = math.atan2(g[1], g[0])-math.atan2(c2[1], c2[0])
                M = mat_TR([0, 0, 0], [0, 0, math.degrees(d)])@M
            targets[jk] = M

    out = [f'/* Generated by gen_furn_skel.py: New Leaf {nl} on the joints of GC {gc} (scale {k:.2f}) */']
    texinfo = {}
    for mi, m in enumerate(meshes):
        tname = m['texture']
        im = Image.open(furn_color.nl_tex_path(nl, tname)).convert('RGBA')
        if tint and tname in tint:
            px = np.array(im, float); mu = px[..., :3].reshape(-1, 3).mean(0)
            px[..., :3] = np.clip(px[..., :3]*(np.array(tint[tname], float)/np.maximum(mu, 1)), 0, 255)
            im = Image.fromarray(px.astype(np.uint8), 'RGBA')
        at = m.get('alphaTest', {}); cut = bool(at.get('isTestEnabled'))
        if gen_furn.blended_cutout(m, im): cut = True; at = {'testReference': 100}
        gk = None if cut or tank else gen_furn.glass_kind(m, im)   # tanks keep the GC glass
        if gk == 'env': im = Image.new('RGBA', (8, 8), gen_furn.GLASS_RGBA)
        if gk == 'chrome': im = gen_furn.chrome_image(im); gk = None
        if not cut and not gk and gen_furn.spec_mask(m): im = gen_furn.bake_spec(im, m, gen_furn.SPEC.get(gc, gen_furn.SPEC_DEFAULT))
        if gk: pass
        elif cut:
            ref = min(at.get('testReference', 0), 8) if at.get('testReference', 0) != 100 else 100
            im = gen_furn.bleed(im); im.putalpha(im.getchannel('A').point(lambda a: 255 if a > ref else 0))
        else: im.putalpha(255)
        w, h = im.size; arr = f'pc_furn_{gc}_tex{mi}'; data = bytearray()
        for ty in range(0, h, 4):
            for tx in range(0, w, 4):
                t = [im.getpixel((tx+x, ty+y)) for y in range(4) for x in range(4)]
                data.extend(cc for r, g, b, a in t for cc in (a, r)); data.extend(cc for r, g, b, a in t for cc in (g, b))
        out.append(f'static u8 {arr}[] ATTRIBUTE_ALIGN(32) = {{'); out += [','.join(map(str, data[i:i+32]))+',' for i in range(0, len(data), 32)]; out.append('};')
        wrap = lambda v: 'GX_MIRROR' if v == 3 else 'GX_REPEAT' if v == 2 else 'GX_CLAMP'
        texinfo[mi] = (arr, w, h, cut, wrap(m['mapper']['wrapU']), wrap(m['mapper']['wrapV']), gk)
    patch = []
    for jk in sorted(targets):
        jt = [t for t in tris if t[1] == jk]
        Mi = targets[jk]; Rn = Mi[:3, :3]
        vtx = []; gfx = [f'static Gfx pc_furn_{gc}_j{jk}[] = {{']
        if jt:
            gfx += ['gsSPTexture(0,0,0,G_TX_RENDERTILE,G_ON),', 'gsDPSetPrimColor(0,128,255,255,255,255),',
                    'gsDPSetCombineLERP(TEXEL0,0,SHADE,0,0,0,0,TEXEL0,PRIMITIVE,0,COMBINED,0,0,0,0,COMBINED),',
                    'gsSPLoadGeometryMode(G_ZBUFFER|G_SHADE|G_CULL_BACK|G_FOG|G_LIGHTING|G_SHADING_SMOOTH|G_DECAL_LEQUAL),']
        for mi in sorted({t[0] for t in jt}, key=lambda q: (bool(texinfo[q][6]), q)):   # see-through glass last
            mt = [t for t in jt if t[0] == mi]
            arr, w, h, cut, wu, wv, gk = texinfo[mi]
            first = len(vtx)
            for _, _, q, uv in mt:
                for j in range(3):
                    fn = np.cross(q[1]-q[0], q[2]-q[0]); fn /= max(np.linalg.norm(fn), 1e-9)
                    nn = sum(f for f in acc[(jk, key(q[j]))] if f@fn > 0.5)   # weld only similar faces (back-to-back would cancel)
                    nn = Rn@(nn/max(np.linalg.norm(nn), 1e-9)); nn /= max(np.linalg.norm(nn), 1e-9)
                    p = Mi@np.r_[q[j], 1.0]
                    nb = ','.join(str(int(round(cc*126)) & 255) for cc in nn)
                    vtx.append('{{{%d,%d,%d},0,{%d,%d},{%s,255}}},' % (round(p[0]), round(p[1]), round(p[2]),
                               round(uv[j][0]*w*32), round((1-uv[j][1])*h*32), nb))
            gfx.append('gsDPSetRenderMode(G_RM_FOG_SHADE_A,G_RM_AA_ZB_XLU_SURF2),' if gk else 'gsDPSetRenderMode(G_RM_FOG_SHADE_A,G_RM_AA_ZB_TEX_EDGE2),' if cut else 'gsDPSetRenderMode(G_RM_FOG_SHADE_A,G_RM_AA_ZB_OPA_SURF2),')
            gfx += [f'gsDPSetTextureImage_Dolphin(G_IM_FMT_RGBA,G_IM_SIZ_32b,{w},{h},{arr}),',
                    f'gsDPSetTile_Dolphin(G_DOLPHIN_TLUT_DEFAULT_MODE,0,0,{wu},{wv},0,0),']
            n = len(mt)*3
            for b in range(0, n, 30):
                kk = min(30, n-b); gfx.append(f'gsSPVertex(&pc_furn_{gc}_j{jk}_v[{first+b}],{kk},0),')
                gfx += [f'gsSP1Triangle({j},{j+1},{j+2},0),' for j in range(0, kk, 3)]
        gfx += ['gsSPEndDisplayList(),', '};']
        if vtx: out += [f'static Vtx pc_furn_{gc}_j{jk}_v[] ATTRIBUTE_ALIGN(32) = {{'] + vtx + ['};']
        out += gfx
        if jk in hands and hands[jk][1]:
            g = hands[jk][1]
            out.insert(1, f'extern Gfx {g}[];')
            patch.append(f'    {{ Gfx* g = {g}; gSPDisplayList(g++, pc_furn_{gc}_j{jk}); gSPEndDisplayList(g++); }}')
        elif tank and not jt and joints[jk]['flags'] != 'cKF_JOINT_FLAG_DISP_OPA' and jk not in crit_hide:
            pass   # keep the GC translucent glass / water joint
        else:
            patch.append(f'    cKF_je_r_{skel_base(gc)}_tbl[{jk}].model = pc_furn_{gc}_j{jk};')
    for jk, g in drawn.items():
        if jk in hands: continue
        # GC glass / face the profile draws itself: hidden, the NL body has its own
        out.insert(1, f'extern Gfx {g}[];')
        patch.append(f'    {{ Gfx* g = {g}; gSPEndDisplayList(g++); }}')
    out.append(f'static void pc_furn_{gc}_apply(void) {{')
    out += patch + ['}']
    (SRC/f'src/furniture/pc_furn_{gc}.c_inc').write_text('\n'.join(out)+'\n')
    reg_p = ROOT/'furn_work'/'furn_registry.json'
    r = json.load(open(reg_p))
    r[gc] = {kk: v for kk, v in (('nl', nl), ('yaw', yaw), ('tint', tint), ('skel', skel_base(gc))) if v}
    json.dump(r, open(reg_p, 'w'), indent=1)
    gen_furn.write_master(r)
    print('ok skel', gc, nl, 'scale', round(k, 2), 'joints', {kk: sum(1 for t in tris if t[1] == kk) for kk in geo}, 'nl nodes', dict(nodes))

if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2], float(sys.argv[3]) if len(sys.argv) > 3 else 0.0)
