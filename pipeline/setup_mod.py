"""New Leaf graphics mod - first-run setup.

Runs on the player's machine with the bundled Python. Converts the New Leaf assets the mod needs from the player's
own ROMs and builds newleaf_cache/game/AnimalCrossing-NL.exe:

  1. check the inputs (decrypted New Leaf ROM, GameCube disc in rom/)
  2. lay out a work folder: generator scripts + the player's ACGC-PC-Port source with the mod overlay applied
  3. copy the needed New Leaf RomFS files and GameCube files out of the ROMs
  4. build the model exporters and export the New Leaf models/textures
  5. run the generators (C source + texture packs)
  6. compile the game with the bundled compiler
  7. record the poses some generators need with that build, regenerate those parts, rebuild
  8. install the game, shaders and texture packs into newleaf_cache/game

usage: python setup_mod.py --root <game folder> --nl-rom <rom file or RomFS folder> [--jobs N] [--keep-work]
"""
import argparse, hashlib, json, os, shutil, struct, subprocess, sys, time, traceback, _winapi
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import acnl_rom, gc_rom  # noqa: E402
from common import SetupError  # noqa: E402

MOD_VERSION = '1.0.0'


class Log:
    def __init__(self, path):
        self.f = open(path, 'w', encoding='utf-8')
        self.t0 = time.time()

    def __call__(self, msg, console=True):
        line = f'[{time.time() - self.t0:7.1f}s] {msg}'
        self.f.write(line + '\n')
        self.f.flush()
        if console:
            print(line, flush=True)


def junction(target, link):
    link = Path(link)
    if link.exists():
        return
    link.parent.mkdir(parents=True, exist_ok=True)
    _winapi.CreateJunction(str(Path(target).resolve()), str(link))


def remove_tree(p):
    """rmtree that unlinks directory junctions instead of following them."""
    p = Path(p)
    if not p.exists():
        return
    for root, dirs, files in os.walk(p, topdown=True):
        for d in list(dirs):
            full = Path(root) / d
            if os.path.isjunction(full) if hasattr(os.path, 'isjunction') else False:
                os.rmdir(full)
                dirs.remove(d)
    shutil.rmtree(p, ignore_errors=True)


class Setup:
    SetupError = SetupError

    def __init__(self, args):
        self.root = Path(args.root).resolve()
        self.cache = self.root / 'newleaf_cache'
        self.work = self.cache / 'work'
        self.game = self.cache / 'game'
        self.downloads = self.cache / 'downloads'
        self.mod = Path(args.mod).resolve() if args.mod else self.root / 'mod'
        self.runtime = Path(args.runtime).resolve() if args.runtime else self.root / 'runtime'
        self.base_source = Path(args.base_source).resolve()
        self.nl_rom_path = Path(args.nl_rom)
        self.jobs = args.jobs or max(1, (os.cpu_count() or 2))
        self.keep_work = args.keep_work
        self.only = set(args.only.split(',')) if args.only else None
        self.skip = set(args.skip.split(',')) if args.skip else set()
        self.tables = self.mod / 'pipeline' / 'tables'
        self.cache.mkdir(exist_ok=True)
        (self.cache / 'READY').unlink(missing_ok=True)
        (self.cache / 'setup_error.txt').unlink(missing_ok=True)
        self.log = Log(self.cache / 'setup.log')

    # ------------------------------------------------------------------ helpers
    def table(self, name):
        return json.load(open(self.tables / name, encoding='utf-8'))

    def run(self, cmd, cwd=None, env=None, what=None, timeout=None, check=True):
        cwd = cwd or self.work
        self.log(f'$ {" ".join(str(c) for c in cmd)}', console=False)
        p = subprocess.run([str(c) for c in cmd], cwd=cwd, env=env, capture_output=True, text=True,
                           errors='replace', timeout=timeout)
        out = (p.stdout or '') + (p.stderr or '')
        self.log.f.write(out[-20000:] + '\n')
        if check and p.returncode != 0:
            tail = '\n'.join(out.strip().splitlines()[-15:])
            raise SetupError(f'{what or cmd[0]} failed (exit {p.returncode}).\n{tail}')
        return p

    def env(self, **extra):
        e = dict(os.environ)
        e['PYTHONDONTWRITEBYTECODE'] = '1'
        e['PYTHONIOENCODING'] = 'utf-8'
        e['ACPC_NL_ROM'] = str(self.nl_rom_image)
        e['ACPC_GC_ROM'] = str(self.gc_disc_path)
        e.update({k: str(v) for k, v in extra.items()})
        return e

    # ------------------------------------------------------------------ steps
    def check_inputs(self):
        self.log('Checking the ACGC-PC-Port source folder ...')
        manifest = self.table('upstream.json')
        if not (self.base_source / 'pc' / 'CMakeLists.txt').is_file() or not (self.base_source / 'src').is_dir() or not (self.base_source / 'include').is_dir():
            raise SetupError('Select the extracted ACGC-PC-Port 0.9.3 source folder from FlyingMeta’s GitHub page. '
                             'The selected folder must contain pc, src and include.')
        for rel, expected in manifest['verify_files'].items():
            path = self.base_source / rel
            if not path.is_file():
                raise SetupError(f'The selected ACGC-PC-Port folder is missing {rel}. Download the pinned 0.9.3 source archive.')
            digest = hashlib.sha256(path.read_bytes().replace(b'\r\n', b'\n')).hexdigest()
            if digest != expected:
                raise SetupError('The selected source is not the supported ACGC-PC-Port 0.9.3 version. '
                                 'Use the pinned source page opened by the launcher.')
        self.log('  ACGC-PC-Port 0.9.3 verified; New Leaf changes will be applied as a mod overlay.')
        self.log('Checking your New Leaf ROM ...')
        try:
            self.nl = acnl_rom.AcnlRom(self.nl_rom_path)
        except acnl_rom.RomError as e:
            raise SetupError(str(e))
        except OSError as e:
            raise SetupError(f'Could not read {self.nl_rom_path}: {e}')
        self.log('  ' + self.nl.describe())
        if self.nl.program_id is not None and self.nl.program_id not in acnl_rom.NL_TITLES:
            raise SetupError('This is not an Animal Crossing: New Leaf ROM (title %016X).' % self.nl.program_id)
        need = self.table('nl_required.json')        # romfs path -> md5 (tested USA release)
        missing = [p for p in need if not self.nl.exists(p)]
        if missing:
            raise SetupError(f'The New Leaf ROM is missing {len(missing)} files the mod needs (first: {missing[0]}).\n'
                             'The mod is made for Animal Crossing: New Leaf (USA, 00040000 00086300).')
        bad = [p for p, md5 in need.items() if hashlib.md5(self.nl.read(p)).hexdigest() != md5]
        if bad:
            self.log(f'  warning: {len(bad)} of {len(need)} files differ from the tested USA release (first: {bad[0]}); '
                     'setup continues, the result may look different.')
        self.log('Checking your GameCube disc ...')
        disc = gc_rom.find_disc(self.root / 'rom') or gc_rom.find_disc(self.root)
        if disc is None:
            raise SetupError('No GameCube disc image (.iso/.gcm/.ciso) found in the "rom" folder.')
        try:
            self.gc = gc_rom.GcDisc(disc)
        except gc_rom.GcRomError as e:
            raise SetupError(str(e))
        if self.gc.game_id != 'GAFE01':
            raise SetupError(f'The GameCube disc is {self.gc.game_id}; the port supports only GAFE01 (USA).')
        self.gc_disc_path = disc
        self.log(f'  {disc.name}: {self.gc.game_id}')
        free = shutil.disk_usage(self.cache).free
        if free < 6 * 1024 ** 3:
            raise SetupError(f'Not enough free disk space: setup needs about 6 GB, {free // 1024 ** 3} GB free.')
        for name, p in (('Python runtime', Path(sys.executable)), ('compiler', self.runtime / 'w64devkit' / 'bin' / 'gcc.exe'),
                        ('Real-ESRGAN', self.runtime / 'realesrgan' / 'realesrgan-ncnn-vulkan.exe'),
                        ('SDL2', self.runtime / 'SDL2-2.30.10')):
            if not p.exists():
                raise SetupError(f'The bundled {name} is missing ({p}). Please re-extract the release zip.')

    def prepare_work(self):
        self.log('Preparing the work folder ...')
        remove_tree(self.work)
        shutil.copytree(self.mod / 'pipeline' / 'scripts', self.work, ignore=shutil.ignore_patterns('_outer'))
        shutil.copytree(self.base_source, self.work / 'ACGC-PC-Port',
                        ignore=shutil.ignore_patterns('.git', '.vs', 'build*', '__pycache__', '*.pyc', '*.o', '*.obj'))
        overlay = self.mod / 'pipeline' / 'overlay'
        shutil.copytree(overlay, self.work / 'ACGC-PC-Port', dirs_exist_ok=True,
                        ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
        outer = self.mod / 'pipeline' / 'scripts' / '_outer'
        if outer.exists():
            for p in outer.rglob('*'):
                if p.is_file():
                    d = self.cache / p.relative_to(outer)
                    d.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(p, d)
        for d in ('texture_pack', 'fixes_test/poses'):
            remove_tree(self.cache / d)
        junction(self.runtime / 'realesrgan', self.work / 'toolchain' / 'realesrgan')
        junction(self.runtime / 'SDL2-2.30.10', self.work / 'SDL2-2.30.10')

    def make_dirs(self):
        for d in self.table('dirs.json'):    # folders the generators write into
            (self.cache / d[len('_outer/'):] if d.startswith('_outer/') else self.work / d).mkdir(parents=True, exist_ok=True)

    def extract_nl(self):
        self.log('Copying New Leaf files out of your ROM ...')
        copies = self.table('nl_raw_copies.json')   # work path -> romfs path
        for local, romfs in sorted(copies.items()):
            dst = self.work / local
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_bytes(self.nl.read(romfs))
        # an inventory with offsets into nl_rom_image (some scripts seek into the ROM directly)
        if self.nl.path.is_dir():
            self.nl_rom_image = self.work / '_romfs_pack.bin'
            inv = []
            with open(self.nl_rom_image, 'wb') as f:
                for p in sorted(self.nl.files):
                    b = self.nl.read(p)
                    inv.append({'path': p, 'offset': f.tell(), 'size': len(b)})
                    f.write(b)
        else:
            self.nl_rom_image = self.nl.path
            inv = self.nl.inventory()
        try:
            (self.work / '_code.bin').write_bytes(self.nl.code())
        except acnl_rom.RomError as e:
            raise SetupError(str(e))
        (self.work / '3ds_inventory.json').write_text(json.dumps(inv, indent=1))
        self.log(f'  {len(copies)} files')

    def extract_gc(self):
        self.log('Copying GameCube files out of your disc ...')
        (self.work / 'foresta.rel').write_bytes(gc_rom.yaz0(self.gc.file('foresta.rel.szs')))
        arcs = {}
        for spec in self.table('gc_files.json'):
            src = spec['src']
            if ':' in src:
                arc, member = src.split(':', 1)
                if arc not in arcs:
                    arcs[arc] = gc_rom.rarc(self.gc.file(arc))
                data = arcs[arc][member]
            else:
                data = self.gc.file(src)
            if 'slice' in spec:
                a, b = spec['slice']
                data = data[a:b]
            if spec.get('swap16_head'):
                n = spec['swap16_head']
                data = b''.join(data[i + 1:i + 2] + data[i:i + 1] for i in range(0, n, 2)) + data[n:]
            dst = spec['dst']
            dst = (self.cache / dst[len('_outer/'):]) if dst.startswith('_outer/') else (self.work / dst)
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_bytes(data)

    def build_exporters(self):
        import build_exporters
        build_exporters.build(self)

    def export_models(self):
        import export_models
        export_models.run(self)

    def check_esr(self):
        """Real-ESRGAN needs a Vulkan GPU; test it once so a failure is explained."""
        from PIL import Image
        t = self.cache / 'esr_test'
        remove_tree(t)
        (t / 'in').mkdir(parents=True)
        (t / 'out').mkdir()
        Image.new('RGB', (16, 16), (120, 160, 90)).save(t / 'in' / 'a.png')
        p = subprocess.run([str(self.runtime / 'realesrgan' / 'realesrgan-ncnn-vulkan.exe'), '-i', str(t / 'in'), '-o', str(t / 'out'),
                            '-n', 'realesrgan-x4plus', '-s', '4', '-f', 'png'], capture_output=True, text=True, errors='replace',
                           cwd=self.runtime / 'realesrgan', timeout=600)
        ok = (t / 'out' / 'a.png').exists()
        remove_tree(t)
        if not ok:
            self.log((p.stdout or '') + (p.stderr or ''), console=False)
            raise SetupError('Real-ESRGAN (texture upscaler) could not run. It needs a graphics card with Vulkan support '
                             'and an up-to-date graphics driver.')

    def generate(self, phase):
        steps = [s for s in self.table('steps.json') if s.get('phase', 1) == phase]
        for i, st in enumerate(steps):
            if self.only and st['name'] not in self.only:
                continue
            if st['name'] in self.skip:
                continue
            cmd = []
            for a in st['cmd']:
                a = a.replace('{work}', self.work.as_posix()).replace('{tables}', self.tables.as_posix())
                if a.startswith('@'):
                    cmd += [l.strip() for l in open(a[1:]) if l.strip()]
                else:
                    cmd.append(a)
            self.log(f'[{i + 1}/{len(steps)}] {st.get("label", st["name"])}  ({st["name"]})')
            cwd = self.work / st['cwd'] if st.get('cwd') else self.work
            script = (self.work / cmd[0]).resolve() if not st.get('cwd') else (cwd / cmd[0])
            self.run([sys.executable, '-s', '-X', 'utf8', str(script)] + cmd[1:], cwd=cwd, env=self.env(**st.get('env', {})),
                     what=st['name'], timeout=st.get('timeout', 3600))
        # generators append themselves to the CMake source list; the shipped list already has everything
        shutil.copy2(self.mod / 'source' / 'ACGC-PC-Port' / 'pc' / 'CMakeLists.txt', self.work / 'ACGC-PC-Port' / 'pc' / 'CMakeLists.txt')
        # sources that only exist once the poses are recorded (phase 2) get an empty placeholder for the first build
        import re as _re
        cm = (self.work / 'ACGC-PC-Port' / 'pc' / 'CMakeLists.txt').read_text()
        for m in _re.finditer(r'\$\{CMAKE_CURRENT_SOURCE_DIR\}/(src/pc_[\w]+\.c)', cm):
            f = self.work / 'ACGC-PC-Port' / 'pc' / m.group(1)
            if not f.exists():
                f.write_text('/* placeholder: generated after the pose capture */\n')
                self.log(f'  placeholder {m.group(1)}', console=False)

    def compile_game(self):
        import build_game
        build_game.build(self)

    def capture_poses(self):
        import capture
        capture.run(self)

    def install(self):
        import install_game
        install_game.run(self)

    # ------------------------------------------------------------------ main
    def main(self):
        steps = [
            ('check_inputs', self.check_inputs),
            ('prepare_work', self.prepare_work),
            ('make_dirs', self.make_dirs),
            ('extract_nl', self.extract_nl),
            ('extract_gc', self.extract_gc),
            ('build_exporters', self.build_exporters),
            ('export_models', self.export_models),
            ('check_esr', self.check_esr),
            ('generate', lambda: self.generate(1)),
            ('compile', self.compile_game),
            ('capture_poses', self.capture_poses),
            ('generate_posed', lambda: self.generate(2)),
            ('recompile', self.compile_game),
            ('install', self.install),
        ]
        t = time.time()
        for name, fn in steps:
            if name in self.skip:
                continue
            self.log(f'== {name}')
            fn()
        (self.cache / 'READY').write_text(f'{MOD_VERSION}\n')
        if not self.keep_work:
            self.log('Removing the work folder ...')
            remove_tree(self.work)
            remove_tree(self.cache / 'build')
        self.log(f'Done in {(time.time() - t) / 60:.1f} minutes.')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--root', required=True)
    ap.add_argument('--nl-rom', required=True)
    ap.add_argument('--base-source', required=True, help='extracted ACGC-PC-Port 0.9.3 source folder')
    ap.add_argument('--mod', default='', help='mod folder (default: <root>/mod)')
    ap.add_argument('--runtime', default='', help='runtime folder (default: <root>/runtime)')
    ap.add_argument('--jobs', type=int, default=0)
    ap.add_argument('--keep-work', action='store_true')
    ap.add_argument('--only', default='')
    ap.add_argument('--skip', default='')
    ap.add_argument('--no-pause', action='store_true')
    args = ap.parse_args()
    s = Setup(args)
    try:
        s.main()
        return 0
    except SetupError as e:
        s.log('ERROR: ' + str(e))
        (s.cache / 'setup_error.txt').write_text(str(e), encoding='utf-8')
    except Exception as e:
        s.log('ERROR: ' + traceback.format_exc())
        (s.cache / 'setup_error.txt').write_text(f'Unexpected error: {e}. See newleaf_cache\\setup.log.', encoding='utf-8')
    if not args.no_pause:
        print('\nSetup did not finish. Press Enter to close this window.')
        try:
            input()
        except Exception:
            pass
    return 1


if __name__ == '__main__':
    sys.exit(main())
