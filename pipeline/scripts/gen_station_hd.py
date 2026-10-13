"""Train station: GC textures (3 station models x summer/winter x 3 textures, 5 palettes each) sharpened with the
approved upscale (ESR + original detail, crisp fallback like the shirts), written to texture_pack/gc_station_hd."""
import re, struct
from pathlib import Path
import numpy as np
from PIL import Image
import xxh64
from install_apple import dds_rgba
ROOT = Path(__file__).resolve().parent
rel = (ROOT/'foresta.rel').read_bytes()
assets = (ROOT/'ACGC-PC-Port/pc/src/pc_assets.c').read_text()
OUT = ROOT.parent/'texture_pack'/'gc_station_hd'
def blob(name):
    m = re.search(r'\{"assets/'+name+r'\.bin",.*?, (0x[0-9A-F]+), (0x[0-9A-F]+),', assets)
    size, off = (int(x, 16) for x in m.groups()); return rel[off:off+size]
def rgb5a3(v):
    if v & 0x8000: return ((v >> 10 & 31)*255//31, (v >> 5 & 31)*255//31, (v & 31)*255//31, 255)
    return ((v >> 8 & 15)*17, (v >> 4 & 15)*17, (v & 15)*17, (v >> 12 & 7)*255//7)
def decode(tex, pal, w, h):
    p = [rgb5a3(struct.unpack_from('>H', pal, i*2)[0]) for i in range(16)]
    im = Image.new('RGBA', (w, h)); px = im.load(); o = 0
    for ty in range(0, h, 8):
        for tx in range(0, w, 8):
            for y in range(8):
                for x in range(0, 8, 2):
                    b = tex[o]; o += 1
                    px[tx+x, ty+y] = p[b >> 4]; px[tx+x+1, ty+y] = p[b & 15]
    return im
def jobs():
    for s in 'sw':
        for n in (1, 2, 3):
            for t in (1, 2, 3):
                tex = blob(f'obj_{s}_station{n}_t{t}_tex_txt')
                for c in 'abcde':
                    pal = blob(f'obj_{s}_station{n}_{c}_pal')
                    yield f'{s}{n}t{t}{c}', xxh64.ci4_name(tex, pal, 128, 32), decode(tex, pal, 128, 32)
if __name__ == '__main__':
    import gen_shirts_hd as gs
    gs.W = ROOT/'station_up'; gs.W.mkdir(exist_ok=True); gs.OUT = OUT
    items = list(jobs()); OUT.mkdir(parents=True, exist_ok=True)
    res = gs.upscale_all([(k, im, 'GX_REPEAT', 'GX_CLAMP') for k, _, im in items])
    from collections import Counter; c = Counter()
    for k, name, im in items:
        r, kind = gs.pick(0, im, res[k], limit=8.0); c[kind] += 1
        r = r.convert('RGBA'); (OUT/f'{name}.dds').write_bytes(dds_rgba(r)); im.save(gs.W/f'gc_{k}.png'); r.save(gs.W/f'hd_{k}.png')
    print(len(items), c)
