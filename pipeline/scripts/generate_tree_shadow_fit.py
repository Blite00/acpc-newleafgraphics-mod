"""Size the mature hardwood shadow to the imported original canopy footprint."""
from pathlib import Path
import json,struct
R=Path(__file__).resolve().parent
all_vertices=json.loads((R/'tree_source/season08_normals/fg_treeA_4.json').read_text())['meshes'][0]['vertices']
scale=12243/max(v['position'][1]for v in all_vertices)
# Exact same original bark/leaf partition as generate_tree_world.py.
leaves=all_vertices[79*3:]
source=[max(v['position'][axis]for v in leaves)-min(v['position'][axis]for v in leaves)for axis in (0,2)]
rel=(R/'foresta.rel').read_bytes()
quad=[struct.unpack_from('>hhh',rel,0x3EF0F0+i*16)for i in range(4)]
native=[max(v[axis]for v in quad)-min(v[axis]for v in quad)for axis in (0,2)]
factors=[source[i]*scale/native[i]for i in range(2)]
center_z=(min(v['position'][2]for v in leaves)+max(v['position'][2]for v in leaves))*scale*.5
(R/'ACGC-PC-Port/pc/include/pc_tree_shadow_fit.h').write_text(
 '/* Generated canopy/host-shadow footprint ratios; preserve native sunlight shear. */\n'
 '#define PC_MATURE_TREE_SHADOW_WIDTH %.9ff\n#define PC_MATURE_TREE_SHADOW_DEPTH %.9ff\n#define PC_MATURE_TREE_SHADOW_CENTER_Z %.9ff\n'%tuple(factors+[center_z]))
(R/'shadow_source/tree_footprint_fit.json').write_text(json.dumps({
 'source':'Original fg_treeA_4 leaf geometry at the existing importer scale',
 'canopy_world_xz':[x*scale*.01 for x in source],
 'native_shadow_world_xz':[x*.01 for x in native], 'fit_xz':factors,
 'scope':'Mature imported hardwood shadow fits the donor canopy extents and Z center; native sunlight X shear and time/weather opacity retained. Full-mask spatial alpha owns edge fade. NPC/player circles and collisions unchanged.',
 'limitation':'Canopy-footprint adapter; donor shadow resource contains only a texture, not projection geometry.'},indent=2))
print('Mature hardwood shadow canopy fit',factors)
