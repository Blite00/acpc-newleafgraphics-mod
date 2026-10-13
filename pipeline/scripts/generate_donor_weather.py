"""Convert original Weather BCRES textures to native weather actor display lists.

Host actors retain spawning, motion, wind and lifetimes. Source four-cell
atlases use the host splash age / petal identity to select a cell; this is an
animation adapter, not a claim that the original emitter runtime was ported.
"""
from pathlib import Path
from PIL import Image

root = Path(__file__).resolve().parent
lines = ['/* Generated from original /Weather assets; see generate_donor_weather.py. */']
for name, path, cells, scale, size, channel in [
    ('snow','snow/snow.png',1,.00196,5.0,'red'),
    ('rain','rain/ame_ground.png',4,.0033,2.0,'alpha'),
    ('sakura','sakura/cherryblossoms.png',4,.05,2.0,'alpha'),
]:
    im=Image.open(root/'terrain_source/weather'/path).convert('RGBA')
    # Source snow alpha explicitly uses texture red, unlike splash/petal alpha.
    if channel=='red':
        im.putdata([(255,255,255,r) for r,g,b,a in im.getdata()])
    w,h=im.size
    data=[]
    for ty in range(0,h,4):
        for tx in range(0,w,4):
            tile=[im.getpixel((tx+x,ty+y)) for y in range(4) for x in range(4)]
            data.extend(c for r,g,b,a in tile for c in (a,r))
            data.extend(c for r,g,b,a in tile for c in (g,b))
    lines += [f'#ifdef PC_DONOR_WEATHER_{name.upper()}',
              f'static u8 pc_donor_{name}_tex[] ATTRIBUTE_ALIGN(32) = {{']
    lines += [','.join(map(str,data[i:i+32]))+',' for i in range(0,len(data),32)]
    lines += ['};',f'static Gfx pc_donor_{name}_setup[] = {{',
              'gsDPPipeSync(),','gsDPSetCycleType(G_CYC_1CYCLE),',
              'gsDPSetAlphaCompare(G_AC_NONE),','gsDPSetTextureFilter(G_TF_BILERP),',
              'gsSPTexture(0,0,0,G_TX_RENDERTILE,G_ON),',
              'gsDPSetCombineMode(G_CC_MODULATEIA_PRIM,G_CC_MODULATEIA_PRIM),',
              'gsDPSetPrimColor(0,0,255,255,255,255),',
              'gsDPSetRenderMode(G_RM_ZB_XLU_SURF,G_RM_ZB_XLU_SURF2),',
              f'gsDPSetTextureImage_Dolphin(G_IM_FMT_RGBA,G_IM_SIZ_32b,{w},{h},pc_donor_{name}_tex),',
              'gsDPSetTile_Dolphin(G_DOLPHIN_TLUT_DEFAULT_MODE,0,0,GX_CLAMP,GX_CLAMP,0,0),',
              f'gsDPSetTileSize_Dolphin(G_TX_RENDERTILE,0,0,{w},{h}),',
              'gsSPLoadGeometryMode(G_ZBUFFER|G_SHADE|G_SHADING_SMOOTH),',
              'gsSPEndDisplayList(),','};']
    # Source 512-unit acre corresponds to native 640 world units. Convert
    # source XZ billboard to host XY and compensate existing actor scale.
    half=round(size*1.25*.5/scale)
    for frame in range(cells):
        left=round((frame*w/cells+.5)*32)
        right=round(((frame+1)*w/cells-.5)*32)
        top,bottom=16,h*32-16
        lines += [f'static Vtx pc_donor_{name}_{frame}_vertices[] = {{']
        for x,y,s,t in [(-half,half,left,top),(half,half,right,top),(-half,-half,left,bottom),(half,-half,right,bottom)]:
            lines += [f'{{{{{{{x},{y},0}},0,{{{s},{t}}},{{255,255,255,255}}}}}},']
        lines += ['};',f'static Gfx pc_donor_{name}_{frame}[] = {{',
                  f'gsSPVertex(pc_donor_{name}_{frame}_vertices,4,0),',
                  'gsSP2Triangles(0,2,1,0,1,2,3,0),','gsSPEndDisplayList(),','};']
    if cells>1:
        lines += [f'static Gfx* pc_donor_{name}_frames[] = {{'+','.join(f'pc_donor_{name}_{i}' for i in range(cells))+'};']
    if name=='rain':
        # Original atlas cell0 is a falling-drop silhouette. Keep the host
        # streak extent/motion; crop only transparent padding around this cell.
        lines += ['static Vtx pc_donor_rain_streak_vertices[] = {']
        for x,y,u,v in [(-1000,-1000,6.5,14.5),(1000,-1000,10.5,14.5),
                        (-1000,1000,6.5,.5),(1000,1000,10.5,.5)]:
            lines += [f'{{{{{{{x},{y},0}},0,{{{round(u*32)},{round(v*32)}}},{{255,255,255,255}}}}}},']
        lines += ['};','static Gfx pc_donor_rain_streak[] = {',
                  'gsSPVertex(pc_donor_rain_streak_vertices,4,0),',
                  'gsSP2Triangles(0,1,2,0,1,3,2,0),','gsSPEndDisplayList(),','};']
    lines += ['#endif']
(root/'ACGC-PC-Port/src/actor/pc_donor_weather.c_inc').write_text('\n'.join(lines)+'\n')
