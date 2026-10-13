import struct
from PIL import Image
from unpack import pix
FM={7:0,8:1,9:2,5:3,11:13,10:12,0:9,1:6,4:8}
def load(fn):
    b=open(f'nlui/Font/{fn}.bcfnt','rb').read()
    o=struct.unpack_from('<H',b,6)[0]+8
    typ,lf,alt=struct.unpack_from('<BBH',b,o); dl,dg,dc,enc,pt,pw,pm,H,W,asc=struct.unpack_from('<bBBBIIIBBB',b,o+4)
    cw,ch,base,maxw,ssz,ns,fmt,cols,rows,sw,sh,doff=struct.unpack_from('<BBbBIHHHHHHI',b,pt)
    sheets=[]
    for s in range(ns):
        d=b[doff+s*ssz:doff+(s+1)*ssz]
        im=Image.new('RGBA',(sw,sh));px=im.load();i=0
        for ty in range(0,sh,8):
            for tx in range(0,sw,8):
                for k in range(64):
                    x=y=0
                    for q in range(3): x|=((k>>(2*q))&1)<<q; y|=((k>>(2*q+1))&1)<<q
                    px[tx+x,ty+y]=pix(FM.get(fmt,fmt),d,i);i+=1
        sheets.append(im)
    # widths
    widths={}
    p=pw
    while p:
        st,en,nx=struct.unpack_from('<HHI',b,p)
        for i in range(en-st+1): widths[st+i]=struct.unpack_from('<bBB',b,p+8+3*i)
        p=nx
    cmap={}
    p=pm
    while p:
        cs,ce,mt,_,nx=struct.unpack_from('<HHHHI',b,p)
        if mt==0:
            off=struct.unpack_from('<H',b,p+12)[0]
            for c in range(cs,ce+1): cmap[c]=off+c-cs
        elif mt==1:
            for c in range(cs,ce+1):
                g=struct.unpack_from('<H',b,p+12+2*(c-cs))[0]
                if g!=0xffff: cmap[c]=g
        else:
            n=struct.unpack_from('<H',b,p+12)[0]
            for i in range(n):
                c,g=struct.unpack_from('<HH',b,p+14+4*i); cmap[c]=g
        p=nx
    return dict(sheets=sheets,cw=cw,ch=ch,cols=cols,rows=rows,widths=widths,cmap=cmap,lf=lf,asc=asc,fmt=fmt,ns=ns,sw=sw,sh=sh)
def glyph(F,c):
    g=F['cmap'].get(ord(c));
    if g is None: return None,(0,0,F['cw']//2)
    per=F['cols']*F['rows']; s=F['sheets'][g//per]; r=g%per
    x=(r%F['cols'])*(F['cw']+1); y=(r//F['cols'])*(F['ch']+1)
    return s.crop((x+1,y+1,x+1+F['cw'],y+1+F['ch'])), F['widths'].get(g,(0,F['cw'],F['cw']))
def render(F,text,color,scale=1):
    w=sum(glyph(F,c)[1][2] for c in text)+4
    im=Image.new('RGBA',(w,F['lf']+4));x=2
    for c in text:
        gi,(l,gw,adv)=glyph(F,c)
        if gi:
            a=gi.split()[3] if F['fmt'] in (8,11) else gi.convert('L')
            col=Image.new('RGBA',gi.size,color); col.putalpha(a)
            im.alpha_composite(col,(x+l,2))
        x+=adv
    return im.resize((im.width*scale,im.height*scale),Image.LANCZOS) if scale!=1 else im
if __name__=='__main__':
    F=load('Garden_msg_size16'); print(F['fmt'],{k:v for k,v in F.items() if k not in('sheets','widths','cmap')}, len(F['cmap']))
    F['sheets'][0].save('font_sheet0.png')
    render(F,'Hi, Blite! Welcome to New Leaf, rawr!',(70,50,30,255),2).save('font_test.png')
