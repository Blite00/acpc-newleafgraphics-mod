"""Ivory piano variant: the New Leaf ebony remake piano's base texture with its black body recoloured ivory
(furn_work/remake/rmk_oth_piano_b/base_90.png, used by sum_liccapiano through the registry's variants)."""
import sys
from pathlib import Path
import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
import furn_color


def main():
    src = Path(furn_color.nl_dir('rmk_oth_piano_b')) / 'base_00.png'
    a = np.array(Image.open(src).convert('RGBA'))
    L = a[..., :3].astype(float).mean(2)
    yy, xx = np.mgrid[:32, :32]
    m = (L < 20) & ~((yy >= 20) & (xx < 28))     # keep the keyboard strip
    a[m, :3] = (238, 232, 216)
    out = ROOT / 'furn_work' / 'remake' / 'rmk_oth_piano_b'
    out.mkdir(parents=True, exist_ok=True)
    Image.fromarray(a).save(out / 'base_90.png')
    print('ivory piano texels', int(m.sum()))


if __name__ == '__main__':
    main()
