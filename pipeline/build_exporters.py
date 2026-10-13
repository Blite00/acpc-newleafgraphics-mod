"""Build the model exporters (ExportModels, ExportTreeModels, DumpAnims) on the player's machine.

They are small programs of ours (pipeline/scripts/*.cs) on top of the CGFX/texture code of Ohana3DS Rebirth
(github.com/gdkchan/Ohana3DS-Rebirth). That code is not part of this mod: it is downloaded at a pinned commit,
checked against known hashes, and compiled with the C# compiler that ships with Windows (.NET Framework 4.x).
Set ACPC_OHANA_ZIP to a local copy of the archive to skip the download.
"""
import hashlib, io, os, shutil, subprocess, urllib.request, zipfile
from pathlib import Path
from common import SetupError

COMMIT = 'c50635e82763fad9d1bcc30a905523a1b92d7d1f'
URL = f'https://github.com/gdkchan/Ohana3DS-Rebirth/archive/{COMMIT}.zip'
FILES = {   # path under "Ohana3DS Rebirth/Ohana" -> sha256 of the text with LF line ends and no BOM
    'Models/CGFX.cs': '80fc9a0d123837d1548412f050bce2c27aede3261be3571ac653815fecf74311',
    'RenderBase.cs': 'b95b900dc6a4c2189772fb70b16525dab6a0309b7668cc2a061fbbfa5b61117c',
    'IOUtils.cs': '6d0439cadc6762888ad53a02c3a1e070fa2ca1b01dc628bcc32e740952c8eced',
    'TextureCodec.cs': '170efaf480bb66ea3ade00bee0f45b9e32c24f88db97711490598eca201a97fb',
    'TextureUtils.cs': 'd56a2df5b9fb3b269f0fc294613a94a7ca85469474e95fb72bacd419f98c0ded',
    'Models/MeshUtils.cs': '8b74a5c111b6c257766b085a9b0611c02f11a78b2e8f5be5363a8a9ef0edef93',
    'Models/PICA200/PICACommand.cs': 'e0d4d4ab1329810de80265c718428cbd85910ae6f6286e2d706b9e34cd178e38',
    'Models/PICA200/PICACommandReader.cs': 'fd34693cfaf8a9810a4d20547ae1afaae4faa511e2a578dde8d4c5c1546ea428',
    'Models/PICA200/PICACommandWriter.cs': 'da9cf65f237ba6a0a2a348d5658b0c218af47ca61eb4aea9ee71fb6d3f00dc6f',
}
CGFX_ANIM_SHA = '11d6bc48215a5587c160c033199aa2271fd4f029b53647971a8cdfde9050e149'
EXES = ('ExportModels.exe', 'ExportTreeModels.exe', 'DumpAnims.exe')


def norm(b):
    return b.replace(b'\r\n', b'\n').lstrip(b'\xef\xbb\xbf')


def csc_path():
    win = os.environ.get('WINDIR', r'C:\Windows')
    for fw in ('Framework64', 'Framework'):
        p = Path(win) / 'Microsoft.NET' / fw / 'v4.0.30319' / 'csc.exe'
        if p.exists():
            return p
    raise SetupError('The .NET Framework 4 C# compiler (csc.exe) was not found. It ships with Windows 10 and 11; '
                     'on older systems install .NET Framework 4.8.')


def anim_patch(text):
    """CGFX.cs -> CGFX_anim.cs (used by DumpAnims): skip bones Ohana cannot read, scale key slopes with values."""
    def once(t, old, new):
        assert t.count(old) >= 1, old[:60]
        return t.replace(old, new, 1)
    a = text.index('foreach (dictEntry entry in memberAnimationDataDictionary)')
    head, tail = text[:a], text[a:]
    tail = once(tail, 'foreach (dictEntry entry in memberAnimationDataDictionary)\n                {\n',
                'foreach (dictEntry entry in memberAnimationDataDictionary)\n                {\ntry {\n')
    tail = once(tail, '                    skeletalAnimation.bone.Add(bone);\n                }\n',
                '                    skeletalAnimation.bone.Add(bone);\n'
                '                } catch (Exception) { Console.Error.WriteLine("skip bone in "+skeletalAnimation.name); }\n}\n')
    text = head + tail
    old = '                keyFrame.value = (keyFrame.value * valueScale) + valueOffset;\n'
    text = once(text, old, old + '                keyFrame.inSlope *= valueScale;\n                keyFrame.outSlope *= valueScale;\n')
    return text


def fetch(s):
    local = os.environ.get('ACPC_OHANA_ZIP')
    if local:
        return Path(local).read_bytes()
    cached = s.downloads / f'Ohana3DS-Rebirth-{COMMIT[:12]}.zip'
    if cached.exists():
        return cached.read_bytes()
    s.log('Downloading Ohana3DS Rebirth (model reader source, about 2 MB) from GitHub ...')
    try:
        with urllib.request.urlopen(URL, timeout=120) as r:
            data = r.read()
    except Exception as e:
        raise SetupError(f'Could not download Ohana3DS Rebirth from GitHub ({e}). Setup needs an internet connection '
                         'once for this, or set ACPC_OHANA_ZIP to a downloaded copy of\n' + URL)
    s.downloads.mkdir(parents=True, exist_ok=True)
    cached.write_bytes(data)
    return data


def build(s):
    out = s.work
    pre = os.environ.get('ACPC_EXPORTERS_DIR')     # developer shortcut: already built exporters
    if pre:
        for e in EXES:
            shutil.copy2(Path(pre) / e, out / e)
        s.log('Using prebuilt exporters from ACPC_EXPORTERS_DIR.')
        return
    z = zipfile.ZipFile(io.BytesIO(fetch(s)))
    root = next(n for n in z.namelist() if n.endswith('/Ohana3DS Rebirth/Ohana/RenderBase.cs')).rsplit('Ohana/RenderBase.cs', 1)[0] + 'Ohana/'
    src = s.cache / 'ohana_src'
    shutil.rmtree(src, ignore_errors=True)
    src.mkdir(parents=True)
    paths = {}
    for rel, sha in FILES.items():
        b = norm(z.read(root + rel))
        if hashlib.sha256(b).hexdigest() != sha:
            raise SetupError(f'Ohana3DS Rebirth file {rel} does not match the tested version.')
        p = src / rel.replace('/', '_')
        p.write_bytes(b)
        paths[rel] = p
    anim = anim_patch(paths['Models/CGFX.cs'].read_bytes().decode('utf-8'))
    if hashlib.sha256(anim.encode('utf-8')).hexdigest() != CGFX_ANIM_SHA:
        raise SetupError('Patching Ohana3DS Rebirth for DumpAnims did not give the tested source.')
    (src / 'CGFX_anim.cs').write_text(anim, encoding='utf-8')
    csc = csc_path()
    common = [str(paths[r]) for r in ('RenderBase.cs', 'IOUtils.cs', 'TextureCodec.cs', 'TextureUtils.cs', 'Models/MeshUtils.cs',
                                       'Models/PICA200/PICACommand.cs', 'Models/PICA200/PICACommandReader.cs',
                                       'Models/PICA200/PICACommandWriter.cs')]
    refs = ['/r:System.Web.Extensions.dll', '/r:System.Drawing.dll']
    for exe, main, cgfx in (('ExportModels.exe', 'ExportModels.cs', paths['Models/CGFX.cs']),
                            ('ExportTreeModels.exe', 'ExportTreeModels.cs', paths['Models/CGFX.cs']),
                            ('DumpAnims.exe', 'DumpAnims.cs', src / 'CGFX_anim.cs')):
        s.run([csc, '/nologo', '/unsafe', '/target:exe', f'/out:{out / exe}'] + refs + [str(s.work / main), str(cgfx)] + common,
              cwd=s.work, what=f'Compiling {exe}')
    s.log('Built the model exporters.')
