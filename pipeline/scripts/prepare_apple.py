"""Extract the original apple for comparison and identify its replacement key."""
from pathlib import Path
import struct, json, hashlib
from PIL import Image, ImageDraw

ROOT=Path(__file__).resolve().parent
GAME=ROOT.parent

def yaz0(b):
    if b[:4]!=b'Yaz0': return b
    size=struct.unpack_from('>I',b,4)[0]; out=bytearray(); pos=16
    while len(out)<size:
        mask=b[pos]; pos+=1
        for bit in range(7,-1,-1):
            if len(out)>=size: break
            if mask & (1<<bit): out.append(b[pos]); pos+=1
            else:
                v=int.from_bytes(b[pos:pos+2],'big'); pos+=2
                count=v>>12; dist=(v&4095)+1
                if count==0: count=b[pos]+18; pos+=1
                else: count+=2
                assert dist<=len(out) and len(out)+count<=size
                for _ in range(count): out.append(out[-dist])
    return bytes(out)

def gc_ci4(data,palette,w=32,h=32):
    colors=[]
    for v in struct.unpack('>16H',palette):
        if v&0x8000:
            rgb=[(v>>shift)&31 for shift in (10,5,0)]
            colors.append(tuple((c<<3)|(c>>2) for c in rgb)+(255,))
        else: colors.append(tuple(((v>>shift)&15)*17 for shift in (8,4,0))+((((v>>12)&7)*255//7),))
    im=Image.new('RGBA',(w,h)); n=0
    for ty in range(0,h,8):
        for tx in range(0,w,8):
            for y in range(8):
                for x in range(8):
                    ix=(data[n//2]>>(4 if n%2==0 else 0))&15; n+=1
                    im.putpixel((tx+x,ty+y),colors[ix])
    return im

def main():
    rel=(ROOT/'foresta.rel').read_bytes()   # extracted by the setup from the player's disc
    tex=rel[0x66ab40:0x66ad40]; pal=rel[0x66ab20:0x66ab40]
    (ROOT/'original_apple_texture.bin').write_bytes(tex)
    (ROOT/'original_apple_palette.bin').write_bytes(pal)
    im=gc_ci4(tex,pal); im.save(ROOT/'original_apple.png')
    new=Image.open(ROOT/'icons/icn_301.png').convert('RGBA')
    canvas=Image.new('RGB',(600,350),'#ddd9cf'); draw=ImageDraw.Draw(canvas)
    draw.text((30,20),'Original GameCube apple',fill='black')
    draw.text((330,20),'Extracted 3DS apple',fill='black')
    for x,img in [(30,im),(330,new)]:
        img=img.resize((240,240),Image.Resampling.NEAREST); canvas.paste(img,(x,60),img)
    draw.text((30,320),'Both source textures are 32 x 32 pixels.',fill='black')
    canvas.save(ROOT/'apple_comparison.png')
    print('REL extracted:',len(rel),'bytes; apple previews prepared')

if __name__=='__main__': main()
