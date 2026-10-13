"""Generate pc_nl_ui_letters_data.c/.h: New Leaf bulletin board art (wooden board + pinned paper) for the
GameCube notice board (m_notice_ovl.c).

The letter screen needs no textures: the paper is the player's GameCube stationery model and the NL drop
shadow is a flat-colour quad, so only the board is pre-rendered here.

Usage: python gen_nlui_letters.py <pc_root>   (e.g. ...\\nlui_agents\\letters\\ACGC-PC-Port\\pc)
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

PX = C.PX


def rgb5a3(img):
    """GX RGB5A3: 4x4 tiles, big-endian u16; opaque texels RGB555, others ARGB3444."""
    a = np.asarray(img.convert('RGBA'), np.uint16)
    h, w = a.shape[:2]
    H, W = (h + 3) // 4 * 4, (w + 3) // 4 * 4
    p = np.zeros((H, W, 4), np.uint16); p[:h, :w] = a
    r, g, b, al = p[..., 0], p[..., 1], p[..., 2], p[..., 3]
    opaque = (r >> 3 << 10) | (g >> 3 << 5) | (b >> 3) | 0x8000
    trans = ((al >> 5) << 12) | ((r >> 4) << 8) | ((g >> 4) << 4) | (b >> 4)
    v = np.where(al >= 0xE0, opaque, trans).astype('>u2')
    t = v.reshape(H // 4, 4, W // 4, 4).transpose(0, 2, 1, 3)
    return W, H, t.tobytes()


def add_5a3(mod, tex, img):
    os.makedirs(C.PREVIEW, exist_ok=True); img.save(os.path.join(C.PREVIEW, tex + '.png'))
    W, H, data = rgb5a3(img)
    mod.textures.append((tex, W, H, data, img.size))


mod = C.Module('pc_nl_ui_letters')

# ---- wooden board: board_base_T, the centred 320x240 GameCube screen of NL's 400x240 top screen ----
L = lyt.Layout('out/Board/board/blyt/board_base_T.bclyt')
r = lyt.R(L, PX); r.draw(L.root)
img = r.rgba()
cx, cy = img.width / 2, img.height / 2
board = img.crop((int(cx - 160 * PX), int(cy - 120 * PX), int(cx + 160 * PX), int(cy + 120 * PX)))
add_5a3(mod, 'nlui_board_base', board)
mod.define('NLUI_BOARD_BASE_W_PX', 320.0)
mod.define('NLUI_BOARD_BASE_H_PX', 240.0)

# ---- pinned paper (board_paper, first paper only; text is drawn by the game) ----
L = lyt.Layout('out/Board/board/blyt/board_paper.bclyt')
r = lyt.R(L, PX, hide=('N_ppr_01',)); r.draw(L.root)
img = r.rgba(); bb = img.getbbox(); assert bb
paper = img.crop(bb)
add_5a3(mod, 'nlui_board_paper', paper)
# paper rectangle in GameCube pixels relative to the layout centre (y up)
x0 = (bb[0] - img.width / 2) / PX; x1 = (bb[2] - img.width / 2) / PX
y1 = (img.height / 2 - bb[1]) / PX; y0 = (img.height / 2 - bb[3]) / PX
mod.define('NLUI_BOARD_PAPER_X0', x0); mod.define('NLUI_BOARD_PAPER_X1', x1)
mod.define('NLUI_BOARD_PAPER_Y0', y0); mod.define('NLUI_BOARD_PAPER_Y1', y1)
print('paper rect', x0, y0, x1, y1)

mod.write(PC_ROOT)

# preview: board + paper composited
prev = board.copy()
ox = int((x0 + 160) * PX); oy = int((120 - y1) * PX)
prev.alpha_composite(paper, (ox, oy))
prev.save(os.path.join(C.PREVIEW, 'nlui_board_preview.png'))
