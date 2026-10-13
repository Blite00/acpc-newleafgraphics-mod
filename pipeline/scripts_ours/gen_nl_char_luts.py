"""Fill the New Leaf character lighting curves (rim on N.V, specular on N.H) into pc/shaders/default.frag.

Decodes lu_player_rim1 / lu_player_spc1 from the New Leaf player LUT file (player_source/LUT/LUT.bcres: PICA LUT
upload commands 0x1C8..0x1CF) and writes them resampled to 64 entries into the NL_RIM / NL_SPC arrays. The shipped
shader has these two arrays zeroed."""
import struct, re
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def decode():
    d = (ROOT / 'player_source' / 'LUT' / 'LUT.bcres').read_bytes()
    W = struct.unpack('<%dI' % (len(d) // 4), d[:len(d) // 4 * 4])
    tabs = []
    for i, w in enumerate(W):
        cid = w & 0xFFFF
        if 0x1C8 <= cid <= 0x1CF and (w >> 16) & 0xF == 0xF:
            extra = (w >> 20) & 0xFF
            tabs.append([W[i - 1]] + list(W[i + 1:i + 1 + extra]))
    out = {}
    for name, (a, b) in zip(['lu_player_rim1', 'lu_player_spc1'], [tabs[0:2], tabs[2:4]]):
        out[name] = [(v & 0xFFF) / 4095 for v in a + b]
    return out


def main():
    luts = decode()
    p = ROOT / 'ACGC-PC-Port' / 'pc' / 'shaders' / 'default.frag'
    s = p.read_bytes().decode('utf-8')
    for arr, name in (('NL_RIM', 'lu_player_rim1'), ('NL_SPC', 'lu_player_spc1')):
        v = luts[name]
        vals = ','.join('%.4ff' % v[min(255, round(i * 255 / 63))] for i in range(64))
        s, n = re.subn(r'const float %s\[64\] = float\[\]\([^)]*\);' % arr, f'const float {arr}[64] = float[]({vals});', s)
        assert n == 1, arr
    p.write_bytes(s.encode('utf-8'))
    print('NL character lighting curves written to', p.name)


if __name__ == '__main__':
    main()
