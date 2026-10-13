"""New Leaf dug-hole textures in place of the GameCube hole texture (texture pack, reversible).

The GC hole (obj_hole_tex, 32x32 CI4) is one texture drawn with two palettes: obj_g_hole_pal on soil/grass and
obj_b_hole_pal on the beach. New Leaf has a matching pair in the fg_bush atlas: fg_hole_soil and fg_hole_sand
(soft-edged ~27 px decals). Each is cut from the atlas, padded to the GC hole's footprint (the GC quad is 36 world
units wide, the New Leaf one 39.6) and written as a 128x128 RGBA DDS keyed to the matching texture+palette hash.
Disable by moving texture_pack/3ds_holes out of texture_pack.
"""
from pathlib import Path
from PIL import Image
import native_models as nm
from install_apple import xxh, dds_rgba

ROOT = Path(__file__).resolve().parent
OUT = ROOT.parent/'texture_pack'/'3ds_holes'
ATLAS = ROOT/'tree_source/season00/fg_bush.png'
SIZE = 128
GC_W, NL_W = 36.0, 26.8581886*12243/83.0161/100   # world units: GC quad 3600, NL quad (donor scale, /100)
# atlas UV boxes from fg_hole_soil.json / fg_hole_sand.json (v up)
BOXES = {'obj_g_hole_pal': (0.771101, 0.378286, 0.984978, 0.488902),
         'obj_b_hole_pal': (0.771101, 0.128286, 0.984978, 0.238902)}


def decal(box):
    atlas = Image.open(ATLAS).convert('RGBA'); aw, ah = atlas.size
    u0, v0, u1, v1 = box
    crop = atlas.crop((round(u0*aw), round((1-v1)*ah), round(u1*aw), round((1-v0)*ah)))
    # Fit the whole decal inside the GC quad. (The old version scaled it up to the New Leaf world size and centre-cropped it,
    # which sliced the round hole into a hexagon.)
    import numpy as np
    a = np.asarray(crop).astype(float); al = a[..., 3:4]/255
    pm = Image.fromarray(np.dstack([a[..., :3]*al, a[..., 3:4]]).astype(np.uint8), 'RGBA')   # resize premultiplied: no dark rim
    r = np.asarray(pm.resize((SIZE, SIZE), Image.BICUBIC)).astype(float); ra = r[..., 3:4]/255
    out = Image.fromarray(np.dstack([np.clip(r[..., :3]/np.maximum(ra, 1e-3), 0, 255), r[..., 3:4]]).astype(np.uint8), 'RGBA')
    return out


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    tex = nm.blob('obj_hole_tex')
    idx = nm.ci_indices(tex, 4)
    for pal_name, box in BOXES.items():
        pal = nm.blob(pal_name)
        ph = xxh(pal[min(idx)*2:(max(idx)+1)*2])
        name = f'tex1_32x32_{xxh(tex)}_{ph}_8.dds'
        im = decal(box)
        (OUT/name).write_bytes(dds_rgba(im))
        im.save(ROOT/f'screens/tools/hole_{pal_name}.png')
        print(pal_name, name, im.size)


if __name__ == '__main__':
    main()
