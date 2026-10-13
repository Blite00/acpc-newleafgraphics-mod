"""Compile the New Leaf build of the game with the bundled w64devkit (i686 GCC + CMake)."""
import os, re, subprocess
from pathlib import Path
from common import SetupError


def toolchain_bin(s):
    for c in (s.runtime / 'w64devkit' / 'bin', s.work / 'toolchain' / 'w64devkit' / 'bin'):
        if (c / 'gcc.exe').exists():
            return c
    raise SetupError('The bundled compiler (runtime\\w64devkit) is missing. Please re-extract the release zip.')


def build(s):
    cb = toolchain_bin(s)
    src = s.work / 'ACGC-PC-Port' / 'pc'
    bld = s.cache / 'build'
    sdl_inc = (s.work / 'SDL2-2.30.10' / 'i686-w64-mingw32' / 'include').as_posix()
    flags = f'-D_WIN32_WINNT=0x0601 -DWINVER=0x0601 -I{sdl_inc}'
    env = dict(os.environ)
    env['PATH'] = str(cb) + os.pathsep + env.get('PATH', '')
    cbp = cb.as_posix()
    if not (bld / 'Makefile').exists():
        s.log('Configuring the build ...')
        s.run([cb / 'cmake.exe', '-S', src, '-B', bld, '-G', 'MinGW Makefiles',
               f'-DCMAKE_C_COMPILER={cbp}/gcc.exe', f'-DCMAKE_CXX_COMPILER={cbp}/g++.exe',
               f'-DCMAKE_MAKE_PROGRAM={cbp}/mingw32-make.exe', '-DCMAKE_DISABLE_FIND_PACKAGE_SDL2=ON',
               f'-DCMAKE_C_FLAGS={flags}', f'-DCMAKE_CXX_FLAGS={flags}',
               '-DPC_GAME_EXECUTABLE_NAME=AnimalCrossing-NL'], env=env, what='CMake configure')
    s.log(f'Compiling the game with {s.jobs} jobs (this is the longest step) ...')
    cmd = [str(cb / 'cmake.exe'), '--build', str(bld), '-j', str(s.jobs)]
    s.log('$ ' + ' '.join(cmd), console=False)
    p = subprocess.Popen(cmd, cwd=s.work, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                         text=True, errors='replace')
    last = -10
    tail = []
    for line in p.stdout:
        s.log.f.write(line)
        tail = (tail + [line.rstrip()])[-40:]
        m = re.match(r'\[\s*(\d+)%\]', line)
        if m and int(m.group(1)) >= last + 10:
            last = int(m.group(1))
            s.log(f'  {last}%')
    p.wait()
    if p.returncode != 0:
        errs = [l for l in tail if 'error' in l.lower()] or tail[-10:]
        raise SetupError('Compiling the game failed:\n' + '\n'.join(errs[-10:]))
    exe = bld / 'bin' / 'AnimalCrossing-NL.exe'
    if not exe.exists():
        raise SetupError('The build finished but AnimalCrossing-NL.exe was not produced.')
    s.built_exe = exe
    return exe
