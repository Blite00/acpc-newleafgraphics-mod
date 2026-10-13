"""Hand-picked New Leaf textures for GC shop/museum surfaces (indices = gc_big.txt -> nl_big.txt)."""
from pathlib import Path
from PIL import Image
from install_apple import dds_rgba
W=Path(__file__).resolve().parent/'furn_work'; OUT=Path(__file__).resolve().parent.parent/'texture_pack'/'3ds_interiors'
gc=open(W/'gc_big.txt').read().split('\n'); nl=open(W/'nl_big.txt').read().split('\n')
PAIRS={}
for g in (45,56,66,67,82): PAIRS[g]=297          # plank floors
for g in (76,86,109,123): PAIRS[g]=223           # grey cobble
PAIRS[78]=143                                    # blue cobble
n=0
for g,k in PAIRS.items():
    name=Path(gc[g]).stem+'.dds'; src=Image.open(W/nl[k]) if not nl[k].startswith('nl_idr') else Image.open(W/nl[k])
    w,h=map(int,Path(gc[g]).stem.split('_')[1].split('x'))
    im=src.convert('RGBA').resize((w*2,h*2),Image.LANCZOS); (OUT/name).write_bytes(dds_rgba(im)); n+=1
print(n)
