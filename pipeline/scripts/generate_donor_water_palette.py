from pathlib import Path
import json,struct
root=Path(__file__).resolve().parent
entry=next(e for e in json.loads((root/'3ds_inventory.json').read_text()) if e['path']=='/Environment/EnvironmentParameter.bin')
with Path(__import__('os').environ['ACPC_NL_ROM']).open('rb') as f:
 f.seek(entry['offset']); data=f.read(entry['size'])
assert len(data)==16+216*140 and struct.unpack_from('<4I',data)==(3000,1000,0,0)
lines=['/* Original environment slots9/10/11: water C0, water TEV buffer, submerged bank. ARM358818 ->777bdc. Weather0/1/2 clear/cloudy/precipitation. Alpha remains material-owned. */','static const unsigned char pc_donor_water_palettes[3][24][3][3] = {']
for block in range(3):
 lines.append('  { /* weather %d */'%block)
 for hour in range(24):
  o=16+(block*24+hour)*140
  colors=[list(data[o+s*4:o+s*4+3]) for s in (9,10,11)]
  lines.append('    {'+','.join('{'+','.join(map(str,c))+'}' for c in colors)+'}, /* %02d:00 */'%hour)
 lines.append('  },')
lines+=['};','''static void pc_donor_water_colors(unsigned char out[3][3], int now, float wet) {
    int h,n,s,role,c;
    now%=86400; if(now<0)now+=86400;
    h=now/3600; n=(h+1)%24; s=now%3600;
    if(wet<0.0f)wet=0.0f; if(wet>1.0f)wet=1.0f;
    for(role=0;role<3;++role)for(c=0;c<3;++c) {
        float dry=(pc_donor_water_palettes[0][h][role][c]*(3600-s)+pc_donor_water_palettes[0][n][role][c]*s)/3600.0f;
        float rain=(pc_donor_water_palettes[2][h][role][c]*(3600-s)+pc_donor_water_palettes[2][n][role][c]*s)/3600.0f;
        /* Source CPU color quantizer truncates; distinct from TEV rounding. */
        out[role][c]=(unsigned char)(dry+(rain-dry)*wet);
    }
}''']
(root/'terrain_source/pc_donor_water_palette.c_inc').write_text('\n'.join(lines)+'\n')
print('Staged 3 weather blocks x 24 hours x 3 RGB roles; runtime untouched.')
