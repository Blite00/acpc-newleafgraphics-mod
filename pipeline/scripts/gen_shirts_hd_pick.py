"""Player shirts, step 2 (after gen_shirts_hd.py): Real-ESRGAN keeps organic art but smears grid patterns (checks,
stripes, text). Where the ESR shirt no longer downsamples to the GameCube original (mean error > 6), use a crisp 4x
nearest with a light blur instead (gen_shirts_hd.pick). Rewrites texture_pack/gc_shirts_hd."""
import importlib.util, sys
from pathlib import Path
from PIL import Image

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from install_apple import dds_rgba

spec = importlib.util.spec_from_file_location('gen_shirts_hd', ROOT / 'gen_shirts_hd.py')
g = importlib.util.module_from_spec(spec)
spec.loader.exec_module(g)


def main():
    crisp = 0
    for i, name, im in g.shirts():
        hd = Image.open(g.W / f'hd_{i:03d}.png')
        r, how = g.pick(i, im, hd, 6.0)
        crisp += how == 'crisp'
        r.save(g.W / f'final_{i:03d}.png')
        (g.OUT / f'{name}.dds').write_bytes(dds_rgba(r))
    print(crisp, 'shirts use the crisp upscale')


if __name__ == '__main__':
    main()
