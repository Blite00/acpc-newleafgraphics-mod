"""Smoother villagers and player: every character display list is rebuilt with more polygons.

The GC characters are skinned the N64 way: each vertex is loaded under one joint matrix, and "stitch" triangles join
vertices of different joints. Here every edge whose two ends belong to the same joint is split at its PN-triangle
midpoint (a cubic curve through both ends that follows their normals), two levels deep, so rounded heads, bodies and
limbs get 16x the triangles and a curved silhouette. Edges between joints are never split, and a triangle is
re-triangulated from whichever of its edges were split, so neighbours always share the same vertices (no cracks), and
the joints bend exactly as before. Texture coordinates, normals and vertex colours are interpolated; all material and
texture commands are copied unchanged, so faces, eyes, mouths and clothing animate as before.

Output: pc/src/pc_chr_smooth.c_inc (compiled by pc_chr_smooth.c) with pc_chr_smooth_install(), which points each
character skeleton's joints at the smoothed display lists. PC_CHR_NATIVE=1 keeps the originals (comparisons).
"""
import re
from pathlib import Path
import numpy as np
import native_models as nm

ROOT = Path(__file__).resolve().parent
PORT = ROOT/'ACGC-PC-Port'
FILES = sorted((PORT/'src/data/npc/model/mdl').glob('*.c')) + [PORT/'src/data/model/boy_model.c', PORT/'src/data/model/girl_model.c']
LEVELS = 2
PN = 0.75            # how far the curved midpoints bulge (1 = full PN triangle)
SLOTS = 32
OUTDIR = PORT/'pc/src'

_TOK = re.compile(r'(gs\w+)\(((?:[^()]|\([^()]*\))*)\)\s*,', re.S)

def tri_indices(op, args):
    a = [x.strip() for x in args.split(',')]
    if op == 'gsSP1Triangle': return [tuple(map(int, a[0:3]))]
    if op == 'gsSP2Triangles': return [tuple(map(int, a[0:3])), tuple(map(int, a[4:7]))]
    if op == 'gsSPNTrianglesInit_5b': return int(a[0]), [tuple(map(int, a[1+3*k:4+3*k])) for k in range(3)]
    if op == 'gsSPNTriangles_5b': return [tuple(map(int, a[3*k:3+3*k])) for k in range(4)]

class Vert:
    __slots__ = ('mtx', 'p', 'uv', 'n', 'c', 'key', 'ng', 'grp', 'j', 'w', 'lit', 'ds')
    def __init__(self, mtx, p, uv, n, c, key):
        self.mtx, self.p, self.uv, self.n, self.c, self.key = mtx, p, uv, n, c, key
        self.ng = None; self.grp = None; self.j = None; self.w = None
        self.lit = True; self.ds = False      # lit by normals / drawn double-sided (geometry mode at load time)

SMOOTH_ANGLE = 60.0   # vertex normals closer than this at one point are averaged (smooth shading)
CREASE_ANGLE = 40.0   # a point whose normals spread wider than this is a crease: edges leave it straight

def weld(verts):
    """GC models repeat a vertex per face; group copies by joint and position. Shading normals are averaged with
    the copies within SMOOTH_ANGLE; the curve normal (ng) is the group average, or None at creases. Both depend
    only on the group, so every copy of an edge gets the same curved midpoint (no cracks)."""
    groups = {}
    for v in verts:
        if v.lit and not v.ds: groups.setdefault(wkey(v), []).append(v)
    cs = np.cos(np.radians(SMOOTH_ANGLE)); cc = np.cos(np.radians(CREASE_ANGLE))
    for vs in groups.values():
        ns = [v.n for v in vs if np.any(v.n)]
        if not ns: continue
        avg = unit(np.sum(ns, 0))
        crease = any(np.dot(n, avg) < cc for n in ns)
        for v in vs:
            v.ng = None if crease else avg
            if np.any(v.n): v.n = unit(np.sum([n for n in ns if np.dot(n, v.n) >= cs], 0))

def unit(v):
    l = np.linalg.norm(v); return v/l if l > 1e-9 else v

def parse_dl(body, vtx_arrays):
    """-> list of items: ('state', text) | ('tris', [(Vert, Vert, Vert)]); and the last matrix command text."""
    body = re.sub(r'//[^\n]*', '', body)
    items = []; slots = {}; mtx = None; pending = 0; last_mtx = None; lit = True; ds = False
    def add_tri(t):
        try: vs = tuple(slots[i] for i in t)
        except KeyError: return
        if items and items[-1][0] == 'tris': items[-1][1].append(vs)
        else: items.append(('tris', [vs]))
    for m in _TOK.finditer(body):
        op, args = m.group(1), m.group(2)
        if op == 'gsSPMatrix':
            mtx = args.split(',')[0].strip(); last_mtx = args; continue
        if op == 'gsSPVertex':
            a = [x.strip() for x in args.split(',')]
            r = re.match(r'&?(\w+)(?:\[(\w+)\])?', a[0]); arr = r.group(1); st = int(r.group(2) or '0', 0)
            n, v0 = int(a[1]), int(a[2])
            vs = vtx_arrays[arr]
            for k in range(n):
                x, y, z, _f, s, t, r_, g, b, al = vs[st+k]
                nrm = unit(np.array([c-256 if c > 127 else c for c in (r_, g, b)], float))
                slots[v0+k] = Vert(mtx, np.array([x, y, z], float), np.array([s, t], float), nrm,
                                   np.array([r_, g, b, al], float), (mtx, arr, st+k))
                slots[v0+k].lit = lit; slots[v0+k].ds = ds
            continue
        if op in ('gsSP1Triangle', 'gsSP2Triangles', 'gsSPNTriangles_5b'):
            for t in tri_indices(op, args):
                if op == 'gsSPNTriangles_5b':
                    if pending <= 0: break
                    pending -= 1
                add_tri(t)
            continue
        if op == 'gsSPNTrianglesInit_5b':
            pending, ts = tri_indices(op, args)
            for t in ts:
                if pending <= 0: break
                pending -= 1; add_tri(t)
            continue
        if op == 'gsSPEndDisplayList': continue
        if op == 'gsSPLoadGeometryMode':
            lit = 'G_LIGHTING' in args; ds = 'G_CULL_BACK' not in args
        items.append(('state', f'{op}({args})'))
    return items, last_mtx

POSED = False         # set per skeleton: True when its joint matrices were captured from the game

def wkey(v):
    """weld / edge key: position in the shared posed space; without a captured pose only within one joint"""
    k = tuple(int(round(c)) for c in v.w)
    return k if POSED else (v.j,)+k

def edge_normals(all_tris):
    """edge (end keys) -> summed shading normals at each end, over every triangle that uses it. Both faces of an
    edge see the same sums, so they agree on the curved midpoint."""
    E = {}
    for t in all_tris:
        for a, b in ((t[0], t[1]), (t[1], t[2]), (t[2], t[0])):
            ka, kb = wkey(a), wkey(b)
            if kb < ka: a, b, ka, kb = b, a, kb, ka
            e = E.setdefault((ka, kb), [np.zeros(3), np.zeros(3), 0, True])
            e[0] = e[0]+a.n; e[1] = e[1]+b.n; e[2] += 1
            e[3] = e[3] and all(v.lit and not v.ds for v in t)
    return E

def _curve_n(n_sum, count):
    l = np.linalg.norm(n_sum)
    return n_sum/l if l > 0.5*count else np.zeros(3)      # opposite faces (thin sheets): keep the edge straight

def subdivide(tris, lit, E, A, Ainv):
    """one level: split edges at their PN midpoint (in the captured pose, where the joints meet as the game draws
    them) and re-triangulate. A midpoint between two joints is skinned to the parent-side joint, so the joint still
    bends where it did. Without a captured pose, edges between joints are left whole."""
    mids = {}
    def mid(a, b):
        if a.j != b.j and not POSED: return None
        k = (a.key, b.key) if str(a.key) < str(b.key) else (b.key, a.key)
        if k in mids: return mids[k]
        ka, kb = wkey(a), wkey(b)
        lo, hi = (a, b) if ka <= kb else (b, a)                           # same result whichever copy asks
        w = (lo.w+hi.w)/2
        e = E.get((min(ka, kb), max(ka, kb)))
        if e is not None and e[3]:
            n1, n2 = _curve_n(e[0], e[2]), _curve_n(e[1], e[2])
            d = hi.w-lo.w
            b1 = (2*lo.w+hi.w-np.dot(d, n1)*n1)/3; b2 = (2*hi.w+lo.w+np.dot(d, n2)*n2)/3
            w = w*(1-PN)+((lo.w+3*b1+3*b2+hi.w)/8)*PN
        own = a if (a.j, str(a.mtx)) <= (b.j, str(b.mtx)) else b
        v = Vert(own.mtx, (np.append(w, 1) @ Ainv[own.j])[:3], (a.uv+b.uv)/2, unit(a.n+b.n), (a.c+b.c)/2, ('m',)+k)
        v.grp = own.grp; v.j = own.j; v.w = w; v.lit = a.lit; v.ds = a.ds or b.ds
        mids[k] = v; return v
    out = []
    for a, b, c in tris:
        ab, bc, ca = mid(a, b), mid(b, c), mid(c, a)
        s_ = (ab is not None)+(bc is not None)+(ca is not None)
        if s_ == 3: out += [(a, ab, ca), (ab, b, bc), (ca, bc, c), (ab, bc, ca)]
        elif s_ == 0: out.append((a, b, c))
        else:
            for _ in range(3):                                            # rotate so the split edges come first
                if s_ == 1 and ab is not None: break
                if s_ == 2 and ab is not None and bc is not None: break
                a, b, c = b, c, a; ab, bc, ca = bc, ca, ab
            if s_ == 1: out += [(a, ab, c), (ab, b, c)]
            else: out += [(a, ab, c), (ab, b, bc), (ab, bc, c)]
    return out

def load_poses():
    """skeleton name -> {matrix index: 4x4} from the PC_DUMP_POSE captures (model viewer: villagers posed with the
    player idle animation; a game run: the player)"""
    poses = {}
    for f in (ROOT/'chr_work/pose_npc.txt', ROOT/'chr_work/pose_game.txt'):
        if not f.exists(): continue
        names = {}
        for l in f.read_text().split('\n'):
            t = l.split()
            if not t: continue
            if t[0] == 'S': names[t[2].lower()] = t[1]
            elif t[0] == 'J' and t[1].lower() in names:
                d = poses.setdefault(names[t[1].lower()], {})
                d.setdefault(int(t[2]), np.array([float(x) for x in t[3:19]]).reshape(4, 4))
    return poses

def joint_spaces(pose, nmodels):
    """per matrix index: A (local row vector -> shared space, relative to the base joint) and its inverse"""
    if pose is None or 0 not in pose or any(k not in pose for k in range(nmodels)):
        I = [np.eye(4)]*nmodels; return False, I, I
    base_inv = np.linalg.inv(pose[0])
    A = [pose[k] @ base_inv for k in range(nmodels)]
    return True, A, [np.linalg.inv(m) for m in A]

def mtx_index(mtx, ji, models):
    if mtx is None: return models.index(ji)
    r = re.search(r'\*\s*(\d+)\s*$', mtx) or re.search(r'\[(\d+)\]', mtx)
    return int(r.group(1)) if r else 0

PUSH = 'gsSPMatrix(&pc_cs_ident, G_MTX_PUSH | G_MTX_MUL | G_MTX_MODELVIEW),'
POP = 'gsSPPopMatrix(G_MTX_MODELVIEW),'

def emit_tris(tris, vname, vout, st):
    """chunks of <= SLOTS vertices: per matrix a gsSPMatrix + gsSPVertex, then the triangles. Vertices that the
    original loaded before any matrix command use the matrix the skeleton set for this joint (st['cur'] None); when
    a list mixes both, that matrix is kept on the stack (pushed at the start) and popped back when needed."""
    dl = []; i = 0
    while i < len(tris):
        used = {}; j = i
        while j < len(tris):
            new = [v for v in tris[j] if id(v) not in used]
            if len(used)+len(set(map(id, new))) > SLOTS: break
            for v in new: used.setdefault(id(v), v)
            j += 1
        chunk = tris[i:j]; i = j
        bym = {}
        for v in used.values(): bym.setdefault(v.mtx, []).append(v)
        order = sorted(bym, key=lambda m: (m is not None, m == st['cur'] and m is not None, str(m)))
        slot = {}; s0 = 0
        for mtx in order:
            vs = bym[mtx]
            if mtx is None:
                if st['cur'] is not None: dl += [POP, PUSH]; st['cur'] = None
            elif st['cur'] != mtx:
                dl.append(f'gsSPMatrix({mtx}, G_MTX_NOPUSH | G_MTX_LOAD | G_MTX_MODELVIEW),'); st['cur'] = mtx
            start = len(vout)
            for v in vs:
                slot[id(v)] = len(slot); vout.append(v)
            dl.append(f'gsSPVertex(&{vname}[{start}], {len(vs)}, {s0}),')
            s0 += len(vs)
        for k in range(0, len(chunk), 2):
            t0 = [slot[id(v)] for v in chunk[k]]
            if k+1 < len(chunk):
                t1 = [slot[id(v)] for v in chunk[k+1]]
                dl.append(f'gsSP2Triangles({t0[0]}, {t0[1]}, {t0[2]}, 0, {t1[0]}, {t1[1]}, {t1[2]}, 0),')
            else:
                dl.append(f'gsSP1Triangle({t0[0]}, {t0[1]}, {t0[2]}, 0),')
    return dl

def vtx_line(v, lit, A):
    x, y, z = (int(round(c)) for c in v.p)
    s, t = (int(round(c)) for c in v.uv)
    if v.lit:
        r, g, b = (int(round(c*120)) & 255 for c in unit(v.n @ A[v.j][:3, :3].T))
    else:
        r, g, b = (int(round(c)) for c in v.c[:3])
    return '{{{%d,%d,%d},0,{%d,%d},{%d,%d,%d,%d}}},' % (x, y, z, s, t, r, g, b, int(round(v.c[3])))

HEAD = ['/* Generated by generate_chr_smooth.py: subdivided character display lists. */',
        '#include "pc_platform.h"', '#include "PR/mbi.h"', '#include "libultra/libultra.h"',
        '#include "c_keyframe.h"', '#include "libforest/gbi_extensions.h"', '', 'extern Mtx pc_cs_ident;',
        'static void pc_chr_smooth_patch(cKF_Skeleton_R_c* sk, const int* idx, Gfx* const* dl, int n) {',
        '    int i; for (i = 0; i < n; i++) if (idx[i] < sk->num_joints) sk->joint_table[idx[i]].model = dl[i];',
        '}', '']
CHUNK_BYTES = 2_500_000      # each generated .c stays small enough for the 32-bit compiler

def main():
    global POSES
    POSES = load_poses()
    blocks = []                  # (code lines, skeleton name, [(joint, dl name)])
    total0 = total1 = 0
    for f in FILES:
        text = f.read_text()
        tm = re.search(r'cKF_Joint_R_c (\w+)\[\] = \{(.*?)\n\};', text, re.S)
        sk = re.search(r'cKF_Skeleton_R_c (\w+) = \{', text)
        if not tm or not sk: continue
        joints = [j.strip() for j in re.findall(r'\{\s*(\w+),\s*\d+,\s*cKF_JOINT', tm.group(2))]
        vtx_arrays = {}
        for arr in set(re.findall(r'gsSPVertex\(&?(\w+)', text)):
            if arr in nm.sym: vtx_arrays[arr] = nm.vertices(arr)
        tag = f.stem
        global POSED
        out = []; repl = []; parsed = []
        models = [i for i, j in enumerate(joints) if j != 'NULL']
        POSED, A, Ainv = joint_spaces(POSES.get(sk.group(1)), len(models))
        for ji, dlname in enumerate(joints):
            if dlname == 'NULL': continue
            m = re.search(rf'Gfx {dlname}\[\] = \{{(.*?)\n\}};', text, re.S)
            if not m: continue
            items, last = parse_dl(m.group(1), vtx_arrays)
            if tag == 'end_1' and dlname == 'base_end_model':
                # K.K. Slider: the GC guitar is replaced by New Leaf's (generate_kk_guitar.py), drawn first with the
                # base joint's matrix; the guitar-textured triangles are left out
                kept = [('state', 'gsSPDisplayList(pc_kk_guitar_dl)')]; cur = ''
                for kind, val in items:
                    if kind == 'state' and 'LoadTextureBlock' in val: cur = val
                    if kind == 'tris' and any(f'anime_4_txt + {t}' in cur for t in ('0x080', '0x140', '0x180', '0x400', '0x440', '0x480')):
                        continue
                    kept.append((kind, val))
                items = kept
            for kind, val in items:
                if kind == 'tris':
                    for t in val:
                        for v in t:
                            if v.j is not None: continue          # shared by an earlier triangle: done
                            v.grp = v.mtx if v.mtx is not None else ('joint', ji)
                            v.j = mtx_index(v.mtx, ji, models)
                            v.w = (np.append(v.p, 1) @ A[v.j])[:3]
                            if v.lit: v.n = unit(v.n @ Ainv[v.j][:3, :3].T)
            parsed.append((ji, m.group(1), items, last))
        total0 += sum(len(val) for _, _, items, _ in parsed for kind, val in items if kind == 'tris')
        weld({id(v): v for _, _, items, _ in parsed for kind, val in items if kind == 'tris' for t in val for v in t}.values())
        for _lvl in range(LEVELS):
            E = edge_normals([t for _, _, items, _ in parsed for kind, val in items if kind == 'tris' for t in val])
            for _, body, items, _ in parsed:
                lit = 'G_LIGHTING' in body
                for i, (kind, val) in enumerate(items):
                    if kind == 'tris': items[i] = ('tris', subdivide(val, lit, E, A, Ainv))
        for ji, body, items, last in parsed:
            lit = 'G_LIGHTING' in body
            vname = f'pc_cs_{tag}_{ji}_v'; vout = []; dl = []
            mtxs = {v.mtx for kind, val in items if kind == 'tris' for t in val for v in t}
            st = {'cur': None, 'mixed': None in mtxs and len(mtxs) > 1}
            if st['mixed']: dl.append(PUSH)
            for kind, val in items:
                if kind == 'state': dl.append(val+','); continue
                total1 += len(val)
                dl += emit_tris(val, vname, vout, st)
            if st['mixed']: dl.append(POP)
            if last is not None: dl.append(f'gsSPMatrix({last}),')
            dl.append('gsSPEndDisplayList(),')
            out.append(f'static Vtx {vname}[] ATTRIBUTE_ALIGN(32) = {{')
            out += [vtx_line(v, lit, A) for v in vout]
            out.append('};')
            out.append(f'static Gfx pc_cs_{tag}_{ji}_dl[] = {{'); out += dl; out.append('};')
            repl.append((ji, f'pc_cs_{tag}_{ji}_dl'))
        out.append(f'extern cKF_Skeleton_R_c {sk.group(1)};')
        if tag == 'end_1': out.insert(0, 'extern Gfx pc_kk_guitar_dl[];')
        # data the copied material commands point at (textures, palettes defined in the model file)
        defined = set(re.findall(r'^(?:u8|u16|unsigned char|unsigned short)\s+(\w+)\[', text, re.M))
        used = sorted({w for l in out if l.startswith('gsDP') for w in re.findall('[A-Za-z_][A-Za-z0-9_]*', l)} & defined)
        out = [f'extern u8 {w}[];' for w in used] + out
        blocks.append((out, sk.group(1), repl))
        print(sk.group(1), 'posed' if POSED else 'joints kept separate')
    # split into compile units
    for old in OUTDIR.glob('pc_chr_smooth_*.c'): old.unlink()
    chunks = [[]]; size = 0
    for blk in blocks:
        n = sum(len(l) for l in blk[0])
        if size and size+n > CHUNK_BYTES: chunks.append([]); size = 0
        chunks[-1].append(blk); size += n
    for k, ch in enumerate(chunks):
        lines = list(HEAD)
        for out, _, _ in ch: lines += out
        lines.append(f'void pc_chr_smooth_install_{k}(void) {{')
        for _, skn, repl in ch:
            if not repl: continue
            lines.append('    {')
            lines.append(f'        static const int idx[] = {{ {", ".join(str(j) for j, _ in repl)} }};')
            lines.append(f'        static Gfx* const dl[] = {{ {", ".join(d for _, d in repl)} }};')
            lines.append(f'        pc_chr_smooth_patch(&{skn}, idx, dl, {len(repl)});')
            lines.append('    }')
        lines.append('}')
        (OUTDIR/f'pc_chr_smooth_{k}.c').write_text('\n'.join(lines)+'\n')
    main_c = ['/* Generated by generate_chr_smooth.py: installs the subdivided character display lists. */',
              '#include "pc_platform.h"', '#include "PR/mbi.h"', '#include "libultra/libultra.h"',
              '#include "libforest/gbi_extensions.h"', '#include "pc_kk_guitar.c_inc"   /* K.K. Slider\'s New Leaf guitar */',
              '#include "pc_platform.h"', '#include "PR/mbi.h"', '#include "libultra/libultra.h"', '',
              '#include <stdio.h>', '#include "c_keyframe.h"', '',
              'Mtx pc_cs_ident;', 'extern void* g_pc_pose_dump;',
              'void pc_pose_dump_joint(void* sk, int k, const MtxF* m) {',
              '    static void* seen_sk[8192]; static int seen_k[8192]; static int n = 0; int i, j;',
              '    for (i = 0; i < n; i++) if (seen_sk[i] == sk && seen_k[i] == k) return;',
              '    if (n >= 8192) return;',
              '    seen_sk[n] = sk; seen_k[n] = k; n++;',
              '    fprintf((FILE*)g_pc_pose_dump, "J %p %d", sk, k);',
              '    for (i = 0; i < 4; i++) for (j = 0; j < 4; j++) fprintf((FILE*)g_pc_pose_dump, " %.7g", m->mf[i][j]);',
              '    fprintf((FILE*)g_pc_pose_dump, "\\n"); fflush((FILE*)g_pc_pose_dump);',
              '}']
    main_c += [f'extern cKF_Skeleton_R_c {skn};' for _, skn, _ in blocks]
    main_c += [f'extern void pc_chr_smooth_install_{k}(void);' for k in range(len(chunks))]
    main_c += ['void pc_chr_smooth_install(void) {', '    extern char* getenv(const char*);',
               '    if (getenv("PC_DUMP_POSE") != NULL && (g_pc_pose_dump = fopen(getenv("PC_DUMP_POSE"), "w")) != NULL) {']
    main_c += [f'        fprintf((FILE*)g_pc_pose_dump, "S {skn} %p\\n", (void*)&{skn});' for _, skn, _ in blocks]
    main_c += ['    }', '    if (getenv("PC_CHR_NATIVE") != NULL) return;', '    guMtxIdent(&pc_cs_ident);']
    main_c += [f'    pc_chr_smooth_install_{k}();' for k in range(len(chunks))]
    main_c.append('}')
    (OUTDIR/'pc_chr_smooth.c').write_text('\n'.join(main_c)+'\n')
    # CMake: list the chunk files after pc_chr_smooth.c
    cm = OUTDIR.parent/'CMakeLists.txt'; t = cm.read_text()
    t = re.sub(r'\n    \$\{CMAKE_CURRENT_SOURCE_DIR\}/src/pc_chr_smooth_\d+\.c', '', t)
    t = t.replace('    ${CMAKE_CURRENT_SOURCE_DIR}/src/pc_chr_smooth.c\n', '    ${CMAKE_CURRENT_SOURCE_DIR}/src/pc_chr_smooth.c\n' +
                  ''.join(f'    ${{CMAKE_CURRENT_SOURCE_DIR}}/src/pc_chr_smooth_{k}.c\n' for k in range(len(chunks))))
    cm.write_text(t)
    print(f'{len(blocks)} skeletons, triangles {total0} -> {total1}, {len(chunks)} compile units')

if __name__ == '__main__':
    main()
