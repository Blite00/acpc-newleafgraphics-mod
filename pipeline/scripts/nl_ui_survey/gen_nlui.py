"""Generate pc_nl_ui_data.c: New Leaf UI art pre-rendered from the 3DS layouts, as GameCube-format textures.

Run from the scratchpad that holds the unpacked layouts (out/), lyt.py, exact.py and font.py.
Usage: python gen_nlui.py <scratch_dir> <output .c path>
"""
import os as _os
_ROOT = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
if _os.path.basename(_ROOT) == 'nl_ui_survey': _ROOT = _os.path.dirname(_ROOT)
os = _os

import os, sys
import numpy as np
from PIL import Image

SCRATCH, OUT = sys.argv[1], sys.argv[2]
os.chdir(SCRATCH); sys.path.insert(0, SCRATCH)
import lyt  # noqa: E402

PX = 3                      # texels per GameCube screen pixel
textures = []               # (name, fmt, w, h, bytes)
defines = []


def rgba32(img):
    """GX RGBA8: 4x4 tiles, 32 bytes of A,R then 32 bytes of G,B."""
    a = np.asarray(img.convert('RGBA'), np.uint8)
    h, w = a.shape[:2]
    H, W = (h + 3) // 4 * 4, (w + 3) // 4 * 4
    p = np.zeros((H, W, 4), np.uint8); p[:h, :w] = a
    out = bytearray()
    for ty in range(0, H, 4):
        for tx in range(0, W, 4):
            blk = p[ty:ty + 4, tx:tx + 4].reshape(16, 4)
            ar = np.stack([blk[:, 3], blk[:, 0]], 1).reshape(-1)
            gb = np.stack([blk[:, 1], blk[:, 2]], 1).reshape(-1)
            out += ar.tobytes() + gb.tobytes()
    return W, H, bytes(out)


def ia8(lum, alpha):
    """GX IA8 (16-bit): 4x4 tiles, each texel A then I."""
    h, w = lum.shape
    H, W = (h + 3) // 4 * 4, (w + 3) // 4 * 4
    L = np.zeros((H, W), np.uint8); A = np.zeros((H, W), np.uint8)
    L[:h, :w] = lum; A[:h, :w] = alpha
    out = bytearray()
    for ty in range(0, H, 4):
        for tx in range(0, W, 4):
            out += np.stack([A[ty:ty + 4, tx:tx + 4].reshape(-1), L[ty:ty + 4, tx:tx + 4].reshape(-1)], 1).reshape(-1).tobytes()
    return W, H, bytes(out)


PREVIEW = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'nlui_preview')


def preview(name, img):
    os.makedirs(PREVIEW, exist_ok=True); img.save(os.path.join(PREVIEW, name + '.png'))


def add_rgba(name, img):
    preview(name, img)
    W, H, data = rgba32(img)
    textures.append((name, 'RGBA32', W, H, data, img.size))


def add_ia(name, lum, alpha, size):
    W, H, data = ia8(lum, alpha)
    textures.append((name, 'IA16', W, H, data, size))


def center_pane(L, name):
    def f(p):
        if p['name'] == name: p['t'] = (0.0, 0.0, 0.0)
        for k in p['kids']: f(k)
    f(L.root)


def render(path, scale, hide=(), show=(), ao=None, mats=None):
    L = lyt.Layout(path)
    if 'msg_win' in path:
        center_pane(L, 'N_win_msg_00')   # NL lets the box run off the bottom of the 3DS screen
        L.size = (440.0, 240.0)          # and its side bumps poke past the 400-wide canvas
    if mats: mats(L)
    r = lyt.R(L, scale, hide=hide, show=show, alpha_over=ao or {}); r.draw(L.root)
    return L, r


# ---------------- dialogue window ----------------
MSG_SCALE = 0.68           # NL units -> GC pixels
k = MSG_SCALE * PX
L, r = render('out/msgWin/msg_win/blyt/msg_win.bclyt', k,
              hide=('N_hard', 'N_win_nam_00', 'N_pageicn_00', 'N_text'))
img = r.rgba()
# crop around the window: NL x -210..210, y (-73) -72..72 relative to N_win_msg_00
cx, cy = r.to_screen(r.boxes['N_win_msg_00'][0], 0, 0)
hw, hh = 214 * k, 74 * k
box = img.crop((int(cx - hw), int(cy - hh), int(cx + hw), int(cy + hh)))
# the two mirrored body halves meet in the middle; blend away the 1-2 texel seam
b = np.asarray(box).astype(float); m = box.width // 2
for c in range(m - 2, m + 3):
    b[:, c] = (b[:, m - 4] + b[:, m + 4]) / 2
box = Image.fromarray(b.astype(np.uint8))
add_rgba('nlui_msg_box', box)
defines += ['#define NLUI_MSG_BOX_W_PX %.2ff' % (box.width / PX), '#define NLUI_MSG_BOX_H_PX %.2ff' % (box.height / PX)]

# name plate: luminance pattern + alpha; tinted at run time with lerp(env=plate colour, prim=cream)
L, r = render('out/msgWin/msg_win/blyt/msg_win.bclyt', k, hide=('N_hard', 'P_bg_L_00', 'P_soft_L', 'P_soft_R', 'P_soft_T', 'P_soft_B', 'N_text', 'N_pageicn_00', 'P_nam_01', 'T_nam_00'),
              show=('N_win_nam_00',), mats=lambda L: [m.update(black=np.array([0, 0, 0, 0.]), white=np.array([1, 1, 1, 1.])) for m in L.mats if m['name'] == 'P_nam_00'])
img = r.rgba(); bb = img.getbbox(); assert bb, 'plate rendered empty'; plate = img.crop(bb)
a = np.asarray(plate)
add_ia('nlui_msg_plate', a[..., :3].mean(-1).astype(np.uint8), a[..., 3], plate.size)
defines += ['#define NLUI_MSG_PLATE_W_PX %.2ff' % (plate.width / PX), '#define NLUI_MSG_PLATE_H_PX %.2ff' % (plate.height / PX)]

# next-page arrow (with its shadow), NL colour b97300
L, r = render('out/msgWin/msg_win/blyt/msg_win.bclyt', k, hide=('N_hard', 'N_soft', 'N_text', 'N_win_nam_00'))
img = r.rgba(); assert img.getbbox(); arrow = img.crop(img.getbbox())
add_rgba('nlui_msg_arrow', arrow)
defines += ['#define NLUI_MSG_ARROW_W_PX %.2ff' % (arrow.width / PX), '#define NLUI_MSG_ARROW_H_PX %.2ff' % (arrow.height / PX)]


# ---------------- choice window ----------------
CH_SCALE = 0.55                    # NL units -> GC pixels (NL option rows are 32 units, GameCube's are 16 px)
k = CH_SCALE * PX
CH_W, CH_H = 460, 236              # biggest GameCube choice window, in NL units
L = lyt.Layout('out/selWin/slct_win/blyt/slct_win.bclyt')
L.size = (CH_W + 80, CH_H + 80)
def _size(p):
    if p['name'] == 'N_slct_win': p['t'] = (0, CH_H / 2 + 4, 0)
    if p['name'] in ('W_slct_00', 'W_slct_sh_00'): p['size'] = (CH_W, CH_H)
    if p['name'] == 'P_pattern_00': p['size'] = (CH_W - 18, CH_H - 16); p['t'] = (0, -8, 0)
    for c in p['kids']: _size(c)
_size(L.root)
for m in L.mats:
    if m['name'] == 'P_pattern_00':
        tx, ty, rr, sx, sy = m['srt'][0]; m['srt'][0] = (tx, ty, rr, sx * (CH_W - 18) / 216, sy * (CH_H - 16) / 58)
hide = tuple('N_meg_%02d' % i for i in range(6)) + ('N_anlg_slct', 'P_kuchi_00', 'P_kuchi_sh_00', 'N_slct_00')
r = lyt.R(L, k, hide=hide); r.draw(L.root)
img = r.rgba(); assert img.getbbox(); win = img.crop(img.getbbox())
add_rgba('nlui_choice_win', win)
defines += ['#define NLUI_CHOICE_WIN_W_PX %.2ff' % (win.width / PX), '#define NLUI_CHOICE_WIN_H_PX %.2ff' % (win.height / PX),
            '#define NLUI_CHOICE_CAP_PX %.2ff' % (36 * CH_SCALE)]
# cursor arrow (with shadow) and the orange underline
L = lyt.Layout('out/selWin/slct_win/blyt/slct_win.bclyt')
r = lyt.R(L, k, hide=('N_meg_00', 'N_meg_01', 'N_meg_02', 'N_meg_03', 'N_meg_04', 'N_meg_05', 'N_anlg_slct', 'P_kuchi_00', 'P_kuchi_sh_00', 'W_slct_sh_00', 'P_pattern_00'), skip=('W_slct_00',))
r.draw(L.root); img = r.rgba(); assert img.getbbox(); cur = img.crop(img.getbbox())
add_rgba('nlui_choice_cursor', cur)
defines += ['#define NLUI_CHOICE_CURSOR_W_PX %.2ff' % (cur.width / PX), '#define NLUI_CHOICE_CURSOR_H_PX %.2ff' % (cur.height / PX)]

# ---------------- item name tag ----------------
TAG_SCALE = 1.0
k = TAG_SCALE * PX
L = lyt.Layout('out/Balloon/itm_balloon/blyt/itm_balloon.bclyt')
def _tag(p):
    if p['name'] == 'P_bln_C': p['size'] = (64, 32)
    if p['name'] == 'P_bln_L': p['t'] = (-32, 0, 0)
    if p['name'] == 'P_bln_R': p['t'] = (32, 0, 0)
    for c in p['kids']: _tag(c)
_tag(L.root)
r = lyt.R(L, k, hide=('P_kuchi_00', 'P_kuchi_01', 'P_kuchi_02', 'T_itm_name', 'S_itm_name')); r.draw(L.root)
img = r.rgba(); assert img.getbbox(); bln = img.crop(img.getbbox())
add_rgba('nlui_tag_balloon', bln)       # left cap | 64-unit uniform middle | right cap
defines += ['#define NLUI_TAG_BALLOON_W_PX %.2ff' % (bln.width / PX), '#define NLUI_TAG_BALLOON_H_PX %.2ff' % (bln.height / PX),
            '#define NLUI_TAG_CAP_PX %.2ff' % ((bln.width / PX - 64 * TAG_SCALE) / 2)]
L = lyt.Layout('out/Balloon/itm_balloon/blyt/itm_balloon.bclyt')
r = lyt.R(L, k, hide=('N_bln',)); r.draw(L.root)
img = r.rgba(); assert img.getbbox(); tail = img.crop(img.getbbox())
add_rgba('nlui_tag_tail', tail)         # the three bubbles, pointing down-left
defines += ['#define NLUI_TAG_TAIL_W_PX %.2ff' % (tail.width / PX), '#define NLUI_TAG_TAIL_H_PX %.2ff' % (tail.height / PX)]

# ---------------- write C ----------------
with open(OUT, 'w') as f:
    f.write('/* Generated by nl_ui_survey/gen_nlui.py from the New Leaf layouts. Do not edit. */\n')
    f.write('#include "pc_nl_ui.h"\n\n')
    for name, fmt, W, H, data, size in textures:
        f.write('u8 %s_tex[%d] ATTRIBUTE_ALIGN(32) = {\n' % (name, len(data)))
        for i in range(0, len(data), 32):
            f.write('    ' + ','.join(str(b) for b in data[i:i + 32]) + ',\n')
        f.write('};\n\n')
with open(OUT.replace('.c', '.h').replace('/src/', '/include/').replace('pc_nl_ui_data', 'pc_nl_ui_data'), 'w') as f:
    f.write('/* Generated by nl_ui_survey/gen_nlui.py. Do not edit. */\n#ifndef PC_NL_UI_DATA_H\n#define PC_NL_UI_DATA_H\n#include "types.h"\n\n')
    f.write('#define NLUI_PX %d\n' % PX)
    for name, fmt, W, H, data, size in textures:
        f.write('extern u8 %s_tex[];\n#define %s_TW %d\n#define %s_TH %d\n#define %s_IW %d\n#define %s_IH %d\n' % (name, name.upper(), W, name.upper(), H, name.upper(), size[0], name.upper(), size[1]))
    for d in defines: f.write(d + '\n')
    f.write('\n#endif\n')
for name, fmt, W, H, data, size in textures:
    print(name, fmt, W, H, len(data))
