"""Retarget donor wooden bridge to the native four-matrix suspension rig."""
from pathlib import Path
from post_deprojection import identify_posts,position_key,unrolled_z,unrolled_normal
from repair_bank_post_shells import repair_bank_post_shells,repair_tall_support_shells
exec((Path(__file__).with_name('generate_bridges.py')).read_text().split('for p in sorted')[0])
out=['/* Donor wooden suspension bridge retargeted to the native bridge joints. */']
s=(ROOT/'src/data/model/obj_s_bridgeA.c').read_text()
# Rest transforms in the native base-joint frame, from the six original joints.
# Matrix indices0..3 correspond to shown joints1,3,4,5.
a0=math.radians(-45.296631);a1=a0+math.radians(90.296631);a2=a1+math.radians(270.302124);a3=a2+math.radians(44.697876)
x1=2828+4000*math.cos(a0);y1=4000*math.sin(a0)
x2=x1+8000*math.cos(a1);y2=y1+8000*math.sin(a1)
x3=x2+4000*math.cos(a2);y3=y2+4000*math.sin(a2)
mat=[(0,0,0),(x1,y1,a1),(x2,y2,a2),(x3,y3,a3)]
base=0x7EFA20;native=[];native_uv=[];points=[]
for name in ['base','step2','step3','step4']:
 block=re.search(r'Gfx obj_s_bridgeA_'+name+r'_model\[\] = \{(.*?)\n\};',s,re.S)[1]
 cache={};uv_cache={};matrix=0 if name=='base'else {'step2':1,'step3':2,'step4':3}[name];left=0
 for cmd,args in re.findall(r'(gsSP\w+)\((.*?)\),',re.sub(r'//[^\n]*','',block),re.S):
  if cmd=='gsSPMatrix':
   match=re.search(r'\[(\d+)\]',args);matrix=int(match[1])if match else 0
  elif cmd=='gsSPVertex':
   h=re.search(r'\[(\d+)\],\s*(\d+),\s*(\d+)',args)
   off,n,v0=map(int,h.groups())if h else (0,*map(int,re.findall(r',\s*(\d+)',args)))
   for k in range(n):
    x,y,z=struct.unpack_from('>hhh',rel,base+(off+k)*16);tx,ty,a=mat[matrix];c=math.cos(a);sn=math.sin(a)
    pos=(x*c-y*sn+tx,x*sn+y*c+ty,z);cache[v0+k]=pos;uv_cache[v0+k]=pos+struct.unpack_from('>hh',rel,base+(off+k)*16+8);points.append((pos,matrix))
  elif cmd.startswith('gsSPNTriangles'):
   nums=list(map(int,re.findall(r'\d+',args)))
   if 'Init' in cmd:left=nums.pop(0)
   for k in range(min(left,len(nums)//3)):
    native.append([cache[i]for i in nums[k*3:k*3+3]])
    native_uv.append([uv_cache[i]for i in nums[k*3:k*3+3]])
   left-=min(left,len(nums)//3)
# The native animated wooden deck also runs along texture V. In its rig's
# base frame V is +X, so the existing donorZ -> nativeX fit is already correct;
# do not add the fixed-acre quarter-turn on top of the native root rotation.
crossing_candidates=[]
for tri in native_uv:
 a,b,c=tri
 area=abs((b[0]-a[0])*(c[2]-a[2])-(b[2]-a[2])*(c[0]-a[0]))
 du1,dv1=b[3]-a[3],b[4]-a[4];du2,dv2=c[3]-a[3],c[4]-a[4]
 det=du1*dv2-du2*dv1
 if area>1 and abs(det)>1:
  dx=((c[0]-a[0])*du1-(b[0]-a[0])*du2)/det
  dz=((c[2]-a[2])*du1-(b[2]-a[2])*du2)/det
  length=math.hypot(dx,dz)
  if length>1e-6:crossing_candidates.append((area,dx/length,dz/length))
_,deck_x,deck_z=max(crossing_candidates)
assert abs(deck_x-1)<1e-6 and abs(deck_z)<1e-6, 'Animated rig no longer matches its native V crossing axis'
source=json.loads((R/'bridge_source/fobj_bridge_02_n_s_fobj_bridge_02_n_s/fobj_bridge_02_n_s.json').read_text())['meshes'][0]['vertices'];sv=[v['position']for v in source];st=[sv[i:i+3]for i in range(0,len(sv),3)]
sx0,sx1=min(v[0]for v in sv),max(v[0]for v in sv);sz0,sz1=min(v[2]for v in sv),max(v[2]for v in sv)
pts=[v for t in native for v in t];x0,x4=min(v[0]for v in pts),max(v[0]for v in pts);z0,z1=min(v[2]for v in pts),max(v[2]for v in pts);scale=(z1-z0)/(sx1-sx0)
radius=donor_ground_radius();contact0,contact1=donor_deck_contacts(st,(sx0+sx1)/2,sz0,sz1,radius)
post_closures,wood_audit=close_wood_parts(source,style=2)
original_count=len(source)
source=source+post_closures
source,tall_shell_audit=repair_tall_support_shells(source,radius,original_count)
write_generated(R/'bridge_source/tall_post_shell_audit.json',json.dumps(tall_shell_audit,indent=2))
source,bank_shell_audit=repair_bank_post_shells(source,radius)
write_generated(R/'bridge_source/bank_post_shell_audit.json',json.dumps(bank_shell_audit,indent=2))
(R/'bridge_source/animated_shell_audit.json').write_text(json.dumps(wood_audit,indent=2),encoding='utf-8')
post_lookup,post_records=identify_posts(source,radius)
for post in post_records:
 ax=x0+(post['anchor_z']-sz0)/(sz1-sz0)*(x4-x0)
 az=z0+(post['anchor_x']-sx0)/(sx1-sx0)*(z1-z0)
 ay=floor_at(native,ax,0,0)
 _,post['bone']=min(points,key=lambda p:(p[0][0]-ax)**2+(p[0][2]-az)**2+.25*(p[0][1]-ay)**2)
 anchor_x=x0+(post['anchor_z']-contact0)/(contact1-contact0)*(x4-x0)
 post['native_y']=floor_at(native,max(x0,min(x4,anchor_x)),0,0)
 ref=floor_at(st,(sx0+sx1)/2,post['anchor_z'],donor_ground_y(radius,post['anchor_z']))
 post['reference_radius']=math.hypot(ref,post['anchor_z'])
verts=[];bones=[];lights=[];old_bones=[]
for v in source:
 x,y,z=v['position'];post=post_lookup.get(position_key(v))
 # Preserve exact pre-embedding skin ownership. Changing the fitted tips
 # must not move a support to a different animated suspension matrix.
 old_x=x0+(z-sz0)/(sz1-sz0)*(x4-x0);zz=z0+(x-sx0)/(sx1-sx0)*(z1-z0)
 sf=floor_at(st,(sx0+sx1)/2,z,480)
 old_y=floor_at(native,old_x,0,0)+(y-sf)*scale
 _,bone=min(points,key=lambda p:(p[0][0]-old_x)**2+(p[0][2]-zz)**2+.25*(p[0][1]-old_y)**2)
 old_bones.append(bone)
 if post:bone=post['bone']
 # Fit the visible deck between native contact points, bury original tips
 # under the banks, and retain the native centerline rest-height profile.
 render_z=unrolled_z(y,z,post,radius) if post else z
 f=(render_z-contact0)/(contact1-contact0);xx=x0+f*(x4-x0)
 floor=floor_at(native,max(x0,min(x4,xx)),0,0)
 reference=sf if 0<=f<=1 else donor_ground_y(radius,z)
 yy=post['native_y']+(math.hypot(y,z)-post['reference_radius'])*scale if post else floor+(y-reference)*scale
 tx,ty,a=mat[bone];c=math.cos(a);sn=math.sin(a);px=(xx-tx)*c+(yy-ty)*sn;py=-(xx-tx)*sn+(yy-ty)*c
 verts.append((round(px),round(py),round(zz),v['uv'],v['color']));bones.append(bone)
 nx,ny,nz=v['normal']
 if post:
  nx,ny,nz=unrolled_normal(v['normal'],y,z,radius);nx/=scale;ny/=scale;nz/=(x4-x0)/(contact1-contact0)
 length=math.sqrt(nx*nx+ny*ny+nz*nz)or 1
 # Base actor points diagonally: rotate donor normal into its rest-world frame.
 bx,by,bz=nz/length,ny/length,nx/length;c=math.cos(-3*math.pi/4);sn=math.sin(-3*math.pi/4)
 lights.append((bx*c+bz*sn,by,-bx*sn+bz*c,v['color']))
assert all(bones[i]==old_bones[i] for i,v in enumerate(source) if position_key(v) not in post_lookup), 'Non-post skin ownership changed'
for post in post_records:
 post['observed_bones']=sorted({bones[i] for i in post['vertex_indices']})
 post['source_and_closure_vertices']=len(post['vertex_indices'])
 assert post['observed_bones']==[post['bone']], 'Pillar has mixed bones'
write_generated(R/'bridge_source/rigid_post_audit.json',json.dumps([{k:v for k,v in p.items() if k!='vertex_indices'} for p in post_records],indent=2))
(R/'bridge_source/animated_embed_audit.json').write_text(json.dumps({'native_crossing_texture_axis':'V','native_crossing_direction':[deck_x,deck_z],'donor_style':2,'vertices':len(verts),'bone_counts':{b:bones.count(b)for b in set(bones)},'ownership_unchanged':bones==old_bones,'non_post_ownership_unchanged':True,'all_pillars_rigid':True,'source_contacts':[contact0,contact1],'source_ground_radius':radius},indent=2))
out+=['static const PC_TreeSourceLight pc_bridge_actor_light[] = {']
for nx,ny,nz,col in lights:out+=['{{%ff,%ff,%ff},{%s}},'%(nx,ny,nz,','.join(str((col>>k)&255)for k in [16,8,0,24]))]
out+=['};','static Vtx pc_bridge_actor_v[] ATTRIBUTE_ALIGN(32) = {']
for x,y,z,uv,col in verts:out+=['{{{%d,%d,%d},0,{%d,%d},{%s}}},'%(x,y,z,round(uv[0]*64*32),round((1-uv[1])*256*32),','.join(str((col>>k)&255)for k in [16,8,0,24]))]
out+=['};','static Gfx pc_bridge_actor_dl[] = {','gsDPPipeSync(),','gsSPTexture(0,0,0,G_TX_RENDERTILE,G_ON),','gsDPSetTextureImage_Dolphin(G_IM_FMT_RGBA,G_IM_SIZ_32b,64,256,pc_bridge_tex_2_0),','gsDPSetTile_Dolphin(G_DOLPHIN_TLUT_DEFAULT_MODE,0,0,GX_MIRROR,GX_MIRROR,0,0),','gsDPSetTileSize_Dolphin(G_TX_RENDERTILE,0,0,64,256),','gsDPSetCycleType(G_CYC_2CYCLE),','gsDPSetPrimColor(0,128,255,255,255,255),','gsDPSetCombineLERP(TEXEL0,0,SHADE,0,0,0,0,1,PRIMITIVE,0,COMBINED,0,0,0,0,COMBINED),','gsDPSetRenderMode(G_RM_FOG_SHADE_A,G_RM_AA_ZB_OPA_SURF2),','gsDPSetAlphaCompare(G_AC_NONE),','gsSPLoadGeometryMode(G_ZBUFFER|G_SHADE|G_FOG|G_SHADING_SMOOTH),']
for i in range(0,len(verts),3):
 for j in range(3):out += [f'gsSPMatrix(&anime_6_mdl[{bones[i+j]}],G_MTX_NOPUSH|G_MTX_LOAD|G_MTX_MODELVIEW),',f'gsSPVertex(&pc_bridge_actor_v[{i+j}],1,{j}),']
 out+=['gsSP1Triangle(0,1,2,0),']
out+=['gsSPLoadGeometryMode(G_ZBUFFER|G_SHADE|G_FOG|G_LIGHTING|G_CULL_BACK|G_SHADING_SMOOTH),','gsSPEndDisplayList(),','};','Gfx* pc_animated_bridge_mesh(void) {','extern int g_pc_terrain_season;','static unsigned generation;','if(generation!=pc_tree_light_generation) { pc_tree_light_vertices(pc_bridge_actor_v,pc_bridge_actor_light,sizeof(pc_bridge_actor_v)/sizeof(Vtx));generation=pc_tree_light_generation; }','pc_bridge_actor_dl[2].words.w1=_GBI_RUNTIME_PTR(g_pc_terrain_season==9?pc_bridge_tex_2_9:pc_bridge_tex_2_0);','return pc_bridge_actor_dl;','}']
target=ROOT/'pc/src/pc_animated_bridge.c_inc';temporary=target.with_suffix('.writing')
write_generated(target,'\n'.join(out)+'\n')
print('Retargeted',len(verts),'vertices; native matrix assignments', {b:bones.count(b)for b in set(bones)})
