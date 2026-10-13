"""GameCube cKF (keyframe skeleton) tables: parse from the decomp C sources, evaluate, and write back.

Animation layout (c_keyframe.c, cKF_SkeletonInfo_R_play):
  flag_table[0] bits 5..3 = root translation x,y,z animated; for each joint i: flag_table[i] bits 2..0 = rot x,y,z animated
  animated channels take key_table[k] keys of (frame, value, tangent) from data_table, the rest take fixed_table values
  rotations are in 0.1 degree; joint local matrix = T(joint translation) * Rz * Ry * Rx (root: animated translation)
"""
import re
from pathlib import Path
import numpy as np

_cache = {}


def _src(path):
    path = Path(path)
    if path not in _cache: _cache[path] = path.read_text()
    return _cache[path]


def _array(src, name):
    if name == 'NULL': return []
    m = re.search(r'\b' + re.escape(name) + r'\[\]\s*(?:ATTRIBUTE_ALIGN\(\d+\)\s*)?=\s*\{(.*?)\};', src, re.S)
    if m is None: raise KeyError(name)
    return [int(x, 0) for x in re.findall(r'-?(?:0x[0-9a-fA-F]+|\d+)', re.sub(r'/\*.*?\*/', '', m.group(1)))]


def joints(path, skel):
    """[(model name or None, child count, (tx,ty,tz))] of cKF_je_r_<skel>_tbl"""
    src = _src(path)
    m = re.search(r'cKF_Joint_R_c\s+cKF_je_r_' + re.escape(skel) + r'_tbl\[\]\s*=\s*\{(.*?)\n?\};', src, re.S)
    out = []
    for e in re.findall(r'\{\s*(\w+)\s*,\s*(\d+)\s*,\s*\w+\s*,\s*\{\s*(-?\d+)\s*,\s*(-?\d+)\s*,\s*(-?\d+)\s*\}\s*\}', m.group(1)):
        t = [int(x) for x in e[2:]]
        t = [x-65536 if x > 32767 else x for x in t]
        out.append((None if e[0] == 'NULL' else e[0], int(e[1]), tuple(t)))
    return out


def parents(jt):
    par = [-1]*len(jt); stack = []
    for i, (_, child, _) in enumerate(jt):
        if stack:
            p = stack[-1]; par[i] = p[0]; p[1] -= 1
            if p[1] == 0: stack.pop()
        if child: stack.append([i, child])
        # pop finished parents
        while stack and stack[-1][1] == 0: stack.pop()
    return par


class Anim:
    def __init__(self, path, name, njoints):
        src = _src(path)
        m = re.search(r'cKF_Animation_R_c\s+cKF_ba_r_' + re.escape(name) + r'\s*=\s*\{(.*?)\};', src, re.S)
        f = [x.strip() for x in m.group(1).split(',')]
        self.flags = _array(src, f[0]); self.data = _array(src, f[1]); self.keys = _array(src, f[2]); self.fixed = _array(src, f[3])
        self.frames = int(f[5]); self.n = njoints; self.name = name
        self.chan = []        # per channel (3 root trans + 3*n rot): ('k', [(frame,value,tangent)]) or ('c', value)
        di = ki = fi = 0
        def take(animated):
            nonlocal di, ki, fi
            if animated:
                n = self.keys[ki]; ki += 1
                ks = [tuple(self.data[(di+j)*3:(di+j)*3+3]) for j in range(n)]; di += n
                return ('k', ks)
            v = self.fixed[fi]; fi += 1
            return ('c', v)
        for j, bit in enumerate((32, 16, 8)): self.chan.append(take(self.flags[0] & bit))
        for i in range(njoints):
            for bit in (4, 2, 1): self.chan.append(take(self.flags[i] & bit))

    @staticmethod
    def keycalc(ks, frame):
        if ks[0][0] >= frame: return ks[0][1]
        if ks[-1][0] <= frame: return ks[-1][1]
        for a, b in zip(ks, ks[1:]):
            if b[0] > frame:
                d = b[0]-a[0]
                if d == 0: return a[1]
                t = (frame-a[0])/d; ten = d/30.0
                t2 = t*t; t3 = t2*t; p = -2*t3+3*t2
                return (1-p)*a[1]+p*b[1]+ten*((t+t3-2*t2)*a[2]+(t3-t2)*b[2])
        return ks[-1][1]

    def sample(self, frame):
        """root translation (3,), rotations (n,3) in degrees"""
        v = [c[1] if c[0] == 'c' else self.keycalc(c[1], frame) for c in self.chan]
        return np.array(v[:3], float), np.array(v[3:], float).reshape(self.n, 3)*0.1


def rotm(deg):
    x, y, z = np.radians(deg)
    cx, sx, cy, sy, cz, sz = np.cos(x), np.sin(x), np.cos(y), np.sin(y), np.cos(z), np.sin(z)
    Rx = np.array([[1, 0, 0], [0, cx, -sx], [0, sx, cx]]); Ry = np.array([[cy, 0, sy], [0, 1, 0], [-sy, 0, cy]])
    Rz = np.array([[cz, -sz, 0], [sz, cz, 0], [0, 0, 1]])
    return Rz@Ry@Rx


def euler_zyx(R):
    """degrees (x,y,z) with R = Rz Ry Rx"""
    sy = -R[2, 0]; sy = max(-1.0, min(1.0, sy))
    y = np.arcsin(sy)
    if abs(np.cos(y)) > 1e-6:
        x = np.arctan2(R[2, 1], R[2, 2]); z = np.arctan2(R[1, 0], R[0, 0])
    else:
        x = np.arctan2(-R[1, 2], R[1, 1]); z = 0.0
    return np.degrees([x, y, z])


def world(jt, root_t, rots):
    """4x4 world matrices of every joint (root at the animated root translation)"""
    par = parents(jt); W = []
    for i, (_, _, t) in enumerate(jt):
        L = np.eye(4); L[:3, :3] = rotm(rots[i]); L[:3, 3] = root_t if i == 0 else t
        W.append(L if par[i] < 0 else W[par[i]]@L)
    return W
