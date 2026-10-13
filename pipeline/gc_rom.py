"""Read files from the user's GameCube Animal Crossing disc image (same formats as the port: ISO/GCM/CISO).

Also: Yaz0 decompression and RARC archive listing, used to pull foresta.rel and forest_1st.arc members.
"""
import struct
from pathlib import Path

CISO_HDR = 0x8000


class GcRomError(Exception):
    pass


def yaz0(b):
    if b[:4] != b'Yaz0':
        return b
    size = struct.unpack_from('>I', b, 4)[0]
    out = bytearray(size)
    o = 0
    pos = 16
    n = len(b)
    while o < size:
        mask = b[pos]
        pos += 1
        for bit in range(7, -1, -1):
            if o >= size:
                break
            if mask & (1 << bit):
                out[o] = b[pos]
                o += 1
                pos += 1
            else:
                v = (b[pos] << 8) | b[pos + 1]
                pos += 2
                count = v >> 12
                dist = (v & 4095) + 1
                if count == 0:
                    count = b[pos] + 18
                    pos += 1
                else:
                    count += 2
                src = o - dist
                if dist >= count:
                    out[o:o + count] = out[src:src + count]
                    o += count
                else:
                    for _ in range(count):
                        out[o] = out[src]
                        o += 1
                        src += 1
    return bytes(out)


class GcDisc:
    def __init__(self, path):
        self.path = Path(path)
        self.fh = open(self.path, 'rb')
        hdr = self.fh.read(CISO_HDR)
        self.ciso = hdr[:4] == b'CISO'
        if self.ciso:
            self.block = struct.unpack_from('<I', hdr, 4)[0]
            phys = 0
            self.map = []
            for i in range(CISO_HDR - 8):
                if hdr[8 + i]:
                    self.map.append(phys)
                    phys += 1
                else:
                    self.map.append(-1)
        boot = self.read(0, 0x440)
        self.game_id = boot[:6].decode('ascii', 'replace')
        if struct.unpack_from('>I', boot, 0x1C)[0] != 0xC2339F3D:
            raise GcRomError(f'{self.path.name}: not a GameCube disc image')
        fst_off, fst_size = struct.unpack_from('>II', boot, 0x424)
        fst = self.read(fst_off, fst_size)
        n = struct.unpack_from('>I', fst, 8)[0]
        names = fst[n * 12:]
        self.files = {}

        def nm(i):
            no = struct.unpack_from('>I', fst, i * 12)[0] & 0xFFFFFF
            return names[no:names.find(b'\0', no)].decode('shift_jis', 'replace')

        def walk(start, end, prefix):
            i = start
            while i < end:
                typ = fst[i * 12]
                a, b = struct.unpack_from('>II', fst, i * 12 + 4)
                name = nm(i)
                if typ == 1:
                    walk(i + 1, b, prefix + name + '/')
                    i = b
                else:
                    self.files[prefix + name] = (a, b)
                    i += 1

        walk(1, n, '')

    def read(self, off, size):
        if not self.ciso:
            self.fh.seek(off)
            return self.fh.read(size)
        out = bytearray()
        while size > 0:
            blk, inner = divmod(off, self.block)
            take = min(size, self.block - inner)
            p = self.map[blk] if blk < len(self.map) else -1
            if p < 0:
                out += bytes(take)
            else:
                self.fh.seek(CISO_HDR + p * self.block + inner)
                out += self.fh.read(take)
            off += take
            size -= take
        return bytes(out)

    def dol(self):
        """The main executable (boot.dol)."""
        off = struct.unpack_from('>I', self.read(0x420, 4), 0)[0]
        hdr = self.read(off, 0x100)
        end = 0
        for i in range(18):
            o = struct.unpack_from('>I', hdr, i * 4)[0]
            s = struct.unpack_from('>I', hdr, 0x90 + i * 4)[0]
            if o and s:
                end = max(end, o + s)
        return self.read(off, end)

    def file(self, name):
        if name not in self.files:
            hits = [k for k in self.files if k.rsplit('/', 1)[-1] == name]
            if len(hits) != 1:
                raise GcRomError(f'{name} not found on the GameCube disc')
            name = hits[0]
        off, size = self.files[name]
        return self.read(off, size)


def rarc(data):
    """Parse a RARC archive -> {path: bytes}."""
    data = yaz0(data)
    if data[:4] != b'RARC':
        raise GcRomError('not a RARC archive')
    data_off = struct.unpack_from('>I', data, 0x0C)[0] + 0x20
    info = 0x20
    node_count, node_off, entry_count, entry_off, str_size, str_off = struct.unpack_from('>IIIIII', data, info)
    node_off += 0x20
    entry_off += 0x20
    str_off += 0x20

    def s(o):
        e = data.index(b'\0', str_off + o)
        return data[str_off + o:e].decode('shift_jis', 'replace')

    out = {}

    def walk(ni, prefix):
        typ, name_off, _h, count, first = struct.unpack_from('>4sIHHI', data, node_off + ni * 16)
        for k in range(count):
            eo = entry_off + (first + k) * 20
            _id, _hash, attr, name_o, a, size = struct.unpack_from('>HHHHII', data, eo)
            nm = s(name_o)
            if attr & 0x0200:          # directory
                if nm in ('.', '..'):
                    continue
                walk(a, prefix + nm + '/')
            else:
                out[prefix + nm] = data[data_off + a:data_off + a + size]

    walk(0, '')
    return out


def find_disc(folder):
    for ext in ('*.ciso', '*.iso', '*.gcm'):
        for p in sorted(Path(folder).glob(ext)):
            return p
    return None


if __name__ == '__main__':
    import sys
    d = GcDisc(sys.argv[1])
    print(d.game_id, len(d.files), 'files')
    for k in list(d.files)[:20]:
        print(' ', k, d.files[k])
