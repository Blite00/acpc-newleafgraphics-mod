"""Read original native mound fans and their exact matching lower rim vertices."""
from pathlib import Path
import re,struct,json,collections
R=Path(__file__).resolve().parent;ROOT=R/'ACGC-PC-Port';rel=(R/'foresta.rel').read_bytes()
def parse(block,base):
 cache={};tris=[];left=0
 for name,args in re.findall(r'(gsSP\w+)\((.*?)\),',re.sub(r'//[^\n]*','',block),re.S):
  if name=='gsSPVertex':
   off,n,v0=map(int,re.search(r'\[(\d+)\],\s*(\d+),\s*(\d+)',args).groups())
   for k in range(n):cache[v0+k]=struct.unpack_from('>hhh',rel,base+(off+k)*16)+struct.unpack_from('>hh',rel,base+(off+k)*16+8)
  elif name.startswith('gsSPNTriangles'):
   nums=list(map(int,re.findall(r'\d+',args)))
   if 'Init' in name:left=nums.pop(0)
   used=min(left,len(nums)//3)
   for k in range(used):
    tri=[cache[i] for i in nums[k*3:k*3+3]]
    if len(set(v[:3] for v in tri))==3:tris.append(tri)
   left-=used
 return tris
records=[]
for p in sorted((ROOT/'src/data/field/bg/acre').glob('*/*.c')):
 s=p.read_text();load=re.search(r'pc_load_asset\("[^\"]+", (\w+), (0x\w+), (0x\w+)',s)
 if not load:continue
 meshes={'a':[],'b':[]}
 for hit in re.finditer(r'gsDPLoadTextureBlock_4b_Dolphin\(bush_([ab])_tex_dummy',s):
  tail=s[hit.start():];end=re.search(r'gsDPLoad(?:Texture|TLUT|Multi)|gsSPEndDisplayList',tail[hit.end()-hit.start():])
  if end:tail=tail[:hit.end()-hit.start()+end.start()]
  meshes[hit[1]]+=parse(tail,int(load[3],16))
 if not meshes['a']:continue
 edges=collections.Counter();oriented={}
 for tri in meshes['a']:
  for i in range(3):
   a,b=tri[i][:3],tri[(i+1)%3][:3];key=tuple(sorted((a,b)));edges[key]+=1;oriented[key]=(a,b)
 bottoms=collections.defaultdict(list)
 for tri in meshes['b']:
  for v in tri:bottoms[(v[0],v[2])].append(v[1])
 walls=[];missing=[]
 for edge,count in edges.items():
  if count!=1:continue
  a,b=oriented[edge];lower=[]
  for v in [a,b]:
   ys=[y for y in bottoms[(v[0],v[2])] if y<v[1]]
   lower.append((v[0],max(ys),v[2]) if ys else None)
  if all(lower):walls.append([a,b,lower[1],lower[0]])
  else:missing.append([a,b])
 records.append({'acre':p.parent.name,'walls':walls,'unmatched_edges':missing,'top_triangles':len(meshes['a']),'bottom_triangles':len(meshes['b'])})
(R/'foliage_source/native_mound_boundaries.json').write_text(json.dumps(records,indent=2))
print('acres',len(records),'walls',sum(len(x['walls']) for x in records),'unmatched',sum(len(x['unmatched_edges'])for x in records))
