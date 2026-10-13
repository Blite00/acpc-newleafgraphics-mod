"""Find GameCube textures by their texture-pack name (tex1_WxH_<xxh64 tex>_<xxh64 pal>_<fmt>) in the player's
GameCube data and decode them to furn_work/gc_tex/<name>.png (the same decoder the PC_TEX_DUMP captures used).

Locations come from a table (offsets into foresta.rel); the data is checked against the hashes in the names.
usage: python gc_tex_extract.py <locations.json>
"""
import re, struct, sys, os
from pathlib import Path
import numpy as np
from PIL import Image
from xxh64 import xxh64

ROOT = Path(__file__).resolve().parent
OUT = ROOT / 'furn_work' / 'gc_tex'
FMT_BPP = {0: 4, 1: 8, 2: 8, 3: 16, 4: 16, 5: 16, 6: 32, 8: 4, 9: 8, 14: 4}


def rgb5a3(c):
    if c & 0x8000:
        return (((c >> 10) & 31) * 255 // 31, ((c >> 5) & 31) * 255 // 31, (c & 31) * 255 // 31, 255)
    return (((c >> 8) & 15) * 17, ((c >> 4) & 15) * 17, (c & 15) * 17, ((c >> 12) & 7) * 255 // 7)


def blocks(w, h, bw, bh, get):
    im = np.zeros((h, w, 4), np.uint8)
    p = 0
    for ty in range(0, h, bh):
        for tx in range(0, w, bw):
            for y in range(bh):
                for x in range(bw):
                    v = get(p)
                    p += 1
                    if ty + y < h and tx + x < w:
                        im[ty + y, tx + x] = v
    return im


def dec(raw, pal, w, h, fmt):
    if fmt == 8:
        P = [rgb5a3(struct.unpack('>H', pal[i * 2:i * 2 + 2])[0]) for i in range(len(pal) // 2)] if pal else [(i * 17,) * 3 + (255,) for i in range(16)]
        px = []
        for v in raw:
            px += [v >> 4, v & 15]
        return blocks(w, h, 8, 8, lambda p: P[px[p]] if px[p] < len(P) else (255, 0, 255, 255))
    if fmt == 9:
        P = [rgb5a3(struct.unpack('>H', pal[i * 2:i * 2 + 2])[0]) for i in range(len(pal) // 2)]
        return blocks(w, h, 8, 4, lambda p: P[raw[p]] if raw[p] < len(P) else (255, 0, 255, 255))
    if fmt == 0:
        px = []
        for v in raw:
            px += [(v >> 4) * 17, (v & 15) * 17]
        return blocks(w, h, 8, 8, lambda p: (px[p], px[p], px[p], 255))
    if fmt == 1:
        return blocks(w, h, 8, 4, lambda p: (raw[p],) * 3 + (255,))
    if fmt == 2:
        return blocks(w, h, 8, 4, lambda p: ((raw[p] & 15) * 17,) * 3 + ((raw[p] >> 4) * 17,))
    if fmt == 3:
        return blocks(w, h, 4, 4, lambda p: (raw[p * 2 + 1],) * 3 + (raw[p * 2],))
    if fmt == 5:
        return blocks(w, h, 4, 4, lambda p: rgb5a3(struct.unpack('>H', raw[p * 2:p * 2 + 2])[0]))
    if fmt == 4:
        def f(p):
            c = struct.unpack('>H', raw[p * 2:p * 2 + 2])[0]
            return (((c >> 11) & 31) * 255 // 31, ((c >> 5) & 63) * 255 // 63, (c & 31) * 255 // 31, 255)
        return blocks(w, h, 4, 4, f)
    if fmt == 6:
        im = np.zeros((h, w, 4), np.uint8)
        p = 0
        for ty in range(0, h, 4):
            for tx in range(0, w, 4):
                for y in range(4):
                    for x in range(4):
                        a, r = raw[p + (y * 4 + x) * 2], raw[p + (y * 4 + x) * 2 + 1]
                        g, b = raw[p + 32 + (y * 4 + x) * 2], raw[p + 32 + (y * 4 + x) * 2 + 1]
                        im[ty + y, tx + x] = (r, g, b, a)
                p += 64
        return im
    return None


def main():
    """usage: gc_tex_extract.py <locations.json>: {name: {"tex": [file, offset, size], "pal": [file, offset, size] or null}}"""
    import json
    loc = json.load(open(sys.argv[1]))
    files = {'foresta.rel': (ROOT / 'foresta.rel').read_bytes()}
    if (ROOT / 'main.dol').exists():
        files['main.dol'] = (ROOT / 'main.dol').read_bytes()
    OUT.mkdir(parents=True, exist_ok=True)
    for n, e in loc.items():
        p = n.split('_')
        w, h = map(int, p[1].split('x'))
        th, ph, fmt = int(p[2], 16), int(p[3], 16), int(p[4])
        f, off, size = e['tex']
        tex = files[f][off:off + size]
        if xxh64(tex) != th:
            sys.exit(f'{n}: texture data does not match (unexpected GameCube disc version?)')
        pal = None
        if e.get('pal'):
            f, off, size = e['pal']
            pal = files[f][off:off + size]
            idx = [v for b in tex for v in ((b >> 4, b & 15) if fmt == 8 else (b,))]
            lo, hi = min(idx), max(idx)
            if xxh64(pal[lo * 2:(hi + 1) * 2]) != ph:
                sys.exit(f'{n}: palette data does not match (unexpected GameCube disc version?)')
        Image.fromarray(dec(tex, pal, w, h, fmt)).save(OUT / (n + '.png'))
    print(len(loc), 'GameCube textures decoded')


if __name__ == '__main__':
    main()
