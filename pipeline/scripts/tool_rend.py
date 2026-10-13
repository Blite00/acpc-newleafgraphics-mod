"""Tiny textured software rasterizer for the tool review sheets.
render(groups, out, yaw, pitch): groups = [(tris, tex)], tri = [(xyz, uv, normal)]*3, uv with v up (0 = bottom).
A shared camera can be passed (center, scale) so GC and NL renders line up."""
import numpy as np
from PIL import Image


def camera(groups, size=400, yaw=30, pitch=25):
    P = np.array([v[0] for tris, _ in groups for t in tris for v in t], float)
    c = (P.max(0)+P.min(0))/2
    R = rot(yaw, pitch)
    Q = (P-c)@R.T
    return c, size*0.45/max(np.abs(Q[:, :2]).max(), 1e-6)


def rot(yaw, pitch):
    a = np.radians(yaw); b = np.radians(pitch)
    Ry = np.array([[np.cos(a), 0, np.sin(a)], [0, 1, 0], [-np.sin(a), 0, np.cos(a)]])
    Rx = np.array([[1, 0, 0], [0, np.cos(b), -np.sin(b)], [0, np.sin(b), np.cos(b)]])
    return Rx@Ry


def render(groups, out=None, yaw=30, pitch=25, size=400, cam=None, bg=(120, 170, 110), light=(0.4, 0.8, 0.5)):
    R = rot(yaw, pitch)
    c, s = cam if cam is not None else camera(groups, size, yaw, pitch)
    img = np.full((size, size, 3), bg, float); zb = np.full((size, size), -1e9)
    L = np.array(light, float); L /= np.linalg.norm(L)
    for tris, tex in groups:
        T = np.asarray(tex.convert('RGBA')).astype(float); th, tw = T.shape[:2]
        for t in tris:
            q = (np.array([v[0] for v in t], float)-c)@R.T
            xs = q[:, 0]*s+size/2; ys = size/2-q[:, 1]*s; zs = q[:, 2]
            n = np.array([v[2] for v in t], float).mean(0)
            n = n@R.T; nn = np.linalg.norm(n); n = n/nn if nn else n
            sh = 0.45+0.55*abs(np.dot(n, L@R.T))
            x0, x1 = int(max(0, xs.min())), int(min(size-1, xs.max())+1); y0, y1 = int(max(0, ys.min())), int(min(size-1, ys.max())+1)
            if x1 <= x0 or y1 <= y0: continue
            X, Y = np.meshgrid(np.arange(x0, x1)+.5, np.arange(y0, y1)+.5)
            d = (ys[1]-ys[2])*(xs[0]-xs[2])+(xs[2]-xs[1])*(ys[0]-ys[2])
            if abs(d) < 1e-9: continue
            w0 = ((ys[1]-ys[2])*(X-xs[2])+(xs[2]-xs[1])*(Y-ys[2]))/d; w1 = ((ys[2]-ys[0])*(X-xs[2])+(xs[0]-xs[2])*(Y-ys[2]))/d; w2 = 1-w0-w1
            m = (w0 >= 0) & (w1 >= 0) & (w2 >= 0)
            z = w0*zs[0]+w1*zs[1]+w2*zs[2]; m &= z > zb[y0:y1, x0:x1]
            uv = np.array([v[1] for v in t], float)
            u = w0*uv[0, 0]+w1*uv[1, 0]+w2*uv[2, 0]; vv = w0*uv[0, 1]+w1*uv[1, 1]+w2*uv[2, 1]
            u = np.mod(u, 2.0); u = np.where(u > 1, 2-u, u); vv = np.mod(vv, 2.0); vv = np.where(vv > 1, 2-vv, vv)
            col = T[np.clip(((1-vv)*th).astype(int), 0, th-1), np.clip((u*tw).astype(int), 0, tw-1)]
            m &= col[..., 3] > 60
            sub = img[y0:y1, x0:x1]; sub[m] = col[..., :3][m]*sh; zb[y0:y1, x0:x1][m] = z[m]
    im = Image.fromarray(np.clip(img, 0, 255).astype(np.uint8))
    if out: im.save(out)
    return im
