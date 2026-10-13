"""Scale2x / Scale4x (EPX) for pixel art: keeps the exact palette and pattern, rounds diagonal edges."""
import numpy as np
def scale2x(a):
    """a: HxWxC array; edges clamp"""
    p = np.pad(a, ((1, 1), (1, 1), (0, 0)), mode='edge')
    B, D, F, H, E = p[:-2, 1:-1], p[1:-1, :-2], p[1:-1, 2:], p[2:, 1:-1], a
    eq = lambda x, y: np.all(x == y, axis=-1, keepdims=True)
    c1 = eq(B, D) & ~eq(B, F) & ~eq(D, H)
    c2 = eq(B, F) & ~eq(B, D) & ~eq(F, H)
    c3 = eq(D, H) & ~eq(D, B) & ~eq(H, F)
    c4 = eq(H, F) & ~eq(D, H) & ~eq(B, F)
    E0 = np.where(c1, D, E); E1 = np.where(c2, F, E); E2 = np.where(c3, D, E); E3 = np.where(c4, F, E)
    h, w = a.shape[:2]; out = np.zeros((h*2, w*2, a.shape[2]), a.dtype)
    out[0::2, 0::2], out[0::2, 1::2], out[1::2, 0::2], out[1::2, 1::2] = E0, E1, E2, E3
    return out
def scale4x(a): return scale2x(scale2x(a))
