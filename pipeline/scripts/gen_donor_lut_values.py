"""pc/src/pc_donor_lut_values.c_inc: the New Leaf field lighting LUTs (grass, cliff, water, water fresnel) as floats,
from terrain_source/lighting_lut_decoded.json (extract_terrain_lut.py)."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ROWS = ['lu_field_grass', 'lu_field_cliff0', 'lu_field_water', 'lu_field_water_f']


def main():
    d = json.load(open(ROOT / 'terrain_source' / 'lighting_lut_decoded.json'))
    t = {e['sampler']: e['values'] for e in d['tables']}
    out = ['/* Original GLSL decimal LUT values, row order: field, cliff, water, fresnel. */',
           'static const GLfloat pc_donor_lut_values[4][256] = {']
    for k, name in enumerate(ROWS):
        v = t[name]
        out.append('{')
        out += [','.join('%.8ff' % x for x in v[i:i + 8]) + ',' for i in range(0, 256, 8)]
        out.append('},')
    out.append('};')
    with open(ROOT / 'ACGC-PC-Port' / 'pc' / 'src' / 'pc_donor_lut_values.c_inc', 'w', newline='\n') as f:
        f.write('\n'.join(out) + '\n')
    print('wrote pc_donor_lut_values.c_inc')


if __name__ == '__main__':
    main()
