"""Original donor shadow masks; native ground projection and fade remain adapters."""
from pathlib import Path
from PIL import Image, ImageOps
import json,subprocess
R=Path(__file__).resolve().parent; O=R/'shadow_source';O.mkdir(exist_ok=True)
with Path(__import__('os').environ['ACPC_NL_ROM']).open('rb') as f:
 for rec in json.loads((R/'3ds_inventory.json').read_text()):
  if rec['path'] in ['/Shadow/sdw_cmn_circle.bcres','/Shadow/sdw_fg_treeA.bcres']:
   p=O/Path(rec['path']).name;f.seek(rec['offset']);p.write_bytes(f.read(rec['size']))
   subprocess.run([str(R/'ExportModels.exe'),str(p),str(O/p.stem)],check=True)
def array(name,data):
 return 'static const unsigned char '+name+'[] = {\n'+'\n'.join(','.join(map(str,data[i:i+32]))+',' for i in range(0,len(data),32))+'\n};\n'
# The donor tree mask, like the contact-circle mask, stores one quadrant.
# Native tree quads mirror U only; directly substituting it omitted the lower
# half and put its fully covered center along a straight polygon boundary.
q=Image.open(O/'sdw_fg_treeA/sdw_fg_treeA.png').convert('RGB').getchannel('R')
# Preserve both center axes. Only the physical outermost two X texels fade.
for y in range(32):
 for x in (30,31):q.putpixel((x,y),round(q.getpixel((x,y))*(31-x)/2))
tree=Image.new('L',(64,64))
tree.paste(ImageOps.mirror(q),(0,0));tree.paste(q,(32,0))
tree.paste(ImageOps.flip(ImageOps.mirror(q)),(0,32));tree.paste(ImageOps.flip(q),(32,32))
tree.save(O/'tree-full-mask.png')
data=[c for value in tree.getdata() for c in [value]*4]
(R/'ACGC-PC-Port/pc/src/pc_donor_shadow_data.c_inc').write_text('/* Full64x64 donor tree mask reconstructed from its original quadrant. */\n'+array('pc_donor_tree_shadow',data))
# Source common circle stores one quadrant with its center at bottom left.
q=Image.open(O/'sdw_cmn_circle/sdw_cmn_circle.png').convert('RGB').getchannel('R')
full=Image.new('L',(64,64));full.paste(ImageOps.mirror(q),(0,0));full.paste(q,(32,0));full.paste(ImageOps.flip(ImageOps.mirror(q)),(0,32));full.paste(ImageOps.flip(q),(32,32));full.save(O/'circle-full-mask.png')
# A separate linear upload for boulder shadows; actor-circle rendering is unchanged.
rock_data=[c for value in full.getdata() for c in [value]*4]
with (R/'ACGC-PC-Port/pc/src/pc_donor_shadow_data.c_inc').open('a',encoding='utf-8') as f:
 f.write(array('pc_donor_rock_shadow',rock_data))
# GC I8 tiled8x4; original intensity becomes TEV alpha.
data=[full.getpixel((tx+x,ty+y)) for ty in range(0,64,4) for tx in range(0,64,8) for y in range(4) for x in range(8)]
s='/* Generated original common-circle shadow, native projection adapter. */\n'+array('pc_donor_circle_shadow_tex',data)
s+='static Vtx pc_donor_circle_shadow_v[] = {\n'
for x,z,u,v in [(-1000,-1000,0,0),(-1000,1000,0,2048),(1000,1000,2048,2048),(1000,-1000,2048,0)]:
 s+='{{{%d,0,%d},0,{%d,%d},{255,255,255,255}}},\n'%(x,z,u,v)
s+='};\nstatic Gfx pc_donor_circle_shadow_dl[] = {\n'
s+='gsDPPipeSync(),\ngsDPSetCycleType(G_CYC_1CYCLE),\ngsDPSetTextureLUT(G_TT_NONE),\ngsDPSetAlphaCompare(G_AC_NONE),\ngsSPTexture(0,0,0,G_TX_RENDERTILE,G_ON),\ngsDPSetCombineLERP(0,0,0,PRIMITIVE,TEXEL0,0,PRIMITIVE,0,0,0,0,PRIMITIVE,TEXEL0,0,PRIMITIVE,0),\ngsDPSetRenderMode(G_RM_ZB_XLU_SURF,G_RM_ZB_XLU_SURF2),\ngsDPSetTextureImage_Dolphin(G_IM_FMT_I,G_IM_SIZ_8b,64,64,pc_donor_circle_shadow_tex),\ngsDPSetTile_Dolphin(G_DOLPHIN_TLUT_DEFAULT_MODE,0,0,GX_CLAMP,GX_CLAMP,0,0),\ngsDPSetTileSize_Dolphin(G_TX_RENDERTILE,0,0,64,64),\ngsSPLoadGeometryMode(G_ZBUFFER|G_SHADE|G_SHADING_SMOOTH|G_DECAL_LEQUAL),\ngsSPVertex(pc_donor_circle_shadow_v,4,0),\ngsSP2Triangles(0,1,2,0,0,2,3,0),\ngsSPEndDisplayList(),\n};\n'
(R/'ACGC-PC-Port/src/game/pc_donor_shadow.c_inc').write_text(s)
