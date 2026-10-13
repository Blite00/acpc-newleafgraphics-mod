"""Scan a folder (the repository or an extracted release) for anything that looks like Nintendo data.

Flags:
  * ROM/asset/container formats (.bcres .bclim .arc .darc .szs .rel .dol .nes .fds .gci .iso .gcm .ciso .cci .3ds .cia
    .cxi .bti .bin .raw .pal .tex .dds .tpl .brres .ptcl .bcfnt .umsbt ...)
  * images (.png .jpg .bmp .tga .gif .webp .ico) outside an allow-list
  * text source files with large numeric arrays (more than LIMIT numbers) that differ from upstream ACGC-PC-Port
  * text files with long base64 / hex runs
Files byte-identical to upstream ACGC-PC-Port (git checkout) are reported separately as upstream. The mod release
contains only `pipeline/overlay`, not the upstream checkout.

usage: python tools/scan_nintendo.py <folder> [--upstream <ACGC-PC-Port checkout>] [--release]
"""
import argparse, os, re, sys
from pathlib import Path

ap = argparse.ArgumentParser()
ap.add_argument('folder')
ap.add_argument('--upstream', default=r'G:\PC_ports\ACPC\ship\_work\upstream')
ap.add_argument('--release', action='store_true', help='a release folder: allow the bundled runtimes')
ap.add_argument('--limit', type=int, default=4000)
args = ap.parse_args()
ROOT = Path(args.folder)
UP = Path(args.upstream)

ASSET_EXT = {'.bcres', '.bclim', '.bclyt', '.bclan', '.arc', '.darc', '.szs', '.rel', '.dol', '.nes', '.fds', '.gci', '.iso',
             '.gcm', '.ciso', '.cci', '.3ds', '.cia', '.cxi', '.app', '.romfs', '.bti', '.raw', '.pal', '.tex', '.dds', '.tpl',
             '.brres', '.ptcl', '.bcfnt', '.umsbt', '.msbt', '.bfwav', '.bcwav', '.bcstm', '.aw', '.baa', '.bms', '.cmp',
             '.yaz0', '.nlzss', '.lz', '.sav', '.dat'}
IMG_EXT = {'.png', '.jpg', '.jpeg', '.bmp', '.tga', '.gif', '.webp', '.ico'}
TEXT_EXT = {'.c', '.h', '.inc', '.c_inc', '.cpp', '.hpp', '.py', '.json', '.txt', '.md', '.cs', '.ps1', '.frag', '.vert', '.glsl',
            '.cmake', '.ini', '.yml', '.yaml', '.s', '.ld', '.sh', '.cmd', '.bat', '.rc', '.manifest', '.toml', '.cfg'}
RUNTIME_DIRS = ('runtime/', 'gc/')
NUM = re.compile(rb'(?<![A-Za-z_0-9.])-?(?:0x[0-9A-Fa-f]+|\d+\.\d+f?|\d+)(?![A-Za-z_0-9.])')
B64 = re.compile(rb'[A-Za-z0-9+/]{400,}={0,2}')
HEXRUN = re.compile(rb'(?:[0-9A-Fa-f]{2}){300,}')
ALLOW_BIN = {'AnimalCrossing.exe', 'SDL2.dll'}


def upstream_twin(rel):
    """the same file in an upstream checkout or in a submitted upstream-source tree."""
    parts = Path(rel).parts
    if 'ACGC-PC-Port' in parts:
        i = parts.index('ACGC-PC-Port')
        p = UP.joinpath(*parts[i + 1:])
        return p if p.exists() else None
    return None


def same_as_upstream(p, rel):
    t = upstream_twin(rel)
    if t is None:
        return False
    return p.read_bytes().replace(b'\r\n', b'\n') == t.read_bytes().replace(b'\r\n', b'\n')


findings, upstream_hits = [], []
n = 0
for p in sorted(ROOT.rglob('*')):
    if not p.is_file():
        continue
    rel = p.relative_to(ROOT).as_posix()
    if '/.git/' in '/' + rel or rel.startswith('.git/'):
        continue
    n += 1
    ext = p.suffix.lower()
    if args.release and rel.startswith(RUNTIME_DIRS):
        continue
    if rel.endswith('.c_inc'):
        ext = '.c_inc'
    if ext in ASSET_EXT:
        (upstream_hits if same_as_upstream(p, rel) else findings).append(('asset-format', rel, p.stat().st_size))
        continue
    if ext in IMG_EXT:
        (upstream_hits if same_as_upstream(p, rel) else findings).append(('image', rel, p.stat().st_size))
        continue
    if ext in ('.exe', '.dll', '.o', '.obj', '.a', '.lib', '.zip', '.7z'):
        if p.name not in ALLOW_BIN:
            findings.append(('binary', rel, p.stat().st_size))
        continue
    if ext in TEXT_EXT or ext == '':
        b = p.read_bytes()
        if b'\0' in b[:4096] and ext not in ('.txt',):
            findings.append(('binary-text', rel, len(b)))
            continue
        nums = len(NUM.findall(b))
        flags = []
        if nums > args.limit:
            flags.append(f'{nums} numbers')
        if B64.search(b):
            flags.append('base64 run')
        if HEXRUN.search(b):
            flags.append('hex run')
        if flags:
            (upstream_hits if same_as_upstream(p, rel) else findings).append(('data? ' + ', '.join(flags), rel, len(b)))
    else:
        findings.append(('unknown-type', rel, p.stat().st_size))

print(f'scanned {n} files in {ROOT}')
print(f'identical to upstream ACGC-PC-Port and flagged by the same rules: {len(upstream_hits)}')
print(f'FINDINGS: {len(findings)}')
for kind, rel, size in findings:
    print(f'  {kind:28s} {size:>10}  {rel}')
sys.exit(1 if findings else 0)
