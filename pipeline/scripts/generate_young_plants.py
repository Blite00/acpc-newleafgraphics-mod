"""Original 3DS saplings, young trees, pines, palms, stumps and withered saplings.

Render-only adapter for the existing native town draw routes and tree effects.
Native item IDs, growth, collision, shadows, fruit overlays and gameplay stay
in charge. Every donor stage uses the same donor-to-world scale as the
accepted mature hardwood, so the original 3DS size progression is preserved.
"""
import json, re, struct
from pathlib import Path
from PIL import Image
from support_closure import support_closure, host_ground_support_depth

ROOT = Path(__file__).resolve().parent
SRC = ROOT/'tree_source'
SCALE = 12243/83.0161  # same as generate_tree_world.py / generate_cedar_world.py

def mesh(folder, name):
    return json.loads((SRC/folder/(name+'.json')).read_text())['meshes'][0]

# ---- native effect skeleton pivots (actual ROM joint tables) ----
rel = (ROOT/'foresta.rel').read_bytes(); DATA = 0x2dd340
sym = {}
for line in open(ROOT/'ACGC-PC-Port/config/GAFE01_00/foresta/symbols.txt'):
    m = re.match(r'(\w+) = \.data:0x([0-9A-F]+); // type:object size:0x([0-9A-F]+)', line)
    if m: sym[m[1]] = (int(m[2], 16), int(m[3], 16))
def joints(name):
    a, s = sym[name]
    return [struct.unpack_from('>IBBhhh', rel, DATA+a+i*12)[3:] for i in range(s//12)]

FAMILIES = {  # family id, donor letter, native effect name
    'tree':  (0, 'A', 'tree'),
    'cedar': (1, 'B', 'cedar'),
    'palm':  (2, 'C', 'palm'),
}
# Native stage -> donor stage. Native stage 5 hardwood/cedar already exist.
STAGES = {'tree': [1, 2, 3, 4], 'cedar': [1, 2, 3, 4], 'palm': [1, 2, 3, 4, 5]}

def components(vs):
    n = len(vs)//3; parent = list(range(n))
    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]; x = parent[x]
        return x
    seen = {}
    for i in range(n):
        for v in vs[3*i:3*i+3]:
            k = tuple(round(c, 3) for c in v['position'])
            if k in seen: parent[find(i)] = find(seen[k])
            else: seen[k] = i
    return [find(i) for i in range(n)]

def split_standing(vs):
    """Trunk = source pieces that start at or below the ground plane (bark,
    buried roots); every other connected source piece is canopy."""
    comp = components(vs); low = {}
    for i, c in enumerate(comp):
        y = min(v['position'][1] for v in vs[3*i:3*i+3])
        low[c] = min(low.get(c, 1e9), y)
    trunk, leaf = [], []
    for i, c in enumerate(comp):
        (trunk if low[c] < 2.0 else leaf).extend(vs[3*i:3*i+3])
    return leaf, trunk

def classify_felled(felled, leaf, trunk):
    """Felled bind-pose triangles inherit the class of the nearest standing
    triangle with the same atlas region (source geometry, not guessed order)."""
    def cen(tri, k): return [sum(v[k][j] for v in tri)/3 for j in range(len(tri[0][k]))]
    ref = [(cen(src[i:i+3], 'position'), cen(src[i:i+3], 'uv'), cls)
           for cls, src in (('leaf', leaf), ('trunk', trunk)) for i in range(0, len(src), 3)]
    out = {'leaf': [], 'trunk': []}
    for i in range(0, len(felled), 3):
        tri = felled[i:i+3]; p, u = cen(tri, 'position'), cen(tri, 'uv')
        best = min(ref, key=lambda r: sum((a-b)**2 for a, b in zip(r[0], p)) + 400*sum((a-b)**2 for a, b in zip(r[1], u)))
        out[best[2]].extend(tri)
    return out['leaf'], out['trunk']

support_depth = host_ground_support_depth(ROOT)
lists = []      # (c_name, vertices, pivot)
routes = {}     # (family, native_stage, part) -> c_name
audit = {}

def unblack_stump(vertices):
    """The pine stump's cut face carries RGB 0 (alpha 255) vertex colors, a
    marker for the separate ring overlay; render its own wood-ring UVs lit."""
    out = []
    for v in vertices:
        if v['color'] & 0xffffff == 0:
            v = dict(v); v['color'] = v['color'] | 0xffffff
        out.append(v)
    return out

def add(name, vertices, pivot=None):
    lists.append((name, vertices, pivot)); return name

for fam, (fid, letter, efname) in FAMILIES.items():
    for stage in STAGES[fam]:
        donor = stage-1
        base = f'fg_tree{letter}_{donor}'
        vs = mesh('season08_normals', base)['vertices']
        for s in range(23):
            assert mesh(f'season{s:02}_normals', base)['vertices'] == vs, (base, s)
        tag = f'{fam}{stage}'
        info = {'source': base}
        # Like the mature tree, only the stump's open rear/base rim is closed;
        # leaf cards and branch edges never receive added faces.
        rear = []
        if donor >= 1:
            stump = unblack_stump(mesh('season08_normals', base+'_b')['vertices'])
            rear = support_closure(stump, extra_depth=support_depth/(SCALE*.01))
        if stage <= 2:
            # Native stages 1/2 are single display lists with no tree effect.
            whole = vs + rear
            routes[(fid, stage, 0)] = add(f'pc_yp_{tag}_whole', whole)
            if stage == 2:
                # Native small-tree shake/fall effect (ef_young_tree) uses this
                # copy: same mesh, effect-style fading combiner, caller's mode.
                routes[(fid, stage, 9)] = add(f'pc_yp_{tag}_effect', whole, 'fade')
            info['whole_triangles'] = len(whole)//3
        else:
            leaf, trunk = split_standing(vs)
            assert leaf and trunk, base
            felled = mesh('animations_normals', base+'_t')['vertices']
            fleaf, ftrunk = classify_felled(felled, leaf, trunk)
            trunk = trunk + rear
            routes[(fid, stage, 0)] = add(f'pc_yp_{tag}_leaf', leaf)
            routes[(fid, stage, 1)] = add(f'pc_yp_{tag}_trunk', trunk)
            shake = joints(f'cKF_je_r_ef_s_{efname}{stage}_shake_tbl')
            routes[(fid, stage, 2)] = add(f'pc_yp_{tag}_shake', leaf, (shake[0][1], 0))
            pivots = {}
            for side, part_leaf, part_trunk in (('L', 3, 5), ('R', 4, 6)):
                j = joints(f'cKF_je_r_ef_s_{efname}{stage}_cut{side}_tbl')
                trunk_pivot = j[2][0]; leaf_pivot = j[2][0]+j[3][0]; offset = j[0][0]
                pivots[side] = {'leaf': leaf_pivot, 'trunk': trunk_pivot, 'offset': offset}
                routes[(fid, stage, part_leaf)] = add(f'pc_yp_{tag}_cut{side}_leaf', fleaf, (leaf_pivot, offset))
                routes[(fid, stage, part_trunk)] = add(f'pc_yp_{tag}_cut{side}_trunk', ftrunk, (trunk_pivot, offset))
            info.update(leaf_triangles=len(leaf)//3, trunk_triangles=len(trunk)//3,
                        felled_leaf=len(fleaf)//3, felled_trunk=len(ftrunk)//3,
                        shake_pivot=shake[0][1], cut_pivots=pivots)
        if donor >= 1:
            stump = stump + rear
            routes[(fid, stage, 7)] = add(f'pc_yp_{tag}_stump', stump)
            info['stump_triangles'] = len(stump)//3
        audit[tag] = info
    # Withered sapling.
    dead = mesh('season08_normals', f'fg_tree{letter}_x')['vertices']
    routes[(fid, 1, 8)] = add(f'pc_yp_{fam}_dead', dead)
# Mature cedar/palm stumps (native cedar stump5 was still original).
for fam, letter, stage in (('cedar', 'B', 5), ('palm', 'C', 5)):
    if (FAMILIES[fam][0], stage, 7) in routes: continue
    stump = unblack_stump(mesh('season08_normals', f'fg_tree{letter}_4_b')['vertices'])
    routes[(FAMILIES[fam][0], stage, 7)] = add(f'pc_yp_{fam}{stage}_stump', stump + support_closure(stump, extra_depth=support_depth/(SCALE*.01)))

out = ['/* Generated by generate_young_plants.py from original Season00..22.bcres',
       ' * and FgObjAnim.bcres; donor colors, normals and UVs preserved. */',
       'int g_pc_young_plants = 1;']

# Palm atlases (hardwood/fruit and pine atlases already exist in this TU).
palm_names = []; seen = {}
for season in range(23):
    im = Image.open(SRC/f'season{season:02}_normals/treeC.png').convert('RGBA')
    assert im.size == (128, 256)
    raw = im.tobytes()
    if raw in seen: palm_names.append(seen[raw]); continue
    name = f'pc_palm_season{season:02}_tex'; seen[raw] = name; palm_names.append(name)
    tex = bytearray()
    for ty in range(0, 256, 4):
        for tx in range(0, 128, 4):
            tile = [im.getpixel((tx+x, ty+y)) for y in range(4) for x in range(4)]
            tex.extend(c for r, g, b, a in tile for c in (a, r)); tex.extend(c for r, g, b, a in tile for c in (g, b))
    out += [f'static u8 {name}[] ATTRIBUTE_ALIGN(32) = {{']
    out += [','.join(map(str, tex[i:i+32]))+',' for i in range(0, len(tex), 32)] + ['};']
out += ['static u8* pc_palm_atlases[23]={'+','.join(palm_names)+'};']

def emit(name, vertices, pivot):
    out.append(f'static const PC_TreeSourceLight {name}_light[] = {{')
    for v in vertices:
        n = v['normal']; length = sum(c*c for c in n)**.5
        if length < .5: print("short normal", name, length); n = [0, 1, 0]; length = 1
        color = [(v['color'] >> b) & 255 for b in (16, 8, 0, 24)]
        out.append('{{%s},{%s}},' % (','.join('%.8ff' % (c/length) for c in n), ','.join(map(str, color))))
    out.append('};')
    out.append(f'static Vtx {name}_v[] ATTRIBUTE_ALIGN(32) = {{')
    for v in vertices:
        x, y, z = [round(c*SCALE) for c in v['position']]
        if pivot and pivot != 'fade': x, y = y-pivot[0], -x+pivot[1]
        u, t = v['uv']; u = round(u*128*32); t = round((1-t)*256*32)
        rgba = [(v['color'] >> s) & 255 for s in (16, 8, 0, 24)]
        out.append('{{{%d,%d,%d},1,{%d,%d},{%s}}},' % (x, y, z, u, t, ','.join(map(str, rgba))))
    out.extend(['};', f'static Gfx {name}_dl[] = {{',
        'gsDPPipeSync(),', 'gsSPTexture(0,0,0,G_TX_RENDERTILE,G_ON),', 'gsDPSetTexEdgeAlpha(78),',
        ('gsDPSetCombineLERP(TEXEL0,0,SHADE,0,0,0,0,TEXEL0,PRIMITIVE,0,COMBINED,0,COMBINED,0,PRIM_LOD_FRAC,PRIMITIVE),' if pivot else
         'gsDPSetCombineLERP(TEXEL0,0,SHADE,0,0,0,0,TEXEL0,PRIMITIVE,0,COMBINED,0,0,0,0,COMBINED),'),
        'gsDPSetTextureImage_Dolphin(G_IM_FMT_RGBA,G_IM_SIZ_32b,128,256,pc_tree_preview_tex),',
        'gsDPSetTile_Dolphin(G_DOLPHIN_TLUT_DEFAULT_MODE,0,0,GX_MIRROR,GX_MIRROR,0,0),',
        'gsSPLoadGeometryMode(G_ZBUFFER|G_SHADE|G_FOG|G_SHADING_SMOOTH|G_DECAL_LEQUAL),'])
    if pivot is None: out.append('gsDPSetRenderMode(G_RM_FOG_SHADE_A,G_RM_AA_ZB_TEX_EDGE2),')
    for base in range(0, len(vertices), 30):
        count = min(30, len(vertices)-base)
        out.append(f'gsSPVertex(&{name}_v[{base}],{count},0),')
        idx = list(range(count)); first = (idx+[0]*9)[:9]
        out.append('gsSPNTrianglesInit_5b(%d,%s),' % (count//3, ','.join(map(str, first))))
        for i in range(9, count, 12):
            out.append('gsSPNTriangles_5b(%s),' % ','.join(map(str, (idx[i:i+12]+[0]*12)[:12])))
    out.extend(['gsDPPipeSync(),', 'gsDPSetTexEdgeAlpha(144),',
        'gsSPLoadGeometryMode(G_ZBUFFER|G_SHADE|G_CULL_BACK|G_FOG|G_LIGHTING|G_SHADING_SMOOTH|G_DECAL_LEQUAL),',
        'gsSPEndDisplayList(),', '};'])
    # A second copy lets fruit and nonfruit hardwoods use different atlases
    # within the same frame without rewriting a list already queued.
    out.append(f'static Gfx {name}_alt_dl[ARRAY_COUNT({name}_dl)];')

for name, vertices, pivot in lists: emit(name, vertices, pivot)

keys = sorted(routes)
out += ['typedef struct { short family, stage, part; Gfx* dl; Gfx* alt; Vtx* v; const PC_TreeSourceLight* light; int count; unsigned generation; unsigned alt_ready; } PC_YoungPlantMesh;',
        'static PC_YoungPlantMesh pc_young_plant_meshes[] = {']
counts = {name: len(v) for name, v, _ in lists}
for k in keys:
    n = routes[k]
    out.append('{%d,%d,%d,%s_dl,%s_alt_dl,%s_v,%s_light,%d,0,0},' % (k[0], k[1], k[2], n, n, n, n, counts[n]))
out += ['};', r'''
/* family 0 hardwood, 1 cedar, 2 palm; native stage 1..5; part 0 leaf/whole,
 * 1 trunk, 2 shake, 3/4 felled leaf L/R, 5/6 felled trunk L/R, 7 stump, 8 withered,
 * 9 stage-2 small-tree effect copy. */
Gfx* pc_young_plant_mesh(int family, int stage, int part, int hardwood) {
    int i;
    for(i=0;i<(int)ARRAY_COUNT(pc_young_plant_meshes);++i) {
        PC_YoungPlantMesh* m=&pc_young_plant_meshes[i];
        int season; u8* atlas; Gfx* dl;
        if(m->family!=family || m->stage!=stage || m->part!=part) continue;
        if(m->generation!=pc_tree_light_generation) {
            pc_tree_light_vertices(m->v,m->light,m->count); m->generation=pc_tree_light_generation;
        }
        season=pc_tree_world_season();
        if(family==0) atlas=hardwood ? pc_tree_hardwood_atlases[season] : pc_tree_season_atlases[season];
        else if(family==1) atlas=pc_cedar_atlases[season];
        else atlas=pc_palm_atlases[season];
        dl=m->dl;
        if(family==0 && hardwood) {
            if(!m->alt_ready) { memcpy(m->alt,m->dl,pc_young_plant_list_size(i)); m->alt_ready=1; }
            dl=m->alt;
        }
        dl[4].words.w1=_GBI_RUNTIME_PTR(atlas);
        return dl;
    }
    return NULL;
}
''']
src = '\n'.join(out)+'\n'
size_fn = ['static unsigned pc_young_plant_list_size(int i) {', 'switch(i) {']
for i, k in enumerate(keys):
    size_fn.append(f'case {i}: return sizeof({routes[k]}_dl);')
size_fn += ['}', 'return 0;', '}']
src = src.replace('/* family 0 hardwood', '\n'.join(size_fn)+'\n/* family 0 hardwood', 1)
(ROOT/'ACGC-PC-Port/pc/src/pc_young_plants.c_inc').write_text(src)

# ---- native draw-route table: exact shape list -> donor part ----
shape_routes = []
for season in ('s', 'w', 'f'):  # f = native cherry-blossom week lists
    for st in (1, 2):
        shape_routes += [(f'obj_{season}_tree{st}T_gfx_model', 0, st, 0), (f'obj_{season}_cedar{st}T_gfx_model', 1, st, 0),
                         (f'obj_{season}_palm{st}T_gfx_model', 2, st, 0)]
    for st in (3, 4):
        for fam, fid in (('tree', 0), ('cedar', 1), ('palm', 2)):
            shape_routes += [(f'obj_{season}_{fam}{st}_leafT_gfx_model', fid, st, 0), (f'obj_{season}_{fam}{st}_trunkT_gfx_model', fid, st, 1)]
    shape_routes += [(f'obj_{season}_palm5_leafT_gfx_model', 2, 5, 0), (f'obj_{season}_palm5_trunkT_gfx_model', 2, 5, 1)]
    shape_routes += [(f'obj_{season}_tree1_deadT_gfx_model', 0, 1, 8), (f'obj_{season}_cedar1_deadT_gfx_model', 1, 1, 8),
                     (f'obj_{season}_palm1_deadT_gfx_model', 2, 1, 8)]
    for st in (2, 3, 4, 5):
        shape_routes += [(f'obj_{season}_cstump{st}T_gfx_model', 1, st, 7)]
    for st in (2, 3, 4):
        shape_routes += [(f'obj_{season}_pstump{st}T_gfx_model', 2, st, 7)]
    shape_routes += [(f'obj_{season}_spstump5T_gfx_model', 2, 5, 7)]
for st in (2, 3, 4):
    shape_routes += [(f'obj_stump{st}T_gfx_model', 0, st, 7)]
model_text = '\n'.join(p.read_text(errors='ignore') for p in (ROOT/'ACGC-PC-Port/src/data/model').glob('*.c'))
defined = set(re.findall(r'^Gfx (\w+)\[\]', model_text, re.M))
shape_routes = [r for r in shape_routes if r[0] in defined]
for r in shape_routes: assert (r[1], r[2], r[3]) in routes, r
gold = sorted(n for n in defined if 'gold' in n and n.endswith('T_mat_model'))
hdr = ['/* Generated by generate_young_plants.py: native young-plant display lists. */',
       '#ifndef PC_YOUNG_PLANT_ROUTES_H', '#define PC_YOUNG_PLANT_ROUTES_H']
hdr += [f'extern Gfx {n}[];' for n, *_ in shape_routes] + [f'extern Gfx {n}[];' for n in gold]
hdr += ['static int pc_young_plant_route(Gfx* material, Gfx* shape, int* family, int* stage, int* part) {',
        '    static Gfx* const gold[] = {'+','.join(gold)+'};',
        '    static const struct { Gfx* shape; signed char family, stage, part; } table[] = {']
hdr += ['        {%s,%d,%d,%d},' % r for r in shape_routes]
hdr += ['    };', '    unsigned i;',
        '    for(i=0;i<sizeof(gold)/sizeof(gold[0]);++i) if(material==gold[i]) return 0;',
        '    for(i=0;i<sizeof(table)/sizeof(table[0]);++i) if(table[i].shape==shape) {',
        '        *family=table[i].family; *stage=table[i].stage; *part=table[i].part; return 1;', '    }',
        '    return 0;', '}', '#endif']
(ROOT/'ACGC-PC-Port/pc/include/pc_young_plant_routes.h').write_text('\n'.join(hdr)+'\n')
audit['routes'] = len(shape_routes); audit['scale'] = SCALE; audit['palm_unique_atlases'] = len(seen)
(SRC/'young_plants_audit.json').write_text(json.dumps(audit, indent=1))
print('lists', len(lists), 'routes', len(shape_routes), 'palm atlases', len(seen))
for k, v in audit.items():
    if isinstance(v, dict): print(k, {a: b for a, b in v.items() if a != 'cut_pivots'})
