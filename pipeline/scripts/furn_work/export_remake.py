"""Export /Ftr/Remake/Texture variants for given model names into furn_work/remake/<model>/<tex>.png"""
import json, subprocess, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
inv = json.load(open(ROOT/'3ds_inventory.json'))
cci = open(__import__('os').environ['ACPC_NL_ROM'], 'rb')
OUT = ROOT/'furn_work'/'remake'
def export(model):
    d = OUT/model; d.mkdir(parents=True, exist_ok=True)
    for e in inv:
        p = e['path']
        if p.startswith('/Ftr/Remake/Texture/'+model+'_'):
            n = p.split('/')[-1][:-6]
            if any(d.glob(n+'*.png')): continue
            cci.seek(e['offset']); b = d/(n+'.bcres'); b.write_bytes(cci.read(e['size']))
            subprocess.run([str(ROOT/'ExportModels.exe'), str(b), str(d)], capture_output=True)
            b.unlink()
    return sorted(d.glob('*.png'))
if __name__ == '__main__':
    for m in sys.argv[1:]: print(m, [p.name for p in export(m)])
