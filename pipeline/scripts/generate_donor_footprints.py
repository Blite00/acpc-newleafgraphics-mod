"""Pack decoded original 3DS footprint artwork into native decal geometry.
The existing effect owns contact position, slope, lifetime and fade.
"""
from pathlib import Path
from PIL import Image
import argparse
p=argparse.ArgumentParser();p.add_argument('texture');a=p.parse_args()
root=Path(__file__).resolve().parent
im=Image.open(a.texture).convert('RGBA');w,h=im.size
assert w%4==0 and h%4==0
blob=[]
for ty in range(0,h,4):
 for tx in range(0,w,4):
  tile=[im.getpixel((tx+x,ty+y)) for y in range(4) for x in range(4)]
  blob.extend(c for r,g,b,alpha in tile for c in (alpha,r))
  blob.extend(c for r,g,b,alpha in tile for c in (g,b))
lines=['/* Generated from original local 3DS particle footprint texture. */','static u8 pc_donor_footprint_tex[] ATTRIBUTE_ALIGN(32) = {']
lines += [','.join(map(str,blob[i:i+32]))+',' for i in range(0,len(blob),32)]
lines += ['};','static Vtx pc_donor_footprint_vertices[] = {']
# Existing effect applies .005 X and .0075 Z: donor7.5x11.25 footprint bounds.
for x,z,s,t in [(-750,750,0,h*32),(750,750,w*32,h*32),(-750,-750,0,0),(750,-750,w*32,0)]:
 lines += ['{{{%d,0,%d},0,{%d,%d},{255,255,255,255}}},'%(x,z,s,t)]
lines += ['};','static Gfx pc_donor_footprint_model[] = {','gsDPPipeSync(),','gsDPSetCycleType(G_CYC_1CYCLE),','gsDPSetAlphaCompare(G_AC_NONE),','gsDPSetTextureFilter(G_TF_BILERP),','gsSPTexture(0,0,0,G_TX_RENDERTILE,G_ON),','gsDPSetCombineMode(G_CC_MODULATEIA_PRIM,G_CC_MODULATEIA_PRIM),','gsDPSetRenderMode(G_RM_ZB_XLU_SURF,G_RM_ZB_XLU_SURF2),',f'gsDPSetTextureImage_Dolphin(G_IM_FMT_RGBA,G_IM_SIZ_32b,{w},{h},pc_donor_footprint_tex),','gsDPSetTile_Dolphin(G_DOLPHIN_TLUT_DEFAULT_MODE,0,0,GX_CLAMP,GX_CLAMP,0,0),',f'gsDPSetTileSize_Dolphin(G_TX_RENDERTILE,0,0,{w},{h}),','gsSPLoadGeometryMode(G_ZBUFFER|G_SHADE|G_SHADING_SMOOTH),','gsSPVertex(pc_donor_footprint_vertices,4,0),','gsSP2Triangles(0,1,2,0,1,3,2,0),','gsSPEndDisplayList(),','};']
(root/'ACGC-PC-Port/src/effect/pc_donor_footprint.c_inc').write_text('\n'.join(lines)+'\n')
print('Packed source footprint',w,h,'at 75 percent size, retaining native contact placement and fade.')

