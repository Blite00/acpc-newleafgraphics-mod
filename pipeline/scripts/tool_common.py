"""Shared loaders for the New Leaf tool swap: GC display lists (with their palettes) and NL tool meshes."""
import json, re
from pathlib import Path
import numpy as np
from PIL import Image
import native_models as nm

ROOT = Path(__file__).resolve().parent
SRC = ROOT/'tool_source'
MODEL = ROOT/'ACGC-PC-Port/src/data/model'
_parsed = {}
_tex = {}


def _palettes(path):
    """{dl_name: {texture symbol: palette symbol}} from the order of LoadTLUT / SetTextureImage commands"""
    src = Path(path).read_text()
    out = {}
    for m in re.finditer(r'\bGfx\s+(\w+)\[\]\s*=\s*\{(.*?)\n\};', src, re.S):
        pal = None; mp = {}
        for op, args in re.findall(r'(gs\w+)\(([^)]*)\)', m.group(2)):
            a = [x.strip() for x in args.split(',')]
            if op == 'gsDPLoadTLUT_Dolphin': pal = a[3]
            elif op == 'gsDPSetTextureImage_Dolphin': mp[a[4]] = pal
        out[m.group(1)] = mp
    return out


def gc_dl(path, dl, default_pal=None):
    """[(tris, PIL texture)] of a GC display list; tri = [(xyz, uv(v up), normal)]"""
    path = Path(path)
    if path not in _parsed: _parsed[path] = (nm.parse_model_file(path), _palettes(path))
    tris, pals = _parsed[path][0].get(dl, []), _parsed[path][1].get(dl, {})
    groups = {}
    for t in tris:
        sym, fmt, bits, w, h, vs = t
        pal = pals.get(sym) or default_pal
        key = (sym, pal)
        if key not in _tex:
            try:
                if fmt == 'CI': im = nm.decode_ci(nm.blob(sym), w, h, nm.palette(pal), bits)
                else: im = Image.new('RGBA', (w, h), (200, 200, 200, 255))
            except Exception:
                im = Image.new('RGBA', (w, h), (255, 0, 255, 255))
            _tex[key] = im
        P = np.array([v[:3] for v in vs], float)
        n = np.cross(P[1]-P[0], P[2]-P[0]); n = n/(np.linalg.norm(n) or 1)
        groups.setdefault(key, []).append([(P[i], (vs[i][3]/w, 1-vs[i][4]/h), n) for i in range(3)])
    return [(g, _tex[k]) for k, g in groups.items()]


def gc_points(groups):
    return np.array([v[0] for g, _ in groups for t in g for v in t], float)


def nl_meshes(name, model=None):
    """New Leaf meshes of tool_source/<name>/<model>.json as [(mesh dict, PIL texture)]"""
    d = json.load(open(SRC/name/f'{model or name}.json'))
    out = []
    for m in d['meshes']:
        tp = SRC/name/f"{m['texture']}.png"
        if not tp.exists(): tp = sorted((SRC/name).glob('*.png'))[0]
        out.append((m, Image.open(tp).convert('RGBA')))
    return out


def nl_groups(meshes, xf):
    """meshes [(mesh, tex)] -> render groups, positions passed through xf(np array Nx3) -> Nx3"""
    groups = []
    for m, tex in meshes:
        V = m['vertices']
        P = xf(np.array([v['position'] for v in V], float))
        N = xf(np.array([v['position'] for v in V], float)+np.array([v.get('normal', [0, 1, 0]) for v in V], float))-P
        tris = []
        for i in range(0, len(V)-2, 3):
            tris.append([(P[i+k], (V[i+k]['uv'][0], V[i+k]['uv'][1]), N[i+k]) for k in range(3)])
        groups.append((tris, tex))
    return groups


_TOK = re.compile(r'(gs\w+)\(([^)]*)\)')
def gc_dl_skinned(path, dl, own, mtx_world, default_pal=None):
    """like gc_dl but places every vertex with the matrix it was loaded under:
    gsSPMatrix(anime_6_mdl[k]) -> mtx_world[k] (skeleton matrix k = k-th drawn joint), otherwise `own` (4x4)."""
    path = Path(path)
    src = path.read_text()
    m = re.search(r'\bGfx\s+' + re.escape(dl) + r'\[\]\s*=\s*\{(.*?)\n\};', src, re.S)
    cur = own; pal = default_pal; tex = None; buf = {}; groups = {}; pending = 0
    def emit(a, b, c):
        if tex is None: return
        try: vs = [buf[i] for i in (a, b, c)]
        except KeyError: return
        sym, fmt, bits, w, h = tex
        key = (sym, pal)
        if key not in _tex:
            try: _tex[key] = nm.decode_ci(nm.blob(sym), w, h, nm.palette(pal), bits) if fmt == 'CI' else Image.new('RGBA', (w, h), (200, 200, 200, 255))
            except Exception: _tex[key] = Image.new('RGBA', (w, h), (255, 0, 255, 255))
        P = np.array([v[0] for v in vs]); n = np.cross(P[1]-P[0], P[2]-P[0]); n = n/(np.linalg.norm(n) or 1)
        groups.setdefault(key, []).append([(v[0], (v[1]/w, 1-v[2]/h), n) for v in vs])
    for op, args in _TOK.findall(m.group(1)):
        a = [x.strip() for x in args.split(',')]
        if op == 'gsSPMatrix':
            mm = re.match(r'&?anime_6_mdl(?:\[(\d+)\])?', a[0])
            cur = mtx_world[int(mm.group(1) or 0)] if mm else own
        elif op == 'gsDPLoadTLUT_Dolphin': pal = a[3]
        elif op == 'gsDPSetTextureImage_Dolphin':
            tex = (a[4], a[0].replace('G_IM_FMT_', ''), int(a[1].replace('G_IM_SIZ_', '').rstrip('b')), int(a[2]), int(a[3]))
        elif op == 'gsSPVertex':
            mm = re.match(r'&?(\w+)(?:\[(\d+)\])?', a[0]); arr, st = mm.group(1), int(mm.group(2) or 0)
            n, v0 = int(a[1]), int(a[2]); vs = nm.vertices(arr)
            for k in range(n):
                x, y, z, _f, u, v = vs[st+k][:6]
                p = cur@np.array([x, y, z, 1.0])
                buf[v0+k] = (p[:3], u/32.0, v/32.0)
        elif op == 'gsSP1Triangle': emit(*map(int, a[:3]))
        elif op == 'gsSP2Triangles': emit(*map(int, a[:3])); emit(*map(int, a[4:7]))
        elif op == 'gsSPNTrianglesInit_5b':
            pending = int(a[0]); idx = list(map(int, a[1:10]))
            for k in range(0, 9, 3):
                if pending > 0: emit(*idx[k:k+3]); pending -= 1
        elif op == 'gsSPNTriangles_5b':
            idx = list(map(int, a[:12]))
            for k in range(0, 12, 3):
                if pending > 0: emit(*idx[k:k+3]); pending -= 1
    return [(g, _tex[k]) for k, g in groups.items()]


def gc_skeleton_groups(path, skel, anim, frame=0, root=np.eye(4)):
    """all GC display lists of a skeleton posed by anim at frame, in the skeleton root frame"""
    import ckf
    jt = ckf.joints(path, skel)
    a = ckf.Anim(path, anim, len(jt)) if isinstance(anim, str) else anim
    rt, r = a.sample(frame); W = [root@w for w in ckf.world(jt, rt, r)]
    drawn = [W[i] for i, j in enumerate(jt) if j[0]]
    out = []
    for i, j in enumerate(jt):
        if j[0]: out += gc_dl_skinned(path, j[0], W[i], drawn)
    return out, W, jt
