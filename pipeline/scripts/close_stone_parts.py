"""Close the donor stone bridge's camera-hidden back faces along its arch."""
from collections import defaultdict
from repair_bridge_closure_uvs import repair_closure_uvs
import math


def close_stone_parts(vertices):
    key=lambda v:tuple(round(q,3) for q in v['position'])
    edges=defaultdict(list)
    for i in range(0,len(vertices),3):
        tri=vertices[i:i+3]
        for a,b in zip(tri,tri[1:]+tri[:1]):
            if key(a)!=key(b):edges[tuple(sorted((key(a),key(b))))].append((a,b))
    boundary={e:u[0] for e,u in edges.items() if len(u)==1}
    adj=defaultdict(set)
    for a,b in boundary:adj[a].add(b);adj[b].add(a)
    remaining=set(adj);added=[];counts=[]
    def emit(a,b,c,underside=False):
        ab=[b['position'][k]-a['position'][k] for k in range(3)]
        ac=[c['position'][k]-a['position'][k] for k in range(3)]
        n=[ab[1]*ac[2]-ab[2]*ac[1],ab[2]*ac[0]-ab[0]*ac[2],ab[0]*ac[1]-ab[1]*ac[0]]
        length=math.sqrt(sum(q*q for q in n))
        if length<1e-7:return
        n=[q/length for q in n]
        # Renderer is two-sided; light newly supplied backs outwards.
        if (underside and n[1]>0) or (not underside and n[2]>0):n=[-q for q in n]
        added.extend(dict(v,normal=n) for v in (a,b,c))
    def original(a,b):
        va,vb=boundary[tuple(sorted((a,b)))]
        return (va,vb) if key(va)==a else (vb,va)
    def sample(chain,ts,t):
        for i in range(len(ts)-1):
            if t<=ts[i+1]+1e-8:
                a,b=original(chain[i],chain[i+1]);f=(t-ts[i])/(ts[i+1]-ts[i])
                return dict(a,position=[a['position'][k]+f*(b['position'][k]-a['position'][k]) for k in range(3)],uv=[a['uv'][k]+f*(b['uv'][k]-a['uv'][k]) for k in range(2)])
        raise AssertionError(t)
    while remaining:
        start=min(remaining);loop=[start];prev=None;cur=start
        while True:
            assert len(adj[cur])==2,'Nonmanifold stone boundary'
            nxt=next(q for q in sorted(adj[cur]) if q!=prev)
            if nxt==start:break
            loop.append(nxt);prev,cur=cur,nxt
        remaining.difference_update(loop)
        before=len(added)
        if len(loop)==4:
            # The two small rail end caps are convex planar quads.
            vs=[original(loop[i],loop[(i+1)%4])[0] for i in range(4)]
            emit(vs[0],vs[1],vs[2]);emit(vs[0],vs[2],vs[3])
        else:
            # Both large openings are symmetric across source X=16. Split at
            # the centerline and span matching stations across the underside.
            # This follows its folded arch profile instead of spanning the
            # intentional open arch with one broad, flat triangle fan.
            center=[i for i,p in enumerate(loop) if abs(p[0]-16)<.01]
            assert len(center)==2,('Unexpected stone underside',loop)
            a,b=center
            left=loop[a:b+1];right=[loop[a]]+list(reversed(loop[b:]+loop[:a]))
            assert right[-1]==left[-1]
            def stations(chain):
                out=[0.0]
                for p,q in zip(chain,chain[1:]):out.append(out[-1]+math.dist(p,q))
                return [v/out[-1] for v in out]
            lt,rt=stations(left),stations(right)
            ts=sorted(set(lt+rt))
            for t0,t1 in zip(ts,ts[1:]):
                l0,l1=sample(left,lt,t0),sample(left,lt,t1)
                r0,r1=sample(right,rt,t0),sample(right,rt,t1)
                emit(l0,r0,r1,True);emit(l0,r1,l1,True)
        counts.append((len(loop),(len(added)-before)//3))
    assert len(counts)==4,counts
    repair_closure_uvs(vertices,added)
    return added,counts
