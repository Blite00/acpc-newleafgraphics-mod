"""Write icon_inventory.json: [name, offset, size] of every file in item_icon_tex.arc (a darc archive).

Input: item_icon_tex.arc (copied out of the player's New Leaf ROM: /Layout/ItemWin/item_icon_tex.arc).
"""
import json, struct
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def darc_files(b):
    tbl, tlen, doff = struct.unpack_from('<III', b, 0x10)
    n = struct.unpack_from('<III', b, tbl)[2]
    names = tbl + n * 12
    out = []
    for i in range(n):
        no, o, s = struct.unpack_from('<III', b, tbl + i * 12)
        isdir = no >> 24
        no &= 0xFFFFFF
        if isdir:
            continue
        j = names + no
        nm = b''
        while b[j:j + 2] != b'\0\0':
            nm += b[j:j + 2]
            j += 2
        out.append([nm.decode('utf-16le'), o, s])
    return out


def main():
    b = (ROOT / 'item_icon_tex.arc').read_bytes()
    files = sorted(darc_files(b), key=lambda e: e[1])
    (ROOT / 'icon_inventory.json').write_text(json.dumps(files, indent=2))
    print(len(files), 'icons')


if __name__ == '__main__':
    main()
