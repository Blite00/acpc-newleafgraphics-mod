"""Generate pc_nl_ui_keyboard_data.c/.h: New Leaf's wooden QWERTY keyboard (Swkbd/swkbd_qwerty Keytop_qwerty)
rearranged onto the GameCube editor's 10x4 key grid, pre-rendered twice (normal keys and NL's lighter "on" keys).

The GameCube grid (m_editor_ovl.c mED_get_code) is 10 columns x 4 rows:
  row 0: 10 keys  -> NL keys 00..09 (NL '-' key merged into the backspace key)
  row 1: 10 keys  -> NL keys 11..20 (q..p); NL's enter key on this row becomes the START "OK" key
  row 2:  9 keys + newline -> NL keys 21..29, keys 30..32 merged into one wide newline (enter-icon) key
  row 3:  9 keys + space   -> NL keys 33..41, keys 42..44 merged into one wide space key
  row 4 (no cursor cells): caps (L), shift (X accent swap), space (R), three mode keys (Y: letters/signs/marks)
The Japanese backspace icon (P_Key_BspIconJP, T_key_BspJP) is hidden: one arrow.
Labels are drawn at run time with the GameCube font; this script bakes only the key art and icons.

Usage: python gen_nlui_keyboard.py [pc_root]
"""
import os, sys
import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import nlui_gen_common as C  # noqa: E402

PC_ROOT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'ACGC-PC-Port', 'pc')
C.use_scratch()
import lyt  # noqa: E402

K = C.PX
LAYOUT = 'out/Swkbd/swkbd_qwerty/blyt/Keytop_qwerty.bclyt'
TOP, BOTTOM = 55.0, -72.0           # NL y range kept (shade window top .. just under the bottom row)
ON = ['KtpQweKey00', 'KtpQweKey01', 'KtpQweKey02', 'KtpQweKey02L', 'KtpQweKey03', 'KtpQweKey04', 'KtpQweKey05',
      'KtpQweKeyBsp', 'KtpQweKeyCps', 'KtpQweKeyEnt', 'KtpQweKeyRomC', 'KtpQweKeyRomL', 'KtpQweKeyRomR',
      'KtpQweKeySft', 'KtpQweKeySpc']


def walk(p, f):
    f(p)
    for k in p['kids']: walk(k, f)


def find(L, name):
    out = []
    walk(L.root, lambda p: out.append(p) if p['name'] == name else None)
    return out[0]


def screen_box(r, name):
    M, x0, y0, x1, y1 = r.boxes[name]
    ax, ay = r.to_screen(M, x0, y1)
    bx, by = r.to_screen(M, x1, y0)
    return min(ax, bx), min(ay, by), max(ax, bx), max(ay, by)


def slice3(r, X0, Y0, X1, Y1, pane, L, cap=7.0):
    """draw pic pane `pane`'s material as a 3-slice key between screen-space X0..X1 (NL units via r.k)"""
    mat = pane['mat']; mt = L.mats[mat]
    T = lyt.tex(L, mt['maps'][0][0]); tw = T.shape[1]
    # back to NL root units (y up)
    def nl(x, y): return (x - r.W / 2) / r.k, -(y - r.H / 2) / r.k
    x0, y1 = nl(X0, Y0); x1, y0 = nl(X1, Y1)
    M = np.eye(3); vc = pane['vc']; cu = cap / tw
    r.quad(M, x0, y0, x0 + cap, y1, mat, vc, (0, 0, cu, 0, 0, 1, cu, 1), 1.0)
    r.quad(M, x0 + cap, y0, x1 - cap, y1, mat, vc, (cu, 0, 1 - cu, 0, cu, 1, 1 - cu, 1), 1.0)
    r.quad(M, x1 - cap, y0, x1, y1, mat, vc, (1 - cu, 0, 1, 0, 1 - cu, 1, 1, 1), 1.0)


def render(on):
    L = lyt.Layout(LAYOUT)
    if on:
        L.tex = [(t[:-6] + 'on.bclim') if t[:-6] in ON else t for t in L.tex]
    probe = lyt.R(L, K); probe.draw(L.root)
    b = {n: screen_box(probe, n) for n in probe.boxes}
    merged = {
        'bsp': (b['P_key_10'][0], b['P_key_Bsp'][1], b['P_key_Bsp'][2], b['P_key_Bsp'][3], 'P_key_Bsp'),
        'nl': (b['P_key_30'][0], b['P_key_30'][1], b['P_key_32'][2], b['P_key_32'][3], 'P_key_Ent'),
        'sp': (b['P_key_42'][0], b['P_key_42'][1], b['P_key_44'][2], b['P_key_44'][3], 'P_key_Spc'),
    }
    # backspace icon to the merged key's centre (its parent N_Key_Bsp also holds the skipped key pic)
    nb = find(L, 'N_Key_Bsp')
    cx = (merged['bsp'][0] + merged['bsp'][2]) / 2 / K - 160
    nb['t'] = (cx, nb['t'][1], nb['t'][2])   # icon +1 inside N_Key_Bsp, N_P_key -1: lands at cx
    hide = ('P_Key_BspIconJP', 'T_key_BspJP', 'P_Key_EntIcon', 'N_Key_10', 'N_Key_31', 'N_Key_32', 'N_Key_43',
            'N_Key_44', 'N_dictionary', 'P_key_SftIcon')
    skip = ('P_key_Bsp', 'P_key_30', 'P_key_42')
    # the shade window fitted to the kept range; its A8 texture is a mask in the material's dark brown
    sh = find(L, 'W_ktpShade')
    sh['size'] = (sh['size'][0], TOP - BOTTOM)
    sh['t'] = (sh['t'][0], (TOP + BOTTOM) / 2 - 11.0, sh['t'][2])
    rs = lyt.R(L, K, show=(), hide=('N_P_key', 'N_romanKey', 'N_dictionary')); rs.draw(L.root)
    shade = np.asarray(rs.rgba()).copy(); shade[..., :3] = (L.mats[sh['mat']]['black'][:3] * 255).astype(np.uint8)
    shade = Image.fromarray(shade)

    def merged_first(rr, p, M, box, a):   # merged keys go under their icons
        if p['name'] == 'N_P_key':
            for k, (X0, Y0, X1, Y1, src) in merged.items():
                slice3(rr, X0, Y0, X1, Y1, find(L, src), L)
    r = lyt.R(L, K, hide=hide + ('W_ktpShade',), skip=skip, hook=merged_first); r.draw(L.root)
    # the enter icon on the newline key
    ei = find(L, 'P_Key_EntIcon'); w, h = ei['size']
    X0, Y0, X1, Y1, _ = merged['nl']
    cx = (X0 + X1) / 2 / K - 160; cy = -((Y0 + Y1) / 2 / K - 120)
    r.quad(np.eye(3), cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2, ei['mat'], ei['vc'], ei['tc'][0], 1.0)
    img = shade.copy(); img.alpha_composite(r.rgba())
    y0 = int(round((120 - TOP) * K)); y1 = int(round((120 - BOTTOM) * K))
    img = img.crop((0, y0, r.W, y1))
    # key rectangles in keyboard pixels (GameCube screen px, origin at the cropped image's top-left)
    def px(box): return tuple(round(v / K, 2) for v in (box[0], box[1] - y0, box[2], box[3] - y0))
    cells = []
    rows = [['P_key_%02d' % i for i in range(0, 10)], ['P_key_%02d' % i for i in range(11, 21)],
            ['P_key_%02d' % i for i in range(21, 30)] + ['nl'], ['P_key_%02d' % i for i in range(33, 42)] + ['sp']]
    for row in rows:
        for n in row:
            cells.append(px(merged[n][:4] if n in merged else b[n]))
    special = {'BSP': px(merged['bsp'][:4]), 'OK': px(b['P_key_Ent']), 'CPS': px(b['P_key_Cps']),
               'SFT': px(b['P_key_Sft']), 'SPC': px(b['P_key_Spc']), 'MODE0': px(b['P_romanKey_00']),
               'MODE1': px(b['P_romanKey_01']), 'MODE2': px(b['P_romanKey_02'])}
    return img, cells, special


def main():
    base, cells, special = render(False)
    on, _, _ = render(True)
    m = C.Module('pc_nl_ui_keyboard')
    m.add_rgba('nlui_kb_base', base)
    m.add_rgba('nlui_kb_on', on)
    # New Leaf's hand cursor (Cursor/crsl_hand): pointing, and the pressed pose; 32x32 NL pixels, upscaled
    for name, f in (('nlui_kb_hand', 'tc_crsl_hand_po'), ('nlui_kb_hand_c', 'tc_crsl_hand_c')):
        im = Image.open('out/Cursor/crsl_hand/timg/%s.png' % f).convert('RGBA')
        m.add_rgba(name, im.resize((im.width * K, im.height * K), Image.LANCZOS))
    m.define('NLUI_KB_HAND_PX', 32.0)
    m.define('NLUI_KB_HAND_HOT_X', 4.0)   # crsl_hand.bclyt: P_point_00 top-left at (-4, +7) from the pointer
    m.define('NLUI_KB_HAND_HOT_Y', 7.0)
    m.define('NLUI_KB_HAND_SHADOW_DY', 3.0)   # P_point_s_00 sits 3 px lower, flat black
    m.define('NLUI_KB_W_PX', base.width / K)
    m.define('NLUI_KB_H_PX', base.height / K)
    m.define('NLUI_KB_CELLS', '{ ' + ', '.join('{ %.2ff, %.2ff, %.2ff, %.2ff }' % c for c in cells) + ' }')
    for k, c in special.items():
        m.define('NLUI_KB_%s' % k, '{ %.2ff, %.2ff, %.2ff, %.2ff }' % c)
    m.write(PC_ROOT)
    # preview: base with the "on" art on one key and the cells outlined
    pv = base.copy()
    x0, y0, x1, y1 = [int(v * K) for v in cells[14]]
    pv.paste(on.crop((x0, y0, x1, y1)), (x0, y0))
    bg = Image.new('RGBA', pv.size, (70, 120, 70, 255)); bg.alpha_composite(pv)
    bg.save(os.path.join(C.PREVIEW, 'nlui_kb_preview.png'))
    print(len(cells), 'cells;', special)


if __name__ == '__main__':
    main()
