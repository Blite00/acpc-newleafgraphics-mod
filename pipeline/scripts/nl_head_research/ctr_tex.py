"""Independent 3DS (PICA) texture decoder for CGFX/BCRES TXOB entries (ETC1, ETC1A4, LA4, LA8, L8, A8, RGBA)."""
import struct, re
import numpy as np
LUT=[[2,8,-2,-8],[5,17,-5,-17],[9,29,-9,-29],[13,42,-13,-42],[18,60,-18,-60],[24,80,-24,-80],[33,106,-33,-106],[47,183,-47,-183]]
def ext(v,b): return (v<<(8-b))|(v>>(2*b-8))
def etc1_block(c):
    hi=c>>32; lo=c&0xffffffff
    diff=(hi>>1)&1; flip=hi&1; t1=(hi>>5)&7; t2=(hi>>2)&7
    if diff:
        r,g,b=(hi>>27)&31,(hi>>19)&31,(hi>>11)&31
        d=[((hi>>s)&7) for s in (24,16,8)]; d=[x-8 if x>3 else x for x in d]
        c1=[ext(x,5) for x in (r,g,b)]; c2=[ext(x,5) for x in (r+d[0],g+d[1],b+d[2])]
    else:
        c1=[ext((hi>>s)&15,4) for s in (28,20,12)]; c2=[ext((hi>>s)&15,4) for s in (24,16,8)]
    out=np.zeros((4,4,3),int)
    for x in range(4):
        for y in range(4):
            px=x*4+y
            sub=(y>=2) if flip else (x>=2)
            base=c2 if sub else c1; t=t2 if sub else t1
            idx=(((lo>>(16+px))&1)<<1)|((lo>>px)&1)
            out[y,x]=np.clip(np.array(base)+LUT[t][idx],0,255)
    return out
def zorder8():
    o=[]
    for i in range(64):
        x=(i&1)|((i>>1)&2)|((i>>2)&4); y=((i>>1)&1)|((i>>2)&2)|((i>>3)&4); o.append((x,y))
    return o
Z=zorder8()
def decode(raw,w,h,fmt):
    img=np.zeros((h,w,4),int); img[...,3]=255
    if fmt in (12,13):
        bs=16 if fmt==13 else 8; bi=0
        for ty in range(0,h,8):
            for tx in range(0,w,8):
                for by,bx in ((0,0),(0,4),(4,0),(4,4)):
                    o=bi*bs; bi+=1
                    if fmt==13:
                        a=struct.unpack_from('<Q',raw,o)[0]; c=struct.unpack_from('<Q',raw,o+8)[0]
                    else:
                        a=None; c=struct.unpack_from('<Q',raw,o)[0]
                    blk=etc1_block(c)
                    img[ty+by:ty+by+4,tx+bx:tx+bx+4,:3]=blk
                    if a is not None:
                        for x in range(4):
                            for y in range(4):
                                img[ty+by+y,tx+bx+x,3]=((a>>(4*(x*4+y)))&15)*17
        return img   # same row order as the Ohana PNGs (importer maps v -> 1-v)
    i=0
    for ty in range(0,h,8):
        for tx in range(0,w,8):
            for x,y in Z:
                if fmt==9:   # LA4: high nibble L, low nibble A
                    v=raw[i]; i+=1; L=(v>>4)*17; A=(v&15)*17; img[ty+y,tx+x]=[L,L,L,A]
                elif fmt==5: # LA8: byte0 A, byte1 L
                    A,L=raw[i],raw[i+1]; i+=2; img[ty+y,tx+x]=[L,L,L,A]
                elif fmt==7: v=raw[i]; i+=1; img[ty+y,tx+x]=[v,v,v,255]
                elif fmt==8: v=raw[i]; i+=1; img[ty+y,tx+x]=[0,0,0,v]
                elif fmt==0: a,b,g,r=raw[i:i+4]; i+=4; img[ty+y,tx+x]=[r,g,b,a]
                elif fmt==11:
                    v=raw[i//2]; v=(v>>4) if i&1 else (v&15); i+=1; img[ty+y,tx+x]=[0,0,0,v*17]
                elif fmt==10:
                    v=raw[i//2]; v=(v>>4) if i&1 else (v&15); i+=1; img[ty+y,tx+x]=[v*17]*3+[255]
                else: raise ValueError(fmt)
    return img
def textures(path):
    d=open(path,'rb').read(); res={}
    for m in re.finditer(b'TXOB',d):
        o=m.start()-4
        nameoff=o+12+struct.unpack_from('<I',d,o+12)[0]
        name=d[nameoff:d.index(b'\0',nameoff)].decode()
        if not name: continue
        h,w=struct.unpack_from('<2I',d,o+24); fmt=struct.unpack_from('<I',d,o+52)[0]
        ln=struct.unpack_from('<I',d,o+68)[0]; off=o+72+struct.unpack_from('<I',d,o+72)[0]
        res[name]=(fmt,decode(d[off:off+ln],w,h,fmt))
    return res
