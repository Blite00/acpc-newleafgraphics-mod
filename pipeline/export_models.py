"""Export New Leaf models/textures to JSON + PNG with the exporters (tables/exports.json, tables/dumpanims.json),
then the raw texture decodes the house and dock generators need (PowerShell scripts that reuse the exporter's codec)."""
import concurrent.futures as cf, hashlib, os, shutil, subprocess
from pathlib import Path
from common import SetupError


def run(s):
    jobs = s.table('exports.json')
    tmp = s.cache / 'export_tmp'
    tmp.mkdir(exist_ok=True)

    def one(job):
        d, romfs, tool = job
        b = tmp / (hashlib.md5(romfs.encode()).hexdigest() + '.bcres')
        if not b.exists():
            b.write_bytes(s.nl.read(romfs))
        out = s.work / d
        out.mkdir(parents=True, exist_ok=True)
        p = subprocess.run([str(s.work / (tool + '.exe')), str(b), str(out)], capture_output=True, text=True, errors='replace',
                           timeout=900)
        if p.returncode != 0:
            return f'{d}: {tool} failed: {(p.stdout + p.stderr).strip()[-300:]}'
        return None

    s.log(f'Exporting {len(jobs)} New Leaf models and textures ...')
    errors = []
    done = 0
    with cf.ThreadPoolExecutor(max(2, min(8, s.jobs))) as ex:
        for r in ex.map(one, jobs):
            done += 1
            if r:
                errors.append(r)
            if done % 200 == 0:
                s.log(f'  {done}/{len(jobs)}')
    if errors:
        s.log('\n'.join(errors), console=False)
        raise SetupError(f'{len(errors)} model exports failed, first: {errors[0]}')
    shutil.rmtree(tmp, ignore_errors=True)
    for src, out in s.table('dumpanims.json'):
        (s.work / out).parent.mkdir(parents=True, exist_ok=True)
        s.run([s.work / 'DumpAnims.exe', s.work / src, s.work / out], what='DumpAnims')
    for d in ('dock_source/season00', 'dock_source/season09'):
        (s.work / d).mkdir(parents=True, exist_ok=True)
    for ps1 in ('export_house_raw_textures.ps1', 'export_dock_raw_textures.ps1'):
        s.run(['powershell.exe', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', s.work / ps1], what=ps1)
    s.log('Exports done.')
