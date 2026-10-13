import struct, math, os, sys
import numpy as np
from PIL import Image


def u32c(b, o):
    return np.array(list(b[o:o + 4]), float) / 255


class Layout:
    def __init__(s, path):
        s.dir = os.path.dirname(os.path.dirname(path))
        b = s.b = open(path, 'rb').read()
        o = struct.unpack_from('<H', b, 6)[0]
        s.tex = []; s.mats = []; s.root = None
        stack = []; last = None
        while o < len(b):
            mg, sz = struct.unpack_from('<4sI', b, o); m = mg.decode()
            if m == 'lyt1':
                s.size = struct.unpack_from('<2f', b, o + 12)
            elif m == 'txl1':
                n = struct.unpack_from('<I', b, o + 8)[0]
                s.tex = [b[o + 12 + struct.unpack_from('<I', b, o + 12 + 4 * i)[0]:].split(b'\0')[0].decode() for i in range(n)]
            elif m == 'mat1':
                n = struct.unpack_from('<I', b, o + 8)[0]
                for i in range(n):
                    s.mats.append(s.mat(o + struct.unpack_from('<I', b, o + 12 + 4 * i)[0]))
            elif m in ('pan1', 'pic1', 'wnd1', 'txt1', 'bnd1', 'prt1'):
                p = s.pane(o, m)
                if stack: stack[-1]['kids'].append(p)
                else: s.root = p
                last = p
            elif m == 'pas1':
                stack.append(last)
            elif m == 'pae1':
                stack.pop()
            o += sz

    def mat(s, o):
        b = s.b
        name = b[o:o + 20].split(b'\0')[0].decode()
        black = u32c(b, o + 20); white = u32c(b, o + 24)
        fl = struct.unpack_from('<I', b, o + 48)[0]; p = o + 52; maps = []
        for i in range(fl & 3):
            idx, f1, f2 = struct.unpack_from('<HBB', b, p); maps.append((idx, f1 & 3, f2 & 3)); p += 4
        srt = []
        for i in range((fl >> 2) & 3):
            srt.append(struct.unpack_from('<5f', b, p)); p += 20
        return dict(name=name, black=black, white=white, maps=maps, srt=srt)

    def pane(s, o, m):
        b = s.b
        fl, org, al = b[o + 8:o + 11]
        nm = b[o + 12:o + 28].split(b'\0')[0].decode()
        p = dict(kind=m, name=nm, vis=fl & 1, org=org, alpha=al / 255, t=struct.unpack_from('<3f', b, o + 36),
                 rot=struct.unpack_from('<3f', b, o + 48)[2], sc=struct.unpack_from('<2f', b, o + 60),
                 size=struct.unpack_from('<2f', b, o + 68), kids=[], o=o)
        q = o + 76
        if m == 'pic1':
            p['vc'] = [u32c(b, q + 4 * i) for i in range(4)]
            p['mat'], ntc = struct.unpack_from('<HH', b, q + 16)
            p['tc'] = [struct.unpack_from('<8f', b, q + 20 + 32 * i) for i in range(ntc)]
        if m == 'wnd1':
            p['ovf'] = struct.unpack_from('<4f', b, q)
            nf = b[q + 16]
            co, fo = struct.unpack_from('<II', b, q + 20)
            c = o + co
            p['vc'] = [u32c(b, c + 4 * i) for i in range(4)]
            p['mat'], ntc = struct.unpack_from('<HB', b, c + 16)
            p['frames'] = []
            for i in range(nf):
                fo_i = struct.unpack_from('<I', b, o + fo + 4 * i)[0]
                mi, flip = struct.unpack_from('<HB', b, o + fo_i)
                p['frames'].append((mi, flip))
        if m == 'txt1':
            p['txtcol'] = (u32c(b, q + 20), u32c(b, q + 24)) if len(b) > q + 28 else None
        return p


TEXC = {}
try:
    import json as _json
    L_FORMATS = {x[1].split('/')[-1][:-6] for x in _json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'report.json'))) if len(x) > 3 and x[1].endswith('.bclim') and x[2] in (0, 12)}
except Exception:
    L_FORMATS = set()


def tex(lay, i):
    n = lay.tex[i][:-6]
    k = (lay.dir, n)
    if k not in TEXC:
        f = os.path.join(lay.dir, 'timg', n + '.png')
        T = np.asarray(Image.open(f).convert('RGBA'), float) / 255 if os.path.exists(f) else None
        TEXC[k] = T
    return TEXC[k]


def sample(T, u, v, ws, wt):
    h, w = T.shape[:2]

    def wrap(x, mode, n):
        if mode == 1:
            x = x % 1.0
        elif mode == 2:
            x = x % 2.0
            x = np.where(x > 1, 2 - x, x)
        else:
            x = np.clip(x, 0, 1)
        return np.clip((x * n).astype(int), 0, n - 1)
    return T[wrap(v, wt, h), wrap(u, ws, w)]


class R:
    def __init__(s, lay, scale=3, hide=(), show=(), alpha_over=None, hook=None):
        s.lay = lay; s.k = scale; W, H = lay.size
        s.W, s.H = int(W * scale), int(H * scale)
        s.img = np.zeros((s.H, s.W, 4)); s.hide = hide; s.show = show; s.ao = alpha_over or {}
        s.hook = hook; s.boxes = {}; s.pattern = True

    def to_screen(s, M, x, y):
        p = M @ np.array([x, y, 1.0])
        return p[0] * s.k + s.W / 2, -p[1] * s.k + s.H / 2

    def quad(s, M, x0, y0, x1, y1, mat, vc, uvs, alpha):
        mt = s.lay.mats[mat]
        P = [s.to_screen(M, x0, y1), s.to_screen(M, x1, y1), s.to_screen(M, x0, y0)]
        sx = [p[0] for p in P]; sy = [p[1] for p in P]
        A = np.array([[sx[1] - sx[0], sx[2] - sx[0]], [sy[1] - sy[0], sy[2] - sy[0]]])
        if abs(np.linalg.det(A)) < 1e-9: return
        cs = P + [(sx[1] + sx[2] - sx[0], sy[1] + sy[2] - sy[0])]
        bx0 = max(0, int(min(c[0] for c in cs))); bx1 = min(s.W, int(max(c[0] for c in cs)) + 1)
        by0 = max(0, int(min(c[1] for c in cs))); by1 = min(s.H, int(max(c[1] for c in cs)) + 1)
        if bx0 >= bx1 or by0 >= by1: return
        X, Y = np.meshgrid(np.arange(bx0, bx1) + .5, np.arange(by0, by1) + .5)
        Ai = np.linalg.inv(A); dx = X - sx[0]; dy = Y - sy[0]
        a = Ai[0, 0] * dx + Ai[0, 1] * dy; c = Ai[1, 0] * dx + Ai[1, 1] * dy
        inside = (a >= 0) & (a < 1) & (c >= 0) & (c < 1)
        if not inside.any(): return
        V = [np.asarray(v) for v in vc]
        col = (V[0] * ((1 - a) * (1 - c))[..., None] + V[1] * (a * (1 - c))[..., None]
               + V[2] * ((1 - a) * c)[..., None] + V[3] * (a * c)[..., None])
        out = np.ones(X.shape + (4,))
        rgb = None
        if mt['maps'] and uvs is not None:
            u0, v0, u1, v1, u2, v2, u3, v3 = uvs
            ub = u0 + (u1 - u0) * a + (u2 - u0) * c
            vb = v0 + (v1 - v0) * a + (v2 - v0) * c
            samples = []
            for mi, (idx, ws, wt) in enumerate(mt['maps']):
                T = tex(s.lay, idx)
                if T is None: samples.append(None); continue
                u, v = ub, vb
                if mi < len(mt['srt']):
                    tx, ty, rr, sxx, syy = mt['srt'][mi]
                    uu = (u - 0.5) * sxx; vv = (v - 0.5) * syy
                    cr, sr = math.cos(math.radians(rr)), math.sin(math.radians(rr))
                    u = uu * cr - vv * sr + 0.5 + tx; v = uu * sr + vv * cr + 0.5 + ty
                samples.append(sample(T, u, v, ws, wt))
            if samples and samples[0] is not None:
                out = samples[0]
                # L4/L8 texture on a flat-colour material: the luminance is the mask
                if s.lay.tex[mt['maps'][0][0]][:-6] in L_FORMATS and np.allclose(mt['black'][:3], mt['white'][:3]):
                    out = out.copy(); out[..., 3] = out[..., :3].mean(-1)
            if len(samples) > 1 and samples[1] is not None and s.pattern:
                lum = samples[1][..., :3].mean(-1, keepdims=True)
                rgb = mt['black'][:3] + (mt['white'][:3] - mt['black'][:3]) * lum
        if rgb is None:
            rgb = mt['black'][:3] + (mt['white'][:3] - mt['black'][:3]) * out[..., :3]
        al = out[..., 3] * mt['white'][3]
        rgb = rgb * col[..., :3]; al = al * col[..., 3] * alpha * inside
        D = s.img[by0:by1, bx0:bx1]
        D[..., :3] = rgb * al[..., None] + D[..., :3] * (1 - al[..., None])
        D[..., 3] = al + D[..., 3] * (1 - al)

    def draw(s, p, M=np.eye(3), alpha=1.0):
        vis = (p['vis'] or p['name'] in s.show) and p['name'] not in s.hide
        if not vis: return
        a = alpha * s.ao.get(p['name'], p['alpha'])
        tx, ty, _ = p['t']; r = math.radians(p['rot']); sx, sy = p['sc']
        L = np.array([[math.cos(r) * sx, -math.sin(r) * sy, tx], [math.sin(r) * sx, math.cos(r) * sy, ty], [0, 0, 1]])
        M2 = M @ L
        w, h = p['size']; hz = p['org'] % 3; vt = p['org'] // 3
        x0 = [0, -w / 2, -w][hz]; y1 = [0, h / 2, h][vt]; x1 = x0 + w; y0 = y1 - h
        s.boxes[p['name']] = (M2, x0, y0, x1, y1)
        if p['kind'] == 'pic1':
            s.quad(M2, x0, y0, x1, y1, p['mat'], p['vc'], p['tc'][0] if p['tc'] else None, a)
        if p['kind'] == 'wnd1':
            s.window(M2, x0, y0, x1, y1, p, a)
        if s.hook: s.hook(s, p, M2, (x0, y0, x1, y1), a)
        for k in p['kids']:
            s.draw(k, M2, a)

    def window(s, M, x0, y0, x1, y1, p, a):
        fr = p['frames']; mats = s.lay.mats

        def tsz(mi):
            T = tex(s.lay, mats[mi]['maps'][0][0]); return T.shape[1], T.shape[0]
        l, r_, t, b_ = p['ovf']
        if len(fr) >= 4:
            (lw, lh), (rw, rh), (lbw, lbh), (rbw, rbh) = [tsz(f[0]) for f in fr[:4]]
            s.quad(M, x0 + lw - l, y0 + lbh - b_, x1 - rw + r_, y1 - lh + t, p['mat'], p['vc'], None, a)

            def fq(mi, flip, X0, Y0, X1, Y1, tw, th):
                u = (X1 - X0) / tw; v = (Y1 - Y0) / th
                if flip == 0: uv = (0, 0, u, 0, 0, v, u, v)
                elif flip == 1: uv = (1, 0, 1 - u, 0, 1, v, 1 - u, v)
                elif flip == 2: uv = (0, 1, u, 1, 0, 1 - v, u, 1 - v)
                else: uv = (1, 1, 1 - u, 1, 1, 1 - v, 1 - u, 1 - v)
                s.quad(M, X0, Y0, X1, Y1, mi, [np.ones(4)] * 4, uv, a)
            fq(fr[0][0], fr[0][1], x0, y1 - lh, x1 - rw, y1, lw, lh)
            fq(fr[1][0], fr[1][1], x1 - rw, y0 + rbh, x1, y1, rw, rh)
            fq(fr[3][0], fr[3][1], x0 + lbw, y0, x1, y0 + rbh, rbw, rbh)
            fq(fr[2][0], fr[2][1], x0, y0, x0 + lbw, y1 - lh, lbw, lbh)

    def save(s, path, bg=(90, 110, 120)):
        I = s.img; B = np.array(bg, float) / 255
        rgb = I[..., :3] + B * (1 - I[..., 3:4])
        Image.fromarray((np.clip(rgb, 0, 1) * 255).astype(np.uint8)).save(path)

    def rgba(s):
        a = s.img[..., 3:4]
        rgb = np.where(a > 0, s.img[..., :3] / np.maximum(a, 1e-6), 0)
        return Image.fromarray((np.clip(np.concatenate([rgb, a], -1), 0, 1) * 255).astype(np.uint8))


if __name__ == '__main__':
    L = Layout(sys.argv[1]); r = R(L, 3); r.draw(L.root); r.save(sys.argv[2])
    for m in L.mats:
        print(m['name'], m['maps'], m['srt'], (m['black'] * 255).astype(int), (m['white'] * 255).astype(int))
