"""Bake New Leaf surface paint onto the GameCube building models' own texture layouts.

For every native texel that a triangle uses, find the nearest matching surface of the
(aligned) New Leaf model and copy its colour. Output is a Dolphin-style texture-pack
replacement (RGBA DDS, keyed by the original texture + palette hash), so native geometry,
UVs, animation, collision and lighting stay untouched and every season/colour palette
gets its own replacement.
"""
import json, struct
from pathlib import Path
import numpy as np
from PIL import Image
import native_models as nm

ROOT = Path(__file__).resolve().parent
MASK = (1 << 64)-1
P1, P2, P3, P4, P5 = 0x9e3779b185ebca87, 0xc2b2ae3d27d4eb4f, 0x165667b19e3779f9, 0x85ebca77c2b2ae63, 0x27d4eb2f165667c5
def _rot(v, n): return ((v << n) | (v >> (64-n))) & MASK
def _rnd(a, v): return _rot((a+v*P2) & MASK, 31)*P1 & MASK
def xxh(b):
    n = len(b); pos = 0
    if n >= 32:
        vs = [(P1+P2) & MASK, P2, 0, (-P1) & MASK]
        while pos <= n-32:
            vs = [_rnd(a, v) for a, v in zip(vs, struct.unpack_from('<4Q', b, pos))]; pos += 32
        h = sum(_rot(v, r) for v, r in zip(vs, [1, 7, 12, 18])) & MASK
        for v in vs: h = ((h ^ _rnd(0, v))*P1+P4) & MASK
    else: h = P5
    h = (h+n) & MASK
    while pos+8 <= n:
        h = (_rot(h ^ _rnd(0, int.from_bytes(b[pos:pos+8], 'little')), 27)*P1+P4) & MASK; pos += 8
    if pos+4 <= n:
        h = (_rot(h ^ ((int.from_bytes(b[pos:pos+4], 'little')*P1) & MASK), 23)*P2+P3) & MASK; pos += 4
    while pos < n:
        h = (_rot(h ^ ((b[pos]*P5) & MASK), 11)*P1) & MASK; pos += 1
    h ^= h >> 33; h = h*P2 & MASK; h ^= h >> 29; h = h*P3 & MASK; h ^= h >> 32
    return f'{h:016x}'
assert xxh(b'') == 'ef46db3751d8e999' and xxh(bytes(range(32))) == 'cbf59c5116ff32b4'

def dds_rgba(im):
    w, h = im.size
    header = bytearray(128); header[:4] = b'DDS '
    struct.pack_into('<7I', header, 4, 124, 0x100f, h, w, w*4, 0, 1)
    struct.pack_into('<8I', header, 76, 32, 0x41, 0, 32, 0xff, 0xff00, 0xff0000, 0xff000000)
    struct.pack_into('<I', header, 108, 0x1000)
    return bytes(header)+im.convert('RGBA').tobytes()

def pack_name(tex_symbol, fmt, bits, w, h, pal_symbol):
    data = nm.blob(tex_symbol)
    pal = nm.blob(pal_symbol)
    idx = nm.ci_indices(data, bits)
    ph = xxh(pal[min(idx)*2:(max(idx)+1)*2])
    code = 8 if bits == 4 else 9
    return f'tex1_{w}x{h}_{xxh(data)}_{ph}_{code}.dds'

# ---------- geometry ----------
def closest_points(P, A, B, C):
    """Ericson closest point on triangle; P (N,3), A/B/C (T,3) -> dist2 (N,T), bary (N,T,3)."""
    P = P[:, None, :]
    ab = B-A; ac = C-A; ap = P-A
    d1 = (ab*ap).sum(-1); d2 = (ac*ap).sum(-1)
    bp = P-B; d3 = (ab*bp).sum(-1); d4 = (ac*bp).sum(-1)
    cp = P-C; d5 = (ab*cp).sum(-1); d6 = (ac*cp).sum(-1)
    vc = d1*d4-d3*d2; vb = d5*d2-d1*d6; va = d3*d6-d5*d4
    denom = va+vb+vc; denom = np.where(np.abs(denom) < 1e-12, 1e-12, denom)
    v = vb/denom; w = vc/denom
    u = 1-v-w
    # region clamps (approximate but robust): clamp barycentrics to the triangle
    u = np.clip(u, 0, None); v = np.clip(v, 0, None); w = np.clip(w, 0, None)
    s = u+v+w; s = np.where(s < 1e-12, 1, s)
    u, v, w = u/s, v/s, w/s
    Q = u[..., None]*A+v[..., None]*B+w[..., None]*C
    d2 = ((Q-P)**2).sum(-1)
    return d2, np.stack([u, v, w], -1)

def tri_normals(A, B, C):
    n = np.cross(B-A, C-A); l = np.linalg.norm(n, axis=1, keepdims=True); l[l < 1e-9] = 1
    return n/l

class Donor:
    """A New Leaf model aligned to native space (positions already transformed)."""
    def __init__(self, tris, textures):
        self.A = np.array([t[0][0] for t in tris], float); self.B = np.array([t[1][0] for t in tris], float)
        self.C = np.array([t[2][0] for t in tris], float)
        self.uv = np.array([[v[1] for v in t[:3]] for t in tris], float)    # (T,3,2)
        self.tex = [t[3] for t in tris]                                     # texture key per triangle
        self.N = tri_normals(self.A, self.B, self.C)

def sample(img, uv, wrap_u, wrap_v):
    """Bilinear sample of PIL image (RGBA ndarray) at uv (N,2) in 0..1 donor space; mirror(3)/repeat(2)/clamp."""
    h, w = img.shape[:2]
    def wr(x, mode):
        if mode == 3: x = np.mod(x, 2); return np.where(x > 1, 2-x, x)
        if mode == 2: return np.mod(x, 1)
        return np.clip(x, 0, 1)
    u = wr(uv[:, 0], wrap_u)*w-0.5; v = (1-wr(uv[:, 1], wrap_v))*h-0.5
    x0 = np.floor(u).astype(int); y0 = np.floor(v).astype(int); fx = (u-x0)[:, None]; fy = (v-y0)[:, None]
    def px(x, y): return img[np.clip(y, 0, h-1), np.clip(x, 0, w-1)].astype(float)
    return (px(x0, y0)*(1-fx)*(1-fy)+px(x0+1, y0)*fx*(1-fy)+px(x0, y0+1)*(1-fx)*fy+px(x0+1, y0+1)*fx*fy)

def native_texels(tris, w, h, F):
    """Rasterise native triangles in UV space; returns arrays of pixel coords, 3D positions, normals."""
    X = []; Y = []; Pp = []; Nn = []
    for (_t, _f, _b, _w, _h, tri) in tris:
        uv = np.array([(v[3]*F, v[4]*F) for v in tri]); pos = np.array([v[:3] for v in tri], float)
        n = np.cross(pos[1]-pos[0], pos[2]-pos[0]); l = np.linalg.norm(n); n = n/l if l > 1e-9 else np.array([0, 1.0, 0])
        x0, y0 = np.floor(uv.min(0)).astype(int)-1, None
        mn = np.floor(uv.min(0)).astype(int)-1; mx = np.ceil(uv.max(0)).astype(int)+1
        if (mx-mn).prod() > 4_000_000: continue
        gx, gy = np.meshgrid(np.arange(mn[0], mx[0]), np.arange(mn[1], mx[1]))
        px = gx+0.5; py = gy+0.5
        (ax, ay), (bx, by), (cx, cy) = uv
        den = (by-cy)*(ax-cx)+(cx-bx)*(ay-cy)
        if abs(den) < 1e-9: continue
        w0 = ((by-cy)*(px-cx)+(cx-bx)*(py-cy))/den; w1 = ((cy-ay)*(px-cx)+(ax-cx)*(py-cy))/den; w2 = 1-w0-w1
        eps = -0.75/F*0  # include boundary pixels generously
        ins = (w0 >= -0.02) & (w1 >= -0.02) & (w2 >= -0.02)
        if not ins.any(): continue
        a0, a1, a2 = w0[ins], w1[ins], w2[ins]
        P = a0[:, None]*pos[0]+a1[:, None]*pos[1]+a2[:, None]*pos[2]
        X.append(np.mod(gx[ins], w*F)); Y.append(np.mod(gy[ins], h*F)); Pp.append(P); Nn.append(np.tile(n, (len(P), 1)))
    if not X: return None
    return np.concatenate(X), np.concatenate(Y), np.concatenate(Pp), np.concatenate(Nn)

def match(donor, P, N, normal_weight):
    """Index of best donor triangle + barycentrics for each point (chunked)."""
    best = np.empty(len(P), int); bary = np.empty((len(P), 3))
    for s in range(0, len(P), 1500):
        d2, bc = closest_points(P[s:s+1500], donor.A, donor.B, donor.C)
        dot = (N[s:s+1500, None, :]*donor.N[None, :, :]).sum(-1)
        cost = np.sqrt(d2)+normal_weight*np.clip(1-dot, 0, 2)
        k = cost.argmin(1); best[s:s+1500] = k; bary[s:s+1500] = bc[np.arange(len(k)), k]
    return best, bary

def dilate(rgb, filled, iters=6):
    rgb = rgb.copy(); filled = filled.copy()
    for _ in range(iters):
        if filled.all(): break
        acc = np.zeros_like(rgb); cnt = np.zeros(filled.shape)
        for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            f = np.roll(filled, (dy, dx), (0, 1)); c = np.roll(rgb, (dy, dx), (0, 1))
            acc += c*f[..., None]; cnt += f
        grow = (~filled) & (cnt > 0)
        rgb[grow] = acc[grow]/cnt[grow][:, None]; filled = filled | grow
    return rgb
