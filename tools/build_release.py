"""Maintainer tool: assemble the release folder (and zip) for players.

Layout of the release:
  AnimalCrossing.exe                 launcher (launcher/launcher.c)
  Set up New Leaf graphics.cmd       runs the setup again
  Play with GameCube graphics.cmd    starts the GameCube-graphics build
  mod/pipeline, mod/overlay          setup scripts and only the New Leaf changes to ACGC-PC-Port
  gc/                                empty folder for the player's own ACGC-PC-Port executable
  runtime/python                     Python 3.12 + numpy, Pillow, scipy (trimmed copy of a local install)
  runtime/w64devkit                  i686 GCC + CMake (w64devkit 2.1.0)
  runtime/realesrgan                 Real-ESRGAN ncnn Vulkan + models
  runtime/SDL2-2.30.10               SDL2 i686 development files (headers + static lib) for the build
  rom/ save/ texture_pack/           empty: the player's GameCube disc, saves, optional HD packs

usage: python tools/build_release.py --out <folder> [--zip]
"""
import argparse, os, shutil, subprocess, sys, zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
ap = argparse.ArgumentParser()
ap.add_argument('--out', required=True)
ap.add_argument('--zip', action='store_true')
ap.add_argument('--python', default=str(Path(sys.executable).parent))
ap.add_argument('--w64devkit', default=r'G:\PC_ports\ACPC\asset_import_work\toolchain\w64devkit')
ap.add_argument('--realesrgan', default=r'G:\PC_ports\ACPC\asset_import_work\toolchain\realesrgan')
ap.add_argument('--sdl2', default=r'G:\PC_ports\ACPC\asset_import_work\SDL2-2.30.10')
args = ap.parse_args()
OUT = Path(args.out)
VERSION = '1.0.0'


def copytree(src, dst, ignore=None):
    shutil.copytree(src, dst, ignore=ignore, dirs_exist_ok=True)


def python_runtime(dst):
    src = Path(args.python)
    dst.mkdir(parents=True, exist_ok=True)
    for f in src.iterdir():
        if f.is_file() and f.suffix.lower() in ('.exe', '.dll') and f.name.lower() not in ('pythonw.exe',):
            shutil.copy2(f, dst / f.name)
    shutil.copy2(src / 'LICENSE.txt', dst / 'LICENSE.txt')
    copytree(src / 'DLLs', dst / 'DLLs', ignore=shutil.ignore_patterns('_tkinter*', 'tcl*', 'tk*', '*.ico', '_test*'))
    skip = {'test', 'idlelib', 'tkinter', 'turtledemo', 'ensurepip', 'lib2to3', 'pydoc_data', 'site-packages', '__pycache__',
            'venv'}
    copytree(src / 'Lib', dst / 'Lib', ignore=lambda d, names: [n for n in names if n in skip or n.endswith('.pyc')])
    import site
    keep = []
    for sp in [src / 'Lib' / 'site-packages', Path(site.getusersitepackages())]:
        if not sp.exists():
            continue
        for n in os.listdir(sp):
            if n.lower().startswith(('numpy', 'scipy', 'pil', 'pillow')) and not n.endswith('.whl'):
                s = sp / n
                d = dst / 'Lib' / 'site-packages' / n
                if s.is_dir():
                    copytree(s, d, ignore=shutil.ignore_patterns('__pycache__', 'tests', 'test', '*.pyc'))
                else:
                    d.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(s, d)
                keep.append(n)
    return keep


def main():
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)
    # launcher
    subprocess.run(['cmd', '/c', str(REPO / 'launcher' / 'build.cmd'), str(Path(args.w64devkit) / 'bin')], cwd=REPO / 'launcher', check=True)
    shutil.copy2(REPO / 'launcher' / 'AnimalCrossing.exe', OUT / 'AnimalCrossing.exe')
    (OUT / 'Set up New Leaf graphics.cmd').write_text('@echo off\r\nstart "" "%~dp0AnimalCrossing.exe" --setup\r\n')
    (OUT / 'Play with GameCube graphics.cmd').write_text('@echo off\r\nstart "" "%~dp0AnimalCrossing.exe" --vanilla\r\n')
    # The original ACGC-PC-Port executable and shaders are obtained by the player from FlyingMeta's page.
    (OUT / 'gc').mkdir()
    (OUT / 'gc' / 'PUT_UPSTREAM_EXECUTABLE_HERE.txt').write_text(
        'Download the original ACGC-PC-Port release from https://github.com/flyngmt/ACGC-PC-Port/releases\r\n'
        'Copy its AnimalCrossing.exe here as AnimalCrossing-GC.exe. Copy its shaders folder next to the mod launcher.\r\n')
    sdl_dll = Path(args.sdl2) / 'i686-w64-mingw32' / 'bin' / 'SDL2.dll'
    if not sdl_dll.is_file():
        raise FileNotFoundError(f'SDL2.dll was not found in {sdl_dll}')
    shutil.copy2(sdl_dll, OUT / 'SDL2.dll')
    # mod
    copytree(REPO / 'pipeline', OUT / 'mod' / 'pipeline', ignore=shutil.ignore_patterns('__pycache__', 'scripts_ours'))
    # runtimes
    keep = python_runtime(OUT / 'runtime' / 'python')
    print('python packages:', keep)
    copytree(args.w64devkit, OUT / 'runtime' / 'w64devkit')
    r = OUT / 'runtime' / 'realesrgan'
    r.mkdir(parents=True)
    for n in ('realesrgan-ncnn-vulkan.exe', 'vcomp140.dll', 'vcomp140d.dll', 'README_windows.md'):
        if (Path(args.realesrgan) / n).exists():
            shutil.copy2(Path(args.realesrgan) / n, r / n)
    copytree(Path(args.realesrgan) / 'models', r / 'models')
    s = OUT / 'runtime' / 'SDL2-2.30.10'
    copytree(Path(args.sdl2) / 'i686-w64-mingw32' / 'include', s / 'i686-w64-mingw32' / 'include')
    (s / 'i686-w64-mingw32' / 'lib').mkdir(parents=True)
    for n in os.listdir(Path(args.sdl2) / 'i686-w64-mingw32' / 'lib'):
        p = Path(args.sdl2) / 'i686-w64-mingw32' / 'lib' / n
        if p.is_file():
            shutil.copy2(p, s / 'i686-w64-mingw32' / 'lib' / n)
    for n in ('LICENSE.txt', 'README-SDL.txt', 'COPYING.txt'):
        if (Path(args.sdl2) / n).exists():
            shutil.copy2(Path(args.sdl2) / n, s / n)
    # player folders + docs
    for d in ('rom', 'save', 'texture_pack'):
        (OUT / d).mkdir(exist_ok=True)
    (OUT / 'rom' / 'PUT YOUR GAMECUBE DISC HERE.txt').write_text(
        'Put your own Animal Crossing (USA, GAFE01) GameCube disc image here: .iso, .gcm or .ciso.\r\n')
    for n in ('README.md', 'LICENSE', 'THIRD_PARTY_NOTICES.md'):
        if (REPO / n).exists():
            shutil.copy2(REPO / n, OUT / n)
    print('release folder:', OUT)
    if args.zip:
        z = OUT.parent / f'acpc-newleaf-graphics-mod-{VERSION}.zip'
        with zipfile.ZipFile(z, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
            for p in sorted(OUT.rglob('*')):
                if p.is_file():
                    zf.write(p, Path(OUT.name) / p.relative_to(OUT))
        print('zip:', z, z.stat().st_size // (1024 * 1024), 'MB')


if __name__ == '__main__':
    main()
