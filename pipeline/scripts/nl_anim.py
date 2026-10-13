"""New Leaf (CGFX) player skeleton + skeletal animation evaluation, from DumpAnims.exe JSON dumps."""
import json
from pathlib import Path
import numpy as np
import ckf

ROOT = Path(__file__).resolve().parent
_skel = json.load(open(ROOT/'anim_dump/sklt.json'))['models'][0]['bones']
BONES = [b['name'] for b in _skel]
PARENT = [b['parent'] for b in _skel]
_anims = None


def anims():
    global _anims
    if _anims is None:
        _anims = {a['name']: a for a in json.load(open(ROOT/'anim_dump/humanAnimCommon.json'))['anims']}
    return _anims


def _key(g, f):
    ks = g['keys']
    if len(ks) == 1 or f <= ks[0][0]: return ks[0][1]
    if f >= ks[-1][0]: return ks[-1][1]
    for a, b in zip(ks, ks[1:]):
        if b[0] >= f:
            if g['interp'] == 'step': return a[1]
            if b[0] == a[0]: return a[1]
            if g['interp'] == 'linear':
                mu = (f-a[0])/(b[0]-a[0]); return a[1]*(1-mu)+b[1]*mu
            d = f-a[0]; t = d/(b[0]-a[0]); t1 = t-1
            return a[1]+(a[1]-b[1])*(2*t-3)*t*t+d*t1*(t1*a[3]+t*b[2])
    return ks[-1][1]


def rot_xyz_rad(r):
    return ckf.rotm(np.degrees(r))


def pose(anim, f):
    """world 4x4 of every NL skeleton bone at frame f of anim (dict) or bind pose (None)"""
    tracks = {b['name']: b for b in anim['bones']} if anim else {}
    W = []
    for i, b in enumerate(_skel):
        t = list(b['t']); r = list(b['r'])
        tr = tracks.get(b['name'])
        if tr:
            for k, ch in enumerate(('rx', 'ry', 'rz')):
                if tr.get(ch): r[k] = _key(tr[ch], f)
            for k, ch in enumerate(('tx', 'ty', 'tz')):
                if tr.get(ch): t[k] = _key(tr[ch], f)
        R = rot_xyz_rad(r)
        if tr and tr.get('rq'): R = quat_m(_frame_vec(tr['rq'], f))
        if tr and tr.get('tq'): t = list(_frame_vec(tr['tq'], f)[:3])
        L = np.eye(4); L[:3, :3] = R; L[:3, 3] = t
        W.append(L if PARENT[i] < 0 else W[PARENT[i]]@L)
    return W


def _frame_vec(fr, f):
    v = fr['v']
    if len(v) == 1: return np.array(v[0], float)
    x = min(max(f-fr['start'], 0.0), len(v)-1.0)
    i = int(np.floor(x)); j = min(i+1, len(v)-1); mu = x-i
    a = np.array(v[i], float); b = np.array(v[j], float)
    if len(a) == 4 and np.dot(a, b) < 0: b = -b
    return a*(1-mu)+b*mu


def quat_m(q):
    x, y, z, w = q/np.linalg.norm(q)
    return np.array([[1-2*(y*y+z*z), 2*(x*y-z*w), 2*(x*z+y*w)],
                     [2*(x*y+z*w), 1-2*(x*x+z*z), 2*(y*z-x*w)],
                     [2*(x*z-y*w), 2*(y*z+x*w), 1-2*(x*x+y*y)]])
