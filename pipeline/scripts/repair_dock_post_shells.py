"""Add the absent eighth lower pier-post corner and its two wall facets."""
import math
from copy import deepcopy
from collections import Counter
from post_deprojection import identify_posts,position_key

def repair_dock_post_shells(source,closures,radius):
    vertices=source+closures;_,posts=identify_posts(vertices,radius);remove=set();added=[];audit=[]
    for post in posts:
        ids=post['vertex_indices'];original=[i for i in ids[::3] if i<len(source)]
        hi=max(math.hypot(*vertices[i]['position'][1:]) for i in ids)
        toptris=[i for i in original if all(math.hypot(*vertices[j]['position'][1:])>hi-1 for j in range(i,i+3))]
        counts=Counter(position_key(vertices[j]) for i in toptris for j in range(i,i+3));rim=[p for p,n in counts.items() if n==2]
        if len(toptris)!=8 or len(rim)!=8:continue
        sideids=[i for i in original if i not in toptris]
        topmap={};bottommap={};covered=set();low=[]
        for i in sideids:
            tri=vertices[i:i+3];tp=[position_key(v) for v in tri if position_key(v) in rim]
            if len(tp)==2:covered.add(frozenset(tp))
            for v in tri:
                p=position_key(v)
                if p in rim:topmap[p]=v
                else:low.append(v)
        unique={position_key(v):v for v in low}
        if len(unique)!=7:continue
        cx=sum(p[0]for p in rim)/8;ca=sum(math.atan2(p[2],p[1])for p in rim)/8
        rim.sort(key=lambda p:math.atan2(radius*(math.atan2(p[2],p[1])-ca),p[0]-cx))
        for p in rim:
            q=min(unique,key=lambda q:(q[0]-p[0])**2+(radius*(math.atan2(q[2],q[1])-math.atan2(p[2],p[1])))**2)
            if (q[0]-p[0])**2+(radius*(math.atan2(q[2],q[1])-math.atan2(p[2],p[1])))**2<4:bottommap[p]=unique[q]
        missing=[p for p in rim if p not in bottommap];assert len(missing)==1
        p=missing[0];k=rim.index(p);prev=rim[k-1];nxt=rim[(k+1)%8]
        def mid(a,b):
            v=deepcopy(a);v['uv']=[(x+y)*.5 for x,y in zip(a['uv'],b['uv'])];return v
        dx=sum(bottommap[q]['position'][0]-q[0]for q in bottommap)/7
        da=sum(math.atan2(bottommap[q]['position'][2],bottommap[q]['position'][1])-math.atan2(q[2],q[1])for q in bottommap)/7
        rr=sum(math.hypot(*v['position'][1:])for v in unique.values())/7
        a=math.atan2(p[2],p[1])+da;v=mid(bottommap[prev],bottommap[nxt]);v['position']=[p[0]+dx,rr*math.cos(a),rr*math.sin(a)];bottommap[p]=v
        v=mid(topmap[prev],topmap[nxt]);v['position']=list(p);topmap[p]=v
        def emit(tri):
            for v in tri:
                v=deepcopy(v);x,y,z=v['position'];a=math.atan2(z,y);nx=x-cx;nz=radius*(a-ca);d=math.hypot(nx,nz)
                v['normal']=[nx/d,-nz/d*math.sin(a),nz/d*math.cos(a)];added.append(v)
        walls=0
        for k,p in enumerate(rim):
            q=rim[(k+1)%8]
            if frozenset((p,q)) in covered:continue
            emit([topmap[p],bottommap[p],bottommap[q]]);emit([topmap[p],bottommap[q],topmap[q]]);walls+=2
        assert walls==4
        for k in range(1,7):
            tri=[deepcopy(bottommap[rim[q]])for q in [0,k+1,k]]
            for v in tri:
                x,y,z=v['position'];v['uv']=[2.2+(x-cx)*.01,.1+radius*(math.atan2(z,y)-ca)*.01]
            emit(tri)
        remove.update(i-len(source) for i in ids if i>=len(source))
        audit.append({'post':post['id'],'original_side_triangles':len(sideids),'top_corners':8,'old_lower_corners':7,'new_lower_corners':8,'replacement_wall_triangles':4})
    assert len(audit)==9,len(audit)
    return [v for i,v in enumerate(closures) if i not in remove]+added,audit

