"""Replace the donor bank posts' triangular lower shell with matching rim facets."""
from copy import deepcopy
import math
from post_deprojection import identify_posts,position_key

def repair_bank_post_shells(vertices,radius):
    _,posts=identify_posts(vertices,radius)
    replacement={};removed=set();audit=[]
    for post in posts:
        if not 24 < post['height'] < 33.0:continue
        indices=post['vertex_indices'];points={position_key(vertices[i]):vertices[i] for i in indices}
        radii={p:math.hypot(p[1],p[2]) for p in points};hi=max(radii.values());lo=min(radii.values())
        toptris=[i for i in indices[::3] if all(math.hypot(*vertices[j]['position'][1:])>hi-6 for j in range(i,i+3))]
        # True top cap center appears six times; perimeter vertices twice.
        from collections import Counter
        edges=Counter(tuple(sorted((position_key(vertices[i+a]),position_key(vertices[i+b])))) for i in toptris for a,b in [(0,1),(1,2),(2,0)])
        rim=sorted({p for e,n in edges.items() if n==1 for p in e});n=len(rim)
        assert n in (6,8),(post['id'],len(toptris),n)
        cx=sum(p[0] for p in rim)/n;ca=sum(math.atan2(p[2],p[1]) for p in rim)/n
        rim.sort(key=lambda p:math.atan2(radius*(math.atan2(p[2],p[1])-ca),p[0]-cx))
        top=[deepcopy(points[p]) for p in rim];bottom=[]
        for v in top:
            q=deepcopy(v);x,y,z=v['position'];a=math.atan2(z,y)
            q['position']=[x,lo*math.cos(a),lo*math.sin(a)];bottom.append(q)
        side=[]
        for k in range(n):
            j=(k+1)%n
            quad=[deepcopy(top[k]),deepcopy(bottom[k]),deepcopy(bottom[j]),deepcopy(top[j])]
            # One detailed donor bark facet per side, with identical vertical rope phase.
            for v,u,t in zip(quad,[1.631,1.631,1.9998,1.9998],[1,0,0,1]):
                v['uv']=[u,.0018+t*(.2341-.0018)]
                x,y,z=v['position'];a=math.atan2(z,y);nx=x-cx;nz=radius*(a-ca);length=math.hypot(nx,nz)
                v['normal']=[nx/length,-nz/length*math.sin(a),nz/length*math.cos(a)]
            for ids in [(0,1,2),(0,2,3)]:side.extend(deepcopy(quad[q]) for q in ids)
        # Hidden bottom is a planar polygon fan from an existing boundary corner.
        for k in range(1,n-1):
            for q in [0,k+1,k]:
                v=deepcopy(bottom[q]);x,y,z=v['position'];a=math.atan2(z,y)
                v['normal']=[0,-math.cos(a),-math.sin(a)];v['uv']=[1.8+(x-cx)*.005,.02+radius*(a-ca)*.005];side.append(v)
        keep={j for i in toptris for j in range(i,i+3)}
        remove=set(indices)-keep;removed.update(remove);replacement[min(remove)]=side
        audit.append({'post':post['id'],'old_bottom_corners':sum(r<lo+2 for r in radii.values()),'top_corners':n,'new_bottom_corners':n,'side_triangles':2*n,'top_cap_unchanged':True})
    result=[]
    for i,v in enumerate(vertices):
        if i in replacement:result.extend(replacement[i])
        if i not in removed:result.append(v)
    assert len(audit)==6
    return result,audit


def repair_tall_support_shells(vertices,radius,original_count):
    _,posts=identify_posts(vertices,radius);remove=set();added=[];audit=[]
    for post in posts:
        if not 61 < post['height'] < 63:continue
        original=[vertices[i] for i in post['vertex_indices'] if i<original_count]
        def nearest(u,v):return deepcopy(min(original,key=lambda q:abs(q['uv'][0]-u)+abs(q['uv'][1]-v)))
        rows=[]
        for va,vb,vc in [(.01021,.01021,.01021),(.09565,.09565,.09565),(.28256,.26561,.2524)]:
            a=nearest(2.56951,va);b=nearest(2.72739,vb);c=nearest(2.80388,vc)
            shared=nearest(2.86949,vc)
            if sum((x-y)**2 for x,y in zip(shared['position'],b['position']))<sum((x-y)**2 for x,y in zip(shared['position'],a['position'])):a,b=b,a
            d=deepcopy(b);d['position']=[b['position'][j]+c['position'][j]-a['position'][j]for j in range(3)]
            rows.append([a,b,d,c])
        def emit(tri,center=None):
            import numpy as np
            q=np.array([v['position']for v in tri]);n=np.cross(q[1]-q[0],q[2]-q[0]);n/=np.linalg.norm(n)
            if center is not None and n@(q.mean(axis=0)-center)<0:n=-n
            for v in tri:added.append(dict(deepcopy(v),normal=n.tolist()))
        for j in range(2):
            for k in [1,2]:
                quad=[deepcopy(rows[j][k]),deepcopy(rows[j][k+1]),deepcopy(rows[j+1][k+1]),deepcopy(rows[j+1][k])]
                for v,u,t in zip(quad,[2.56951,2.72739,2.72739,2.56951],[j,j,j+1,j+1]):v['uv']=[u,[.01021,.09565,.28256][t]]
                center=[sum(v['position'][a]for row in rows[j:j+2] for v in row)/8 for a in range(3)]
                emit([quad[0],quad[1],quad[2]],center);emit([quad[0],quad[2],quad[3]],center)
        for row in [rows[0],rows[-1]]:
            for ids in [(0,1,2),(0,2,3)]:
                tri=[deepcopy(row[k]) for k in ids]
                for v,k in zip(tri,ids):v['uv']=[[2.56951,2.72739,2.72739,2.56951][k],[.01021,.01021,.06,.06][k]]
                emit(tri)
        remove.update(i for i in post['vertex_indices'] if i>=original_count)
        audit.append({'post':post['id'],'stations':3,'old_station_corners':3,'new_station_corners':4,'original_faces_unchanged':True,'knee_preserved':True})
    assert len(audit)==4
    return [v for i,v in enumerate(vertices)if i not in remove]+added,audit
