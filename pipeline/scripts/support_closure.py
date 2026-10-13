"""Geometry repair: close omitted donor rear support faces only.
No executable asset writes occur when this module is imported.
"""
from collections import defaultdict
from copy import deepcopy
import math

def support_closure(vertices, rear_only=False, extra_depth=0.0):
    """Return new triangles down to the source's existing buried base plane.
    Original triangles/UVs are untouched; new backfaces reuse source atlas UVs.
    This repairs an open rear silhouette, not actor height or collision.
    """
    source_base=min(v['position'][1] for v in vertices)
    ground=source_base-extra_depth
    buried=[v for v in vertices if v['position'][1]<=source_base+0.25]
    edges=defaultdict(list)
    key=lambda v: tuple(round(c,3) for c in v['position'])
    for i in range(0,len(vertices),3):
        for a,b in [(0,1),(1,2),(2,0)]:
            va,vb=vertices[i+a],vertices[i+b]
            edges[tuple(sorted((key(va),key(vb))))].append((va,vb))
    added=[]
    def base(v):
        p=deepcopy(v);x,_,z=p['position'];p['position']=[x,ground,z]
        nearest=min(buried,key=lambda q:(q['position'][0]-x)**2+(q['position'][2]-z)**2)
        p['uv']=deepcopy(nearest['uv'])
        return p
    def triangle(a,b,c):
        u=[b['position'][k]-a['position'][k] for k in range(3)]
        v=[c['position'][k]-a['position'][k] for k in range(3)]
        n=[u[1]*v[2]-u[2]*v[1],u[2]*v[0]-u[0]*v[2],u[0]*v[1]-u[1]*v[0]]
        length=math.sqrt(sum(t*t for t in n))
        if length<1e-7:return
        for q in (a,b,c):
            q=deepcopy(q);q['normal']=[t/length for t in n];added.append(q)
    for instances in edges.values():
        if len(instances)!=1:continue
        a,b=instances[0]
        if rear_only and (a['position'][2]>=0 or b['position'][2]>=0):continue
        if max(a['position'][1],b['position'][1])<=ground+1e-5:continue
        qa,qb=base(a),base(b)
        # Opposite winding along the shared edge closes the original surface.
        triangle(b,a,qa);triangle(b,qa,qb)
    return added


def host_ground_support_depth(root):
    """Conservative buried skirt depth from actual host land triangle spans.
    No upper donor vertex moves. This covers the chord below the per-vertex
    cylinder, including the strongest allowed rolling setting and the full
    exported land height range; one world unit provides overlap.
    """
    import re,struct,json
    rel=(root/'foresta.rel').read_bytes()
    max_span=0.0;heights=[];limiting=None
    land={'grass_tex_dummy','earth_tex_dummy','cliff_tex_dummy','sand_tex_dummy','stone_tex_dummy'}
    for path in (root/'ACGC-PC-Port/src/data/field/bg/acre').glob('grd_s_*/*.c'):
        original=root/'bridge_source/native_sources'/path.name
        text=(original if original.exists() else path).read_text()
        match=re.search(r'pc_load_asset\("[^\"]+", \w+, 0x\w+, (0x\w+)',text)
        marker=f'extern Gfx {path.stem}_model[]'
        if not match or marker not in text:continue
        offset=int(match[1],16);text=text[text.index(marker):]
        cache={};left=0;texture=None
        for cmd,args in re.findall(r'(gs\w+)\((.*?)\),',re.sub(r'//[^\n]*','',text),re.S):
            if cmd.startswith('gsDPLoadTexture'):
                texture=args.split(',')[0].strip()
            elif cmd=='gsSPVertex':
                found=re.search(r'\[(\d+)\],\s*(\d+),\s*(\d+)',args)
                if not found:continue
                start,n,v0=map(int,found.groups())
                for k in range(n):cache[v0+k]=struct.unpack_from('>hhh',rel,offset+(start+k)*16)
            elif cmd.startswith('gsSPNTriangles'):
                values=list(map(int,re.findall(r'\d+',args)))
                if 'Init' in cmd:left=values.pop(0)
                n=min(left,len(values)//3)
                for k in range(n):
                    tri=[cache[q] for q in values[k*3:k*3+3]]
                    if texture not in land or len(set(tri))<3:continue
                    if max(v[1] for v in tri)!=min(v[1] for v in tri):continue
                    span=(max(v[2] for v in tri)-min(v[2] for v in tri))/16.0
                    heights.append(tri[0][1]/16.0)
                    if span>max_span:max_span=span;limiting=path.stem
                left-=n
    assert heights and max_span>0
    gx=(root/'ACGC-PC-Port/pc/src/pc_gx.c').read_text()
    main=(root/'ACGC-PC-Port/pc/src/pc_main.c').read_text()
    base_radius=float(re.search(r'radius=(\d+(?:\.\d+)?)f/g_pc_rolling_world_strength',gx)[1])
    max_strength=float(re.search(r'value > (\d+(?:\.\d+)?)f \? \1f',main)[1])
    radius=base_radius/max_strength
    height_range=max(heights)-min(heights)
    deficit=(radius+height_range)*(1-math.cos(max_span/(2*radius)))
    depth=math.ceil((deficit+1.0)*100)/100
    (root/'tree_source/support_depth_audit.json').write_text(json.dumps({
        'max_land_triangle_z_span':max_span,'limiting_acre':limiting,
        'exported_land_height_range':height_range,'minimum_supported_radius':radius,
        'max_supported_rolling_strength':max_strength,'maximum_chord_deficit':deficit,
        'overlap':1.0,'buried_extra_depth_world':depth,
        'original_donor_vertices_unchanged':True},indent=2))
    return depth
