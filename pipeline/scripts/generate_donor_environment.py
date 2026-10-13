"""Export original 3DS hourly sky/cloud and lighting colors.
Original ARM runtime calls verify sky slots 5/6 (0x1a3ef8), cloud 7/8
(0x22ece8), fragment diffuse/specular 0/1 (0x3d5bdc), and hemisphere
sky/ground 2/3 (0x3f3fa4). Resource field names corroborated by SPICA.
ARM0x1f6ee8 verifies ordinary blocks0/1/2 as clear/cloudy/precipitation.
Special daily-pattern palettes3..8 have no direct native-host equivalent.
See terrain_source/donor_runtime_environment_audit.txt for evidence.
"""
from pathlib import Path
import json
import struct

root = Path(__file__).resolve().parent
inventory = json.loads((root / '3ds_inventory.json').read_text())
entry = next(e for e in inventory if e['path'] == '/Environment/EnvironmentParameter.bin')
with Path(__import__('os').environ['ACPC_NL_ROM']).open('rb') as source:
    source.seek(entry['offset'])
    data = source.read(entry['size'])
assert len(data) == 16 + 216 * 140
assert struct.unpack_from('<4I', data) == (3000, 1000, 0, 0)

def table(name, slots):
    lines = ['static const unsigned char %s[3][24][%d][3] = {' % (name, len(slots))]
    for block in range(3):
        lines.append('  { /* donor weather block %d */' % block)
        for hour in range(24):
            record = data[16 + (block * 24 + hour) * 140:]
            colors = [list(record[slot * 4:slot * 4 + 3]) for slot in slots]
            lines.append('    {' + ','.join('{' + ','.join(map(str, c)) + '}' for c in colors) + '}, /* %02d:00 */' % hour)
        lines.append('  },')
    return lines + ['};']

comment = [
    '/* Generated from original local 3DS EnvironmentParameter.bin.',
    ' * Original ARM 1f6ee8 maps ordinary clear/cloudy/precipitation to blocks0/1/2.',
    ' * Host has no cloudy enum: native transition blends clear0 and rain/snow2.',
    ' * Special daily weather-pattern blocks3..8 remain unrepresented. */'
]
lines = comment + [
    '/* Sky5/6 and cloud7/8 verified by original ARM sky/cloud actors. */',
    'enum { PC_DONOR_SKY_ZENITH, PC_DONOR_SKY_HORIZON,',
    '       PC_DONOR_CLOUD_LIGHT, PC_DONOR_CLOUD_SHADE };'
] + table('pc_donor_weather_environment', (5,6,7,8)) + [
    'static void pc_donor_environment_color(unsigned char out[3], int slot, int now, float wet) {',
    '    int h, n, s, c;',
    '    now %= 86400; if (now < 0) now += 86400;',
    '    h = now / 3600; n = (h + 1) % 24; s = now % 3600;',
    '    if (wet < 0.0f) wet = 0.0f; if (wet > 1.0f) wet = 1.0f;',
    '    if (slot < 0 || slot > 3) slot = 0;',
    '    for (c = 0; c < 3; ++c) {',
    '        float dry = (pc_donor_weather_environment[0][h][slot][c] * (3600-s)',
    '            + pc_donor_weather_environment[0][n][slot][c] * s) / 3600.0f;',
    '        float rain = (pc_donor_weather_environment[2][h][slot][c] * (3600-s)',
    '            + pc_donor_weather_environment[2][n][slot][c] * s) / 3600.0f;',
    '        out[c] = (unsigned char)(dry + (rain-dry)*wet + 0.5f);',
    '    }',
    '}',
]
lines += [
    '',
    '/* Candidate cloud-cutoff mapping: source float 0 tracks clear/overcast',
    ' * density plausibly, but its original runtime role is NOT verified.',
    ' * It may instead be a sunlight/shadow parameter; this is a prototype',
    ' * interpretation of original values, not a confirmed material binding. */',
    'static const float pc_donor_clear_cloud_cutoff_candidate[24] = {'
]
for hour in range(24):
    value = struct.unpack_from('<f', data, 16 + hour * 140 + 88)[0]
    lines.append('    %.9ff, /* %02d:00 */' % (value, hour))
lines += [
    '};',
    'static float pc_donor_cloud_cutoff(int seconds_since_midnight) {',
    '    int hour, next, seconds;',
    '    seconds_since_midnight %= 86400;',
    '    if (seconds_since_midnight < 0) seconds_since_midnight += 86400;',
    '    hour = seconds_since_midnight / 3600;',
    '    next = (hour + 1) % 24;',
    '    seconds = seconds_since_midnight % 3600;',
    '    return pc_donor_clear_cloud_cutoff_candidate[hour] +',
    '        (pc_donor_clear_cloud_cutoff_candidate[next] - pc_donor_clear_cloud_cutoff_candidate[hour]) * (seconds / 3600.0f);',
    '}',
]
(root / 'ACGC-PC-Port/src/game/pc_donor_environment.c_inc').write_text('\n'.join(lines) + '\n')
light_lines = comment + [
    '/* Verified ARM bindings: diffuse0, specular0/specular1=1, hemiSky2, hemiGround3. */'
] + table('pc_donor_weather_lights', (0,1,2,3)) + [
    'static void pc_donor_lighting_colors(unsigned char out[4][3], int now, float wet) {',
    '    int h, n, s, role, c;',
    '    now %= 86400; if (now < 0) now += 86400;',
    '    h = now / 3600; n = (h + 1) % 24; s = now % 3600;',
    '    if (wet < 0.0f) wet = 0.0f; if (wet > 1.0f) wet = 1.0f;',
    '    for (role = 0; role < 4; ++role) for (c = 0; c < 3; ++c) {',
    '        float dry = (pc_donor_weather_lights[0][h][role][c] * (3600-s)',
    '            + pc_donor_weather_lights[0][n][role][c] * s) / 3600.0f;',
    '        float rain = (pc_donor_weather_lights[2][h][role][c] * (3600-s)',
    '            + pc_donor_weather_lights[2][n][role][c] * s) / 3600.0f;',
    '        out[role][c] = (unsigned char)(dry + (rain-dry)*wet + 0.5f);',
    '    }',
    '}',
]
(root / 'ACGC-PC-Port/src/game/pc_donor_lighting.c_inc').write_text('\n'.join(light_lines) + '\n')
