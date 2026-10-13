"""Export the character textures (villagers, special NPCs, the player and clothing) for an external upscaler.

Writes texture_handoff_chr/:
  source/<group>/<key>.png   original texture decoded with its palette (RGBA)
  manifest.json              one entry per texture: size, target size, what it is, where its data comes from
  README.md                  the brief, and how to bring the results back (import_upscaled_chr.py)

Groups:
  villager      every villager / special NPC: eyes (8 frames), mouths (6 frames), body atlas parts
  player_face   player eyes and mouths: 2 genders x 8 face types (+ bee-sting and decoy versions)
  player_body   player skin, hair, shoes, legs (drawn with the face palette)
  clothing      the 256 shirt / dress patterns (players and villagers wear the same ones)
"""
import json, re, shutil, struct
from pathlib import Path
import numpy as np
from PIL import Image
import native_models as nm

ROOT = Path(__file__).resolve().parent
SRC = ROOT/'ACGC-PC-Port/src/data'
ARC = ROOT/'chr_work/arc'                     # face_boy.bin, tex_boy.bin, pallet_boy.bin (from forest_1st.arc)
OUT = ROOT/'texture_handoff_chr'
UP = 8

def untile(data, w, h):
    idx = np.array(nm.ci_indices(data, 4)); img = np.zeros((h, w), int); o = 0
    for ty in range(0, h, 8):
        for tx in range(0, w, 8):
            bw = min(8, w-tx); img[ty:ty+8, tx:tx+8] = idx[o:o+64].reshape(8, 8)[:min(8, h-ty), :bw]; o += 64
    return img

def pal16(b):
    return [nm.rgb5a3(struct.unpack_from('>H', b, i*2)[0]) for i in range(len(b)//2)]

def uses():
    """Every (group, key, data, w, h, palette bytes, info) the game draws. One key can appear with several palettes
    (player faces and body parts follow the face type and the tan); the first one is the exported picture."""
    # ---------------- villagers and special NPCs ----------------
    for mdl in sorted((SRC/'npc/model/mdl').glob('*.c')):
        species = mdl.stem.rsplit('_', 1)[0]
        text = mdl.read_text()
        tmem = sorted({(int(o, 16), int(w), int(h)) for o, w, h in
                       re.findall(r'anime_4_txt \+ 0x([0-9A-Fa-f]+), G_IM_FMT_CI, (\d+), (\d+)', text)})
        for tex in sorted((SRC/'npc/model/tex').glob(f'{species}_*.c')):
            v = tex.stem
            if f'{v}_pal' not in nm.sym: continue
            pal = nm.blob(f'{v}_pal')
            for part in ('eye', 'mouth'):
                for n in range(1, 9):
                    s = f'{v}_{part}{n}_TA_tex_txt'
                    if s not in nm.sym: continue
                    d = nm.blob(s); w, h = (32, 16) if len(d) == 0x100 else (32, 32)
                    yield 'villager', f'{v}_{part}{n}', d, w, h, pal, dict(villager=v, kind=f'{part} frame {n}')
            if f'{v}_tmem_txt' in nm.sym:
                d = nm.blob(f'{v}_tmem_txt')
                for o, w, h in tmem:
                    if o+w*h//2 > len(d): continue
                    yield 'villager', f'{v}_body_{o:03x}', d[o:o+w*h//2], w, h, pal, dict(villager=v, kind='body parts atlas')

    # ---------------- player faces: base palette and the 7 tan palettes of each face ----------------
    face = (ARC/'face_boy.bin').read_bytes(); TAIL = 64*0xE20
    def face_pals(sex, ft, swell, decoy):
        i = decoy*32+ft+sex*8+swell*16; base = i*0xE20
        out = [face[base+0xE00:base+0xE20]]
        if not decoy:
            idx = ft*8+sex*64+swell*128
            out += [face[TAIL+(idx+r)*0x20:TAIL+(idx+r+1)*0x20] for r in range(1, 8)]
        return out
    for sex, sname in ((0, 'boy'), (1, 'girl')):
        for ft in range(8):
            for swell in (0, 1):
                for decoy in (0, 1):
                    i = decoy*32+ft+sex*8+swell*16; base = i*0xE20
                    tag = f'{sname}_face{ft+1}' + ('_sting' if swell else '') + ('_decoy' if decoy else '')
                    for k in range(14):
                        d = face[base+k*0x100:base+(k+1)*0x100]
                        part = f'eye{k+1}' if k < 8 else f'mouth{k-7}'
                        for pal in face_pals(sex, ft, swell, decoy):
                            yield 'player_face', f'{tag}_{part}', d, 32, 16, pal, dict(kind=f'player {sname} face type {ft+1} {part}')

    # ---------------- player body: drawn with every face palette of that gender ----------------
    for sex, pre, mfile in ((0, 'boy_1', 'boy_model.c'), (1, 'grl_1', 'girl_model.c')):
        pals = [p for ft in range(8) for sw in (0, 1) for dc in (0, 1) for p in face_pals(sex, ft, sw, dc)]
        for w, h, name in sorted(set(re.findall(rf'G_IM_SIZ_4b, (\d+), (\d+), ({pre}_\w+_tex_txt)\)', (SRC/'model'/mfile).read_text()))):
            for pal in pals:
                yield 'player_body', name, nm.blob(name), int(w), int(h), pal, dict(kind=f'player {"boy" if sex == 0 else "girl"} body part (skin-tone palette)')

    # ---------------- clothing ----------------
    tex = (ARC/'tex_boy.bin').read_bytes(); pals = (ARC/'pallet_boy.bin').read_bytes()
    for i in range(len(tex)//0x200):
        yield 'clothing', f'shirt_{i:03d}', tex[i*0x200:(i+1)*0x200], 32, 32, pals[i*0x20:(i+1)*0x20],             dict(kind='shirt / dress pattern (body, sleeves and back share this 32x32 sheet)')

if __name__ == '__main__':
    shutil.rmtree(OUT, ignore_errors=True)
    for g in ('villager', 'player_face', 'player_body', 'clothing'): (OUT/'source'/g).mkdir(parents=True)
    manifest = {}; by_data = {}
    for group, key, d, w, h, pal, info in uses():
        dk = (group, d)
        if dk in by_data and by_data[dk] != key: continue          # identical picture already exported under another name
        by_data[dk] = key
        if key in manifest: manifest[key]['palettes'] += 1; continue
        img = untile(d, w, h)
        Image.fromarray(np.array(pal16(pal), np.uint8)[img]).save(OUT/'source'/group/f'{key}.png')
        manifest[key] = dict(group=group, key=key, size=[w, h], target_size=[w*UP, h*UP], palettes=1, **info)
    (OUT/'manifest.json').write_text(json.dumps(list(manifest.values()), indent=1))
    from collections import Counter
    print(Counter(m['group'] for m in manifest.values()))
