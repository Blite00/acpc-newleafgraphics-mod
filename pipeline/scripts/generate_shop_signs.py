"""Sharp shop signage for the four GameCube shops (Nook's Cranny, Nook 'n' Go, Nookway, Nookington's).

New Leaf's town shops carry different names (T&T Mart, Super T&T, ...), so the GC sign art is kept and redrawn at 8x:
inside each sign rectangle every palette colour is turned into a smooth shape (its texel mask is upscaled bicubically
and the strongest colour wins per pixel), which gives clean curved letters and logos with the exact GC colours and no
blur. Everything outside the sign rectangles is a plain bilinear upscale, so walls, wood and roofs look as they do now.
Summer and winter textures, written as a texture pack (shop_signs).
"""
import shutil
from pathlib import Path
import numpy as np
from PIL import Image
import native_models as nm
import texture_bake as tb

ROOT = Path(__file__).resolve().parent
PACK = ROOT/'texture_pack_staging/shop_signs'
OUT = ROOT/'shop_work/out'
UP = 8

# texture -> sign rectangles in texels (x0, y0, x1, y1)
# method: 'esr' = anime Real-ESRGAN (big lettering), 'esr2' = same on a 2x pixel copy (small lettering keeps its
# letter shapes), 'shape' = smooth colour shapes (tiny dot text)
SIGNS = {
    'shop1_front_txt':  [(84, 4, 106, 26, 'esr2')],
    'shop1_roof_txt':   [(0, 0, 64, 32, 'esr')],
    'shop1_side_txt':   [(96, 0, 128, 32, 'esr')],
    'shop2_t2_tex_txt': [(0, 0, 64, 32, 'esr2'), (64, 6, 128, 16, 'esr2')],
    'shop2_t3_tex_txt': [(32, 0, 56, 32, 'esr2'), (8, 32, 40, 64, 'shape')],
    'shop3_t2_tex_txt': [(16, 0, 96, 32, 'esr2')],
    'shop3_t3_tex_txt': [(0, 0, 64, 16, 'esr'), (0, 16, 64, 32, 'esr2'), (64, 0, 112, 32, 'shape')],
    'shop4_t2_tex_txt': [(16, 2, 40, 30, 'esr2'), (72, 0, 96, 32, 'esr2')],
    'shop4_t3_tex_txt': [(0, 0, 112, 32, 'esr')],
}
ESR = ROOT/'toolchain/realesrgan/realesrgan-ncnn-vulkan.exe'
EW = ROOT/'shop_work/esr'
PADT = 4

def esr_all(images):
    """{tex: RGB uint8 array} -> {(tex, prescale): RGB at UP x} via anime Real-ESRGAN (two 4x passes, 16x -> UP x)"""
    import subprocess
    for d in ('in', 'mid', 'out'): shutil.rmtree(EW/d, ignore_errors=True); (EW/d).mkdir(parents=True)
    for tex, a in images.items():
        a = np.pad(a, ((PADT, PADT), (PADT, PADT), (0, 0)), mode='edge')
        for k in (1, 2):
            Image.fromarray(a).resize((a.shape[1]*k, a.shape[0]*k), Image.NEAREST).save(EW/'in'/f'{tex}__{k}.png')
    run = lambda i, o: subprocess.run([str(ESR), '-i', str(i), '-o', str(o), '-n', 'realesrgan-x4plus-anime', '-s', '4', '-f', 'png'], check=True, capture_output=True)
    run(EW/'in', EW/'mid')
    for f in (EW/'mid').glob('*__1.png'): shutil.move(str(f), str(EW/'out'/f.name))
    # prescale 1: second 4x pass; prescale 2: the first pass already gives 8x
    (EW/'mid1').mkdir(exist_ok=True)
    for f in (EW/'out').glob('*__1.png'): shutil.move(str(f), str(EW/'mid1'/f.name))
    run(EW/'mid1', EW/'out')
    res = {}
    for tex, a in images.items():
        h, w = a.shape[:2]
        for k, sc in ((1, 16), (2, 8)):
            im = Image.open(EW/'out'/f'{tex}__{k}.png' if k == 1 else EW/'mid'/f'{tex}__{k}.png').convert('RGB')
            im = im.crop((PADT*sc, PADT*sc, PADT*sc+w*sc, PADT*sc+h*sc))
            if sc != UP: im = im.resize((w*UP, h*UP), Image.LANCZOS)
            res[(tex, k)] = np.asarray(im)
    return res

def snap(rgb, cols):
    """Each pixel -> nearest point on a segment between two of the region's colours (exact GC colours, with
    anti-aliased edges kept)."""
    X = rgb.reshape(-1, 3).astype(float); best_d = None; best_c = None
    segs = [(a, b) for i, a in enumerate(cols) for b in cols[i:]]
    for a, b in segs:
        ab = b-a; L = max(np.dot(ab, ab), 1e-9)
        t = np.clip((X-a) @ ab/L, 0, 1)[:, None]; q = a+t*ab; d = ((X-q)**2).sum(1)
        if best_d is None: best_d, best_c = d, q
        else: m = d < best_d; best_d = np.where(m, d, best_d); best_c = np.where(m[:, None], q, best_c)
    return best_c.reshape(rgb.shape)

import re
SIZES = {m[2]: (int(m[0]), int(m[1])) for m in re.findall(r'G_IM_SIZ_4b, (\d+), (\d+), (obj_[sw]_shop\w+)\)',
         (ROOT/'ACGC-PC-Port/src/data/model/obj_s_shop1.c').read_text())}

# New Leaf leaf logo (tex_dobj_shop_main: pink leaf on the white panel), used in place of the GC leaf logos.
# texture -> [(sample texel on the GC leaf, search box)]
LOGOS_NL = {
    'shop1_roof_txt':   [((11, 22), (2, 5, 22, 31))],
    'shop1_side_txt':   [((110, 14), (98, 3, 125, 29))],
    'shop2_t2_tex_txt': [((25, 15), (17, 2, 44, 29))],
    'shop2_t3_tex_txt': [((40, 18), (33, 7, 48, 29))],
    'shop3_t2_tex_txt': [((54, 15), (45, 4, 61, 26))],
    'shop4_t2_tex_txt': [((86, 12), (74, 2, 95, 28))],
}
# Off: the GC leaf comes out of the upscale clean and keeps the GameCube look; the NL leaf is a different drawing.
LOGOS = {}
def nl_logo_mask():
    im = np.asarray(Image.open(ROOT/'shop_source/dobj_shop/Textures/season00/tex_dobj_shop_main.png').convert('RGB')).astype(float)
    sq = im[128:194, 89:153]
    m = np.clip((sq[..., 0]-sq[..., 1]-25)/50, 0, 1)
    ys, xs = np.nonzero(m > 0.5)
    return m[ys.min():ys.max()+1, xs.min():xs.max()+1]
NL_LOGO = None
_REF = None
def gc_ref_leaf():
    global _REF
    if _REF is None:
        from scipy.ndimage import label
        b = nm.blob('obj_s_shop1_roof_txt'); idx = np.array(nm.ci_indices(b, 4)); img = np.zeros((32, 128), int); o = 0
        for ty in range(0, 32, 8):
            for tx in range(0, 128, 8): img[ty:ty+8, tx:tx+8] = idx[o:o+64].reshape(8, 8); o += 64
        lab, _ = label(img == img[22, 11]); m = lab == lab[22, 11]
        ys, xs = np.nonzero(m); _REF = m[ys.min():ys.max()+1, xs.min():xs.max()+1].astype(float)
    return _REF

def place_logo(out, img, pal, sample, box):
    """Replace the GC leaf (the connected texels of the sample's colour inside box) by the NL leaf, oriented and
    sized to fit the GC leaf best, in the GC leaf colour on the GC background colour."""
    global NL_LOGO
    from scipy.ndimage import label
    if NL_LOGO is None: NL_LOGO = nl_logo_mask()
    x0, y0, x1, y1 = box
    sub = img[y0:y1, x0:x1]; leaf_c = img[sample[1], sample[0]]
    lab, _ = label(sub == leaf_c); leaf = lab == lab[sample[1]-y0, sample[0]-x0]
    ring = sub[~leaf]; vals, cnt = np.unique(ring, return_counts=True); bg_c = vals[np.argmax(cnt)]
    ys, xs = np.nonzero(leaf); ly0, ly1, lx0, lx1 = ys.min(), ys.max()+1, xs.min(), xs.max()+1
    cy, cx = (ly0+ly1)/2, (lx0+lx1)/2; side = max(ly1-ly0, lx1-lx0)*1.05
    def placed(m, res):
        """NL mask at its own aspect, longest side = side texels, centred on the GC leaf; rendered at res px/texel
        over the search box."""
        h, w = m.shape; sc = side/max(h, w)
        H, W = sub.shape[0]*res, sub.shape[1]*res
        yy, xx = np.mgrid[0:H, 0:W]
        u = ((xx+0.5)/res-cx)/sc+w/2; v = ((yy+0.5)/res-cy)/sc+h/2
        ok = (u >= 0) & (u < w-1) & (v >= 0) & (v < h-1)
        u0 = np.clip(u.astype(int), 0, w-2); v0 = np.clip(v.astype(int), 0, h-2); fu = u-u0; fv = v-v0
        val = (m[v0, u0]*(1-fu)*(1-fv)+m[v0, u0+1]*fu*(1-fv)+m[v0+1, u0]*(1-fu)*fv+m[v0+1, u0+1]*fu*fv)
        return np.where(ok, val, 0)
    # orientation: the GC leaf of the Nook's Cranny sign is upright (as is the NL logo); every other GC leaf is
    # matched against it, and the NL logo gets the same turn/flip
    ref = gc_ref_leaf()
    best = None
    for k in range(4):
        for fl in (False, True):
            r = np.rot90(ref, k); r = r[:, ::-1] if fl else r
            small = np.asarray(Image.fromarray((r*255).astype(np.uint8)).resize((lx1-lx0, ly1-ly0), Image.BILINEAR)) > 127
            g = leaf[ly0:ly1, lx0:lx1]
            iou = (small & g).sum()/max((small | g).sum(), 1)
            m = np.rot90(NL_LOGO, k); m = m[:, ::-1] if fl else m
            if best is None or iou > best[0]: best = (iou, m)
    big = placed(best[1], UP)
    a = np.clip((big-0.5)*3+0.5, 0, 1)[..., None]
    P = np.array(pal, float)
    # wipe the GC leaf (and its 1-texel shading) to the background, then draw the NL leaf
    nb, _ = label(sub != bg_c); wipe = np.isin(nb, np.unique(nb[leaf])) & (nb > 0)
    for ty, tx in zip(*np.nonzero(wipe)):
        out[(y0+ty)*UP:(y0+ty+1)*UP, (x0+tx)*UP:(x0+tx+1)*UP] = P[bg_c].astype(np.uint8)
    reg = out[y0*UP:y1*UP, x0*UP:x1*UP].astype(float)
    out[y0*UP:y1*UP, x0*UP:x1*UP] = np.clip(reg*(1-a)+P[leaf_c]*a, 0, 255).astype(np.uint8)
    return best[0]

def pal_name(k, season):
    if k == '4': return f'obj_{season}_shop4_pal'
    return f'obj_shop{k}_pal' if season == 's' else f'obj_shop{k}_winter_pal'

def _weights(sub, pal):
    """Per-pixel weights over the region's main colours. A minor colour that sits between two main colours (an
    anti-aliasing texel) splits its weight between them, so outlines keep their sub-texel position."""
    cols, cnt = np.unique(sub, return_counts=True)
    P = np.array(pal, float)[:, :3]
    major = []
    for c in cols[np.argsort(-cnt)]:
        n = cnt[list(cols).index(c)]
        if major and n < 6: continue
        if any(_seg_dist(P[c], P[a], P[b])[0] < 22 for i, a in enumerate(major) for b in major[i+1:]): continue
        major.append(c)
    W = np.zeros(sub.shape+(len(major),))
    for c in cols:
        m = sub == c
        if c in major: W[m, major.index(c)] = 1; continue
        best = None
        for i, a in enumerate(major):
            for j, b in enumerate(major):
                if j <= i: continue
                d, t = _seg_dist(P[c], P[a], P[b])
                if best is None or d < best[0]: best = (d, t, i, j)
        if best is None or len(major) < 2:
            k = int(np.argmin(((P[major]-P[c])**2).sum(1))); W[m, k] = 1
        else:
            _, t, i, j = best; W[m, i] = 1-t; W[m, j] = t
    return major, W

def _seg_dist(p, a, b):
    ab = b-a; t = float(np.clip(np.dot(p-a, ab)/max(np.dot(ab, ab), 1e-9), 0, 1))
    return float(np.linalg.norm(a+t*ab-p)), t

def smooth_region(idx, pal, x0, y0, x1, y1):
    """Redraw idx[y0:y1, x0:x1] as smooth colour shapes at UP x (2-texel context so shapes continue past the edge)."""
    h, w = idx.shape
    cx0, cy0, cx1, cy1 = max(x0-2, 0), max(y0-2, 0), min(x1+2, w), min(y1+2, h)
    sub = idx[cy0:cy1, cx0:cx1]
    major, W = _weights(sub, pal)
    size = ((cx1-cx0)*UP, (cy1-cy0)*UP)
    F = np.stack([np.asarray(Image.fromarray(W[..., k].astype(np.float32), 'F').resize(size, Image.BICUBIC))
                  for k in range(len(major))], -1)
    order = np.argsort(-F, -1); f1 = np.take_along_axis(F, order[..., :1], -1)[..., 0]
    f2 = np.take_along_axis(F, order[..., 1:2], -1)[..., 0] if len(major) > 1 else np.zeros_like(f1)
    C = np.array(pal, float)[major]
    c1 = C[order[..., 0]]; c2 = C[order[..., 1]] if len(major) > 1 else c1
    # one output pixel of anti-aliasing at each shape edge
    a = np.clip(0.5+(f1-f2)*UP*0.6, 0.5, 1.0)[..., None]
    rgba = np.clip(c1*a+c2*(1-a), 0, 255).astype(np.uint8)
    oy, ox = (y0-cy0)*UP, (x0-cx0)*UP
    return rgba[oy:oy+(y1-y0)*UP, ox:ox+(x1-x0)*UP]

def untile(b, w, h):
    """CI4 data (8x8 tiles) -> h x w index image"""
    idx = np.array(nm.ci_indices(b, 4)); img = np.zeros((h, w), int); o = 0
    for ty in range(0, h, 8):
        for tx in range(0, w, 8):
            img[ty:ty+8, tx:tx+8] = idx[o:o+64].reshape(8, 8); o += 64
    return img

def build(tex, pal_sym, rects, esr=None):
    b = nm.blob(tex); w, h = SIZES[tex]
    pal = nm.palette(pal_sym)
    img = untile(b, w, h)
    base = Image.fromarray(np.array(pal, np.uint8)[img]).resize((w*UP, h*UP), Image.BILINEAR)
    out = np.asarray(base).copy()
    for (x0, y0, x1, y1, how) in rects:
        shape = smooth_region(img, pal, x0, y0, x1, y1)
        if how == 'shape':
            out[y0*UP:y1*UP, x0*UP:x1*UP] = shape; continue
        sub = img[y0:y1, x0:x1]
        major, _ = _weights(sub, pal)
        cols = [np.array(pal[c][:3], float) for c in major if pal[c][3] > 0]
        up = esr[(tex, 1 if how == 'esr' else 2)][y0*UP:y1*UP, x0*UP:x1*UP]
        rgb = snap(up, cols)
        region = shape.copy(); region[..., :3] = np.clip(rgb, 0, 255).astype(np.uint8)
        region[..., 3] = shape[..., 3]          # cut-out edges keep the smooth-shape outline
        out[y0*UP:y1*UP, x0*UP:x1*UP] = region
    for sample, box in LOGOS.get(tex[6:], []):
        iou = place_logo(out, img, pal, sample, box); print(tex, 'logo fit', round(iou, 2))
    return Image.fromarray(out), w, h

if __name__ == '__main__':
    shutil.rmtree(PACK, ignore_errors=True); PACK.mkdir(parents=True); OUT.mkdir(parents=True, exist_ok=True)
    rgbs = {}
    for key in SIGNS:
        for season in 'sw':
            tex = f'obj_{season}_{key}'; w, h = SIZES[tex]
            img = untile(nm.blob(tex), w, h)
            rgbs[tex] = np.array(nm.palette(pal_name(key[4], season)), np.uint8)[img][..., :3]
    esr = esr_all(rgbs)
    for key, rects in SIGNS.items():
        k = key[4]
        for season in 'sw':
            tex = f'obj_{season}_{key}'; pal = pal_name(k, season)
            im, w, h = build(tex, pal, rects, esr)
            (PACK/tb.pack_name(tex, 'CI', 4, w, h, pal)).write_bytes(tb.dds_rgba(im))
            im.save(OUT/f'{tex}.png')
    print('pack files', len(list(PACK.iterdir())))
