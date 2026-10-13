"""Maintainer tool: write pipeline/tables/*.json from the verified provenance data in the work folder.

Tables (all hold paths, offsets and hashes only, no Nintendo data):
  nl_raw_copies.json   work path -> New Leaf RomFS path (files the generators read straight from the ROM)
  exports.json         Ohana exports: [out dir, RomFS path, exporter] (each verified to reproduce the dev exports)
  dumpanims.json       DumpAnims exports
  gc_files.json        files taken from the GameCube disc (archive members, slices)
  nl_required.json     md5 of every New Leaf RomFS file the mod reads (tested USA release)
  steps.json           generator steps, in order
  texture_packs.json   which generated folders become texture packs
  gc_tex_locations.json GameCube textures used by the interior steps (offsets + hash check)
"""
import json, hashlib, glob, os
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
T = REPO / 'pipeline' / 'tables'
T.mkdir(parents=True, exist_ok=True)
WORK = Path(r'G:\PC_ports\ACPC\ship\_work')
DEV = Path(r'G:\PC_ports\ACPC\asset_import_work')
CCI = r'E:\acnl\animal crossing fan made.cci'
BS = chr(92)
inv = {e['path']: e for e in json.load(open(DEV / '3ds_inventory.json'))}


def dump(name, obj):
    (T / name).write_text(json.dumps(obj, indent=1, sort_keys=isinstance(obj, dict)))
    print(name, len(obj))


# ---- raw copies
raw = json.load(open(WORK / 'dev' / 'nl_raw_copies.json'))
raw.update(json.load(open(WORK / 'dev' / 'nlui_raw.json')))
dump('nl_raw_copies.json', raw)

# ---- which export folders the generators read
reads = set()
for tj in glob.glob(str(WORK / 'trace' / '*.json')):
    if os.path.basename(tj).startswith('_'):
        continue
    t = json.load(open(tj))
    for x in t['reads'] + t['read_and_written']:
        reads.add(x.lower().replace(BS, '/'))


def used(d):
    d = d.lower() + '/'
    return any(x.startswith(d) for x in reads)


exports = {}
for d, r in json.load(open(WORK / 'dev' / 'exports_verified.json')).items():
    if r['match']:
        src = r['src'] if r['kind'] == 'romfs' else raw[r['src']]
        exports[d] = (src, r['tool'])
for f in glob.glob(str(WORK / 'dev' / 'tex_exports_*.json')):
    for folder, name, src, tool in json.load(open(f)):
        exports[f'furn_work/{folder}/{name}'] = (src, tool)
for d, r in json.load(open(WORK / 'dev' / 'manual_exports.json')).items():
    if r:
        exports[d] = tuple(r)
exports['tree_source/outside'] = ('/Fg/Bcres/FgItemOutside.bcres', 'ExportModels.exe')
for d, r in json.load(open(WORK / 'dev' / 'more_exports.json')).items():
    if r:
        exports[d] = tuple(r)
keep = []
for d, (src, tool) in sorted(exports.items()):
    if d.startswith('furn_work/nl_ftr/shopumb_') or d.startswith('station_work') or d in ('kk_source/skkv', 'terrain_source/uv_audit'):
        continue
    if not used(d) and not d.startswith('furn_work/'):
        continue
    keep.append([d, src, tool.replace('.exe', '')])
dump('exports.json', keep)

# ---- DumpAnims
dump('dumpanims.json', [
    ['human_anim/humanAnimCommon.bcres', 'anim_dump/humanAnimCommon.json'],
    ['human_anim/Common.bcres', 'anim_dump/sklt.json'],
] + [[f'tool_source/{t}.bcres', f'anim_dump/{t}.json'] for t in ('pole', 'net', 'axe', 'sling', 'umb_red', 'windmill', 'balloon_nml_tool')])

# ---- GameCube files
gc = []
for n in ('face_boy.bin', 'tex_boy.bin', 'pallet_boy.bin'):
    gc.append({'src': 'forest_1st.arc:data/' + n, 'dst': 'chr_work/arc/' + n})
for n in ('message_data.bin', 'message_data_table.bin'):
    gc.append({'src': 'forest_2nd.arc:data/' + n, 'dst': 'chr_work/arc/' + n})
for i in range(255):
    gc.append({'src': 'forest_1st.arc:data/tex_boy.bin', 'slice': [i * 512, (i + 1) * 512], 'dst': f'_outer/fixes_test/cloth/cloth_{i:03d}.tex'})
    gc.append({'src': 'forest_1st.arc:data/pallet_boy.bin', 'slice': [i * 32, (i + 1) * 32], 'dst': f'_outer/fixes_test/cloth/cloth_{i:03d}.pal'})
for kind, sz in (('floor', 8224), ('wall', 4128)):
    for i in range(71):
        gc.append({'src': f'forest_2nd.arc:data/player_room_{kind}.bin', 'slice': [i * sz, (i + 1) * sz], 'swap16_head': 32,
                   'dst': f'furn_work/room/{kind}_{i:02d}.bin'})
dump('gc_files.json', gc)

# ---- md5 of every New Leaf file the mod reads
need = set(raw.values()) | {src for _, src, _ in keep} | {'/Particle/seadPtcl.ptcl', '/Environment/EnvironmentParameter.bin'}
for p in list(inv):
    if p.startswith('/Item/Model/') or p.startswith('/Ftr/Remake/Texture/'):
        pass
req = {}
with open(CCI, 'rb') as f:
    for p in sorted(need):
        e = inv[p]
        f.seek(e['offset'])
        req[p] = hashlib.md5(f.read(e['size'])).hexdigest()
dump('nl_required.json', req)

# ---- GameCube textures for the interior steps
loc = json.load(open(WORK / 'dev' / 'gc_tex_locations.json'))
dump('gc_tex_locations.json', loc)
