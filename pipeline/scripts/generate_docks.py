"""Adapt the original New Leaf ocean pier to native lake fishing platforms."""
from pathlib import Path
import json,re,math,struct,statistics
from PIL import Image
from close_donor_parts import close_open_parts
from post_deprojection import identify_posts,position_key,unrolled_z,unrolled_normal
from repair_dock_post_shells import repair_dock_post_shells
R=Path(__file__).resolve().parent; ROOT=R/'ACGC-PC-Port';rel=(R/'foresta.rel').read_bytes()

def publish(path,text):
    if path.exists():path.with_name(path.name+'.post-backup').write_bytes(path.read_bytes())
    temporary=path.with_name(path.name+'.post-tmp')
    temporary.write_text(text,encoding='utf-8');temporary.replace(path)

helpers=(R/'generate_bridges.py').read_text()
exec(helpers[helpers.index('def floor_at'):helpers.index('def donor_ground_radius')])
source=json.loads((R/'dock_source/model/sobj_pier_v.json').read_text())['meshes'][0]['vertices']
source_closures,closed_parts=close_open_parts(source)
# The dominant upward surface is the original cylindrical deck, not post tops.
radii=[math.hypot(*v['position'][1:]) for v in source if v['normal'][1]>.7]
from collections import Counter
mode=Counter(round(r,1) for r in radii).most_common(1)[0][0]
radius=statistics.median(r for r in radii if abs(r-mode)<.05)
source_closures,dock_shell_audit=repair_dock_post_shells(source,source_closures,radius)
publish(R/'dock_source/post_shell_audit.json',json.dumps(dock_shell_audit,indent=2))
post_lookup,post_records=identify_posts(source+source_closures,radius)
deck=[[v['position'] for v in source[i:i+3]] for i in range(0,len(source),3)
      if all(abs(math.hypot(*v['position'][1:])-radius)<.04 for v in source[i:i+3])]
def section(z):
 xs=[]
 for t in deck:
  for a,b in zip(t,t[1:]+t[:1]):
   if min(a[2],b[2])<=z<=max(a[2],b[2]) and abs(a[2]-b[2])>1e-6:
    xs.append(a[0]+(b[0]-a[0])*(z-a[2])/(b[2]-a[2]))
 return (min(xs),max(xs)) if xs else None
zmin=min(p[2] for t in deck for p in t);zmax=max(p[2] for t in deck for p in t)
# Keep the rounded donor tip beyond the native collision endpoint. The core
# ends where its width returns to the entry width, before the taper closes.
entry=zmin+1;entry_width=section(entry)[1]-section(entry)[0]
samples=[(zmin+(zmax-zmin)*i/2048,section(zmin+(zmax-zmin)*i/2048)) for i in range(1,2048)]
exit_z=max(z for z,b in samples if b and b[1]-b[0]>=entry_width)
def profile(z):
 z=max(entry,min(exit_z,z));b=section(z)
 if b is None:
  _,b=min(((abs(q-z),v)for q,v in samples if v),key=lambda a:a[0])
 return b
out=['/* Original donor elbow pier; uniform placement with matching native collision. */'];audit=[]
outline_out=[]; support_rows=[]; outline_counts=[]
collision_out=['/* Donor dock support cells plus explicit contour walls. */', 'static void pc_dock_collision_patch(mCoBG_Collision_u* cells, u8* keep, mActor_name_t bg_id, int bx, int bz) {', 'extern int g_pc_tree_world;', 'if (!g_pc_tree_world || bx<0 || bz<0 || bx>=16 || bz>=16) return;', 'pc_dock_block[ bz ][ bx ]=0;', 'switch(bg_id) {']
bg_source=(ROOT/'src/data/field/bg/acre/bg_data.c').read_text()
for snow in (0,9):
 im=Image.open(R/f'dock_source/season{snow:02}/sobj_pier_v.png').convert('RGBA');data=[]
 for y in range(0,im.height,4):
  for x in range(0,im.width,4):
   v=[im.getpixel((x+i,y+j))for j in range(4)for i in range(4)]
   data.extend(c for r,g,b,a in v for c in(a,r));data.extend(c for r,g,b,a in v for c in(g,b))
 out += [f'static u8 pc_dock_tex_{snow}[] ATTRIBUTE_ALIGN(32)={{']+[','.join(map(str,data[i:i+32]))+','for i in range(0,len(data),32)]+['};']
directions={v['acre']:v['directions'][0]for v in json.loads((R/'bridge_source/direction_audit.json').read_text())}
records=[]
for prefix,_,_,name,_ in json.loads((R/'bridge_source/fit_audit.json').read_text()):
 if not re.fullmatch(r'grd_s_r[1-7]_p_1',name):continue
 s=(R/'bridge_source/native_sources'/f'{name}.c').read_text()
 base=int(re.search(r'pc_load_asset\("[^"]+", \w+, 0x\w+, (0x\w+)',s)[1],16)
 water=parse(re.search(r'Gfx \w+_modelT\[\] = \{(.*?)\n\};',s,re.S)[1],base)
 hit=re.search(r'gsDPLoadTextureBlock_4b_Dolphin\(bridge_2_tex_dummy',s)
 end=hit.end()+re.search(r'gsDPLoad(?:TLUT|Texture|Multi)',s[hit.end():]).start()
 native=parse(s[hit.start():end],base);pts=[v for t in native for v in t]
 lx,lz=directions[name];n=math.hypot(lx,lz);lx/=n;lz/=n;wx,wz=-lz,lx
 aa=[v[0]*lx+v[2]*lz for v in pts];bb=[v[0]*wx+v[2]*wz for v in pts]
 a0,a1=min(aa),max(aa);b0,b1=min(bb),max(bb);mid=(b0+b1)/2
 wet=[]
 for endpoint,sign in((a0,-1),(a1,1)):
  wet.append(sum(floor_at(water,(endpoint+sign*d)*lx+mid*wx,(endpoint+sign*d)*lz+mid*wz,None)is not None for d in(200,400,640,960,1280)))
 assert wet[0]!=wet[1],(name,'Ambiguous bank direction',wet)
 bank,tip=(a0,a1)if wet[0]<wet[1]else(a1,a0)
 width=b1-b0;scale=width/entry_width;vtx=[];lighting=[]
 entry_center=sum(section(entry))/2
 along_sign=1 if tip>bank else -1
 deck_floor=floor_at(native,(bank+tip)*.5*lx+mid*wx,(bank+tip)*.5*lz+mid*wz,640)
 def place(x,z):
  along=bank+(z-entry)*scale*along_sign
  across=mid+(x-entry_center)*scale
  return along*lx+across*wx,along*lz+across*wz
 target_deck=[[(place(x,z)[0],deck_floor,place(x,z)[1])for x,y,z in t]for t in deck]
 # Verify the original elbow remains above native water, not through a bank.
 assert all(floor_at(water,*place(x,z),None) is not None or floor_at(native,*place(x,z),None) is not None
            for t in deck for x,y,z in t if z>entry+15),name

 for v in source+source_closures:
  x,y,z=v['position'];post=post_lookup.get(position_key(v));render_z=unrolled_z(y,z,post,radius) if post else z;tx,tz=place(x,render_z)
  # Undo the donor's baked curvature, then let the host shader bend it once.
  ty=deck_floor+(math.hypot(y,z)-radius)*scale
  vtx.append((round(tx),round(ty),round(tz),v['uv']))
  nx,ny,nz=v['normal'];theta=math.atan2(z,y)
  if post:nx,ny,nz=unrolled_normal(v['normal'],y,z,radius)
  else:ny,nz=ny*math.cos(theta)+nz*math.sin(theta),-ny*math.sin(theta)+nz*math.cos(theta)
  nz*=along_sign;length=math.sqrt(nx*nx+ny*ny+nz*nz)or 1
  lighting.append(((nx*wx+nz*lx)/length,ny/length,(nx*wz+nz*lz)/length))

 # Shallow solid plank thickness closes the source camera-hidden deck rim.
 top_indices=[i for i,v in enumerate(source)if abs(math.hypot(*v['position'][1:])-radius)<.04]
 def edge_v(x,z,bottom=False):
  donor=min((source[i]for i in top_indices),key=lambda v:(v['position'][0]-x)**2+(v['position'][2]-z)**2)
  tx,tz=place(x,z);u,t=donor['uv']
  return (round(tx),round(deck_floor-(48 if bottom else 1)),round(tz),(u,t-(.08 if bottom else 0)))
 sections=[]
 for j in range(33):
  z=entry+(zmax-entry-.2)*j/32;lo,hi=section(z);sections.append((lo,hi,z))
 contour=[(lo,z)for lo,hi,z in sections]+[(hi,z)for lo,hi,z in reversed(sections)]
 for a,b in zip(contour,contour[1:]+contour[:1]):
  q=[edge_v(*a),edge_v(*b),edge_v(*b,True),edge_v(*a,True)]
  dx,dz=q[1][0]-q[0][0],q[1][2]-q[0][2];length=math.hypot(dx,dz)or 1
  normal=(dz/length,0,-dx/length)
  for i in(0,1,2,0,2,3):vtx.append(q[i]);lighting.append(normal)
 for tri in deck:
  for x,y,z in reversed(tri):
   vtx.append(edge_v(x,z,True));lighting.append((0,-1,0))
 # Native collision is a 40-world-unit grid with diagonal half-cell wood edges.
 # Fit those same primitives to the source walk surface, preserving all land.
 block=bg_source.split('BG_TYPE_'+name.upper()+',',1)[1].split('// collision data',1)[1]
 raw=re.findall(r'\{\s*(\d+),\s*(\d+),\s*(\d+),\s*(\d+),\s*(\d+),\s*(\d+),\s*(mCoBG_ATTRIBUTE_\w+)\s*\}',block)[:256]
 assert len(raw)==256
 oldwood={'mCoBG_ATTRIBUTE_'+str(i)for i in range(27,32)}
 waterattrs={'mCoBG_ATTRIBUTE_WATER','mCoBG_ATTRIBUTE_WATERFALL'}|{'mCoBG_ATTRIBUTE_RIVER_'+d for d in ('N','NW','W','SW','S','SE','E','NE')}
 masks={12:0,27:12,28:9,29:3,30:6,31:15}
 def area(x,z):
  return (0 if z<0 else 2) if abs(z)>=abs(x) else (1 if x<0 else 3)
 # Keep an uninterrupted central walking route, including the original entry.
 required={}
 for j in range(201):
  z=entry+(zmax-entry-12)*j/200
  bounds=section(z)
  if bounds is None:continue
  x=(bounds[0]+bounds[1])/2;px,pz=place(x,z)
  ux,uz=int(px//640),int(pz//640)
  assert 0<=ux<16 and 0<=uz<16,(name,'source dock leaves acre')
  required[uz*16+ux]=required.get(uz*16+ux,0)|(1<<area(px-(ux+.5)*640,pz-(uz+.5)*640))
 patches=[];raster=[]
 for i,c in enumerate(raw):
  if c[-1] not in oldwood|waterattrs:continue
  ux,uz=i%16,i//16;samples=[]
  for iz in range(8):
   for ix in range(8):
    dx=(ix+.5)*80-320;dz=(iz+.5)*80-320
    inside=floor_at(target_deck,(ux+.5)*640+dx,(uz+.5)*640+dz,None) is not None
    samples.append((area(dx,dz),inside))
  def score(k):
   mask=masks[k]
   if required.get(i,0)&~mask:return 1e9
   return sum((3 if mask&(1<<a) else 1)for a,inside in samples if bool(mask&(1<<a))!=inside)
  selected=31 if any(inside for _,inside in samples) or i in required else 12;mask=masks[selected]
  assert score(selected)<1e9
  if mask or c[-1] in oldwood:
   height=round(deck_floor/160) if mask else 0
   patches.append((i,height,selected));raster.append({'cell':[ux,uz],'wood_mask':mask,'height':height*10})
 assert all(raw[i][-1] not in oldwood|waterattrs or any(p[0]==i and masks[p[2]]&required[i]==required[i]for p in patches)for i in required)
 # Contour walls, rather than bridge-interior tile flags, contain every edge.
 left=[];right=[]
 for j in range(33):
  z=entry+(zmax-entry-.2)*j/32;lo,hi=section(z)
  left.append(tuple(q/16 for q in place(lo,z)));right.append(tuple(q/16 for q in place(hi,z)))
 def simplify(points):
  if len(points)<3:return points
  ax,az=points[0];bx,bz=points[-1];dx,dz=bx-ax,bz-az;den=dx*dx+dz*dz
  values=[]
  for x,z in points[1:-1]:
   t=max(0,min(1,((x-ax)*dx+(z-az)*dz)/den))if den else 0
   values.append(math.hypot(x-ax-t*dx,z-az-t*dz))
  error=max(values);index=values.index(error)+1
  return simplify(points[:index+1])[:-1]+simplify(points[index:]) if error>4.0 else [points[0],points[-1]]
 # Plank notches are decoration, not actor-sized obstacles. Filter at the
 # 12-world-unit player radius scale, retaining entrance/tip endpoints.
 def smooth_side(points):
  return [points[0]]+[tuple((points[j-1][k]+2*points[j][k]+points[j+1][k])/4 for k in range(2))for j in range(1,len(points)-1)]+[points[-1]]
 polygon=simplify(smooth_side(left))+list(reversed(simplify(smooth_side(right))))
 cleaned=[polygon[0]]
 for q in polygon[1:-1]:
  if math.dist(q,cleaned[-1])>=4.0:cleaned.append(q)
 polygon=cleaned+[polygon[-1]]
 variant=len(outline_counts)
 outline_out += [f'static const float pc_dock_outline_{variant}[][2]={{'+','.join('{%ff,%ff}'%q for q in polygon)+'};']
 outline_counts.append(len(polygon));support_rows.append([int(any(p[0]==i and p[1]>0 for p in patches))for i in range(256)])
 collision_out += ['case BG_TYPE_'+name.upper()+':',f'pc_dock_block[bz][bx]={variant+1};']
 for i,h,attr in patches:
  collision_out += [f'cells[{i}]=(mCoBG_Collision_u){{{{0,{h},{h},{h},{h},{h},mCoBG_ATTRIBUTE_{attr if attr!=12 else "WATER"}}}}}; keep[{i}]={h};']
 collision_out += ['break;']
 tag='pc_dock_'+name
 out += [f'static const PC_TreeSourceLight {tag}_light[]={{']+['{{%ff,%ff,%ff},{255,255,255,255}},'%n for n in lighting]+['};',f'static Vtx {tag}_v[] ATTRIBUTE_ALIGN(32)={{']
 out += ['{{{%d,%d,%d},1,{%d,%d},{255,255,255,255}}},'%(x,y,z,round(uv[0]*128*32),round((1-uv[1])*64*32))for x,y,z,uv in vtx]+['};',f'static Gfx {tag}_dl[]={{','gsDPPipeSync(),','gsSPTexture(0,0,0,G_TX_RENDERTILE,G_ON),','gsDPSetTextureImage_Dolphin(G_IM_FMT_RGBA,G_IM_SIZ_32b,128,64,pc_dock_tex_0),','gsDPSetTile_Dolphin(G_DOLPHIN_TLUT_DEFAULT_MODE,0,0,GX_MIRROR,GX_REPEAT,0,0),','gsDPSetTileSize_Dolphin(G_TX_RENDERTILE,0,0,128,64),','gsDPSetCycleType(G_CYC_2CYCLE),','gsDPSetPrimColor(0,128,255,255,255,255),','gsDPSetCombineLERP(TEXEL0,0,SHADE,0,0,0,0,1,PRIMITIVE,0,COMBINED,0,0,0,0,COMBINED),','gsDPSetRenderMode(G_RM_FOG_SHADE_A,G_RM_AA_ZB_OPA_SURF2),','gsSPLoadGeometryMode(G_ZBUFFER|G_SHADE|G_FOG|G_SHADING_SMOOTH),']
 for start in range(0,len(vtx),30):
  n=min(30,len(vtx)-start);out += [f'gsSPVertex(&{tag}_v[{start}],{n},0),']+[f'gsSP1Triangle({i},{i+1},{i+2},0),'for i in range(0,n,3)]
 out+=['gsSPLoadGeometryMode(G_ZBUFFER|G_SHADE|G_FOG|G_LIGHTING|G_CULL_BACK|G_SHADING_SMOOTH),','gsSPEndDisplayList(),','};']
 records.append((prefix,tag,len(vtx)));audit.append({'acre':name,'source':'sobj_pier_v','vertices':len(vtx),'collision_patch_cells':raster,'bank_water_probe_counts':wet,'bank':bank,'tip':tip,'deck_radius':radius,'source_core_z':[entry,exit_z],'adaptation':'Original elbow footprint preserved at uniform native entry-width scale; original baked curvature removed. Native wood/water collision raster follows deck, old straight cells re-evaluated.'})
out+=['void pc_dock_prepare(void) {','extern int g_pc_tree_world,g_pc_terrain_season;','static unsigned generation;','if(!g_pc_tree_world)return;']
for slot,tag,count in records:
 out += [f'{slot}_slot[0].words.w1=_GBI_RUNTIME_PTR({tag}_dl);',f'{tag}_dl[2].words.w1=_GBI_RUNTIME_PTR(g_pc_terrain_season==9?pc_dock_tex_9:pc_dock_tex_0);',f'if(generation!=pc_tree_light_generation)pc_tree_light_vertices({tag}_v,{tag}_light,{count});']
out+=['generation=pc_tree_light_generation;','}']
collision_out+=['default: break;', '}', '}']
outline_out += ['static unsigned char pc_dock_block[16][16];',
 'static const unsigned char pc_dock_support[7][256]={'+','.join('{'+','.join(map(str,row))+'}'for row in support_rows)+'};',
 'static const float (*const pc_dock_outlines[7])[2]={'+','.join('pc_dock_outline_'+str(i)for i in range(7))+'};',
 'static const int pc_dock_outline_counts[7]={'+','.join(map(str,outline_counts))+'};']
collision_out=outline_out+collision_out+[
 'int pc_dock_support_unit(int ux,int uz) {',
 'extern int g_pc_tree_world; int bx=ux/16,bz=uz/16;',
 'if(!g_pc_tree_world || !mFI_CheckFieldData() || mFI_GET_TYPE(mFI_GetFieldId())!=mFI_FIELD_FG || ux<0 || uz<0 || bx>=16 || bz>=16)return 0;',
 'int index=pc_dock_block[bz][bx]; return index ? pc_dock_support[index-1][(uz%16)*16+ux%16] : 0;', '}',
 'int pc_dock_get_outline(float x,float z,const float (**points)[2],int* count,float* ox,float* oz) {',
 'extern int g_pc_tree_world; int bx=(int)(x/640.0f),bz=(int)(z/640.0f);',
 'if(!g_pc_tree_world || !mFI_CheckFieldData() || mFI_GET_TYPE(mFI_GetFieldId())!=mFI_FIELD_FG || x<0 || z<0 || bx>=16 || bz>=16)return 0;',
 'int index=pc_dock_block[bz][bx]; if(!index)return 0;',
 '*points=pc_dock_outlines[index-1]; *count=pc_dock_outline_counts[index-1]; *ox=bx*640.0f; *oz=bz*640.0f; return 1;', '}']

publish(ROOT/'src/game/pc_dock_collision.c_inc','\n'.join(collision_out)+'\n')
publish(ROOT/'pc/src/pc_docks.c_inc','\n'.join(out)+'\n');publish(R/'dock_source/fit_audit.json',json.dumps(audit,indent=2))
print('Generated',len(records),'original ocean dock replacements;',sum(n for _,_,n in records),'vertices')
