"""Colour signatures of GC furniture models vs NL models (area-weighted texture colour at triangle centroids).
Used to pick New Leaf remake colour variants and to reject swaps that read as a different item."""
import re, json, struct
from pathlib import Path
import numpy as np
from PIL import Image
import native_models as nm

ROOT = Path(__file__).resolve().parent
FW = ROOT/'furn_work'/'nl_ftr'
RM = ROOT/'furn_work'/'remake'
_TOK = re.compile(r'(gs\w+)\(([^)]*)\)')

def _lab(rgb):
    c = np.asarray(rgb, float)/255.0
    c = np.where(c > 0.04045, ((c+0.055)/1.055)**2.4, c/12.92)
    M = np.array([[0.4124, 0.3576, 0.1805], [0.2126, 0.7152, 0.0722], [0.0193, 0.1192, 0.9505]])
    xyz = c@M.T/np.array([0.9505, 1.0, 1.089])
    f = np.where(xyz > 0.008856, np.cbrt(xyz), 7.787*xyz+16/116)
    return np.stack([116*f[..., 1]-16, 500*(f[..., 0]-f[..., 1]), 200*(f[..., 1]-f[..., 2])], -1)

_texcache = {}
def _gc_tex(sym, fmt, bits, w, h, pal):
    k = (sym, pal)
    if k not in _texcache:
        data = nm.blob(sym)
        if fmt == 'CI': im = nm.decode_ci(data, w, h, nm.palette(pal), bits)
        else: im = Image.new('RGBA', (w, h), (128, 128, 128, 255))
        _texcache[k] = im.convert('RGBA')
    return _texcache[k]

def gc_samples(item):
    """[(rgb, area)] for int_<item> (all display lists in the model file)."""
    src = (ROOT/f'ACGC-PC-Port/src/data/model/int_{item}.c').read_text()
    out = []
    for m in re.finditer(r'\bGfx\s+(\w+)\[\]\s*=\s*\{(.*?)\n\};', src, re.S):
        pal = None; tex = None; buf = {}; pending = 0; prim = (255, 255, 255)
        def emit(a, b, c):
            if tex is None or pal is None: return
            try: t = [buf[i] for i in (a, b, c)]
            except KeyError: return
            P = np.array([x[:3] for x in t], float); area = np.linalg.norm(np.cross(P[1]-P[0], P[2]-P[0]))/2
            if area <= 0: return
            im = _gc_tex(tex[4], tex[0], tex[1], tex[2], tex[3], pal)
            for wts in ((1/3, 1/3, 1/3), (.6, .2, .2), (.2, .6, .2), (.2, .2, .6)):
                u = sum(wt*x[3] for wt, x in zip(wts, t)); v = sum(wt*x[4] for wt, x in zip(wts, t))
                px = im.getpixel((int(u) % tex[2], int(v) % tex[3]))
                if px[3] > 64: out.append((px[:3], area/4))
        for op, args in _TOK.findall(m.group(2)):
            args = [a.strip() for a in args.split(',')]
            if op == 'gsDPLoadTLUT_Dolphin': pal = args[3]
            elif op == 'gsDPSetTextureImage_Dolphin':
                tex = (args[0].replace('G_IM_FMT_', ''), int(args[1].replace('G_IM_SIZ_', '').rstrip('b')), int(args[2]), int(args[3]), args[4])
            elif op == 'gsSPVertex':
                a = re.match(r'&?(\w+)(?:\[(\d+)\])?', args[0]); arr, st = a.group(1), int(a.group(2) or 0)
                try: vs = nm.vertices(arr)
                except KeyError: continue
                for k in range(int(args[1])):
                    x, y, z, _f, u, v = vs[st+k][:6]; buf[int(args[2])+k] = (x, y, z, u/32.0, v/32.0)
            elif op == 'gsSP1Triangle': emit(*map(int, args[:3]))
            elif op == 'gsSP2Triangles': emit(*map(int, args[:3])); emit(*map(int, args[4:7]))
            elif op == 'gsSPNTrianglesInit_5b':
                pending = int(args[0]); idx = list(map(int, args[1:10]))
                for k in range(0, 9, 3):
                    if pending > 0: emit(*idx[k:k+3]); pending -= 1
            elif op == 'gsSPNTriangles_5b':
                idx = list(map(int, args[:12]))
                for k in range(0, 12, 3):
                    if pending > 0: emit(*idx[k:k+3]); pending -= 1
    return out

def nl_dir(nl):
    return FW/f'int_{nl}' if (FW/f'int_{nl}').exists() else FW/nl

def nl_tex_path(nl, tname, variants=None):
    """variants: {'base': '03', 'fabric': '05'} picks /Ftr/Remake textures for base_00/fabric_00."""
    if variants:
        for part, num in variants.items():
            if tname == f'{part}_00' and (RM/nl/f'{part}_{num}.png').exists(): return RM/nl/f'{part}_{num}.png'
    p = nl_dir(nl)/f'{tname}.png'
    return p if p.exists() else next(nl_dir(nl).glob('*.png'))

def nl_samples(nl, variants=None):
    d = json.load(open(next(nl_dir(nl).glob('*.json'))))
    out = []
    for m in d['meshes']:
        im = Image.open(nl_tex_path(nl, m['texture'], variants)).convert('RGBA'); w, h = im.size
        at = m['alphaTest']; thr = at['testReference'] if at['isTestEnabled'] else -1
        vs = m['vertices']
        for i in range(0, len(vs)-2, 3):
            P = np.array([vs[i+j]['position'] for j in range(3)], float)
            area = np.linalg.norm(np.cross(P[1]-P[0], P[2]-P[0]))/2
            if area <= 0: continue
            for wts in ((1/3, 1/3, 1/3), (.6, .2, .2), (.2, .6, .2), (.2, .2, .6)):
                u = sum(wt*vs[i+j]['uv'][0] for j, wt in enumerate(wts)); v = sum(wt*vs[i+j]['uv'][1] for j, wt in enumerate(wts))
                px = im.getpixel((int(u*w) % w, int((1-v)*h) % h))
                if px[3] > thr: out.append((px[:3], area/4))
    return out

def signature(samples, bins=8):
    if not samples: return np.zeros((0, 3)), np.zeros(0)
    c = np.array([s[0] for s in samples], float); w = np.array([s[1] for s in samples], float)
    q = (c//(256//bins)).astype(int); key = q[:, 0]*bins*bins+q[:, 1]*bins+q[:, 2]
    labs, ws = [], []
    for k in np.unique(key):
        sel = key == k; ws.append(w[sel].sum()); labs.append(_lab((c[sel]*w[sel, None]).sum(0)/w[sel].sum()))
    ws = np.array(ws)/sum(ws); return np.array(labs), ws

def distance(sa, sb):
    """Weighted chamfer distance in Lab between two signatures (lower = closer). ~10 close, >25 different."""
    (la, wa), (lb, wb) = sa, sb
    if len(wa) == 0 or len(wb) == 0: return 99.0
    D = np.linalg.norm(la[:, None]-lb[None], axis=-1)
    return float((D.min(1)*wa).sum()+(D.min(0)*wb).sum())/2

def remake_options(nl):
    parts = {}
    for p in sorted((RM/nl).glob('*_[0-9][0-9].png')):
        part, num = p.stem.rsplit('_', 1); parts.setdefault(part, []).append(num)
    return parts

def best_variant(gc, nl):
    """Returns (variants dict or None, distance)."""
    import itertools
    sg = signature(gc_samples(gc))
    best = (None, distance(sg, signature(nl_samples(nl))))
    parts = remake_options(nl)
    if parts:
        names = list(parts)
        for combo in itertools.product(*[parts[n] for n in names]):
            v = dict(zip(names, combo)); dd = distance(sg, signature(nl_samples(nl, v)))
            if dd < best[1]: best = (v, dd)
    return best

if __name__ == '__main__':
    import sys
    reg = json.load(open(ROOT/'furn_work/furn_registry.json'))
    for gc, nl in reg.items():
        if len(sys.argv) > 1 and gc not in sys.argv[1:]: continue
        nlname = nl if isinstance(nl, str) else nl['nl']
        base = distance(signature(gc_samples(gc)), signature(nl_samples(nlname)))
        print(f'{gc:24s} {nlname:22s} default {base:5.1f}')
