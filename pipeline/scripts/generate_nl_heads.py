"""New Leaf player heads on the GameCube player.

Each of the GC face types (8 per gender) gets a New Leaf hairstyle, hair colour and face. The New Leaf head
(hair/head shell + eye and mouth patches, which close the face) replaces the GC head display list on the head
joint; its proportions balance the original skull and face widths, anchored at the original collar.
Both games model the head bone along +x with the face at +z.

Colours:
- skin = the GC face palette's skin entry, read at draw time (so face type and suntan colour it like the GC head):
  the head texture's alpha marks skin (combiner: lerp(texture, ENV, texture alpha) * shade), and the eye/mouth
  patches are drawn first in plain skin, then their artwork on top.
- eyes and mouth: the patches sample the GC eye/mouth textures (segments 8/9), so the GC talk/blink animation
  drives them; a texture pack (nl_faces) replaces every GC eye/mouth frame with the matching New Leaf frame
  (same 8 eye + 6 mouth frame order in both games), transparent where skin shows, iris in the GC face's eye colour.

Output: pc/src/pc_nl_heads.c_inc (+ texture_pack_staging/nl_faces). pc_nl_heads_frame() (called from the player
draw) picks the head for the player's gender/face type and sets the skin colour. PC_GC_HEAD=1 keeps the GC head.
"""
import json, re, shutil, sys
from pathlib import Path
import numpy as np
from PIL import Image
import native_models as nm
import generate_chr_smooth as g
sys.argv = sys.argv[:1]
import export_character_handoff as ex
import texture_bake as tb

ROOT = Path(__file__).resolve().parent
SRC = ROOT/'player_source'
OUT = ROOT/'ACGC-PC-Port/pc/src/pc_nl_heads.c_inc'
PACK = ROOT/'texture_pack_staging/nl_faces'
NL_SKIN = np.array([255, 189, 148.])                    # = GC face palette entry 4 (untanned)
SKIN_IDX = 4
# New Leaf's hair is one flat colour on the head shell; its look comes from the lighting (rim + specular LUTs),
# which the renderer applies to these display lists (PC_NOOP_NL_CHAR_ON). PAINTED = 1 brings back the earlier
# painted strands / sheen and skin shadow for GC lighting.
PAINTED = 0
UP = 2
# GC face type (1-8) -> New Leaf face / hairstyle, picked by look (eye shape, lashes, brows)
FACE = {'boy': [0, 1, 2, 3, 5, 6, 7, 4], 'girl': [0, 1, 6, 3, 7, 5, 2, 8]}
HAIR = {'boy': [0, 1, 2, 3, 4, 5, 6, 7], 'girl': [0, 1, 2, 3, 4, 5, 6, 7]}
HAIR_COLOUR = [(118, 72, 40), (52, 40, 38), (170, 110, 60), (150, 64, 40),
               (85, 55, 40), (225, 185, 110), (190, 80, 50), (110, 90, 80)]
PLAYERS = [('boy', 0, 'boy_model.c', 'head_boy_model', 'cKF_bs_r_boy_1'),
           ('girl', 1, 'girl_model.c', 'head_grl_model', 'cKF_bs_r_grl_1')]

def gc_eye_box(mfile, dlname):
    text = (ROOT/'ACGC-PC-Port/src/data/model'/mfile).read_text()
    va = {a: nm.vertices(a) for a in set(re.findall(r'gsSPVertex\(&?(\w+)', text)) if a in nm.sym}
    body = re.search(rf'Gfx {dlname}\[\] = \{{(.*?)\n\}};', text, re.S).group(1)
    items, _ = g.parse_dl(re.sub(r'//[^\n]*', '', body), va)
    cur = None; pts = []
    for k, v in items:
        if k == 'state' and 'TextureImage' in v: cur = v
        if k == 'tris':
            for t in v:
                for x in t:
                    if x.mtx and '[12]' in x.mtx and cur and 'anime_1_txt' in cur: pts.append(x.p)
    P = np.array(pts)
    return P.min(0), P.max(0)

def gc_head_fit(mfile, dlname):
    """Fit the shared NL skull to the GC skull, excluding hats and hair ornaments.
    A common anatomical reference keeps all hairstyles and hats at the same scale.
    """
    text = (ROOT/'ACGC-PC-Port/src/data/model'/mfile).read_text()
    va = {a: nm.vertices(a) for a in set(re.findall(r'gsSPVertex\(&?(\w+)', text)) if a in nm.sym}
    body = re.search(rf'Gfx {dlname}\[\] = \{{(.*?)\n\}};', text, re.S).group(1)
    items, _ = g.parse_dl(body, va)
    cur = ''; pts = []
    for k, v in items:
        if k == 'state' and 'TextureImage' in v: cur = v
        if k == 'tris' and any(t in cur for t in ('skin_tex', 'anime_1_txt', 'anime_2_txt')):
            pts += [x.p for tri in v for x in tri if x.mtx and '[12]' in x.mtx]
    P = np.array(pts)
    ref = json.loads((SRC/'head_mdl/boy00a/boy00a.json').read_text())
    Q = np.array([v['position'] for m in ref['meshes'] for v in m['vertices']])
    skull_scale = np.ptp(P[:, 1])/np.ptp(Q[:, 1])
    emin, emax = gc_eye_box(mfile, dlname)
    E = np.array([v['position'] for m in ref['meshes'] if m['texture'][0] == 'e' for v in m['vertices']])
    eye_scale = (emax[1]-emin[1])/np.ptp(E[:, 1])
    # Balance face and skull proportions: shell width alone made the face too small.
    scale = np.sqrt(skull_scale*eye_scale)
    # Attach at the original collar ring, not the nose/front plane. The two
    # games have different facial depth, so front-plane matching moves the
    # entire skull ahead of the neck. NL's bottom-center vertex is z=0.
    collar = np.array([x.p for k, ts in items if k == 'tris' for tri in ts
                       if any(v.mtx and '[7]' in v.mtx for v in tri)
                       for x in tri if x.mtx and '[12]' in x.mtx])
    offset = np.array([collar[:, 0].min()-scale*Q[:, 0].min(),
                       (collar[:, 1].min()+collar[:, 1].max())/2,
                       (collar[:, 2].min()+collar[:, 2].max())/2])
    return scale, offset


def emit_gc_collar(out, mfile, dlname, sexi):
    """Preserve the original nine triangles that stitch torso to head bone."""
    text = (ROOT/'ACGC-PC-Port/src/data/model'/mfile).read_text()
    body = re.search(rf'Gfx {dlname}\[\] = \{{(.*?)\n\}};', text, re.S).group(1)
    end = list(re.finditer(r'gsSPNTriangles_5b\([^)]*\),', body))[1].end()
    body = body[:end]
    arr = re.search(r'gsSPVertex\((\w+),', body).group(1)
    count = 21 if sexi == 0 else 19
    vn = f'pc_nlh_collar_v{sexi}'
    out.append(f'static Vtx {vn}[] = {{')
    for x,y,z,f,u,v,r,g_,b,a in nm.vertices(arr)[:count]:
        out.append('{{{%d,%d,%d},%d,{%d,%d},{%d,%d,%d,%d}}},' % (x,y,z,f,u,v,r,g_,b,a))
    out += ['};', f'static Gfx pc_nlh_collar_{sexi}[] = {{', body.replace(arr,vn), 'gsSPEndDisplayList(),', '};']

def surface_maps(vs, size):
    """per texel of the head texture: height along the head (0 = neck, 1 = crown) and angle around it, from the
    triangles that use that texel (rasterised in UV space)"""
    P = np.array([v['position'] for v in vs], float)
    lo, hi = P[:, 0].min(), P[:, 0].max()
    H = np.full((size, size), np.nan); A = np.full((size, size), np.nan); N = np.full((size, size, 3), np.nan)
    yy, xx = np.mgrid[0:size, 0:size]+0.5
    for i in range(0, len(vs), 3):
        t = vs[i:i+3]
        uv = np.array([[v['uv'][0]*size, (1-v['uv'][1])*size] for v in t])
        x0, y0 = np.floor(uv.min(0)).astype(int); x1, y1 = np.ceil(uv.max(0)).astype(int)
        x0, y0 = max(x0, 0), max(y0, 0); x1, y1 = min(x1, size), min(y1, size)
        if x1 <= x0 or y1 <= y0: continue
        (ax, ay), (bx, by), (cx, cy) = uv
        den = (by-cy)*(ax-cx)+(cx-bx)*(ay-cy)
        if abs(den) < 1e-9: continue
        X = xx[y0:y1, x0:x1]; Y = yy[y0:y1, x0:x1]
        w0 = ((by-cy)*(X-cx)+(cx-bx)*(Y-cy))/den; w1 = ((cy-ay)*(X-cx)+(ax-cx)*(Y-cy))/den; w2 = 1-w0-w1
        inside = (w0 >= -0.02) & (w1 >= -0.02) & (w2 >= -0.02)
        p3 = np.array([v['position'] for v in t], float)
        hgt = (w0*p3[0, 0]+w1*p3[1, 0]+w2*p3[2, 0]-lo)/max(hi-lo, 1e-6)
        ang = np.arctan2(w0*p3[0, 1]+w1*p3[1, 1]+w2*p3[2, 1], w0*p3[0, 2]+w1*p3[1, 2]+w2*p3[2, 2])
        H[y0:y1, x0:x1] = np.where(inside, hgt, H[y0:y1, x0:x1]); A[y0:y1, x0:x1] = np.where(inside, ang, A[y0:y1, x0:x1])
        n3 = np.array([v['normal'] for v in t], float)
        nn = w0[..., None]*n3[0]+w1[..., None]*n3[1]+w2[..., None]*n3[2]
        N[y0:y1, x0:x1] = np.where(inside[..., None], nn, N[y0:y1, x0:x1])
    from scipy.ndimage import distance_transform_edt
    miss = np.isnan(H)
    if miss.any() and (~miss).any():
        _, (iy, ix) = distance_transform_edt(miss, return_indices=True); H = H[iy, ix]; A = A[iy, ix]; N = N[iy, ix]
    N = np.nan_to_num(N); N /= np.maximum(np.linalg.norm(N, axis=-1, keepdims=True), 1e-6)
    return np.nan_to_num(H), np.nan_to_num(A), N

def uv_wraps(vs):
    """heads whose UVs run well outside 0..1 keep the original per-triangle tile shift and wrapped coverage; the rest are
    clamped (the shift swapped edge texels on them and painted off-tone triangles on the face)"""
    uv = np.array([v['uv'] for v in vs], float)
    return uv.min() < -0.01 or uv.max() > 1.01

def uv_coverage(vs, size):
    """texels of a size x size texture covered by the triangles' UVs"""
    cover = np.zeros((size, size), bool)
    wraps = uv_wraps(vs)
    yy, xx = np.mgrid[0:size, 0:size]+0.5
    for i in range(0, len(vs), 3):
        uv = np.array([[(v['uv'][0] % 1.0000001 if wraps else np.clip(v['uv'][0], 0, 0.9999999))*size, ((1-v['uv'][1]) % 1.0000001 if wraps else np.clip(1-v['uv'][1], 0, 0.9999999))*size] for v in vs[i:i+3]])
        (ax, ay), (bx, by), (cx, cy) = uv
        den = (by-cy)*(ax-cx)+(cx-bx)*(ay-cy)
        if abs(den) < 1e-9: continue
        w0 = ((by-cy)*(xx-cx)+(cx-bx)*(yy-cy))/den; w1 = ((cy-ay)*(xx-cx)+(ax-cx)*(yy-cy))/den
        cover |= (w0 >= -0.01) & (w1 >= -0.01) & (1-w0-w1 >= -0.01)
    # Several cheek/neck triangles intentionally sample a single skin texel.
    # They have zero UV area, but must survive island padding too.
    for v in vs:
        x = int(np.clip(v['uv'][0]*size, 0, size-1))
        y = int(np.clip((1-v['uv'][1])*size, 0, size-1))
        cover[max(0,y-1):min(size,y+2), max(0,x-1):min(size,x+2)] = True
    return cover

def pad_islands(a, cover):
    """texels outside every UV island take their nearest island texel"""
    from scipy.ndimage import distance_transform_edt
    if not cover.any() or cover.all(): return a
    _, (iy, ix) = distance_transform_edt(~cover, return_indices=True)
    return a[iy, ix]

def bake_head(n, hair, vs=None):
    """RGB = hair (shaded); alpha = 1 where hair, outlines or shading show, 0 where the run-time skin colour shows.
    The hair gets New Leaf-style painted shading: darker towards the ends, a soft highlight ring near the crown and
    fine strands running down the head."""
    h0 = np.asarray(Image.open(SRC/f'head_mdl/{n}/h.png').convert('RGBA')).astype(float)
    c0 = np.asarray(Image.open(SRC/f'head_mdl/{n}/hC.png').convert('RGBA')).astype(float)
    if vs is not None:
        # pad the UV islands at the source resolution first, so upscaling can't blur one island's hair coverage
        # into a neighbouring island's skin (that drew faint seam lines along island edges on the face)
        cov = uv_coverage(vs, h0.shape[0])
        h0 = pad_islands(h0, cov); c0 = pad_islands(c0, cov)
    up = lambda a: np.asarray(Image.fromarray(np.clip(a, 0, 255).astype(np.uint8), 'RGBA').resize((64*UP, 64*UP), Image.BICUBIC)).astype(float)
    h = up(h0); c = up(c0)
    sk = c[..., 3:4]/max(c[..., 3].max(), 1.0)
    shade = np.ones(h.shape[:2])
    if vs is not None and PAINTED:
        H, A, N = surface_maps(vs, h.shape[0])
        rng = np.random.default_rng(len(n))
        strands = np.interp(A*24/np.pi % 48, np.arange(49), np.r_[rng.normal(0, 1, 48), 0])
        strands = 0.5*strands+0.5*np.sin(A*37+H*3)
        shade = (0.80+0.28*np.clip(H, 0, 1))                                  # ends darker, top lighter
        shade *= 1+0.20*np.exp(-((H-0.80)/0.07)**2)                            # highlight ring
        shade *= 1+0.06*strands*(1-np.exp(-((H-0.80)/0.07)**2)*0.5)            # strands
        up = N[..., 0]                                                         # head space: +x is up
        side = np.sqrt(np.clip(1-up**2, 0, 1))
        sheen = np.clip((up*0.75+side*0.66-0.55)/0.45, 0, 1)**3                # New Leaf specular sheen
        rim = np.clip(side-0.55, 0, 1)/0.45*np.clip(1-H*1.2, 0, 1)             # rim light on the lower sides
        shade = shade*(1+0.30*sheen*(0.6+0.4*np.clip(strands+0.5, 0, 1)))+0.16*rim
        shade *= 0.92+0.08*np.clip(up+1, 0, 1)                                 # under-hair a little darker
    hr = np.array(hair, float)*(h[..., :3]/179.0).clip(0, 1.12)*shade[..., None]
    line = 1-0.45*c[..., :3]/255
    if not PAINTED:
        # New Leaf: base = hair mask * hair colour + skin mask (hC alpha) * skin colour, two flat colours. hC's rgb
        # (the hair mask) comes out garbled from Ohana's ETC1A4 export, so it must not darken anything here
        line = np.ones_like(line)
        hr = np.broadcast_to(np.array(hair, float), hr.shape)
    # skin shading (New Leaf lights skin with a soft shadow under the hair and a darker neck): the run-time skin
    # colour is lerped towards black by the alpha, so skin = ENV * sk * line * ss
    ss = np.ones(h.shape[:2])
    if vs is not None and PAINTED:
        from scipy.ndimage import distance_transform_edt
        dist = distance_transform_edt(sk[..., 0] > 0.5)/UP                     # texels (64 res) from the hair
        # (baked soft shadow under the hair / dark neck removed: single-texel face triangles picked up different amounts
        #  of it and showed as patches of a different skin tone; the real lighting shades the skin)
        pass
    k = sk[..., 0]*line[..., 0]*ss
    alpha = 1-k                                          # alpha = hair (and outline/shading); 0 = run-time skin
    col = hr*(1-sk)*line/np.maximum(alpha, 1e-3)[..., None]
    out = np.dstack([np.clip(col, 0, 255), np.clip(alpha*255, 0, 255)]).astype(np.float64)
    # the New Leaf skin mask is not flat inside the skin (soft variations): wherever the texel is only faintly hair
    # (< 40%), use plain skin, so the face is one colour and only the lighting shades it
    out[out[..., 3] < 100, :] = 0
    if vs is not None:
        # Single-texel (zero UV area) shell triangles: a texel that is only faintly hair/outline (alpha < 40%) gave that
        # one flat triangle a slightly different skin tone, a visible seam on the forehead and cheeks. Snap to pure skin.
        wr = uv_wraps(vs); size = out.shape[0]
        for i in range(0, len(vs), 3):
            uvs = np.array([v['uv'] for v in vs[i:i+3]], float)
            d1, d2 = uvs[1]-uvs[0], uvs[2]-uvs[0]
            if abs(d1[0]*d2[1]-d1[1]*d2[0])/2*size*size >= 0.5: continue
            for u, v in uvs:
                if wr: u, v = u % 1.0000001, v % 1.0000001
                x = int(np.clip(u*size, 0, size-1)); y = int(np.clip((1-v)*size, 0, size-1))
                r = max(2, size//64)
                blk = out[max(0, y-r):y+r+1, max(0, x-r):x+r+1]
                faint = blk[..., 3] < 100
                blk[faint, 3] = 0; blk[faint, :3] = 0
        if uv_wraps(vs):
            # shifted-texture heads: triangles on the lower front of the face (below the eyes) that land on a hair texel
            # drew a beard; those texels are skin
            dj = json.load(open(SRC/f'head_mdl/{n}/{n}.json')); pm = {m['texture'][0]: m for m in dj['meshes']}
            ep = np.array([v['position'] for v in pm['e']['vertices']], float)
            fp = np.array([v['position'] for k in 'em' for v in pm[k]['vertices']], float)
            xlim, ylim, zmin = ep[:, 0].min()+1.5, np.abs(fp[:, 1]).max(), fp[:, 2].min()
            size = out.shape[0]
            for i in range(0, len(vs), 3):
                c = np.mean([v['position'] for v in vs[i:i+3]], 0)
                if not (c[0] <= xlim and abs(c[1]) <= ylim and c[2] >= zmin): continue
                for v in vs[i:i+3]:
                    x = int(np.clip((v['uv'][0] % 1.0000001)*size, 0, size-1)); y = int(np.clip(((1-v['uv'][1]) % 1.0000001)*size, 0, size-1))
                    out[max(0, y-1):y+2, max(0, x-1):x+2, 3] = 0; out[max(0, y-1):y+2, max(0, x-1):x+2, :3] = 0
        # pad every UV island outwards so filtering at island edges never pulls in texels from outside it (that
        # showed as thin seam lines on the face under the New Leaf lighting)
        out = pad_islands(out, uv_coverage(vs, out.shape[0]))
    return Image.fromarray(out.astype(np.uint8), 'RGBA')

def iris_colour(sex, ft):
    """the GC face's eye colour: its most common clearly coloured (not skin, nose red or outline brown) texel colour
    in the open-eye frame; plain dark brown when the GC eyes are black/brown"""
    import colorsys
    face = (ex.ARC/'face_boy.bin').read_bytes(); base = (ft+sex*8)*0xE20
    pal = np.array(ex.pal16(face[base+0xE00:base+0xE20]), float)
    img = ex.untile(face[base:base+0x100], 32, 16)
    best = None
    for i, n in zip(*np.unique(img, return_counts=True)):
        if pal[i][3] < 128 or i == SKIN_IDX: continue
        hh, ss, vv = colorsys.rgb_to_hsv(*(pal[i][:3]/255))
        if ss < 0.35 or vv < 0.25 or hh < 0.13 or hh > 0.95: continue        # greys, browns, reds/oranges
        if best is None or n > best[0]: best = (n, pal[i][:3])
    return np.array(best[1]) if best is not None else np.array([70, 45, 35.])

def face_art(path, cpath, iris):
    """New Leaf frame -> RGBA artwork; transparent where New Leaf shows plain skin"""
    e = np.asarray(Image.open(path).convert('RGBA')).astype(float)
    m = np.asarray(Image.open(cpath).convert('RGBA')).astype(float)[..., 3:4]/255 if cpath else np.zeros(e.shape[:2]+(1,))
    a = e[..., 3:4]/255
    col = e[..., :3]*(1-m)+(iris if iris is not None else 0)*m
    hl = e[..., :3].min(-1, keepdims=True) > 200
    col = np.where(hl & (m > 0.5), e[..., :3], col)
    vis = np.clip(np.maximum(1-a, m), 0, 1)
    return np.dstack([np.clip(col, 0, 255), vis*255])

def eye_art(nl, k, iris):
    """New Leaf eye frame as New Leaf's shader draws it: colour = skin * eC.rgb + e.rgb + iris * eC.a, where eC.rgb is
    the skin mask (0 at the outlines and the ruddy nose, which e.rgb colours). Read with the correct 3DS decoder
    (nl_head_research/ctr_tex.py): Ohana's PNG export garbles ETC1A4 colour, so eC.png's rgb is unusable."""
    import sys
    sys.path.insert(0, str(ROOT/'nl_head_research')); import ctr_tex
    t = ctr_tex.textures(str(SRC/f'face_tex/{nl}.bcres'))
    e = t[f'e.{k}'][1].astype(float); c = t[f'eC.{k}'][1].astype(float)
    S = c[..., :3].mean(-1, keepdims=True)/255                    # skin mask
    m = c[..., 3:4]/255                                            # iris mask
    vis = np.clip(1-S, 0, 1)
    # the nose (New Leaf's ruddy (216,63,0)) brightened to a clear orange, as asked
    nose = (e[..., 0:1] > 150) & (e[..., 1:2] < 110) & (e[..., 2:3] < 60)
    e[..., :3] = np.where(nose, e[..., :3]*[1.08, 1.75, 1.0]+[0, 0, 24], e[..., :3])
    col = (e[..., :3]+(iris if iris is not None else 0)*m)/np.maximum(vis, 1e-3)
    return np.dstack([np.clip(col, 0, 255), vis*255])

SKIN = np.array([255.0, 189.0, 148.0])
def defringe(a):
    """transparent texels carry arbitrary (black) colour; the upscale and the sampler blend it into the outline as a dark
    halo around eyes, nose and mouth. Composite the colour over skin so edges only blend toward skin."""
    al = a[..., 3:4]/255
    a[..., :3] = a[..., :3]*al+SKIN*(1-al)
    return a

def eye_image(nl, k, iris):
    a = eye_art(nl, k, iris)
    # see-through eye whites: texels enclosed by the eye outline that would show skin are the white of the eye
    from scipy.ndimage import label, binary_dilation
    clear = a[..., 3] < 128
    lab, n = label(clear)
    border = set(np.unique(np.concatenate([lab[0], lab[-1], lab[:, 0], lab[:, -1]])))
    inside = clear & ~np.isin(lab, list(border)) & (lab > 0)
    a[inside, :3] = 250; a[inside, 3] = 255
    a = defringe(a)
    return Image.fromarray(a.astype(np.uint8), 'RGBA').resize((a.shape[1]*UP, a.shape[0]*UP), Image.BICUBIC)

def mouth_image(nl, k):
    a = face_art(SRC/f'face_tex/{nl}/m.{k}.png', None, None)
    a = np.concatenate([a, a[:, ::-1]], 1)               # New Leaf mirrors the mouth in U: [m | mirror(m)]
    a = defringe(a)
    return Image.fromarray(a.astype(np.uint8), 'RGBA').resize((a.shape[1]*UP*2, a.shape[0]*UP*2), Image.BICUBIC)

def rgba8(name, im, out):
    w, h = im.size; data = bytearray()
    for ty in range(0, h, 4):
        for tx in range(0, w, 4):
            tile = [im.getpixel((tx+x, ty+y)) for y in range(4) for x in range(4)]
            data.extend(cc for r, g_, b, a in tile for cc in (a, r)); data.extend(cc for r, g_, b, a in tile for cc in (g_, b))
    out.append(f'static u8 {name}[] ATTRIBUTE_ALIGN(32) = {{')
    out.extend(','.join(map(str, data[i:i+32]))+',' for i in range(0, len(data), 32)); out.append('};')

def smooth_head(vs, levels=2, pn=0.35):
    """PN-triangle subdivision of a New Leaf triangle list (vertex copies welded by position so every copy of an
    edge gets the same curved midpoint), and normals turned outwards from the head centre where they point in
    (the open underside / inner shell of the hair would otherwise light up black)."""
    P = np.array([v['position'] for v in vs], float)
    centre = (P.min(0)+P.max(0))/2
    tris = [[dict(p=np.array(v['position'], float), n=np.array(v['normal'], float), uv=np.array(v['uv'], float))
             for v in vs[i:i+3]] for i in range(0, len(vs), 3)]
    key = lambda q: tuple(np.round(q*64).astype(int))
    for _ in range(levels):
        nsum = {}
        for t in tris:
            for v in t: nsum[key(v['p'])] = nsum.get(key(v['p']), 0)+v['n']
        mids = {}
        def mid(a, b):
            ka, kb = key(a['p']), key(b['p'])
            lo, hi = (a, b) if ka <= kb else (b, a)
            k = (min(ka, kb), max(ka, kb))
            if k not in mids:
                n1 = nsum[key(lo['p'])]; n2 = nsum[key(hi['p'])]
                n1 = n1/max(np.linalg.norm(n1), 1e-9); n2 = n2/max(np.linalg.norm(n2), 1e-9)
                d = hi['p']-lo['p']
                b1 = (2*lo['p']+hi['p']-np.dot(d, n1)*n1)/3; b2 = (2*hi['p']+lo['p']+np.dot(d, n2)*n2)/3
                mids[k] = (lo['p']+hi['p'])/2*(1-pn)+(lo['p']+3*b1+3*b2+hi['p'])/8*pn
            nn = a['n']+b['n']
            return dict(p=mids[k], n=nn/max(np.linalg.norm(nn), 1e-9), uv=(a['uv']+b['uv'])/2)
        out = []
        for a, b, c in tris:
            ab, bc, ca = mid(a, b), mid(b, c), mid(c, a)
            out += [[a, ab, ca], [ab, b, bc], [ca, bc, c], [ab, bc, ca]]
        tris = out
    # one normal per position: New Leaf's per-copy normals differ at UV seams and where the eye/mouth patches meet
    # the shell, which the per-pixel New Leaf lighting shows as hard seams
    # (only copies within ~60 degrees are averaged, so real creases such as the fringe's edge stay sharp)
    # copies are grouped (each joins the first group whose seed normal is within ~100 degrees; the fringe edges are 120+) and every member of a
    # group gets the group's mean, so the shell and patch copies of a border vertex always agree exactly
    groups = {}
    for t in tris:
        for v in t:
            n0 = v['n']/max(np.linalg.norm(v['n']), 1e-9); gl = groups.setdefault(key(v['p']), [])
            for gr in gl:
                if np.dot(gr[0], n0) > -0.2: gr[1].append(n0); break
            else: gl.append((n0, [n0]))
    # relax the group normals across neighbouring vertices (only between similar normals, so real creases stay): the
    # flat-shaded look of big face triangles becomes one smooth skin surface
    gid = {}
    for k, gl in groups.items():
        for gi, gr in enumerate(gl):
            m = sum(gr[1]); gid[(k, gi)] = m/max(np.linalg.norm(m), 1e-9)
    nbr = {}
    for t in tris:
        ks = [key(v['p']) for v in t]
        for a in ks:
            for b in ks:
                if a != b: nbr.setdefault(a, set()).add(b)
    for _ in range(3):
        new_gid = {}
        for (k, gi), n in gid.items():
            acc = n.copy()
            for kb in nbr.get(k, ()):
                for gj in range(len(groups[kb])):
                    nb = gid[(kb, gj)]
                    if np.dot(nb, n) > 0.8: acc = acc+nb
            new_gid[(k, gi)] = acc/max(np.linalg.norm(acc), 1e-9)
        gid = new_gid
    res = []
    for t in tris:
        for v in t:
            n0 = v['n']/max(np.linalg.norm(v['n']), 1e-9)
            gl = groups[key(v['p'])]
            gi = next(i for i, gr in enumerate(gl) if np.dot(gr[0], n0) > -0.2 and any(np.array_equal(n0, x) for x in gr[1]))
            n = gid[(key(v['p']), gi)]
            res.append(dict(position=list(v['p']), normal=list(n), uv=list(v['uv'])))
    return res

def hair_weight(n):
    """hair coverage of the head texture (1 = hair, 0 = skin), from the colour mask"""
    c = np.asarray(Image.open(SRC/f'head_mdl/{n}/hC.png').convert('RGBA')).astype(float)
    return 1-c[..., 3]/max(c[..., 3].max(), 1.0)

def hair_volume(vs, W, base=0.55, ridge=0.45, clumps=11):
    """New Leaf's hair is part of the head shell; give it volume: hair vertices move out along their normal (so the
    hair stands off the skin with a lip at the hairline) plus strand clumps running down the head, deeper towards
    the ends. Copies of a vertex share one displacement (keyed by position), and normals are rebuilt."""
    size = W.shape[0]
    def w_at(uv):
        u = uv[0] % 2; v = (1-uv[1]) % 2
        u = 2-u if u > 1 else u; v = 2-v if v > 1 else v
        return W[min(int(v*size), size-1), min(int(u*size), size-1)]
    P = np.array([v['position'] for v in vs], float)
    lo, hi = P[:, 0].min(), P[:, 0].max()
    key = lambda q: tuple(np.round(np.array(q)*64).astype(int))
    wk, nk = {}, {}
    for v in vs:
        k = key(v['position'])
        wk[k] = max(wk.get(k, 0.0), w_at(v['uv']))
        nk[k] = nk.get(k, 0)+np.array(v['normal'], float)
    dk = {}
    for k, w in wk.items():
        p = np.array(k, float)/64
        hgt = (p[0]-lo)/max(hi-lo, 1e-6); ang = np.arctan2(p[1], p[2])
        r = 0.5+0.5*np.cos(ang*clumps+1.7*np.sin(hgt*4.0))                      # 1 on a clump, 0 in a groove
        n = nk[k]/max(np.linalg.norm(nk[k]), 1e-9)
        w = np.clip((w-0.15)/0.6, 0, 1)
        dk[k] = n*w*(base+ridge*(r-0.5)*(0.5+0.8*np.clip(1-hgt, 0, 1)))
    out = [dict(v, position=list(np.array(v['position'])+dk[key(v['position'])])) for v in vs]
    # normals from the displaced surface, blended with the smooth ones (keeps the soft New Leaf look)
    fn = {}
    for i in range(0, len(out), 3):
        a, b, c = (np.array(v['position']) for v in out[i:i+3])
        f = np.cross(b-a, c-a)
        for v in vs[i:i+3]:
            fn[key(v['position'])] = fn.get(key(v['position']), 0)+f
    for v0, v in zip(vs, out):
        k = key(v0['position']); g = fn[k]/max(np.linalg.norm(fn[k]), 1e-9)
        n0 = np.array(v0['normal'], float)
        if np.dot(g, n0) < 0: g = -g
        m = n0*0.45+g*0.55 if wk[k] > 0.3 else n0
        v['normal'] = list(m/max(np.linalg.norm(m), 1e-9))
    return out

def emit_vtx(out, vname, vs, s, off, uv):
    out.append(f'static Vtx {vname}[] ATTRIBUTE_ALIGN(32) = {{')
    for i in range(0, len(vs), 3):
        tri = vs[i:i+3]; st = [uv(v['uv'], tri) for v in tri]
        for v, (su, tv) in zip(tri, st):
            p = s*np.array(v['position'])+off
            nn = np.array(v['normal'], float); nn /= max(np.linalg.norm(nn), 1e-9)
            out.append('{{{%d,%d,%d},0,{%d,%d},{%s,255}}},' % (round(p[0]), round(p[1]), round(p[2]), round(su), round(tv),
                       ','.join(str(int(round(c*120)) & 255) for c in nn)))
    out.append('};')

def tris(dl, vname, n):
    for base in range(0, n, 30):
        k = min(30, n-base); dl.append(f'gsSPVertex(&{vname}[{base}],{k},0),')
        dl += [f'gsSP1Triangle({j},{j+1},{j+2},0),' for j in range(0, k, 3)]

def main():
    out = ['/* Generated by generate_nl_heads.py: New Leaf player heads. */',
           'Gfx pc_nlh_env[] = { gsDPSetEnvColor(255,189,148,255), gsSPEndDisplayList() };']
    heads = {}; fits = {}; blocks = []
    for sex, sexi, mfile, dlname, skel in PLAYERS:
        s, off = gc_head_fit(mfile, dlname)
        emit_gc_collar(out, mfile, dlname, sexi)
        for ft, var in [(f, v) for f in range(8) for v in 'ab']:      # b = the short version worn under hats
            start = len(out)
            hs = f'{sex}{HAIR[sex][ft]:02d}{var}'
            d = json.load(open(SRC/f'head_mdl/{hs}/{hs}.json'))
            meshes = {m['texture'][0]: m for m in d['meshes']}
            tag = f'{sex}{ft}{var}'
            fits[sexi] = (s, off)
            him = bake_head(hs, HAIR_COLOUR[ft], meshes['h']['vertices']); tw, th = him.size
            rgba8(f'pc_nlh_{tag}_htex', him, out)
            def uv_head(u, tri, tw=tw, th=th):
                su = sv = 0
                if uv_wraps(meshes['h']['vertices']) and not all(0 <= x <= 1 for v in tri for x in v['uv']):
                    su = 2*np.floor(min(v['uv'][0] for v in tri)/2); sv = 2*np.floor(min(v['uv'][1] for v in tri)/2)
                    if max(abs(tri[0]['uv'][k]-tri[j]['uv'][k]) for j in (1,2) for k in (0,1)) < 0.02 and abs(np.mean([v['position'][1] for v in tri])) < 9 and ((np.mean([v['position'][0] for v in tri]) < 10.5 and np.mean([v['position'][2] for v in tri]) > 4.8) or (np.mean([v['position'][0] for v in tri]) < 5.5 and np.mean([v['position'][2] for v in tri]) > 2.5)):   # lower-front single-texel triangle: wrap by whole tiles, don't clamp to the edge
                        su = np.floor(tri[0]['uv'][0]); sv = np.floor(tri[0]['uv'][1])
                return (u[0]-su)*tw*32, (1-(u[1]-sv))*th*32
            # head shell and face patches subdivided together so their shared edges stay closed
            hv0, ev0, mv0 = meshes['h']['vertices'], meshes['e']['vertices'], meshes['m']['vertices']
            allv = smooth_head(hv0+ev0+mv0)
            hverts = allv[:len(hv0)*16]; everts = allv[len(hv0)*16:(len(hv0)+len(ev0))*16]; mverts = allv[(len(hv0)+len(ev0))*16:]
            # where the eye/mouth patches meet the head shell, the patch takes the shell's normal so the New Leaf
            # lighting has no step at the patch border
            kk = lambda q: tuple(np.round(np.array(q)*64).astype(int))
            shelln = {}
            for v in hverts: shelln.setdefault(kk(v['position']), []).append(np.array(v['normal']))
            for v in everts+mverts:
                ns = shelln.get(kk(v['position']))
                if ns:
                    v['normal'] = list(max(ns, key=lambda n: np.dot(n, v['normal'])))
            emit_vtx(out, f'pc_nlh_{tag}_hv', hverts, s, off, uv_head)
            # eye: GC eye texture is 32x16, clamped; New Leaf eye UVs map straight onto it
            emit_vtx(out, f'pc_nlh_{tag}_ev', everts, s, off,
                     lambda u, tri: (u[0]*32*32, (1-u[1])*16*32))
            # mouth: GC 32x16 holds [m | mirror(m)] = New Leaf U range 0..2 -> u/2, mirrored beyond
            emit_vtx(out, f'pc_nlh_{tag}_mv', mverts, s, off,
                     lambda u, tri: (u[0]/2*32*32, (1-u[1])*16*32))
            ne, nmo, nh = len(everts), len(mverts), len(hverts)
            dl = [f'Gfx pc_nlh_{tag}[] = {{', 'gsDPPipeSync(),', 'gsDPNoOpTag(PC_NOOP_NL_CHAR_ON),',  # New Leaf lighting
                  'gsSPMatrix(&anime_6_mdl[12], G_MTX_NOPUSH | G_MTX_LOAD | G_MTX_MODELVIEW),',
                  'gsSPDisplayList(pc_nlh_env),', 'gsDPSetPrimColor(0,128,255,255,255,255),',
                  'gsSPLoadGeometryMode(G_ZBUFFER|G_SHADE|G_CULL_BACK|G_FOG|G_LIGHTING|G_SHADING_SMOOTH),',
                  'gsDPSetRenderMode(G_RM_FOG_SHADE_A,G_RM_AA_ZB_OPA_SURF2),',
                  # head: skin (alpha) from ENV, hair from the texture
                  'gsSPTexture(0,0,0,G_TX_RENDERTILE,G_ON),',
                  'gsDPSetCombineLERP(TEXEL0,ENVIRONMENT,TEXEL0_ALPHA,ENVIRONMENT,0,0,0,1,COMBINED,0,SHADE,0,0,0,0,COMBINED),',
                  f'gsDPSetTextureImage_Dolphin(G_IM_FMT_RGBA,G_IM_SIZ_32b,{tw},{th},pc_nlh_{tag}_htex),',
                  'gsDPSetTile_Dolphin(G_DOLPHIN_TLUT_DEFAULT_MODE,0,0,GX_CLAMP,GX_CLAMP,0,0),']
            tris(dl, f'pc_nlh_{tag}_hv', nh)
            # face patches in plain skin
            dl += ['gsDPSetCombineLERP(ENVIRONMENT,0,SHADE,0,0,0,0,1,COMBINED,0,PRIMITIVE,0,0,0,0,COMBINED),']
            tris(dl, f'pc_nlh_{tag}_ev', ne); tris(dl, f'pc_nlh_{tag}_mv', nmo)
            # eye / mouth artwork on top (GC frames, replaced by the nl_faces pack)
            dl += ['gsDPNoOpTag(PC_NOOP_NL_CHAR_NOSPEC),', 'gsDPSetCombineLERP(TEXEL0,0,SHADE,0,0,0,0,TEXEL0,PRIMITIVE,0,COMBINED,0,0,0,0,COMBINED),',
                   'gsDPSetRenderMode(G_RM_FOG_SHADE_A,G_RM_AA_ZB_XLU_DECAL2),',
                   'gsDPLoadTLUT_Dolphin(15, 16, 1, anime_5_txt),',
                   'gsDPSetTextureImage_Dolphin(G_IM_FMT_CI, G_IM_SIZ_4b, 32, 16, anime_1_txt),',
                   'gsDPSetTile_Dolphin(G_DOLPHIN_TLUT_DEFAULT_MODE, 0, 15, GX_CLAMP, GX_CLAMP, 0, 0),']
            tris(dl, f'pc_nlh_{tag}_ev', ne)
            dl += ['gsDPSetTextureImage_Dolphin(G_IM_FMT_CI, G_IM_SIZ_4b, 32, 16, anime_2_txt),',
                   'gsDPSetTile_Dolphin(G_DOLPHIN_TLUT_DEFAULT_MODE, 0, 15, GX_MIRROR, GX_CLAMP, 0, 0),']
            tris(dl, f'pc_nlh_{tag}_mv', nmo)
            dl += ['gsDPSetRenderMode(G_RM_FOG_SHADE_A,G_RM_AA_ZB_OPA_SURF2),', 'gsDPNoOpTag(PC_NOOP_NL_CHAR_OFF),',
                   'gsSPEndDisplayList(),', '};']
            out += dl
            heads[(sexi, ft, var)] = f'pc_nlh_{tag}'
            blocks.append(out[start:]); del out[start:]
            out.append(f'extern Gfx pc_nlh_{tag}[];')
        print(sex, 'scale', round(s, 1))
    out += ['extern cKF_Skeleton_R_c cKF_bs_r_boy_1;', 'extern cKF_Skeleton_R_c cKF_bs_r_grl_1;',
            '#include <stdio.h>', '#include <string.h>', '#include <SDL.h>',
            'extern int pc_nl_hat_count;', 'extern Gfx* pc_nl_hat_dl[];', 'extern const unsigned char pc_nl_hat_fullhair[];', 'extern const char* pc_nl_hat_name[];']
    for var in 'ab':
        out += [f'static Gfx* const pc_nlh_heads_{var}[2][8] = {{',
                '    { '+', '.join(heads[(0, f, var)] for f in range(8))+' },',
                '    { '+', '.join(heads[(1, f, var)] for f in range(8))+' },', '};']
    # hat space (New Leaf head units x100) -> GC head joint space, per gender
    for sexi in (0, 1):
        sc, of = fits[sexi]
        out.append(f'static const float pc_nlh_hatfit_{sexi}[4] = {{ {sc/100:.6f}f, {of[0]:.2f}f, {of[1]:.2f}f, {of[2]:.2f}f }};')
    out += r"""
static Gfx pc_nlh_slot[2][6];
static Mtx pc_nlh_hatmtx[2];
static int pc_nlh_hat = -2;          /* -2 = not loaded yet, -1 = no hat, else index into pc_nl_hat_dl */

static const char* pc_nlh_hat_env = NULL;  /* PC_HAT=<name>|none: preview override */
static int pc_nlh_hat_env_idx = -1;

static void pc_nlh_hat_load(void) {
    int i;
    extern char* getenv(const char*);
    pc_nlh_hat = -1;
    pc_nlh_hat_env = getenv("PC_HAT");
    if (pc_nlh_hat_env != NULL)
        for (i = 0; i < pc_nl_hat_count; i++) if (strcmp(pc_nlh_hat_env, pc_nl_hat_name[i]) == 0) pc_nlh_hat_env_idx = i;
    for (i = 0; i < 2; i++) {
        const float* fit = i ? pc_nlh_hatfit_1 : pc_nlh_hatfit_0;
        float mf[4][4] = { { fit[0], 0, 0, 0 }, { 0, fit[0], 0, 0 }, { 0, 0, fit[0], 0 }, { fit[1], fit[2], fit[3], 1 } };
        guMtxF2L(mf, &pc_nlh_hatmtx[i]);
    }
}

/* F8: take the worn hat off (into a free pocket); polled by the player draw */
/* character creator thread (pc_nl_creator.c): the player's chosen hairstyle/colour head, NULL = face default */
extern Gfx* pc_cc_head(int sex, int face, int short_hair) __attribute__((weak));

int pc_hat_take_off_pressed(void) {
    static int prev = 0;
    const Uint8* k = SDL_GetKeyboardState(NULL);
    int now = k != NULL && k[SDL_SCANCODE_F8];
    int hit = now && !prev;
    prev = now;
    return hit;
}

void pc_nl_heads_frame(int sex, int face, const u16* pal, int hat) {
    extern char* getenv(const char*);
    static int off = -1;
    cKF_Skeleton_R_c* sk;
    Gfx* g;
    u16 c;
    if (off < 0) off = getenv("PC_GC_HEAD") != NULL;
    if (off || sex < 0 || sex > 1 || face < 0 || face > 7) return;
    if (pc_nlh_hat == -2) pc_nlh_hat_load();
    pc_nlh_hat = pc_nlh_hat_env != NULL ? pc_nlh_hat_env_idx : (hat >= 0 && hat < pc_nl_hat_count ? hat : -1);
    g = pc_nlh_slot[sex];
    gSPDisplayList(g++, sex ? pc_nlh_collar_1 : pc_nlh_collar_0);
    if (pc_nlh_hat >= 0) {
        int shorth = !pc_nl_hat_fullhair[pc_nlh_hat];
        Gfx* hd = pc_cc_head != NULL ? pc_cc_head(sex, face, shorth) : NULL;    /* character creator choice */
        if (hd == NULL) hd = shorth ? pc_nlh_heads_b[sex][face] : pc_nlh_heads_a[sex][face];
        gSPDisplayList(g++, hd);
        gSPMatrix(g++, &pc_nlh_hatmtx[sex], G_MTX_PUSH | G_MTX_MUL | G_MTX_MODELVIEW);
        gSPDisplayList(g++, pc_nl_hat_dl[pc_nlh_hat]);
        gSPPopMatrix(g++, G_MTX_MODELVIEW);
    } else {
        Gfx* hd = pc_cc_head != NULL ? pc_cc_head(sex, face, 0) : NULL;         /* character creator choice */
        if (hd == NULL) hd = pc_nlh_heads_a[sex][face];
        gSPDisplayList(g++, hd);
    }
    gSPEndDisplayList(g++);
    sk = sex ? &cKF_bs_r_grl_1 : &cKF_bs_r_boy_1;
    if (sk->num_joints > 24) sk->joint_table[24].model = pc_nlh_slot[sex];
    if (pal != NULL) {
        c = pal[SKIN_IDX];      /* native order after the PC palette byte swap; RGB5A3 */
        if (c & 0x8000) { gDPSetEnvColor(&pc_nlh_env[0], ((c >> 10) & 31) * 255 / 31, ((c >> 5) & 31) * 255 / 31, (c & 31) * 255 / 31, 255); }
        else { gDPSetEnvColor(&pc_nlh_env[0], ((c >> 8) & 15) * 17, ((c >> 4) & 15) * 17, (c & 15) * 17, 255); }
    }
}
""".replace('SKIN_IDX', str(SKIN_IDX)).split('\n')
    # model-viewer preview: the GC open-eye / closed-mouth frame data of each face type
    face = (ex.ARC/'face_boy.bin').read_bytes()
    for nm_, k in (('eye', 0), ('mouth', 8)):
        out.append(f'static u8 pc_nlh_prev_{nm_}[2][8][256] ATTRIBUTE_ALIGN(32) = {{')
        for sexi in (0, 1):
            out.append('{'+','.join('{'+','.join(map(str, face[(ft+sexi*8)*0xE20+k*0x100:(ft+sexi*8)*0xE20+(k+1)*0x100]))+'}'
                                    for ft in range(8))+'},')
        out.append('};')
    out += ['void* pc_nl_heads_preview_tex(int sex, int face, int mouth) {',
            '    return mouth ? (void*)pc_nlh_prev_mouth[sex & 1][face & 7] : (void*)pc_nlh_prev_eye[sex & 1][face & 7];', '}']
    OUT.write_text('\n'.join(out)+'\n')
    # the heads themselves, a few per compile unit (the 32-bit compiler runs out of memory on one big file)
    hdr = ['/* Generated by generate_nl_heads.py: New Leaf player head models. */', '#include "pc_platform.h"',
           '#include "PR/mbi.h"', '#include "libultra/libultra.h"', '#include "c_keyframe.h"',
           '#include "libforest/gbi_extensions.h"', 'extern Gfx pc_nlh_env[];', '']
    for old in OUT.parent.glob('pc_nl_heads_*.c'): old.unlink()
    per = 4
    files = []
    for k in range(0, len(blocks), per):
        f = OUT.parent/f'pc_nl_heads_{k//per}.c'; files.append(f.name)
        f.write_text('\n'.join(hdr+[l for b in blocks[k:k+per] for l in b])+'\n')
    cm = OUT.parent.parent/'CMakeLists.txt'; t = cm.read_text()
    t = re.sub(r'\n    \$\{CMAKE_CURRENT_SOURCE_DIR\}/src/pc_nl_heads_\d+\.c', '', t)
    t = t.replace('    ${CMAKE_CURRENT_SOURCE_DIR}/src/pc_nl_heads.c\n', '    ${CMAKE_CURRENT_SOURCE_DIR}/src/pc_nl_heads.c\n' +
                  ''.join(f'    ${{CMAKE_CURRENT_SOURCE_DIR}}/src/{n}\n' for n in files))
    cm.write_text(t)

    # ---- face pack: every GC eye/mouth frame -> the New Leaf frame (any palette: the art is skin-free) ----
    if __import__('os').environ.get('PC_HEAD_GEOMETRY_ONLY') == '1': return
    shutil.rmtree(PACK, ignore_errors=True); PACK.mkdir(parents=True)
    face = (ex.ARC/'face_boy.bin').read_bytes(); done = set()
    for sex, sexi, *_ in PLAYERS:
        for ft in range(8):
            iris = iris_colour(sexi, ft)
            for swell in (0, 1):
                nl = f'{sex}{FACE[sex][ft]:02d}{"b" if swell else "a"}'          # New Leaf 'b' faces = bee-stung
                imgs = [eye_image(nl, k, iris) for k in range(8)]+[mouth_image(nl, k) for k in range(6)]
                for decoy in (0, 1):
                    base = (decoy*32+ft+sexi*8+swell*16)*0xE20
                    for k in range(14):
                        dat = face[base+k*0x100:base+(k+1)*0x100]
                        name = f'tex1_32x16_{tb.xxh(dat)}_$_8.dds'
                        if name in done: continue
                        done.add(name)
                        (PACK/name).write_bytes(tb.dds_rgba(imgs[k]))
    print('face pack', len(done))

if __name__ == '__main__':
    main()
