"""Town map (m_map_ovl) re-textured the New Leaf way, as approved in nl_map_mock2.png (mapmock2.py).

Every GameCube acre picture (kan_tizu_*_TA_tex_txt, CI4 32x32, 22x22 used, + kan_tizu1/2 palette) keeps its shapes,
cliffs and icons; grass / water / sand palette indices are replaced by NL grass (grd_F_0), NL water (grd_Oe_0) and NL
sand colour, with smoothed class masks, NL's brown outline where grass meets water/sand, and the GC acre grid line
(row 0 / column 0) dropped. Bridge acres get NL's bridge plank (tc_mpi_B_00 cell 0,0) over the GC bridge marker.

One RGBA texture (CELL x CELL) per distinct texture+palette pair is written to pc_nl_ui_map_data.c, plus a lookup
table {GC texture, palette, NL texture} used by pc_nl_ui_map.c.

Usage: python gen_nlui_map.py [pc_root]   (default: the map helper's root)
"""
import os, re, sys
import numpy as np
from PIL import Image, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import nlui_gen_common as C

PC_ROOT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'ACGC-PC-Port', 'pc')
MAP_SRC = os.path.join(os.path.dirname(PC_ROOT.rstrip('/\\')), 'src', 'game', 'm_map_ovl.c')
C.use_scratch()
import gcwin

CELL = 64                    # texels per acre (acre is 22x22 GC pixels on screen)
NLT = 'out/Menu/map_village/timg/grd_%s.png'
GRASS = {0: {1, 2, 8, 10, 12}, 1: {1, 2, 10}}
WATER = {0: {11, 14, 15}, 1: {13, 14, 15}}
SAND = {0: set(), 1: {4, 8}}
WHITE = {0: 13, 1: 11}       # GC bridge marker colour
NL_EDGE = (115, 75, 30)

SRC = open(MAP_SRC).read()
TEX = re.findall(r'kan_tizu_(\w+?)_TA_tex_txt, // mFM_BLOCK_TYPE_(\w+)', SRC.split('l_map_texture[')[1].split('};')[0])
PALSEL = [int(x) for x in re.findall(r'\s(\d), // mFM_BLOCK_TYPE_', SRC.split('l_map_pal[mFM_BLOCK_TYPE_NUM]')[1].split('};')[0])]
assert len(TEX) == len(PALSEL), (len(TEX), len(PALSEL))
PALS = []
for name in ('kan_tizu1_pal', 'kan_tizu2_pal'):
    vals = re.search(name + r'\[16\][^{]*\{(.*?)\}', SRC, re.S).group(1)
    PALS.append([gcwin.rgb5a3(int(v, 16)) for v in re.findall(r'0x([0-9a-fA-F]+)', vals)])


def indices(tex):
    raw = gcwin.data('kan_tizu_%s_TA_tex_txt' % tex)
    idx = np.zeros((32, 32), int); i = 0
    for by in range(0, 32, 8):
        for bx in range(0, 32, 8):
            blk = raw[i:i + 32]; i += 32
            for y in range(8):
                for x in range(8):
                    b = blk[(y * 8 + x) // 2]; idx[by + y, bx + x] = (b >> 4) if x % 2 == 0 else (b & 15)
    return idx[:22, :22]


def tiled(path):
    t = Image.open(path).convert('RGBA')
    if t.size != (CELL, CELL): t = t.resize((CELL, CELL), Image.NEAREST)
    return np.asarray(t, float)


def sand_colour():
    px = np.asarray(Image.open(NLT % 'Ms_0').convert('RGB')).reshape(-1, 3)
    sandy = px[(px[:, 0] > 200) & (px[:, 1] > 190) & (px[:, 2] < 190)]
    return tuple(int(c) for c in np.median(sandy, 0))


def smooth(mask):
    m = Image.fromarray((mask * 255).astype(np.uint8)).resize((CELL, CELL), Image.BILINEAR).filter(ImageFilter.GaussianBlur(0.8))
    return np.asarray(m, float) / 255 > 0.5


GRASS_T, WATER_T = tiled(NLT % 'F_0'), tiled(NLT % 'Oe_0')
SAND_C = sand_colour()
ATLAS_B = Image.open('out/Menu/map_village/timg/tc_mpi_B_00.png').convert('RGBA')
PLANK = ATLAS_B.crop((0, 0, 16, 16))


def render(tex, pal, bridge_base=None):
    full = indices(tex)
    idx = full[1:22, 1:22]                         # drop GC's acre grid line
    pal_rgba = np.array(PALS[pal], float)
    out = pal_rgba[idx]
    out = np.asarray(Image.fromarray(out.astype(np.uint8)).resize((CELL, CELL), Image.NEAREST), float).copy()
    cls = {}
    for k, table in (('g', GRASS), ('w', WATER), ('s', SAND)):
        cls[k] = smooth(np.isin(idx, list(table[pal])).astype(float))
    out[cls['g']] = GRASS_T[cls['g']]
    out[cls['w']] = WATER_T[cls['w']]
    out[cls['s']] = SAND_C + (255,)
    # brown outline where grass meets water or sand (grass mask extended past the acre edge by replication)
    pad = 3
    g = np.pad(cls['g'], pad, mode='edge')
    near = np.asarray(Image.fromarray((g * 255).astype(np.uint8)).filter(ImageFilter.MaxFilter(5)), bool)[pad:-pad, pad:-pad]
    near &= ~cls['g'] & (cls['w'] | cls['s'])
    out[near] = NL_EDGE + (255,)
    out[..., 3] = 255
    img = Image.fromarray(out.astype(np.uint8))
    if bridge_base is not None:
        base = indices(bridge_base)[1:22, 1:22]
        w = WHITE[pal]
        white = np.argwhere((idx == w) & (base != w))
        if len(white):
            (y0, x0), (y1, x1) = white.min(0), white.max(0)
            plank = PLANK if (x1 - x0) >= (y1 - y0) else PLANK.transpose(Image.ROTATE_90)
            plank = plank.resize((CELL // 2, CELL // 2), Image.NEAREST)
            cy, cx = (white.mean(0) + 0.5) / 21 * CELL
            img.alpha_composite(plank, (int(round(cx - plank.width / 2)), int(round(cy - plank.height / 2))))
    return img


def main():
    combos = {}   # (tex, pal) -> [type names]
    for (tex, t), pal in zip(TEX, PALSEL):
        combos.setdefault((tex, pal), []).append(t)
    m = C.Module('pc_nl_ui_map')
    table = []
    for (tex, pal), types in sorted(combos.items()):
        bridge_base = None
        if any('BRIDGE' in t for t in types) and tex.endswith('b'):
            bridge_base = tex[:-1]
        sym = 'nlui_map_%s_p%d' % (tex, pal)
        m.add_rgba(sym, render(tex, pal, bridge_base))
        table.append((tex, pal, sym))
        print('%-8s pal%d  %s' % (tex, pal, ' '.join(types)))
    m.define('NLUI_MAP_CELL', CELL)
    m.define('NLUI_MAP_COUNT', len(table))
    m.write(PC_ROOT)
    # lookup table, appended to the generated .c
    cpath = os.path.join(PC_ROOT, 'src', 'pc_nl_ui_map_data.c')
    with open(cpath, 'a') as f:
        f.write('/* GameCube acre texture + palette -> re-textured New Leaf acre */\n')
        for tex in sorted(set(t for t, _, _ in table)):
            f.write('extern u8 kan_tizu_%s_TA_tex_txt[];\n' % tex)
        f.write('\nstruct nlui_map_entry { u8* gc_tex; int pal; u8* nl_tex; };\n')
        f.write('const struct nlui_map_entry pc_nl_ui_map_table[%d] = {\n' % len(table))
        for tex, pal, sym in table:
            f.write('    { kan_tizu_%s_TA_tex_txt, %d, %s_tex },\n' % (tex, pal, sym))
        f.write('};\n')
    # preview sheet of every acre
    cols = 10
    rows = (len(table) + cols - 1) // cols
    sheet = Image.new('RGBA', (cols * (CELL + 4), rows * (CELL + 4)), (40, 40, 40, 255))
    for i, (tex, pal, sym) in enumerate(table):
        sheet.paste(Image.open(os.path.join(C.PREVIEW, sym + '.png')), ((i % cols) * (CELL + 4), (i // cols) * (CELL + 4)))
    sheet.save(os.path.join(C.PREVIEW, 'nlui_map_sheet.png'))


if __name__ == '__main__':
    main()
