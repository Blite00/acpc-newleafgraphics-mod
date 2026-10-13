"""Fit original donor bridges to native deck profiles; keep native collision."""
from pathlib import Path
import re,json,struct,math,subprocess,sys
from PIL import Image
from close_donor_parts import close_open_parts
from close_stone_parts import close_stone_parts
from close_wood_parts import close_wood_parts
from repair_timber_post_shells import repair_timber_post_shells
from timber_gap_strips import timber_gap_strips
from post_deprojection import identify_posts,position_key,unrolled_z,unrolled_normal
R=Path(__file__).resolve().parent;ROOT=R/'ACGC-PC-Port';rel=(R/'foresta.rel').read_bytes()

def write_generated(path,text):
    # Keep the previous artifact recoverable and publish complete UTF-8 files.
    if path.exists():
        backup=path.with_name(path.name+'.bridge-backup')
        backup.write_bytes(path.read_bytes())
    temporary=path.with_name(path.name+'.bridge-tmp')
    temporary.write_text(text,encoding='utf-8')
    temporary.replace(path)

# The generic Ohana OTexture Bitmap copy discards RGB when gloss alpha is zero.
# Decode these textures directly so opaque bridges retain their original albedo.
if '--skip-textures' not in sys.argv:
 subprocess.run(['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass','-File',str(R/'export_bridge_raw_textures.ps1')],check=True)
out=['/* Generated donor bridge geometry. Native deck profiles and footprints retained. */'];records=[];direction_records=[]
def rgba(im):
 data=[]
 for y in range(0,im.height,4):
  for x in range(0,im.width,4):
   v=[im.getpixel((x+i,y+j)) for j in range(4)for i in range(4)]
   # Donor alpha stores gloss, never cutout coverage. Preserve source PNGs
   # but upload opaque albedo so inherited host alpha state cannot punch holes.
   data.extend(c for r,g,b,a in v for c in (255,r));data.extend(c for r,g,b,a in v for c in (g,b))
 return data
for style in [0,2,3]:
 for snow in [0,9]:
  im=Image.open(R/f'bridge_source/fobj_bridge_{style:02}_n_s_season{snow:02}/tex_bridge.png').convert('RGBA');data=rgba(im)
  out += [f'static u8 pc_bridge_tex_{style}_{snow}[] ATTRIBUTE_ALIGN(32) = {{']+[','.join(map(str,data[i:i+32]))+','for i in range(0,len(data),32)]+['};']
def floor_at(tris,x,z,default):
 ys=[]
 for tri in tris:
  a,b,c=tri;den=(b[2]-c[2])*(a[0]-c[0])+(c[0]-b[0])*(a[2]-c[2])
  if abs(den)<1e-5:continue
  u=((b[2]-c[2])*(x-c[0])+(c[0]-b[0])*(z-c[2]))/den;v=((c[2]-a[2])*(x-c[0])+(a[0]-c[0])*(z-c[2]))/den
  if u>=-.001 and v>=-.001 and u+v<=1.001:ys.append(u*a[1]+v*b[1]+(1-u-v)*c[1])
 return max(ys) if ys else default
def parse(block,base):
 cache={};tris=[];left=0
 for name,args in re.findall(r'(gsSP\w+)\((.*?)\),',re.sub(r'//[^\n]*','',block),re.S):
  if name=='gsSPVertex':
   off,n,v0=map(int,re.search(r'\[(\d+)\],\s*(\d+),\s*(\d+)',args).groups())
   for k in range(n):cache[v0+k]=struct.unpack_from('>hhh',rel,base+(off+k)*16)+struct.unpack_from('>hh',rel,base+(off+k)*16+8)
  elif name.startswith('gsSPNTriangles'):
   nums=list(map(int,re.findall(r'\d+',args)))
   if 'Init' in name:left=nums.pop(0)
   for k in range(min(left,len(nums)//3)):
    tri=[cache[i]for i in nums[k*3:k*3+3]]
    if len(set(tri))==3:tris.append(tri)
   left-=min(left,len(nums)//3)
 return tris
def groups(tris):
 gs=[]
 for tri in tris:
  touching=[i for i,g in enumerate(gs)if any(v in {p for t in g for p in t}for v in tri)]
  new=[tri]
  for i in reversed(touching):new+=gs.pop(i)
  gs.append(new)
 # Rail/post islands belong to the deck whose horizontal footprint overlaps.
 change=True
 while change:
  change=False
  for i in range(len(gs)):
   a=[v for t in gs[i]for v in t]
   for j in range(i):
    b=[v for t in gs[j]for v in t]
    if all(min(v[k]for v in a)<=max(v[k]for v in b)+80 and min(v[k]for v in b)<=max(v[k]for v in a)+80 for k in [0,2]):
     gs[j]+=gs.pop(i);change=True;break
   if change:break
 return gs
def donor_ground_radius():
    # The extracted acre contains New Leaf's original cylindrical projection.
    ground=json.loads((R/'terrain_source/grd_F_0/grd_F_0.json').read_text())
    radii=[math.hypot(*v['position'][1:3]) for m in ground['meshes'] for v in m['vertices']]
    radius=sum(radii)/len(radii)
    assert max(abs(v-radius) for v in radii)<0.01, 'Donor ground is not the expected cylinder'
    return radius

def donor_ground_y(radius,z):
    assert abs(z)<radius
    return math.sqrt(radius*radius-z*z)

def donor_deck_contacts(tris,x,z0,z1,radius):
    # Solve the two crossings of the actual walkable deck and donor ground.
    # Mesh tips lie below ground and must not define the visible bank span.
    def clearance(z):
        y=floor_at(tris,x,z,float('nan'))
        assert math.isfinite(y), ('Missing donor centerline',z)
        return y-donor_ground_y(radius,z)
    roots=[];a=z0;fa=clearance(a)
    for i in range(1,1025):
        b=z0+(z1-z0)*i/1024;fb=clearance(b)
        if fa*fb<0:
            lo,hi=a,b;flo=fa
            for _ in range(40):
                mid=(lo+hi)/2;fm=clearance(mid)
                if flo*fm<=0:hi=mid
                else:lo=mid;flo=fm
            roots.append((lo+hi)/2)
        a,fa=b,fb
    assert len(roots)==2, ('Expected two bank contact points',roots)
    assert clearance(z0)<0 and clearance(z1)<0
    return roots

def donor_timber_deck_bounds(source):
    # Style03 has separated logs almost flush with the ground cylinder. Its
    # projecting underside supports are not bank contacts. Recover the real
    # walk surface from upward-facing triangles crossing the source centerline.
    positions=[v['position'] for v in source]
    center=(min(v[0] for v in positions)+max(v[0] for v in positions))/2
    deck=[]
    for i in range(0,len(source),3):
        tri=source[i:i+3]
        p=[v['position'] for v in tri]
        if min(v[0] for v in p)<=center<=max(v[0] for v in p) and sum(v['normal'][1] for v in tri)>0:
            deck.extend(p)
    assert deck
    return min(v[0] for v in deck),max(v[0] for v in deck),min(v[2] for v in deck),max(v[2] for v in deck)

def donor_recessed_wood_backing(source,z0,z1,reference):
    # The original separate planks remain visible. A narrow recessed layer
    # prevents open donor gaps revealing the host's much deeper river/cliff.
    # It uses original plank UVs/colors and enters the same fit/skin path.
    deck=[v for v in source if v['normal'][1]>.5 and abs(v['position'][1]-reference(v['position'][2]))<2.0]
    assert deck,'No donor plank walk surface'
    lo=min(v['position'][0]for v in deck)+1.0
    hi=max(v['position'][0]for v in deck)-1.0
    assert hi>lo
    def vertex(x,z):
        nearest=min(deck,key=lambda v:(v['position'][0]-x)**2+(v['position'][2]-z)**2)
        color=nearest['color'];rgb=[round(((color>>k)&255)*.65)for k in(16,8,0)]
        return {'position':[x,reference(z)-1.5,z], 'normal':[0,1,0],
                'uv':nearest['uv'][:], 'color':(255<<24)|(rgb[0]<<16)|(rgb[1]<<8)|rgb[2]}
    added=[]
    for i in range(32):
        a=z0+(z1-z0)*i/32;b=z0+(z1-z0)*(i+1)/32
        q=[vertex(lo,a),vertex(hi,a),vertex(hi,b),vertex(lo,b)]
        added.extend([q[j]for j in(0,2,1,0,3,2)])
    return added

for p in sorted((ROOT/'src/data/field/bg/acre').glob('*/*.c')):
 s=p.read_text()
 if 'PC_DONOR_BRIDGE_SECTION' in s:
  # Regeneration uses exact stored original source.
  s=(R/'bridge_source/native_sources'/p.name).read_text()
 hit=re.search(r'gsDPLoadTextureBlock_4b_Dolphin\(bridge_([12])_tex_dummy',s)
 if not hit:continue
 start=hit.start();nxt=re.search(r'gsDPLoad(?:TLUT|Texture|Multi)',s[hit.end():]);lim=hit.end()+nxt.start() if nxt else len(s)
 calls=list(re.finditer(r'gsSPNTriangles(?:Init)?_5b\(.*?\),',s[start:lim],re.S))
 if not calls:raise ValueError(p)
 end=start+calls[-1].end();block=s[start:end]
 load=re.search(r'pc_load_asset\("[^"]+", (\w+), (0x\w+), (0x\w+)',s);assert load
 native=parse(block,int(load[3],16));parts=groups(native);style=0 if hit[1]=='1'else 3
 idx=len(records);prefix=f'pc_bridge_{idx}';directions=[]
 source=json.loads((R/f'bridge_source/fobj_bridge_{style:02}_n_s_fobj_bridge_{style:02}_n_s/fobj_bridge_{style:02}_n_s.json').read_text())['meshes'][0]['vertices']
 sv=[v['position']for v in source];st=[sv[i:i+3]for i in range(0,len(sv),3)]
 sx0,sx1=min(v[0]for v in sv),max(v[0]for v in sv);sz0,sz1=min(v[2]for v in sv),max(v[2]for v in sv)
 radius=donor_ground_radius()
 if style==3:
  sx0,sx1,contact0,contact1=donor_timber_deck_bounds(source)
 else:
  contact0,contact1=donor_deck_contacts(st,(sx0+sx1)/2,sz0,sz1,radius)
 source_contact0,source_contact1=contact0,contact1
 if style==0:
  # Extend the original rail/deck tips farther into both banks. Retain the
  # original reference-height crossings so the walk surface stays continuous.
  embed=min(8.0,(contact1-contact0)*.08)
  contact0+=embed;contact1-=embed
  stone_closures,stone_closure_audit=close_stone_parts(source)
  source=source+stone_closures
 if style==3:
  closures,wood_audit=close_wood_parts(source)
  gap_strips,gap_audit=timber_gap_strips(source,lambda z:floor_at(st,(sx0+sx1)/2,z,donor_ground_y(radius,z)))
  closures+=gap_strips
  wood_audit['recessed_gap_strips']=gap_audit
  source,post_lookup,post_records,timber_post_audit=repair_timber_post_shells(source,closures,radius)
  write_generated(R/'bridge_source/timber_post_shell_audit.json',json.dumps(timber_post_audit,indent=2))
  (R/'bridge_source/timber_shell_audit.json').write_text(json.dumps(wood_audit,indent=2),encoding='utf-8')
 def bank_sink(z):
  if style!=0:return 0.0
  # Only the already-overlapping ends are buried. The complete crossing
  # between native bank endpoints retains its exact original fitted height.
  if z<contact0:t=(contact0-z)/(contact0-source_contact0)
  elif z>contact1:t=(z-contact1)/(source_contact1-contact1)
  else:return 0.0
  t=max(0.0,min(1.0,t))
  return 3.0*t*t*(3.0-2.0*t)
 if style!=3:post_lookup,post_records={},[]
 for post in post_records:
  reference=floor_at(st,(sx0+sx1)/2,post['anchor_z'],donor_ground_y(radius,post['anchor_z']))
  post['reference_radius']=math.hypot(reference,post['anchor_z'])
 transformed=[];lights=[]
 for target in parts:
  pts=[v for t in target for v in t];cx=sum(v[0]for v in pts)/len(pts);cz=sum(v[2]for v in pts)/len(pts)
  # Native stone uses U along its deck; native wooden planks use V along
  # the crossing and U across it. Derive the selected UV tangent from native
  # triangles, since asymmetric abutments and short spans defeat bbox/PCA.
  candidates=[]
  for tri in target:
   a,b,c=tri
   area=abs((b[0]-a[0])*(c[2]-a[2])-(b[2]-a[2])*(c[0]-a[0]))
   du1,dv1=b[3]-a[3],b[4]-a[4];du2,dv2=c[3]-a[3],c[4]-a[4]
   det=du1*dv2-du2*dv1
   if area>1 and abs(det)>1:
    if hit[1]=='2':
     dx=((c[0]-a[0])*du1-(b[0]-a[0])*du2)/det
     dz=((c[2]-a[2])*du1-(b[2]-a[2])*du2)/det
    else:
     dx=((b[0]-a[0])*dv2-(c[0]-a[0])*dv1)/det
     dz=((b[2]-a[2])*dv2-(c[2]-a[2])*dv1)/det
    length=math.hypot(dx,dz)
    if length>1e-6:candidates.append((area,dx/length,dz/length))
  assert candidates, (p.name,'No native deck UV direction')
  _,lx,lz=max(candidates);wx,wz=-lz,lx
  directions.append([round(lx,6),round(lz,6)])
  along=[v[0]*lx+v[2]*lz for v in pts];across=[v[0]*wx+v[2]*wz for v in pts]
  a0,a1=min(along),max(along);b0,b1=min(across),max(across);scale=(b1-b0)/(sx1-sx0);mid=(b0+b1)/2
  for v in source:
   x,y,z=v['position'];post=post_lookup.get(position_key(v));render_z=unrolled_z(y,z,post,radius) if post else z
   f=(render_z-contact0)/(contact1-contact0);a=a0+f*(a1-a0);b=b0+(x-sx0)/(sx1-sx0)*(b1-b0)
   tx,tz=a*lx+b*wx,a*lz+b*wz
   sourcefloor=floor_at(st,(sx0+sx1)/2,z,donor_ground_y(radius,z))
   # Clamp the native deck query to its existing bank endpoints. The
   # walkable span stays exactly on native collision; only buried tips extend.
   deck_a=max(a0,min(a1,a))
   nativefloor=floor_at(target,deck_a*lx+mid*wx,deck_a*lz+mid*wz,max(q[1]for q in pts))
   reference=sourcefloor if source_contact0<=z<=source_contact1 else donor_ground_y(radius,z)
   ty=nativefloor+(y-reference-bank_sink(z))*scale
   if post:
    anchor_a=a0+(post['anchor_z']-contact0)/(contact1-contact0)*(a1-a0)
    anchor_a=max(a0,min(a1,anchor_a))
    post_floor=floor_at(target,anchor_a*lx+mid*wx,anchor_a*lz+mid*wz,max(q[1]for q in pts))
    ty=post_floor+(math.hypot(y,z)-post['reference_radius']-bank_sink(post['anchor_z']))*scale
   transformed.append((round(tx),round(ty),round(tz),v['uv'],v['color']))
   # Retargeting changes deck slope as well as scale. Apply the inverse
   # transpose of that full deformation; scale-only normals incorrectly
   # retained the donor arch on the now native-profile stone deck.
   def vertical_offset(q):
    fraction=(q-contact0)/(contact1-contact0)
    alongq=a0+fraction*(a1-a0)
    clamped=max(a0,min(a1,alongq))
    host=floor_at(target,clamped*lx+mid*wx,clamped*lz+mid*wz,max(p[1]for p in pts))
    ref=floor_at(st,(sx0+sx1)/2,q,donor_ground_y(radius,q)) if source_contact0<=q<=source_contact1 else donor_ground_y(radius,q)
    return host-(ref+bank_sink(q))*scale
   # Stay within the current face region at bank boundaries.
   eps=.01
   derivative=(vertical_offset(z+eps)-vertical_offset(z-eps))/(2*eps)
   if post:
    nx,ny,nz=unrolled_normal(v['normal'],y,z,radius);nx/=scale;ny/=scale;nz/=(a1-a0)/(contact1-contact0)
   else:
    nx,ny,nz=v['normal'];nz=(nz-ny*derivative/scale)/((a1-a0)/(contact1-contact0));nx/=scale;ny/=scale
   length=math.sqrt(nx*nx+ny*ny+nz*nz)or 1
   lights.append(((nx*wx+nz*lx)/length,ny/length,(nx*wz+nz*lz)/length,v['color']))
 count=len(transformed);out += [f'static const PC_TreeSourceLight {prefix}_light[] = {{']
 for nx,ny,nz,color in lights:out+=['{{%ff,%ff,%ff},{%s}},'%(nx,ny,nz,','.join(str((color>>k)&255)for k in [16,8,0,24]))]
 out+=['};',f'static Vtx {prefix}_v[] ATTRIBUTE_ALIGN(32) = {{']
 im=Image.open(R/f'bridge_source/fobj_bridge_{style:02}_n_s_season00/tex_bridge.png');w,h=im.size
 for x,y,z,uv,color in transformed:out+=['{{{%d,%d,%d},1,{%d,%d},{%s}}},'%(x,y,z,round(uv[0]*w*32),round((1-uv[1])*h*32),','.join(str((color>>k)&255)for k in [16,8,0,24]))]
 out+=['};',f'static Gfx {prefix}_dl[] = {{','gsDPPipeSync(),','gsSPTexture(0,0,0,G_TX_RENDERTILE,G_ON),',f'gsDPSetTextureImage_Dolphin(G_IM_FMT_RGBA,G_IM_SIZ_32b,{w},{h},pc_bridge_tex_{style}_0),','gsDPSetTile_Dolphin(G_DOLPHIN_TLUT_DEFAULT_MODE,0,0,GX_MIRROR,GX_MIRROR,0,0),',f'gsDPSetTileSize_Dolphin(G_TX_RENDERTILE,0,0,{w},{h}),','gsDPSetCycleType(G_CYC_2CYCLE),','gsDPSetPrimColor(0,128,255,255,255,255),','gsDPSetCombineLERP(TEXEL0,0,SHADE,0,0,0,0,1,PRIMITIVE,0,COMBINED,0,0,0,0,COMBINED),','gsDPSetRenderMode(G_RM_FOG_SHADE_A,G_RM_AA_ZB_OPA_SURF2),','gsDPSetAlphaCompare(G_AC_NONE),','gsSPLoadGeometryMode(G_ZBUFFER|G_SHADE|G_FOG|G_SHADING_SMOOTH),']
 for base in range(0,count,30):
  n=min(30,count-base);out+=[f'gsSPVertex(&{prefix}_v[{base}],{n},0),']+[f'gsSP1Triangle({j},{j+1},{j+2},0),'for j in range(0,n,3)]
 out+=['gsSPLoadGeometryMode(G_ZBUFFER|G_SHADE|G_FOG|G_LIGHTING|G_CULL_BACK|G_SHADING_SMOOTH),','gsSPEndDisplayList(),','};',f'extern Gfx {prefix}_slot[];',f'extern Gfx {prefix}_native[];']
 # The source state surrounding the replaced triangle section remains verbatim.
 (R/'bridge_source/native_sources').mkdir(exist_ok=True)
 if '--geometry-only' not in sys.argv: (R/'bridge_source/native_sources'/p.name).write_text(s)
 declaration=f'\n#ifdef TARGET_PC\n/* PC_DONOR_BRIDGE_SECTION: original crossing collision remains native. */\nGfx {prefix}_native[] = {{\n    {block}\n    gsSPEndDisplayList(),\n}};\nGfx {prefix}_slot[] = {{gsSPDisplayList({prefix}_native),gsSPEndDisplayList()}};\n#endif\n'
 loc=s.rfind('extern Gfx ',0,start)
 modified=s[:start]+f'#ifdef TARGET_PC\n    gsSPDisplayList({prefix}_slot),\n#else\n    '+block+'\n#endif'+s[end:]
 modified=modified[:loc]+declaration+modified[loc:]
 if '--geometry-only' not in sys.argv:p.write_text(modified)
 records.append((prefix,count,style,p.stem,len(parts)))
 direction_records.append({'acre':p.stem,'directions':directions})
out+=['void pc_bridge_prepare(void) {','extern int g_pc_terrain_season, g_pc_tree_world;','static unsigned generation;','int snow=g_pc_terrain_season==9;']
for prefix,count,style,name,n in records:
 out += [f'{prefix}_slot[0].words.w1=_GBI_RUNTIME_PTR(g_pc_tree_world?{prefix}_dl:{prefix}_native);',f'{prefix}_dl[2].words.w1=_GBI_RUNTIME_PTR(snow?pc_bridge_tex_{style}_9:pc_bridge_tex_{style}_0);',f'if(generation!=pc_tree_light_generation) pc_tree_light_vertices({prefix}_v,{prefix}_light,{count});']
out+=['generation=pc_tree_light_generation;','}']
write_generated(ROOT/'pc/src/pc_bridges.c_inc','\n'.join(out)+'\n')
write_generated(R/'bridge_source/fit_audit.json',json.dumps(records,indent=2))
write_generated(R/'bridge_source/direction_audit.json',json.dumps(direction_records,indent=2))
print('Generated',len(records),'fixed bridge acre replacements,',sum(r[4]for r in records),'bridge components')

