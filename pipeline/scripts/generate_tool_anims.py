"""New Leaf tool-use animations retargeted onto the GameCube player skeleton.

Both skeletons share the bone names (base, chest, arms, legs, head) and the same world frame (y up, facing +z,
left arm +x). Each mapped GC joint takes the New Leaf bone's world rotation times a constant offset fixed by the two
idle poses (GC wait1 vs NL nml_wait1): GC_world(t) = NL_world(t) * inv(NL_idle) * GC_idle; local angles are then
taken against the GC parent chain. Unmapped GC joints keep the native animation. The GC clip length is kept (the
game times hits and state changes by frame), and for swings the lowest point of the right hand is lined up with the
GC clip's, so the native hit frame still matches the motion.
Writes ACGC-PC-Port/pc/src/pc_tool_anims.c_inc and screens/tools/anim_*.png stick-figure strips.
"""
from pathlib import Path
import numpy as np
import ckf, nl_anim as na, stick
from PIL import Image

ROOT = Path(__file__).resolve().parent
PA = ROOT/'ACGC-PC-Port/src/data/model/player_anim.c'
JT = ckf.joints(ROOT/'ACGC-PC-Port/src/data/model/boy_model.c', 'boy_1')
PAR = ckf.parents(JT)
NJ = len(JT)
MAP = {'base': 1, 'Lfoot1': 3, 'Lfoot2': 4, 'Lfoot3': 5, 'Rfoot1': 7, 'Rfoot2': 8, 'Rfoot3': 9, 'chest': 13,
       'Larm1': 15, 'Larm2': 16, 'Rarm1': 18, 'Rarm2': 19, 'Rhand': 20, 'head': 24}
GC_OF = {g: na.BONES.index(n) for n, g in MAP.items()}
K = 70.0      # NL -> GC length units for the body translation

# GC clip <- New Leaf clips played back to back; align=True lines up the lowest right-hand point (swings)
# GC clip <- New Leaf clips played back to back; align=True lines up the lowest right-hand point (swings).
# The hold poses (axe1, net1, ...) stay GameCube: the game blends them per body part with walk/run, and the
# right hand offset is taken from the matching GC/NL hold-pose pair so the tool keeps its grip.
CLIPS = [
    ('net_swing1', ['net_swing1'], True, ('net1', 'net_wait1')),
    ('dig1', ['scoop_swing1', 'scoop_dig1'], True, ('scoop1', 'scoop_wait1')),
    ('dig_suka1', ['scoop_swing1', 'scoop_suka1'], True, ('scoop1', 'scoop_wait1')),
    ('not_dig1', ['scoop_swing1', 'scoop_hane1'], True, ('scoop1', 'scoop_wait1')),
]
# Checked in game 2026-10-06 and left GameCube: the axe swings (New Leaf's 4-frame wind-up reads much weaker than
# the GC chop), the rod cast (New Leaf clip is 50 frames vs GC 32, release timing not verifiable on land) and the
# umbrella opening (could not be verified). Their clips were:
#   axe_swing1 <- axe_swing1+axe_hit1, axe_hane1 <- axe_swing1+axe_hane1, axe_suka1 <- axe_swing1+axe_suka1,
#   sao_swing1 <- pole_swing1, umb_open1 <- umb_open1

A = na.anims()
gc_idle = ckf.Anim(PA, 'ply_1_wait1', NJ)
_rt0, _r0 = gc_idle.sample(1)
GW0 = ckf.world(JT, _rt0, _r0)
NW0 = na.pose(A['nml_wait1'], 0)
OFF = {g: NW0[GC_OF[g]][:3, :3].T@GW0[g][:3, :3] for g in GC_OF}
NBASE0 = NW0[na.BONES.index('base')][:3, 3]


def nl_seq(names):
    lens = [A[n]['frames'] for n in names]
    total = float(sum(lens))
    def at(t):
        for n, L in zip(names, lens):
            if t <= L or n == names[-1]: return na.pose(A[n], min(t, L))
            t -= L
    return at, total


def retarget(gc_name, nl_names, align, hold):
    gca = ckf.Anim(PA, 'ply_1_'+gc_name, NJ)
    N = gca.frames
    gh = ckf.world(JT, *ckf.Anim(PA, 'ply_1_'+hold[0], NJ).sample(1)); nh = na.pose(A[hold[1]], 0)
    off = dict(OFF); off[20] = nh[GC_OF[20]][:3, :3].T@gh[20][:3, :3]
    at, total = nl_seq(nl_names)
    gframes = np.arange(1, N+1, dtype=float)
    # time map GC frame -> NL time
    if N == 1 or total == 0: tmap = lambda f: 0.0
    else:
        u = lambda f: (f-1)/(N-1)
        if align:
            ts = np.linspace(0, total, 61)
            nl_low = ts[int(np.argmin([at(t)[na.BONES.index('Rhand')][1, 3] for t in ts]))]
            gl = [ckf.world(JT, *gca.sample(f))[20][1, 3] for f in gframes]
            gc_low = gframes[int(np.argmin(gl))]
            if 1 < gc_low < N and 0 < nl_low < total:
                tmap = lambda f: np.interp(f, [1, gc_low, N], [0, nl_low, total])
            else: tmap = lambda f: u(f)*total
        else: tmap = lambda f: u(f)*total
    root = []; rots = []
    for f in gframes:
        rt, r = gca.sample(f)
        NW = at(tmap(f))
        r = r.copy()
        W = []
        for i in range(NJ):
            if i in GC_OF:
                Rw = NW[GC_OF[i]][:3, :3]@off[i]
                Rp = W[PAR[i]][:3, :3] if PAR[i] >= 0 else np.eye(3)
                r[i] = ckf.euler_zyx(Rp.T@Rw)
            L = np.eye(4); L[:3, :3] = ckf.rotm(r[i]); L[:3, 3] = rt if i == 0 else JT[i][2]
            W.append(L if PAR[i] < 0 else W[PAR[i]]@L)
        d = (NW[na.BONES.index('base')][:3, 3]-NBASE0)*K
        root.append(_rt0+d); rots.append(r)
    return gca, np.array(root), np.array(rots), tmap, at


def unwrap(v):
    """degrees -> continuous tenths of a degree"""
    v = np.degrees(np.unwrap(np.radians(v)))
    return np.round(v*10).astype(int)


out = ['/* Generated by generate_tool_anims.py: New Leaf tool animations on the GC player skeleton. */']
patches = []
strips = []
for gc_name, nl_names, align, hold in CLIPS:
    gca, root, rots, tmap, at = retarget(gc_name, nl_names, align, hold)
    N = gca.frames
    chans = [np.round(root[:, k]).astype(int) for k in range(3)]
    for i in range(NJ):
        for k in range(3): chans.append(unwrap(rots[:, i, k]))
    flags = [0]*NJ; fixed = []; keys = []; data = []
    for c, vals in enumerate(chans):
        const = np.all(vals == vals[0])
        if c < 3: bit = (32, 16, 8)[c]; j = 0
        else: j = (c-3)//3; bit = (4, 2, 1)[(c-3) % 3]
        if const or N == 1:
            fixed.append(int(vals[0]))
        else:
            flags[j] |= bit
            g = np.gradient(vals.astype(float))
            keys.append(N)
            for f in range(N): data += [f+1, int(vals[f]), int(np.clip(round(g[f]*30), -32768, 32767))]
    nm_ = f'pc_nl_ply_{gc_name}'
    out.append(f'static u8 {nm_}_flags[] = {{{",".join(map(str, flags))}}};')
    out.append(f'static s16 {nm_}_keys[] = {{{",".join(map(str, keys)) or "0"}}};')
    out.append(f'static s16 {nm_}_fixed[] = {{{",".join(map(str, fixed)) or "0"}}};')
    out.append(f'static s16 {nm_}_data[] = {{')
    out += [','.join(map(str, data[i:i+30]))+',' for i in range(0, len(data), 30)] or ['0,']
    out.append('};')
    out.append(f'static cKF_Animation_R_c {nm_} = {{ {nm_}_flags, {nm_}_data, {nm_}_keys, {nm_}_fixed, -1, {N} }};')
    patches.append((f'cKF_ba_r_ply_1_{gc_name}', nm_))
    # review strip: GC native (red) vs retargeted (blue) at 6 points
    ims = []
    for f in np.linspace(1, N, 6):
        fi = int(round(f))
        Wg = ckf.world(JT, *gca.sample(fi))
        Wn = ckf.world(JT, root[fi-1], rots[fi-1])
        ims.append(stick.draw([(np.array([w[:3, 3] for w in Wg]), PAR, (200, 0, 0)),
                               (np.array([w[:3, 3] for w in Wn]), PAR, (0, 0, 200))], size=160, scale=0.05))
    strip = Image.new('RGB', (320*6, 160), 'white')
    for k, im in enumerate(ims): strip.paste(im, (320*k, 0))
    strips.append(strip)
    print(gc_name, N, '<-', nl_names, 'flags', sum(bin(x).count('1') for x in flags))

out += [f'extern cKF_Animation_R_c {a};' for a, _ in patches]
out += ['void pc_tool_patch_anims(void) {'] + [f'    {a} = {b};' for a, b in patches] + ['}']
(ROOT/'ACGC-PC-Port/pc/src/pc_tool_anims.c_inc').write_text('\n'.join(out)+'\n')
sheet = Image.new('RGB', (320*6, 160*len(strips)), 'white')
for k, s in enumerate(strips): sheet.paste(s, (0, 160*k))
sheet.save(ROOT/'screens/tools/anim_review.png')
