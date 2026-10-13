"""Shop umbrellas (Able Sisters display): GC obj_shop_umbNN -> the New Leaf umbrella (held-tool export), placed along
the GC umbrella's own shaft axis (handle -> canopy), canopy radius and centre matched, drawn without back-face
culling (the canopy is single-sided, its underside showed as dark). UMB map from generate_tools.py."""
import json, shutil, re
from pathlib import Path
import numpy as np
import gen_furn, native_models as nm
ROOT = Path(__file__).resolve().parent
src = open(ROOT/'generate_tools.py').read()
UMB = eval(src[src.index('UMB = {')+6:src.index('}', src.index('UMB = {'))+1])
FW = ROOT/'furn_work'/'nl_ftr'
GCF = nm.parse_model_file(ROOT/'ACGC-PC-Port/src/data/model/obj_shop_umb01.c')
done = []
for num, tool in UMB.items():
    tris = GCF[f'obj_shop_umb{num:02d}_model']
    kasa = np.array([p[:3] for t in tris if 'kasa' in t[0] for p in t[5]], float)
    tuka = np.array([p[:3] for t in tris if 'kasa' not in t[0] for p in t[5]], float)
    axis = kasa.mean(0)-tuka.mean(0); axis /= np.linalg.norm(axis)
    rad_gc = np.percentile(np.linalg.norm((kasa-kasa.mean(0))-np.outer((kasa-kasa.mean(0))@axis, axis), axis=1), 95)
    d = json.load(open(ROOT/'tool_source'/tool/f'{tool}.json'))
    can = [m for m in d['meshes'] if not m['texture'].endswith('_0')] or d['meshes']
    C = np.array([v['position'] for m in can for v in m['vertices']], float)
    rad_nl = np.percentile(np.linalg.norm(C[:, :2]-C[:, :2].mean(0), axis=1), 95)
    s = rad_gc/rad_nl
    # rotation taking NL +z (shaft, canopy end) to the GC axis
    z = np.array([0, 0, 1.0]); v = np.cross(z, axis); c = float(z@axis)
    vx = np.array([[0, -v[2], v[1]], [v[2], 0, -v[0]], [-v[1], v[0], 0]])
    R = np.eye(3)+vx+vx@vx/(1+c)
    off = kasa.mean(0)-s*(R@C.mean(0))
    for m in d['meshes']:
        for vv in m['vertices']: vv['position'] = list(off+s*(R@np.array(vv['position'], float)))
    # face every mesh's triangles outward (along the shaft axis / away from it): the canopy is single-sided and
    # its winding pointed the lit side underneath, so the top rendered dark
    for m in d['meshes']:
        vs = m['vertices']; dots = []
        for i in range(0, len(vs)-2, 3):
            P = np.array([vs[i+j]['position'] for j in range(3)], float)
            n = np.cross(P[1]-P[0], P[2]-P[0]); cen = P.mean(0)-kasa.mean(0)
            dots.append(float(n@axis)+0.3*float(n@(cen-(cen@axis)*axis)))
        if sum(dots) < 0:
            m['vertices'] = [vs[i+j] for i in range(0, len(vs)-2, 3) for j in (0, 2, 1)]
    out = FW/f'shopumb_{tool}'; out.mkdir(parents=True, exist_ok=True)
    json.dump(d, open(out/f'shopumb_{tool}.json', 'w'))
    for p in (ROOT/'tool_source'/tool).glob('*.png'): shutil.copy(p, out/p.name)
    for p in (ROOT/'tool_source_hd'/tool).glob('*.png'): shutil.copy(p, out/p.name)   # 4x canopies (gen_shopumb_hd.py)
    key = f'shop_umb{num:02d}'
    gen_furn.BOUNDS_SYM[key] = f'obj_shop_umb{num:02d}_v'; gen_furn.NOFIT[key] = True
    gen_furn.main(key, f'shopumb_{tool}', 0.0)
    f = ROOT/f'ACGC-PC-Port/src/furniture/pc_furn_{key}.c_inc'
    t = f.read_text().replace('G_ZBUFFER|G_SHADE|G_CULL_BACK|', 'G_ZBUFFER|G_SHADE|')
    # lit as a flat open canopy facing up (the computed normals left it in shadow: dark purple-blue)
    t = re.sub(r'(\{\{\{-?\d+,-?\d+,-?\d+\},0,\{-?\d+,-?\d+\},\{)\d+,\d+,\d+(,255\}\}\},)', r'\g<1>0,126,0\g<2>', t)
    f.write_text(t)
    r = json.load(open(ROOT/'furn_work/furn_registry.json'))
    r[key] = {'nl': f'shopumb_{tool}', 'gfx': [f'obj_shop_umb{num:02d}_model', f'obj_shop_umb{num:02d}_modelT']}
    json.dump(r, open(ROOT/'furn_work/furn_registry.json', 'w'), indent=1)
    done.append(key); print(key, tool, 'scale', round(s, 1))
b = json.load(open(ROOT/'furn_work/furn_block.json')); b = [x for x in b if x not in done]; json.dump(b, open(ROOT/'furn_work/furn_block.json', 'w'))
gen_furn.write_master(json.load(open(ROOT/'furn_work/furn_registry.json')))
