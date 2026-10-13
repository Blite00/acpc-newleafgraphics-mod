"""Close source camera-hidden post backs with original boundary UVs/materials."""
from collections import defaultdict
from close_post_perimeters import post_perimeter_strip
import math

def close_open_parts(vertices,max_horizontal=40):
    edges=defaultdict(list)
    key=lambda v:tuple(round(q,3)for q in v['position'])
    for i in range(0,len(vertices),3):
        tri=vertices[i:i+3]
        for a,b in zip(tri,tri[1:]+tri[:1]):
            if key(a)!=key(b):edges[tuple(sorted((key(a),key(b))))].append((a,b))
    boundary={edge:uses[0]for edge,uses in edges.items()if len(uses)==1}
    adj=defaultdict(set)
    for a,b in boundary:adj[a].add(b);adj[b].add(a)
    remaining=set(adj);added=[];count=0
    while remaining:
        todo=[remaining.pop()];group=set(todo)
        while todo:
            for q in adj[todo.pop()]:
                if q not in group:group.add(q);todo.append(q);remaining.discard(q)
        if not 3<=len(group)<=20 or any(len(adj[q])!=2 for q in group):continue
        if max(max(p[k]for p in group)-min(p[k]for p in group)for k in(0,2))>max_horizontal:continue
        start=min(group);ordered=[start];prev=None;cur=start
        while True:
            nxt=next(q for q in sorted(adj[cur]) if q!=prev)
            if nxt==start:break
            ordered.append(nxt);prev,cur=cur,nxt
        ring=[]
        for i,q in enumerate(ordered):
            pair=boundary[tuple(sorted((q,ordered[(i+1)%len(ordered)])))]
            ring.append(next(v for v in pair if key(v)==q))
        post=post_perimeter_strip(ring)
        if post is not None:
            added.extend(post);count+=1;continue
        center=[sum(p[k]for p in group)/len(group)for k in range(3)]
        uses=[v for edge,v in boundary.items()if edge[0]in group]
        center_uv=[sum(v['uv'][k]for edge in uses for v in edge)/(2*len(uses))for k in range(2)]
        for a,b in uses:
            ab=[a['position'][k]-b['position'][k]for k in range(3)]
            bc=[center[k]-b['position'][k]for k in range(3)]
            n=[ab[1]*bc[2]-ab[2]*bc[1],ab[2]*bc[0]-ab[0]*bc[2],ab[0]*bc[1]-ab[1]*bc[0]]
            length=math.sqrt(sum(q*q for q in n))
            if length<1e-5:continue
            n=[q/length for q in n]
            # Original edge UVs are preserved, continuing the existing wood.
            c={'position':center,'uv':center_uv,'normal':n,'color':a['color']}
            aa=dict(a,normal=n);bb=dict(b,normal=n)
            added.extend([bb,aa,c])
        count+=1
    return added,count
