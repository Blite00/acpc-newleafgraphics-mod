"""Regenerate every registered furniture swap with the current generators (registry params). usage: python furn_work/regen_all.py [gc ...]"""
import json, sys, time
sys.path.insert(0, '.')
import gen_furn, gen_furn_skel as gs
r = json.load(open('furn_work/furn_registry.json'))
only = sys.argv[1:]; t0 = time.time(); fails = []
for i, (gc, e) in enumerate(list(r.items())):
    if only and gc not in only: continue
    if isinstance(e, dict) and e.get('gfx'): continue   # shop umbrellas: gen_shopumb.py
    try:
        if isinstance(e, str): gen_furn.main(gc, e)
        elif e.get('skel'): gs.main(gc, e['nl'], e.get('yaw', 0.0), e.get('tint'))
        else: gen_furn.main(gc, e['nl'], e.get('yaw', 0.0), e.get('variants'), e.get('tint'), e.get('screen'), e.get('blank'))
    except Exception as ex: fails.append((gc, repr(ex)[:150]))
    if i % 25 == 0: print(i, gc, round(time.time()-t0), flush=True)
print('FAILS', fails)
