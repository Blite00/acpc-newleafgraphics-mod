"""GameCube villager houses, upscaled: smoother geometry on the curved parts and detail-preserving textures.

Geometry: every body display list (t1..t4) of the five GC houses, summer and winter, is rebuilt. Triangles on a
curved surface (roof ridges, rounded eaves, chimneys, bay windows) get crease-aware PN tessellation: a vertex is
only smoothed with neighbouring faces that bend less than CREASE degrees, so flat walls stay flat and sharp
corners stay sharp, and shared edges bend identically on both sides (no cracks). Flat triangles are kept as they
are. All texture/palette/render commands are copied verbatim, so the native palettes (a..e) keep working.

Textures: every CI texture the houses use, under every palette (5 houses x 5 palettes x summer/winter), goes
through the same wrap-aware general-model Real-ESRGAN pass with the original detail added back, and is written to
the texture pack (replaced by hash at load time).
"""
import re, shutil, subprocess
from pathlib import Path
import numpy as np
from PIL import Image
import native_models as nm
import texture_bake as tb
from generate_villager_fences_defs import FENCE_PART, is_fence_tri

ROOT = Path(__file__).resolve().parent
src = (ROOT/'generate_mailbox_hd.py').read_text()
exec(src[src.index('def _pad_mode'):src.index('# ---------------- textures')])   # _esr_pass, upscale_all
W = ROOT/'villager_up'; UP = 4; PAD = 6; DETAIL = 0.35
ESR = ROOT/'toolchain/realesrgan/realesrgan-ncnn-vulkan.exe'
PACK = ROOT/'texture_pack_staging/gc_villager_houses'
MODEL = ROOT/'ACGC-PC-Port/src/data/model/obj_s_house1.c'
CREASE = 40.0; LEVEL = 4
text = MODEL.read_text()

def dl_body(name):
    m = re.search(rf'Gfx {name}\[\] = \{{(.*?)\n\}};', text, re.S)
    return m[1] if m else None

def commands(body):
    return re.findall(r'(gs\w+)\(([^()]*(?:\([^()]*\)[^()]*)*)\)', body)


from scipy.ndimage import gaussian_filter, uniform_filter, maximum_filter, minimum_filter
def scale2x(a):
    h, w = a.shape[:2]; P = np.pad(a, ((1, 1), (1, 1), (0, 0)), mode='edge')
    B, D, E, F, H = P[:-2, 1:-1], P[1:-1, :-2], P[1:-1, 1:-1], P[1:-1, 2:], P[2:, 1:-1]
    eq = lambda x, y: (np.abs(x-y).sum(-1) < 1)[..., None]
    c = eq(B, H) | eq(D, F)
    E0 = np.where(~c & eq(D, B), D, E); E1 = np.where(~c & eq(B, F), F, E)
    E2 = np.where(~c & eq(D, H), D, E); E3 = np.where(~c & eq(H, F), F, E)
    out = np.empty((h*2, w*2, a.shape[2])); out[0::2, 0::2] = E0; out[0::2, 1::2] = E1; out[1::2, 0::2] = E2; out[1::2, 1::2] = E3
    return out
def scale4x(a): return scale2x(scale2x(a.astype(float)))
def fractal(h, w, seed):
    """soft plaster/grain noise (3 octaves, tileable) for areas the original painted in one flat colour"""
    rng = np.random.default_rng(seed); n = np.zeros((h, w))
    for sg, amp in ((1.0, 0.35), (2.5, 0.35), (6.0, 0.3)):
        g = gaussian_filter(rng.standard_normal((h, w)), sg, mode='wrap'); n += amp*g/(g.std()+1e-9)
    return n/(n.std()+1e-9)

def _inside(poly, x, y):
    c = False; m = len(poly)
    for i in range(m):
        x1, y1 = poly[i]; x2, y2 = poly[(i+1) % m]
        if (y1 > y) != (y2 > y) and x < (x2-x1)*(y-y1)/((y2-y1) or 1e-12)+x1: c = not c
    return c

FENCE_THICK = {1: 220, 2: 320, 3: 260, 4: 450, 5: 420}
def extrude_fence(tris, img, thick, n):
    """Turn the GC's flat cut-out fence quads into solid fences: front and back faces carry the original texture
    (its cut-out alpha shapes the pickets/logs), and side walls run along every edge of the cut-out silhouette,
    coloured by the texel there. The fence is sunk slightly into the ground."""
    tex, w, h = img
    pal = f'obj_{tex[4]}_house{n}_a_pal'
    alpha = np.asarray(nm.decode_ci(nm.blob(tex), w, h, nm.palette(pal), 4).convert('RGBA'))[..., 3]
    down = np.array([0, -90.0, 0])
    planes = {}
    for t in tris:
        P = np.array([v[0] for v in t], float); nrm = np.cross(P[1]-P[0], P[2]-P[0]); l = np.linalg.norm(nrm)
        if l < 1e-6: continue
        nrm /= l
        if nrm[np.argmax(np.abs(nrm))] < 0: nrm = -nrm
        key = (tuple(np.round(nrm, 2)), round(float(np.dot(nrm, P[0]))/60))
        planes.setdefault(key, []).append(t)
    # split each plane into separate panels (triangles sharing corners), so a gap such as the doorway stays open
    panels = []
    for key, ts in planes.items():
        groups = []
        for t in ts:
            ks = {tuple(np.round(v[0]).astype(int)) for v in t}
            hit = [g for g in groups if g[0] & ks]
            merged = (set(ks), [t])
            for g in hit: merged[0].update(g[0]); merged[1].extend(g[1]); groups.remove(g)
            groups.append(merged)
        panels += [(key, g[1]) for g in groups]
    out = []
    for key, ts in panels:
        pts = {}
        for t in ts:
            for v in t: pts[tuple(np.round(v[0]).astype(int))] = v
        V = list(pts.values())
        if len(V) < 3: continue
        P = np.array([v[0] for v in V], float); UV = np.array([v[1] for v in V], float)/32.0
        nrm = np.array(key[0], float); nrm /= max(np.linalg.norm(nrm), 1e-9)
        A = np.c_[UV, np.ones(len(UV))]; M, *_ = np.linalg.lstsq(A, P, rcond=None)
        pos = lambda u, v: np.array([u, v, 1.0]) @ M
        ctr = UV.mean(0); order = np.argsort(np.arctan2(UV[:, 1]-ctr[1], UV[:, 0]-ctr[0]))
        poly = [tuple(UV[i]) for i in order]
        u0, v0 = np.floor(UV.min(0)).astype(int); u1, v1 = np.ceil(UV.max(0)).astype(int)
        cells = {}
        for vv in range(v0, v1):
            for uu in range(u0, u1):
                if _inside(poly, uu+0.5, vv+0.5): cells[(uu, vv)] = alpha[vv % h, uu % w] > 0
        off = nrm*thick/2
        def V3(p, uv, n_): return (p+down, (uv[0]*32, uv[1]*32), n_)
        for sgn in (1, -1):
            c_ = [V3(P[i]+sgn*off, UV[i], sgn*nrm) for i in order]
            for i in range(1, len(c_)-1):
                tri = [c_[0], c_[i], c_[i+1]]
                out.append(tri); out.append(tri[::-1])
        # silhouette edges, merged into straight runs (one wall per run instead of one per texel)
        edges = {}
        for (uu, vv), solid in cells.items():
            if not solid: continue
            for du, dv in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                if cells.get((uu+du, vv+dv), False): continue
                edges.setdefault((du, dv), set()).add((uu, vv))
        for (du, dv), cs in edges.items():
            lines = {}
            for uu, vv in cs: lines.setdefault(vv if dv else uu, []).append(uu if dv else vv)
            for fixed, run in lines.items():
                run.sort(); start = prev = run[0]
                for r in run[1:]+[None]:
                    if r is not None and r == prev+1: prev = r; continue
                    if dv: a_ = (start, fixed+(1 if dv > 0 else 0)); b_ = (prev+1, a_[1]); mid = ((start+prev+1)/2, fixed+0.5)
                    else: a_ = (fixed+(1 if du > 0 else 0), start); b_ = (a_[0], prev+1); mid = (fixed+0.5, (start+prev+1)/2)
                    pa, pb = pos(*a_), pos(*b_); side = pos(mid[0]+du, mid[1]+dv)-pos(*mid)
                    sn = side/max(np.linalg.norm(side), 1e-9)
                    q = [V3(pa+off, mid, sn), V3(pb+off, mid, sn), V3(pb-off, mid, sn), V3(pa-off, mid, sn)]
                    out += [[q[0], q[1], q[2]], [q[0], q[2], q[3]], [q[2], q[1], q[0]], [q[3], q[2], q[0]]]
                    if r is not None: start = prev = r
    return [v for t in out for v in t]

# ---------------- textures ----------------
# The GC house textures are small atlases: several unrelated pictures packed into one 128x32 sheet, each mapped
# onto its own triangles. Upscaling a whole sheet bleeds one picture into its neighbour, which showed as seams
# along triangle edges, and the palette's transparent colour bled a fringe into cut-out edges. So each texture is
# split into the UV islands its triangles actually use; every island is upscaled on its own with its edge pixels
# extended outward (never its neighbours'), and only the island's own pixels are kept.
from scipy.ndimage import label, distance_transform_edt, binary_dilation
from PIL import ImageDraw, ImageFilter
uv_tris = {}     # tex symbol -> list of triangles in texel coords
modes = {}
for season in 'sw':
    for n in range(1, 6):
        verts_ = nm.vertices(f'obj_{season}_house{n}_v')
        for part in ('t1', 't2', 't3', 't4', 'name', 'door', 'light'):
            body = dl_body(f'obj_{season}_house{n}_{part}_model')
            if body is None: continue
            img = None; slot = {}; pend = 0
            for op, args in commands(body):
                a_ = [x.strip() for x in args.split(',')]
                if op == 'gsDPSetTextureImage_Dolphin': img = (a_[4], int(a_[2]), int(a_[3])) if a_[0] == 'G_IM_FMT_CI' else None
                elif op == 'gsDPSetTile_Dolphin' and img: modes[img] = (a_[3], a_[4])
                elif op == 'gsSPVertex':
                    m = re.match(r'&?(\w+)(?:\[(\d+)\])?', a_[0]); st = int(m[2] or 0)
                    for k in range(int(a_[1])): slot[int(a_[2])+k] = st+k
                elif op in ('gsSPNTrianglesInit_5b', 'gsSPNTriangles_5b') and img:
                    idx = list(map(int, a_[1:10])) if op == 'gsSPNTrianglesInit_5b' else list(map(int, a_[:12]))
                    if op == 'gsSPNTrianglesInit_5b': pend = int(a_[0])
                    for k in range(0, len(idx), 3):
                        if pend > 0:
                            uv_tris.setdefault(img, []).append([(verts_[slot[i]][4]/32.0, verts_[slot[i]][5]/32.0) for i in idx[k:k+3]]); pend -= 1

def wrap_coord(x, size, mode):
    if mode == 'GX_CLAMP': return np.clip(x, 0, size-1)
    if mode == 'GX_REPEAT': return np.mod(x, size)
    period = np.mod(x, 2*size); return np.where(period < size, period, 2*size-1-period)

def islands(img_key):
    tex, w, h = img_key; mu, mv = modes[img_key]
    mask = np.zeros((h, w), bool)
    for tri in uv_tris.get(img_key, []):
        pts = np.array(tri); x0, y0 = np.floor(pts.min(0)).astype(int)-1; x1, y1 = np.ceil(pts.max(0)).astype(int)+1
        if (x1-x0)*(y1-y0) > 64*w*h: continue
        im = Image.new('L', (x1-x0, y1-y0), 0)
        ImageDraw.Draw(im).polygon([(float(px-x0), float(py-y0)) for px, py in pts], fill=255, outline=255)
        ys, xs = np.nonzero(np.asarray(im) > 0)
        mask[wrap_coord(ys+y0, h, mv), wrap_coord(xs+x0, w, mu)] = True
    lab, n_ = label(binary_dilation(mask, iterations=1), structure=np.ones((3, 3)))
    return [lab == k for k in range(1, n_+1)] or [np.ones((h, w), bool)]

ISL = {}; jobs = []; meta = {}
for season in 'sw':
    for n in range(1, 6):
        for img_key in [k for k in modes if f'obj_{season}_house{n}_' in k[0]]:
            tex, w, h = img_key
            if img_key not in ISL: ISL[img_key] = islands(img_key)
            for letter in 'abcde':
                pal = f'obj_{season}_house{n}_{letter}_pal'
                key = f'{tex}__{pal}'
                if key in meta: continue
                src_im = np.asarray(nm.decode_ci(nm.blob(tex), w, h, nm.palette(pal), 4).convert('RGBA')).astype(float)
                meta[key] = (tex, pal, w, h, src_im, img_key)
                opaque = src_im[..., 3] > 0
                for k, isl in enumerate(ISL[img_key]):
                    keep = isl & opaque if (isl & opaque).any() else isl
                    _, (iy, ix) = distance_transform_edt(~keep, return_indices=True)
                    filled = src_im[iy, ix]                       # island pixels extended outward
                    ys, xs = np.nonzero(isl); y0, y1, x0, x1 = ys.min(), ys.max()+1, xs.min(), xs.max()+1
                    crop = filled[max(0, y0-2):y1+2, max(0, x0-2):x1+2]
                    jobs.append((f'{key}__{k}', Image.fromarray(crop.astype(np.uint8), 'RGBA'), 'GX_CLAMP', 'GX_CLAMP'))
print('upscaling', len(jobs), 'islands for', len(meta), 'texture/palette pairs')
up = upscale_all(jobs)
shutil.rmtree(PACK, ignore_errors=True); PACK.mkdir(parents=True)
# External (hand-painted) textures: which texel rectangles to take from them. Missing = whole texture,
# [] = none (built-in upscale). Only the doors and the wooden signs are kept.
EXTERNAL_KEEP = {
    'house1_t1_tex_txt': [(0, 0, 32, 32), (77, 0, 128, 32)],     # arrow signpost, front door
    'house1_t2_tex_txt': [], 'house1_t3_tex_txt': [],
    'house2_t1_tex_txt': [], 'house2_t2_tex_txt': [],
    'house2_t3_tex_txt': [(0, 0, 48, 32)],                         # front door
}

def clean_external(rgb, img_key, w, h):
    """Make an externally painted atlas safe for the game's wrapping: every UV island keeps only its own interior
    and is extended outward from there (so a triangle edge never samples a neighbouring picture or a painted
    border), and on GX_MIRROR edges the outermost texel is replaced by its inner neighbour (a drawn edge line
    would otherwise show twice as a seam down the middle of a mirrored wall)."""
    from scipy.ndimage import binary_erosion, distance_transform_edt
    mu, mv = modes[img_key]
    keep = np.zeros((h*UP, w*UP), bool)
    for isl in ISL[img_key]:
        core = binary_erosion(isl, iterations=1) if binary_erosion(isl, iterations=1).any() else isl
        keep |= np.kron(core, np.ones((UP, UP), bool))
    # mirrored edges: the outer texel row/column comes from the next one in
    e = UP
    out = rgb.copy()
    if mu == 'GX_MIRROR':
        out[:, :e] = out[:, e:e+1]; out[:, -e:] = out[:, -e-1:-e]
    if mv == 'GX_MIRROR':
        out[:e, :] = out[e:e+1, :]; out[-e:, :] = out[-e-1:-e, :]
    if keep.any() and (~keep).any():
        _, (iy, ix) = distance_transform_edt(~keep, return_indices=True)
        out = np.where(keep[..., None], out, out[iy, ix])
    return out

for key, (tex, pal, w, h, src_im, img_key) in meta.items():
    out_im = np.asarray(Image.fromarray(src_im.astype(np.uint8), 'RGBA').resize((w*UP, h*UP), Image.BICUBIC)).astype(float)
    for k, isl in enumerate(ISL[img_key]):
        ys, xs = np.nonzero(isl); y0, x0 = max(0, ys.min()-2), max(0, xs.min()-2)
        u = np.asarray(up[f'{key}__{k}']).astype(float)
        big = np.kron(isl, np.ones((UP, UP), bool))
        region = big[y0*UP:y0*UP+u.shape[0], x0*UP:x0*UP+u.shape[1]]
        tgt = out_im[y0*UP:y0*UP+u.shape[0], x0*UP:x0*UP+u.shape[1]]
        tgt[..., :3][region] = u[..., :3][:region.shape[0], :region.shape[1]][region]
    # lock every pixel to the house's own 16-colour GC palette: the upscale only redraws the shapes at 4x, the
    # colours stay exactly the original's (no colour drift, no halos); a light box filter softens stair steps
    palc = np.array(nm.palette(pal))[:, :3].astype(float); palc = palc[np.array(nm.palette(pal))[:, 3] > 0]
    rgb = out_im[..., :3]; q = np.empty_like(rgb)
    for r0 in range(0, rgb.shape[0], 32):
        blk = rgb[r0:r0+32]; dd = ((blk[..., None, :]-palc[None, None])**2).sum(-1); q[r0:r0+32] = palc[dd.argmin(-1)]
    ovr = ROOT/'upscale_override'/W.name/f'{key}.png'
    part = tex[6:]                                       # e.g. house1_t1_tex_txt
    ext = None
    if ovr.exists() and EXTERNAL_KEEP.get(part, []) != []:
        rgbq = clean_external(np.asarray(Image.open(ovr).convert('RGB').resize((w*UP, h*UP), Image.LANCZOS)).astype(float), img_key, w, h)
        # painted-in dark gaps/outlines that the GameCube art doesn't have: take the GC colour there
        _la = rgbq @ np.array([0.3, 0.59, 0.11]); _lq = q @ np.array([0.3, 0.59, 0.11])
        _dark = (_lq-_la > 70) & (_lq > 90)
        from scipy.ndimage import binary_dilation as _bd
        _dark = _bd(_dark, iterations=2)
        rgbq = np.where(_dark[..., None], gaussian_filter(q, (1, 1, 0)), rgbq)
        # cut-out edges: replace the ring just inside a transparent hole with the colour further in
        _al = np.asarray(Image.fromarray(src_im[..., 3].astype(np.uint8)).resize((w*UP, h*UP), Image.BICUBIC)) > 128
        if (~_al).any() and _al.any():
            from scipy.ndimage import binary_erosion as _be, distance_transform_edt as _dt
            _core = _be(_al, iterations=UP+1)
            if _core.any():
                _, (_iy, _ix) = _dt(~_core, return_indices=True)
                rgbq = np.where((_al & ~_core)[..., None], rgbq[_iy, _ix], rgbq)
        ext = rgbq
    if ext is not None and EXTERNAL_KEEP.get(part) is None:
        rgbq = ext
    elif '_name_' in tex or tex.endswith('house1_t4_tex_txt'):
        # name signs: the AI upscale's smooth pen strokes (no palette snapping, which made the script blocky),
        # sharpened so the lettering reads clearly
        sm = out_im[..., :3]; bl = np.stack([gaussian_filter(sm[..., c], 1.5) for c in range(3)], -1)
        rgbq = sm+0.8*(sm-bl)
    else:
        # crisp outlines, but the painted shading steps (neighbouring palette shades of one colour) blend into
        # smooth gradients: wherever the local colour range is small, take a softened version
        rng_ = sum(maximum_filter(q[..., c], 5)-minimum_filter(q[..., c], 5) for c in range(3))
        wsm = np.clip((110-rng_)/60, 0, 1); wsm = gaussian_filter(wsm, 1.0)
        soft = np.stack([gaussian_filter(q[..., c], 2.6) for c in range(3)], -1)
        rgbq = q*(1-wsm[..., None])+soft*wsm[..., None]
        slum = src_im[..., :3] @ np.array([0.3, 0.59, 0.11])
        var = uniform_filter(slum**2, 3)-uniform_filter(slum, 3)**2
        flat = gaussian_filter(np.kron((var < 40).astype(float), np.ones((UP, UP))), 3)
        rgbq = rgbq*(1+0.03*fractal(h*UP, w*UP, hash(key) & 0xffff)*flat)[..., None]
    if ext is not None and EXTERNAL_KEEP.get(part):
        # only the doors and wooden signs come from the external set; everything else is the built-in upscale
        m = np.zeros((h, w))
        for x0, y0, x1, y1 in EXTERNAL_KEEP[part]: m[y0:y1, x0:x1] = 1
        m = gaussian_filter(np.kron(m, np.ones((UP, UP))), UP*0.3)[..., None]
        rgbq = ext*m+rgbq*(1-m)
    out_im[..., :3] = np.clip(rgbq, 0, 255)
    # alpha: the source's own cut-out edge, smoothed (no fringe from the transparent colour)
    a_big = np.asarray(Image.fromarray(src_im[..., 3].astype(np.uint8)).resize((w*UP, h*UP), Image.BICUBIC)).astype(float)
    out_im[..., 3] = a_big
    im = Image.fromarray(np.clip(out_im, 0, 255).astype(np.uint8), 'RGBA')
    (PACK/tb.pack_name(tex, 'CI', 4, w, h, pal)).write_bytes(tb.dds_rgba(im))
    if pal.endswith('_a_pal'): im.save(W/f'final_{tex}.png')


# ---------------- geometry ----------------
def pn_tri(tri, G, level, straight=()):
    """tri: 3 x (pos, st, n); G: 3 geometry normals (crease-aware). Returns triangles of (pos, st, n)."""
    P = [np.array(v[0], float) for v in tri]; N = [np.array(v[2], float)/max(np.linalg.norm(v[2]), 1e-9) for v in tri]
    T = [np.array(v[1], float) for v in tri]
    keys = [tuple(int(c) for c in v[0]) for v in tri]
    def ctrl(i, j):
        if frozenset((keys[i], keys[j])) in straight: return (2*P[i]+P[j])/3
        return (2*P[i]+P[j]-np.dot(P[j]-P[i], G[i])*G[i])/3
    b210 = ctrl(0, 1); b120 = ctrl(1, 0); b021 = ctrl(1, 2); b012 = ctrl(2, 1); b102 = ctrl(2, 0); b201 = ctrl(0, 2)
    E = (b210+b120+b021+b012+b102+b201)/6; V = (P[0]+P[1]+P[2])/3; b111 = E+(E-V)/2
    def pt(u, v_):
        w_ = 1-u-v_
        pos = (P[0]*w_**3+P[1]*u**3+P[2]*v_**3+b210*3*w_*w_*u+b120*3*w_*u*u+b201*3*w_*w_*v_
               + b021*3*u*u*v_+b102*3*w_*v_*v_+b012*3*u*v_*v_+b111*6*w_*u*v_)
        n = N[0]*w_+N[1]*u+N[2]*v_; n /= max(np.linalg.norm(n), 1e-9)
        return (pos, T[0]*w_+T[1]*u+T[2]*v_, n)
    out = []
    for i in range(level):
        for j in range(level-i):
            a = pt(j/level, i/level); b = pt((j+1)/level, i/level); c = pt(j/level, (i+1)/level)
            out.append((a, b, c))
            if i+j+1 < level: out.append((b, pt((j+1)/level, (i+1)/level), c))
    return out

def face_normal(tri):
    P = [np.array(v[0], float) for v in tri]; n = np.cross(P[1]-P[0], P[2]-P[0]); l = np.linalg.norm(n)
    return n/l if l > 1e-6 else None


# ---------------- winter: 3DS roof snow ----------------
# Surfaces the GC winter textures cover in snow (roofs, awnings, chimney tops) get a New Leaf snow blanket laid
# just above them: the snow sheet from the 3DS player-home winter roof, its wavy fringe hanging at the eaves.
SNOW_SRC = np.asarray(Image.open(ROOT/'house_source/my_house/Textures/season09/roof_00_raw.png').convert('RGBA')).astype(float)
_sn = SNOW_SRC[:, 14:200].copy(); _r, _g, _b = _sn[..., 0], _sn[..., 1], _sn[..., 2]
_sn[..., 3] = np.where((_b > 185) & (_r > 150) & (_b >= _r), 255, 0)
SNOW_TEX = Image.fromarray(_sn.astype(np.uint8), 'RGBA').resize((128, 64), Image.LANCZOS)
_whiteness = {}
def _white_frac(tex, w, h, pal, tri):
    a = np.asarray(nm.decode_ci(nm.blob(tex), w, h, nm.palette(pal), 4).convert('RGB')).astype(float)
    m = Image.new('L', (w, h), 0)
    ImageDraw.Draw(m).polygon([(float(v[1][0]/32.0) % w, float(v[1][1]/32.0) % h) for v in tri], fill=255)
    sel = np.asarray(m) > 0
    if not sel.any(): return 0.0
    px = a[sel]; return float(((px.min(1) > 190) & (px[:, 2] >= px[:, 0]-10)).mean())
def snowy(img, tri, n):
    """roofs, awnings and chimney tops: every up-facing surface above head height (the GC winter textures snow
    only part of them; the 3DS blanket covers the whole roof)"""
    vn = np.mean([np.array(v[2], float)/max(np.linalg.norm(v[2]), 1e-9) for v in tri], 0)   # authored normals (winding varies)
    if vn[1] < 0.12: return False
    f = face_normal(tri)
    if f is None or abs(f[1]) < 0.12: return False          # gable walls under a smoothed roof edge stay bare
    return min(v[0][1] for v in tri) > 4500
snow_arrays = []
def snow_cap(name, tris):
    """Snow blanket over smoothed roof triangles: v runs from the top of each roof face down to its eave."""
    P = np.array([[v[0] for v in t] for t in tris], float)
    ytop, ylow = P[..., 1].max(), P[..., 1].min()
    rows = []
    for t in tris:
        Q = np.array([v[0] for v in t], float); f = np.cross(Q[1]-Q[0], Q[2]-Q[0]); f /= max(np.linalg.norm(f), 1e-9)
        hz = np.array([f[2], 0, -f[0]]); hz = hz/np.linalg.norm(hz) if np.linalg.norm(hz) > 1e-6 else np.array([1.0, 0, 0])
        for pos, st, nn in t:
            nn = np.array(nn, float); nn /= max(np.linalg.norm(nn), 1e-9)
            q = np.array(pos, float)+nn*35.0                      # rests just on the roof
            u = np.dot(q, hz)/6000.0; v = (ytop-q[1])/max(ytop-ylow, 1)*0.98+0.01
            nb = ','.join(str(int(round(c*126)) & 255) for c in nn)
            rows.append('{{{%d,%d,%d},0,{%d,%d},{%s,255}}},' % (round(q[0]), round(q[1]), round(q[2]), round(u*128*32), round(v*64*32), nb))
    snow_arrays.append((name, rows))
    dl = ['gsDPPipeSync(),', 'gsSPTexture(0,0,0,G_TX_RENDERTILE,G_ON),', 'gsDPSetPrimColor(0,128,255,255,255,255),',
          'gsDPSetCombineLERP(TEXEL0,0,SHADE,0,0,0,0,TEXEL0,PRIMITIVE,0,COMBINED,0,0,0,0,COMBINED),',
          'gsDPSetRenderMode(G_RM_FOG_SHADE_A,G_RM_AA_ZB_TEX_EDGE2),',
          'gsDPSetTextureImage_Dolphin(G_IM_FMT_RGBA,G_IM_SIZ_32b,128,64,pc_vsnow_tex),',
          'gsDPSetTile_Dolphin(G_DOLPHIN_TLUT_DEFAULT_MODE,0,0,GX_MIRROR,GX_CLAMP,0,0),',
          'gsSPLoadGeometryMode(G_ZBUFFER|G_SHADE|G_FOG|G_LIGHTING|G_SHADING_SMOOTH),']
    for base in range(0, len(rows), 30):
        c = min(30, len(rows)-base)
        dl.append(f'gsSPVertex(&{name}_v[{base}],{c},0),')
        for k in range(0, c, 3): dl.append(f'gsSP1Triangle({k},{k+1},{k+2},0),')
    return dl

out = ['/* Generated by generate_villager_hd.py: GC villager houses with smoothed curved parts (textures via pack). */',
       'int g_pc_villager_hd = 1;']
externs = set(); swaps = []; stats = {}
cos_crease = np.cos(np.radians(CREASE))
for season in 'sw':
    for n in range(1, 6):
        verts = nm.vertices(f'obj_{season}_house{n}_v')
        vsym = f'obj_{season}_house{n}_v'
        house_tris = []                      # (part, [vertex indices]) over every body list of this house
        for part_ in ('t1', 't2', 't3', 't4', 'light', 'door', 'name'):
            b_ = dl_body(f'obj_{season}_house{n}_{part_}_model')
            if b_ is None: continue
            sl_ = {}; pd_ = 0
            for op, args in commands(b_):
                a = [x.strip() for x in args.split(',')]
                if op == 'gsSPVertex':
                    m = re.match(r'&?(\w+)(?:\[(\d+)\])?', a[0]); st = int(m[2] or 0)
                    for k in range(int(a[1])): sl_[int(a[2])+k] = st+k
                elif op in ('gsSPNTrianglesInit_5b', 'gsSPNTriangles_5b'):
                    idx = list(map(int, a[1:10])) if op == 'gsSPNTrianglesInit_5b' else list(map(int, a[:12]))
                    if op == 'gsSPNTrianglesInit_5b': pd_ = int(a[0])
                    for k in range(0, len(idx), 3):
                        if pd_ > 0: house_tris.append((part_, [sl_[i] for i in idx[k:k+3]])); pd_ -= 1
        P_ = lambda i: tuple(verts[i][:3])
        hfn = []
        for part_, t in house_tris:
            A, B, C = (np.array(P_(i), float) for i in t); nn_ = np.cross(B-A, C-A); l_ = np.linalg.norm(nn_)
            hfn.append(nn_/l_ if l_ > 1e-6 else None)
        h_inc = {}
        for (part_, t), f in zip(house_tris, hfn):
            if f is None: continue
            for i in t: h_inc.setdefault(P_(i), []).append(f)
        def h_curved(t, f):
            for i in t:
                ns = [m for m in h_inc.get(P_(i), []) if np.dot(m, f) > cos_crease]
                g = np.mean(ns, 0); g /= max(np.linalg.norm(g), 1e-9)
                if np.dot(g, f) < 0.999: return True
            return False
        edge_faces = {}
        for k_, ((part_, t), f) in enumerate(zip(house_tris, hfn)):
            for a_, b_ in ((0, 1), (1, 2), (2, 0)):
                edge_faces.setdefault(frozenset((P_(t[a_]), P_(t[b_]))), []).append((part_, f is not None and h_curved(t, f)))
        straight = {e for e, fs in edge_faces.items() if len(fs) != 2 or not all(c for _, c in fs) or fs[0][0] != fs[1][0]}
        for part in ('t1', 't2', 't3', 't4'):
            name = f'obj_{season}_house{n}_{part}_model'
            body = dl_body(name)
            if body is None: continue
            cmds = commands(body)
            # pass 1: collect all triangles (for neighbourhood normals)
            slot = {}; tris_all = []; pend = 0
            for op, args in cmds:
                a = [x.strip() for x in args.split(',')]
                if op == 'gsSPVertex':
                    m = re.match(r'&?(\w+)(?:\[(\d+)\])?', a[0]); st = int(m[2] or 0)
                    for k in range(int(a[1])): slot[int(a[2])+k] = st+k
                elif op in ('gsSPNTrianglesInit_5b', 'gsSPNTriangles_5b'):
                    idx = list(map(int, a[1:10])) if op == 'gsSPNTrianglesInit_5b' else list(map(int, a[:12]))
                    if op == 'gsSPNTrianglesInit_5b': pend = int(a[0])
                    for k in range(0, len(idx), 3):
                        if pend > 0: tris_all.append([slot[i] for i in idx[k:k+3]]); pend -= 1
            def vd(i):
                x, y, z, _f, s, t, r, g, b, al = verts[i]
                return ((x, y, z), (s, t), [c-256 if c > 127 else c for c in (r, g, b)])
            fn = {}; incident = {}
            for ti, t in enumerate(tris_all):
                f = face_normal([vd(i) for i in t]); fn[ti] = f
                if f is None: continue
                pass
            incident = h_inc
            def geo_normals(t, f):
                G = []
                for i in t:
                    ns = [m for m in incident.get(tuple(verts[i][:3]), []) if np.dot(m, f) > cos_crease]
                    g = np.mean(ns, 0) if ns else f; G.append(g/max(np.linalg.norm(g), 1e-9))
                return G
            # pass 2: emit
            dl = []; batch = []; vcount = [0]; arrays = []; pend = 0; slot = {}; cur_tex = [None]; snow_tris = []; fence_batch = []
            def flush():
                if not batch and not fence_batch: return
                verts_out = []
                fence_batch.clear()                     # flat GC fence: replaced by the 3DS fence below
                for t in batch:
                    tri = [vd(i) for i in t]; f = face_normal(tri)
                    if f is None: continue
                    G = geo_normals(t, f)
                    curved = any(np.dot(g, f) < 0.999 for g in G)
                    made = pn_tri(tri, G, LEVEL, straight) if curved else [tuple(tri)]
                    if season == 'w' and cur_tex[0] and snowy(cur_tex[0], tri, n): snow_tris.extend(made)
                    verts_out += [v for tt in made for v in tt]
                an = f'pc_vh_{season}{n}_{part}_{len(arrays)}'
                rows = []
                for pos, st, nn in verts_out:
                    nb = ','.join(str(int(round(c*126 if isinstance(c, float) else c)) & 255) for c in (np.array(nn, float)/max(np.linalg.norm(nn), 1e-9)))
                    rows.append('{{{%d,%d,%d},0,{%d,%d},{%s,255}}},' % (round(pos[0]), round(pos[1]), round(pos[2]), round(st[0]), round(st[1]), nb))
                arrays.append((an, rows))
                for base in range(0, len(verts_out), 30):
                    c = min(30, len(verts_out)-base)
                    dl.append(f'gsSPVertex(&{an}[{base}],{c},0),')
                    for k in range(0, c, 3): dl.append(f'gsSP1Triangle({k},{k+1},{k+2},0),')
                vcount[0] += len(verts_out)
                batch.clear()
            for op, args in cmds:
                a = [x.strip() for x in args.split(',')]
                if op == 'gsSPVertex':
                    flush()
                    m = re.match(r'&?(\w+)(?:\[(\d+)\])?', a[0]); st = int(m[2] or 0)
                    for k in range(int(a[1])): slot[int(a[2])+k] = st+k
                elif op in ('gsSPNTrianglesInit_5b', 'gsSPNTriangles_5b'):
                    idx = list(map(int, a[1:10])) if op == 'gsSPNTrianglesInit_5b' else list(map(int, a[:12]))
                    if op == 'gsSPNTrianglesInit_5b': pend = int(a[0])
                    for k in range(0, len(idx), 3):
                        if pend > 0:
                            tri_ = [slot[i] for i in idx[k:k+3]]; pend -= 1
                            if FENCE_PART.get(n) == part and is_fence_tri([verts[i][:3] for i in tri_]): fence_batch.append(tri_)
                            else: batch.append(tri_)
                elif op == 'gsSPEndDisplayList':
                    flush()
                else:
                    flush()
                    if op == 'gsDPSetTextureImage_Dolphin': cur_tex[0] = (a[4], int(a[2]), int(a[3])) if a[0] == 'G_IM_FMT_CI' else None
                    for sym in re.findall(r'\bobj_[sw]_house\w*_txt\b', args): externs.add(sym)
                    dl.append(f'{op}({args}),')
            for an, rows in arrays:
                out.append(f'static Vtx {an}[] ATTRIBUTE_ALIGN(32) = {{'); out += rows; out.append('};')
            if FENCE_PART.get(n) == part:
                for letter in 'abcde':
                    out += [f'extern Gfx pc_vf_{season}{n}_{letter}[];', f'static Gfx pc_vh_{season}{n}_{part}_{letter}[] = {{'] + dl + [f'gsSPDisplayList(pc_vf_{season}{n}_{letter}),', 'gsSPEndDisplayList(),', '};']
                swaps.append((name, [f'pc_vh_{season}{n}_{part}_{l}' for l in 'abcde']))
            else:
                out += [f'static Gfx pc_vh_{season}{n}_{part}[] = {{'] + dl + ['gsSPEndDisplayList(),', '};']
                swaps.append((name, f'pc_vh_{season}{n}_{part}'))
            stats[name] = (len(tris_all), vcount[0]//3)
def _rgba8(im):
    w, h = im.size; data = bytearray()
    for ty in range(0, h, 4):
        for tx in range(0, w, 4):
            tile = [im.getpixel((tx+x, ty+y)) for y in range(4) for x in range(4)]
            data.extend(c for r, g, b, a in tile for c in (a, r)); data.extend(c for r, g, b, a in tile for c in (g, b))
    return data
_d = _rgba8(SNOW_TEX)
snow_out = ['static u8 pc_vsnow_tex[] ATTRIBUTE_ALIGN(32) = {'] + [','.join(map(str, _d[i:i+32]))+',' for i in range(0, len(_d), 32)] + ['};']
for nm_, rows in snow_arrays: snow_out += [f'static Vtx {nm_}_v[] ATTRIBUTE_ALIGN(32) = {{'] + rows + ['};']
out = out[:2] + snow_out + [f'extern u8 {s}[];' for s in sorted(externs)] + [f'extern Gfx {a}[];' for a, _ in swaps] + out[2:]
out += ['/* native body display list -> smoothed one (NULL = keep native); pal 0..4 picks the fence colour */', 'Gfx* pc_villager_hd_swap(Gfx* native, int pal) {',
        '    if (!g_pc_villager_hd || native == NULL) return NULL;', '    if (pal < 0 || pal > 4) pal = 0;']
for a, b in swaps:
    if isinstance(b, list): out.append(f'    if (native == {a}) {{ static Gfx* v[5] = {{{",".join(b)}}}; return v[pal]; }}')
    else: out.append(f'    if (native == {a}) return {b};')
out += ['    return NULL;', '}']
(ROOT/'ACGC-PC-Port/pc/src/pc_villager_hd.c_inc').write_text('\n'.join(out)+'\n')
print('pack files', len(list(PACK.iterdir())))
for k, v in stats.items(): print(k, 'tris', v[0], '->', v[1])
