"""Convert extracted mature hardwood geometry into native ACPC display lists."""
import json
from pathlib import Path
from PIL import Image

ROOT=Path(__file__).resolve().parent
mesh=json.loads((ROOT/'tree_source/season08/fg_treeA_4.json').read_text())['meshes'][0]
verts=mesh['vertices']
assert len(verts)%3==0 and all(not v['nodes'] for v in verts)
im=Image.open(ROOT/'tree_source/season08/treeA.png').convert('RGBA')
w,h=im.size
# GameCube RGBA8 uses 4x4 tiles, with AR and GB in separate 32-byte planes.
data=bytearray()
for ty in range(0,h,4):
    for tx in range(0,w,4):
        tile=[im.getpixel((tx+x,ty+y)) for y in range(4) for x in range(4)]
        data.extend(c for r,g,b,a in tile for c in (a,r))
        data.extend(c for r,g,b,a in tile for c in (g,b))
lines=['/* Generated from local Season08.bcres: fg_treeA_4; preview only. */',
       'static u8 pc_tree_preview_tex[] ATTRIBUTE_ALIGN(32) = {']
lines += [','.join(str(v) for v in data[i:i+32])+',' for i in range(0,len(data),32)]
lines += ['};','static Vtx pc_tree_preview_v[] ATTRIBUTE_ALIGN(32) = {']
scale=12243.0/max(v['position'][1] for v in verts)
for v in verts:
    x,y,z=[round(c*scale) for c in v['position']]
    # 3DS material UVs use a bottom origin; the GX image uses a top origin.
    u,t=v['uv']; u=round(u*w*32); t=round((1-t)*h*32)
    c=v['color']; rgba=[(c>>s)&255 for s in [16,8,0,24]]
    # ACPC uses flag 1 for vertices transformed by the current model matrix.
    lines.append('{{{%d,%d,%d},1,{%d,%d},{%s}}},'%(x,y,z,u,t,','.join(map(str,rgba))))
lines += ['};','static Gfx pc_tree_preview_dl[] = {',
 'gsDPPipeSync(),',
 'gsSPTexture(0,0,0,G_TX_RENDERTILE,G_ON),',
 'gsDPSetRenderMode(G_RM_FOG_SHADE_A,G_RM_AA_ZB_TEX_EDGE2),',
 # Source material replaces alpha with texture alpha * 2, then tests >156.
 # Equivalent cutout at >78 uses texture alpha directly, independent of vertex alpha.
 'gsDPSetTexEdgeAlpha(78),',
 'gsDPSetCombineLERP(TEXEL0,0,SHADE,0,0,0,0,TEXEL0,0,0,0,COMBINED,0,0,0,COMBINED),',
 'gsDPSetTextureImage_Dolphin(G_IM_FMT_RGBA,G_IM_SIZ_32b,%d,%d,pc_tree_preview_tex),'%(w,h),
 'gsDPSetTile_Dolphin(G_DOLPHIN_TLUT_DEFAULT_MODE,0,0,GX_MIRROR,GX_MIRROR,0,0),',
 'gsDPSetPrimColor(0,128,255,255,255,255),',
 'gsSPLoadGeometryMode(G_ZBUFFER|G_SHADE|G_SHADING_SMOOTH),']
for base in range(0,len(verts),30):
    count=min(30,len(verts)-base)
    lines.append('gsSPVertex(&pc_tree_preview_v[%d],%d,0),'%(base,count))
    indices=list(range(count))
    first=indices[:9]+[0]*max(0,9-count)
    lines.append('gsSPNTrianglesInit_5b(%d,%s),'%(count//3,','.join(map(str,first))))
    for i in range(9,count,12):
        batch=indices[i:i+12]; batch += [0]*(12-len(batch))
        lines.append('gsSPNTriangles_5b(%s),'%','.join(map(str,batch)))
lines+=['gsSPEndDisplayList(),','};']
(ROOT/'ACGC-PC-Port/pc/src/pc_tree_preview.c_inc').write_text('\n'.join(lines)+'\n')
(ROOT/'tree_source/preview_manifest.json').write_text(json.dumps({'model':'fg_treeA_4','source':'/Fg/Bcres/Season08.bcres','vertices':len(verts),'triangles':len(verts)//3,'texture_size':[w,h],'scale':scale,'status':'development viewer only; world tree behavior integration pending'},indent=2))
print('Generated full tree:',len(verts)//3,'triangles; texture',im.size)
