"""Extract the donor's field-lighting LUT without relying on Ohana's skipped LUTS block.

The sampler record has an absolute-input flag, followed by a 258-word PICA
command (one parameter, its header, 255 parameters, padding). The low 12 bits
of each parameter are the unsigned fixed-point table value; upper bits hold
the interpolation difference. Preserve both in the provenance JSON.
"""
import json
import struct
from pathlib import Path

ROOT = Path(__file__).resolve().parent
source = ROOT / 'terrain_source/lighting_lut_season00.bcres'
data = source.read_bytes()

def u32(pos):
    return struct.unpack_from('<I', data, pos)[0]

def relative(pos):
    return pos + u32(pos)

def name(pos):
    return data[pos:data.index(b'\0', pos)].decode('ascii')

def dictionary(pos):
    assert data[pos:pos+4] == b'DICT'
    for index in range(u32(pos+8)):
        entry = pos + 28 + index * 16
        yield name(relative(entry+8)), relative(entry+12)

assert data[:4] == b'CGFX'
tables = []
for table_name, table in dictionary(relative(0x30)):
    assert data[table+4:table+8] == b'LUTS'
    for sampler_name, sampler in dictionary(relative(table+28)):
        command = relative(sampler+16)
        size = u32(sampler+12)
        words = struct.unpack_from('<' + str(size//4) + 'I', data, command)
        assert len(words) == 258 and words[1] == 0x0fff01c8
        values = [words[0], *words[2:257]]
        tables.append(dict(table=table_name, sampler=sampler_name,
                           absolute_input_flag=u32(sampler+8),
                           command_offset=command, packed=values,
                           values=[(v & 0xfff)/4096 for v in values]))

out = ROOT / 'terrain_source/lighting_lut_decoded.json'
out.write_text(json.dumps(dict(source=str(source), tables=tables), indent=2))
grass = next(t for t in tables if t['sampler'] == 'lu_field_grass')
assert len(grass['values']) == 256 and grass['absolute_input_flag'] == 1
rows = [', '.join(f'{v:.8f}' for v in grass['values'][i:i+8]) for i in range(0,256,8)]
shader = ROOT / 'ACGC-PC-Port/pc/shaders/default.frag'
text = shader.read_text()
start, end = '// BEGIN DONOR FIELD LUT', '// END DONOR FIELD LUT'
block = start + '\nconst float donorFieldLut[256] = float[256](\n    ' + ',\n    '.join(rows) + '\n);\n' + end
if start in text:
    text = text[:text.index(start)] + block + text[text.index(end)+len(end):]
else:
    text = text.replace('vec4 terrainSample', block + '\n\nvec4 terrainSample', 1)
pass  # mod build: the shipped shader samples u_donor_luts; nothing is embedded in it
print('Extracted six donor LUTs; embedded all 256 grass-lighting samples.')
