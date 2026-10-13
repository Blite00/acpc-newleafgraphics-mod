"""GameCube button pictures in menus -> PC key caps or controller buttons, one set per prompt style (pc_controls.c applies them after the assets load).

Same size and format as the originals (IA4 = 4-bit intensity + 4-bit alpha, GC 8x4 tiles; I4 for letter textures).
These are drawn as lerp(ENV, PRIM, intensity): intensity 1 = the button colour, 0 = dark, so the caps are light with
dark labels like the GameCube START button. Keys follow pc_keybindings.c defaults.
Output: ACGC-PC-Port/pc/src/pc_controls_icons.c_inc, preview control_icons_preview.png.
"""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
SS = 8  # supersampling
FONT = 'C:/Windows/Fonts/arialbd.ttf'
SYM = 'C:/Windows/Fonts/seguisym.ttf'


def cap(w, h, box, label, pressed=False, size=None, font=FONT):
    """intensity/alpha arrays (0..1) of one key cap inside box=(x0,y0,x1,y1) of a w x h texture"""
    W, H = w * SS, h * SS
    a = Image.new('L', (W, H), 0)
    i = Image.new('L', (W, H), 0)
    da, di = ImageDraw.Draw(a), ImageDraw.Draw(i)
    x0, y0, x1, y1 = [v * SS for v in box]
    r = 3 * SS
    lip = 0 if pressed else 2 * SS
    top = y0 + (2 * SS if pressed else 0)
    da.rounded_rectangle((x0, top, x1 - 1, y1 - 1), r, fill=255)
    di.rounded_rectangle((x0, top, x1 - 1, y1 - 1), r, fill=90)                        # outline / side
    di.rounded_rectangle((x0 + SS, top + SS, x1 - 1 - SS, y1 - 1 - SS), r - SS, fill=150)  # lip
    di.rounded_rectangle((x0 + SS, top + SS, x1 - 1 - SS, y1 - 1 - SS - lip), r - SS, fill=255)  # top face
    if label:
        fs = (size or 9) * SS
        f = ImageFont.truetype(font, fs)
        bb = di.textbbox((0, 0), label, font=f)
        cx = (x0 + x1) / 2 - (bb[0] + bb[2]) / 2
        cy = (top + SS + y1 - SS - lip) / 2 - (bb[1] + bb[3]) / 2
        di.text((cx, cy), label, font=f, fill=25)
    ia = np.asarray(i.resize((w, h), Image.LANCZOS), float) / 255
    aa = np.asarray(a.resize((w, h), Image.LANCZOS), float) / 255
    return ia, aa


def arrows(w, h, pressed=False):
    """inverted-T arrow key cluster (camera = arrow keys)"""
    I = np.zeros((h, w)); A = np.zeros((h, w))
    keys = [((11, 3, 22, 14), 'up'), ((0, 16, 11, 27), 'left'), ((11, 16, 22, 27), 'down'), ((22, 16, 32, 27), 'right')]
    for box, d in keys:
        ia, aa = cap(w, h, box, None)
        # triangle
        W, H = w * SS, h * SS
        t = Image.new('L', (W, H), 0); dt = ImageDraw.Draw(t)
        x0, y0, x1, y1 = [v * SS for v in box]
        cx, cy, s = (x0 + x1) / 2, (y0 + y1 - 2 * SS) / 2, 2.6 * SS
        pts = {'up': [(cx, cy - s), (cx - s, cy + s * 0.7), (cx + s, cy + s * 0.7)],
               'down': [(cx, cy + s), (cx - s, cy - s * 0.7), (cx + s, cy - s * 0.7)],
               'left': [(cx - s, cy), (cx + s * 0.7, cy - s), (cx + s * 0.7, cy + s)],
               'right': [(cx + s, cy), (cx - s * 0.7, cy - s), (cx - s * 0.7, cy + s)]}[d]
        dt.polygon(pts, fill=255)
        tm = np.asarray(t.resize((w, h), Image.LANCZOS), float) / 255
        ia = ia * (1 - tm) + 0.1 * tm
        I = np.where(aa > A, ia, I); A = np.maximum(A, aa)
    return I, A


def ia4(I, A):
    h, w = I.shape
    q = lambda v: np.clip(np.round(v * 15), 0, 15).astype(int)
    qi, qa = q(I), q(A)
    out = bytearray()
    for by in range(0, h, 4):
        for bx in range(0, w, 8):
            for y in range(4):
                for x in range(8):
                    out.append((qa[by + y, bx + x] << 4) | qi[by + y, bx + x])
    return bytes(out)


def i4_blank(w, h):
    return bytes(w * h // 2)


def button(w, h, box, label=None, shape=None, size=None, font=FONT, pressed=False):
    """round face button: light disc, dark outline, dark letter or PlayStation shape"""
    W, H = w * SS, h * SS
    a = Image.new('L', (W, H), 0)
    i = Image.new('L', (W, H), 0)
    da, di = ImageDraw.Draw(a), ImageDraw.Draw(i)
    x0, y0, x1, y1 = [v * SS for v in box]
    if pressed:
        y0 += SS; y1 += SS
    da.ellipse((x0, y0, x1 - 1, y1 - 1), fill=255)
    di.ellipse((x0, y0, x1 - 1, y1 - 1), fill=90)
    di.ellipse((x0 + SS, y0 + SS, x1 - 1 - SS, y1 - 1 - SS), fill=200 if pressed else 255)
    cx, cy, r = (x0 + x1) / 2, (y0 + y1) / 2, (x1 - x0) * 0.27
    lw = max(SS, int((x1 - x0) * 0.09))
    if shape == 'cross':
        di.line((cx - r, cy - r, cx + r, cy + r), fill=25, width=lw)
        di.line((cx - r, cy + r, cx + r, cy - r), fill=25, width=lw)
    elif shape == 'circle':
        di.ellipse((cx - r, cy - r, cx + r, cy + r), outline=25, width=lw)
    elif shape == 'square':
        di.rectangle((cx - r * 0.85, cy - r * 0.85, cx + r * 0.85, cy + r * 0.85), outline=25, width=lw)
    elif shape == 'triangle':
        di.polygon([(cx, cy - r), (cx - r * 1.1, cy + r * 0.75), (cx + r * 1.1, cy + r * 0.75)], outline=25, width=lw)
    elif label:
        f = ImageFont.truetype(font, (size or 9) * SS)
        bb = di.textbbox((0, 0), label, font=f)
        di.text((cx - (bb[0] + bb[2]) / 2, cy - (bb[1] + bb[3]) / 2), label, font=f, fill=25)
    return (np.asarray(i.resize((w, h), Image.LANCZOS), float) / 255,
            np.asarray(a.resize((w, h), Image.LANCZOS), float) / 255)


def stick(w, h, label):
    """analog stick seen from above: dark ring + light cap with the stick's name"""
    I1, A1 = button(w, h, (1, 1, w - 1, h - 1))
    I2, A2 = button(w, h, (7, 7, w - 7, h - 7), label, size=9)
    return np.where(A2 > 0.5, I2, I1 * 0.55), np.maximum(A1, A2)


ENTER = '↵'
MENU = '☰'
FACE = {'xbox': {'Y': ('Y', None), 'X': ('X', None)}, 'nin': {'Y': ('Y', None), 'X': ('X', None)},
        'ps': {'Y': (None, 'triangle'), 'X': (None, 'square')}}
TRIG = {'xbox': 'RT', 'ps': 'R2', 'nin': 'ZR'}
STICK = {'xbox': 'RS', 'ps': 'R3', 'nin': 'R'}
BLANK = [('x', 16, 16), ('y', 16, 16), ('rmoji', 16, 16)]  # GameCube letters drawn over the old button shapes


def build(style):
    """(name, IA4 bytes, I, A) for one prompt style (pad buttons follow the default pad bindings)"""
    out = []
    add = lambda name, I, A: out.append((name, ia4(I, A), I, A))
    for pressed, suf in ((False, ''), (True, '2')):
        if style == 'kb':
            add(f'onp__y{suf}_tex_rgb_ia8', *cap(32, 16, (2, 1, 30, 16), 'Tab', pressed))
            add(f'onp__x{suf}_tex_rgb_ia8', *cap(16, 32, (0, 8, 16, 24), 'M', pressed, 10))
            add(f'onp_win_rbutton{suf}_tex_rgb_ia8', *cap(32, 16, (8, 1, 24, 16), 'R', pressed, 10))
            add(f'start{suf}_tex_rgb_ia8', *cap(32, 32, (0, 7, 32, 26), 'Enter', pressed, 8))
            continue
        l, sh = FACE[style]['Y']
        add(f'onp__y{suf}_tex_rgb_ia8', *button(32, 16, (8, 0, 24, 16), l, sh, 10, pressed=pressed))
        l, sh = FACE[style]['X']
        add(f'onp__x{suf}_tex_rgb_ia8', *button(16, 32, (0, 8, 16, 24), l, sh, 10, pressed=pressed))
        add(f'onp_win_rbutton{suf}_tex_rgb_ia8', *cap(32, 16, (5, 1, 27, 16), TRIG[style], pressed, 9))
        if style == 'xbox':
            add(f'start{suf}_tex_rgb_ia8', *button(32, 32, (6, 6, 26, 26), MENU, None, 12, SYM, pressed))
        elif style == 'ps':
            add(f'start{suf}_tex_rgb_ia8', *cap(32, 32, (0, 9, 32, 24), 'OPTIONS', pressed, 6))
        else:
            add(f'start{suf}_tex_rgb_ia8', *button(32, 32, (6, 6, 26, 26), '+', None, 16, pressed=pressed))
    for name in ('des_win_start_tex', 'kai_sousa_button3_tex'):
        if style == 'kb': add(name, *cap(16, 16, (0, 1, 16, 16), ENTER, False, 15, SYM))
        elif style == 'xbox': add(name, *button(16, 16, (0, 0, 16, 16), MENU, None, 10, SYM))
        elif style == 'ps': add(name, *cap(16, 16, (0, 3, 16, 14), 'OPT', False, 5))
        else: add(name, *button(16, 16, (0, 0, 16, 16), '+', None, 13))
    add('ct_tex', *(arrows(32, 32) if style == 'kb' else stick(32, 32, STICK[style])))
    return out


def main():
    src = ['/* Generated by asset_import_work/pc_controls/gen_control_icons.py: GameCube button pictures -> each prompt style */',
           'typedef struct { const char* name; const u8* data; unsigned size; } PCCtlIcon;',
           'typedef struct { const PCCtlIcon* icons; int count; } PCCtlIconSet;']
    sets, tiles = [], {}
    for style in ('kb', 'xbox', 'ps', 'nin'):
        rows = []
        for name, b, I, A in build(style):
            src.append(f'static const u8 pc_ctl_icon_{style}_{name}[{len(b)}] = {{ ' + ','.join(map(str, b)) + ' };')
            rows.append(f'    {{ "{name}", pc_ctl_icon_{style}_{name}, sizeof(pc_ctl_icon_{style}_{name}) }},')
            h, w = I.shape   # preview: tinted like the game (grey body, dark label) on blue
            col = I[..., None] * np.array([215, 220, 205]) + (1 - I[..., None]) * np.array([30, 30, 40])
            px = col * A[..., None] + np.array([60, 90, 150]) * (1 - A[..., None])
            tiles.setdefault(style, []).append(Image.fromarray(px.astype('uint8'), 'RGB').resize((w * 6, h * 6), Image.NEAREST))
        for name, w, h in BLANK:
            rows.append(f'    {{ "{name}", NULL, {w * h // 2} }}, /* cleared */')
        src += [f'static const PCCtlIcon pc_ctl_icons_{style}[] = {{'] + rows + ['};']
        sets.append(f'    {{ pc_ctl_icons_{style}, {len(rows)} }},')
    src += ['static const PCCtlIconSet pc_ctl_icon_sets[PC_CTL_STYLE_COUNT] = {  /* kb, xbox, ps, nin */'] + sets + ['};']
    (ROOT / 'ACGC-PC-Port/pc/src/pc_controls_icons.c_inc').write_text('\n'.join(src) + '\n')
    W = max(sum(t.width + 6 for t in r) for r in tiles.values())
    H = sum(max(t.height for t in r) + 6 for r in tiles.values())
    sheet = Image.new('RGB', (W, H), 'white'); y = 0
    for r in tiles.values():
        x = 0
        for t in r:
            sheet.paste(t, (x, y)); x += t.width + 6
        y += max(t.height for t in r) + 6
    sheet.save(Path(__file__).parent / 'control_icons_preview.png')
    print({k: len(v) for k, v in tiles.items()}, 'icons')


if __name__ == '__main__':
    main()
