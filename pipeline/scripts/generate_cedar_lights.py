"""Import original pine glow geometry with native holiday selection and blink adapter."""
from pathlib import Path
import json
from PIL import Image
R=Path(__file__).resolve().parent
scale=12243/83.0161
mesh=json.loads((R/'tree_source/animations_normals/fg_treeB_d.json').read_text())['meshes'][0]
animated=json.loads((R/'tree_source/animations_normals/fg_treeB_d_t.json').read_text())['meshes'][0]
assert mesh['texture']=='t_treeB_d' and len(mesh['vertices'])==198
assert len(animated['vertices'])==198
out=['/* Original pine additive lights; native holiday selection, blink tint and fade. */']
names=[];seen={}
for season in range(23):
 im=Image.open(R/f'tree_source/season{season:02}_normals/t_treeB_d.png').convert('RGBA')
 assert im.size==(16,16)
 raw=im.tobytes()
 if raw in seen:names.append(seen[raw]);continue
 name=f'pc_cedar_lights_tex_{season}';names.append(name);seen[raw]=name;data=[]
 for ty in range(0,16,4):
  for tx in range(0,16,4):
   tile=[im.getpixel((tx+x,ty+y))for y in range(4)for x in range(4)]
   data.extend(c for r,g,b,a in tile for c in (a,r));data.extend(c for r,g,b,a in tile for c in (g,b))
 out += [f'static u8 {name}[] ATTRIBUTE_ALIGN(32) = {{'+','.join(map(str,data))+'};']
out += ['static u8* pc_cedar_lights_atlases[23]={'+','.join(names)+'};']
for part,pivot in enumerate([None,(9000,0),(9000,-1000),(9000,1000)]):
 vs=mesh['vertices'] if part==0 else animated['vertices']
 out += [f'static Vtx pc_cedar_lights_{part}_v[] ATTRIBUTE_ALIGN(32) = {{']
 for v in vs:
  x,y,z=[round(c*scale)for c in v['position']]
  if pivot:x,y=y-pivot[0],-x+pivot[1]
  u,t=v['uv'];u=round(u*16*32);t=round((1-t)*16*32)
  out += ['{{{%d,%d,%d},0,{%d,%d},{255,255,255,255}}},'%(x,y,z,u,t)]
 out += ['};',f'static Gfx pc_cedar_lights_{part}_dl[] = {{',
  'gsDPPipeSync(),','gsDPSetCycleType(G_CYC_2CYCLE),',
  'gsSPTexture(0,0,0,G_TX_RENDERTILE,G_ON),',
  'gsDPSetCombineLERP(TEXEL0,0,1,TEXEL0,0,0,0,TEXEL0,COMBINED,0,PRIMITIVE,0,COMBINED,0,PRIMITIVE,0),',
  f'gsDPSetTextureImage_Dolphin(G_IM_FMT_RGBA,G_IM_SIZ_32b,16,16,{names[0]}),',
  'gsDPSetTile_Dolphin(G_DOLPHIN_TLUT_DEFAULT_MODE,0,0,GX_CLAMP,GX_CLAMP,0,0),',
  'gsDPSetAlphaCompare(G_AC_NONE),',
  'gsDPSetRenderMode(Z_CMP|IM_RD|CVG_DST_CLAMP|FORCE_BL|ZMODE_XLU|GBL_c1(G_BL_CLR_IN,G_BL_A_IN,G_BL_CLR_MEM,G_BL_1),Z_CMP|IM_RD|CVG_DST_CLAMP|FORCE_BL|ZMODE_XLU|GBL_c2(G_BL_CLR_IN,G_BL_A_IN,G_BL_CLR_MEM,G_BL_1)),',
  'gsSPLoadGeometryMode(G_ZBUFFER|G_SHADE|G_SHADING_SMOOTH),']
 for base in range(0,len(vs),30):
  count=min(30,len(vs)-base);out += [f'gsSPVertex(&pc_cedar_lights_{part}_v[{base}],{count},0),']
  for i in range(0,count,3):out += [f'gsSP1Triangle({i},{i+1},{i+2},0),']
 out += ['gsSPEndDisplayList(),','};']
out += ['/* part0 standing,1 shake,2 cut-left,3 cut-right. Caller owns native',
 ' * cedar selection, seasonal eligibility, transform/root inset and restoring',
 ' * the surrounding pipeline. Only call behind g_pc_cedar_world. */',
 'Gfx* pc_cedar_lights_mesh(int part) {',
 'int season=pc_tree_world_season();',
 'static Gfx* lists[]={pc_cedar_lights_0_dl,pc_cedar_lights_1_dl,pc_cedar_lights_2_dl,pc_cedar_lights_3_dl};',
 'if(part<0 || part>3 || season<0 || season>22)return NULL;',
 'lists[part][4].words.w1=_GBI_RUNTIME_PTR(pc_cedar_lights_atlases[season]);',
 'return lists[part];','}']
(R/'ACGC-PC-Port/pc/src/pc_cedar_lights.c_inc').write_text('\n'.join(out)+'\n')
print('Imported four original198-vertex pine light poses; seasonal atlases:',len(seen))
