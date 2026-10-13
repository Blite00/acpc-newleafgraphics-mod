"""Player shirts, step 1: every GC shirt design (32x32 CI4) upscaled 4x with the approved method
(general-model Real-ESRGAN, original detail added back), written to texture_pack/gc_shirts_hd by pack name.
Input: fixes_test/cloth/cloth_NNN.tex/.pal (PC_CLOTH_DUMP=<dir> --tree-self-test). NL-art shirts (gen_shirts_nl.py)
are written to texture_pack/nl_shirts and win because that folder replaces these files."""
import shutil, subprocess, struct
from pathlib import Path
import numpy as np
from PIL import Image
import xxh64
from install_apple import dds_rgba
ROOT = Path(__file__).resolve().parent
CL = ROOT.parent/'fixes_test'/'cloth'
OUT = ROOT.parent/'texture_pack'/'gc_shirts_hd'
src = (ROOT/'generate_mailbox_hd.py').read_text()
W = ROOT/'shirts_up'; UP = 4; PAD = 6; DETAIL = 0.35
ESR = ROOT/'toolchain/realesrgan/realesrgan-ncnn-vulkan.exe'
exec(src[src.index('def _pad_mode'):src.index('# ---------------- textures')])
def rgb5a3(v):
    if v & 0x8000: return ((v >> 10 & 31)*255//31, (v >> 5 & 31)*255//31, (v & 31)*255//31, 255)
    return ((v >> 8 & 15)*17, (v >> 4 & 15)*17, (v & 15)*17, (v >> 12 & 7)*255//7)
def decode(tex, pal):
    p = [rgb5a3(struct.unpack_from('>H', pal, i*2)[0]) for i in range(16)]
    im = Image.new('RGBA', (32, 32)); px = im.load(); o = 0
    for ty in range(0, 32, 8):
        for tx in range(0, 32, 8):
            for y in range(8):
                for x in range(0, 8, 2):
                    b = tex[o]; o += 1
                    px[tx+x, ty+y] = p[b >> 4]; px[tx+x+1, ty+y] = p[b & 15]
    return im
def shirts():
    for i in range(255):
        t = (CL/f'cloth_{i:03d}.tex').read_bytes(); p = (CL/f'cloth_{i:03d}.pal').read_bytes()
        yield i, xxh64.ci4_name(t, p, 32, 32), decode(t, p)
if __name__ == '__main__':
    items = list(shirts())
    W.mkdir(exist_ok=True); OUT.mkdir(parents=True, exist_ok=True)
    jobs = [(f's{i:03d}', im, 'GX_CLAMP', 'GX_CLAMP') for i, _, im in items]
    res = upscale_all(jobs)
    for i, name, im in items:
        r = res[f's{i:03d}']; (OUT/f'{name}.dds').write_bytes(dds_rgba(r))
        im.save(W/f'gc_{i:03d}.png'); r.save(W/f'hd_{i:03d}.png')
    print(len(items), 'shirts ->', OUT)

def pick(i, gc_im, esr_im, limit=6.0):
    """ESR keeps organic art but smears grid patterns (checks, stripes, text): when the ESR result no longer
    downsamples to the original (mean error > limit), use a crisp 4x nearest with a light blur instead."""
    from PIL import ImageFilter
    g = np.asarray(gc_im.convert('RGB')).astype(float)
    h = np.asarray(esr_im.convert('RGB').resize(gc_im.size, Image.BOX)).astype(float)
    if np.abs(g-h).mean() <= limit: return esr_im, 'esr'
    return gc_im.resize((gc_im.width*UP, gc_im.height*UP), Image.NEAREST).filter(ImageFilter.GaussianBlur(0.5)), 'crisp'
