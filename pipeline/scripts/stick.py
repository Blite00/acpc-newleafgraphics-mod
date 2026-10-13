"""stick-figure renders of GC and NL skeleton poses (front: x-y, side: z-y)"""
import numpy as np
from PIL import Image, ImageDraw
def draw(skel_list, size=300, out=None, scale=None):
    """skel_list: [(positions Nx3, parents, color)]; returns image with front + side views"""
    im = Image.new('RGB', (size*2, size), 'white'); d = ImageDraw.Draw(im)
    allp = np.concatenate([p for p, _, _ in skel_list])
    c = (allp.max(0)+allp.min(0))/2; s = scale or size*0.42/max(np.abs(allp-c).max(), 1e-6)
    for view, ox in ((0, 0), (2, size)):
        for P, par, col in skel_list:
            for i, j in enumerate(par):
                if j < 0: continue
                a = P[j]-c; b = P[i]-c
                d.line([(ox+size/2+a[view]*s*(1 if view == 0 else -1), size/2-a[1]*s), (ox+size/2+b[view]*s*(1 if view == 0 else -1), size/2-b[1]*s)], fill=col, width=3)
    if out: im.save(out)
    return im
