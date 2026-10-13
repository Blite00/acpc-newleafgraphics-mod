"""Inventory icons for the New Leaf hat items (visuals side; the item table lives in generate_nl_hat_items.py).

Each hat is rendered from its 3DS model (hat_source/cap_*) from the front-left and above, supersampled, with every
mesh drawn (untextured parts take their material colour), cropped to the hat and scaled to fill the 32x32 icon,
then given the dark one-pixel outline GC inventory icons have. Texture alpha is only treated as a cut-out when the
material has alpha test on (otherwise it is a gloss mask).

Output: pc_nl_hat_visuals.c: icons (pc_hat_icon_tex / pc_hat_icon_pal), the ground model (obj_item_hatT_*), pc_hat_item_draw and screens/hat_icons_v2.png
"""
import json, sys
from pathlib import Path
import numpy as np
from PIL import Image
from scipy.ndimage import binary_dilation

ROOT = Path(__file__).resolve().parent
SRC = ROOT/'hat_source'
ICONS = ROOT/'icons'
OUT = ROOT/'ACGC-PC-Port/pc/src/pc_nl_hat_visuals.c'  # compiled once listed in pc/CMakeLists.txt (the hats thread owns that line)
SS = 256

def mesh_colour(m):
    c = m['colors']
    k = c['constant0']
    if m['texture'] is None and (k['R'], k['G'], k['B']) != (0, 0, 0): return np.array([k['R'], k['G'], k['B']], float)
    d = c['diffuse']
    return np.array([d['R'], d['G'], d['B']], float)

def wrap(c, mode):
    if mode == 3: c = np.abs(((c+1) % 2)-1)
    elif mode == 2: c = c % 1
    return np.clip(c, 0, 0.9999)

def render(n, yaw=30, pitch=34):
    d = json.load(open(SRC/n/f'{n}.json'))
    tris = []
    for m in d['meshes']:
        if not m.get('visible', True) or m['coordinator']['projection'] != 0: continue
        tex = None
        if m['texture']:
            tp = SRC/n/f"{m['texture']}.png"
            if tp.exists(): tex = np.asarray(Image.open(tp).convert('RGBA')).astype(float)
        # alpha is a cut-out with alpha test on, or when much of the texture is fully clear (blended decals,
        # the halo); otherwise it is a gloss mask
        cut = m['alphaTest']['isTestEnabled'] or (tex is not None and (tex[..., 3] < 16).mean() > 0.15)
        vs = m['vertices']
        for i in range(0, len(vs)-2, 3):
            t = vs[i:i+3]
            # the glowing antennae come in a left/right pair: show one so it reads at icon size
            if n.startswith('cap_glow_') and sum(v['position'][1] for v in t) < 0: continue
            tris.append((m, tex, cut, t))
    P = np.array([v['position'] for *_, t in tris for v in t], float)
    ctr = (P.min(0)+P.max(0))/2
    ya, pa = np.radians(yaw), np.radians(pitch)
    def view(p, c=ctr):
        q = p-c
        up, side, front = q[..., 0], q[..., 1], q[..., 2]
        x = side*np.cos(ya)+front*np.sin(ya); z = -side*np.sin(ya)+front*np.cos(ya)
        y = up*np.cos(pa)-z*np.sin(pa); z2 = up*np.sin(pa)+z*np.cos(pa)
        return np.stack([x, y, z2], -1)
    V = view(P); vc = (V[:, :2].min(0)+V[:, :2].max(0))/2
    ext = np.abs(V[:, :2]-vc).max()*1.02
    light = np.array([-0.45, 0.65, 0.6]); light /= np.linalg.norm(light)
    img = np.zeros((SS, SS, 4)); zb = np.full((SS, SS), -1e9)
    for m, tex, cut, t in tris:
        q = view(np.array([v['position'] for v in t], float))
        sx = ((q[:, 0]-vc[0])/ext*0.5+0.5)*SS; sy = (0.5-(q[:, 1]-vc[1])/ext*0.5)*SS
        x0, x1 = int(max(0, np.floor(sx.min()))), int(min(SS, np.ceil(sx.max())+1))
        y0, y1 = int(max(0, np.floor(sy.min()))), int(min(SS, np.ceil(sy.max())+1))
        if x1 <= x0 or y1 <= y0: continue
        den = (sy[1]-sy[2])*(sx[0]-sx[2])+(sx[2]-sx[1])*(sy[0]-sy[2])
        if abs(den) < 1e-9: continue
        yy, xx = np.mgrid[y0:y1, x0:x1]+0.5
        w0 = ((sy[1]-sy[2])*(xx-sx[2])+(sx[2]-sx[1])*(yy-sy[2]))/den
        w1 = ((sy[2]-sy[0])*(xx-sx[2])+(sx[0]-sx[2])*(yy-sy[2]))/den
        w2 = 1-w0-w1
        ins = (w0 >= 0) & (w1 >= 0) & (w2 >= 0)
        if not ins.any(): continue
        z = w0*q[0, 2]+w1*q[1, 2]+w2*q[2, 2]
        if tex is not None:
            uv = np.array([v['uv'] for v in t], float)
            u = w0*uv[0, 0]+w1*uv[1, 0]+w2*uv[2, 0]; v = w0*uv[0, 1]+w1*uv[1, 1]+w2*uv[2, 1]
            th, tw = tex.shape[:2]
            col = tex[(wrap(1-v, m['mapper']['wrapV'])*th).astype(int) % th, (wrap(u, m['mapper']['wrapU'])*tw).astype(int) % tw]
            rgb, al = col[..., :3], (col[..., 3] if cut else np.full(col.shape[:2], 255.))
        else:
            rgb = np.broadcast_to(mesh_colour(m), ins.shape+(3,)); al = np.full(ins.shape, 255.)
        if 'normal' in t[0]:
            nrm = np.array([v['normal'] for v in t], float)
            nv = view(nrm, 0)
            nn = w0[..., None]*nv[0]+w1[..., None]*nv[1]+w2[..., None]*nv[2]
        else:
            fn = np.cross(q[1]-q[0], q[2]-q[0]); nn = np.broadcast_to(fn, ins.shape+(3,))
        nn = nn/np.maximum(np.linalg.norm(nn, axis=-1, keepdims=True), 1e-9)
        lam = np.clip(0.62+0.5*np.abs(nn @ light)*np.sign(nn @ light+0.3), 0.42, 1.12)
        sub_z = zb[y0:y1, x0:x1]; sub = img[y0:y1, x0:x1]
        ok = ins & (z > sub_z) & (al > 100)
        sub_z[ok] = z[ok]
        sub[ok, :3] = np.clip(rgb[ok]*lam[ok, None], 0, 255); sub[ok, 3] = 255
    return img

def to_icon(img, size=32, margin=2):
    a = img[..., 3] > 0
    ys, xs = np.nonzero(a)
    y0, y1, x0, x1 = ys.min(), ys.max()+1, xs.min(), xs.max()+1
    side = max(y1-y0, x1-x0)
    cy, cx = (y0+y1)/2, (x0+x1)/2
    box = (int(cx-side/2), int(cy-side/2), int(cx-side/2)+side, int(cy-side/2)+side)
    im = Image.fromarray(img.astype(np.uint8), 'RGBA').crop(box)
    inner = size-2*margin
    # premultiplied downsample
    pm = np.asarray(im).astype(float); pm[..., :3] *= pm[..., 3:]/255
    pm = np.asarray(Image.fromarray(pm.astype(np.uint8), 'RGBA').resize((inner, inner), Image.LANCZOS)).astype(float)
    al = pm[..., 3:]
    pm[..., :3] = np.where(al > 0, pm[..., :3]*255/np.maximum(al, 1), 0)
    out = np.zeros((size, size, 4)); out[margin:margin+inner, margin:margin+inner] = pm
    solid = out[..., 3] >= 110
    out[..., 3] = np.where(solid, 255, 0)
    ring = binary_dilation(solid) & ~solid
    out[ring] = (36, 30, 30, 255)
    return Image.fromarray(np.clip(out, 0, 255).astype(np.uint8), 'RGBA')

def to_ci4(im):
    """32x32 RGBA -> (CI4 tiled bytes, 16 native RGB5A3 palette values); index 0 = transparent"""
    a = np.asarray(im.convert('RGBA'))
    rgb = Image.fromarray(np.where(a[..., 3:] > 0, a[..., :3], a[..., :3][a[..., 3] > 0].mean(0)).astype(np.uint8))
    q = rgb.quantize(15, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)
    idx = np.asarray(q).astype(int)+1
    idx[a[..., 3] < 128] = 0
    pal = (q.getpalette()+[0]*45)[:45]
    pal16 = [0x0000]+[0x8000 | ((pal[i*3] >> 3) << 10) | ((pal[i*3+1] >> 3) << 5) | (pal[i*3+2] >> 3) for i in range(15)]
    data = bytearray()
    for ty in range(0, 32, 8):
        for tx in range(0, 32, 8):
            for y in range(8):
                for x in range(0, 8, 2):
                    data.append((idx[ty+y, tx+x] << 4) | idx[ty+y, tx+x+1])
    return bytes(data), pal16

def decode(t, p):
    idx = np.zeros((32, 32), int); o = 0
    for ty in range(0, 32, 8):
        for tx in range(0, 32, 8):
            for y in range(8):
                for x in range(0, 8, 2):
                    b = t[o]; o += 1; idx[ty+y, tx+x] = b >> 4; idx[ty+y, tx+x+1] = b & 15
    cols = np.array([[((v >> 10) & 31)*8, ((v >> 5) & 31)*8, (v & 31)*8, 255 if v & 0x8000 else 0] for v in p], np.uint8)
    return Image.fromarray(cols[idx], 'RGBA')

def hat_names():
    return [l.split('"')[1] for l in (ROOT/'ACGC-PC-Port/pc/src/pc_nl_hats.c').read_text().split('\n')
            if l.strip().startswith('"')]

def main():
    names = hat_names()
    from hat_visuals_models import write_visuals
    write_visuals(OUT, names)            # shelf draw only; icons stay in generate_nl_hat_items.py
    if '--icons' not in sys.argv:        # the icon renderer below is kept for reference / previews only
        print('shelf draw ->', OUT); return
    texs, pals = [], []
    for short in names:
        t, p = to_ci4(to_icon(render('cap_'+short))); texs.append(t); pals.append(p)
    sheet = Image.new('RGBA', (16*36, (len(names)+15)//16*36), (90, 90, 90, 255))
    for i, (t, p) in enumerate(zip(texs, pals)):
        sheet.alpha_composite(decode(t, p), ((i % 16)*36+2, (i//16)*36+2))
    sheet.save(ROOT/'screens/hat_icons_v2.png')
    print(len(names), 'icons ->', OUT)

if __name__ == '__main__':
    main()
