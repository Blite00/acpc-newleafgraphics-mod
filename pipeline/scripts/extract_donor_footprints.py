"""Decode original SPBD footprint textures, with source-verified PICA format9."""
from pathlib import Path
from PIL import Image,ImageDraw
import struct,json
R=Path(__file__).resolve().parent;O=R/'terrain_source/footprints';O.mkdir(parents=True,exist_ok=True)
with Path(__import__('os').environ['ACPC_NL_ROM']).open('rb') as f:_e=next(e for e in json.loads((R/'3ds_inventory.json').read_text()) if e['path']=='/Particle/seadPtcl.ptcl');f.seek(_e['offset']);b=f.read(_e['size'])
texture_base=struct.unpack_from('<I',b,0x14)[0];records=[]
for name,emitter,aliases in [('human_left',0x30c88,['cg_footmrk_h00_l','cg_footmrk_h_l']),('human_right',0x30e7c,['cg_footmrk_h00_r','cg_footmrk_h_r']),('shoe',0x31840,['cg_footmrk_s','cg_footmrk_s00'])]:
 w,h,fmt=struct.unpack_from('<HHI',b,emitter+0x14);size,offset=struct.unpack_from('<II',b,emitter+0x20)
 assert (w,h,fmt,size)==(8,8,9,64)
 data=b[texture_base+offset:texture_base+offset+size];im=Image.new('RGBA',(w,h))
 for y in range(h):
  for x in range(w):
   morton=sum((((x>>k)&1)<<(2*k))|(((y>>k)&1)<<(2*k+1)) for k in range(3));v=data[morton]
   # PICA LA4: upper nibble luminance, lower nibble alpha. PNG flips V.
   l=(v>>4)*17;a=(v&15)*17;im.putpixel((x,h-1-y),(l,l,l,a))
 im.save(O/(name+'.png'))
 preview=Image.new('RGB',(512,256),(185,174,146));draw=ImageDraw.Draw(preview)
 for y in range(0,256,32):
  for x in range(0,256,32):
   if (x//32+y//32)%2:draw.rectangle((x,y,x+31,y+31),fill=(210,198,166))
 preview.paste(im.resize((256,256),Image.Resampling.NEAREST),(0,0),im.getchannel('A').resize((256,256),Image.Resampling.NEAREST))
 preview.paste(im.getchannel('A').resize((256,256),Image.Resampling.NEAREST).convert('RGB'),(256,0));preview.save(O/(name+'-alpha-preview.png'))
 records.append({'name':name,'emitters':aliases,'emitterOffset':hex(emitter),'textureBase':hex(texture_base),'dataOffset':hex(offset),'width':w,'height':h,'format':'PICA9 LA4','maxAlpha':max(im.getchannel('A').getdata()),'sourceFloatRGB_at_D8':struct.unpack_from('<3f',b,emitter+0xd8),'sourceFloatXY_at_108':struct.unpack_from('<2f',b,emitter+0x108),'parameterRoles':'Color and half-size candidates only; draw binding not yet traced.'})
(O/'texture_decode_audit.json').write_text(json.dumps({'assets':records,'runtimeProof':['5B91AC..B4: textureBase=file+header14','5B92C0..D8: image=textureBase+emitter24,descriptor=emitter14','5B8F2C/30 and5B8F5C/64: raw width/height copied','5B8F20..6C: descriptorformat copied textureobject8','5B7B80..8C: textureobject8 written to PICA TEX0_TYPE register008E'],'interpretation':'Original shoe is an8x8 translucent embossed oval impression: luminance encodes a directional shading ramp, alpha encodes a shallow rim. No outsole silhouette or recoloring has been fabricated.'},indent=2))
print('Extracted three original8x8 LA4 footprint textures.')
