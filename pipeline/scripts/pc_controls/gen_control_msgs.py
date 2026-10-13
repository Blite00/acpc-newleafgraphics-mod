"""In-game text that names GameCube buttons, rewritten for each prompt style (pc_controls.c picks the set of the
device used last): keyboard (PC keys), Xbox, PlayStation and Nintendo controllers.

Reads chr_work/arc/message_data(.bin/_table.bin), rewrites every entry that mentions a button and writes
ACGC-PC-Port/pc/src/pc_controls_msgs.c_inc (one sorted index table per style, used by pc_ctl_msg_override).
Keys follow pc_keybindings.c defaults: A = E, Y = Tab, X = M, L/R/Z = Q/R/Z, stick = WASD, C Stick = arrow keys,
D-pad = numpad. Pads: A/B/X/Y = south/east/west/north, Z = right shoulder, L/R = triggers, START = Start/Options/+.
PlayStation shapes use the game font's own symbols (circle, cross, square, triangle).
"""
import re, struct, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'ACGC-PC-Port/tools'))
import msg_tool as mt

ARC = ROOT / 'chr_work/arc'
CROSS, CIRCLE, SQUARE, TRIANGLE = '\U0001F5D9', '○', '□', '△'   # game font 177 / 176 / 178 / 179
STYLES = {
    'kb': {'keys': {'A': 'E key', 'Y': 'Tab key', 'X': 'M key', 'B': 'F key', 'L': 'Q key', 'R': 'R key', 'Z': 'Z key'},
           'cstick': 'arrow keys', 'stick': 'WASD keys', 'dpad': 'numpad', 'plural': True},
    'xbox': {'keys': {'A': 'A Button', 'B': 'B Button', 'X': 'X Button', 'Y': 'Y Button', 'L': 'LT', 'R': 'RT', 'Z': 'RB'},
             'cstick': 'right stick', 'stick': 'left stick', 'dpad': 'D-pad', 'plural': False},
    'ps': {'keys': {'A': f'{CROSS} Button', 'B': f'{CIRCLE} Button', 'X': f'{SQUARE} Button', 'Y': f'{TRIANGLE} Button',
                    'L': 'L2 Button', 'R': 'R2 Button', 'Z': 'R1 Button'},
           'cstick': 'right stick', 'stick': 'left stick', 'dpad': 'D-pad', 'plural': False},
    'nin': {'keys': {'A': 'A Button', 'B': 'B Button', 'X': 'X Button', 'Y': 'Y Button', 'L': 'ZL Button', 'R': 'ZR Button',
                     'Z': 'R Button'},
            'cstick': 'right stick', 'stick': 'left stick', 'dpad': 'D-pad', 'plural': False},
}

# NES: quit with L + R + Z
QUIT = ("Press the <<COLORCHARS [5F 7D 9B {l:02X}]>>{L},\n"
        "the <<COLORCHARS [5F 7D 9B {r:02X}]>>{R}, and the\n"
        "<<COLORCHARS [7D 32 E1 {z:02X}]>>{Z} all at once to\n"
        "quit playing your <<COLORCHARS [32 4B E1 03]>>NES.")
QUIT_PAD = ("Press <<COLORCHARS [5F 7D 9B {l:02X}]>>{L}, <<COLORCHARS [5F 7D 9B {r:02X}]>>{R},\n"
            "and <<COLORCHARS [7D 32 E1 {z:02X}]>>{Z} all at once to\n"
            "quit playing your <<COLORCHARS [32 4B E1 03]>>NES.")


QUIT_NAMES = {'xbox': ('LT', 'RT', 'RB'), 'ps': ('L2', 'R2', 'R1'), 'nin': ('ZL', 'ZR', 'R')}


def manual(style):
    k = STYLES[style]['keys']
    if style in QUIT_NAMES: k = dict(zip('LRZ', QUIT_NAMES[style]))   # bare names keep the lines short
    t = QUIT if style == 'kb' else QUIT_PAD
    return {6069: t.format(L=k['L'], R=k['R'], Z=k['Z'], l=len(k['L']), r=len(k['R']), z=len(k['Z']))}


def subs(style):
    st = STYLES[style]
    s = {14895: [("Work that\n", "Work those\n")] if st['plural'] else [],
         14897: [("Work that\n", "Work those\n"), (" Lift it up, slow-like!", " Up, slow-like!")] if st['plural'] else [],
         5373: [("the <<COLORCHARS [50 46 28 0D]>>+ Control Pad to play?", f"the <<COLORCHARS [50 46 28 {len(st['dpad']):02X}]>>{st['dpad']} to play?"),
                ("<<COLORCHARS [4B 3C 73 0D]>>Control Stick, too!", f"<<COLORCHARS [4B 3C 73 {len(st['stick']):02X}]>>{st['stick']}, too!")]}
    return s


def entries():
    data = (ARC / 'message_data.bin').read_bytes()
    table = (ARC / 'message_data_table.bin').read_bytes()
    last = 0
    for idx in range(len(table) // 4):
        end = struct.unpack_from('>I', table, idx * 4)[0]
        if end:
            yield idx, data[last:end]
            last = end


def text_of(raw):
    s = mt.decode_entry(bytearray(raw), 0, len(raw), 0)
    return s[len('[[ENTRY 0 START]]\n'):-2]


def rewrite(idx, s, style):
    st = STYLES[style]
    man = manual(style)
    if idx in man:
        return man[idx] + s[s.index('<<MSGEND>>'):] if '<<MSGEND>>' in s else man[idx]
    for a, b in subs(style).get(idx, []):
        assert a in s, (idx, a)
        s = s.replace(a, b)

    def btn(m):
        col, cnt, k = m.group(1), m.group(2), m.group(3)
        rep = st['keys'][k]
        if col is not None:
            n = int(cnt, 16)
            n = n - len(k + ' Button') + len(rep) if n >= len(k + ' Button') else n
            return f'<<COLORCHARS [{col} {n:02X}]>>{rep}'
        return rep

    def cstick(m):
        lead = m.group(1) or ''
        if st['plural']: lead = {'that ': 'those '}.get(lead, lead)
        col = m.group(2)
        if col is not None:
            return f'{lead}<<COLORCHARS [{col} {len(st["cstick"]):02X}]>>{st["cstick"]}'
        return lead + st['cstick']
    s = re.sub(r'(that |your )?(?:<<COLORCHARS \[([0-9A-F]{2} [0-9A-F]{2} [0-9A-F]{2}) [0-9A-F]{2}\]>>)?C Sticks?', cstick, s)
    return re.sub(r'(?:<<COLORCHARS \[([0-9A-F]{2} [0-9A-F]{2} [0-9A-F]{2}) ([0-9A-F]{2})\]>>)?([ABXYZLR]) Button', btn, s)


def main():
    src = ['/* Generated by asset_import_work/pc_controls/gen_control_msgs.py: GameCube button names -> each prompt style */',
           'typedef struct { int index; int len; const u8* data; } PCCtlMsg;',
           'typedef struct { const PCCtlMsg* msgs; int count; } PCCtlMsgSet;']
    sets = []
    for style in STYLES:
        rows, n = [], 0
        for idx, raw in entries():
            s = text_of(raw)
            plain = re.sub(r'<<[^>]*>>', '', s)
            if not (re.search(r'\b[ABXYZLR] Button|Control Stick|Control Pad|C Stick', plain) or idx == 6069):
                continue
            assert bytes(mt.encode_entry(s)) == raw, idx  # round trip
            t = rewrite(idx, s, style)
            if t == s: continue   # pads: "A Button" stays as the GameCube wrote it
            left = re.sub(r'<<[^>]*>>', '', t)
            if style == 'kb' and re.search(r'Button|Control Stick|Control Pad|C Stick', left):
                print('WARNING still names a button:', idx, left[:200].encode('ascii', 'replace'))
            b = bytes(mt.encode_entry(t))
            src.append(f'static const u8 pc_ctl_msg_{style}_{idx}[{len(b)}] = {{ ' + ','.join(map(str, b)) + ' };')
            rows.append(f'    {{ {idx}, sizeof(pc_ctl_msg_{style}_{idx}), pc_ctl_msg_{style}_{idx} }},')
            n += 1
        src += [f'static const PCCtlMsg pc_ctl_msgs_{style}[] = {{'] + (rows or ['    { -1, 0, NULL },']) + ['};']
        sets.append(f'    {{ pc_ctl_msgs_{style}, {n} }},')
        print(style, n, 'messages')
    src += ['static const PCCtlMsgSet pc_ctl_msg_sets[PC_CTL_STYLE_COUNT] = {  /* kb, xbox, ps, nin */'] + sets + ['};']
    (ROOT / 'ACGC-PC-Port/pc/src/pc_controls_msgs.c_inc').write_text('\n'.join(src) + '\n')


if __name__ == '__main__':
    main()
