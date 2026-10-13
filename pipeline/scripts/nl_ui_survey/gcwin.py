"""Render the GameCube pocket window (inv_mwin) straight from foresta.rel + the decomp display lists.

Only the GBI commands used by inv_mwin.c are interpreted. Output is in 320x240 UI space, y up, centred.
"""
import os as _os
_ROOT = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
if _os.path.basename(_ROOT) == 'nl_ui_survey': _ROOT = _os.path.dirname(_ROOT)
os = _os

import re, struct, math
import numpy as np
from PIL import Image

REPO = os.path.join(_ROOT, 'ACGC-PC-Port') + '/'
REL = open(os.path.join(_ROOT, 'foresta.rel'), 'rb').read()


def asset_table():
    t = {}
    for line in open(REPO + 'pc/src/pc_assets.c', encoding='utf-8', errors='ignore'):
        m = re.match(r'\s*\{"[^"]+",\s*(\w+),\s*(0x[0-9A-Fa-f]+),\s*(0x[0-9A-Fa-f]+),\s*(\d)', line)
        if m: t[m.group(1)] = (int(m.group(3), 16), int(m.group(2), 16), int(m.group(4)))
    import glob as _g
    for line in (l for f in _g.glob(REPO + 'src/data/model/*.c') for l in open(f, errors='ignore') if 'pc_load_asset(' in l):
        m = re.search(r'pc_load_asset\("[^"]+",\s*(\w+),\s*(0x[0-9A-Fa-f]+),\s*(0x[0-9A-Fa-f]+),\s*(\d)', line)
        if m: t[m.group(1)] = (int(m.group(3), 16), int(m.group(2), 16), int(m.group(4)))
    return t


ASSETS = asset_table()


def data(sym):
    off, size, src = ASSETS[sym]
    assert src == 0, sym
    return REL[off:off + size]


def rgb5a3(v):
    if v & 0x8000:
        return (((v >> 10) & 31) * 255 // 31, ((v >> 5) & 31) * 255 // 31, (v & 31) * 255 // 31, 255)
    return (((v >> 8) & 15) * 17, ((v >> 4) & 15) * 17, (v & 15) * 17, ((v >> 12) & 7) * 255 // 7)


def decode(fmt, siz, w, h, raw, pal=None):
    out = np.zeros((h, w, 4), float)
    if siz == 4:
        bw, bh, bpb = 8, 8, 32
    else:
        bw, bh, bpb = (8, 4, 32) if siz == 8 else (4, 4, 32)
    i = 0
    for by in range(0, h, bh):
        for bx in range(0, w, bw):
            blk = raw[i:i + bpb]; i += bpb
            for y in range(bh):
                for x in range(bw):
                    if siz == 4:
                        b = blk[(y * bw + x) // 2]; v = (b >> 4) if x % 2 == 0 else (b & 15)
                        if fmt == 'CI': c = pal[v]
                        else: c = (v * 17,) * 3 + (v * 17,)
                    else:
                        if fmt == 'IA' and siz == 8:
                            b = blk[y * bw + x]; l = (b & 15) * 17; c = (l, l, l, (b >> 4) * 17)
                        elif fmt == 'IA':
                            a, l = blk[(y * bw + x) * 2], blk[(y * bw + x) * 2 + 1]; c = (l, l, l, a)
                        elif fmt == 'I':
                            l = blk[y * bw + x]; c = (l, l, l, l)
                        else:
                            c = pal[blk[y * bw + x]]
                    if by + y < h and bx + x < w: out[by + y, bx + x] = np.array(c) / 255
    return out


def parse_models(path='src/data/model/inv_mwin.c'):
    src = open(REPO + path).read()
    models = {}
    for m in re.finditer(r'Gfx (\w+)\[\] = \{(.*?)\};', src, re.S):
        cmds = []
        for c in re.finditer(r'(gs\w+)\((.*?)\),\n', m.group(2) + '\n', re.S):
            args = [a.strip() for a in c.group(2).replace('\n', ' ').split(',')]
            cmds.append((c.group(1), args))
        models[m.group(1)] = cmds
    return models


MODELS = parse_models()
def load_vtx(sym):
    raw = data(sym)
    return [struct.unpack_from('>hhhHhhBBBB', raw, i * 16) for i in range(len(raw) // 16)]


VTX_CACHE = {}
WRAP = {'GX_CLAMP': 0, 'GX_REPEAT': 1, 'GX_MIRROR': 2}


class GCWin:
    def __init__(s, scale=3, shirt=None, shirt_scroll=(0, 0)):
        s.k = scale; s.W, s.H = 320 * scale, 240 * scale
        s.img = np.zeros((s.H, s.W, 4)); s.cov = np.zeros((s.H, s.W))   # cov = window-shape alpha
        s.tlut = {}; s.timg = None; s.tiles = {}; s.vbuf = [None] * 64
        s.prim = np.ones(4); s.env = np.ones(4); s.mode = 'shirt'
        s.shirt = shirt; s.scroll = shirt_scroll; s.wscale = 1.0; s.models = MODELS

    def tex_sample(s, tile, u, v):
        T, ws, wt = s.tiles[tile]
        h, w = T.shape[:2]

        def wr(x, mode, n):
            x = x / n
            if mode == 1: x = x % 1.0
            elif mode == 2:
                x = x % 2.0; x = np.where(x > 1, 2 - x, x)
            else: x = np.clip(x, 0, 1)
            return np.clip((x * n).astype(int), 0, n - 1)
        return T[wr(v, wt, h), wr(u, ws, w)]

    def tri(s, a, b, c):
        P = [s.vbuf[i] for i in (a, b, c)]
        X = np.array([p[0] for p in P], float) * s.k * s.wscale + s.W / 2
        Y = -np.array([p[1] for p in P], float) * s.k * s.wscale + s.H / 2
        x0, x1 = int(max(0, X.min())), int(min(s.W, X.max() + 1))
        y0, y1 = int(max(0, Y.min())), int(min(s.H, Y.max() + 1))
        if x0 >= x1 or y0 >= y1: return
        gx, gy = np.meshgrid(np.arange(x0, x1) + .5, np.arange(y0, y1) + .5)
        d = (Y[1] - Y[2]) * (X[0] - X[2]) + (X[2] - X[1]) * (Y[0] - Y[2])
        if abs(d) < 1e-9: return
        l0 = ((Y[1] - Y[2]) * (gx - X[2]) + (X[2] - X[1]) * (gy - Y[2])) / d
        l1 = ((Y[2] - Y[0]) * (gx - X[2]) + (X[0] - X[2]) * (gy - Y[2])) / d
        l2 = 1 - l0 - l1
        inside = (l0 >= -1e-6) & (l1 >= -1e-6) & (l2 >= -1e-6)
        if not inside.any(): return
        U = sum(l * (p[4] / 32.0) for l, p in zip((l0, l1, l2), P))
        V = sum(l * (p[5] / 32.0) for l, p in zip((l0, l1, l2), P))
        if s.mode == 'shirt':
            piece = s.tex_sample(1, U, V)
            al = piece[..., 3]
            if s.shirt is not None:
                sh = s.shirt; n = sh.shape[0]
                col = sh[((V + s.scroll[1]).astype(int)) % n, ((U + s.scroll[0]).astype(int)) % n][..., :3]
            else:
                col = np.ones(U.shape + (3,)) * 0.8
            s.cov[y0:y1, x0:x1] = np.maximum(s.cov[y0:y1, x0:x1], al * inside)
        else:
            t = s.tex_sample(0, U, V)
            if s.mode == 'tex':
                col = t[..., :3]; al = t[..., 3]
            elif s.mode == 'prim':
                col = np.broadcast_to(s.prim[:3], U.shape + (3,)); al = t[..., 3] * s.prim[3]
            elif s.mode == 'primtex':
                col = s.prim[:3] * t[..., :3]; al = t[..., 3] * s.prim[3]
            else:  # lerp env->prim by texel
                col = s.env[:3] + (s.prim[:3] - s.env[:3]) * t[..., :3]; al = t[..., 3]
        al = al * inside
        D = s.img[y0:y1, x0:x1]
        D[..., :3] = col * al[..., None] + D[..., :3] * (1 - al[..., None])
        D[..., 3] = al + D[..., 3] * (1 - al)

    def run(s, name):
        tris_left = 0
        for cmd, a in s.models[name]:
            if cmd == 'gsSPDisplayList': s.run(a[0]) if a[0] in s.models else None
            elif cmd == 'gsDPSetPrimColor': s.prim = np.array([int(x) for x in a[2:6]]) / 255
            elif cmd == 'gsDPSetEnvColor': s.env = np.array([int(x) for x in a[0:4]]) / 255
            elif cmd == 'gsDPLoadTLUT_Dolphin':
                raw = data(a[3]); s.tlut[int(a[0])] = [rgb5a3(struct.unpack_from('>H', raw, i * 2)[0]) for i in range(int(a[1]))]
            elif cmd == 'gsDPSetTextureImage_Dolphin':
                s.timg = (a[0].split('_')[-1], int(a[1].split('_')[-1].rstrip('b')), int(a[2]), int(a[3]), a[4])
            elif cmd == 'gsDPSetTile_Dolphin':
                fmt, siz, w, h, sym = s.timg; tile, tl = int(a[1]), int(a[2])
                T = decode(fmt, siz, w, h, data(sym), s.tlut.get(tl))
                s.tiles[tile] = (T, WRAP[a[3]], WRAP[a[4]])
            elif cmd == 'gsSPVertex':
                ref = a[0]; m = re.match(r'&?(\w+)(?:\[(\d+)\])?', ref)
                base = int(m.group(2) or 0); n, dst = int(a[1]), int(a[2])
                if m.group(1) not in VTX_CACHE: VTX_CACHE[m.group(1)] = load_vtx(m.group(1))
                V = VTX_CACHE[m.group(1)]
                for i in range(n): s.vbuf[dst + i] = V[base + i]
            elif cmd == 'gsSP2Triangles':
                v = [int(x) for x in a]; s.tri(v[0], v[1], v[2]); s.tri(v[4], v[5], v[6])
            elif cmd == 'gsSP1Triangle':
                v = [int(x) for x in a]; s.tri(v[0], v[1], v[2])
            elif cmd in ('gsSPNTrianglesInit_5b', 'gsSPNTriangles_5b'):
                vals = [int(x) for x in a]
                if cmd == 'gsSPNTrianglesInit_5b': tris_left = vals[0]; vals = vals[1:]
                for i in range(0, len(vals), 3):
                    if tris_left <= 0: break
                    s.tri(*vals[i:i + 3]); tris_left -= 1
            elif cmd == 'gsDPSetCombineLERP':
                j = ','.join(a)
                if j.startswith('0,0,0,TEXEL0,0,0,0,TEXEL0'): s.mode = 'tex'
                elif j.startswith('0,0,0,PRIMITIVE,0,0,0,TEXEL0'): s.mode = 'prim'
                elif j.startswith('0,0,0,PRIMITIVE,PRIMITIVE,0,TEXEL0'): s.mode = 'primtex'
                elif j.startswith('PRIMITIVE,ENVIRONMENT,TEXEL0'): s.mode = 'lerp'

    def rgba(s):
        a = s.img[..., 3:4]
        rgb = np.where(a > 0, s.img[..., :3] / np.maximum(a, 1e-6), 0)
        return Image.fromarray((np.clip(np.concatenate([rgb, a], -1), 0, 1) * 255).astype(np.uint8))


def render(shirt_png=None, scale=3, slots=True):
    sh = np.asarray(Image.open(shirt_png).convert('RGBA'), float) / 255 if shirt_png else None
    g = GCWin(scale, sh)
    g.mode = 'shirt'
    g.run('inv_mwin_model')
    if slots:
        g.mode = 'lerp'; g.prim = np.ones(4)
        for i in range(1, 16):
            g.env = np.array([120, 140, 255, 255]) / 255; g.run('inv_mwin_%dbT_model' % i)
        for i in range(1, 11):
            g.env = np.array([255, 90, 90, 255]) / 255; g.run('inv_mwin_%daT_model' % i)
        g.mode = 'primtex'; g.run('inv_mwin_kuni_model'); g.run('inv_mwin_kuni2_model')
    return g


if __name__ == '__main__':
    g = render('gcshirt_000.png')
    g.rgba().save('gc_pocket_frame.png')
    Image.fromarray((g.cov * 255).astype(np.uint8)).save('gc_pocket_mask.png')
