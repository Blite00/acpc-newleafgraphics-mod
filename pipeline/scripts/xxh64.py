"""Pure-python XXH64 (seed 0), same as pc_texture_pack.c, and the texture-pack name for CI textures."""
M = (1 << 64)-1
P1, P2, P3, P4, P5 = 0x9E3779B185EBCA87, 0xC2B2AE3D27D4EB4F, 0x165667B19E3779F9, 0x85EBCA77C2B2AE63, 0x27D4EB2F165667C5
rotl = lambda x, r: ((x << r) | (x >> (64-r))) & M
def _round(acc, inp): return rotl((acc+inp*P2) & M, 31)*P1 & M
def _merge(acc, val): return ((acc ^ _round(0, val))*P1+P4) & M
def xxh64(b):
    n = len(b); p = 0
    if n >= 32:
        v1, v2, v3, v4 = (P1+P2) & M, P2, 0, (-P1) & M
        while p <= n-32:
            v1 = _round(v1, int.from_bytes(b[p:p+8], 'little')); v2 = _round(v2, int.from_bytes(b[p+8:p+16], 'little'))
            v3 = _round(v3, int.from_bytes(b[p+16:p+24], 'little')); v4 = _round(v4, int.from_bytes(b[p+24:p+32], 'little')); p += 32
        h = (rotl(v1, 1)+rotl(v2, 7)+rotl(v3, 12)+rotl(v4, 18)) & M
        for v in (v1, v2, v3, v4): h = _merge(h, v)
    else: h = P5
    h = (h+n) & M
    while p+8 <= n:
        h ^= _round(0, int.from_bytes(b[p:p+8], 'little')); h = (rotl(h, 27)*P1+P4) & M; p += 8
    if p+4 <= n:
        h ^= int.from_bytes(b[p:p+4], 'little')*P1 & M; h = (rotl(h, 23)*P2+P3) & M; p += 4
    while p < n:
        h ^= b[p]*P5 & M; h = rotl(h, 11)*P1 & M; p += 1
    h ^= h >> 33; h = h*P2 & M; h ^= h >> 29; h = h*P3 & M; h ^= h >> 32
    return h
assert xxh64(b'') == 0xEF46DB3751D8E999 and xxh64(bytes(range(32))) == 0xCBF59C5116FF32B4
def ci4_name(tex, pal_be, w, h):
    idx = [v for b in tex for v in (b >> 4, b & 15)]
    lo, hi = min(idx), max(idx)
    return f'tex1_{w}x{h}_{xxh64(tex):016x}_{xxh64(pal_be[lo*2:(hi+1)*2]):016x}_8'
