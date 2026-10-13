"""Original 3DS pine render adapter; only native cedar draw routes use these lists."""
import json
from pathlib import Path
from PIL import Image
from support_closure import support_closure, host_ground_support_depth
ROOT=Path(__file__).resolve().parent
scale=12243/83.0161 # Same donor-to-world scale as the imported hardwood.
def mesh(folder,name):
 return json.loads((ROOT/'tree_source'/folder/(name+'.json')).read_text())['meshes'][0]['vertices']
def key(tri):
 return tuple(sorted(tuple(round(x,3)for x in v['position'])for v in tri))
vs=mesh('season08_normals','fg_treeB_4')
stump=mesh('season08_normals','fg_treeB_4_b')
felled=mesh('animations_normals','fg_treeB_4_t')
# Source animated node1 is bark; nodes2/3 are the two needle branches.
# Match the standing geometry to that source partition and the original stump.
bark={key(felled[i:i+3])for i in range(0,len(felled),3)if felled[i]['nodes']==[1]}
bark|={key(stump[i:i+3])for i in range(0,len(stump),3)if min(v['position'][1]for v in stump[i:i+3])<15.99}
parts={'leaf':[],'trunk':[],'felled_leaf':[],'felled_trunk':[],'stump':stump}
for i in range(0,len(vs),3):parts['trunk' if key(vs[i:i+3])in bark else 'leaf']+=vs[i:i+3]
for i in range(0,len(felled),3):parts['felled_trunk' if felled[i]['nodes']==[1] else 'felled_leaf']+=felled[i:i+3]
assert len(parts['trunk'])==210 and len(parts['leaf'])==408
assert len(parts['felled_trunk'])==60 and len(parts['felled_leaf'])==408
assert len(stump)==171
assert min(v['position'][1]for v in felled)==16
support=support_closure(stump,extra_depth=host_ground_support_depth(ROOT)/(scale*.01))
parts['trunk']=parts['trunk']+support;parts['stump']=stump+support
out=['/* Generated original seasonal 3DS pine; native cedar instances only. */', 'int g_pc_cedar_world = 1; /* Replace existing native cedars only; distribution stays native. */']
atlases=[];seen={}
for season in range(23):
 folder=ROOT/f'tree_source/season{season:02}_normals'
 assert mesh(folder.name,'fg_treeB_4')==vs
 assert mesh(folder.name,'fg_treeB_4_b')==stump
 atlas=Image.open(folder/'treeB.png').convert('RGBA');assert atlas.size==(128,256)
 raw=atlas.tobytes()
 if raw in seen:atlases.append(seen[raw]);continue
 name=f'pc_cedar_season{season:02}_tex';seen[raw]=name;atlases.append(name)
 tex=bytearray()
 for ty in range(0,256,4):
  for tx in range(0,128,4):
   tile=[atlas.getpixel((tx+x,ty+y))for y in range(4)for x in range(4)]
   tex.extend(c for r,g,b,a in tile for c in (a,r));tex.extend(c for r,g,b,a in tile for c in (g,b))
 out += [f'static u8 {name}[] ATTRIBUTE_ALIGN(32) = {{']
 out += [','.join(map(str,tex[i:i+32]))+','for i in range(0,len(tex),32)]+['};']
out+=['static u8* pc_cedar_atlases[23]={'+','.join(atlases)+'};']
variants=[('leaf','leaf',None),('trunk','trunk',None),('shake','leaf',(9000,0)),
 ('cutL_leaf','felled_leaf',(9000,-1000)),('cutR_leaf','felled_leaf',(9000,1000)),
 ('cutL_trunk','felled_trunk',(2250,-1000)),('cutR_trunk','felled_trunk',(2250,1000)),('stump','stump',None)]
for name, part, pivot in variants:
    vertices=parts[part]
    out.append('static const PC_TreeSourceLight pc_cedar_%s_light[] = {'%name)
    for v in vertices:
        normal=v['normal']; length=sum(c*c for c in normal)**.5
        assert length>.9
        normal=[c/length for c in normal]
        color=[(v['color']>>b)&255 for b in (16,8,0,24)]
        out.append('{{%s},{%s}},'%(','.join('%.8ff'%c for c in normal),','.join(map(str,color))))
    out.append('};')
    out.append('static Vtx pc_cedar_%s_v[] ATTRIBUTE_ALIGN(32) = {'%name)
    for v in vertices:
        x,y,z=[round(c*scale) for c in v['position']]
        if pivot: x,y=y-pivot[0],-x+pivot[1]
        u,t=v['uv']; u=round(u*128*32); t=round((1-t)*256*32)
        c=v['color']; rgba=[(c>>s)&255 for s in (16,8,0,24)]
        out.append('{{{%d,%d,%d},1,{%d,%d},{%s}}},'%(x,y,z,u,t,','.join(map(str,rgba))))
    out += ['};','static Gfx pc_cedar_%s_dl[] = {'%name,
        'gsDPPipeSync(),','gsSPTexture(0,0,0,G_TX_RENDERTILE,G_ON),',
        'gsDPSetTexEdgeAlpha(78),',
        ('gsDPSetCombineLERP(TEXEL0,0,SHADE,0,0,0,0,TEXEL0,PRIMITIVE,0,COMBINED,0,COMBINED,0,PRIM_LOD_FRAC,PRIMITIVE),' if pivot else
         'gsDPSetCombineLERP(TEXEL0,0,SHADE,0,0,0,0,TEXEL0,PRIMITIVE,0,COMBINED,0,0,0,0,COMBINED),'),
        'gsDPSetTextureImage_Dolphin(G_IM_FMT_RGBA,G_IM_SIZ_32b,128,256,pc_tree_preview_tex),',
        'gsDPSetTile_Dolphin(G_DOLPHIN_TLUT_DEFAULT_MODE,0,0,GX_MIRROR,GX_MIRROR,0,0),',
        'gsSPLoadGeometryMode(G_ZBUFFER|G_SHADE|G_FOG|G_SHADING_SMOOTH|G_DECAL_LEQUAL),']
    if pivot is None:
        out.append('gsDPSetRenderMode(G_RM_FOG_SHADE_A,G_RM_AA_ZB_TEX_EDGE2),')
    for base in range(0,len(vertices),30):
        count=min(30,len(vertices)-base)
        out.append('gsSPVertex(&pc_cedar_%s_v[%d],%d,0),'%(name,base,count))
        indices=list(range(count)); first=(indices+[0]*9)[:9]
        out.append('gsSPNTrianglesInit_5b(%d,%s),'%(count//3,','.join(map(str,first))))
        for i in range(9,count,12):
            batch=(indices[i:i+12]+[0]*12)[:12]
            out.append('gsSPNTriangles_5b(%s),'%','.join(map(str,batch)))
    out += ['gsDPPipeSync(),','gsDPSetTexEdgeAlpha(144),',
        'gsSPLoadGeometryMode(G_ZBUFFER|G_SHADE|G_CULL_BACK|G_FOG|G_LIGHTING|G_SHADING_SMOOTH|G_DECAL_LEQUAL),',
        'gsSPEndDisplayList(),','};']

out += ['Gfx* pc_cedar_world_mesh(int part) {',
 'static Gfx* lists[] = {'+','.join('pc_cedar_'+n+'_dl'for n,_,_ in variants)+'};',
 'static Vtx* vertices[] = {'+','.join('pc_cedar_'+n+'_v'for n,_,_ in variants)+'};',
 'static const PC_TreeSourceLight* source[] = {'+','.join('pc_cedar_'+n+'_light'for n,_,_ in variants)+'};',
 'static const int counts[] = {'+','.join(str(len(parts[p]))for _,p,_ in variants)+'};',
 'static unsigned generations[8];',
 'if(part<0 || part>=8) return NULL;',
 'if(generations[part]!=pc_tree_light_generation) {',
 'pc_tree_light_vertices(vertices[part],source[part],counts[part]); generations[part]=pc_tree_light_generation;',
 '}',
 'lists[part][4].words.w1=_GBI_RUNTIME_PTR(pc_cedar_atlases[pc_tree_world_season()]);',
 'return lists[part];','}']
(ROOT/'ACGC-PC-Port/pc/src/pc_cedar_world.c_inc').write_text('\n'.join(out)+'\n')
(ROOT/'tree_source/cedar_import_audit.json').write_text(json.dumps({'source':'Original fg_treeB_4, fg_treeB_4_b, fg_treeB_4_t; treeB seasonal atlas','scale':scale,'season_topology_verified':23,'unique_atlases':len(seen),'parts':{k:len(v)for k,v in parts.items()},'native_pivots':{'shake':9000,'cut_leaf':9000,'cut_trunk':2250,'cut_offset':1000},'support_depth_world':host_ground_support_depth(ROOT),'scope':'Render replacement of native cedar IDs only; no foreground IDs, counts, growth, schedules, positions or collision altered.'},indent=2))
print('Cedar vertices:',{k:len(v)for k,v in parts.items()},'atlases',len(seen))
