"""Recessed backing only beneath actual gaps in the separate timber logs."""
from repair_bridge_closure_uvs import repair_closure_uvs


def timber_gap_strips(source,floor):
    center=(min(v['position'][0] for v in source)+max(v['position'][0] for v in source))/2
    deck=[];intervals=[]
    for i in range(0,len(source),3):
        tri=source[i:i+3];p=[v['position'] for v in tri]
        if not(min(q[0] for q in p)<=center<=max(q[0] for q in p) and sum(v['normal'][1] for v in tri)>1.5):continue
        zs=[]
        for a,b in zip(p,p[1:]+p[:1]):
            if min(a[0],b[0])<=center<=max(a[0],b[0]) and abs(a[0]-b[0])>1e-7:
                t=(center-a[0])/(b[0]-a[0]);zs.append(a[2]+t*(b[2]-a[2]))
        if len(zs)>=2:intervals.append((min(zs),max(zs)));deck.extend(tri)
    merged=[]
    for a,b in sorted(intervals):
        if merged and a<=merged[-1][1]+1e-4:merged[-1]=(merged[-1][0],max(b,merged[-1][1]))
        else:merged.append((a,b))
    lo=min(v['position'][0] for v in deck)+.5;hi=max(v['position'][0] for v in deck)-.5
    added=[];gaps=[]
    for left,right in zip(merged,merged[1:]):
        a,b=left[1],right[0]
        if b-a<.01:continue
        # Slightly overlap below each plank edge, never across the whole deck.
        z0,z1=a-.2,b+.2;y0,y1=floor(z0)-1.0,floor(z1)-1.0
        def vertex(x,y,z):
            nearest=min(deck,key=lambda v:sum((v['position'][k]-q)**2 for k,q in enumerate((x,y,z))))
            col=nearest['color'];rgb=[round(((col>>k)&255)*.72) for k in (16,8,0)]
            return dict(nearest,position=[x,y,z],normal=[0,1,0],uv=[0.0,0.0],color=(255<<24)|(rgb[0]<<16)|(rgb[1]<<8)|rgb[2])
        q=[vertex(lo,y0,z0),vertex(hi,y0,z0),vertex(hi,y1,z1),vertex(lo,y1,z1)]
        # Independent vertex dictionaries allow planar mapping without aliases.
        added.extend(dict(q[j]) for j in (0,2,1,0,3,2));gaps.append([a,b])
    uv_audit=repair_closure_uvs(deck,added,wood_style=3)
    return added,{'gaps':gaps,'added_triangles':len(added)//3,**uv_audit}
