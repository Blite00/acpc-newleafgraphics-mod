"""Close missing post sides along existing perimeter arcs, never through center."""
import numpy as np
from copy import deepcopy
from collections import Counter

POST_STRIP_AUDIT=[]


def post_perimeter_strip(ring):
    p=np.asarray([v['position'] for v in ring]);span=p.max(axis=0)-p.min(axis=0)
    if span[1]<15 or span[1]<1.25*max(span[0],span[2]):return None
    center=p.mean(axis=0);_,_,basis=np.linalg.svd(p-center,full_matrices=False);axis=basis[0]
    if axis[1]<0:axis=-axis
    s=(p-center)@axis;lo=s.min();hi=s.max()
    def arc(mask):
        starts=[i for i in range(len(ring)) if mask[i] and not mask[i-1]]
        if len(starts)!=1:return None
        out=[];i=starts[0]
        while mask[i]:
            out.append(i);i=(i+1)%len(ring)
            if len(out)>len(ring):return None
        return out
    top=arc(s>lo+.78*(hi-lo));bottom=arc(s<lo+.22*(hi-lo))
    if top is None or bottom is None or len(top)<2 or len(bottom)<2:return None
    # Top arc follows boundary order; reverse the bottom to align its ends.
    upper=[ring[i] for i in top];lower=[ring[i] for i in reversed(bottom)]
    def walk(a,b):
        out=[ring[a]]
        while a!=b:a=(a+1)%len(ring);out.append(ring[a])
        return out
    left=walk(bottom[-1],top[0]);right=list(reversed(walk(top[-1],bottom[0])))
    s0=np.mean([(np.asarray(v['position'])-center)@axis for v in lower]);s1=np.mean([(np.asarray(v['position'])-center)@axis for v in upper])
    if s1-s0<1e-6:return None
    def side_times(side):
        t=[0.0]+[float(((np.asarray(v['position'])-center)@axis-s0)/(s1-s0)) for v in side[1:-1]]+[1.0]
        if any(b-a<1e-7 for a,b in zip(t,t[1:])):return None
        return t
    lt,rt=side_times(left),side_times(right)
    if lt is None or rt is None:return None
    def arc_times(chain):
        t=[0.0]
        for a,b in zip(chain,chain[1:]):t.append(t[-1]+float(np.linalg.norm(np.asarray(a['position'])-b['position'])))
        if t[-1]<1e-7:return None
        return [q/t[-1] for q in t]
    bt,tt=arc_times(lower),arc_times(upper)
    if bt is None or tt is None:return None
    def lerp(a,b,f):
        return dict(a,position=[a['position'][k]+f*(b['position'][k]-a['position'][k]) for k in range(3)],uv=[a['uv'][k]+f*(b['uv'][k]-a['uv'][k]) for k in range(2)])
    def sample(chain,times,t):
        if t<=0:return deepcopy(chain[0])
        if t>=1:return deepcopy(chain[-1])
        for i in range(len(times)-1):
            if t<=times[i+1]+1e-8:return lerp(chain[i],chain[i+1],(t-times[i])/(times[i+1]-times[i]))
        raise AssertionError(t)
    rows=[];li=ri=0
    states=[(0,0)]
    while li<len(left)-1 or ri<len(right)-1:
        nl=lt[li+1] if li<len(left)-1 else float('inf')
        nr=rt[ri+1] if ri<len(right)-1 else float('inf')
        if abs(nl-nr)<1e-8:li+=1;ri+=1
        elif nl<nr:li+=1
        else:ri+=1
        states.append((li,ri))
    for li,ri in states:
        if li==0 and ri==0:rows.append((bt,deepcopy(lower)));continue
        if li==len(left)-1 and ri==len(right)-1:rows.append((tt,deepcopy(upper)));continue
        left_actual=left[li];right_actual=right[ri]
        left_linear=lerp(lower[0],upper[0],lt[li]);right_linear=lerp(lower[-1],upper[-1],rt[ri])
        lc=np.asarray(left_actual['position'])-left_linear['position'];rc=np.asarray(right_actual['position'])-right_linear['position']
        times=sorted(set(bt+tt));row=[]
        for across in times:
            height=lt[li]*(1-across)+rt[ri]*across
            if across==0:v=deepcopy(left_actual)
            elif across==1:v=deepcopy(right_actual)
            else:
                v=lerp(sample(lower,bt,across),sample(upper,tt,across),height)
                v['position']=(np.asarray(v['position'])+lc*(1-across)+rc*across).tolist()
            row.append(v)
        rows.append((times,row))
    added=[]
    def emit(a,b,c):
        q=np.asarray([v['position'] for v in(a,b,c)]);n=np.cross(q[1]-q[0],q[2]-q[0]);length=np.linalg.norm(n)
        if length<1e-7:return
        n/=length;radial=q.mean(axis=0)-center;radial-=axis*(radial@axis)
        if n@radial<0:n=-n;b,c=c,b
        added.extend(dict(deepcopy(v),normal=n.tolist()) for v in(a,b,c))
    # Zipper arcs without adding vertices to the original top/bottom border:
    # every original boundary edge remains exactly shared, no T junctions.
    for (at,a),(bt_,b) in zip(rows,rows[1:]):
        i=j=0
        while i<len(a)-1 or j<len(b)-1:
            ta=at[i+1] if i<len(a)-1 else float('inf');tb=bt_[j+1] if j<len(b)-1 else float('inf')
            if abs(ta-tb)<1e-8:
                emit(a[i],a[i+1],b[j+1]);emit(a[i],b[j+1],b[j]);i+=1;j+=1
            elif ta<tb:emit(a[i],a[i+1],b[j]);i+=1
            else:emit(a[i],b[j+1],b[j]);j+=1
    key=lambda v:tuple(round(x,3) for x in v['position'])
    actual=Counter()
    for i in range(0,len(added),3):
        tri=added[i:i+3]
        for a,b in zip(tri,tri[1:]+tri[:1]):actual[tuple(sorted((key(a),key(b))))]+=1
    expected={tuple(sorted((key(a),key(b)))) for a,b in zip(ring,ring[1:]+ring[:1])}
    assert all(actual[edge]==1 for edge in expected),'Post perimeter boundary changed'
    assert all(n==2 for edge,n in actual.items() if edge not in expected),'Open post strip interior'
    POST_STRIP_AUDIT.append({'boundary_vertices':len(ring),'top_arc_vertices':len(upper),
        'bottom_arc_vertices':len(lower),'perimeter_rows':len(rows),'triangles':len(added)//3,
        'boundary_edges_preserved':True,'interior_edges_paired':True,
        'center_fan_vertices':0})
    return added
