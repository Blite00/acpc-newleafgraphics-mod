"""Extract one straight run from a 3DS fence model, as triangles in run space: u along the run (0..L), y up, w across."""
import json, glob
import numpy as np
from pathlib import Path
ROOT = Path(__file__).resolve().parent

def load(name):
    if name.startswith('hobj'):
        d = ROOT/'house_source/fence'/name
        js = glob.glob(str(d/f'{name}_n/*.json'))[0]
        tex = {0: d/'Textures/season00_raw.png', 1: d/'Textures/season09_raw.png'}
        if not tex[1].exists(): tex[1] = tex[0]
    else:
        d = ROOT/'fence_source'/name; js = str(d/f'{name}.json')
        tex = {0: d/f'{name}.png', 1: d/f'{name}.png'}
    m = json.load(open(js)); tris = []
    for mm in m['meshes']:
        if 'shadow' in (mm.get('texture') or ''): continue
        vs = mm['vertices']
        tris += [[(np.array(v['position'], float), tuple(v['uv']), np.array(v['normal'], float)) for v in vs[k:k+3]] for k in range(0, len(vs), 3)]
    return tris, tex

def run(name):
    tris, tex = load(name)
    P = np.array([[v[0] for v in t] for t in tris]); C = P.mean(1)
    lo, hi = P.reshape(-1, 3).min(0), P.reshape(-1, 3).max(0); span = hi-lo
    cands = []
    for axis, side in ((0, lo[0]), (0, hi[0]), (2, lo[2]), (2, hi[2])):
        sel = np.abs(C[:, axis]-side) < 0.075*span[axis]
        along = 2 if axis == 0 else 0
        if sel.sum() == 0: continue
        cands.append((sel.sum(), axis, side, along, sel))
    _, axis, side, along, sel = max(cands, key=lambda c: c[0])
    out = []
    for t, s in zip(tris, sel):
        if not s: continue
        nt = []
        for p, uv, n in t:
            nt.append((np.array([p[along], p[1], p[axis]-side]), uv, np.array([n[along], n[1], n[axis]])))
        out.append(nt)
    Q = np.array([[v[0] for v in t] for t in out]).reshape(-1, 3)
    u0, u1 = Q[:, 0].min(), Q[:, 0].max(); y0, y1 = Q[:, 1].min(), Q[:, 1].max(); w0, w1 = Q[:, 2].min(), Q[:, 2].max()
    # keep the donor's own ground level (y=0): the part modelled below ground stays below ground
    out = [[(p-np.array([u0, 0.0, (w0+w1)/2]), uv, n) for p, uv, n in t] for t in out]
    out_sign = -1.0 if np.isclose(side, lo[axis]) else 1.0      # which way along w faced out of the donor's yard
    return out, (u1-u0, y1, w1-w0), tex, out_sign


def parts(name):
    """Split a straight donor run into posts (narrow pieces: pickets, logs, uprights) and rails (pieces spanning
    most of the run). Returns posts as triangle lists centred on u=0, rails as triangle lists in run space,
    the typical post spacing, and run sizes."""
    run_, size, tex, out_sign = run(name)
    n = len(run_); parent = list(range(n))
    def find(x):
        while parent[x] != x: parent[x] = parent[parent[x]]; x = parent[x]
        return x
    seen = {}
    for i, tri in enumerate(run_):
        for p, _, _ in tri:
            k = tuple(np.round(p, 2))
            if k in seen: parent[find(i)] = find(seen[k])
            else: seen[k] = i
    groups = {}
    for i in range(n): groups.setdefault(find(i), []).append(run_[i])
    L = size[0]; posts = []; rails = []
    for g in groups.values():
        u = np.array([v[0][0] for tri in g for v in tri])
        if u.max()-u.min() > 0.4*L: rails.append(g)
        else: posts.append((float((u.min()+u.max())/2), g))
    posts.sort(key=lambda x: x[0])
    big = max(len(g) for _, g in posts)
    if sum(1 for _, g in posts if len(g) >= 0.6*big) < 3:          # e.g. a rail section on two legs: the whole leg set is the repeating unit
        posts = [(L/2, [tri for _, g in posts if len(g) >= 0.6*big for tri in g])]   # legs only, no clipped slivers
        post = [[[(p-np.array([L/2, 0, 0]), uv, nn) for p, uv, nn in tri] for tri in posts[0][1]]]
        return post, rails, L, size, tex, out_sign
    xs = [c for c, _ in posts]
    spacing = float(np.median(np.diff(xs))) if len(xs) > 1 else L
    # every donor post in order, each centred on u=0, so the fence keeps the donor's mix of post designs
    # (clipped end slivers dropped)
    full = max(len(g) for _, g in posts)
    post = [[[(p-np.array([c, 0, 0]), uv, nn) for p, uv, nn in tri] for tri in g] for c, g in posts if len(g) >= 0.6*full]
    return post, rails, spacing, size, tex, out_sign
