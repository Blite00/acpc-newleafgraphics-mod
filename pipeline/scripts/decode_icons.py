"""Decode the local 3DS inventory icons; no game files are modified.

Format references: gdkchan/Ohana3DS-Rebirth BCLIM.cs and TextureCodec.cs.
"""
import json
import struct
from pathlib import Path
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent
MODIFIERS = [(2,8,-2,-8),(5,17,-5,-17),(9,29,-9,-29),(13,42,-13,-42),
             (18,60,-18,-60),(24,80,-24,-80),(33,106,-33,-106),(47,183,-47,-183)]

def decode_etc(data, width, height, alpha=True):
    image = Image.new('RGBA', (width, height))
    pos = 0
    for ty in range(0, height, 8):
        for tx in range(0, width, 8):
            for by, bx in [(0,0),(0,4),(4,0),(4,4)]:
                a = int.from_bytes(data[pos:pos+8], 'little') if alpha else (1<<64)-1
                pos += 8 if alpha else 0
                v = int.from_bytes(data[pos:pos+8], 'little'); pos += 8
                hi, lo = v >> 32, v & 0xffffffff
                flip, diff = hi & 1, hi & 2
                c1, c2 = [], []
                for shift in [24,16,8]:
                    c = (hi >> shift) & 255
                    if diff:
                        base, delta = c >> 3, c & 7
                        if delta >= 4: delta -= 8
                        other = base + delta
                        c1.append((base << 3) | (base >> 2))
                        c2.append((other << 3) | (other >> 2))
                    else:
                        c1.append((c >> 4)*17); c2.append((c & 15)*17)
                tables = [(hi >> 5)&7, (hi >> 2)&7]
                for y in range(4):
                    for x in range(4):
                        k=x*4+y; side = int((y if flip else x)>=2)
                        mod=MODIFIERS[tables[side]][((lo>>k)&1) | (((lo>>(k+16))&1)<<1)]
                        rgb=tuple(max(0,min(255,c+mod)) for c in [c1,c2][side])
                        image.putpixel((tx+bx+x,ty+by+y),rgb+(((a>>(4*k))&15)*17,))
    return image

def main():
    archive=(ROOT/'item_icon_tex.arc').read_bytes()
    entries=json.loads((ROOT/'icon_inventory.json').read_text())
    out=ROOT/'icons'; out.mkdir(exist_ok=True)
    sheet=Image.new('RGB',(16*80,((len(entries)+15)//16)*90),'#ddd9cf')
    draw=ImageDraw.Draw(sheet)
    for i,(name,off,size) in enumerate(entries):
        b=archive[off:off+size]
        assert b[-40:-36]==b'CLIM'
        w,h,fmt,length=struct.unpack_from('<HHII',b,len(b)-12)
        assert (w,h,fmt)==(32,32,11)
        im=decode_etc(b[:length],w,h)
        im.save(out/(Path(name).stem+'.png'))
        large=im.resize((64,64),Image.Resampling.NEAREST)
        x,y=(i%16)*80,(i//16)*90
        sheet.paste(large,(x+8,y),large); draw.text((x+6,y+66),Path(name).stem,fill='black')
    sheet.save(ROOT/'icon_contact_sheet.png')
    print('Decoded',len(entries),'icons')

if __name__=='__main__': main()
