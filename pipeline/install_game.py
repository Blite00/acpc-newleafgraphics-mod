"""Install the built game, its shaders and the generated texture packs into newleaf_cache/game."""
import shutil
from pathlib import Path
from common import SetupError


def run(s):
    g = s.game
    if g.exists():
        shutil.rmtree(g)
    g.mkdir(parents=True)
    exe = getattr(s, 'built_exe', None) or (s.cache / 'build' / 'bin' / 'AnimalCrossing-NL.exe')
    if not exe.exists():
        raise SetupError('AnimalCrossing-NL.exe is missing after the build.')
    shutil.copy2(exe, g / 'AnimalCrossing-NL.exe')
    for dll in exe.parent.glob('*.dll'):
        shutil.copy2(dll, g / dll.name)
    if not (g / 'SDL2.dll').exists():
        sdl = s.root / 'SDL2.dll'
        if sdl.exists():
            shutil.copy2(sdl, g / 'SDL2.dll')
    shutil.copytree(s.work / 'ACGC-PC-Port' / 'pc' / 'shaders', g / 'shaders')
    tp = g / 'texture_pack'
    tp.mkdir()
    n = 0
    for spec in s.table('texture_packs.json'):
        src = (s.cache / spec['src'][len('_outer/'):]) if spec['src'].startswith('_outer/') else (s.work / spec['src'])
        if not src.is_dir():
            if spec.get('optional'):
                s.log(f'  skipped texture pack {spec["name"]} ({spec.get("why", "not generated")})')
                continue
            raise SetupError(f'Texture pack {spec["name"]} was not generated ({src}).')
        shutil.copytree(src, tp / spec['name'])
        n += sum(1 for _ in (tp / spec['name']).rglob('*.dds'))
    s.log(f'Installed the game, shaders and {n} texture-pack textures.')
