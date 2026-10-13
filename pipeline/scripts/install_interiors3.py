"""Museum / police / post office / Able Sisters walls and floors -> that building's New Leaf etc_wall / etc_carpet.
GC textures are picked by index from fixes_test/dump_<scene>/index.txt (contact sheets fixes_test/shots/dump_*.png).
crop = (x0, y0, x1, y1) as fractions of the NL texture."""
from pathlib import Path
from PIL import Image
from install_apple import dds_rgba
ROOT = Path(__file__).resolve().parent
NL = ROOT/'furn_work'/'nl_idr'
OUT = ROOT.parent/'texture_pack'/'3ds_interiors'
DUMP = ROOT.parent/'fixes_test'
FULL = (0, 0, 1, 1); TOP = (0, 0, 1, .5); BOT = (0, .5, 1, 1); MID = (0, .2, 1, .7)
PAIRS = [  # scene, dump index, NL texture, crop
    (35, 16, 'Models__idr_museum_ent/etc_carpet.png', FULL), (35, 20, 'Models__idr_museum_ent/etc_carpet.png', FULL),
    (35, 15, 'Common_idr__museum_wall__museum_wall/etc_wall.png', MID), (35, 19, 'Common_idr__museum_wall__museum_wall/etc_wall.png', BOT),
    (36, 11, 'Models__idr_museum_art_0/etc_carpet.png', (0, 0, .5, .5)),
    (36, 10, 'Models__idr_museum_art_0/etc_wall.png', TOP), (36, 8, 'Models__idr_museum_art_0/etc_wall.png', BOT),
    (37, 14, 'Models__idr_museum_fossil_0/etc_wall.png', TOP), (37, 16, 'Models__idr_museum_fossil_0/etc_wall.png', BOT),
    (39, 20, 'Models__idr_museum_fish_0/etc_carpet.png', (0, 0, .5, .5)), (39, 16, 'Models__idr_museum_fish_0/etc_wall.png', MID),
    (17, 15, 'Models__idr_police_A/etc_carpet.png', FULL), (17, 14, 'Models__idr_police_A/etc_wall.png', TOP), (17, 10, 'Models__idr_police_A/etc_wall.png', FULL),
    (14, 21, 'Models__idr_postoffice/etc_carpet.png', FULL), (14, 23, 'Models__idr_postoffice/etc_carpet.png', FULL),
    (9, 21, 'Models__idr_shop_grocery/etc_wall.png', MID),      # Nook's Cranny plank wall
    (12, 7, 'Models__idr_tent/etc_wall.png', MID),             # Redd's tent curtain wall
    (12, 17, 'Models__idr_tent/etc_carpet.png', (.35, 0, 1, .65)),   # Redd's straw mat floor -> NL tent tarp (clear of the plant shadow)
    (38, 19, 'Models__idr_museum_ent/etc_carpet.png', FULL),        # insect room parquet -> museum floor (matches the entrance)
    (38, 13, 'Models__idr_museum_insect_1/tex_grass.png', FULL),   # insect room grass beds
    (38, 22, 'Models__idr_museum_insect_1/tex_grass.png', FULL),
    # post office 14/15 are the ATM and a counter panel, not walls: left GameCube
]
def main():
    n = 0
    for sc, idx, nl, crop in PAIRS:
        names = (DUMP/f'dump_{sc}'/'index.txt').read_text().split('\n')
        gc = names[idx]; w, h = map(int, gc.split('_')[1].split('x'))
        src = Image.open(NL/nl).convert('RGBA'); W, H = src.size
        im = src.crop((round(crop[0]*W), round(crop[1]*H), round(crop[2]*W), round(crop[3]*H)))
        s = max(1, min(4, round(max(im.size[0]/w, im.size[1]/h))))
        im = im.resize((w*s, h*s), Image.LANCZOS); im.putalpha(255)
        (OUT/f'{gc}.dds').write_bytes(dds_rgba(im)); n += 1
        print(sc, idx, gc, '<-', nl, im.size)
    print(n, 'installed')
if __name__ == '__main__':
    main()
