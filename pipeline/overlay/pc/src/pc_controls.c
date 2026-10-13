/* pc_controls.c - modern PC keyboard + mouse layer over the GameCube pad (see pc_controls.h).
 * Default keys (pc_keybindings.c): WASD move, Shift run, E/Space interact (A), F pick up (B), Tab/I pockets (Y),
 * M map (X), Enter start, Q/R page tabs (L/R), Z lights, arrow keys = C Stick, numpad = D-pad, G puts the tool away.
 * Mouse: left click = A / right click = B unless a mouse UI (pockets, keyboard) claims it; wheel cycles tools. */
#include "pc_platform.h"
#include "pc_controls.h"
#include "pc_keybindings.h"
#include <dolphin/pad.h>
#include <string.h>
#include <stdlib.h>

int g_pc_editor_end_req = 0;

static unsigned int s_frame;      /* frames (pc_ctl_frame, once per event poll); PADRead runs twice a frame */
static unsigned int s_menu_frame; /* last frame the game said a menu was open */
static int s_menu_open;
static unsigned int s_claim_frame;
static int s_claimed;
static unsigned short s_pulse;   /* buttons held for a few reads (Esc, wheel) */
static int s_pulse_reads;

static unsigned short s_hold;     /* buttons a UI holds from the mouse this frame (pattern editor: A on the canvas) */
static unsigned int s_hold_frame;

void pc_ctl_hold(unsigned short bits) {
    s_hold = bits;
    s_hold_frame = s_frame;
}

void pc_ctl_set_menu_open(int open) {
    s_menu_open = open;
    s_menu_frame = s_frame;
}

void pc_ctl_claim_mouse(void) {
    s_claimed = 1;
    s_claim_frame = s_frame;
}

int pc_ctl_menu_open(void) {
    return s_menu_open && (s_frame - s_menu_frame) <= 3; /* stale outside the play scene */
}

int pc_ctl_mouse_claimed(void) {
    return s_claimed && (s_frame - s_claim_frame) <= 3;
}

static void pulse(unsigned short bits) {
    s_pulse = bits;
    s_pulse_reads = 2; /* frames: long enough for a trigger edge, short enough not to repeat */
}

int pc_ctl_escape(void) {
    extern int g_pc_editor_active;
    if (g_pc_editor_active) {
        g_pc_editor_end_req = 1;
        return 1;
    }
    if (pc_ctl_menu_open()) {
        pulse(PAD_BUTTON_B);
        return 1;
    }
    return 0;
}

void pc_ctl_wheel(int dy) {
    if (dy == 0 || pc_ctl_mouse_claimed()) return;
    if (pc_ctl_menu_open()) {
        pulse(dy > 0 ? PAD_BUTTON_UP : PAD_BUTTON_DOWN);
    } else {
        pulse(dy > 0 ? PAD_BUTTON_LEFT : PAD_BUTTON_RIGHT); /* previous / next tool */
    }
}

void pc_ctl_frame(void) {
    static int sim = -2;
    s_frame++;
    if (sim == -2) { const char* e = getenv("PC_CTL_SIM_PAD"); sim = e ? atoi(e) : -1; } /* dev: a fake pad press at that frame */
    if (sim > 0 && (int)s_frame == sim) {
        SDL_Event ev;
        SDL_zero(ev);
        ev.type = SDL_CONTROLLERBUTTONDOWN;
        ev.cbutton.which = -1;
        ev.cbutton.button = SDL_CONTROLLER_BUTTON_GUIDE;
        pc_ctl_input_event(&ev);
    }
    if (s_pulse_reads > 0) s_pulse_reads--;
}

unsigned short pc_ctl_pad_extra(int typing) {
    unsigned short b = 0;
    if (s_hold && (s_frame - s_hold_frame) <= 1) b |= s_hold;
    if (s_pulse_reads > 0) b |= s_pulse;
    if (!typing && g_pc_window != NULL && SDL_GetMouseFocus() == g_pc_window && !pc_ctl_mouse_claimed()) {
        Uint32 m = SDL_GetMouseState(NULL, NULL);
        if (m & SDL_BUTTON(SDL_BUTTON_LEFT)) b |= PAD_BUTTON_A;
        if (pc_ctl_menu_open() && (m & SDL_BUTTON(SDL_BUTTON_RIGHT))) b |= PAD_BUTTON_B;
    }
    return b;
}

int pc_ctl_run_active(void) {
    const Uint8* keys = SDL_GetKeyboardState(NULL);
    PCInputCode c = g_pc_keybindings.run;
    if (pc_ctl_menu_open() || c < 0) return 0;
    if (c & PC_INPUT_MOUSE_BIT) return (SDL_GetMouseState(NULL, NULL) & SDL_BUTTON(c & 0xFF)) != 0;
    return keys[(SDL_Scancode)c] != 0;
}

/* ---- in-game text ---- */
#include "pc_controls_msgs.c_inc"

int pc_ctl_msg_override(int index, unsigned char* buf, int size, int cap) {
    const PCCtlMsgSet* set = &pc_ctl_msg_sets[pc_ctl_style()];
    int lo = 0, hi = set->count - 1;
    (void)size;
    while (lo <= hi) {
        int mid = (lo + hi) / 2;
        if (set->msgs[mid].index == index) {
            if (set->msgs[mid].len > cap) return -1;
            memcpy(buf, set->msgs[mid].data, set->msgs[mid].len);
            return set->msgs[mid].len;
        }
        if (set->msgs[mid].index < index) lo = mid + 1;
        else hi = mid - 1;
    }
    return -1;
}

/* ---- key names for prompts (game font: ASCII letters/digits only) ---- */
const char* pc_ctl_key_label(int code) {
    static char buf[16];
    const char* n;
    int i, j;
    if (code < 0) return "";
    if (code & PC_INPUT_MOUSE_BIT) {
        switch (code & 0xFF) {
            case SDL_BUTTON_LEFT: return "LMB";
            case SDL_BUTTON_RIGHT: return "RMB";
            default: return "MMB";
        }
    }
    switch (code) {
        case SDL_SCANCODE_RETURN: return "Enter";
        case SDL_SCANCODE_BACKSPACE: return "Bksp";
        case SDL_SCANCODE_ESCAPE: return "Esc";
        case SDL_SCANCODE_LSHIFT: case SDL_SCANCODE_RSHIFT: return "Shift";
        case SDL_SCANCODE_LCTRL: case SDL_SCANCODE_RCTRL: return "Ctrl";
        case SDL_SCANCODE_LALT: case SDL_SCANCODE_RALT: return "Alt";
        case SDL_SCANCODE_SPACE: return "Space";
    }
    n = SDL_GetScancodeName((SDL_Scancode)code);
    for (i = j = 0; n[i] && j < (int)sizeof(buf) - 1; i++) {
        char c = n[i];
        if ((c >= 'A' && c <= 'Z') || (c >= 'a' && c <= 'z') || (c >= '0' && c <= '9') || c == ' ') buf[j++] = c;
    }
    buf[j] = 0;
    return buf;
}

/* ---- dev: PC_CTL_SHOTS="<folder>:<step>,<step>,..." saves ctl_<step>.bmp when the fake mouse (PC_NLUI_FAKE_MOUSE)
 * reaches those steps, for the mouse UI tests. Inactive without the variable. */
#include "pc_gx_internal.h"
#include <stdio.h>
#include <stdlib.h>
void pc_ctl_dev_frame(void) {
    extern int pc_nlui_mouse_fake_step(void);
    static const char* spec = (const char*)1;
    static int last = -1;
    const char* p;
    char dir[256], path[300];
    int step, n, w, h, y;
    if (spec == (const char*)1) spec = getenv("PC_CTL_SHOTS");
    if (spec == NULL) return;
    step = pc_nlui_mouse_fake_step();
    if (getenv("PC_CTL_SHOTS_BY_FRAME")) step = (int)s_frame; /* dev: steps are frames, no fake mouse needed */
    if (step == last || step <= 0) return;
    last = step;
    p = strchr(spec, ':');
    if (p == NULL) return;
    n = (int)(p - spec) < 255 ? (int)(p - spec) : 255;
    memcpy(dir, spec, n);
    dir[n] = 0;
    for (p = p + 1; *p; p++) {
        if (atoi(p) == step) {
            unsigned char *px, *fl;
            SDL_Surface* s;
            SDL_GL_GetDrawableSize(g_pc_window, &w, &h);
            px = malloc((size_t)w * h * 4);
            fl = malloc((size_t)w * h * 4);
            if (px && fl) {
                glReadPixels(0, 0, w, h, GL_RGBA, GL_UNSIGNED_BYTE, px);
                for (y = 0; y < h; y++) memcpy(fl + (size_t)y * w * 4, px + (size_t)(h - 1 - y) * w * 4, (size_t)w * 4);
                s = SDL_CreateRGBSurfaceFrom(fl, w, h, 32, w * 4, 0xff, 0xff00, 0xff0000, 0xff000000);
                snprintf(path, sizeof(path), "%s/ctl_%04d.bmp", dir, step);
                if (s) { SDL_SaveBMP(s, path); SDL_FreeSurface(s); }
            }
            free(px);
            free(fl);
            break;
        }
        p = strchr(p, ',');
        if (p == NULL) break;
    }
}

/* ---- GameCube button pictures -> PC key caps (gen_control_icons.py) ---- */
#include "pc_controls_icons.c_inc"

/* every patched picture is remembered so a style change can redraw it */
static struct { const char* name; void* dst; unsigned size; } s_icon_reg[32];
static int s_icon_reg_n;

static void apply_icon(const char* name, void* dst, unsigned size) {
    extern void pc_gx_texture_invalidate_image(const void* data);
    const PCCtlIconSet* set = &pc_ctl_icon_sets[pc_ctl_style()];
    int i;
    for (i = 0; i < set->count; i++) {
        if (strcmp(set->icons[i].name, name) == 0 && set->icons[i].size == size) {
            if (set->icons[i].data) memcpy(dst, set->icons[i].data, size);
            else memset(dst, 0, size);
            pc_gx_texture_invalidate_image(dst);
            return;
        }
    }
}

void pc_ctl_patch_icon(const char* name, void* dst, unsigned size) {
    int i;
    if (getenv("PC_GC_ICONS") != NULL) return; /* dev: keep the GameCube pictures */
    for (i = 0; i < s_icon_reg_n && s_icon_reg[i].dst != dst; i++) {}
    if (i == s_icon_reg_n && s_icon_reg_n < (int)(sizeof(s_icon_reg) / sizeof(s_icon_reg[0]))) {
        s_icon_reg[i].name = name;
        s_icon_reg[i].dst = dst;
        s_icon_reg[i].size = size;
        s_icon_reg_n++;
    }
    apply_icon(name, dst, size);
}

static void repatch_icons(void) {
    int i;
    for (i = 0; i < s_icon_reg_n; i++) apply_icon(s_icon_reg[i].name, s_icon_reg[i].dst, s_icon_reg[i].size);
}

/* ---- prompt style: keyboard/mouse or the kind of controller used last (switches live) ---- */
static int s_style = -1;

static int forced_style(void) {
    static int f = -2;
    if (f == -2) {
        const char* e = getenv("PC_CTL_STYLE"); /* dev: kb / xbox / ps / nin */
        f = -1;
        if (e) f = !strcmp(e, "xbox") ? PC_CTL_STYLE_XBOX : !strcmp(e, "ps") ? PC_CTL_STYLE_PS
                 : !strcmp(e, "nin") ? PC_CTL_STYLE_NIN : PC_CTL_STYLE_KB;
    }
    return f;
}

int pc_ctl_style(void) {
    if (forced_style() >= 0) return forced_style();
    return s_style < 0 ? PC_CTL_STYLE_KB : s_style;
}

static int pad_style(SDL_JoystickID id) {
    SDL_GameController* gc = SDL_GameControllerFromInstanceID(id);
    const char* name;
    if (gc == NULL) return PC_CTL_STYLE_XBOX;
    switch (SDL_GameControllerGetType(gc)) {
        case SDL_CONTROLLER_TYPE_PS3:
        case SDL_CONTROLLER_TYPE_PS4:
        case SDL_CONTROLLER_TYPE_PS5:
            return PC_CTL_STYLE_PS;
        case SDL_CONTROLLER_TYPE_NINTENDO_SWITCH_PRO:
        case SDL_CONTROLLER_TYPE_NINTENDO_SWITCH_JOYCON_LEFT:
        case SDL_CONTROLLER_TYPE_NINTENDO_SWITCH_JOYCON_RIGHT:
        case SDL_CONTROLLER_TYPE_NINTENDO_SWITCH_JOYCON_PAIR:
            return PC_CTL_STYLE_NIN;
        default:
            break;
    }
    name = SDL_GameControllerName(gc); /* GameCube adapters and the like report no type */
    if (name && (SDL_strcasestr(name, "gamecube") || SDL_strcasestr(name, "nintendo") || SDL_strcasestr(name, "switch")))
        return PC_CTL_STYLE_NIN;
    if (name && (SDL_strcasestr(name, "playstation") || SDL_strcasestr(name, "dualshock") || SDL_strcasestr(name, "dualsense")))
        return PC_CTL_STYLE_PS;
    return PC_CTL_STYLE_XBOX; /* Xbox and generic XInput pads */
}

static void set_style(int st) {
    if (st == s_style) return;
    s_style = st;
    if (forced_style() < 0) repatch_icons();
}

void pc_ctl_input_event(const void* ev) {
    const SDL_Event* e = (const SDL_Event*)ev;
    switch (e->type) {
        case SDL_KEYDOWN:
        case SDL_MOUSEBUTTONDOWN:
        case SDL_MOUSEWHEEL:
            set_style(PC_CTL_STYLE_KB);
            break;
        case SDL_MOUSEMOTION:
            if (e->motion.xrel * e->motion.xrel + e->motion.yrel * e->motion.yrel > 16) set_style(PC_CTL_STYLE_KB);
            break;
        case SDL_CONTROLLERBUTTONDOWN:
            set_style(pad_style(e->cbutton.which));
            break;
        case SDL_CONTROLLERAXISMOTION:
            if (e->caxis.value > 16000 || e->caxis.value < -16000) set_style(pad_style(e->caxis.which));
            break;
    }
}

/* short pad button names; PlayStation shapes are game-font symbols (CHAR_CIRCLE 176, CROSS 177, SQUARE 178,
 * TRIANGLE 179, PLUS 180) */
static const char* pad_label(int code, int st) {
    if (code < 0) return "";
    if (code & PC_PAD_AXIS_BIT) {
        int left = (code & 0xFF) == SDL_CONTROLLER_AXIS_TRIGGERLEFT;
        if (st == PC_CTL_STYLE_PS) return left ? "L2" : "R2";
        if (st == PC_CTL_STYLE_NIN) return left ? "ZL" : "ZR";
        return left ? "LT" : "RT";
    }
    switch (code) {
        case SDL_CONTROLLER_BUTTON_A: return st == PC_CTL_STYLE_PS ? "\xb1" : "A";
        case SDL_CONTROLLER_BUTTON_B: return st == PC_CTL_STYLE_PS ? "\xb0" : "B";
        case SDL_CONTROLLER_BUTTON_X: return st == PC_CTL_STYLE_PS ? "\xb2" : "X";
        case SDL_CONTROLLER_BUTTON_Y: return st == PC_CTL_STYLE_PS ? "\xb3" : "Y";
        case SDL_CONTROLLER_BUTTON_START: return st == PC_CTL_STYLE_PS ? "Opt" : st == PC_CTL_STYLE_NIN ? "\xb4" : "Menu";
        case SDL_CONTROLLER_BUTTON_BACK: return st == PC_CTL_STYLE_PS ? "Share" : st == PC_CTL_STYLE_NIN ? "-" : "View";
        case SDL_CONTROLLER_BUTTON_LEFTSHOULDER: return st == PC_CTL_STYLE_PS ? "L1" : st == PC_CTL_STYLE_NIN ? "L" : "LB";
        case SDL_CONTROLLER_BUTTON_RIGHTSHOULDER: return st == PC_CTL_STYLE_PS ? "R1" : st == PC_CTL_STYLE_NIN ? "R" : "RB";
        case SDL_CONTROLLER_BUTTON_LEFTSTICK: return st == PC_CTL_STYLE_PS ? "L3" : "LS";
        case SDL_CONTROLLER_BUTTON_RIGHTSTICK: return st == PC_CTL_STYLE_PS ? "R3" : "RS";
        default: return pc_pad_code_name(code);
    }
}

const char* pc_ctl_prompt(char b) {
    int st = pc_ctl_style();
    if (st == PC_CTL_STYLE_KB) {
        PCKeybindings* k = &g_pc_keybindings;
        switch (b) {
            case 'A': return pc_ctl_key_label(k->a);
            case 'B': return pc_ctl_key_label(k->b2 >= 0 ? k->b2 : k->b);
            case 'X': return pc_ctl_key_label(k->x);
            case 'Y': return pc_ctl_key_label(k->y2 >= 0 ? k->y2 : k->y);
            case 'S': return pc_ctl_key_label(k->start);
            case 'Z': return pc_ctl_key_label(k->z);
            case 'L': return pc_ctl_key_label(k->l);
            case 'R': return pc_ctl_key_label(k->r);
        }
    } else {
        PCPadBindings* p = &g_pc_padbindings;
        switch (b) {
            case 'A': return pad_label(p->a, st);
            case 'B': return pad_label(p->b, st);
            case 'X': return pad_label(p->x, st);
            case 'Y': return pad_label(p->y, st);
            case 'S': return pad_label(p->start, st);
            case 'Z': return pad_label(p->z, st);
            case 'L': return pad_label(p->l, st);
            case 'R': return pad_label(p->r, st);
        }
    }
    return "";
}

/* the global ones (the tune editor's X / Y / R / START, the pattern editor's START, letters over the old buttons) */
void pc_ctl_patch_icons(void) {
    extern u8 onp__y_tex_rgb_ia8[], onp__y2_tex_rgb_ia8[], onp__x_tex_rgb_ia8[], onp__x2_tex_rgb_ia8[];
    extern u8 onp_win_rbutton_tex_rgb_ia8[], onp_win_rbutton2_tex_rgb_ia8[], start_tex_rgb_ia8[], start2_tex_rgb_ia8[];
    extern u8 des_win_start_tex[], x[], y[], rmoji[];
    pc_ctl_patch_icon("onp__y_tex_rgb_ia8", onp__y_tex_rgb_ia8, 0x200);
    pc_ctl_patch_icon("onp__y2_tex_rgb_ia8", onp__y2_tex_rgb_ia8, 0x200);
    pc_ctl_patch_icon("onp__x_tex_rgb_ia8", onp__x_tex_rgb_ia8, 0x200);
    pc_ctl_patch_icon("onp__x2_tex_rgb_ia8", onp__x2_tex_rgb_ia8, 0x200);
    pc_ctl_patch_icon("onp_win_rbutton_tex_rgb_ia8", onp_win_rbutton_tex_rgb_ia8, 0x200);
    pc_ctl_patch_icon("onp_win_rbutton2_tex_rgb_ia8", onp_win_rbutton2_tex_rgb_ia8, 0x200);
    pc_ctl_patch_icon("start_tex_rgb_ia8", start_tex_rgb_ia8, 0x400);
    pc_ctl_patch_icon("start2_tex_rgb_ia8", start2_tex_rgb_ia8, 0x400);
    pc_ctl_patch_icon("des_win_start_tex", des_win_start_tex, 0x100);
    pc_ctl_patch_icon("x", x, 0x80);
    pc_ctl_patch_icon("y", y, 0x80);
    pc_ctl_patch_icon("rmoji", rmoji, 0x80);
}
