/* New Leaf wooden QWERTY keyboard for the GameCube editor. The art is New Leaf's Swkbd keytops rearranged onto
 * the GameCube 10x4 key grid (asset_import_work/nl_ui_survey/gen_nlui_keyboard.py), pre-rendered twice: normal
 * keys and NL's lighter "on" keys. The cursor key, the active page key, caps and any held button's key are drawn
 * from the "on" picture. Labels are GameCube font characters. PC_NL_UI=0 restores the GameCube keyboard. */

#include "pc_nl_ui_keyboard.h"
#include "pc_nl_ui_keyboard_data.h"
#include "pc_nl_ui_internal.h"

#include "m_font.h"
#include "m_controller.h"
#include "sys_matrix.h"
#include "m_rcp.h"
#include "libforest/gbi_extensions.h"
#include <string.h>

#define KB_W NLUI_KB_W_PX
#define KB_H NLUI_KB_H_PX
/* Scaled to the GameCube keyboard panel's footprint (about x 25..295, top edge y 122), so it covers no more of
 * the letter / board paper than the GameCube keyboard did. Keyboard pixels * KB_S = screen pixels. */
#define KB_S 0.84f
#define KB_X0 (160.0f - KB_W * KB_S * 0.5f) /* keyboard top-left on the 320x240 screen */
#define KB_Y0 122.0f

typedef struct {
    f32 x0, y0, x1, y1;
} kb_rect;

static const kb_rect kb_cells[mED_COLUMNS * mED_ROWS] = NLUI_KB_CELLS;
static const kb_rect kb_bsp = NLUI_KB_BSP, kb_ok = NLUI_KB_OK, kb_cps = NLUI_KB_CPS, kb_sft = NLUI_KB_SFT,
                     kb_spc = NLUI_KB_SPC;
static const kb_rect kb_mode[mED_INPUT_MODE_NUM] = { NLUI_KB_MODE0, NLUI_KB_MODE1, NLUI_KB_MODE2 };

f32 pc_nlui_kb_top(void) {
    return KB_Y0;
}

/* ---- mouse ---- */
extern int pc_nlui_mouse_ui(float* ux, float* uy, int* left); /* pc_nl_ui_mouse.c */
#include "pc_controls.h"
#include "pc_keybindings.h"
extern void pc_nlui_mouse_show_os(int show);
extern void pc_nlui_mouse_reset(void);

static struct {
    int active;         /* the mouse moved since the keyboard opened: hand shown, OS cursor hidden */
    int inside;         /* over the game window */
    int left, left_prev;
    f32 ux, uy;         /* UI pixels, y down */
    f32 last_ux, last_uy;
    int primed;
    int hover;          /* PC_NLUI_KB_* key under the hand, or -1 */
    f32 panel_x, panel_y; /* the editor panel offset the keyboard was last drawn at */
} kb_mouse;

void pc_nlui_kb_open(void) {
    memset(&kb_mouse, 0, sizeof(kb_mouse));
    kb_mouse.hover = -1;
    pc_nlui_mouse_reset();
}

void pc_nlui_kb_close(void) {
    kb_mouse.active = 0;
    kb_mouse.hover = -1;
    pc_nlui_mouse_show_os(1);
}

static int kb_in(const kb_rect* r, f32 x, f32 y) {
    return x >= r->x0 && x < r->x1 && y >= r->y0 && y < r->y1;
}

/* key under a UI point: cell index 0..39, a PC_NLUI_KB_* special, or -1 */
static int kb_hit(f32 ux, f32 uy) {
    f32 x = (ux - KB_X0 - kb_mouse.panel_x) / KB_S, y = (uy - KB_Y0 + kb_mouse.panel_y) / KB_S;
    int i;
    for (i = 0; i < mED_COLUMNS * mED_ROWS; i++) {
        if (kb_in(&kb_cells[i], x, y)) return i;
    }
    if (kb_in(&kb_bsp, x, y)) return PC_NLUI_KB_BSP;
    if (kb_in(&kb_ok, x, y)) return PC_NLUI_KB_OK;
    if (kb_in(&kb_spc, x, y)) return PC_NLUI_KB_SPC;
    if (kb_in(&kb_cps, x, y)) return PC_NLUI_KB_CPS;
    if (kb_in(&kb_sft, x, y)) return PC_NLUI_KB_SFT;
    for (i = 0; i < mED_INPUT_MODE_NUM; i++) {
        if (kb_in(&kb_mode[i], x, y)) return PC_NLUI_KB_MODE0 + i;
    }
    return -1;
}

int pc_nlui_kb_mouse(mED_Ovl_c* ed) {
    int hit, click;
    pc_ctl_claim_mouse(); /* the keyboard handles the mouse: no click = A (pc_controls.c) */
    kb_mouse.inside = pc_nlui_mouse_ui(&kb_mouse.ux, &kb_mouse.uy, &kb_mouse.left);
    if (!kb_mouse.inside) {
        kb_mouse.left = 0;
        kb_mouse.left_prev = 0;
        kb_mouse.hover = -1;
        pc_nlui_mouse_show_os(1);
        return PC_NLUI_KB_NONE;
    }
    if (!kb_mouse.primed) { /* where the mouse already was when the keyboard opened does not count as a move */
        kb_mouse.primed = 1;
        kb_mouse.last_ux = kb_mouse.ux;
        kb_mouse.last_uy = kb_mouse.uy;
        kb_mouse.left_prev = kb_mouse.left;
    }
    click = kb_mouse.left && !kb_mouse.left_prev;
    kb_mouse.left_prev = kb_mouse.left;
    hit = kb_hit(kb_mouse.ux, kb_mouse.uy);

    if (kb_mouse.ux != kb_mouse.last_ux || kb_mouse.uy != kb_mouse.last_uy || click) {
        kb_mouse.last_ux = kb_mouse.ux;
        kb_mouse.last_uy = kb_mouse.uy;
        kb_mouse.active = 1;
        /* hovering a character key moves the key cursor there */
        if (hit >= 0 && hit < mED_COLUMNS * mED_ROWS) {
            ed->select_col = (u8)(hit % mED_COLUMNS);
            ed->select_row = (u8)(hit / mED_COLUMNS);
        }
    }
    if (kb_mouse.active) pc_nlui_mouse_show_os(0);
    kb_mouse.hover = kb_mouse.active ? hit : -1;
    if (!click || hit < 0) return PC_NLUI_KB_NONE;
    return hit < mED_COLUMNS * mED_ROWS ? PC_NLUI_KB_TYPE : hit;
}

/* NL hand cursor on top of the keyboard, in the same space as pc_nlui_kb_draw */
void pc_nlui_kb_draw_hand(GRAPH* graph) {
    f32 s = NLUI_KB_HAND_PX * KB_S, x, y; /* hand scaled with the keys */
    int pressed = kb_mouse.left;
    Gfx* g;
    if (!kb_mouse.active || !kb_mouse.inside) return;
    x = kb_mouse.ux - 160.0f - NLUI_KB_HAND_HOT_X * KB_S;   /* texture top-left, model pixels, y up */
    y = 120.0f - kb_mouse.uy + NLUI_KB_HAND_HOT_Y * KB_S;
    nlui_graph = graph;
    nlui_unit = 1.0f;
    Matrix_scale(16.0f, 16.0f, 1.0f, MTX_LOAD);

    OPEN_POLY_OPA_DISP(graph);
    g = POLY_OPA_DISP;
    gSPMatrix(g++, _Matrix_to_Mtx_new(graph), G_MTX_NOPUSH | G_MTX_LOAD | G_MTX_MODELVIEW);
    g = nlui_mode(g);
    g = nlui_tex(g, G_IM_FMT_RGBA, G_IM_SIZ_32b, NLUI_KB_HAND_TW, NLUI_KB_HAND_TH,
                 pressed ? nlui_kb_hand_c_tex : nlui_kb_hand_tex);
    /* NL's flat black shadow a few pixels lower, then the hand */
    gDPSetCombineLERP(g++, 0, 0, 0, 0, TEXEL0, 0, PRIMITIVE, 0, 0, 0, 0, 0, TEXEL0, 0, PRIMITIVE, 0);
    gDPSetPrimColor(g++, 0, 255, 0, 0, 0, 90);
    g = nlui_quad(g, x, y - s - NLUI_KB_HAND_SHADOW_DY * KB_S, x + s, y - NLUI_KB_HAND_SHADOW_DY * KB_S, 0, 0, NLUI_KB_HAND_IW,
                  NLUI_KB_HAND_IH);
    gDPPipeSync(g++);
    gDPSetCombineLERP(g++, 0, 0, 0, TEXEL0, 0, 0, 0, TEXEL0, 0, 0, 0, TEXEL0, 0, 0, 0, TEXEL0);
    g = nlui_quad(g, x, y - s, x + s, y, 0, 0, NLUI_KB_HAND_IW, NLUI_KB_HAND_IH);
    POLY_OPA_DISP = g;
    CLOSE_POLY_OPA_DISP(graph);
}

/* the "on" picture over one key; keyboard pixels -> model pixels (origin screen centre, y up) */
static Gfx* kb_on_key(Gfx* g, const kb_rect* r) {
    f32 ox = KB_X0 - 160.0f, oy = 120.0f - KB_Y0;
    return nlui_quad(g, ox + r->x0 * KB_S, oy - r->y1 * KB_S, ox + r->x1 * KB_S, oy - r->y0 * KB_S, r->x0 * NLUI_PX, r->y0 * NLUI_PX,
                     r->x1 * NLUI_PX, r->y1 * NLUI_PX);
}

/* NL orange cursor frame around the selected key */
static Gfx* kb_frame(Gfx* g, const kb_rect* r, int alpha) {
    f32 ox = KB_X0 - 160.0f, oy = 120.0f - KB_Y0, t = 1.5f;
    f32 x0 = ox + r->x0 * KB_S - 0.5f, x1 = ox + r->x1 * KB_S + 0.5f, y0 = oy - r->y1 * KB_S - 0.5f,
        y1 = oy - r->y0 * KB_S + 0.5f;
    gDPPipeSync(g++);
    gSPTexture(g++, 0, 0, 0, G_TX_RENDERTILE, G_OFF);
    gDPSetCombineLERP(g++, 0, 0, 0, PRIMITIVE, 0, 0, 0, PRIMITIVE, 0, 0, 0, PRIMITIVE, 0, 0, 0, PRIMITIVE);
    gDPSetPrimColor(g++, 0, 255, 255, 150, 30, alpha);
    g = nlui_quad(g, x0, y1 - t, x1, y1, 0, 0, 0, 0);
    g = nlui_quad(g, x0, y0, x1, y0 + t, 0, 0, 0, 0);
    g = nlui_quad(g, x0, y0 + t, x0 + t, y1 - t, 0, 0, 0, 0);
    g = nlui_quad(g, x1 - t, y0 + t, x1, y1 - t, 0, 0, 0, 0);
    return g;
}

static int kb_pulse(mED_Ovl_c* ed) {
    int s = ed->cursol_opacity_step; /* 0..35, the text cursor's blink */
    if (s > 17) s = 35 - s;
    return 150 + s * 105 / 17;
}

void pc_nlui_kb_draw(GRAPH* graph, mED_Ovl_c* ed, f32 x, f32 y) {
    int sel = ed->select_col + ed->select_row * mED_COLUMNS;
    int i;
    Gfx* g;

    kb_mouse.panel_x = x;
    kb_mouse.panel_y = y;
    nlui_graph = graph;
    nlui_unit = 1.0f; /* the matrix below makes model units pixels */
    Matrix_scale(16.0f, 16.0f, 1.0f, MTX_LOAD);
    Matrix_translate(x, y, 0.0f, MTX_MULT);

    OPEN_POLY_OPA_DISP(graph);
    g = POLY_OPA_DISP;
    gSPMatrix(g++, _Matrix_to_Mtx_new(graph), G_MTX_NOPUSH | G_MTX_LOAD | G_MTX_MODELVIEW);
    g = nlui_mode(g);
    gDPSetCombineLERP(g++, 0, 0, 0, TEXEL0, 0, 0, 0, TEXEL0, 0, 0, 0, TEXEL0, 0, 0, 0, TEXEL0);
    g = nlui_tex(g, G_IM_FMT_RGBA, G_IM_SIZ_32b, NLUI_KB_BASE_TW, NLUI_KB_BASE_TH, nlui_kb_base_tex);
    g = nlui_quad(g, KB_X0 - 160.0f, 120.0f - KB_Y0 - KB_H * KB_S, KB_X0 - 160.0f + KB_W * KB_S, 120.0f - KB_Y0, 0, 0,
                  NLUI_KB_BASE_IW, NLUI_KB_BASE_IH);

    /* keys shown "on": the cursor key, the page in use, caps, and the key of any held button */
    g = nlui_tex(g, G_IM_FMT_RGBA, G_IM_SIZ_32b, NLUI_KB_ON_TW, NLUI_KB_ON_TH, nlui_kb_on_tex);
    g = kb_on_key(g, &kb_cells[sel]);
    g = kb_on_key(g, &kb_mode[ed->input_mode < mED_INPUT_MODE_NUM ? ed->input_mode : 0]);
    if ((ed->input_mode == mED_INPUT_MODE_LETTER && ed->shift_mode == mED_SHIFT_UPPER) || chkButton(BUTTON_L)) {
        g = kb_on_key(g, &kb_cps);
    }
    if (chkButton(BUTTON_B)) g = kb_on_key(g, &kb_bsp);
    if (chkButton(BUTTON_START)) g = kb_on_key(g, &kb_ok);
    if (chkButton(BUTTON_R)) g = kb_on_key(g, &kb_spc);
    if (chkButton(BUTTON_X)) g = kb_on_key(g, &kb_sft);
    if (chkButton(BUTTON_Y)) {
        for (i = 0; i < mED_INPUT_MODE_NUM; i++) g = kb_on_key(g, &kb_mode[i]);
    }
    if (kb_mouse.hover >= mED_COLUMNS * mED_ROWS) { /* special key under the hand */
        static const kb_rect* sp[] = { &kb_bsp, &kb_ok, &kb_spc, &kb_cps, &kb_sft, &kb_mode[0], &kb_mode[1],
                                       &kb_mode[2] };
        int k = kb_mouse.hover - PC_NLUI_KB_BSP;
        if (k >= 0 && k < 8) {
            g = kb_on_key(g, sp[k]);
            g = kb_frame(g, sp[k], kb_pulse(ed));
        }
    }

    g = kb_frame(g, &kb_mode[ed->input_mode < mED_INPUT_MODE_NUM ? ed->input_mode : 0], 140); /* page in use */
    g = kb_frame(g, &kb_cells[sel], kb_pulse(ed));
    POLY_OPA_DISP = g;
    CLOSE_POLY_OPA_DISP(graph);
}

/* ---- labels ---- */

#define KB_TEXT_R 90 /* NL keytop text colour */
#define KB_TEXT_G 30
#define KB_TEXT_B 0

/* one string centred on a key rectangle (keyboard pixels), scale s */
static void kb_text(GAME* game, u8* str, int len, const kb_rect* r, f32 dx, f32 dy, f32 s, int cr, int cg, int cb,
                    int a, f32 x, f32 y) {
    f32 w, tx, ty;
    s *= KB_S;
    w = (f32)mFont_GetStringWidth(str, len, TRUE) * s;
    tx = x + KB_X0 + ((r->x0 + r->x1) * 0.5f + dx) * KB_S - w * 0.5f;
    ty = -y + KB_Y0 + ((r->y0 + r->y1) * 0.5f + dy) * KB_S - 8.0f * s;
    mFont_SetLineStrings(game, str, len, tx, ty, cr, cg, cb, a, FALSE, TRUE, s, s, mFont_MODE_POLY);
}

/* small GameCube button name in a special key's top-left corner */
static void kb_badge(GAME* game, const char* name, const kb_rect* r, f32 x, f32 y) {
    u8 buf[8];
    int n = 0;
    while (name[n] && n < 8) {
        buf[n] = (u8)name[n];
        n++;
    }
    mFont_SetLineStrings(game, buf, n, x + KB_X0 + (r->x0 + 3.0f) * KB_S, -y + KB_Y0 + (r->y0 + 1.5f) * KB_S, 255, 235, 190, 230, FALSE,
                         TRUE, 0.5f, 0.5f, mFont_MODE_POLY);
}

void pc_nlui_kb_strings(GAME* game, mED_Ovl_c* ed, const u8* codes, f32 x, f32 y) {
    static u8 s_space[] = "space";
    static u8 s_ok[] = "OK";
    static u8 s_abc[] = "abc";
    static u8 s_ABC[] = "ABC";
    static u8 s_sign[] = { CHAR_HASHTAG, '&', '@' };
    static u8 s_mark[] = { CHAR_SYMBOL_STAR, CHAR_SYMBOL_SMILE };
    static u8 s_arrow[] = { '>' };
    int sel = ed->select_col + ed->select_row * mED_COLUMNS;
    int i;

    for (i = 0; i < mED_COLUMNS * mED_ROWS; i++) {
        u8 code = codes[i];
        int on = (i == sel);
        f32 dy = on ? 1.0f : 0.0f; /* NL's pressed keytop text sits a pixel lower */

        if (code == CHAR_SPACE_3 || code == CHAR_NEW_LINE) continue; /* empty / the enter icon is in the art */
        if (code == CHAR_SPACE) {
            kb_text(game, s_space, sizeof(s_space) - 1, &kb_cells[i], 0, dy, 0.75f, 255, 245, 225, 255, x, y);
        } else {
            kb_text(game, &code, 1, &kb_cells[i], 0, dy, 1.0f, on ? 185 : KB_TEXT_R, on ? 70 : KB_TEXT_G,
                    on ? 0 : KB_TEXT_B, 255, x, y);
        }
    }

    /* special keys: START = OK, B = backspace, R = space, L = caps, X = accent swap, Y = page */
    kb_text(game, s_ok, sizeof(s_ok) - 1, &kb_ok, 4.0f, 0, 1.0f, 255, 245, 225, 255, x, y);
    /* PC key names: typing on the real keyboard (Enter / Backspace / Space / Shift), else the bound keys */
    {
        extern int g_pc_typing_mode;
        PCKeybindings* kb = &g_pc_keybindings;
        if (pc_ctl_style() != PC_CTL_STYLE_KB) { /* controller in use: its buttons */
            kb_badge(game, pc_ctl_prompt('S'), &kb_ok, x, y);
            kb_badge(game, pc_ctl_prompt('B'), &kb_bsp, x, y);
            kb_badge(game, pc_ctl_prompt('R'), &kb_spc, x, y);
            kb_badge(game, pc_ctl_prompt('L'), &kb_cps, x, y);
            kb_badge(game, pc_ctl_prompt('X'), &kb_sft, x, y);
            kb_badge(game, pc_ctl_prompt('Y'), &kb_mode[0], x, y);
        } else if (g_pc_typing_mode) {
            kb_badge(game, ed->max_line_no <= 1 ? "Enter" : "Esc", &kb_ok, x, y);
            kb_badge(game, "Bksp", &kb_bsp, x, y);
            kb_badge(game, "Space", &kb_spc, x, y);
        } else {
            kb_badge(game, pc_ctl_key_label(kb->start), &kb_ok, x, y);
            kb_badge(game, pc_ctl_key_label(kb->b2 >= 0 ? kb->b2 : kb->b), &kb_bsp, x, y);
            kb_badge(game, pc_ctl_key_label(kb->r), &kb_spc, x, y);
            kb_badge(game, pc_ctl_key_label(kb->l), &kb_cps, x, y);
            kb_badge(game, pc_ctl_key_label(kb->x), &kb_sft, x, y);
            kb_badge(game, pc_ctl_key_label(kb->y2 >= 0 ? kb->y2 : kb->y), &kb_mode[0], x, y);
        }
    }

    if (ed->exchange_code != -1 && ed->cursor_idx > 0) {
        u8 prev = ed->input_str[ed->cursor_idx - 1];
        u8 next = (u8)ed->exchange_code;
        kb_rect l = kb_sft, m = kb_sft, r = kb_sft;
        f32 third = (kb_sft.x1 - kb_sft.x0) / 3.0f;
        l.x1 = l.x0 + third + 4.0f;
        m.x0 = l.x1 - 2.0f; m.x1 = m.x0 + third - 4.0f;
        r.x0 = m.x1 - 2.0f;
        kb_text(game, &prev, 1, &l, 2.0f, 0, 1.0f, 255, 220, 190, 255, x, y);
        kb_text(game, s_arrow, 1, &m, 0, 1.0f, 0.75f, 255, 245, 225, 200, x, y);
        kb_text(game, &next, 1, &r, -2.0f, 0, 1.0f, 255, 255, 255, 255, x, y);
    }

    kb_text(game, (ed->shift_mode == mED_SHIFT_UPPER) ? s_ABC : s_abc, 3, &kb_mode[0], 0, 0, 0.75f,
            255, 245, 225, 255, x, y);
    kb_text(game, s_sign, sizeof(s_sign), &kb_mode[1], 0, 0, 0.75f, 255, 245, 225, 255, x, y);
    kb_text(game, s_mark, sizeof(s_mark), &kb_mode[2], 0, 0, 0.85f, 255, 245, 225, 255, x, y);
}
