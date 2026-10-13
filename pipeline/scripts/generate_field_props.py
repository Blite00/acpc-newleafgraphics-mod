"""Original seasonal boulder and weed/clover geometry for native field actors."""
from pathlib import Path
from PIL import Image
import json
from support_closure import support_closure, host_ground_support_depth
ROOT=Path(__file__).resolve().parent
out=['/* Generated from original Season00..22.bcres; geometry and texture colors preserved. */']
textures={}
support_depth=host_ground_support_depth(ROOT)
for atlas in ['t_wild','fg_bush']:
    names=[]; seen={}
    for season in range(23):
        im=Image.open(ROOT/f'tree_source/season{season:02}_normals/{atlas}.png').convert('RGBA')
        raw=im.tobytes()
        if raw in seen: names.append(seen[raw]);continue
        name=f'pc_prop_{atlas}_{season:02}'
        seen[raw]=name;names.append(name);w,h=im.size
        data=[]
        for ty in range(0,h,4):
            for tx in range(0,w,4):
                tile=[im.getpixel((tx+x,ty+y))for y in range(4)for x in range(4)]
                data.extend(c for r,g,b,a in tile for c in (a,r))
                data.extend(c for r,g,b,a in tile for c in (g,b))
        out += [f'static u8 {name}[] ATTRIBUTE_ALIGN(32) = {{']
        out += [','.join(map(str,data[i:i+32]))+','for i in range(0,len(data),32)]+['};']
    out += [f'static u8* pc_prop_{atlas}_seasons[23] = {{'+','.join(names)+'};']
models=['fg_stone'+x for x in 'ABCDE']+['fg_grassA','fg_grassC','fg_grassE']
# Shadow dimensions follow the same imported body vertices and actor scale.
shadow_bounds=[]
for name in models[:5]:
    vs=json.load(open(ROOT/f'tree_source/season08_normals/{name}.json'))['meshes'][0]['vertices']
    shadow_bounds.append([round(f(v['position'][axis] for v in vs)*125) for axis in (0,2) for f in (min,max)])
(ROOT/'ACGC-PC-Port/pc/include/pc_rock_shadow_fit.h').write_text(
    '/* Imported boulder XZ bounds in native 0.01-scale actor coordinates. */\n'
    'static const short pc_rock_shadow_bounds[5][4] = {\n'+
    ''.join('{'+','.join(map(str,b))+'},\n' for b in shadow_bounds)+'};\n',encoding='utf-8')
counts=[]
for idx,name in enumerate(models):
    mesh=json.load(open(ROOT/f'tree_source/season08_normals/{name}.json'))['meshes'][0]
    vs=mesh['vertices'];atlas=mesh['texture']
    w,h=Image.open(ROOT/f'tree_source/season08_normals/{atlas}.png').size
    for season in range(23):
        assert json.load(open(ROOT/f'tree_source/season{season:02}_normals/{name}.json'))['meshes'][0]['vertices']==vs
    if idx<5: vs=vs+support_closure(vs,extra_depth=support_depth/1.25)
    counts.append(len(vs))
    out += [f'static const PC_TreeSourceLight pc_prop_{idx}_light[] = {{']
    for v in vs:
        n=v['normal'];length=sum(c*c for c in n)**.5
        rgba=[(v['color']>>b)&255 for b in (16,8,0,24)]
        out += ['{{'+','.join(f'{c/length:.8f}f'for c in n)+'},{'+','.join(map(str,rgba))+'}},']
    out += ['};',f'static Vtx pc_prop_{idx}_v[] ATTRIBUTE_ALIGN(32) = {{']
    for v in vs:
        x,y,z=[round(c*125)for c in v['position']]
        u,t=v['uv'];u=round(u*w*32);t=round((1-t)*h*32)
        rgba=[(v['color']>>b)&255 for b in (16,8,0,24)]
        out += ['{{{%d,%d,%d},1,{%d,%d},{%s}}},'%(x,y,z,u,t,','.join(map(str,rgba)))]
    out += ['};',f'static Gfx pc_prop_{idx}_dl[] = {{','gsDPPipeSync(),','gsSPTexture(0,0,0,G_TX_RENDERTILE,G_ON),',
        f'gsDPSetTextureImage_Dolphin(G_IM_FMT_RGBA,G_IM_SIZ_32b,{w},{h},{"pc_prop_"+atlas+"_00"}),',
        'gsDPSetTile_Dolphin(G_DOLPHIN_TLUT_DEFAULT_MODE,0,0,GX_MIRROR,GX_MIRROR,0,0),',
        f'gsDPSetTileSize_Dolphin(G_TX_RENDERTILE,0,0,{w},{h}),',
        'gsDPSetCycleType(G_CYC_2CYCLE),',
        'gsDPSetTextureFilter(G_TF_BILERP),',
        'gsDPSetCombineLERP(TEXEL0,0,SHADE,0,TEXEL0,0,ENVIRONMENT,0,PRIMITIVE,0,COMBINED,0,0,0,0,COMBINED),',
        'gsDPSetTexEdgeAlpha(76),',
        'gsSPLoadGeometryMode(G_ZBUFFER|G_SHADE|G_FOG|G_SHADING_SMOOTH|G_DECAL_LEQUAL),']
    for base in range(0,len(vs),30):
        count=min(30,len(vs)-base)
        out += [f'gsSPVertex(&pc_prop_{idx}_v[{base}],{count},0),']
        for j in range(0,count,3):out += [f'gsSP1Triangle({j},{j+1},{j+2},0),']
    out += ['gsDPSetTexEdgeAlpha(144),','gsSPLoadGeometryMode(G_ZBUFFER|G_SHADE|G_CULL_BACK|G_FOG|G_LIGHTING|G_SHADING_SMOOTH|G_DECAL_LEQUAL),','gsSPEndDisplayList(),','};']
out += ['Gfx* pc_field_prop_mesh(int part) {',
    'static Gfx* lists[]={'+','.join(f'pc_prop_{i}_dl'for i in range(8))+'};',
    'static Vtx* vertices[]={'+','.join(f'pc_prop_{i}_v'for i in range(8))+'};',
    'static const PC_TreeSourceLight* source[]={'+','.join(f'pc_prop_{i}_light'for i in range(8))+'};',
    'static const int counts[]={'+','.join(map(str,counts))+'};','static unsigned generations[8];',
    'if(part<0 || part>=8) return NULL;',
    'if(generations[part]!=pc_tree_light_generation) { pc_tree_light_vertices(vertices[part],source[part],counts[part]);generations[part]=pc_tree_light_generation; }',
    'lists[part][2].words.w1=_GBI_RUNTIME_PTR((part<5?pc_prop_t_wild_seasons:pc_prop_fg_bush_seasons)[pc_tree_world_season()]);',
    'return lists[part];','}']
(ROOT/'ACGC-PC-Port/pc/src/pc_field_props.c_inc').write_text('\n'.join(out)+'\n')
print('Generated donor boulders A-E, upright weeds A/C and clover E.')
