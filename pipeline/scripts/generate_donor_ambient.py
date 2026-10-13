"""Regenerate original slot4 global ambient table; preserve runtime sampler."""
from pathlib import Path
import json
root=Path(__file__).resolve().parent
entry=next(e for e in json.loads((root/'3ds_inventory.json').read_text()) if e['path']=='/Environment/EnvironmentParameter.bin')
with Path(__import__('os').environ['ACPC_NL_ROM']).open('rb') as f:f.seek(entry['offset']);data=f.read(entry['size'])
p=root/'ACGC-PC-Port/src/game/pc_donor_ambient.c_inc'
s=p.read_text();start=s.index('static const unsigned char');end=s.index('};',start)+2
lines=['static const unsigned char pc_donor_ambient_palettes[3][24][3] = {']
for weather in range(3):
 lines.append(' {')
 for hour in range(24):
  o=16+(weather*24+hour)*140+16
  lines.append('  {'+','.join(map(str,data[o:o+3]))+'}, /* %02d:00 */'%hour)
 lines.append(' },')
lines.append('};');p.write_text(s[:start]+'\n'.join(lines)+s[end:])
