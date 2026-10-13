"""New Leaf wallpaper / carpet textures for the GameCube player rooms (texture pack, reversible).

GC wall = 0x1020 bytes: 16-entry RGB5A3 palette + two 64x64 CI4 tiles (upper, lower). GC floor = palette + four 64x64
CI4 tiles (2x2). Each GC wall/floor is matched to a New Leaf wall_*/carpet_* (visual + name; overrides below), the NL image
is cut into the same tiles and written as a DDS keyed to the GC tile + palette hash. Disable by moving
texture_pack/3ds_interiors out of texture_pack.
"""
import json, os, struct, glob
import numpy as np
from pathlib import Path
from PIL import Image
from install_apple import xxh, dds_rgba

ROOT = Path(__file__).resolve().parent
W = ROOT/'furn_work'
OUT = ROOT.parent/'texture_pack'/'3ds_interiors'
UP = 2

SHOPS = {67: 'shop_homecenter', 68: 'shop_conveni', 69: 'shop_super', 70: 'shop_depart_2F'}
WALL_OVERRIDE = {67: 'wood', 27: 'music_room', 9: 'plaster', 18: 'wilderness', 43: 'office', 44: 'egypt', 46: 'empty_lot', 48: 'highlands',
                 49: 'roadside_tree', 57: 'desert', 60: 'tropical'}
FLOOR_OVERRIDE = {67: 'flooring_old', 68: 'tile_grn', 69: 'red', 70: 'tile_fresh', 2: 'tile_redblack', 3: 'flooring_old', 4: 'tile_honeycomb', 5: 'flooring_birch', 8: 'arabia', 9: 'moss',
                  10: 'tatami', 11: 'tatami_plank', 12: 'citrus', 14: 'road', 17: 'halloween', 18: 'wilderness', 19: 'green',
                  25: 'snowman', 29: 'tile_fresh', 30: 'luxurious', 31: 'tatami', 32: 'bamboo', 33: 'kitchen',
                  34: 'tile_coarse', 36: 'dynasty', 37: 'antique', 38: 'slate', 41: 'cowhide', 42: 'steel', 43: 'office',
                  44: 'egypt', 46: 'empty_lot', 47: 'xmas', 48: 'flowers_grass', 49: 'sidewalk', 50: 'tile_mosaic',
                  51: 'parquet', 52: 'basement', 53: 'chessboard', 55: 'straw', 56: 'concrete', 57: 'desert', 59: 'palace',
                  60: 'tropical', 61: 'toy', 62: 'kitsch', 63: 'tile_ylw', 64: 'mario', 65: 'wrestling', 66: 'harvest'}

def pal_entries(b):
    return [struct.unpack('<H', b[i*2:i*2+2])[0] for i in range(16)]       # dump is host order

def rgba(c):
    if c & 0x8000: return (((c >> 10) & 31)*255//31, ((c >> 5) & 31)*255//31, (c & 31)*255//31, 255)
    return (((c >> 8) & 15)*17, ((c >> 4) & 15)*17, (c & 15)*17, ((c >> 12) & 7)*255//7)

def indices(tile):
    out = []
    for v in tile: out += [v >> 4, v & 15]
    return out

def tile_name(tile, pal):
    idx = indices(tile); lo, hi = min(idx), max(idx)
    be = b''.join(struct.pack('>H', c) for c in pal[lo:hi+1])
    return f'tex1_64x64_{xxh(bytes(tile))}_{xxh(be)}_8.dds'

def decode(tile, pal):
    P = [rgba(c) for c in pal]; im = np.zeros((64, 64, 4), np.uint8); p = 0
    for ty in range(0, 64, 8):
        for tx in range(0, 64, 8):
            for y in range(8):
                for x in range(0, 8, 2):
                    v = tile[p]; p += 1
                    im[ty+y, tx+x] = P[v >> 4]; im[ty+y, tx+x+1] = P[v & 15]
    return im

def desc(im, size): return np.asarray(im.convert('RGB').resize(size, Image.BOX)).astype(float).reshape(-1)/255

def up(im, size):
    return im.convert('RGB').resize((size, size), Image.LANCZOS).convert('RGBA')

def main():
    OUT.mkdir(parents=True, exist_ok=True)
    nlw = {os.path.basename(f)[5:-4]: Image.open(f).convert('RGB') for f in glob.glob(str(W/'nl_png/wall_*/*.png'))}
    nlc = {os.path.basename(f)[7:-4]: Image.open(f).convert('RGB') for f in glob.glob(str(W/'nl_png/carpet_*/*.png'))}
    report = {'wall': {}, 'floor': {}}; n = 0
    for k in range(71):
        b = open(W/f'room/wall_{k:02d}.bin', 'rb').read(); pal = pal_entries(b[:32])
        tiles = [b[32:32+0x800], b[32+0x800:32+0x1000]]
        gc = Image.new('RGB', (64, 128))
        for i, t in enumerate(tiles): gc.paste(Image.fromarray(decode(t, pal)[..., :3]), (0, i*64))
        key = WALL_OVERRIDE.get(k) or min(nlw, key=lambda s: np.abs(desc(nlw[s], (8, 16))-desc(gc, (8, 16))).mean())
        im = nlw[key].resize((64, 128), Image.LANCZOS)
        for i, t in enumerate(tiles):
            (OUT/tile_name(t, pal)).write_bytes(dds_rgba(up(im.crop((0, i*64, 64, i*64+64)), 64*UP))); n += 1
        report['wall'][k] = key
    for k in range(71):
        b = open(W/f'room/floor_{k:02d}.bin', 'rb').read(); pal = pal_entries(b[:32])
        tiles = [b[32+i*0x800:32+(i+1)*0x800] for i in range(4)]
        gc = Image.new('RGB', (128, 128))
        for i, t in enumerate(tiles): gc.paste(Image.fromarray(decode(t, pal)[..., :3]), ((i % 2)*64, (i//2)*64))
        gd = desc(gc, (8, 8))
        def score(s):
            im = nlc[s]; full = np.abs(desc(im, (8, 8))-gd).mean(); quad = np.abs(desc(im.crop((0, 0, 128, 128)), (8, 8))-gd).mean()
            return min(full, quad)
        key = FLOOR_OVERRIDE.get(k) or min(nlc, key=score)
        im = nlc[key]
        quad_better = np.abs(desc(im.crop((0, 0, 128, 128)), (8, 8))-gd).mean() < np.abs(desc(im, (8, 8))-gd).mean()
        src = im.crop((0, 0, 128, 128)) if quad_better else im          # a rug: the GC floor holds its top-left quarter
        src = src.resize((128, 128), Image.LANCZOS)
        for i, t in enumerate(tiles):
            x, y = (i % 2)*64, (i//2)*64
            (OUT/tile_name(t, pal)).write_bytes(dds_rgba(up(src.crop((x, y, x+64, y+64)), 64*UP))); n += 1
        report['floor'][k] = (key, 'rug' if quad_better else 'tile')
    json.dump(report, open(W/'room_mapping.json', 'w'), indent=1)
    print('wrote', n, 'textures to', OUT)

if __name__ == '__main__':
    main()
