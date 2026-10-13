/* pc_nl_creator.c - the intro character creator.
 *
 * Rover asks what the player looks like (after "isn't it cool / cute?"), the message window hides and this menu
 * opens: a New Leaf head on the left, gender / face / hairstyle / hair colour on the right. Closing it writes the
 * choice into the player's private data and Rover carries on.
 *
 * The chosen hairstyle and hair colour are saved in Private->unk_10A8[2] (0x80 | style) and [3] (colour); [0..1]
 * are the worn hat. pc_cc_head() hands the New Leaf head draw (pc_nl_heads.c_inc) the player's own head; with no
 * saved style it returns NULL and the face type's default head is used.
 *
 * Hair textures are painted at run time from colour-free maps (generate_nl_creator_heads.py):
 * texel = colour * G + New Leaf skin * S, alpha = A. The intro creator is on by default; PC_CREATOR=0 turns it off.
 */
#include "pc_platform.h"
#include "pc_nl_ui.h"
#include "PR/mbi.h"
#include "libultra/libultra.h"
#include "libforest/gbi_extensions.h"
#include "game.h"
#include "graph.h"
#include "main.h"
#include "m_font.h"
#include "m_rcp.h"
#include "m_common_data.h"
#include "m_controller.h"
#include "m_private.h"
#include "sys_matrix.h"
#include "jsyswrap.h"
#include "pc_text_draw.h"
#include "pc_nl_creator_heads.h"

#include <stdio.h>
#include <string.h>
#include <math.h>

#include "pc_nl_creator_msgs.c_inc"

extern Gfx pc_nlh_env[];
extern void pc_gx_texture_invalidate_image(const void* data);

#define CC_COLOURS 16
static const u8 cc_colour[CC_COLOURS][3] = {
    /* the eight the face types used before the creator (generate_nl_heads.HAIR_COLOUR) */
    { 118, 72, 40 }, { 52, 40, 38 }, { 170, 110, 60 }, { 150, 64, 40 },
    { 85, 55, 40 }, { 225, 185, 110 }, { 190, 80, 50 }, { 110, 90, 80 },
    { 34, 28, 30 }, { 232, 226, 210 }, { 130, 180, 235 }, { 55, 85, 175 },
    { 95, 160, 85 }, { 240, 145, 180 }, { 140, 90, 180 }, { 185, 30, 40 },
};
static const char* const cc_colour_name[CC_COLOURS] = {
    "Brown", "Dark brown", "Light brown", "Auburn", "Chestnut", "Blonde", "Ginger", "Ash brown",
    "Black", "Platinum", "Light blue", "Blue", "Green", "Pink", "Purple", "Red",
};

#define CC_TEXBYTES (PC_CCH_TEX * PC_CCH_TEX * 4)
#define CC_SLOTS 5 /* [sex*2 + short hair] for the player, 4 = menu preview */
static u8 cc_tex[CC_SLOTS][CC_TEXBYTES] ATTRIBUTE_ALIGN(32);
static const u8* cc_tex_map[CC_SLOTS];
static int cc_tex_colour[CC_SLOTS] = { -1, -1, -1, -1, -1 };
static Gfx cc_dl[CC_SLOTS][64];
static const PcCchHead* cc_dl_head[CC_SLOTS];

/* ---- state ---- */
static int cc_disabled = -1;
static int cc_intro = 0;   /* a train guide is on screen: Rover's creator lines are active */
static int cc_applied = 0; /* the creator set this player's look during this intro */
static int cc_open = 0;
static int cc_row, cc_sex, cc_face, cc_style, cc_col;
static int cc_frame;
static int cc_stick_latch_x, cc_stick_latch_y;

int pc_cc_enabled(void) {
    if (cc_disabled < 0) {
        extern char* getenv(const char*);
        const char* e = getenv("PC_CREATOR"); /* on by default; PC_CREATOR=0 turns it off */
        cc_disabled = e != NULL && e[0] == '0';
    }
    return !cc_disabled;
}

void pc_cc_intro_active(int on) {
    cc_intro = on;
    if (on) cc_applied = 0;
}

int pc_cc_applied(void) { return cc_applied; }
int pc_cc_is_open(void) { return cc_open; }

/* ---- texture paint ---- */
static void cc_paint(int slot, const u8* map, int colour) {
    u8* dst = cc_tex[slot];
    float k[3];
    int t, i, c;
    if (cc_tex_map[slot] == map && cc_tex_colour[slot] == colour) return;
    for (c = 0; c < 3; c++) k[c] = cc_colour[colour][c] * PC_CCH_GSCALE / 255.0f;
    for (t = 0; t < PC_CCH_TEX * PC_CCH_TEX / 16; t++) {
        const u8* m = map + t * 48;
        u8* o = dst + t * 64;
        for (i = 0; i < 16; i++) {
            float G = m[i * 3], S = m[i * 3 + 1] / 255.0f;
            int r = (int)(k[0] * G + PC_CCH_SKIN_R * S + 0.5f);
            int g = (int)(k[1] * G + PC_CCH_SKIN_G * S + 0.5f);
            int b = (int)(k[2] * G + PC_CCH_SKIN_B * S + 0.5f);
            o[i * 2] = m[i * 3 + 2];
            o[i * 2 + 1] = (u8)(r > 255 ? 255 : r);
            o[32 + i * 2] = (u8)(g > 255 ? 255 : g);
            o[32 + i * 2 + 1] = (u8)(b > 255 ? 255 : b);
        }
    }
    cc_tex_map[slot] = map;
    cc_tex_colour[slot] = colour;
    pc_gx_texture_invalidate_image(dst);
}

/* the head list, same as the heads thread's generated heads but with this slot's painted hair texture.
 * Player slots load the head joint matrix and the run-time skin colour; the preview slot gets both from the menu. */
/* Runtime GBI macros tag real PC pointers; segmented addresses must stay plain integers, or the player slots'
 * &anime_6_mdl[12] / anime_N_txt would be read as host memory. */
#define CC_TEXIMG(g, fmt, siz, h, w, a)     do { if (seg) { gDPSetTextureImage_Dolphin(g, fmt, siz, h, w, (u32)(a)); }          else { gDPSetTextureImage_Dolphin(g, fmt, siz, h, w, (void*)(a)); } } while (0)
#define CC_TLUT(g, a)     do { if (seg) { gDPLoadTLUT_Dolphin(g, 15, 16, 1, (u32)(a)); } else { gDPLoadTLUT_Dolphin(g, 15, 16, 1, (void*)(a)); } } while (0)

static Gfx* cc_build(int slot, const PcCchHead* hd, uintptr_t eye, uintptr_t mouth, uintptr_t pal) {
    Gfx* g = cc_dl[slot];
    int preview = slot == 4, seg = !preview;
    gDPPipeSync(g++);
    if (!preview) {
        gSPMatrix(g++, (u32)SEGMENT_ADDR(ANIME_6_TXT_SEG, 12 * sizeof(Mtx)), G_MTX_NOPUSH | G_MTX_LOAD | G_MTX_MODELVIEW);
        gSPDisplayList(g++, pc_nlh_env);
    }
    gDPSetPrimColor(g++, 0, 128, 255, 255, 255, 255);
    gSPLoadGeometryMode(g++, G_ZBUFFER | G_SHADE | G_CULL_BACK | (preview ? 0 : G_FOG) | G_LIGHTING | G_SHADING_SMOOTH);
    if (preview) { gDPSetRenderMode(g++, G_RM_PASS, G_RM_AA_ZB_OPA_SURF2); }
    else { gDPSetRenderMode(g++, G_RM_FOG_SHADE_A, G_RM_AA_ZB_OPA_SURF2); }
    gSPTexture(g++, 0, 0, 0, G_TX_RENDERTILE, G_ON);
    gDPSetCombineLERP(g++, TEXEL0, ENVIRONMENT, TEXEL0_ALPHA, ENVIRONMENT, 0, 0, 0, 1, COMBINED, 0, SHADE, 0, 0, 0, 0,
                      COMBINED);
    gDPSetTextureImage_Dolphin(g++, G_IM_FMT_RGBA, G_IM_SIZ_32b, PC_CCH_TEX, PC_CCH_TEX, cc_tex[slot]);
    gDPSetTile_Dolphin(g, G_DOLPHIN_TLUT_DEFAULT_MODE, 0, 0, GX_CLAMP, GX_CLAMP, 0, 0);
    g->words.w1 = 0; g++;
    gSPDisplayList(g++, hd->h);
    /* face patches in plain skin, then the eye / mouth artwork on top */
    gDPSetCombineLERP(g++, ENVIRONMENT, 0, SHADE, 0, 0, 0, 0, 1, COMBINED, 0, PRIMITIVE, 0, 0, 0, 0, COMBINED);
    gSPDisplayList(g++, hd->e);
    gSPDisplayList(g++, hd->m);
    gDPNoOpTag(g++, PC_NOOP_NL_CHAR_NOSPEC); /* face art: no specular layer (it turned the nose pink) */
    gDPSetCombineLERP(g++, TEXEL0, 0, SHADE, 0, 0, 0, 0, TEXEL0, PRIMITIVE, 0, COMBINED, 0, 0, 0, 0, COMBINED);
    if (preview) { gDPSetRenderMode(g++, G_RM_PASS, G_RM_AA_ZB_XLU_DECAL2); }
    else { gDPSetRenderMode(g++, G_RM_FOG_SHADE_A, G_RM_AA_ZB_XLU_DECAL2); }
    CC_TLUT(g++, pal);
    CC_TEXIMG(g++, G_IM_FMT_CI, G_IM_SIZ_4b, 16, 32, eye);
    gDPSetTile_Dolphin(g, G_DOLPHIN_TLUT_DEFAULT_MODE, 0, 15, GX_CLAMP, GX_CLAMP, 0, 0);
    g->words.w1 = 0; g++;
    gSPDisplayList(g++, hd->e);
    CC_TEXIMG(g++, G_IM_FMT_CI, G_IM_SIZ_4b, 16, 32, mouth);
    gDPSetTile_Dolphin(g, G_DOLPHIN_TLUT_DEFAULT_MODE, 0, 15, GX_MIRROR, GX_CLAMP, 0, 0);
    g->words.w1 = 0; g++;
    gSPDisplayList(g++, hd->m);
    if (preview) { gDPSetRenderMode(g++, G_RM_PASS, G_RM_AA_ZB_OPA_SURF2); }
    else { gDPSetRenderMode(g++, G_RM_FOG_SHADE_A, G_RM_AA_ZB_OPA_SURF2); }
    gSPEndDisplayList(g++);
    cc_dl_head[slot] = hd;
    return cc_dl[slot];
}

/* called by the New Leaf head draw: this player's own hairstyle and colour, or NULL for the face default */
Gfx* pc_cc_head(int sex, int face, int short_hair) {
    Private_c* p = Common_Get(now_private);
    int b, style, colour, slot;
    const PcCchHead* hd;
    (void)face;
    {
        static int nohead = -1; /* dev: PC_CC_NOHEAD=1 keeps the face default head */
        extern char* getenv(const char*);
        if (nohead < 0) nohead = getenv("PC_CC_NOHEAD") != NULL;
        if (nohead) return NULL;
    }
    if (p == NULL || sex < 0 || sex > 1) return NULL;
    b = p->unk_10A8[2];
    if (!(b & 0x80) || (b & 0x7F) >= PC_CCH_STYLES) return NULL;
    style = b & 0x7F;
    colour = p->unk_10A8[3] % CC_COLOURS;
    slot = sex * 2 + (short_hair ? 1 : 0);
    hd = &pc_cch_heads[sex][style][short_hair ? 1 : 0];
    {
        static int calls = 0;
        if (calls++ < 3) { printf("[CREATOR] head call sex %d short %d style %d colour %d\n", sex, short_hair, style, colour); fflush(stdout); }
    }
    cc_paint(slot, hd->map, colour);
    if (cc_dl_head[slot] != hd) cc_build(slot, hd, (uintptr_t)anime_1_txt, (uintptr_t)anime_2_txt, (uintptr_t)anime_5_txt);
    return cc_dl[slot];
}

/* ---- face textures for the preview, read from the game's face archive like the player does ---- */
static u8 cc_eye[0x100] ATTRIBUTE_ALIGN(32);
static u8 cc_mouth[0x100] ATTRIBUTE_ALIGN(32);
static u16 cc_pal[16] ATTRIBUTE_ALIGN(32);
static u8 cc_face_buf[0xE20 + 32] ATTRIBUTE_ALIGN(32);
static int cc_face_loaded = -1;

static void cc_load_face(int sex, int face) {
    int key = sex * 8 + face, i;
    u32 addr;
    if (cc_face_loaded == key) return;
    addr = JW_GetAramAddress(RESOURCE_FACE_BOY) + (u32)(face + sex * 8) * 0xE20;
    _JW_GetResourceAram(addr, cc_face_buf, 0xE20);
    memcpy(cc_eye, cc_face_buf, 0x100);
    memcpy(cc_mouth, cc_face_buf + 8 * 0x100, 0x100);
    for (i = 0; i < 16; i++) cc_pal[i] = (u16)((cc_face_buf[0xE00 + i * 2] << 8) | cc_face_buf[0xE00 + i * 2 + 1]);
    pc_gx_texture_invalidate_image(cc_eye);
    pc_gx_texture_invalidate_image(cc_mouth);
    cc_face_loaded = key;
    cc_dl_head[4] = NULL;
}

static void cc_skin(int* r, int* g, int* b) {
    u16 c = cc_pal[4];
    if (c & 0x8000) { *r = ((c >> 10) & 31) * 255 / 31; *g = ((c >> 5) & 31) * 255 / 31; *b = (c & 31) * 255 / 31; }
    else { *r = ((c >> 8) & 15) * 17; *g = ((c >> 4) & 15) * 17; *b = (c & 15) * 17; }
}

/* ---- menu ---- */
void pc_cc_open(void) {
    cc_open = 1;
    cc_row = 0;
    cc_sex = 0;
    cc_face = 0;
    cc_style = 0;
    cc_col = 0;
    cc_frame = 0;
    cc_stick_latch_x = cc_stick_latch_y = 1; /* ignore a stick already held */
}

static void cc_apply(void) {
    Private_c* p = Common_Get(now_private);
    if (p != NULL) {
        p->gender = (s8)cc_sex;
        p->face = (s8)cc_face;
        p->unk_10A8[2] = (u8)(0x80 | cc_style);
        p->unk_10A8[3] = (u8)cc_col;
    }
    cc_applied = 1;
    printf("[CREATOR] %s face %d hair %d colour %s\n", cc_sex ? "girl" : "boy", cc_face + 1, cc_style + 1,
           cc_colour_name[cc_col]);
}

#define CC_ROWS 5
static void cc_change(int d) {
    switch (cc_row) {
        case 0: cc_sex ^= 1; break;
        case 1: cc_face = (cc_face + 8 + d) % 8; break;
        case 2: cc_style = (cc_style + PC_CCH_STYLES + d) % PC_CCH_STYLES; break;
        case 3: cc_col = (cc_col + CC_COLOURS + d) % CC_COLOURS; break;
    }
}

static void cc_input(void) {
    int x = getJoystick_X(), y = getJoystick_Y();
    int up = chkTrigger(BUTTON_DUP), down = chkTrigger(BUTTON_DDOWN);
    int left = chkTrigger(BUTTON_DLEFT), right = chkTrigger(BUTTON_DRIGHT);
    if (cc_stick_latch_x) { if (x > -20 && x < 20) cc_stick_latch_x = 0; }
    else if (x <= -40) { left = 1; cc_stick_latch_x = 1; }
    else if (x >= 40) { right = 1; cc_stick_latch_x = 1; }
    if (cc_stick_latch_y) { if (y > -20 && y < 20) cc_stick_latch_y = 0; }
    else if (y >= 40) { up = 1; cc_stick_latch_y = 1; }
    else if (y <= -40) { down = 1; cc_stick_latch_y = 1; }

    if (up) cc_row = (cc_row + CC_ROWS - 1) % CC_ROWS;
    if (down) cc_row = (cc_row + 1) % CC_ROWS;
    if (left) cc_change(-1);
    if (right) cc_change(1);
    if (chkTrigger(BUTTON_A)) {
        if (cc_row == CC_ROWS - 1) { cc_apply(); cc_open = 0; }
        else if (cc_row != 0) cc_change(1);
        else cc_change(1);
    }
    if (chkTrigger(BUTTON_START)) { cc_apply(); cc_open = 0; }
    if (chkTrigger(BUTTON_B)) cc_row = CC_ROWS - 1;
}

static Gfx* cc_rect(Gfx* g, int x0, int y0, int x1, int y1, int r, int gg, int b, int a) {
    gDPPipeSync(g++);
    gDPSetOtherMode(g++,
                    G_AD_DISABLE | G_CD_MAGICSQ | G_CK_NONE | G_TC_FILT | G_TF_POINT | G_TT_NONE | G_TL_TILE |
                        G_TD_CLAMP | G_TP_NONE | G_CYC_1CYCLE | G_PM_NPRIMITIVE,
                    G_AC_NONE | G_ZS_PRIM | G_RM_XLU_SURF | G_RM_XLU_SURF2);
    gDPSetCombineMode(g++, G_CC_PRIMITIVE, G_CC_PRIMITIVE);
    gDPSetPrimColor(g++, 0, 0, r, gg, b, a);
    g = gfx_gSPTextureRectangle1(g, x0 << 2, y0 << 2, x1 << 2, y1 << 2, 0, 0, 0, 0, 0);
    return g;
}

static Lights1 cc_lights = gdSPDefLights1(110, 104, 100, 175, 170, 165, 40, 60, 90);

static void cc_draw_head(GRAPH* graph) {
    const PcCchHead* hd = &pc_cch_heads[cc_sex][cc_style][0];
    Mtx* proj = GRAPH_ALLOC_TYPE(graph, Mtx, 1);
    Mtx* mv;
    int r, g_, b;
    Gfx* g;
    s16 yaw = (s16)(sinf(cc_frame * 0.025f) * 0x1C00);

    cc_load_face(cc_sex, cc_face);
    cc_paint(4, hd->map, cc_col);
    if (cc_dl_head[4] != hd) cc_build(4, hd, (uintptr_t)cc_eye, (uintptr_t)cc_mouth, (uintptr_t)cc_pal);
    cc_skin(&r, &g_, &b);

    /* screen space, y up, the head well in front of the scene's depth */
    guOrtho(proj, 0.0f, 320.0f, 0.0f, 240.0f, 1.0f, 100000.0f, 1.0f);
    Matrix_push();
    Matrix_translate(77.0f, 240.0f - 124.0f, -400.0f, MTX_LOAD);
    Matrix_RotateY(yaw, MTX_MULT);
    Matrix_RotateZ(0x4000, MTX_MULT);              /* head bone +x = up */
    Matrix_scale(0.029f, 0.029f, 0.029f, MTX_MULT);
    Matrix_translate(-1530.0f, 0.0f, 0.0f, MTX_MULT);
    mv = _Matrix_to_Mtx_new(graph);
    Matrix_pull();

    OPEN_DISP(graph);
    g = NOW_FONT_DISP;
    gDPPipeSync(g++);
    gDPSetOtherMode(g++,
                    G_AD_DISABLE | G_CD_MAGICSQ | G_CK_NONE | G_TC_FILT | G_TF_BILERP | G_TT_RGBA16 | G_TL_TILE |
                        G_TD_CLAMP | G_TP_PERSP | G_CYC_2CYCLE | G_PM_NPRIMITIVE,
                    G_AC_NONE | G_ZS_PIXEL | G_RM_PASS | G_RM_AA_ZB_OPA_SURF2);
    gSPMatrix(g++, proj, G_MTX_PROJECTION | G_MTX_LOAD | G_MTX_NOPUSH);
    gSPMatrix(g++, mv, G_MTX_MODELVIEW | G_MTX_LOAD | G_MTX_NOPUSH);
    gSPSetLights1(g++, cc_lights);
    gDPSetEnvColor(g++, r, g_, b, 255);
    gSPDisplayList(g++, cc_dl[4]);
    gDPPipeSync(g++);
    gDPSetCycleType(g++, G_CYC_1CYCLE);
    SET_FONT_DISP(g);
    CLOSE_DISP(graph);
}

/* New Leaf look: the same dark dotted window, white shadowed text, orange underline and arrow as the New Leaf choice
 * window (pc_nl_ui.c). Window space: x right, y up, origin at the screen centre; text is in screen pixels. */
#define CC_WX(x) ((f32)(x) - 160.0f)
#define CC_WY(y) (120.0f - (f32)(y))

static void cc_text(GAME* game, const char* s, f32 x, f32 y, f32 scale) {
    pc_text_draw(game, s, x + 0.75f, y + 1.0f, 0, 0, 0, 190, scale);
    pc_text_draw(game, s, x, y, 255, 255, 255, 255, scale);
}

static void cc_text_row(GAME* game, int row, const char* label, const char* value, f32 y) {
    char buf[48];
    cc_text(game, label, 186.0f, y, 1.0f);
    if (value != NULL) {
        snprintf(buf, sizeof(buf), row == cc_row ? "< %s >" : "  %s", value);
        cc_text(game, buf, 234.0f, y, 0.9f);
    }
}

static void cc_draw(GAME* game) {
    GRAPH* graph = game->graph;
    char v[24];
    f32 y0 = 74.0f, dy = 19.0f;
    f32 ysel = y0 + dy * (cc_row == CC_ROWS - 1 ? 4 : cc_row) + (cc_row == CC_ROWS - 1 ? 5.0f : 0.0f);
    Gfx* g;

    mFont_SetMatrix(graph, mFont_MODE_FONT);
    OPEN_DISP(graph);
    g = NOW_FONT_DISP;
    g = pc_nlui_choice_rect(graph, g, CC_WX(14), CC_WY(188), CC_WX(148), CC_WY(56), 1.0f, 1.0f, 255);   /* head */
    g = pc_nlui_choice_rect(graph, g, CC_WX(156), CC_WY(188), CC_WX(310), CC_WY(56), 1.0f, 1.0f, 255); /* options */
    g = pc_nlui_choice_underline(graph, g, 186.0f, ysel, 112.0f);
    g = pc_nlui_choice_cursor(graph, g, 186.0f, ysel);
    gDPPipeSync(g++);
    SET_FONT_DISP(g);
    CLOSE_DISP(graph);
    mFont_UnSetMatrix(graph, mFont_MODE_FONT);

    cc_draw_head(graph);

    mFont_SetMatrix(graph, mFont_MODE_FONT);
    cc_text(game, "What do you look like?", 92.0f, 32.0f, 1.1f);
    cc_text_row(game, 0, "Gender", cc_sex ? "Girl" : "Boy", y0);
    snprintf(v, sizeof(v), "%d of 8", cc_face + 1);
    cc_text_row(game, 1, "Face", v, y0 + dy);
    snprintf(v, sizeof(v), "%d of %d", cc_style + 1, PC_CCH_STYLES);
    cc_text_row(game, 2, "Hair", v, y0 + dy * 2);
    cc_text_row(game, 3, "Colour", cc_colour_name[cc_col], y0 + dy * 3);
    cc_text_row(game, 4, "That's me!", NULL, y0 + dy * 4 + 5.0f);
    cc_text(game, "Up Down: pick    Left Right: change    A: OK", 48.0f, 206.0f, 0.8f);
    mFont_UnSetMatrix(graph, mFont_MODE_FONT);
}

/* run every frame by the train guide while the menu is open */
void pc_cc_update(GAME* game) {
    if (!cc_open) return;
    cc_frame++;
    if (cc_frame > 2) cc_input();
    if (cc_open && game != NULL && game->graph != NULL) cc_draw(game);
}

/* Rover's lines for the creator (called from mMsg_LoadMsgData): returns the new length, or -1 to keep the text */
int pc_cc_msg_override(int index, u8* buf, int size, int cap) {
    const u8* src = NULL;
    int n = 0;
    if (!cc_intro || !pc_cc_enabled()) return -1;
    switch (index) {
        case 0x2AD6: src = pc_cc_msg_2AD6; n = sizeof(pc_cc_msg_2AD6); break;
        case 0x2AD7: src = pc_cc_msg_2AD7; n = sizeof(pc_cc_msg_2AD7); break;
        case 0x2AD8:
        case 0x2AD9:
            if (!cc_applied || size + (int)sizeof(pc_cc_msg_prefix) > cap) return -1;
            memmove(buf + sizeof(pc_cc_msg_prefix), buf, size);
            memcpy(buf, pc_cc_msg_prefix, sizeof(pc_cc_msg_prefix));
            return size + (int)sizeof(pc_cc_msg_prefix);
        default: return -1;
    }
    if (n > cap) return -1;
    memcpy(buf, src, n);
    return n;
}
