"""Record the poses some generators need (tables/captures.json) by running the first build of the game.

The character and furniture generators fit New Leaf models onto GameCube skeletons in the pose the game draws
them in. Those joint matrices come from the GameCube animations, so they are captured from the player's own copy:
the freshly built game is started a few times (PC_DUMP_POSE) in a sandbox folder (its own save/, the game folder's
rom/ linked in) and quits by itself. A game window opens briefly for each run.
"""
import os, shutil, subprocess, _winapi
from pathlib import Path
from common import SetupError


def run(s):
    caps = s.table('captures.json')
    box = s.cache / 'capture'
    shutil.rmtree(box, ignore_errors=True)
    box.mkdir(parents=True)
    exe_dir = s.cache / 'build' / 'bin'
    exe = exe_dir / 'AnimalCrossing-NL.exe'
    rom = s.gc_disc_path.parent
    _winapi.CreateJunction(str(rom), str(box / 'rom'))
    shutil.copytree(s.work / 'ACGC-PC-Port' / 'pc' / 'shaders', box / 'shaders')
    for dll in exe_dir.glob('*.dll'):
        shutil.copy2(dll, box / dll.name)
    tmp = box / 'tmp'
    tmp.mkdir()
    s.log(f'Recording character and furniture poses ({len(caps)} short game runs; a game window opens briefly) ...')
    try:
        for i, c in enumerate(caps):
            out = (s.cache / c['out'][len('_outer/'):]) if c['out'].startswith('_outer/') else (s.work / c['out'])
            out.parent.mkdir(parents=True, exist_ok=True)
            if out.exists():
                out.unlink()
            env = dict(os.environ)
            env.update(c.get('env', {}))
            env['PC_DUMP_POSE'] = str(out)
            args = [a.replace('{tmp}', str(tmp)) for a in c['args']]
            s.log(f'  [{i + 1}/{len(caps)}] {c["name"]}')
            try:
                subprocess.run([str(exe)] + args, cwd=box, env=env, capture_output=True, timeout=c.get('timeout', 300))
            except subprocess.TimeoutExpired:
                pass                      # the dump is written as it goes; a run that does not quit is stopped
            if not out.exists() or out.stat().st_size == 0:
                raise SetupError(f'The game run "{c["name"]}" did not record any poses. Check that the game starts '
                                 '(graphics driver) and try again.')
    finally:
        try:
            os.rmdir(box / 'rom')          # remove the junction only, never the player's rom folder
        except OSError:
            pass
    shutil.rmtree(box, ignore_errors=True)
    s.log('Poses recorded.')
