"""pc_museum4_tex.c_inc: New Leaf stand-ins for the outdoor-bank textures the insect room garden draws (they are empty
indoors and drew black). Scripted replay of the 2026-10-09 fix: cliff and river from New Leaf interior textures
(furn_work/nl_big.txt 223 / 154), earth and grass from the New Leaf dig-soil grass.
rom_museum4.c (shipped source) already points at these arrays."""
from pathlib import Path
from PIL import Image

ROOT = Path(__file__).resolve().parent


def arr(name, im, n):
    im = im.convert('RGBA').resize((n, n), Image.LANCZOS)
    data = bytearray()
    for ty in range(0, n, 4):
        for tx in range(0, n, 4):
            t = [im.getpixel((tx + x, ty + y)) for y in range(4) for x in range(4)]
            data.extend(c for r, g, b, a in t for c in (255, r))
            data.extend(c for r, g, b, a in t for c in (g, b))
    return f'static u8 {name}[] ATTRIBUTE_ALIGN(32) = {{\n' + '\n'.join(','.join(map(str, data[i:i + 32])) + ',' for i in range(0, len(data), 32)) + '\n};\n'


def main():
    nl = (ROOT / 'furn_work' / 'nl_big.txt').read_text().split('\n')
    grass = Image.open(ROOT / 'dig_source' / 'soil' / 'tex_grass.png').convert('RGB')
    out = '/* New Leaf stand-ins for outdoor-bank textures that are empty indoors (they drew black in the insect room garden) */\n'
    out += arr('pc_m4_cliff', Image.open(ROOT / 'furn_work' / nl[223]), 64)
    out += arr('pc_m4_earth', grass, 64)
    out += arr('pc_m4_river', Image.open(ROOT / 'furn_work' / nl[154]), 64)
    out += arr('pc_m4_grass', grass, 32)
    p = ROOT / 'ACGC-PC-Port' / 'src' / 'data' / 'model' / 'pc_museum4_tex.c_inc'
    with open(p, 'w', newline='\n') as f:
        f.write(out)
    print('wrote', p.name)


if __name__ == '__main__':
    main()
