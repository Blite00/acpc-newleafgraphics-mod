"""Build a small mod overlay from a local ACGC-PC-Port 0.9.3 checkout.

The overlay contains only files added or changed by the mod; it never copies
the upstream project into the mod repository or release.
"""
import argparse
import hashlib
import json
import shutil
import subprocess
from pathlib import Path

PIN = '4099d246c927e75b4fd342ca13f4ac4395c55af5'
URL = 'https://github.com/flyngmt/ACGC-PC-Port/tree/' + PIN
ROOT = Path(__file__).resolve().parent.parent
VERIFY = ('README.md', 'pc/CMakeLists.txt', 'pc/src/pc_main.c',
          'include/m_name_table.h', '.gitignore')


def files(root):
    return {p.relative_to(root).as_posix(): p for p in root.rglob('*')
            if p.is_file() and '.git' not in p.parts and '__pycache__' not in p.parts}


def normalized(data):
    return data.replace(b'\r\n', b'\n')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--upstream', required=True, type=Path)
    ap.add_argument('--modified', required=True, type=Path)
    ap.add_argument('--out', default=ROOT/'pipeline'/'overlay', type=Path)
    ap.add_argument('--allow-unpinned', action='store_true', help='for preparing a release from a verified source archive')
    a = ap.parse_args()
    base, mod, out = a.upstream.resolve(), a.modified.resolve(), a.out.resolve()
    if not (base/'pc/CMakeLists.txt').is_file() or not (base/'include').is_dir() or not (base/'src').is_dir():
        raise SystemExit('Upstream folder must be the extracted ACGC-PC-Port source root (contains pc, include and src).')
    if (base/'.git').exists():
        rev = subprocess.run(['git', '-c', f'safe.directory={base.as_posix()}', '-C', str(base), 'rev-parse', 'HEAD'], check=True,
                             capture_output=True, text=True).stdout.strip()
        if rev != PIN and not a.allow_unpinned:
            raise SystemExit(f'Expected upstream {PIN}, got {rev}.')
    src, dst = files(base), files(mod)
    changed = []
    for rel, path in dst.items():
        if rel not in src or normalized(path.read_bytes()) != normalized(src[rel].read_bytes()):
            changed.append(rel)
    if not changed:
        raise SystemExit('No mod overlay files found.')
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    for rel in sorted(changed):
        target = out/rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(dst[rel], target)
    anchors = {}
    for rel in VERIFY:
        if rel not in src:
            raise SystemExit('Upstream source is missing required file: '+rel)
        anchors[rel] = hashlib.sha256(normalized(src[rel].read_bytes())).hexdigest()
    manifest = {'upstream_url': URL, 'upstream_revision': PIN, 'upstream_version': '0.9.3',
                'verify_files': anchors, 'overlay_files': sorted(changed)}
    (out/'..'/'tables'/'upstream.json').write_text(json.dumps(manifest, indent=2)+'\n', encoding='utf-8')
    size = sum((out/r).stat().st_size for r in changed)
    print(f'{len(changed)} overlay files, {size/1024/1024:.2f} MiB; base source not copied.')


if __name__ == '__main__':
    main()
