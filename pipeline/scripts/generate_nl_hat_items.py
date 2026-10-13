"""Hat items: names, prices, inventory icons and the dropped-item look for the New Leaf hats.

Item numbers 0x2B10.. (spare indices of the GC "dummy/diary" item category), one per hat in pc_nl_hat_dl order.
- names (16 characters, game character set = ASCII here) and prices
- inventory icon: New Leaf's cap icon (feather icons for the feathers), tinted to the hat's own colour,
  as a 32x32 CI4 icon with a 16-colour palette like every GC inventory icon
- dropped / lost-and-found / hand-over look: the GC flat item card (the diary card's geometry) with the plain cap icon

Output: pc/src/pc_nl_hat_items.c
"""
import json, colorsys
from pathlib import Path
import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parent
SRC = ROOT/'hat_source'
ICONS = ROOT/'icons'
OUT = ROOT/'ACGC-PC-Port/pc/src/pc_nl_hat_items.c'
COL = {'blu': 'blue', 'grn': 'green', 'wht': 'white', 'ylw': 'yellow', 'ppl': 'purple', 'pnk': 'pink', 'blk': 'black',
       'red': 'red', 'org': 'orange', 'ltb': 'light-blue', 'rainbow': 'rainbow'}
NAMES = {
    'actress': "actress's hat", 'baloon': 'balloon hat', 'bandanna': 'bandanna', 'bandanna_tri': 'kerchief',
    'beret': 'beret', 'beret_daikoku': 'lucky beret', 'birthday': 'party hat', 'boater': 'boater',
    'cap_eboshi': 'eboshi', 'cap_group_blue': 'blue team cap', 'cap_group_red': 'red team cap',
    'cap_group_white': 'white team cap', 'cap_group_whiteBlue': 'sports cap', 'cap_hunters': "hunter's cap",
    'cap_jesters': "jester's cap", 'cap_paperboy': 'paperboy cap', 'cap_police': "officer's cap",
    'cap_police_korean': 'patrol cap', 'cap_school': 'school cap', 'cap_star': 'star cap', 'cap_swimming': 'swim cap',
    'cap_wizards': "wizard's cap", 'captain_sky': 'pilot cap', 'cloche': 'cloche', 'crown_queen': "queen's crown",
    'crown_royal': 'royal crown', 'fruit_citrus': 'orange hat', 'fruit_grape': 'grape hat', 'fruit_kiwi': 'kiwi hat',
    'fruit_melon': 'melon hat', 'fruit_strawberry': 'strawberry hat', 'fruit_watermelon': 'watermelon hat',
    'glow_ball': 'glowing ball', 'glow_flower': 'glowing flower', 'glow_heart': 'glowing heart', 'glow_star': 'glowing star',
    'hair_hibiscus': 'hibiscus clip', 'hair_ornament': 'hair ornament', 'hairpin_heart': 'heart hairpin',
    'hairpin_moon': 'moon hairpin', 'hairpin_star': 'star hairpin', 'halo': 'halo', 'hat_Xmas': 'Santa hat',
    'hat_banana': 'banana hat', 'hat_bigbros': 'big bro hat', 'hat_captains': "captain's hat", 'hat_cavalier': 'cavalier hat',
    'hat_chefs': "chef's hat", 'hat_dandy': 'dandy hat', 'hat_detective': 'detective hat', 'hat_dutch': 'Dutch hat',
    'hat_elegant': 'elegant hat', 'hat_explorers': "explorer's hat", 'hat_flamenco': 'flamenco hat', 'hat_grace': 'Gracie hat',
    'hat_grandpa': "grandpa's hat", 'hat_hotdog': 'hot-dog hat', 'hat_lilbros': 'lil bro hat', 'hat_outback': 'outback hat',
    'hat_pirates': "pirate's hat", 'hat_puffy': 'puffy hat', 'hat_sailors': "sailor's hat", 'hat_scholars': "scholar's hat",
    'hat_shamrock': 'shamrock hat', 'hat_silk': 'silk hat', 'hat_straw': 'straw hat', 'hat_top': 'top hat',
    'hat_tulip': 'tulip hat', 'hat_tyrolean': 'Tyrolean hat', 'hat_wario': 'Wario hat', 'hat_witchs': "witch's hat",
    'helmet_bicycle': 'bike helmet', 'helmet_combat': 'combat helmet', 'helmet_npaper': 'paper helmet',
    'helmet_safety': 'safety helmet', 'helmet_viking': 'Viking helmet', 'knit_badge': 'badge knit cap',
    'matador': "matador's hat", 'newyear_cone': 'New Year cone', 'newyear_grn': 'green NY hat',
    'newyear_hat': 'New Year hat', 'newyear_ylw': 'yellow NY hat', 'nonla': 'non la', 'nurse': "nurse's cap",
    'patched': 'patched hat', 'postman': "postman's cap", 'samba': 'samba headdress', 'sandogasa': 'sandogasa',
    'scool_girl': 'school hat', 'showercap': 'shower cap', 'silkhat_small': 'mini silk hat', 'small': 'mini hat',
    'softfelt': 'soft felt hat', 'sombrero': 'sombrero', 'towel': 'towel', 'workcap': 'work cap',
}
FEATHER_ICON = {'red': 432, 'blu': 433, 'grn': 434, 'ylw': 435, 'ppl': 436, 'wht': 437, 'pnk': 438, 'rainbow': 439}

def name_of(n):
    k = n[4:]
    if k in NAMES: return NAMES[k]
    parts = k.split('_')
    if parts[-1] in COL:
        base = {'cap': 'cap', 'feather': 'feather', 'knit': 'knit cap', 'nightcap': 'nightcap', 'ribbon': 'bow'}.get(parts[0], parts[0])
        return f'{COL[parts[-1]]} {base}'
    return k.replace('_', ' ')

def price_of(n):
    k = n[4:]
    if k.startswith(('crown', 'halo')): return 9800
    if k.startswith(('hat_top', 'hat_silk', 'hat_elegant', 'helmet_viking', 'samba')): return 2400
    if k.startswith(('hairpin', 'hair_', 'feather', 'ribbon')): return 560
    if k.startswith(('cap_cap', 'knit', 'bandanna')): return 820
    return 1400

def hat_colour(n):
    """the hat's main colour: saturation-weighted mean of its textures"""
    px = []
    for f in (SRC/n).glob('*.png'):
        a = np.asarray(Image.open(f).convert('RGBA').resize((32, 32))).reshape(-1, 4).astype(float)
        px.append(a[a[:, 3] > 128, :3])
    if not px: return np.array([200, 60, 60.])
    P = np.concatenate(px)/255
    if len(P) < 4: return np.array([200, 60, 60.])
    hsv = np.array([colorsys.rgb_to_hsv(*p) for p in P[::max(1, len(P)//400)]])
    w = hsv[:, 1]*hsv[:, 2]+0.05
    if w.sum() < 1e-6: return P.mean(0)*255
    mean_rgb = (P[::max(1, len(P)//400)]*w[:, None]).sum(0)/w.sum()
    return mean_rgb*255

def tint_icon(icon, colour):
    """recolour the red cap icon: keep its shading (value), take the hat's hue/saturation"""
    a = np.asarray(icon.convert('RGBA')).astype(float)
    h, s, v = colorsys.rgb_to_hsv(*(np.array(colour)/255))
    out = a.copy()
    for y in range(a.shape[0]):
        for x in range(a.shape[1]):
            r, g, b, al = a[y, x]
            if al < 8: continue
            hh, ss, vv = colorsys.rgb_to_hsv(r/255, g/255, b/255)
            if ss > 0.35 and (hh < 0.08 or hh > 0.9):        # the red cloth of the cap
                nv = min(1, vv*(0.55+0.6*v)); ns = s*min(1, ss*1.1)
                out[y, x, :3] = np.array(colorsys.hsv_to_rgb(h, ns, nv))*255
    return Image.fromarray(np.clip(out, 0, 255).astype(np.uint8), 'RGBA')

def render_icon(n, size=128):
    """the hat itself, drawn from the front-left and slightly above with simple lighting and a dark outline, the way
    the game's inventory icons look"""
    d = json.load(open(SRC/n/f'{n}.json'))
    img = np.zeros((size, size, 4)); zb = np.full((size, size), -1e9)
    tris = []
    for m in d['meshes']:
        if m['coordinator']['projection'] != 0: continue
        tp = SRC/n/f"{m['texture']}.png"
        if not tp.exists(): continue
        tex = np.asarray(Image.open(tp).convert('RGBA')).astype(float)
        vs = m['vertices']
        for i in range(0, len(vs), 3):
            tris.append((tex, m['mapper']['wrapU'], m['mapper']['wrapV'], vs[i:i+3]))
    if not tris: return None
    P = np.array([v['position'] for _, _, _, t in tris for v in t], float)
    ctr = (P.min(0)+P.max(0))/2
    # view: head x = up, z = front; yaw 35 deg, pitch 25 deg
    ya, pa = np.radians(30), np.radians(38)
    def view(p):
        q = p-ctr
        up, side, front = q[..., 0], q[..., 1], q[..., 2]
        x = side*np.cos(ya)+front*np.sin(ya); z = -side*np.sin(ya)+front*np.cos(ya)
        y = up*np.cos(pa)-z*np.sin(pa); z2 = up*np.sin(pa)+z*np.cos(pa)
        return np.stack([x, y, z2], -1)
    V = view(P); vc = (V[:, :2].min(0)+V[:, :2].max(0))/2
    ext = np.abs(V[:, :2]-vc).max()*1.15
    light = np.array([-0.4, 0.6, 0.7]); light /= np.linalg.norm(light)
    for tex, wu, wv, t in tris:
        q = view(np.array([v['position'] for v in t], float))
        sx = ((q[:, 0]-vc[0])/ext*0.5+0.5)*size; sy = (0.5-(q[:, 1]-vc[1])/ext*0.5)*size
        uv = np.array([v['uv'] for v in t], float)
        nrm = np.array([v['normal'] for v in t], float)
        nv = view(nrm+ctr); nv = nv/np.maximum(np.linalg.norm(nv, axis=-1, keepdims=True), 1e-9)
        x0, x1 = int(max(0, np.floor(sx.min()))), int(min(size, np.ceil(sx.max())+1))
        y0, y1 = int(max(0, np.floor(sy.min()))), int(min(size, np.ceil(sy.max())+1))
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
        u = w0*uv[0, 0]+w1*uv[1, 0]+w2*uv[2, 0]; v = w0*uv[0, 1]+w1*uv[1, 1]+w2*uv[2, 1]
        def wrap(c, mode):
            if mode == 3: c = np.abs(((c+1) % 2)-1)
            elif mode == 2: c = c % 1
            return np.clip(c, 0, 0.9999)
        th, tw = tex.shape[:2]
        col = tex[(wrap(1-v, wv)*th).astype(int) % th, (wrap(u, wu)*tw).astype(int) % tw]
        nn = w0[..., None]*nv[0]+w1[..., None]*nv[1]+w2[..., None]*nv[2]
        nn /= np.maximum(np.linalg.norm(nn, axis=-1, keepdims=True), 1e-9)
        lam = np.clip(0.55+0.55*(nn @ light), 0.35, 1.15)
        sub_z = zb[y0:y1, x0:x1]; sub = img[y0:y1, x0:x1]
        ok = ins & (z > sub_z) & (col[..., 3] > 100)
        sub_z[ok] = z[ok]
        sub[ok, :3] = np.clip(col[ok, :3]*lam[ok, None], 0, 255); sub[ok, 3] = 255
    if (img[..., 3] > 0).sum() < 20: return None
    from scipy.ndimage import binary_dilation
    a = img[..., 3] > 0
    ring = binary_dilation(a, iterations=3) & ~a
    img[ring, :3] = 40; img[ring, 3] = 255
    return Image.fromarray(img.astype(np.uint8), 'RGBA')

def to_ci4(im):
    """32x32 RGBA -> (CI4 tiled bytes, 16 native RGB5A3 palette values); index 0 = transparent"""
    im = im.convert('RGBA').resize((32, 32), Image.LANCZOS)
    a = np.asarray(im)
    rgb = Image.fromarray(a[..., :3]).quantize(15, method=Image.Quantize.MEDIANCUT)
    idx = np.asarray(rgb).astype(int)+1
    idx[a[..., 3] < 128] = 0
    pal = rgb.getpalette()[:45]
    pal16 = [0x0000]+[0x8000 | ((pal[i*3] >> 3) << 10) | ((pal[i*3+1] >> 3) << 5) | (pal[i*3+2] >> 3) for i in range(15)]
    data = bytearray()
    for ty in range(0, 32, 8):
        for tx in range(0, 32, 8):
            for y in range(8):
                for x in range(0, 8, 2):
                    data.append((idx[ty+y, tx+x] << 4) | idx[ty+y, tx+x+1])
    return bytes(data), pal16

def main():
    names = [l.split('"')[1] for l in (ROOT/'ACGC-PC-Port/pc/src/pc_nl_hats.c').read_text().split('\n')
             if l.strip().startswith('"')]
    cap = Image.open(ICONS/'icn_314.png').convert('RGBA')
    out = ['/* Generated by generate_nl_hat_items.py: New Leaf hats as items (names, prices, icons, dropped look). */',
           '#include "pc_platform.h"', '#include "PR/mbi.h"', '#include "libultra/libultra.h"',
           '#include "libforest/gbi_extensions.h"', '']
    pals = []; texs = []; nm = []; pr = []
    for i, short in enumerate(names):
        n = 'cap_'+short
        parts = short.split('_')
        if parts[0] == 'feather' and parts[-1] in FEATHER_ICON:
            icon = Image.open(ICONS/f'icn_{FEATHER_ICON[parts[-1]]}.png')
        else:
            icon = tint_icon(cap, hat_colour(n))         # New Leaf's own (flat) cap icon in the hat's colour
        t, p = to_ci4(icon); texs.append(t); pals.append(p)
        nm.append(name_of(n)[:16]); pr.append(price_of(n))
    out.append(f'int pc_hat_item_count = {len(names)};')
    out.append('u16 pc_hat_icon_pal[][16] ATTRIBUTE_ALIGN(32) = {')
    out += ['    {'+','.join(f'0x{v:04X}' for v in p)+'},' for p in pals]; out.append('};')
    out.append('u8 pc_hat_icon_tex[][512] ATTRIBUTE_ALIGN(32) = {')
    out += ['    {'+','.join(map(str, t))+'},' for t in texs]; out.append('};')
    out.append('const char pc_hat_item_name[][17] = {')
    out += ['    "'+s.replace('"', '')+'",' for s in nm]; out.append('};')
    out.append('const unsigned short pc_hat_item_price[] = {'+', '.join(map(str, pr))+'};')
    # dropped look: the plain New Leaf cap icon on the GC flat item card
    t, p = to_ci4(cap)
    out.append('static u16 pc_hat_drop_pal[16] ATTRIBUTE_ALIGN(32) = {'+','.join(f'0x{v:04X}' for v in p)+'};')
    out.append('static u8 pc_hat_drop_tex[512] ATTRIBUTE_ALIGN(32) = {'+','.join(map(str, t))+'};')
    out += ['Gfx obj_item_hatT_mat_model[] = {',
            '    gsSPTexture(0, 0, 0, G_TX_RENDERTILE, G_ON),',
            '    gsDPSetRenderMode(G_RM_FOG_SHADE_A, G_RM_AA_ZB_TEX_EDGE2),',
            '    gsDPSetCombineLERP(TEXEL0, 0, SHADE, 0, 0, 0, 0, TEXEL0, PRIMITIVE, 0, COMBINED, 0, 0, 0, 0, COMBINED),',
            '    gsDPLoadTLUT_Dolphin(15, 16, 1, pc_hat_drop_pal),',
            '    gsDPSetTextureImage_Dolphin(G_IM_FMT_CI, G_IM_SIZ_4b, 32, 32, pc_hat_drop_tex),',
            '    gsDPSetTile_Dolphin(G_DOLPHIN_TLUT_DEFAULT_MODE, 0, 15, GX_CLAMP, GX_CLAMP, 0, 0),',
            '    gsDPSetPrimColor(0, 128, 255, 255, 255, 255),',
            '    gsSPLoadGeometryMode(G_ZBUFFER | G_SHADE | G_CULL_BACK | G_FOG | G_LIGHTING | G_SHADING_SMOOTH | G_DECAL_LEQUAL),',
            '    gsSPEndDisplayList(),', '};',
            'extern Gfx obj_item_diaryT_gfx_model[];',
            'Gfx obj_item_hatT_gfx_model[] = { gsSPDisplayList(obj_item_diaryT_gfx_model), gsSPEndDisplayList() };']
    OUT.write_text('\n'.join(out)+'\n')
    sheet = Image.new('RGBA', (16*36, (len(names)+15)//16*36), (90, 90, 90, 255))
    for i, (t, p) in enumerate(zip(texs, pals)):
        idx = np.zeros((32, 32), int); o = 0
        for ty in range(0, 32, 8):
            for tx in range(0, 32, 8):
                for y in range(8):
                    for x in range(0, 8, 2):
                        b = t[o]; o += 1; idx[ty+y, tx+x] = b >> 4; idx[ty+y, tx+x+1] = b & 15
        cols = np.array([[((v >> 10) & 31)*8, ((v >> 5) & 31)*8, (v & 31)*8, 255 if v & 0x8000 else 0] for v in p], np.uint8)
        sheet.alpha_composite(Image.fromarray(cols[idx], 'RGBA'), ((i % 16)*36, (i//16)*36))
    sheet.save(ROOT/'screens/hat_icons.png')
    print(len(names), 'hat items;', nm[:6])

if __name__ == '__main__':
    main()
