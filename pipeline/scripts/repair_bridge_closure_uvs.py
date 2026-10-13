"""Map generated bridge caps into nearby donor material regions.
Original donor vertices and UVs are never modified.
"""
from collections import defaultdict
import numpy as np


def repair_closure_uvs(source, added, wood_style=None):
    key=lambda v:tuple(round(q,3) for q in v['position'])
    area=lambda t:abs(float(np.linalg.det(np.asarray([t[1]['uv'],t[2]['uv']])-t[0]['uv'])))
    triangles=[added[i:i+3] for i in range(0,len(added),3)]
    source_triangles=[source[i:i+3] for i in range(0,len(source),3)]
    valid=[t for t in source_triangles if area(t)>1e-7]
    assert valid
    edges=defaultdict(list);adj=defaultdict(set);normals=[]
    for i,t in enumerate(triangles):
        p=np.asarray([v['position'] for v in t]);n=np.cross(p[1]-p[0],p[2]-p[0]);n/=np.linalg.norm(n);normals.append(n)
        for a,b in zip(t,t[1:]+t[:1]):edges[tuple(sorted((key(a),key(b))))].append(i)
    for ids in edges.values():
        for i in ids:
            for j in ids:
                # Keep bent arch/log patches separate. A common projection is
                # continuous across each nearly planar cap, including its good
                # triangles, rather than repairing only isolated bad triangles.
                if abs(float(normals[i]@normals[j]))>.999:adj[i].add(j)
    remaining=set(range(len(triangles)));patches=0;fixed=0
    before=sum(area(t)<1e-8 for t in triangles)
    while remaining:
        group={min(remaining)};remaining-=group;todo=list(group)
        while todo:
            for j in sorted(adj[todo.pop()] & remaining):remaining.remove(j);group.add(j);todo.append(j)
        if wood_style is None and not any(area(triangles[i])<1e-8 for i in group):continue
        vertices=[v for i in sorted(group) for v in triangles[i]]
        positions=np.asarray([v['position'] for v in vertices]);center=positions.mean(axis=0)
        keys={key(v) for v in vertices}
        def score(t):
            p=np.asarray([v['position'] for v in t])
            shared=sum(key(v) in keys for v in t)
            return (shared,-float(np.linalg.norm(p.mean(axis=0)-center)))
        donor=max(valid,key=score)
        dp=np.asarray([donor[1]['position'],donor[2]['position']])-donor[0]['position']
        duv=np.asarray([donor[1]['uv'],donor[2]['uv']])-donor[0]['uv']
        # World-space UV gradients provide original grain direction/density.
        gradients=np.linalg.lstsq(dp,duv,rcond=None)[0]
        _,_,basis=np.linalg.svd(positions-center,full_matrices=False)
        normal=basis[2];u=gradients[:,0]-normal*(normal@gradients[:,0])
        if np.linalg.norm(u)<1e-8:
            v=gradients[:,1]-normal*(normal@gradients[:,1])
            u=np.cross(v,normal)
        if np.linalg.norm(u)<1e-8:u=basis[0]
        u/=np.linalg.norm(u);v=np.cross(normal,u)
        if v@gradients[:,1]<0:v=-v
        coords=np.column_stack(((positions-center)@u,(positions-center)@v))
        lo=coords.min(axis=0);hi=coords.max(axis=0);span=hi-lo
        assert min(span)>1e-8
        donor_uv=np.asarray([q['uv'] for q in donor]);uvlo=donor_uv.min(axis=0);uvhi=donor_uv.max(axis=0)
        if wood_style is not None:
            # Exact brown panels in the original 64x256 donor atlas. Some
            # source edge UVs intentionally touch blue unused atlas strips;
            # extending those coordinates across a new back face is incorrect.
            # Preserve donor density/orientation, but keep new faces wholly
            # inside a wood panel. Original source surfaces are not remapped.
            rect=(17,4,61,125) if wood_style==2 else ((2,29,62,126) if abs(normal[1])>.75 else (2,138,45,195))
            x0,y0,x1,y1=rect
            uvlo=np.asarray([x0/64,1-y1/256]);uvhi=np.asarray([x1/64,1-y0/256])

        # Use the adjacent valid face's material rectangle, with a small inset;
        # this avoids walking into another atlas panel when the new cap is wide.
        uvspan=(uvhi-uvlo)*.96
        density=np.linalg.norm(gradients,axis=0)
        scales=np.minimum(density,uvspan/span)
        assert min(scales)>1e-10
        mapped=(coords-(lo+hi)/2)*scales+(uvlo+uvhi)/2
        for vertex,uv in zip(vertices,mapped):vertex['uv']=[float(q) for q in uv]
        patches+=1;fixed+=len(group)
    post_audit=wrap_suspension_posts(source,triangles,wood_style) if wood_style in (2,3) else {'post_groups':0,'post_triangles':0}
    added[:]=[vertex for triangle in triangles for vertex in triangle]
    after=sum(area(t)<1e-8 for t in triangles)
    assert after==0,('Degenerate closure UVs remain',before,after)
    return {'collapsed_uv_triangles_before':before,'collapsed_uv_triangles_after':after,
            'projected_cap_patches':patches,'projected_cap_triangles':fixed,
            'original_uvs_modified':False,**post_audit}


def wrap_suspension_posts(source,triangles,style=2):
    # These are the actual two post-side panels in style02, recovered from
    # original visible faces (support triangles204..213, rope-post978..993).
    # Keep one vertical phase across each post instead of selecting a different
    # artwork strip for each triangulated back face.
    key=lambda v:tuple(round(q,3) for q in v['position'])
    adjacency=defaultdict(set);owners=defaultdict(list)
    for i,t in enumerate(triangles):
        for v in t:owners[key(v)].append(i)
    for ids in owners.values():
        for i in ids:adjacency[i].update(ids)
    remaining=set(range(len(triangles)));posts=changed=0;regions=[];deck_count=0;replacements={}
    deck=[]
    for i in range(0,len(source),3):
        tri=source[i:i+3]
        if max(v['position'][0] for v in tri)-min(v['position'][0] for v in tri)>50 and sum(v['normal'][1] for v in tri)>1.5:
            deck.extend(tri)
    knots_by_z=defaultdict(list)
    for vertex in deck:knots_by_z[round(vertex['position'][2],4)].append(vertex['uv'][1])
    deck_z=sorted(knots_by_z);deck_v=[sum(knots_by_z[z])/len(knots_by_z[z]) for z in deck_z]
    deck_x0=min(v['position'][0] for v in deck);deck_x1=max(v['position'][0] for v in deck)

    while remaining:
        group={min(remaining)};remaining-=group;todo=list(group)
        while todo:
            for j in sorted(adjacency[todo.pop()] & remaining):remaining.remove(j);group.add(j);todo.append(j)
        points=np.asarray([v['position'] for i in sorted(group) for v in triangles[i]])
        lo=points.min(axis=0);hi=points.max(axis=0);height=hi[1]-lo[1]
        if hi[0]-lo[0]>50:
            # Original deck underside panel, with the plank-phase V knots
            # taken directly from the visible donor deck. No post artwork.
            for i in sorted(group):
                tri=triangles[i];p=np.asarray([v['position'] for v in tri])
                normal=np.cross(p[1]-p[0],p[2]-p[0]);dominant=int(np.argmax(np.abs(normal)))
                if style==2:
                    phase=np.interp(p[:,2],deck_z,deck_v)
                    depth=(hi[1]-p[:,1])/max(hi[1]-lo[1],1e-6)
                    if dominant==0:
                        # Original narrow side-board atlas strip, with plank
                        # phase following the unchanged lengthwise donor V.
                        uv=np.column_stack((-.01803+.22039*depth,phase))
                    elif dominant==2:
                        direction=1 if float(phase.mean())<1 else -1
                        uv=np.column_stack((.197+(p[:,0]-deck_x0)/(deck_x1-deck_x0)*1.593,phase+direction*.07*depth))
                    else:
                        uv=np.column_stack((-1.32415+(p[:,0]-deck_x0)/(deck_x1-deck_x0)*(.63706),phase))
                else:
                    # Each timber log has its own original upper bark panel.
                    # Only broad upward log faces qualify, never rail/filler.
                    refs=[deck[k:k+3] for k in range(0,len(deck),3)]
                    ref=min(refs,key=lambda t:abs(sum(v['position'][2] for v in t)/3-float(p[:,2].mean())))
                    rp=np.asarray([[v['position'][0],v['position'][2]] for v in ref]);ru=np.asarray([v['uv'] for v in ref])
                    if abs(float(np.linalg.det(rp[1:]-rp[0])))<1e-8:continue
                    gradient=np.linalg.solve(rp[1:]-rp[0],ru[1:]-ru[0])
                    uv=(p[:,[0,2]]-rp[0])@gradient+ru[0]
                    if dominant!=1:
                        # Roll the same log's bark panel over its visible
                        # vertical edge, rather than retaining a flat top map.
                        mid=float(ru[:,1].mean());direction=1 if float(uv[:,1].mean())<mid else -1
                        depth=(hi[1]-p[:,1])/max(hi[1]-lo[1],1e-6)
                        if dominant==0:
                            # Across-log end grain varies with depth in U;
                            # lengthwise vertical edges roll the V coordinate.
                            umid=float(ru[:,0].mean());udir=1 if float(uv[:,0].mean())<umid else -1
                            uv[:,0]+=udir*.10*depth
                        else:uv[:,1]+=direction*.05*depth

                if abs(float(np.linalg.det(uv[1:]-uv[0])))<1e-8:continue
                for vertex,q in zip(tri,uv):vertex['uv']=[float(x) for x in q]
                deck_count+=1
            continue
        if height<(20 if style==2 else 25) or max(hi[0]-lo[0],hi[2]-lo[2])>40:continue
        tall=height>45
        center=points.mean(axis=0);_,_,basis=np.linalg.svd(points-center,full_matrices=False)
        axis=basis[0]
        if axis[1]<0:axis=-axis
        longitudinal=(points-center)@axis;s0=longitudinal.min();s1=longitudinal.max()
        radial=points-center-longitudinal[:,None]*axis
        # Actual donor bark spans; main posts mirror around U2 at the corner.
        u0,u1=(.1702,.3439) if style==3 else ((2.5695,2.7274) if tall else (1.631,1.9998))
        if style==3:
            knots=[s0,s1];rows=[.0601,.4060]
        elif tall:
            # Original support knee at V.0957 divides buried foot and upper
            # bark; preserve this nonuniform row spacing instead of smearing it.
            nearby=[v for v in source if abs(v['uv'][1]-.0957)<.001
                    and lo[0]-2<=v['position'][0]<=hi[0]+2
                    and lo[2]-2<=v['position'][2]<=hi[2]+2]
            knee=np.mean([(np.asarray(v['position'])-center)@axis for v in nearby]) if nearby else s0+.54*(s1-s0)
            knots=[s0,float(knee),s1];rows=[.0102,.0957,.2826]
        else:knots=[s0,s1];rows=[.0778 if height<25 else .0018,.2341]
        count=0;work=[]
        for i in sorted(group):
            pieces=[triangles[i]]
            if style==2 and tall:
                tri=triangles[i];dist=[float((np.asarray(v['position'])-center)@axis-knee) for v in tri]
                if min(dist)<-1e-5 and max(dist)>1e-5:
                    pieces=[]
                    for sign in (-1,1):
                        polygon=[]
                        for j,a in enumerate(tri):
                            b=tri[(j+1)%3];da=dist[j]*sign;db=dist[(j+1)%3]*sign
                            if da>=-1e-8:polygon.append(dict(a))
                            if (da<0<db) or (db<0<da):
                                f=da/(da-db)
                                polygon.append(dict(a,position=[a['position'][k]+f*(b['position'][k]-a['position'][k]) for k in range(3)],uv=[0.0,0.0]))
                        for j in range(1,len(polygon)-1):pieces.append([dict(polygon[0]),dict(polygon[j]),dict(polygon[j+1])])
                    replacements[i]=pieces
            work.extend(pieces)
        for tri in work:
            p=np.asarray([v['position'] for v in tri]);n=np.cross(p[1]-p[0],p[2]-p[0])
            uaxis=np.cross(axis,n);length=np.linalg.norm(uaxis)
            if length<1e-7:continue
            uaxis/=length
            # Choose stable handedness; every cap plane sees the same post's
            # bark width, with vertical position shared across all planes.
            if uaxis[np.argmax(np.abs(uaxis))]<0:uaxis=-uaxis
            cross=radial@uaxis;a,b=cross.min(),cross.max()
            if b-a<1e-7:continue
            along=(p-center)@axis
            across=(p-center-along[:,None]*axis)@uaxis
            uv=np.column_stack((u0+(u1-u0)*(across-a)/(b-a),np.interp(along,knots,rows)))
            if abs(float(np.linalg.det(uv[1:]-uv[0])))<1e-8:continue
            for v,q in zip(tri,uv):v['uv']=[float(x) for x in q]
            count+=1
        posts+=1;changed+=count;regions.append({'triangles':count,'panel_u':[u0,u1],'panel_v':rows,'height':float(height)})
    triangles[:]=[piece for i,tri in enumerate(triangles) for piece in replacements.get(i,[tri])]
    return {'post_groups':posts,'post_triangles':changed,'post_material_regions':regions,'deck_underside_triangles':deck_count,'deck_v_from_original':True,'support_knee_split_faces':len(replacements)}
