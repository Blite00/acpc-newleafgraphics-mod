"""Scripted replay of the hand-made 3ds_interiors entries (2026-10-09):
  * the SOLD OUT shop sign: the GameCube sign texture upscaled, with a New Leaf style SOLD OUT panel drawn on top
  * shop floors left GameCube after install_room_textures: nearest-colour New Leaf carpets, a green tile, and plain
    floors as soft noise in the GameCube floor's own average colour (fixed seed)
GameCube textures come from furn_work/gc_tex (gc_tex_extract.py). Run after install_room_textures.py."""
from pathlib import Path
import glob, os
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from install_apple import dds_rgba

ROOT = Path(__file__).resolve().parent
W = ROOT / 'furn_work'
OUT = ROOT.parent / 'texture_pack' / '3ds_interiors'
SOLD_OUT = 'tex1_32x32_215cab545676adda_272b7b605d4a641f_8'
NEAREST = ['tex1_64x64_33e9c797d2d85047_347f5334d43531e2_8', 'tex1_64x64_33e9c797d2d85047_8290dec09e7413b8_8',
           'tex1_64x64_9efb68fbe4d63f69_347f5334d43531e2_8', 'tex1_64x64_9efb68fbe4d63f69_8290dec09e7413b8_8',
           'tex1_64x64_bfed8a8d896636a3_231bdeb3822c15e8_8', 'tex1_64x64_ede729c68be40080_b46501efa5f31a9b_8',
           'tex1_64x64_fa2de98b60dc8767_231bdeb3822c15e8_8', 'tex1_64x64_faa9823078d371de_b46501efa5f31a9b_8',
           'tex1_32x32_a4315e690663bc41_8507d654cb327fec_8']
# built by the game at run time (not stored on the disc): its nearest New Leaf carpet, picked once from a capture
FIXED = {'tex1_32x32_935561b89167a779_0000000000000000_6': ('insect', 32, 32)}
GREEN_TILE = 'tex1_32x32_80790b6cee0634d3_4a662c5b043c2734_8'
NOISE = NEAREST[:8]
FONT = 'C:/Windows/Fonts/arialbd.ttf'


def gc(n):
    return Image.open(W / 'gc_tex' / (n + '.png'))


def sold_out():
    S = 256
    im = gc(SOLD_OUT).convert('RGBA').resize((S, S), Image.LANCZOS)
    panel_h = int(S * 16 / 32)
    d = ImageDraw.Draw(im)
    d.rectangle((0, 0, S, panel_h), fill=(255, 250, 235, 255))
    d.rounded_rectangle((6, 6, S - 7, panel_h - 6), radius=22, outline=(236, 128, 40, 255), width=7, fill=(255, 247, 226, 255))
    d.rounded_rectangle((18, 18, S - 19, panel_h - 18), radius=14, outline=(90, 170, 70, 255), width=3)
    f1 = ImageFont.truetype(FONT, 50)
    f2 = ImageFont.truetype(FONT, 44)

    def ctr(t, f, y, col):
        w = d.textlength(t, font=f)
        d.text(((S - w) / 2, y), t, font=f, fill=col)

    ctr('SOLD', f1, 22, (214, 52, 40, 255))
    ctr('OUT', f2, 70, (214, 52, 40, 255))
    d.ellipse((S // 2 - 14, panel_h - 30, S // 2 + 14, panel_h - 6), fill=(236, 128, 40, 255))
    (OUT / (SOLD_OUT + '.dds')).write_bytes(dds_rgba(im))


def floors():
    nl = {os.path.basename(f)[7:-4]: Image.open(f).convert('RGB') for f in glob.glob(str(W / 'nl_png/carpet_*/*.png'))}
    mean = lambda im: np.asarray(im.convert('RGB')).reshape(-1, 3).mean(0)
    for n in NEAREST:
        g = gc(n).convert('RGB')
        m = mean(g)
        k = min(nl, key=lambda s: np.abs(mean(nl[s]) - m).sum() + 0.0)
        w, h = g.size
        (OUT / (n + '.dds')).write_bytes(dds_rgba(nl[k].resize((w * 2, h * 2), Image.LANCZOS).convert('RGBA')))
    for n, (k, w, h) in FIXED.items():
        (OUT / (n + '.dds')).write_bytes(dds_rgba(nl[k].resize((w * 2, h * 2), Image.LANCZOS).convert('RGBA')))
    im = Image.open(glob.glob(str(W / 'nl_png/carpet_tile_grn/*.png'))[0]).convert('RGBA').resize((64, 64), Image.LANCZOS)
    (OUT / (GREEN_TILE + '.dds')).write_bytes(dds_rgba(im))
    rng = np.random.default_rng(3)
    for n in NOISE:
        g = gc(n).convert('RGB')
        m = np.asarray(g).reshape(-1, 3).mean(0)
        w, h = g.size
        Wd, Ht = w * 2, h * 2
        noise = rng.normal(0, 5, (Ht, Wd, 1)) + (rng.normal(0, 3, (Ht // 2, Wd // 2, 1)).repeat(2, 0).repeat(2, 1))
        a = np.clip(m * 0.92 + noise, 0, 255).astype(np.uint8)
        im = Image.fromarray(np.dstack([a, np.full((Ht, Wd), 255, np.uint8)]), 'RGBA')
        (OUT / (n + '.dds')).write_bytes(dds_rgba(im))


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    sold_out()
    floors()
    print('installed SOLD OUT sign and', len(NEAREST) + len(FIXED) + 1, 'shop floors')


if __name__ == '__main__':
    main()
