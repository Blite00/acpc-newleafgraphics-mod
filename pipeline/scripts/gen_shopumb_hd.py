"""Shop umbrella canopies: the NL umbrella canopy textures are tiny (most 32x32 or 32x64, paper 16x64) and the
shop/furniture umbrella is drawn much larger than the held one, so they read as low-res. 4x Real-ESRGAN (general model,
source detail added back, same method as the shirts), falling back to crisp 4x for grid patterns (gingham, dots) that
ESR smears. Writes tool_source_hd/<tool>/<tex>.png; gen_shopumb.py uses these when present."""
import json, shutil, subprocess
from pathlib import Path
import numpy as np
from PIL import Image, ImageFilter
ROOT = Path(__file__).resolve().parent
src = (ROOT/'generate_mailbox_hd.py').read_text()
W = ROOT/'shopumb_up'; UP = 4; PAD = 6; DETAIL = 0.35
ESR = ROOT/'toolchain/realesrgan/realesrgan-ncnn-vulkan.exe'
exec(src[src.index('def _pad_mode'):src.index('# ---------------- textures')])
gsrc = open(ROOT/'generate_tools.py').read()
UMB = eval(gsrc[gsrc.index('UMB = {')+6:gsrc.index('}', gsrc.index('UMB = {'))+1])
WRAP = {0: 'GX_CLAMP', 1: 'GX_CLAMP', 2: 'GX_REPEAT', 3: 'GX_MIRROR'}
jobs = []; srcs = {}
for num, tool in UMB.items():
    d = json.load(open(ROOT/'tool_source'/tool/f'{tool}.json'))
    for m in d['meshes']:
        t = m['texture']; p = ROOT/'tool_source'/tool/f'{t}.png'
        im = Image.open(p).convert('RGBA')
        if im.width*im.height < 16*64 and t.endswith('_0'): continue   # handle / shaft strips stay as they are
        key = f'{tool}__{t}'
        if key in srcs: continue
        srcs[key] = (tool, t, im)
        jobs.append((key, im, WRAP.get(m['mapper']['wrapU'], 'GX_CLAMP'), WRAP.get(m['mapper']['wrapV'], 'GX_CLAMP')))
W.mkdir(exist_ok=True)
res = upscale_all(jobs)
for key, (tool, t, im) in srcs.items():
    r = res[key]
    g = np.asarray(im.convert('RGB')).astype(float)
    h = np.asarray(r.convert('RGB').resize(im.size, Image.BOX)).astype(float)
    a = np.asarray(im.getchannel('A')) > 0
    err = np.abs(g-h).mean(2)[a].mean() if a.any() else 0.0   # only texels the canopy shows
    if err > 8.0:   # ESR drifted from the art (grid patterns): EPX 4x keeps the pattern, edges rounded, lightly softened
        import scalenx
        r = Image.fromarray(scalenx.scale4x(np.asarray(im))).filter(ImageFilter.GaussianBlur(0.6)); how = 'epx'
    else: how = 'esr'
    out = ROOT/'tool_source_hd'/tool; out.mkdir(parents=True, exist_ok=True)
    r.save(out/f'{t}.png'); im.save(W/f'{key}_src.png'); r.save(W/f'{key}_hd.png')
    print(tool, t, im.size, '->', r.size, how, round(float(err), 2))
