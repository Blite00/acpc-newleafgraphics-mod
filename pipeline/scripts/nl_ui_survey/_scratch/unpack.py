import os as _os
_ROOT = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
if _os.path.basename(_ROOT) == 'nl_ui_survey': _ROOT = _os.path.dirname(_ROOT)
os = _os

import struct,os,sys,glob
from PIL import Image
sys.path.insert(0,_ROOT)
from decode_icons import MODIFIERS
def darc(b):
    tbl,tlen,doff=struct.unpack_from('<III',b,0x10)
    n=struct.unpack_from('<III',b,tbl)[2]
    names=tbl+n*12
    out=[];stack=[]
    path=[]; ends=[]
    for i in range(n):
        no,o,s=struct.unpack_from('<III',b,tbl+i*12)
        isdir=no>>24; no&=0xffffff
        j=names+no; nm=b''
        while b[j:j+2]!=b'\0\0': nm+=b[j:j+2]; j+=2
        nm=nm.decode('utf-16le')
        while ends and i>=ends[-1]: ends.pop(); path.pop()
        if isdir:
            path.append(nm); ends.append(s)
        else: out.append(('/'.join(p for p in path+[nm] if p and p!='.'),b[o:o+s]))
    return out
def morton(x,y):
    r=0
    for i in range(3): r|=((x>>i)&1)<<(2*i) | ((y>>i)&1)<<(2*i+1)
    return r
def etc(data,w,h,alpha):
    im=Image.new('RGBA',(w,h));px=im.load();pos=0
    for ty in range(0,h,8):
        for tx in range(0,w,8):
            for by,bx in [(0,0),(0,4),(4,0),(4,4)]:
                a=int.from_bytes(data[pos:pos+8],'little') if alpha else (1<<64)-1
                pos+=8 if alpha else 0
                v=int.from_bytes(data[pos:pos+8],'little');pos+=8
                hi,lo=v>>32,v&0xffffffff;flip,diff=hi&1,hi&2;c1,c2=[],[]
                for sh in [24,16,8]:
                    c=(hi>>sh)&255
                    if diff:
                        base,d=c>>3,c&7
                        if d>=4:d-=8
                        ot=base+d;c1.append((base<<3)|(base>>2));c2.append(((ot&31)<<3)|((ot&31)>>2))
                    else: c1.append((c>>4)*17);c2.append((c&15)*17)
                tb=[(hi>>5)&7,(hi>>2)&7]
                for y in range(4):
                    for x in range(4):
                        k=x*4+y;side=int((y if flip else x)>=2)
                        m=MODIFIERS[tb[side]][((lo>>k)&1)|(((lo>>(k+16))&1)<<1)]
                        X,Y=tx+bx+x,ty+by+y
                        if X<w and Y<h: px[X,Y]=tuple(max(0,min(255,c+m)) for c in [c1,c2][side])+(((a>>(4*k))&15)*17,)
    return im
BPP={0:8,1:8,2:8,3:16,4:16,5:16,6:24,7:16,8:16,9:32,12:4,13:4}
def pix(fmt,d,i):
    if fmt==0: return (d[i],)*3+(255,)
    if fmt==1: return (255,255,255,d[i])
    if fmt==2: v=d[i]; return ((v>>4)*17,)*3+((v&15)*17,)
    if fmt==3: return (d[2*i+1],)*3+(d[2*i],)
    if fmt==4: return (d[2*i+1],d[2*i],0,255)
    if fmt==5:
        v=d[2*i]|d[2*i+1]<<8; return (((v>>11)&31)*255//31,((v>>5)&63)*255//63,(v&31)*255//31,255)
    if fmt==6: return (d[3*i+2],d[3*i+1],d[3*i],255)
    if fmt==7:
        v=d[2*i]|d[2*i+1]<<8; return (((v>>11)&31)*255//31,((v>>6)&31)*255//31,((v>>1)&31)*255//31,255*(v&1))
    if fmt==8:
        v=d[2*i]|d[2*i+1]<<8; return ((v>>12)*17,((v>>8)&15)*17,((v>>4)&15)*17,(v&15)*17)
    if fmt==9: return (d[4*i+3],d[4*i+2],d[4*i+1],d[4*i])
    if fmt==12: v=(d[i//2]>>(4*(i&1)))&15; return (v*17,)*3+(255,)
    if fmt==13: v=(d[i//2]>>(4*(i&1)))&15; return (255,255,255,v*17)
def clim(b):
    w,h,fmt=struct.unpack_from('<HHI',b,len(b)-12)
    # pad to pow2 tile dims
    W=max(8,1<<(w-1).bit_length()); H=max(8,1<<(h-1).bit_length())
    if fmt in(10,11): im=etc(b,W,H,fmt==11)
    else:
        im=Image.new('RGBA',(W,H));px=im.load();i=0
        for ty in range(0,H,8):
            for tx in range(0,W,8):
                for k in range(64):
                    x=y=0
                    for s in range(3): x|=((k>>(2*s))&1)<<s; y|=((k>>(2*s+1))&1)<<s
                    px[tx+x,ty+y]=pix(fmt,b,i); i+=1
    return im.crop((0,0,w,h)),fmt,(w,h)
if __name__=='__main__':
    import json
    rep=[]
    for arc in sorted(glob.glob('nlui/Layout/**/*.arc',recursive=True)):
        b=open(arc,'rb').read()
        if b[:4]!=b'darc': rep.append((arc,'notdarc',b[:4].hex()));continue
        base='out/'+arc[len('nlui/Layout/'):-4]
        for name,data in darc(b):
            p=base+'/'+name; os.makedirs(os.path.dirname(p),exist_ok=True)
            if name.endswith('.bclim'):
                try:
                    im,fmt,sz=clim(data); im.save(p[:-6]+'.png'); rep.append((arc,name,fmt,sz))
                except Exception as e: rep.append((arc,name,'ERR',str(e)))
            else:
                open(p,'wb').write(data); rep.append((arc,name,len(data)))
    json.dump(rep,open('report.json','w'),indent=0)
    print(len(rep))
