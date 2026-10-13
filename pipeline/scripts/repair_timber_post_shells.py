"""Restore style03 octagonal post walls from their intact upper perimeters."""
import math
from copy import deepcopy
from collections import defaultdict,Counter
import numpy as np
from post_deprojection import position_key

def repair_timber_post_shells(source,closures,radius):
    vertices=source+closures;owners=defaultdict(set)
    for i in range(0,len(vertices),3):
        for v in vertices[i:i+3]:owners[position_key(v)].add(i)
    left=set(range(0,len(vertices),3));removed=set();replacements={};audit=[];records=[]
    starts={312,396,846,882,918,936,954,990}
    while left:
        group={min(left)};left-=group;todo=list(group)
        while todo:
            i=todo.pop()
            for v in vertices[i:i+3]:
                q=owners[position_key(v)]&left;left-=q;group|=q;todo+=list(q)
        if min(group) not in starts:continue
        points={position_key(v):v for i in group for v in vertices[i:i+3]}
        hi=max(math.hypot(*p[1:])for p in points);lo=min(math.hypot(*p[1:])for p in points)
        toptris=[i for i in group if all(math.hypot(*v['position'][1:])>hi-4 for v in vertices[i:i+3])]
        edges=Counter(tuple(sorted((position_key(vertices[i+a]),position_key(vertices[i+b]))))for i in toptris for a,b in[(0,1),(1,2),(2,0)])
        rim=sorted({p for e,n in edges.items()if n==1 for p in e});n=len(rim);assert 8<=n<=10,(min(group),n)
        cx=sum(p[0]for p in rim)/n;ca=sum(math.atan2(p[2],p[1])for p in rim)/n
        rim.sort(key=lambda p:math.atan2(radius*(math.atan2(p[2],p[1])-ca),p[0]-cx))
        low=[p for p in points if math.hypot(*p[1:])<lo+1];assert len(low)==7
        bx=(min(p[0]for p in low)+max(p[0]for p in low))/2
        ba=(min(math.atan2(p[2],p[1])for p in low)+max(math.atan2(p[2],p[1])for p in low))/2
        sx=(max(p[0]for p in low)-min(p[0]for p in low))/(max(p[0]for p in rim)-min(p[0]for p in rim))
        sa=(max(math.atan2(p[2],p[1])for p in low)-min(math.atan2(p[2],p[1])for p in low))/(max(math.atan2(p[2],p[1])for p in rim)-min(math.atan2(p[2],p[1])for p in rim))
        top=[deepcopy(points[p])for p in rim];bottom=[];ut=[]
        tall=hi-lo>30;vt=.40599 if tall else .01137;vb=.06014 if tall else .10235
        for p,v in zip(rim,top):
            candidates=[w for i in group if i<len(source)for w in vertices[i:i+3]if position_key(w)==p]
            u=min(candidates,key=lambda w:abs(w['uv'][1]-vt))['uv'][0];ut.append(u)
            q=deepcopy(v);a=ba+(math.atan2(p[2],p[1])-ca)*sa;q['position']=[bx+(p[0]-cx)*sx,lo*math.cos(a),lo*math.sin(a)];bottom.append(q)
        shell=[]
        def emit(tri,center):
            q=np.array([v['position']for v in tri]);normal=np.cross(q[1]-q[0],q[2]-q[0]);normal/=np.linalg.norm(normal)
            if normal@(q.mean(axis=0)-center)<0:normal=-normal
            shell.extend(dict(deepcopy(v),normal=normal.tolist())for v in tri)
        center=np.mean([v['position']for v in top+bottom],axis=0)
        for k in range(n):
            j=(k+1)%n;u0,u1=ut[k],ut[j]
            if abs(u1-u0)>.4:u1=min([u1+2*d for d in(-1,0,1)]+[-u1+2*d for d in(-1,0,1)],key=lambda u:abs(u-u0))
            if abs(u1-u0)<.01:u1=u0+.1737
            quad=[deepcopy(top[k]),deepcopy(bottom[k]),deepcopy(bottom[j]),deepcopy(top[j])]
            for v,u,vv in zip(quad,[u0,u0,u1,u1],[vt,vb,vb,vt]):v['uv']=[u,vv]
            emit([quad[0],quad[1],quad[2]],center);emit([quad[0],quad[2],quad[3]],center)
        for k in range(1,n-1):
            tri=[deepcopy(bottom[q])for q in[0,k+1,k]]
            for v in tri:
                x,y,z=v['position'];v['uv']=[.2+(x-bx)*.008,.06+radius*(math.atan2(z,y)-ba)*.008]
            emit(tri,center)
        keep={i for t in toptris for i in range(t,t+3)};drop={i for t in group for i in range(t,t+3)}-keep
        removed|=drop;replacements[min(drop)]=shell
        record={'id':len(records),'anchor_x':cx,'anchor_z':sum(p[2]for p in rim)/n,'anchor_angle':ca,'height':hi-lo,'keys':{position_key(v)for v in shell}|{position_key(vertices[i])for i in keep}}
        records.append(record);audit.append({'source_first_vertex':min(group),'height':hi-lo,'top_corners':n,'old_lower_corners':7,'new_lower_corners':n,'top_cap_unchanged':True,'flat_outward_wall_normals':True})
    result=[]
    for i,v in enumerate(vertices):
        if i in replacements:result+=replacements[i]
        if i not in removed:result.append(v)
    assert len(records)==8
    lookup={key:p for p in records for key in p.pop('keys')}
    return result,lookup,records,audit
