"""Seamless mound foliage assembled from original seasonal 3DS leaf/clover cutouts.
This is an adaptation for native large mound meshes, not a donor texture export.
"""
from pathlib import Path
from PIL import Image
import random,json
R=Path(__file__).resolve().parent;O=R/'foliage_source';O.mkdir(exist_ok=True)
# Original treeA2 canopy clusters follow the same plain-hardwood calendar.
# The minor fg_grassE clover accents retain their own original seasonal art.
leaves=[(0,0,48,57),(52,0,106,58),(0,58,53,112),(54,59,108,112)]
clovers=[(64,0,92,31),(91,0,120,31)]
size=256;images=[];wall_names=[];wall_seen={};out=['/* Derived original seasonal leaf/clover cutouts; no recoloring. */'];names=[];seen={}
def stamp_wrap(tile,cut,x,y):
 for ox in [-size,0,size]:
  for oy in [-size,0,size]:tile.alpha_composite(cut,(x+ox,y+oy))
for season in range(23):
 source=Image.open(R/f'tree_source/season{season:02}_normals/fg_bush.png').convert('RGBA')
 leaf_source=Image.open(R/f'tree_source/season{season:02}_normals/treeA2.png').convert('RGBA')
 # Donor foliage materials double the atlas alpha before coverage testing.
 source.putalpha(source.getchannel('A').point(lambda a:min(255,a*2)))
 leaf_source.putalpha(leaf_source.getchannel('A').point(lambda a:min(255,a*2)))
 # Preserve donor cutouts. Physical sidewalls belong to geometry, not alpha fill.
 tile=Image.new('RGBA',(size,size),(0,0,0,0))
 rng=random.Random(7301)
 # Same placement in every season prevents patterns jumping when dates change.
 for layer in range(2):
  for gy in range(7):
   for gx in range(7):
    # Preserve every original donor texel: lossless quarter turns only.
    cut=leaf_source.crop(rng.choice(leaves))
    cut=cut.rotate(90*rng.randrange(4),expand=True)
    if rng.randrange(2):cut=cut.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
    x=round(gx*size/7)+2*rng.randint(-8,8)-cut.width//2;y=round(gy*size/7)+2*rng.randint(-8,8)-cut.height//2
    stamp_wrap(tile,cut,x,y)
 for k in range(12):
  # Clover accents stay at their source size instead of a blurred2x enlargement.
  cut=source.crop(clovers[k%2]).rotate(90*rng.randrange(4),expand=True)
  stamp_wrap(tile,cut,rng.randrange(size)-cut.width//2,rng.randrange(size)-cut.height//2)
 # Seasonal treeA2 cutouts already contain the original winter snow.
 # Do not enlarge and wrap a second shrub cap over those individual leaves.
 tile.save(O/f'mound_season{season:02}.png');images.append(tile)
 # Only physical sidewalls have a backing layer: an actual dark donor leaf
 # texel from this season. Top cutouts and their stored RGB remain unchanged.
 pixels=[p for box in leaves for p in leaf_source.crop(box).getdata() if p[3]>240]
 pixels.sort(key=lambda p:sum(p[:3]));backing=pixels[len(pixels)//6]
 wall=Image.new('RGBA',(size,size),(*backing[:3],255));wall.alpha_composite(tile)
 # Outer banks retain leaf cutouts; the recessed inner shell uses the filled
 # RGB with opaque coverage, selected by its geometry UV sentinel.
 wall.putalpha(tile.getchannel('A'))
 wall.save(O/f'wall_season{season:02}.png')
 wall_raw=wall.tobytes()
 if wall_raw in wall_seen:wall_names.append(wall_seen[wall_raw])
 else:
  wall_name=f'pc_foliage_wall_{season:02}';wall_seen[wall_raw]=wall_name;wall_names.append(wall_name)
  out+=[f'static const unsigned char {wall_name}[256*256*4] = {{']+[','.join(map(str,wall_raw[i:i+32]))+','for i in range(0,len(wall_raw),32)]+['};']
 raw=tile.tobytes()
 if raw in seen:names.append(seen[raw]);continue
 name=f'pc_foliage_{season:02}';seen[raw]=name;names.append(name)
 out+=[f'static const unsigned char {name}[256*256*4] = {{']+[','.join(map(str,raw[i:i+32]))+','for i in range(0,len(raw),32)]+['};']
out+=['static const unsigned char* const pc_foliage_seasons[23] = {'+','.join(names)+'};', 'static const unsigned char* const pc_foliage_wall_seasons[23] = {'+','.join(wall_names)+'};']
(R/'ACGC-PC-Port/pc/src/pc_foliage_data.c_inc').write_text('\n'.join(out)+'\n')
preview=Image.new('RGBA',(1024,512))
for j,season in enumerate([8,14,18,0]):
 im=images[season]
 for y in range(2):preview.paste(im,(j*256,y*256))
preview.save(O/'season-preview.png')
(O/'provenance.json').write_text(json.dumps({'source':'/Fg/Bcres/Season00..22.bcres treeA2 canopy leaves with their original seasonal snow + fg_bush clover accents','leaf_rects':leaves,'clover_rects':clovers,'clover_model':'fg_grassE UV U0.500106..0.93655 V0.874123..0.995468','snow_handling':'Use snow already present in seasonal treeA2 cutouts; no additional enlarged shrub snow cap.','seasonal_adapter':'Dominant leaf artwork follows actual plain-hardwood treeA2 atlas, including blossoms; donor shrubs did not necessarily share these colors.', 'method':'256-pixel tile assembled from native-size donor crops with lossless quarter-turn rotation and mirroring, no resize or arbitrary-angle filtering. Native-size clover accents. Deterministic wraparound placement of original cutouts; source colors retained. Transparent cutout tile; multiply by unmodified native silhouette alpha. Sample donor tile in continuous XZ projection, not the discontinuous native fan UV chart.','wall_backing':'Original cutout alpha on rounded outer banks; donor leaf backing RGB for recessed opaque inner shell.', 'size':[256,256]},indent=2))
print('Generated 23 seasonal 256x256 foliage tiles;'.replace('23',' 23 ').replace('seasonal128','seasonal 128'))
