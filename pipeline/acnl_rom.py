"""Read files out of a user-supplied Animal Crossing: New Leaf ROM.

Supported inputs (all must be DECRYPTED):
  * .3ds / .cci  - NCSD cartridge image (partition 0 is the game)
  * .cxi / .app  - a single NCCH (the game's main content)
  * .cia         - CTR importable archive whose content 0 is a decrypted NCCH
  * a folder     - extracted RomFS (the folder that contains Bg/, Item/, Strc/ ...),
                   optionally with exefs/code.bin (or .code) next to it or inside it

Everything is read lazily from the user's file; nothing is copied unless asked.
"""
import os, struct
from pathlib import Path

MEDIA = 0x200
NL_TITLES = {
    0x0004000000086300: 'Animal Crossing: New Leaf (USA)',
    0x0004000000086400: 'Animal Crossing: New Leaf (EUR)',
    0x0004000000086200: 'Tobidase Doubutsu no Mori (JPN)',
    0x0004000000086500: 'Animal Crossing: New Leaf (KOR)',
    0x0004000000198D00: 'Animal Crossing: New Leaf - Welcome amiibo (JPN)',
    0x0004000000198E00: 'Animal Crossing: New Leaf - Welcome amiibo (USA)',
    0x0004000000198F00: 'Animal Crossing: New Leaf - Welcome amiibo (EUR)',
}


class RomError(Exception):
    pass


def _u32(b, o):
    return struct.unpack_from('<I', b, o)[0]


def _u64(b, o):
    return struct.unpack_from('<Q', b, o)[0]


def _blz_decompress(data):
    """Decompress ExeFS .code (reverse LZSS, 'BLZ')."""
    if len(data) < 8:
        return data
    footer_off = len(data) - 8
    buffer_top_and_bottom, original_bottom = struct.unpack_from('<II', data, footer_off)
    top = buffer_top_and_bottom & 0xFFFFFF
    bottom = buffer_top_and_bottom >> 24
    out_size = len(data) + original_bottom
    out = bytearray(out_size)
    out[:len(data)] = data
    src = len(data) - bottom
    dst = out_size
    end = len(data) - top
    while src > end:
        src -= 1
        flags = out[src]
        for _ in range(8):
            if src <= end:
                break
            if flags & 0x80:
                src -= 2
                v = out[src] | (out[src + 1] << 8)
                size = ((v >> 12) & 0xF) + 3
                disp = (v & 0xFFF) + 3
                for _ in range(size):
                    dst -= 1
                    out[dst] = out[dst + disp]
            else:
                src -= 1
                dst -= 1
                out[dst] = out[src]
            flags = (flags << 1) & 0xFF
    return bytes(out)


class _Ncch:
    def __init__(self, fh, base, label):
        fh.seek(base)
        h = fh.read(0x200)
        if h[0x100:0x104] != b'NCCH':
            raise RomError(f'{label}: no NCCH header found (is this a 3DS game image?)')
        self.base = base
        self.program_id = _u64(h, 0x118)
        flags7 = h[0x18F]
        if not (flags7 & 0x4):
            raise RomError('This ROM is encrypted. Decrypt it first (for example with GodMode9: '
                           '"Decrypt file (...)") and try again.')
        self.exefs = (base + _u32(h, 0x1A0) * MEDIA, _u32(h, 0x1A4) * MEDIA)
        self.romfs = (base + _u32(h, 0x1B0) * MEDIA, _u32(h, 0x1B4) * MEDIA)
        exh_size = _u32(h, 0x180)
        self.code_compressed = False
        if exh_size:
            fh.seek(base + 0x200)
            exh = fh.read(0x400)
            self.code_compressed = bool(exh[0xD] & 1)


class AcnlRom:
    def __init__(self, path):
        self.path = Path(path)
        self.files = {}           # '/Bg/Data/x.bin' -> (offset, size)  (or Path for folder input)
        self.code_path = None
        self.title = None
        self.program_id = None
        self._fh = None
        if self.path.is_dir():
            self._open_dir()
        else:
            self._open_file()

    # -- inputs ------------------------------------------------------------------------------
    def _open_dir(self):
        d = self.path
        if (d / 'romfs').is_dir():
            d = d / 'romfs'
        if not any((d / x).is_dir() for x in ('Bg', 'Item', 'Strc')):
            raise RomError(f'{self.path}: this folder does not look like an extracted New Leaf RomFS '
                           '(expected Bg/, Item/, Strc/ folders).')
        for p in d.rglob('*'):
            if p.is_file():
                self.files['/' + p.relative_to(d).as_posix()] = p
        for c in (self.path / 'exefs' / 'code.bin', self.path / 'exefs' / '.code', self.path / 'code.bin',
                  d.parent / 'exefs' / 'code.bin', d.parent / 'exefs' / '.code', d.parent / 'code.bin'):
            if c.is_file():
                self.code_path = c
                break
        self.kind = 'romfs folder'

    def _open_file(self):
        fh = self._fh = open(self.path, 'rb')
        head = fh.read(0x4000)
        if head[0x100:0x104] == b'NCSD':
            off = _u32(head, 0x120) * MEDIA
            ncch = _Ncch(fh, off, 'NCSD partition 0')
            self.kind = 'NCSD (.3ds/.cci)'
        elif head[0x100:0x104] == b'NCCH':
            ncch = _Ncch(fh, 0, 'NCCH')
            self.kind = 'NCCH (.cxi)'
        elif _u32(head, 0) == 0x2020:
            ncch = self._cia(fh, head)
            self.kind = 'CIA'
        elif head[:4] == b'IVFC':
            self.kind = 'raw RomFS (.romfs)'
            self._read_romfs(fh, 0)
            return
        else:
            raise RomError(f'{self.path.name}: unknown file type. Use a decrypted .3ds/.cci, .cxi or .cia, '
                           'or an extracted RomFS folder.')
        self.program_id = ncch.program_id
        self.title = NL_TITLES.get(ncch.program_id)
        self._ncch = ncch
        if ncch.romfs[1] == 0:
            raise RomError('This image has no RomFS (is it an update or DLC title instead of the game?).')
        self._read_romfs(fh, ncch.romfs[0])

    def _cia(self, fh, head):
        hdr, _type, _ver, cert, tik, tmd, meta = struct.unpack_from('<IHHIIII', head, 0)
        al = lambda x: (x + 63) & ~63
        tmd_off = al(hdr) + al(cert) + al(tik)
        content_off = tmd_off + al(tmd)
        fh.seek(tmd_off)
        t = fh.read(tmd)
        sig_type = struct.unpack_from('>I', t, 0)[0]
        sig_len = {0x10000: 0x200 + 0x3C, 0x10001: 0x100 + 0x3C, 0x10002: 0x3C + 0x40,
                   0x10003: 0x200 + 0x3C, 0x10004: 0x100 + 0x3C, 0x10005: 0x3C + 0x40}.get(sig_type, 0x13C)
        h = 4 + sig_len
        count = struct.unpack_from('>H', t, h + 0x9E)[0]
        chunks = h + 0xC4 + 0x900
        if count:
            ctype = struct.unpack_from('>H', t, chunks + 6)[0]
            if ctype & 1:
                raise RomError('This CIA is encrypted. Decrypt it first (for example with GodMode9) and try again.')
        return _Ncch(fh, content_off, 'CIA content 0')

    def _read_romfs(self, fh, base):
        fh.seek(base)
        ivfc = fh.read(0x60)
        if ivfc[:4] != b'IVFC':
            raise RomError('RomFS has no IVFC header (the image may still be encrypted).')
        master = _u32(ivfc, 0x08)
        l3_block = _u32(ivfc, 0x4C)
        lvl3 = base + ((0x60 + master + (1 << l3_block) - 1) & ~((1 << l3_block) - 1))
        fh.seek(lvl3)
        l3 = fh.read(0x28)
        (hlen, dh_off, dh_len, dm_off, dm_len, fh_off, fh_len, fm_off, fm_len, data_off) = struct.unpack('<10I', l3)
        fh.seek(lvl3 + dm_off)
        dmeta = fh.read(dm_len)
        fh.seek(lvl3 + fm_off)
        fmeta = fh.read(fm_len)
        data_base = lvl3 + data_off

        def name(buf, o, n):
            return buf[o:o + n].decode('utf-16-le')

        def walk_dir(off, prefix):
            parent, sibling, child, cfile, _hn, nl = struct.unpack_from('<6I', dmeta, off)
            f = cfile
            while f != 0xFFFFFFFF:
                _p, fsib, doff, dsize, _h, fnl = struct.unpack_from('<IIQQII', fmeta, f)
                self.files[prefix + '/' + name(fmeta, f + 0x20, fnl)] = (data_base + doff, dsize)
                f = fsib
            c = child
            while c != 0xFFFFFFFF:
                _p, csib, _c, _f, _h, cnl = struct.unpack_from('<6I', dmeta, c)
                walk_dir(c, prefix + '/' + name(dmeta, c + 0x18, cnl))
                c = csib

        walk_dir(0, '')

    # -- access ------------------------------------------------------------------------------
    def read(self, romfs_path):
        e = self.files.get(romfs_path)
        if e is None:
            raise RomError(f'{romfs_path} is missing from the ROM')
        if isinstance(e, Path):
            return e.read_bytes()
        self._fh.seek(e[0])
        return self._fh.read(e[1])

    def exists(self, romfs_path):
        return romfs_path in self.files

    def code(self):
        """Return the decompressed ExeFS .code segment."""
        if self.code_path:
            b = self.code_path.read_bytes()
            return b
        n = getattr(self, '_ncch', None)
        if n is None or n.exefs[1] == 0:
            raise RomError('ExeFS (.code) not available from this input; an extracted RomFS needs '
                           'exefs/code.bin next to it.')
        self._fh.seek(n.exefs[0])
        h = self._fh.read(0x200)
        for i in range(10):
            nm = h[i * 16:i * 16 + 8].rstrip(b'\0')
            off, size = struct.unpack_from('<II', h, i * 16 + 8)
            if nm == b'.code':
                self._fh.seek(n.exefs[0] + 0x200 + off)
                b = self._fh.read(size)
                return _blz_decompress(b) if n.code_compressed else b
        raise RomError('ExeFS has no .code section')

    def code_raw_offset(self):
        """File offset of an uncompressed .code inside the image (None if not applicable)."""
        n = getattr(self, '_ncch', None)
        if n is None or n.code_compressed:
            return None
        self._fh.seek(n.exefs[0])
        h = self._fh.read(0x200)
        for i in range(10):
            if h[i * 16:i * 16 + 8].rstrip(b'\0') == b'.code':
                return n.exefs[0] + 0x200 + struct.unpack_from('<I', h, i * 16 + 8)[0]
        return None

    def inventory(self):
        """List in the same shape as the old 3ds_inventory.json ({path, offset, size})."""
        out = []
        for p, e in sorted(self.files.items(), key=lambda kv: (kv[1][0] if isinstance(kv[1], tuple) else 0, kv[0])):
            if isinstance(e, tuple):
                out.append({'path': p, 'offset': e[0], 'size': e[1]})
            else:
                out.append({'path': p, 'offset': 0, 'size': e.stat().st_size})
        return out

    def describe(self):
        t = self.title or ('unknown title %016X' % self.program_id if self.program_id else 'unknown title')
        return f'{self.kind}: {t}, {len(self.files)} RomFS files'


if __name__ == '__main__':
    import sys, json
    r = AcnlRom(sys.argv[1])
    print(r.describe())
    if len(sys.argv) > 2:
        json.dump(r.inventory(), open(sys.argv[2], 'w'), indent=1)
