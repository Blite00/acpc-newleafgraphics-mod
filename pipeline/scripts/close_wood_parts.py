"""Close individual donor wooden shells without inserting a deck-wide backing.

Use actual boundary vertices/UVs. Ear clipping avoids center-fan UV averages
and fills concave openings without triangles extending outside their outline.
"""
from collections import defaultdict
from close_post_perimeters import post_perimeter_strip
from repair_bridge_closure_uvs import repair_closure_uvs
from copy import deepcopy
import math
import numpy as np


def close_wood_parts(vertices,style=3):
    key = lambda v: tuple(round(x, 3) for x in v['position'])
    edges = defaultdict(list)
    for i in range(0, len(vertices), 3):
        tri = vertices[i:i + 3]
        for a, b in zip(tri, tri[1:] + tri[:1]):
            if key(a) != key(b):
                edges[tuple(sorted((key(a), key(b))))].append((a, b))
    boundary = {edge: uses[0] for edge, uses in edges.items() if len(uses) == 1}
    adjacency = defaultdict(set)
    for a, b in boundary:
        adjacency[a].add(b)
        adjacency[b].add(a)
    remaining = set(boundary)
    loops = []
    # Split touching loops at repeated vertices; degree-four rail intersections
    # are multiple closed shell rims, not a reason to drop the whole component.
    while remaining:
        start = min(remaining)[0]
        walk = [start]
        while True:
            candidates = sorted(q for q in adjacency[walk[-1]]
                                if tuple(sorted((walk[-1], q))) in remaining)
            if not candidates:
                assert len(walk) == 1, ('Open donor wood boundary', walk)
                break
            q = candidates[0]
            remaining.remove(tuple(sorted((walk[-1], q))))
            if q in walk:
                at = walk.index(q)
                loop = walk[at:]
                if len(loop) >= 3:
                    loops.append(loop)
                walk = walk[:at + 1]
            else:
                walk.append(q)
    added = []
    for loop in loops:
        # Reverse the original winding at its shared boundary edge.
        original = boundary[tuple(sorted(loop[:2]))]
        if key(original[0]) == loop[0]:
            loop = list(reversed(loop))
        ring = []
        for j, point in enumerate(loop):
            edge = boundary[tuple(sorted((point, loop[(j + 1) % len(loop)])))]
            ring.append(deepcopy(next(v for v in edge if key(v) == point)))
        post=post_perimeter_strip(ring)
        if post is not None:
            added.extend(post)
            continue
        pos = [v['position'] for v in ring]
        centered=np.asarray(pos)-np.mean(pos,axis=0)
        _,_,basis=np.linalg.svd(centered,full_matrices=False)
        xy=[tuple(q) for q in centered @ basis[:2].T]
        cross = lambda a, b, c: (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])
        area = sum(a[0]*b[1]-a[1]*b[0] for a,b in zip(xy,xy[1:]+xy[:1]))
        if abs(area) < 1e-6:
            continue  # Coincident original rim has no surface area to fill.
        sign = 1 if area > 0 else -1
        ids = list(range(len(ring)))
        triangles = []
        while len(ids) > 3:
            ear = None
            for j, b in enumerate(ids):
                a,c = ids[j-1],ids[(j+1)%len(ids)]
                if cross(xy[a],xy[b],xy[c])*sign <= 1e-7:
                    continue
                if any(all(cross(xy[u],xy[v],xy[p])*sign > 1e-7
                           for u,v in ((a,b),(b,c),(c,a)))
                       for p in ids if p not in (a,b,c)):
                    continue
                ear=j;triangles.append((a,b,c));break
            if ear is None:
                # Remove only collinear projected rim points. Never invent a
                # center fan across a non-simple opening.
                collinear = next((j for j,b in enumerate(ids)
                    if abs(cross(xy[ids[j-1]],xy[b],xy[ids[(j+1)%len(ids)]])) < 1e-6), None)
                if collinear is None:
                    # Some rims wrap around curved log/post ends and have no
                    # simple 2D projection. Find their minimum-area 3D surface
                    # using existing boundary vertices, without a central fan.
                    from functools import lru_cache
                    @lru_cache(None)
                    def fill(lo,hi):
                        if hi-lo<2:return (0.0,())
                        best=None
                        for mid in range(lo+1,hi):
                            va,vb,vc=(np.asarray(pos[q]) for q in (lo,mid,hi))
                            cost=float(np.linalg.norm(np.cross(vb-va,vc-va)))
                            ca,ta=fill(lo,mid);cb,tb=fill(mid,hi)
                            candidate=(ca+cb+cost,ta+tb+((lo,mid,hi),))
                            if best is None or candidate[0]<best[0]:best=candidate
                        return best
                    triangles=list(fill(0,len(ring)-1)[1]);ids=[];break
                ids.pop(collinear)
            else:
                ids.pop(ear)
        if len(ids) == 3:
            triangles.append(tuple(ids))
        for indices in triangles:
            tri = [deepcopy(ring[j]) for j in indices]
            a,b,c = [v['position'] for v in tri]
            u=[b[k]-a[k] for k in range(3)];v=[c[k]-a[k] for k in range(3)]
            n=[u[1]*v[2]-u[2]*v[1],u[2]*v[0]-u[0]*v[2],u[0]*v[1]-u[1]*v[0]]
            length=math.sqrt(sum(q*q for q in n))
            if length < 1e-7:
                continue
            for vertex in tri:
                vertex['normal']=[q/length for q in n]
            added.extend(tri)
    # Topological coverage check, including deck-wide and touching rail loops.
    counts={edge:len(uses) for edge,uses in edges.items()}
    for i in range(0,len(added),3):
        tri=added[i:i+3]
        for a,b in zip(tri,tri[1:]+tri[:1]):
            edge=tuple(sorted((key(a),key(b))))
            counts[edge]=counts.get(edge,0)+1
    open_edges=sum(count==1 for count in counts.values())
    assert open_edges==0, ('Unclosed donor wooden shell',open_edges)
    uv_audit=repair_closure_uvs(vertices,added,wood_style=style)
    return added, {**uv_audit,'boundary_edges':len(boundary),'closed_loops':len(loops),
                   'added_triangles':len(added)//3,'source_vertices':len(vertices),
                   'remaining_open_edges':open_edges,'new_center_vertices':0,
                   'source_boundary_uvs_retained_on_unmodified_caps':True}
