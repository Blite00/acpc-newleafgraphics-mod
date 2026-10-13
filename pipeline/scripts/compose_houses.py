"""Rebuild GC house textures from cut-up New Leaf material crops.

Per native texel we know (palette colour, role from the native triangle normal / door region).
Roof texels get a New Leaf roof-tile crop, light wall texels a plaster crop, brown trim a wood
crop and the door region the donor door image. GC shading is kept by modulating each crop with the
native colour's brightness relative to its role mean; GC outlines and cut-outs are kept as they are.
"""
import sys, json, colorsys
from pathlib import Path
import numpy as np
from PIL import Image
import native_models as nm
import texture_bake as tb

ROOT = Path(__file__).resolve().parent
OUT = ROOT/'texture_pack_staging/3ds_buildings'
H = ROOT/'house_source/npc_house'
D = ROOT/'house_source/door/hobj_door/Textures'
F = 4

def lum(a): return a @ np.array([0.299, 0.587, 0.114])

# Curated crop windows (x, y, w, h) in each donor atlas, found by looking at them.
ROOF_RECT = {0: (0, 16, 64, 32), 1: (20, 4, 64, 40), 2: (4, 4, 50, 50), 3: (16, 4, 64, 56), 4: (0, 0, 64, 64), 5: (30, 4, 64, 40)}
WALL_RECT = {0: (0, 0, 28, 100), 1: (46, 84, 10, 20), 2: (46, 84, 10, 20), 3: (0, 64, 34, 50), 4: (46, 84, 10, 20), 5: (0, 10, 22, 100)}
WOOD_RECT = (8, 12, 48, 28)

def crop(img, rect):
    x, y, w, h = rect
    return img[y:y+h, x:x+w, :3]

def mean_rgb(p): return p.reshape(-1, 3).mean(0)

class Library:
    """All curated crops with their mean colours."""
    def __init__(self, winter):
        self.roof = []; self.wall = []; self.wood = []
        for s in range(6):
            for vv in range(10):
                season = 'season09' if winter else 'season00'
                rp = H/f'hobj_npchouse_0{s}/Textures/{season}/roof_{s}_{vv:02}_raw.png'
                if not rp.exists(): rp = H/f'hobj_npchouse_0{s}/Textures/season00/roof_{s}_{vv:02}_raw.png'
                wp = H/f'hobj_npchouse_0{s}/Textures/season00/wall_{s}_{vv:02}_raw.png'
                r = np.asarray(Image.open(rp).convert('RGB')).astype(float); w = np.asarray(Image.open(wp).convert('RGB')).astype(float)
                self.roof.append((s, vv, crop(r, ROOF_RECT[s]))); self.wall.append((s, vv, crop(w, WALL_RECT[s])))
        for d in range(22):
            im = np.asarray(Image.open(D/f'hobj_door_{d:02}_a_raw.png').convert('RGB')).astype(float)
            self.wood.append((d, 0, crop(im, WOOD_RECT)))

def pick(cands, target, prefer=None):
    best = None
    for s, vv, p in cands:
        if prefer is not None and s not in prefer: continue
        a = mean_rgb(p); a = a/max(a.sum(), 1); b = target/max(target.sum(), 1)
        d = np.linalg.norm(a-b)
        if best is None or d < best[0]: best = (d, p)
    return best[1]

class Materials:
    def __init__(self, lib, roof_target, wall_target, wood_target, roof_prefer, wall_prefer, door_idx):
        self.roof = pick(lib.roof, roof_target, roof_prefer)
        self.wall = pick(lib.wall, wall_target, wall_prefer)
        self.wood = pick(lib.wood, wood_target)
        self.door = None  # chosen later from the native door colour

def tile_sample(patch, X, Y, period):
    ph, pw = patch.shape[:2]
    u = (X/period) % 1.0; v = (Y/period) % 1.0
    xs = (u*pw).astype(int) % pw; ys = (v*ph).astype(int) % ph
    return patch[ys, xs]

def roles_for(house, season, texsym, w, h):
    """role map: 0 none, 1 roof, 2 wall/other-body, 3 door (rect)"""
    dls = nm.parse_model_file(ROOT/'ACGC-PC-Port/src/data/model/obj_s_house1.c')
    tris = []
    for part in ('t1', 't2', 't3', 't4'):
        tris += [t for t in dls.get(f'obj_{season}_house{house}_{part}_model', []) if t[0] == texsym]
    role = np.zeros((h*F, w*F), np.uint8)
    tex = tb.native_texels(tris, w, h, F) if tris else None
    if tex is not None:
        X, Y, P, N = tex
        role[Y, X] = np.where(N[:, 1] > 0.35, 1, 2)
    door = []
    for t in dls.get(f'obj_{season}_house{house}_door_model', []):
        if t[0] == texsym: door.append(t)
    rect = None
    if door:
        uv = np.array([(v[3], v[4]) for t in door for v in t[5]])
        rect = (uv[:, 0].min(), uv[:, 1].min(), uv[:, 0].max(), uv[:, 1].max())
    return role, rect

def compose(native_img, w, h, role, door_rect, lib, roof_pref, wall_pref, door_idx, strength=1.0):
    nat = np.asarray(native_img).astype(float)           # (h,w,4)
    big = np.repeat(np.repeat(nat, F, 0), F, 1)            # nearest at F x
    rgb = big[..., :3].copy(); alpha = big[..., 3]
    L = lum(big[..., :3])
    out = rgb.copy()
    yy, xx = np.mgrid[0:h*F, 0:w*F]
    # roles
    roof = (role == 1) & (alpha > 20)
    body = (role == 2) & (alpha > 20)
    hsv = np.array([colorsys.rgb_to_hsv(*(c/255)) for c in big.reshape(-1, 4)[:, :3][::1].astype(float)[:1]]) if False else None
    # light wall vs wood trim vs outline, from native colour
    r, g, b = rgb[..., 0]/255, rgb[..., 1]/255, rgb[..., 2]/255
    mx = np.maximum(np.maximum(r, g), b); mn = np.minimum(np.minimum(r, g), b)
    sat = (mx-mn)/np.maximum(mx, 1e-6)
    light = body & (mx > 0.78) & (sat < 0.35)
    dark = (L < 55)
    wood = body & ~light & ~dark
    def cmean(mask):
        return rgb[mask].mean(0) if mask.any() else np.array([128.0, 128, 128])
    mats = Materials(lib, cmean(roof & ~dark), cmean(light), cmean(wood), roof_pref, wall_pref, door_idx)
    def paint(mask, patch, period, ref):
        if not mask.any(): return
        s = tile_sample(patch, xx[mask], yy[mask], period)
        # keep GC brightness: normalise the crop to the native class luminance, then apply GC shading
        s = s/max(lum(patch.reshape(-1, 3)).mean(), 1.0)*ref
        mod = np.clip(L[mask]/max(ref, 1.0), 0.45, 1.4)[:, None]**0.9
        out[mask] = np.clip(s*mod*strength+rgb[mask]*(1-strength), 0, 255)
    if roof.any(): paint(roof & ~dark, mats.roof, 48*F/2, L[roof & ~dark].mean())
    if light.any(): paint(light, mats.wall, 40*F/2, L[light].mean())
    if wood.any(): paint(wood, mats.wood, 40*F/2, L[wood].mean())
    if door_rect is not None:
        x0, y0, x1, y1 = door_rect
        dx0, dx1, dy0, dy1 = int(x0*F), int(x1*F), int(y0*F), int(y1*F)
        native_door = rgb[max(dy0, 0):dy1, max(dx0, 0):dx1].reshape(-1, 3)
        al = alpha[max(dy0, 0):dy1, max(dx0, 0):dx1].reshape(-1) > 20
        target = native_door[al].mean(0) if al.any() else np.array([140.0, 90, 60])
        best = None
        for d in range(22):
            im = np.asarray(Image.open(D/f'hobj_door_{d:02}_a_raw.png').convert('RGB')).astype(float)
            dist = np.linalg.norm(im.reshape(-1, 3).mean(0)-target)
            if best is None or dist < best[0]: best = (dist, im)
        mats.door = best[1]
        X0, X1 = int(x0*F), int(x1*F); Y0, Y1 = int(y0*F), int(y1*F)
        X0 = max(X0, 0); Y0 = max(Y0, 0); X1 = min(X1, w*F); Y1 = min(Y1, h*F)
        if X1 > X0 and Y1 > Y0:
            d = Image.fromarray(mats.door.astype(np.uint8)).resize((X1-X0, Y1-Y0), Image.LANCZOS)
            sub = np.asarray(d).astype(float)
            m = alpha[Y0:Y1, X0:X1] > 20
            out[Y0:Y1, X0:X1][m] = sub[m]
    res = np.dstack([np.clip(out, 0, 255), alpha])
    return Image.fromarray(res.astype(np.uint8), 'RGBA')

ROOF_PREF = {1: (1, 5), 2: (3, 5), 3: (1, 5), 4: (3, 0), 5: (3, 5)}
WALL_PREF = {1: (1, 2, 4), 2: (3, 5), 3: (3, 5), 4: (0, 3), 5: (1, 2, 4)}
PAL_VARIANT = {'a': 0, 'b': 2, 'c': 4, 'd': 6, 'e': 8}
DOOR_IDX = {1: 0, 2: 5, 3: 3, 4: 8, 5: 13}

def run(houses):
    OUT.mkdir(parents=True, exist_ok=True)
    report = []
    libs = {False: Library(False), True: Library(True)}
    for house in houses:
        for season, winter in (('s', False), ('w', True)):
            lib = libs[winter]
            dls = nm.parse_model_file(ROOT/'ACGC-PC-Port/src/data/model/obj_s_house1.c')
            texes = {}
            for part in ('t1', 't2', 't3', 't4'):
                for t in dls.get(f'obj_{season}_house{house}_{part}_model', []): texes[t[0]] = t
            for texsym, t in texes.items():
                if texsym.endswith('t4_tex_txt') or '_name_' in texsym: continue
                fmt, bits, w, h = t[1], t[2], t[3], t[4]
                data = nm.blob(texsym)
                role, rect = roles_for(house, season, texsym, w, h)
                for letter, variant in PAL_VARIANT.items():
                    pal_sym = f'obj_{season}_house{house}_{letter}_pal'
                    img = nm.decode_ci(data, w, h, nm.palette(pal_sym), bits)
                    res = compose(img, w, h, role, rect, lib, ROOF_PREF[house], WALL_PREF[house], DOOR_IDX[house]+('abcde'.index(letter)))
                    name = tb.pack_name(texsym, fmt, bits, w, h, pal_sym)
                    (OUT/name).write_bytes(tb.dds_rgba(res))
                    if letter == 'a': res.save(ROOT/f'house_source/comp_{texsym}.png')
                    report.append({'house': house, 'texture': texsym, 'palette': pal_sym, 'file': name})
    print(len(report), 'composed replacements')

if __name__ == '__main__':
    run([int(a) for a in sys.argv[1:]] or [1, 2, 3, 4, 5])
