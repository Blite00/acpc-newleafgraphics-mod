"""Fit only native leaf-render vertices to their matching native ground floor.
Collision, acre layouts, floor geometry and source texture coordinates are untouched.
"""
from pathlib import Path
import re, struct, collections, math, json
R=Path(__file__).resolve().parent
ROOT=R/'ACGC-PC-Port'
rel=(R/'foresta.rel').read_bytes()
out=['/* Generated render-only ground-cover height/normal patches. */',
     'typedef struct { unsigned short index; short y; signed char nx,ny,nz; } PCFoliageVertexPatch;']
tables=[];audit=[]
for p in sorted((ROOT/'src/data/field/bg/acre').glob('*/*.c')):
 s=p.read_text(encoding='utf-8')
 load=re.search(r'pc_load_asset\("([^\"]+)", (\w+), (0x\w+), (0x\w+)',s)
 if not load or 'bush_a_tex_dummy' not in s: continue
 cache={};left=0;kind='other';tris=collections.defaultdict(list)
 for name,args in re.findall(r'(gs\w+)\((.*?)\),',re.sub(r'//[^\n]*','',s),re.S):
  if name.startswith('gsDPLoadTexture'):
   kind='a' if 'bush_a_tex_dummy' in args else 'b' if 'bush_b_tex_dummy' in args else 'other'
  elif name=='gsSPVertex':
   off,n,v0=map(int,re.search(r'\[(\d+)\],\s*(\d+),\s*(\d+)',args).groups())
   for k in range(n): cache[v0+k]=off+k
  elif name.startswith('gsSPNTriangles'):
   nums=list(map(int,re.findall(r'\d+',args)))
   if 'Init' in name:left=nums.pop(0)
   used=min(left,len(nums)//3)
   for k in range(used):
    tri=tuple(cache[i]for i in nums[k*3:k*3+3])
    if len(set(tri))==3:tris[kind].append(tri)
   left-=used
 base=int(load[4],16);size=int(load[3],16)
 verts=[struct.unpack_from('>hhh',rel,base+i)for i in range(0,size,16)]
 normals=[struct.unpack_from('>bbb',rel,base+i+12)for i in range(0,size,16)]
 ids=lambda key:{i for t in tris[key]for i in t}
 assert not ids('a')&(ids('b')|ids('other')), (p.stem,'shared material vertex')
 # Weld the native fan's duplicated UV vertices before finding each outline.
 positions={verts[i] for i in ids('a')}
 adjacency=collections.defaultdict(set);edges=collections.Counter()
 for tri in tris['a']:
  points=[verts[i]for i in tri]
  for a,b in zip(points,points[1:]+points[:1]):
   if a==b:continue
   adjacency[a].add(b);adjacency[b].add(a)
   edges[tuple(sorted((a,b)))]+=1
 components=[];unseen=set(positions)
 while unseen:
  component={unseen.pop()};stack=list(component)
  while stack:
   for neighbor in adjacency[stack.pop()]:
    if neighbor not in component:component.add(neighbor);stack.append(neighbor)
  unseen-=component;components.append(component)
 def edge_distance(pos,a,b):
  dx=b[0]-a[0];dz=b[2]-a[2];length2=dx*dx+dz*dz
  t=max(0,min(1,((pos[0]-a[0])*dx+(pos[2]-a[2])*dz)/length2)) if length2 else 0
  return math.hypot(pos[0]-a[0]-t*dx,pos[2]-a[2]-t*dz)
 relief={};flat_components=0
 for component in components:
  boundary=[edge for edge,count in edges.items() if count==1 and edge[0] in component]
  assert boundary,(p.stem,'closed leaf fan')
  distances={pos:min(edge_distance(pos,*edge)for edge in boundary)for pos in component}
  deepest=max(distances.values())
  if deepest<1e-6:flat_components+=1
  for pos,distance in distances.items():
   fraction=distance/deepest if deepest>1e-6 else 0
   # Native full footprint: 0.625-unit cutout fringe, gently domed 7.5-unit center.
   relief[pos]=10+110*math.sin(fraction*math.pi*.5)
 patches=[];clearances=[];new_positions={};ground_normals={}
 for i in sorted(ids('a')):
  x,y,z=verts[i];matches=[]
  for t in tris['b']:
   a,b,c=[verts[j]for j in t]
   det=(b[2]-c[2])*(a[0]-c[0])+(c[0]-b[0])*(a[2]-c[2])
   if abs(det)<1e-8:continue
   u=((b[2]-c[2])*(x-c[0])+(c[0]-b[0])*(z-c[2]))/det
   v=((c[2]-a[2])*(x-c[0])+(a[0]-c[0])*(z-c[2]))/det
   w=1-u-v
   if min(u,v,w)>=-1e-5:
    floor=u*a[1]+v*b[1]+w*c[1]
    n=[sum(weight*normals[j][axis]for weight,j in zip((u,v,w),t))for axis in range(3)]
    matches.append((floor,n))
  assert matches,(p.stem,i,'no native floor')
  floor,n=max(matches,key=lambda m:m[0])
  new_y=round(floor+relief[verts[i]])
  assert -32768<=new_y<=32767
  new_positions[verts[i]]=(x,new_y,z);ground_normals[verts[i]]=n
  clearances.append((new_y-floor)/16)
 # Area-weighted geometric normals give a soft, welded highlight on the dome.
 # They include the actual underlying terrain slope, not a global up vector.
 smooth=collections.defaultdict(lambda:[0.,0.,0.])
 for tri in tris['a']:
  points=[new_positions[verts[i]]for i in tri]
  a,b,c=points;ab=[b[j]-a[j]for j in range(3)];ac=[c[j]-a[j]for j in range(3)]
  n=[ab[1]*ac[2]-ab[2]*ac[1],ab[2]*ac[0]-ab[0]*ac[2],ab[0]*ac[1]-ab[1]*ac[0]]
  if n[1]<0:n=[-q for q in n]
  for i in tri:
   dst=smooth[verts[i]]
   for axis in range(3):dst[axis]+=n[axis]
 for i in sorted(ids('a')):
  n=smooth[verts[i]];length=math.sqrt(sum(q*q for q in n))
  if not length:n=ground_normals[verts[i]];length=math.sqrt(sum(q*q for q in n))
  normal=tuple(round(q*127/length)for q in n) if length else (0,127,0)
  patches.append((i,new_positions[verts[i]][1],*normal))
 if not patches:continue
 name='pc_low_foliage_'+p.stem
 out.append('static const PCFoliageVertexPatch '+name+'[] = {')
 out.extend('{%d,%d,%d,%d,%d},'%v for v in patches);out.append('};')
 tables.append((load[1],size,name,len(patches)))
 audit.append({'acre':p.stem,'leaf_vertices':len(patches),'floor_coverage':'all leaf vertices covered by native floor triangles',
               'other_material_vertices_changed':0,'dome_components':len(components),'components_without_interior_vertex':flat_components,'xz_footprint':'original unscaled coordinates','clearance_world':[min(clearances),max(clearances)]})
out+=['static void pc_low_foliage_patch(const char* path, void* data, unsigned int size) {',
      'extern int g_pc_tree_world;',
      'if (!g_pc_tree_world || !path || strncmp(path,"assets/field/bg/",16) != 0) return;',
      'static const struct { const char* path; unsigned int size; const PCFoliageVertexPatch* vertices; unsigned int count; } entries[] = {']
out+=['{"%s",%d,%s,%d},'%entry for entry in tables]
out+=['};','for (unsigned int e=0;e<sizeof(entries)/sizeof(entries[0]);e++) {',
      'if (entries[e].size != size || strcmp(entries[e].path,path) != 0) continue;',
      'Vtx* vertices=(Vtx*)data;',
      'for (unsigned int i=0;i<entries[e].count;i++) {',
      'const PCFoliageVertexPatch* p=&entries[e].vertices[i];',
      'if ((unsigned int)p->index>=size/sizeof(Vtx)) continue;',
      'vertices[p->index].n.ob[1]=p->y;',
      'vertices[p->index].n.n[0]=p->nx; vertices[p->index].n.n[1]=p->ny; vertices[p->index].n.n[2]=p->nz;',
      '}','return;','}','}']
for target,text in [(ROOT/'pc/src/pc_low_foliage.c_inc','\n'.join(out)+'\n'),
                    (R/'foliage_source/low_ground_cover_audit.json',json.dumps(audit,indent=2))]:
 temporary=target.with_suffix('.writing')
 temporary.write_text(text,encoding='utf-8');temporary.replace(target)
print('Generated',len(tables),'acre patches;',sum(t[3]for t in tables),'leaf vertices; all native floors covered; no material sharing.')
