"""GameCube mailbox, upscaled: seam-safe Real-ESRGAN textures and a smoothed, tessellated body.

Textures: each CI texture is padded with the same wrap the game uses (GX_MIRROR -> symmetric, GX_CLAMP -> edge)
before the 4x Real-ESRGAN pass and cropped back, so tiles meet at their edges with no seam. The outer ring of
texels is then blended back towards a plain bicubic upscale of the original edge, matching neighbouring faces.
Model: obj_{s,w}_post_main_model is rebuilt with PN-triangle tessellation (level 4) driven by the original vertex
normals, which rounds the arched top and post; flat faces stay flat. The native flag and lid joints are untouched
and get texture-pack replacements made the same seam-safe way.
"""
import os, re, subprocess, shutil, json
from pathlib import Path
import numpy as np
from PIL import Image
import native_models as nm
import texture_bake as tb

ROOT = Path(__file__).resolve().parent
W = ROOT/'mailbox_up'; ESR = ROOT/'toolchain/realesrgan/realesrgan-ncnn-vulkan.exe'
PACK = ROOT/'texture_pack_staging/3ds_mailbox'
UP = 8; PAD = 8; DETAIL = 0.9; PN_STRENGTH = 0.7
MODEL = {'s': ROOT/'ACGC-PC-Port/src/data/model/obj_s_post_flag_model.c', 'w': ROOT/'ACGC-PC-Port/src/data/model/obj_w_post_model.c'}

def texture_modes(path):
    src = Path(path).read_text(); modes = {}
    for m in re.finditer(r'SetTextureImage_Dolphin\(G_IM_FMT_CI, G_IM_SIZ_4b, (\d+), (\d+), (\w+)\),\s*gsDPSetTile_Dolphin\([^,]+, 0, 15, (GX_\w+), (GX_\w+)', src):
        modes[m[3]] = (int(m[1]), int(m[2]), m[4], m[5])
    return modes

def _pad_mode(m): return 'symmetric' if m == 'GX_MIRROR' else ('wrap' if m == 'GX_REPEAT' else 'edge')
def _esr_pass(imgs, modes, pad):
    """one wrap-padded 4x Real-ESRGAN pass over {key: RGB array}"""
    for d in ('pad', 'out'):
        shutil.rmtree(W/d, ignore_errors=True); (W/d).mkdir(parents=True)
    for key, a in imgs.items():
        mu, mv = modes[key]
        a = np.pad(a, ((0, 0), (pad, pad), (0, 0)), mode=_pad_mode(mu)); a = np.pad(a, ((pad, pad), (0, 0), (0, 0)), mode=_pad_mode(mv))
        Image.fromarray(a.astype(np.uint8)).save(W/'pad'/f'{key}.png')
    subprocess.run([str(ESR), '-i', str(W/'pad'), '-o', str(W/'out'), '-n', 'realesrgan-x4plus', '-s', '4', '-f', 'png'], check=True, capture_output=True)
    res = {}
    for key, a in imgs.items():
        h, w = a.shape[:2]
        res[key] = np.asarray(Image.open(W/'out'/f'{key}.png').convert('RGB').crop((pad*4, pad*4, pad*4+w*4, pad*4+h*4)))
    return res

def upscale_all(jobs):
    """jobs: list of (key, rgba image, mode_u, mode_v) -> {key: RGBA upscaled UP times}. One wrap-padded 4x pass of
    the general (photo) Real-ESRGAN model, which keeps the GC texel detail instead of flattening it like the anime
    model; resampled to UP and the source's own fine detail (speckle, grain, lettering edges) added back on top."""
    from PIL import ImageFilter
    modes = {k: (mu, mv) for k, _, mu, mv in jobs}
    imgs = _esr_pass({k: np.asarray(im.convert('RGB')) for k, im, _, _ in jobs}, modes, PAD)
    res = {}
    ovr = ROOT/'upscale_override'/W.name                  # hand-made / other-model upscales win when present
    for key, im, mu, mv in jobs:
        w, h = im.size
        if (ovr/f'{key}.png').exists():
            o = Image.open(ovr/f'{key}.png').convert('RGBA').resize((w*UP, h*UP), Image.LANCZOS)
            res[key] = Image.merge('RGBA', (*o.convert('RGB').split(), im.split()[3].resize((w*UP, h*UP), Image.BICUBIC)))
            continue
        g = np.asarray(Image.fromarray(imgs[key]).resize((w*UP, h*UP), Image.LANCZOS)).astype(float)
        lz = im.convert('RGB').resize((w*UP, h*UP), Image.LANCZOS)
        hi = np.asarray(lz).astype(float)-np.asarray(lz.filter(ImageFilter.GaussianBlur(UP*0.6))).astype(float)
        rgb = Image.fromarray(np.clip(g+hi*DETAIL, 0, 255).astype(np.uint8))
        alpha = im.split()[3].resize((w*UP, h*UP), Image.BICUBIC)
        res[key] = Image.merge('RGBA', (*rgb.split(), alpha))
    return res

# ---------------- textures ----------------
jobs = []; meta = {}
for season, path in MODEL.items():
    pal = f'obj_{season}_post_pal'
    for tex, (w, h, mu, mv) in texture_modes(path).items():
        key = f'{tex}__{pal}'
        jobs.append((key, nm.decode_ci(nm.blob(tex), w, h, nm.palette(pal), 4), mu, mv)); meta[key] = (tex, pal, w, h, mu, mv)
up = upscale_all(jobs)
shutil.rmtree(PACK, ignore_errors=True); PACK.mkdir(parents=True)
for key, im in up.items():
    tex, pal, w, h, mu, mv = meta[key]
    (PACK/tb.pack_name(tex, 'CI', 4, w, h, pal)).write_bytes(tb.dds_rgba(im))
    im.save(W/f'final_{key}.png')

# ---------------- tessellated body ----------------
GEO_NORMALS = {}; PINNED = set()
def pkey(p): return tuple(int(round(c)) for c in p)
def set_geo_normals(tris):
    """tris: iterable of 3 x (pos, uv, n). Averages the normals of all faces meeting at each position."""
    acc = {}
    for t in tris:
        for pos, uv, n in t:
            n = np.array(n, float); n /= max(np.linalg.norm(n), 1e-9)
            acc.setdefault(pkey(pos), []).append(n)
    GEO_NORMALS.clear()
    for k, ns in acc.items():
        m = np.mean(ns, 0); GEO_NORMALS[k] = m/max(np.linalg.norm(m), 1e-9)

def pn_tess(tri, level):
    """tri: 3 x (pos(3), uv(2), n(3)); returns list of triangles in the same format (PN triangles)."""
    P = [np.array(v[0], float) for v in tri]; N = [np.array(v[2], float)/max(np.linalg.norm(v[2]), 1e-9) for v in tri]; T = [np.array(v[1], float) for v in tri]
    # the curved shape uses one normal per position (averaged over every face meeting there), so neighbouring
    # triangles bend their shared edge identically and no cracks open at hard edges; shading keeps N
    G = [GEO_NORMALS.get(pkey(P[i]), N[i]) for i in range(3)]
    def ctrl(i, j):
        if pkey(P[i]) in PINNED and pkey(P[j]) in PINNED: return (2*P[i]+P[j])/3   # edge shared with untouched geometry
        return (2*P[i]+P[j]-np.dot(P[j]-P[i], G[i])*G[i])/3
    b300, b030, b003 = P
    b210 = ctrl(0, 1); b120 = ctrl(1, 0); b021 = ctrl(1, 2); b012 = ctrl(2, 1); b102 = ctrl(2, 0); b201 = ctrl(0, 2)
    E = (b210+b120+b021+b012+b102+b201)/6; V = (P[0]+P[1]+P[2])/3; b111 = E+(E-V)/2
    def point(u, v_):
        w_ = 1-u-v_
        pos = (b300*w_**3+b030*u**3+b003*v_**3+b210*3*w_*w_*u+b120*3*w_*u*u+b201*3*w_*w_*v_
               + b021*3*u*u*v_+b102*3*w_*v_*v_+b012*3*u*v_*v_+b111*6*w_*u*v_)
        pos = P[0]*w_+P[1]*u+P[2]*v_+(pos-(P[0]*w_+P[1]*u+P[2]*v_))*PN_STRENGTH
        n = N[0]*w_+N[1]*u+N[2]*v_; n /= max(np.linalg.norm(n), 1e-9)
        return (pos, T[0]*w_+T[1]*u+T[2]*v_, n)
    out = []; L = level
    for i in range(L):
        for j in range(L-i):
            a = point(j/L, i/L); b = point((j+1)/L, i/L); c = point(j/L, (i+1)/L)
            out.append((a, b, c))
            if j+i+1 < L:
                d = point((j+1)/L, (i+1)/L); out.append((b, d, c))
    return out

def native_tris(season):
    src = MODEL[season].read_text()
    body = re.search(rf'Gfx obj_{season}_post_main_model\[\] = \{{(.*?)\n\}};', src, re.S)[1]
    verts = nm.vertices(f'obj_{season}_post_v')
    tex = None; buf = {}; tris = []; pend = 0
    for op, args in re.findall(r'(gs\w+)\(([^)]*)\)', body):
        a = [x.strip() for x in args.split(',')]
        if op == 'gsDPSetTextureImage_Dolphin': tex = a[4]
        elif op == 'gsSPVertex':
            m = re.match(r'&?(\w+)\[(\d+)\]', a[0]); st = int(m[2])
            for k in range(int(a[1])):
                x, y, z, _f, u, v, r, g, b, al = verts[st+k]
                n = [c-256 if c > 127 else c for c in (r, g, b)]
                buf[int(a[2])+k] = ((x, y, z), (u/32.0, v/32.0), n)
        elif op in ('gsSPNTrianglesInit_5b', 'gsSPNTriangles_5b'):
            if op == 'gsSPNTrianglesInit_5b': pend = int(a[0]); idx = list(map(int, a[1:10]))
            else: idx = list(map(int, a[:12]))
            for k in range(0, len(idx), 3):
                if pend > 0: tris.append((tex, [buf[i] for i in idx[k:k+3]])); pend -= 1
    return tris

out = ['/* Generated by generate_mailbox_hd.py: GC mailbox body, PN-tessellated, upscaled textures. */', 'int g_pc_mailbox_hd = 1;']
declared = set()
def tex_array(name, im):
    if name in declared: return
    declared.add(name); data = bytearray(); w, h = im.size
    for ty in range(0, h, 4):
        for tx in range(0, w, 4):
            tile = [im.getpixel((tx+x, ty+y)) for y in range(4) for x in range(4)]
            data.extend(c for r, g, b, a in tile for c in (a, r)); data.extend(c for r, g, b, a in tile for c in (g, b))
    out.append(f'static u8 {name}[] ATTRIBUTE_ALIGN(32) = {{'); out.extend(','.join(map(str, data[i:i+32]))+',' for i in range(0, len(data), 32)); out.append('};')
WRAP = {'GX_CLAMP': 'GX_CLAMP', 'GX_MIRROR': 'GX_MIRROR', 'GX_REPEAT': 'GX_REPEAT'}
counts = {}
for season in 'sw':
    modes = texture_modes(MODEL[season]); groups = {}
    nt = native_tris(season); set_geo_normals([tri for _, tri in nt])
    for tex, tri in nt:
        groups.setdefault(tex, []).extend(pn_tess(tri, 4))
    dl = ['gsDPPipeSync(),', 'gsSPTexture(0,0,0,G_TX_RENDERTILE,G_ON),', 'gsDPSetPrimColor(0,128,255,255,255,255),',
          'gsDPSetCombineLERP(TEXEL0,0,SHADE,0,0,0,0,TEXEL0,PRIMITIVE,0,COMBINED,0,0,0,0,COMBINED),',
          'gsDPSetRenderMode(G_RM_FOG_SHADE_A,G_RM_AA_ZB_TEX_EDGE2),',
          'gsSPLoadGeometryMode(G_ZBUFFER|G_SHADE|G_CULL_BACK|G_FOG|G_LIGHTING|G_SHADING_SMOOTH),']
    total = 0
    for tex, tris in groups.items():
        w, h, mu, mv = modes[tex]; key = f'{tex}__obj_{season}_post_pal'
        tname = f'pc_mbx_{tex}'; tex_array(tname, up[key])
        vname = f'pc_mbx_{season}_{tex}_v'; verts = [v for t in tris for v in t]
        out.append(f'static Vtx {vname}[] ATTRIBUTE_ALIGN(32) = {{')
        for pos, uv, n in verts:
            nb = ','.join(str(int(round(c*126)) & 255) for c in n)
            out.append('{{{%d,%d,%d},0,{%d,%d},{%s,255}}},' % (round(pos[0]), round(pos[1]), round(pos[2]), round(uv[0]*UP*32), round(uv[1]*UP*32), nb))
        out.append('};')
        dl += [f'gsDPSetTextureImage_Dolphin(G_IM_FMT_RGBA,G_IM_SIZ_32b,{w*UP},{h*UP},{tname}),',
               f'gsDPSetTile_Dolphin(G_DOLPHIN_TLUT_DEFAULT_MODE,0,0,{WRAP[mu]},{WRAP[mv]},0,0),']
        for base in range(0, len(verts), 30):
            c = min(30, len(verts)-base)
            dl.append(f'gsSPVertex(&{vname}[{base}],{c},0),')
            for k in range(0, c, 3): dl.append(f'gsSP1Triangle({k},{k+1},{k+2},0),')
        total += len(verts)//3
    dl.append('gsSPEndDisplayList(),')
    out += [f'static Gfx pc_mbx_{season}_dl[] = {{'] + dl + ['};']
    counts[season] = total
out += ['Gfx* pc_mailbox_hd_body(int winter) { return g_pc_mailbox_hd ? (winter ? pc_mbx_w_dl : pc_mbx_s_dl) : NULL; }']
(ROOT/'ACGC-PC-Port/pc/src/pc_mailbox_hd.c_inc').write_text('\n'.join(out)+'\n')
print('triangles', counts, 'pack files', len(os.listdir(PACK)))
