"""Identify connected donor pillars and undo their baked cylindrical coordinates."""
from collections import defaultdict
import math


def position_key(v):return tuple(round(q,3) for q in v['position'])


def identify_posts(vertices,radius):
    owners=defaultdict(set);adj=defaultdict(set)
    for i in range(0,len(vertices),3):
        for v in vertices[i:i+3]:owners[position_key(v)].add(i)
    for ids in owners.values():
        for i in ids:adj[i].update(ids)
    remaining=set(range(0,len(vertices),3));lookup={};posts=[]
    while remaining:
        group={min(remaining)};remaining-=group;todo=list(group)
        while todo:
            for i in sorted(adj[todo.pop()] & remaining):remaining.remove(i);group.add(i);todo.append(i)
        points=sorted({position_key(v) for i in group for v in vertices[i:i+3]})
        radial=[math.hypot(y,z) for x,y,z in points];arc=[radius*math.atan2(z,y) for x,y,z in points]
        height=max(radial)-min(radial);width=max(x for x,y,z in points)-min(x for x,y,z in points);depth=max(arc)-min(arc)
        if height<24 or max(width,depth)>.85*height:continue
        top=[p for p,r in zip(points,radial) if r>max(radial)-min(5.0,height*.1)]
        post={'id':len(posts),'anchor_x':sum(p[0] for p in top)/len(top),
            'anchor_z':sum(p[2] for p in top)/len(top),
            'anchor_angle':sum(math.atan2(p[2],p[1]) for p in top)/len(top),
            'height':height,'triangles':len(group),'vertex_indices':[i+k for i in sorted(group) for k in range(3)]}
        posts.append(post)
        for point in points:lookup[point]=post
    return lookup,posts


def unrolled_z(y,z,post,radius):
    # Keep the top attachment in place; remove only height-dependent raw-Z
    # motion introduced by the donor's baked cylindrical projection.
    return post['anchor_z']+radius*(math.atan2(z,y)-post['anchor_angle'])


def unrolled_normal(normal,y,z,radius):
    nx,ny,nz=normal;angle=math.atan2(z,y);c=math.cos(angle);s=math.sin(angle)
    # Inverse transpose of (radial height, R*angle), not just a rotation.
    return nx,ny*c+nz*s,(-ny*s+nz*c)*math.hypot(y,z)/radius
