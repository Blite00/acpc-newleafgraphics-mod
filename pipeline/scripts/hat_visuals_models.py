"""Ground model and shelf placement for the New Leaf hat items (used by generate_nl_hat_visuals.py)."""
import json
from collections import defaultdict
from pathlib import Path
import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parent
SRC = ROOT/'hat_source'
FG = ROOT/'tree_source/outside'
GSCALE = 12243/83.0161          # donor-to-world scale shared with generate_ground_items.py
K = 100.0                       # pc_nl_hat_dl head space


def rgba8(im):
    w, h = im.size; data = bytearray()
    for ty in range(0, h, 4):
        for tx in range(0, w, 4):
            tile = [im.getpixel((tx+x, ty+y)) for y in range(4) for x in range(4)]
            data.extend(c for r, g, b, a in tile for c in (a, r)); data.extend(c for r, g, b, a in tile for c in (g, b))
    return data


def ground_model():
    """Dropped / lost-and-found / hand-over look: New Leaf's own dropped-hat model fg_cap_out (FgItemOutside), one
    shared model for every hat as in New Leaf. obj_item_hatT_mat_model = render state + texture,
    obj_item_hatT_gfx_model = geometry in GC ground-item units, lit through normals like the native item cards."""
    meshes = json.load(open(FG/'fg_cap_out.json'))['meshes']
    vs = [v for m in meshes for v in m['vertices']]
    atlas = Image.open(FG/'t_fg_outside.png').convert('RGBA'); aw, ah = atlas.size
    rows = [(1-v['uv'][1])*ah for v in vs]
    r0 = int(np.floor(min(rows)/4)*4); r1 = int(np.ceil(max(rows)/4)*4)
    crop = atlas.crop((0, r0, aw, r1))
    acc = defaultdict(lambda: np.zeros(3))
    for i in range(0, len(vs), 3):
        a, b, c = [np.array(v['position']) for v in vs[i:i+3]]
        n = np.cross(b-a, c-a)
        for p in (a, b, c): acc[tuple(np.round(p, 4))] += n
    out = ['static u8 pc_hat_ground_tex[] ATTRIBUTE_ALIGN(32) = {']
    data = rgba8(crop); out += [','.join(map(str, data[i:i+32]))+',' for i in range(0, len(data), 32)]; out.append('};')
    out.append('static Vtx pc_hat_ground_v[] ATTRIBUTE_ALIGN(32) = {')
    for v, row in zip(vs, rows):
        x, y, z = (int(round(c*GSCALE)) for c in v['position'])
        n = acc[tuple(np.round(np.array(v['position']), 4))]; n = n/max(np.linalg.norm(n), 1e-9)
        out.append('{{{%d,%d,%d},0,{%d,%d},{%s,255}}},' % (x, y, z, round(v['uv'][0]*aw*32), round((row-r0)*32),
                   ','.join(str(int(round(c*120)) & 255) for c in n)))
    out.append('};')
    out += ['Gfx obj_item_hatT_mat_model[] = {',
            '    gsDPPipeSync(),',
            '    gsSPTexture(0, 0, 0, G_TX_RENDERTILE, G_ON),',
            '    gsDPSetRenderMode(G_RM_FOG_SHADE_A, G_RM_AA_ZB_OPA_SURF2),',
            '    gsDPSetCombineLERP(TEXEL0, 0, SHADE, 0, 0, 0, 0, TEXEL0, PRIMITIVE, 0, COMBINED, 0, 0, 0, 0, COMBINED),',
            f'    gsDPSetTextureImage_Dolphin(G_IM_FMT_RGBA, G_IM_SIZ_32b, {crop.size[0]}, {crop.size[1]}, pc_hat_ground_tex),',
            '    gsDPSetTile_Dolphin(G_DOLPHIN_TLUT_DEFAULT_MODE, 0, 0, GX_MIRROR, GX_CLAMP, 0, 0),',
            '    gsDPSetPrimColor(0, 128, 255, 255, 255, 255),',
            '    gsSPLoadGeometryMode(G_ZBUFFER | G_SHADE | G_CULL_BACK | G_FOG | G_LIGHTING | G_SHADING_SMOOTH | G_DECAL_LEQUAL),',
            '    gsSPEndDisplayList(),', '};', 'Gfx obj_item_hatT_gfx_model[] = {']
    for base in range(0, len(vs), 30):
        k = min(30, len(vs)-base); out.append(f'    gsSPVertex(&pc_hat_ground_v[{base}], {k}, 0),')
        out += [f'    gsSP1Triangle({j}, {j+1}, {j+2}, 0),' for j in range(0, k, 3)]
    out += ['    gsSPEndDisplayList(),', '};']
    return out


def dl_bbox(n):
    """bounds of what pc_nl_hat_dl draws (same mesh filter as generate_nl_hats.py), head space x100"""
    d = json.load(open(SRC/n/f'{n}.json'))
    P = []
    for m in d['meshes']:
        if m['coordinator']['projection'] != 0 or not m['texture']: continue
        tp = SRC/n/f"{m['texture']}.png"
        if not tp.exists(): continue
        w, h = Image.open(tp).size
        if w % 4 or h % 4 or w > 256 or h > 256: continue
        P += [v['position'] for v in m['vertices']]
    P = np.array(P)*K
    return P.min(0), P.max(0)


# New Leaf's shop hat stand (Ftr/Mannequin/mq_stndB, the wooden ball head on a foot, y up, 21 units tall), shrunk
# by STAND_SCALE so the ball fills a hat the way a player head does. Head space maps onto it 1:1: x (up) -> y lowered
# by STAND_UP, side y -> -x, z (front) pushed forward by STAND_FRONT (fitted so no cap's crown is hidden in the ball).
STAND = ROOT/'mannequin_source/mq_stndB'
STAND_SCALE = 1.0
STAND_UP = -0.5
STAND_FRONT = 1.0
BALL_C = np.array([0, 12.21, 0])*STAND_SCALE   # ball centre / radius of the scaled stand
BALL_R = 10.77*STAND_SCALE
WORLD = 1.7       # shelf units per display-list unit (head space x100): the ball is ~2400 wide like a shop item, a cap ~3600
MAX_W = 3800.0    # wider hats (sombrero, straw hat) shrink to this width so they stay inside their 4000-wide shelf unit
ORNAMENTS = ('feather_', 'hair_', 'hairpin_', 'glow_', 'halo', 'ribbon_')   # worn beside / above the head (pc_nl_hat_fullhair)    # wider hats (sombrero, straw hat) shrink to this width on the shelf


def on_stand(P):
    """head-space points (NL units) -> stand space (NL units)"""
    return np.stack([-P[:, 1], P[:, 0]-STAND_UP, P[:, 2]+STAND_FRONT], 1)


def shelf_fit(names):
    """per hat: (pull, shrink). Ornaments that sit beside a player head (hairpins, feathers) would float beside the
    smaller ball, so they are pulled in about the ball centre until they touch it; very wide hats shrink as a whole."""
    rows = []
    for short in names:
        lo, hi = dl_bbox('cap_'+short)
        d = json.load(open(SRC/f'cap_{short}'/f'cap_{short}.json'))
        P = on_stand(np.array([v['position'] for m in d['meshes'] if m['coordinator']['projection'] == 0
                               for v in m['vertices']]))
        # ornaments: pull the piece's middle in to just outside the ball (halo stays a little above it)
        mid = np.linalg.norm(P.mean(0)-BALL_C)
        goal = BALL_R*(1.25 if short == 'halo' else 1.05)
        pull = float(min(1.0, goal/mid)) if short.startswith(ORNAMENTS) else 1.0
        width = max(hi[1]-lo[1], hi[2]-lo[2])*pull*WORLD
        rows.append((pull, float(min(1.0, MAX_W/width))))
    return rows


def stand_code():
    from collections import defaultdict
    d = json.load(open(STAND/'mq_stndB.json'))
    im = Image.open(STAND/'mq_stndB.png').convert('RGBA')
    im.putalpha(255)                       # texture alpha is a gloss mask
    tw, th = im.size
    out = ['static u8 pc_hat_stand_tex[] ATTRIBUTE_ALIGN(32) = {']
    data = rgba8(im); out += [','.join(map(str, data[i:i+32]))+',' for i in range(0, len(data), 32)]; out.append('};')
    vs = [v for m in d['meshes'] for v in m['vertices']]
    acc = defaultdict(lambda: np.zeros(3))
    for i in range(0, len(vs), 3):
        a, b, c = [np.array(v['position']) for v in vs[i:i+3]]
        n = np.cross(b-a, c-a)
        for q in (a, b, c): acc[tuple(np.round(q, 4))] += n
    out.append('static Vtx pc_hat_stand_v[] ATTRIBUTE_ALIGN(32) = {')
    for v in vs:
        x, y, z = (int(round(c*K*STAND_SCALE)) for c in v['position'])
        n = acc[tuple(np.round(np.array(v['position']), 4))]; n = n/max(np.linalg.norm(n), 1e-9)
        out.append('{{{%d,%d,%d},0,{%d,%d},{%s,255}}},' % (x, y, z, round(v['uv'][0]*tw*32), round((1-v['uv'][1])*th*32),
                   ','.join(str(int(round(c*120)) & 255) for c in n)))
    out += ['};', 'static Gfx pc_hat_stand_dl[] = {', '    gsDPPipeSync(),', '    gsSPTexture(0, 0, 0, G_TX_RENDERTILE, G_ON),',
            '    gsDPSetPrimColor(0, 128, 255, 255, 255, 255),',
            '    gsDPSetCombineLERP(TEXEL0, 0, SHADE, 0, 0, 0, 0, TEXEL0, PRIMITIVE, 0, COMBINED, 0, 0, 0, 0, COMBINED),',
            '    gsDPSetRenderMode(G_RM_FOG_SHADE_A, G_RM_AA_ZB_OPA_SURF2),',
            '    gsSPLoadGeometryMode(G_ZBUFFER | G_SHADE | G_CULL_BACK | G_FOG | G_LIGHTING | G_SHADING_SMOOTH),',
            f'    gsDPSetTextureImage_Dolphin(G_IM_FMT_RGBA, G_IM_SIZ_32b, {tw}, {th}, pc_hat_stand_tex),',
            '    gsDPSetTile_Dolphin(G_DOLPHIN_TLUT_DEFAULT_MODE, 0, 0, GX_REPEAT, GX_REPEAT, 0, 0),']
    for base in range(0, len(vs), 30):
        k = min(30, len(vs)-base); out.append(f'    gsSPVertex(&pc_hat_stand_v[{base}], {k}, 0),')
        out += [f'    gsSP1Triangle({j}, {j+1}, {j+2}, 0),' for j in range(0, k, 3)]
    out += ['    gsSPEndDisplayList(),', '};']
    return out


def shelf_code(names):
    """pc_hat_item_draw(game, i): New Leaf's wooden head stand with hat i on it, on the shelf spot whose matrix the
    caller set (pos/angle/scale applied, Y up) with lights already set. PC_HAT_STAND=0 draws the hat alone."""
    c = BALL_C*K
    out = stand_code() + ['',
           'static const float pc_hat_shelf_fit[][2] = {   /* pull toward the ball centre, whole-model shrink */']
    out += ['    {%.4ff, %.4ff},' % r for r in shelf_fit(names)]
    out += ['};', '',
            'void pc_hat_item_draw(GAME* game, int hat_idx) {',
            '    extern Gfx* pc_nl_hat_dl[];',
            '    static int stand = -1;',
            '    const float* f;',
            '    GRAPH* graph = game->graph;',
            f'    if (hat_idx < 0 || hat_idx >= {len(names)}) return;',
            '    if (stand < 0) { const char* e = getenv("PC_HAT_STAND"); stand = !(e != NULL && e[0] == \'0\'); }',
            '    f = pc_hat_shelf_fit[hat_idx];',
            '    OPEN_DISP(graph);',
            f'    Matrix_scale({WORLD}f * f[1], {WORLD}f * f[1], {WORLD}f * f[1], MTX_MULT);',
            '    if (stand) {',
            '        gSPMatrix(NEXT_POLY_OPA_DISP, _Matrix_to_Mtx_new(graph), G_MTX_NOPUSH | G_MTX_LOAD | G_MTX_MODELVIEW);',
            '        gSPDisplayList(NEXT_POLY_OPA_DISP, pc_hat_stand_dl);',
            '    }',
            f'    Matrix_translate(0.0f, {c[1]:.1f}f, 0.0f, MTX_MULT);   /* scale ornaments in about the ball centre */',
            '    Matrix_scale(f[0], f[0], f[0], MTX_MULT);',
            f'    Matrix_translate(0.0f, {-c[1]-STAND_UP*K:.1f}f, {STAND_FRONT*K:.1f}f, MTX_MULT);',
            '    Matrix_RotateZ(0x4000, MTX_MULT);   /* head +x (up) -> world +y */',
            '    gSPMatrix(NEXT_POLY_OPA_DISP, _Matrix_to_Mtx_new(graph), G_MTX_NOPUSH | G_MTX_LOAD | G_MTX_MODELVIEW);',
            '    gSPDisplayList(NEXT_POLY_OPA_DISP, pc_nl_hat_dl[hat_idx]);',
            '    CLOSE_DISP(graph);',
            '}']
    return out


def write_visuals(path, names, texs=None, pals=None):
    """Only the shop-shelf draw is generated here now; the inventory icons and the ground card (New Leaf's tinted cap
    icon) live in generate_nl_hat_items.py / pc_nl_hat_items.c, per the user's choice on 2026-10-06."""
    out = ['/* Generated by generate_nl_hat_visuals.py: New Leaf hat items on the shop shelf (pc_hat_item_draw). */',
           '#include "pc_platform.h"', '#include "PR/mbi.h"', '#include "libultra/libultra.h"',
           '#include "libforest/gbi_extensions.h"', '#include "game.h"', '#include "graph.h"', '#include "sys_matrix.h"',
           '#include <stdlib.h>', '']
    out += shelf_code(names)
    Path(path).write_text(chr(10).join(out)+chr(10))

