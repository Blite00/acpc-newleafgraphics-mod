"""pc_furn_tvprog.c: the New Leaf TV programmes (/Ftr/TV, exported to furn_work/nl_tv/<prog>/tv.N.png) as GameCube
RGBA32 64x32 frames for pc_furn_tv.c.
Index order (pc_furn_tv.c relies on it): 0 test card (night), 1..20 shows, 21 sunny, 22 rain, 23 snow,
24 cloudy weather report, 25 static."""
from pathlib import Path
import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parent
TV = ROOT / 'furn_work' / 'nl_tv'
ORDER = ['1_US'] + [str(i) for i in range(2, 22)] + ['ff', 'rr', 'ss', 'cc', '0']


def rgba32(im):
    a = np.asarray(im.convert('RGBA'), np.uint8).copy()
    a[..., 3] = 255                     # the TV screen is opaque
    h, w = a.shape[:2]
    out = bytearray()
    for ty in range(0, h, 4):
        for tx in range(0, w, 4):
            blk = a[ty:ty + 4, tx:tx + 4].reshape(16, 4)
            out += bytes(np.stack([blk[:, 3], blk[:, 0]], 1).reshape(-1))
            out += bytes(np.stack([blk[:, 1], blk[:, 2]], 1).reshape(-1))
    return out


def folder(k):
    return TV / ('tv_program_' + k if k in ('ff', 'rr', 'ss', 'cc') else 'tv_program' + k)


def main():
    out = ['/* Generated: New Leaf TV programmes (/Ftr/TV), RGBA32 64x32 frames, used by pc_furn_tv.c */', '#include "types.h"']
    counts = []
    for k in ORDER:
        frames = sorted(folder(k).glob('tv.*.png'), key=lambda p: int(p.name.split('.')[1]))
        names = []
        for i, f in enumerate(frames):
            data = rgba32(Image.open(f).resize((64, 32)) if Image.open(f).size != (64, 32) else Image.open(f))
            n = f'pc_tvprog_{k}_{i}'
            names.append(n)
            out.append(f'static u8 {n}[] ATTRIBUTE_ALIGN(32) = {{')
            out += [','.join(map(str, data[j:j + 32])) + ',' for j in range(0, len(data), 32)]
            out.append('};')
        out.append(f'static u8* pc_tvprog_{k}_frames[] = {{ ' + ', '.join(names) + ' };')
        counts.append(len(frames))
    out.append(f'const int pc_tvprog_count = {len(ORDER)};')
    out.append('u8** pc_tvprog_frames[] = { ' + ', '.join(f'pc_tvprog_{k}_frames' for k in ORDER) + ' };')
    out.append('const int pc_tvprog_nframes[] = { ' + ', '.join(map(str, counts)) + ' };')
    out.append('/* index: 0 test card (night), 1..20 shows, 21 sunny, 22 rain, 23 snow, 24 cloudy weather report, 25 static */')
    with open(ROOT / 'ACGC-PC-Port' / 'pc' / 'src' / 'pc_furn_tvprog.c', 'w', newline='\n') as f:
        f.write('\n'.join(out) + '\n')
    print(len(ORDER), 'programmes,', sum(counts), 'frames')


if __name__ == '__main__':
    main()
