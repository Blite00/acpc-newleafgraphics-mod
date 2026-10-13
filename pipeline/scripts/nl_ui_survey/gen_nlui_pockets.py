"""Generate pc_nl_ui_pockets_data.c/.h for the GameCube pocket screen's New Leaf extras:
  * New Leaf item icons (asset_import_work/icons/icn_NNN.png, 32x32) for the GameCube item icons, as RGBA8;
    the item -> icon table itself is in pc_nl_ui_pockets.c (pc_nlui_pk_icon_index), this only packs the art,
  * New Leaf's hand cursor (Cursor/crsl_hand) for the mouse,
  * New Leaf's item action window (ItemWin/itm_slct_win): lined cream paper in three slices (top with the item-name
    pill, one repeatable option row, bottom) and its orange arrow cursor.
Usage: python gen_nlui_pockets.py [pc_root]   (default: the pockets helper root)
"""
import os as _os
_ROOT = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
if _os.path.basename(_ROOT) == 'nl_ui_survey': _ROOT = _os.path.dirname(_ROOT)
os = _os

import os, sys
import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import nlui_gen_common as C  # noqa: E402

PC_ROOT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'ACGC-PC-Port', 'pc')
ICONS = os.path.join(_ROOT, 'icons', 'icn_%03d.png')
C.use_scratch()
import lyt  # noqa: E402

PX = C.PX
M = C.Module('pc_nl_ui_pockets')

# ---- item icons: every NL icon pc_nl_ui_pockets.c can ask for (keep in step with pc_nlui_pk_icon_index) ----
USED = sorted({
    0, 10, 39, 69,                                                   # furniture leaf, bell bags (small, mid, big)
    191, 192, 193, 194, 195, 196, 197, 198, 199, 200, 201, 202, 203, 204, 205, 206, 207, 208, 210, 212, 213, 214,
    215, 216, 217, 218, 220, 221, 223, 224, 227, 238, 239, 240, 254,                              # fish
    127, 128, 129, 132, 138, 139, 140, 141, 142, 144, 145, 146, 147, 149, 150, 151, 152, 153, 154, 156, 157, 158,
    159, 160, 163, 164, 166, 168, 170, 171, 172, 173, 174, 178, 179, 184, 185, 188,               # insects
    255, 256, 257, 259, 261, 262, 263, 264, 265, 266,                                            # junk, shells
    301, 302, 303, 304, 305, 306, 345, 368,                                                      # food
    332, 333, 334,                                                                               # seeds, saplings
    307, 308, 309, 310, 311, 313, 317, 318, 319, 320, 321, 322, 323, 324, 325, 326, 330, 335, 355, 357, 369, 370,
    427, 490,
})
for n in USED:
    im = Image.open(ICONS % n).convert('RGBA')
    assert im.size == (32, 32), n
    a = np.asarray(im).copy()
    a[..., 3] = np.where(a[..., 3] >= 128, 255, 0)   # the GameCube icon path alpha-tests at 254
    M.add_rgba('nlui_pk_icn_%03d' % n, Image.fromarray(a))
slot = [-1] * 522
for i, n in enumerate(USED): slot[n] = i
M.define('NLUI_PK_ICON_N', len(USED))
M.define('NLUI_PK_ICON_TEXES', '{ ' + ', '.join('nlui_pk_icn_%03d_tex' % n for n in USED) + ' }')
M.define('NLUI_PK_ICON_SLOT', '{ ' + ', '.join(str(s) for s in slot) + ' }')

# ---- New Leaf hand cursor (as the keyboard helper): pointing, pressed and grabbing; 32x32 NL pixels ----
for name, f in (('nlui_pk_hand', 'tc_crsl_hand_po'), ('nlui_pk_hand_c', 'tc_crsl_hand_c'), ('nlui_pk_hand_g', 'tc_crsl_hand_g')):
    p = 'out/Cursor/crsl_hand/timg/%s.png' % f
    if not os.path.exists(p): p = 'out/Cursor/crsl_hand/timg/tc_crsl_hand_c.png'
    im = Image.open(p).convert('RGBA')
    M.add_rgba(name, im.resize((im.width * PX, im.height * PX), Image.LANCZOS))
M.define('NLUI_PK_HAND_PX', 32.0)
M.define('NLUI_PK_HAND_HOT_X', 4.0)   # crsl_hand.bclyt: P_point_00 top-left at (-4, +7) from the pointer
M.define('NLUI_PK_HAND_HOT_Y', 7.0)
M.define('NLUI_PK_HAND_SHADOW_DY', 3.0)

# ---- item action window, after ItemWin/itm_slct_win: cream paper (W_slct_00C 255,245,185) with a green rim and a
# green underline per option (P_undrLine 155,220,70), the NL hand-off shadow. Drawn here at PX texels per pixel
# in three slices: top, one option row (repeated), bottom, so it fits any GameCube option count.
from PIL import ImageDraw  # noqa: E402
SEL_W, SEL_ROW, SEL_CAP, SEL_R = 132, 16, 8, 7          # pixels: width, option row, top/bottom caps, corner radius
SEL_PAPER, SEL_RIM, SEL_LINE, SEL_SHADE = (255, 245, 185, 255), (155, 220, 70, 255), (155, 220, 70, 255), (60, 50, 20, 110)
SEL_TEXT_X = 18                                          # text column from the left edge


def paper(rows):
    W, H = SEL_W * PX, (2 * SEL_CAP + rows * SEL_ROW) * PX
    im = Image.new('RGBA', (W + 3 * PX, H + 3 * PX), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle([2 * PX, 3 * PX, W + 2 * PX, H + 3 * PX], SEL_R * PX, fill=SEL_SHADE)      # soft shade
    d.rounded_rectangle([0, 0, W - 1, H - 1], SEL_R * PX, fill=SEL_RIM)
    d.rounded_rectangle([int(1.5 * PX), int(1.5 * PX), W - 1 - int(1.5 * PX), H - 1 - int(1.5 * PX)],
                        (SEL_R - 1.5) * PX, fill=SEL_PAPER)
    for i in range(rows):
        y = (SEL_CAP + i * SEL_ROW + SEL_ROW - 2) * PX
        d.rectangle([(SEL_TEXT_X - 2) * PX, y, (SEL_W - 6) * PX, y + int(1.2 * PX)], fill=SEL_LINE)
    return im


pp = paper(3)
cap, row = SEL_CAP * PX, SEL_ROW * PX
M.add_rgba('nlui_pk_sel_top', pp.crop((0, 0, pp.width, cap + row)))                 # cap + first option row
M.add_rgba('nlui_pk_sel_row', pp.crop((0, cap + row, pp.width, cap + 2 * row)))      # a middle option row
M.add_rgba('nlui_pk_sel_bot', pp.crop((0, cap + 2 * row, pp.width, pp.height)))     # last option row + cap + shade
M.define('NLUI_PK_SEL_W', pp.width / PX)
M.define('NLUI_PK_SEL_TOP_H', (cap + row) / PX)
M.define('NLUI_PK_SEL_ROW_H', SEL_ROW)
M.define('NLUI_PK_SEL_BOT_H', (pp.height - cap - 2 * row) / PX)
M.define('NLUI_PK_SEL_CAP', SEL_CAP)
M.define('NLUI_PK_SEL_TEXT_X', SEL_TEXT_X)
win, top1, mid0, mid1, bot0, row_h, _tx = pp, cap + row, cap + row, cap + 2 * row, cap + 2 * row, row, SEL_TEXT_X * PX
SEL_SCALE = 0.8
K = SEL_SCALE * PX
# NL's orange arrow cursor (P_crsl_00)
L2 = lyt.Layout('out/ItemWin/itm_slct_win/blyt/itm_slct_win.bclyt')
r2 = lyt.R(L2, K, hide=('N_itm_nm_00', 'W_slct_00'))
r2.draw(L2.root)
ci = r2.rgba(); cb = ci.getbbox()
if cb is None:   # the arrow lives under the window pane; draw it on its own
    L2 = lyt.Layout('out/ItemWin/itm_slct_win/blyt/itm_slct_win.bclyt')
    r2 = lyt.R(L2, K, hide=('N_itm_nm_00',), skip=('W_slct_00',) + tuple('P_undrLine_%02d' % i for i in range(6)))
    r2.draw(L2.root); ci = r2.rgba(); cb = ci.getbbox()
cur = ci.crop(cb)
M.add_rgba('nlui_pk_sel_cursor', cur)
M.define('NLUI_PK_SEL_CURSOR_W', cur.width / PX); M.define('NLUI_PK_SEL_CURSOR_H', cur.height / PX)
M.write(PC_ROOT)

prev = Image.new('RGBA', (win.width, top1 + (mid1 - mid0) + win.height - bot0), (60, 70, 80, 255))
prev.alpha_composite(win.crop((0, 0, win.width, top1)), (0, 0))
prev.alpha_composite(win.crop((0, mid0, win.width, mid1)), (0, top1))
prev.alpha_composite(win.crop((0, bot0, win.width, win.height)), (0, top1 + mid1 - mid0))
prev.alpha_composite(cur, (int(_tx - cur.width - 4), int(top1 - row_h + 4)))
prev.save(os.path.join(C.PREVIEW, 'nlui_pk__sel3.png'))
