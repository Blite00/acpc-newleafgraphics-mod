"""Shared by generate_villager_hd.py and generate_villager_fences.py: which triangles are the flat GC fences."""
FENCE_PART = {1: 't1', 2: 't3', 3: 't3', 4: 't3', 5: 't3'}

def is_fence_tri(pts):
    ys = [p[1] for p in pts]
    return not (all(abs(y-125) < 2 for y in ys) or min(ys) >= 5000)
