"""Shared helpers for the New Leaf UI texture generators (gen_nlui*.py).

Each generator renders New Leaf layout art with lyt.py (scratchpad renderer), encodes it as GameCube texture
formats and writes <module>_data.c / <module>_data.h for the PC port.
"""
import os as _os
_ROOT = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
if _os.path.basename(_ROOT) == 'nl_ui_survey': _ROOT = _os.path.dirname(_ROOT)
os = _os

import os
import numpy as np
from PIL import Image

SCRATCH = os.path.join(os.path.dirname(os.path.abspath(__file__)), '_scratch')
PREVIEW = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'nlui_preview')
PX = 3   # texels per GameCube screen pixel


def use_scratch():
    """chdir to the scratchpad holding out/ (unpacked NL layouts), lyt.py, font.py, gcwin.py, and import from it."""
    import sys
    os.chdir(SCRATCH)
    if SCRATCH not in sys.path: sys.path.insert(0, SCRATCH)


def rgba32(img):
    """GX RGBA8: 4x4 tiles, 32 bytes of A,R then 32 bytes of G,B."""
    a = np.asarray(img.convert('RGBA'), np.uint8)
    h, w = a.shape[:2]
    H, W = (h + 3) // 4 * 4, (w + 3) // 4 * 4
    p = np.zeros((H, W, 4), np.uint8); p[:h, :w] = a
    t = p.reshape(H // 4, 4, W // 4, 4, 4).transpose(0, 2, 1, 3, 4).reshape(-1, 16, 4)
    ar = np.stack([t[:, :, 3], t[:, :, 0]], 2).reshape(-1, 32)
    gb = np.stack([t[:, :, 1], t[:, :, 2]], 2).reshape(-1, 32)
    return W, H, np.concatenate([ar, gb], 1).tobytes()


def ia16(lum, alpha):
    """GX IA8 (16-bit): 4x4 tiles, each texel A then I."""
    h, w = lum.shape
    H, W = (h + 3) // 4 * 4, (w + 3) // 4 * 4
    L = np.zeros((H, W), np.uint8); A = np.zeros((H, W), np.uint8)
    L[:h, :w] = lum; A[:h, :w] = alpha
    t = np.stack([A, L], 2).reshape(H // 4, 4, W // 4, 4, 2).transpose(0, 2, 1, 3, 4)
    return W, H, t.reshape(-1).tobytes()


class Module:
    """Collects textures and #defines, then writes pc/src/<name>_data.c and pc/include/<name>_data.h."""

    def __init__(self, name):
        self.name = name; self.textures = []; self.defines = []

    def add_rgba(self, tex, img):
        os.makedirs(PREVIEW, exist_ok=True); img.save(os.path.join(PREVIEW, tex + '.png'))
        W, H, data = rgba32(img)
        self.textures.append((tex, W, H, data, img.size))

    def add_ia(self, tex, img):
        """IA16 from an RGBA image: intensity = mean RGB, alpha = alpha."""
        os.makedirs(PREVIEW, exist_ok=True); img.save(os.path.join(PREVIEW, tex + '.png'))
        a = np.asarray(img.convert('RGBA'))
        W, H, data = ia16(a[..., :3].mean(-1).astype(np.uint8), a[..., 3])
        self.textures.append((tex, W, H, data, img.size))

    def define(self, name, value):
        self.defines.append('#define %s %s' % (name, ('%.3ff' % value) if isinstance(value, float) else value))

    def write(self, pc_root):
        c = os.path.join(pc_root, 'src', self.name + '_data.c')
        h = os.path.join(pc_root, 'include', self.name + '_data.h')
        guard = self.name.upper() + '_DATA_H'
        with open(c, 'w') as f:
            f.write('/* Generated from the New Leaf layouts by nl_ui_survey. Do not edit. */\n#include "types.h"\n\n')
            for tex, W, H, data, size in self.textures:
                f.write('u8 %s_tex[%d] ATTRIBUTE_ALIGN(32) = {\n' % (tex, len(data)))
                for i in range(0, len(data), 40):
                    f.write('    ' + ','.join(str(b) for b in data[i:i + 40]) + ',\n')
                f.write('};\n\n')
        with open(h, 'w') as f:
            f.write('/* Generated from the New Leaf layouts by nl_ui_survey. Do not edit. */\n#ifndef %s\n#define %s\n#include "types.h"\n\n' % (guard, guard))
            f.write('#ifndef NLUI_PX\n#define NLUI_PX %d\n#endif\n' % PX)
            for tex, W, H, data, size in self.textures:
                T = tex.upper()
                f.write('extern u8 %s_tex[];\n#define %s_TW %d\n#define %s_TH %d\n#define %s_IW %d\n#define %s_IH %d\n' % (tex, T, W, T, H, T, size[0], T, size[1]))
            for d in self.defines: f.write(d + '\n')
            f.write('\n#endif\n')
        for tex, W, H, data, size in self.textures:
            print('%-28s %4dx%-4d %8d bytes' % (tex, W, H, len(data)))
