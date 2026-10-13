"""Recolour a New Leaf texture to a GameCube texture's colours (Reinhard colour transfer in Lab, opaque and
non-dark pixels only, so outlines, eyes and shading are kept). needs_recolor() flags textures whose overall colour
differs clearly from the GC one."""
import numpy as np

def _srgb_to_lab(rgb):
    c = rgb/255.0
    c = np.where(c > 0.04045, ((c+0.055)/1.055)**2.4, c/12.92)
    M = np.array([[0.4124, 0.3576, 0.1805], [0.2126, 0.7152, 0.0722], [0.0193, 0.1192, 0.9505]])
    xyz = c @ M.T / np.array([0.95047, 1.0, 1.08883])
    f = np.where(xyz > 0.008856, np.cbrt(xyz), 7.787*xyz+16/116)
    return np.stack([116*f[..., 1]-16, 500*(f[..., 0]-f[..., 1]), 200*(f[..., 1]-f[..., 2])], -1)

def _lab_to_srgb(lab):
    fy = (lab[..., 0]+16)/116; fx = fy+lab[..., 1]/500; fz = fy-lab[..., 2]/200
    f = np.stack([fx, fy, fz], -1)
    xyz = np.where(f**3 > 0.008856, f**3, (f-16/116)/7.787)*np.array([0.95047, 1.0, 1.08883])
    M = np.array([[3.2406, -1.5372, -0.4986], [-0.9689, 1.8758, 0.0415], [0.0557, -0.2040, 1.0570]])
    c = xyz @ M.T
    c = np.where(c > 0.0031308, 1.055*np.clip(c, 0, None)**(1/2.4)-0.055, 12.92*c)
    return np.clip(c*255, 0, 255)

def _mask(a):
    lum = a[..., :3] @ np.array([0.3, 0.59, 0.11])
    return (a[..., 3] > 100) & (lum > 35)

def needs_recolor(nl, gc, threshold=22.0):
    m1, m2 = _mask(nl), _mask(gc)
    if m1.sum() < 10 or m2.sum() < 4: return False
    l1 = _srgb_to_lab(nl[..., :3][m1].astype(float)).mean(0); l2 = _srgb_to_lab(gc[..., :3][m2].astype(float)).mean(0)
    return float(np.linalg.norm((l1-l2)[1:])) > threshold          # hue/chroma difference (lightness ignored)

def recolor(nl, gc, strength=1.0):
    """nl, gc: RGBA uint8 arrays. Returns nl recoloured to gc's colour statistics."""
    out = nl.astype(float).copy()
    m1, m2 = _mask(nl), _mask(gc)
    if m1.sum() < 10 or m2.sum() < 4: return nl
    L1 = _srgb_to_lab(nl[..., :3].astype(float)); L2 = _srgb_to_lab(gc[..., :3][m2].astype(float))
    mu1, sd1 = L1[m1].mean(0), L1[m1].std(0)+1e-6; mu2, sd2 = L2.mean(0), L2.std(0)+1e-6
    sd2[1:] = np.maximum(sd2[1:], 6.0)                         # keep some colour variation from the NL detail
    T = (L1-mu1)*(sd2/sd1)+mu2
    T[..., 0] = L1[..., 0]+(mu2[0]-mu1[0])*0.5                 # keep NL shading, move overall brightness halfway
    rgb = _lab_to_srgb(T)
    w = m1[..., None]*strength
    out[..., :3] = out[..., :3]*(1-w)+rgb*w
    return np.clip(out, 0, 255).astype(np.uint8)
