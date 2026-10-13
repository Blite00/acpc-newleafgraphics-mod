"""Install a reversible, exact-palette apple replacement from local assets."""
import hashlib, json, struct
from pathlib import Path
from PIL import Image

ROOT=Path(__file__).resolve().parent
MASK=(1<<64)-1
P1,P2,P3,P4,P5=0x9e3779b185ebca87,0xc2b2ae3d27d4eb4f,0x165667b19e3779f9,0x85ebca77c2b2ae63,0x27d4eb2f165667c5
def rot(v,n): return ((v<<n)|(v>>(64-n)))&MASK
def rnd(a,v): return rot((a+v*P2)&MASK,31)*P1&MASK
def xxh(b):
    n=len(b); pos=0
    if n>=32:
        vs=[(P1+P2)&MASK,P2,0,(-P1)&MASK]
        while pos<=n-32:
            vs=[rnd(a,v) for a,v in zip(vs,struct.unpack_from('<4Q',b,pos))]; pos+=32
        h=sum(rot(v,r) for v,r in zip(vs,[1,7,12,18]))&MASK
        for v in vs: h=((h^rnd(0,v))*P1+P4)&MASK
    else: h=P5
    h=(h+n)&MASK
    while pos+8<=n:
        h=(rot(h^rnd(0,int.from_bytes(b[pos:pos+8],'little')),27)*P1+P4)&MASK; pos+=8
    if pos+4<=n:
        h=(rot(h^((int.from_bytes(b[pos:pos+4],'little')*P1)&MASK),23)*P2+P3)&MASK; pos+=4
    while pos<n:
        h=(rot(h^((b[pos]*P5)&MASK),11)*P1)&MASK; pos+=1
    h^=h>>33; h=h*P2&MASK; h^=h>>29; h=h*P3&MASK; h^=h>>32
    return f'{h:016x}'

def dds_rgba(im):
    w,h=im.size
    header=bytearray(128); header[:4]=b'DDS '
    struct.pack_into('<7I',header,4,124,0x100f,h,w,w*4,0,1)
    struct.pack_into('<8I',header,76,32,0x41,0,32,0xff,0xff00,0xff0000,0xff000000)
    struct.pack_into('<I',header,108,0x1000)
    return bytes(header)+im.convert('RGBA').tobytes()

def main():
    assert xxh(b'')=='ef46db3751d8e999'
    assert xxh(bytes(range(32)))=='cbf59c5116ff32b4'
    rel=(ROOT/'foresta.rel').read_bytes()
    im=Image.open(ROOT/'icons/icn_301.png').convert('RGBA')
    payload=dds_rgba(im)
    out=ROOT.parent/'texture_pack'/'3ds_apple_trial'; out.mkdir(exist_ok=True)
    records=[]
    for label,t,p in [('dropped_apple',0x66ab40,0x66ab20),('inventory_apple',0x731a80,0x731a00)]:
        tex=rel[t:t+512]; pal=rel[p:p+32]
        indices=[n for v in tex for n in (v>>4,v&15)]
        ph=xxh(pal[min(indices)*2:(max(indices)+1)*2])
        name=f'tex1_32x32_{xxh(tex)}_{ph}_8.dds'
        dest=out/name
        if dest.exists() and dest.read_bytes()!=payload: raise RuntimeError(f'Refusing to overwrite {dest}')
        dest.write_bytes(payload)
        check=Image.open(dest).convert('RGBA')
        assert check.size==im.size and check.tobytes()==im.tobytes()
        records.append({'use':label,'file':str(dest),'texture_offset':hex(t),'palette_offset':hex(p),'sha256':hashlib.sha256(payload).hexdigest()})
    manifest={'source_image':'player ROM',
              'source_archive':'/Layout/ItemWin/item_icon_tex.arc','source_asset':'icn_301.bclim',
              'dimensions':[32,32],'status':'DDS decoded and verified; live item appearance not yet checked','files':records}
    (ROOT/'apple_trial_manifest.json').write_text(json.dumps(manifest,indent=2))
    print(json.dumps(manifest,indent=2))

if __name__=='__main__': main()
