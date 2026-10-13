"""Decode native GameCube display lists + textures straight from foresta.rel.

Gives, per display list, textured triangles (texture symbol, 3 x (x,y,z,u,v)) with UV
in texels, and decodes CI4/CI8 textures with the structure palettes.
Used by the texture-baking tools (houses, shops, ...).
"""
import re, struct
from pathlib import Path
from PIL import Image

ROOT = Path(__file__).resolve().parent
rel = (ROOT/'foresta.rel').read_bytes()
DATA = 0x2dd340
sym = {}
sym_first = {}   # some names exist twice in foresta.rel (e.g. bug textures); the first copy is the field actor's
for _l in open(ROOT/'ACGC-PC-Port/config/GAFE01_00/foresta/symbols.txt'):
    _m = re.match(r'(\w+) = \.data:0x([0-9A-F]+); // type:object size:0x([0-9A-F]+)', _l)
    if _m:
        sym[_m[1]] = (int(_m[2], 16), int(_m[3], 16))
        sym_first.setdefault(_m[1], sym[_m[1]])

def blob(name):
    a, s = sym[name]; return rel[DATA+a:DATA+a+s]

def blob_first(name):
    a, s = sym_first[name]; return rel[DATA+a:DATA+a+s]

def palette_first(name):
    b = blob_first(name); return [rgb5a3(struct.unpack_from('>H', b, i*2)[0]) for i in range(len(b)//2)]

def vertices(name):
    b = blob(name)
    return [struct.unpack_from('>hhhHhhBBBB', b, i*16) for i in range(len(b)//16)]

def rgb5a3(v):
    if v & 0x8000: return ((v >> 10 & 31)*255//31, (v >> 5 & 31)*255//31, (v & 31)*255//31, 255)
    return ((v >> 8 & 15)*17, (v >> 4 & 15)*17, (v & 15)*17, (v >> 12 & 7)*255//7)

def palette(name):
    b = blob(name); return [rgb5a3(struct.unpack_from('>H', b, i*2)[0]) for i in range(len(b)//2)]

def decode_ci(data, w, h, pal, bits):
    im = Image.new('RGBA', (w, h)); px = im.load(); o = 0
    bw, bh = (8, 8) if bits == 4 else (8, 4)
    for ty in range(0, h, bh):
        for tx in range(0, w, bw):
            for y in range(bh):
                if bits == 4:
                    for x in range(0, 8, 2):
                        b = data[o]; o += 1
                        for k, i in enumerate((b >> 4, b & 15)):
                            if tx+x+k < w and ty+y < h: px[tx+x+k, ty+y] = pal[i] if i < len(pal) else (255, 0, 255, 255)
                else:
                    for x in range(8):
                        i = data[o]; o += 1
                        if tx+x < w and ty+y < h: px[tx+x, ty+y] = pal[i] if i < len(pal) else (255, 0, 255, 255)
    return im

def ci_indices(data, bits):
    return [n for v in data for n in (v >> 4, v & 15)] if bits == 4 else list(data)

_TOK = re.compile(r'(gs\w+)\(([^)]*)\)')
def parse_model_file(path):
    """{dl_name: [ (texture_symbol, fmt, bits, w, h, [(x,y,z,u,v)*3]) ]}"""
    src = Path(path).read_text()
    out = {}
    for m in re.finditer(r'\bGfx\s+(\w+)\[\]\s*=\s*\{(.*?)\n\};', src, re.S):
        name, body = m.group(1), m.group(2)
        tex = None; buf = {}; tris = []; pending = 0
        def emit(a, b, c):
            if tex is None: return
            try: tri = [buf[i] for i in (a, b, c)]
            except KeyError: return
            tris.append((tex[4], tex[0], tex[1], tex[2], tex[3], tri))
        for op, args in _TOK.findall(body):
            args = [a.strip() for a in args.split(',')]
            if op == 'gsDPSetTextureImage_Dolphin':
                fmt = args[0].replace('G_IM_FMT_', ''); bits = int(args[1].replace('G_IM_SIZ_', '').rstrip('b'))
                tex = (fmt, bits, int(args[2]), int(args[3]), args[4])
            elif op == 'gsSPVertex':
                a = re.match(r'&?(\w+)(?:\[(\d+)\])?', args[0]); arr, st = a.group(1), int(a.group(2) or 0)
                n, v0 = int(args[1]), int(args[2])
                vs = vertices(arr)
                for k in range(n):
                    x, y, z, _f, u, v = vs[st+k][:6]
                    buf[v0+k] = (x, y, z, u/32.0, v/32.0)
            elif op == 'gsSP1Triangle':
                emit(*map(int, args[:3]))
            elif op == 'gsSP2Triangles':
                emit(*map(int, args[:3])); emit(*map(int, args[4:7]))
            elif op == 'gsSPNTrianglesInit_5b':
                pending = int(args[0]); idx = list(map(int, args[1:10]))
                for k in range(0, 9, 3):
                    if pending > 0: emit(*idx[k:k+3]); pending -= 1
            elif op == 'gsSPNTriangles_5b':
                idx = list(map(int, args[:12]))
                for k in range(0, 12, 3):
                    if pending > 0: emit(*idx[k:k+3]); pending -= 1
        out[name] = tris
    return out
