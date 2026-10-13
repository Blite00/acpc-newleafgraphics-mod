/* New Leaf UI drawing. The art is New Leaf's own, rendered from its 3DS layouts at NLUI_PX texels per
 * GameCube pixel; see asset_import_work/nl_ui_survey/gen_nlui.py. PC_NL_UI=0 restores the GameCube UI. */

#include "pc_nl_ui.h"
#include "pc_nl_ui_data.h"
#include "pc_nl_ui_internal.h"

#include "libforest/gbi_extensions.h"
#include "graph.h"
#include <stdlib.h>
#include <string.h>

extern void pc_gx_texture_invalidate_image(void* p);

int pc_nlui_enabled(void) {
    static int enabled = -1;
    if (enabled < 0) {
        const char* e = getenv("PC_NL_UI");
        enabled = !(e != NULL && e[0] == '0');
    }
    return enabled;
}

/* ---- quads ---- */
GRAPH* nlui_graph;   /* per-frame vertex memory comes from the graph being built */
f32 nlui_unit = 16.0f; /* model units per pixel in the caller's matrix space */

Vtx* nlui_alloc_quad(void) {
    return (Vtx*)GRAPH_ALLOC_TYPE(nlui_graph, Vtx, 4);
}

void nlui_set_v(Vtx* v, f32 x, f32 y, f32 s, f32 t) {
    v->v.ob[0] = (s16)(x * nlui_unit);
    v->v.ob[1] = (s16)(y * nlui_unit);
    v->v.ob[2] = 0;
    v->v.flag = 0;
    v->v.tc[0] = (s16)(s * 32.0f);
    v->v.tc[1] = (s16)(t * 32.0f);
    v->v.cn[0] = v->v.cn[1] = v->v.cn[2] = v->v.cn[3] = 255;
}

/* rectangle in model pixels (y up), texture texels s0..s1, t0..t1 (t down) */
Gfx* nlui_quad(Gfx* g, f32 x0, f32 y0, f32 x1, f32 y1, f32 s0, f32 t0, f32 s1, f32 t1) {
    Vtx* v = nlui_alloc_quad();
    nlui_set_v(&v[0], x0, y1, s0, t0);
    nlui_set_v(&v[1], x1, y1, s1, t0);
    nlui_set_v(&v[2], x1, y0, s1, t1);
    nlui_set_v(&v[3], x0, y0, s0, t1);
    gSPVertex(g++, v, 4, 0);
    gSP2Triangles(g++, 0, 2, 1, 0, 0, 3, 2, 0);
    return g;
}

Gfx* nlui_mode(Gfx* g) {
    gDPPipeSync(g++);
    gSPClearGeometryMode(g++, G_ZBUFFER | G_SHADE | G_CULL_BOTH | G_FOG | G_LIGHTING | G_TEXTURE_GEN | G_TEXTURE_GEN_LINEAR);
    gDPSetOtherMode(g++,
                    G_AD_DISABLE | G_CD_MAGICSQ | G_CK_NONE | G_TC_FILT | G_TF_BILERP | G_TT_NONE | G_TL_TILE |
                        G_TD_CLAMP | G_TP_PERSP | G_CYC_1CYCLE | G_PM_NPRIMITIVE,
                    G_AC_NONE | G_ZS_PRIM | G_RM_XLU_SURF | G_RM_XLU_SURF2);
    gSPTexture(g++, 0, 0, 0, G_TX_RENDERTILE, G_ON);
    return g;
}

Gfx* nlui_tex(Gfx* g, int fmt, int siz, int w, int h, void* tex) {
    /* the run-time macro takes (height, width): see gDPSetTextureImage_Dolphin in gbi_extensions.h */
    gDPSetTextureImage_Dolphin(g++, fmt, siz, h, w, tex);
    gDPSetTile_Dolphin(g, G_DOLPHIN_TLUT_DEFAULT_MODE, 0, 0, GX_CLAMP, GX_CLAMP, 0, 0);
    g->words.w1 = 0;
    g++;
    return g;
}

/* ---- dialogue window ---- */
#define MSG_BOX_CX 4.0f
#define MSG_BOX_CY 0.0f

Gfx* pc_nlui_msg_box(GRAPH* graph, Gfx* g, int alpha) {
    nlui_graph = graph;
    nlui_unit = 16.0f;
    f32 hw = NLUI_MSG_BOX_W_PX * 0.5f, hh = NLUI_MSG_BOX_H_PX * 0.5f;
    g = nlui_mode(g);
    gDPSetCombineLERP(g++, 0, 0, 0, TEXEL0, TEXEL0, 0, PRIMITIVE, 0, 0, 0, 0, TEXEL0, TEXEL0, 0, PRIMITIVE, 0);
    gDPSetPrimColor(g++, 0, 255, 255, 255, 255, alpha);
    g = nlui_tex(g, G_IM_FMT_RGBA, G_IM_SIZ_32b, NLUI_MSG_BOX_TW, NLUI_MSG_BOX_TH, nlui_msg_box_tex);
    g = nlui_quad(g, MSG_BOX_CX - hw, MSG_BOX_CY - hh, MSG_BOX_CX + hw, MSG_BOX_CY + hh, 0, 0, NLUI_MSG_BOX_IW,
                  NLUI_MSG_BOX_IH);
    return g;
}

/* NL name tag: checked pill tinted with the speaker's GameCube plate colour, sized to the name.
 * text_x is the name's left edge in window pixels, text_w its width. */
Gfx* pc_nlui_msg_plate(GRAPH* graph, Gfx* g, f32 text_x, f32 text_w, rgba_t* color) {
    nlui_graph = graph;
    nlui_unit = 16.0f;
    f32 h = NLUI_MSG_PLATE_H_PX, cap = h * 0.6f;
    f32 w = text_w + 18.0f;
    f32 x0, x1, y0 = 48.0f - h * 0.5f, y1 = 48.0f + h * 0.5f;
    f32 tcap = cap * NLUI_PX, tw = NLUI_MSG_PLATE_IW, th = NLUI_MSG_PLATE_IH;
    if (w < NLUI_MSG_PLATE_W_PX * 0.75f) w = NLUI_MSG_PLATE_W_PX * 0.75f;
    x0 = text_x + text_w * 0.5f - w * 0.5f;
    x1 = x0 + w;
    g = nlui_mode(g);
    /* NL material: lerp(plate colour, cream) by the texture's luminance */
    gDPSetCombineLERP(g++, PRIMITIVE, ENVIRONMENT, TEXEL0, ENVIRONMENT, TEXEL0, 0, PRIMITIVE, 0, PRIMITIVE, ENVIRONMENT,
                      TEXEL0, ENVIRONMENT, TEXEL0, 0, PRIMITIVE, 0);
    gDPSetPrimColor(g++, 0, 255, 255, 255, 225, 255);
    gDPSetEnvColor(g++, color->r, color->g, color->b, 255);
    g = nlui_tex(g, G_IM_FMT_IA, G_IM_SIZ_16b, NLUI_MSG_PLATE_TW, NLUI_MSG_PLATE_TH, nlui_msg_plate_tex);
    g = nlui_quad(g, x0, y0, x0 + cap, y1, 0, 0, tcap, th);
    g = nlui_quad(g, x0 + cap, y0, x1 - cap, y1, tcap, 0, tw - tcap, th);
    g = nlui_quad(g, x1 - cap, y0, x1, y1, tw - tcap, 0, tw, th);
    return g;
}

Gfx* pc_nlui_msg_arrow(GRAPH* graph, Gfx* g, int alpha) {
    nlui_graph = graph;
    nlui_unit = 16.0f;
    f32 w = NLUI_MSG_ARROW_W_PX, h = NLUI_MSG_ARROW_H_PX;
    f32 x = MSG_BOX_CX + 112.0f, y = MSG_BOX_CY - 30.0f;
    g = nlui_mode(g);
    gDPSetCombineLERP(g++, 0, 0, 0, TEXEL0, TEXEL0, 0, PRIMITIVE, 0, 0, 0, 0, TEXEL0, TEXEL0, 0, PRIMITIVE, 0);
    gDPSetPrimColor(g++, 0, 255, 255, 255, 255, alpha);
    g = nlui_tex(g, G_IM_FMT_RGBA, G_IM_SIZ_32b, NLUI_MSG_ARROW_TW, NLUI_MSG_ARROW_TH, nlui_msg_arrow_tex);
    g = nlui_quad(g, x - w * 0.5f, y - h * 0.5f, x + w * 0.5f, y + h * 0.5f, 0, 0, NLUI_MSG_ARROW_IW, NLUI_MSG_ARROW_IH);
    return g;
}

void pc_nlui_msg_text_color(rgba_t* out, const rgba_t* in) {
    int sum = in->r + in->g + in->b;
    if (sum < 240) { /* GameCube body text (50,60,50) and other near-blacks */
        out->r = out->g = out->b = 255;
    } else { /* keep the hue, lift it so it reads on the dark window */
        out->r = (u8)(255 - (255 - in->r) * 45 / 100);
        out->g = (u8)(255 - (255 - in->g) * 45 / 100);
        out->b = (u8)(255 - (255 - in->b) * 45 / 100);
    }
    out->a = in->a;
}

/* ---- choice window ---- */

/* NL choice window w x h pixels centred on the origin, cut from the pre-rendered window without stretching.
 * sx/sy undo the GameCube display-scale matrix the window body is drawn under. */
Gfx* pc_nlui_choice_box(GRAPH* graph, Gfx* g, f32 w, f32 h, f32 sx, f32 sy, int alpha) {
    return pc_nlui_choice_rect(graph, g, -w * 0.5f, -h * 0.5f, w * 0.5f, h * 0.5f, sx, sy, alpha);
}

/* NL choice window over the rectangle x0..x1, y0..y1 (pixels, y up, in the unscaled window space) */
Gfx* pc_nlui_choice_rect(GRAPH* graph, Gfx* g, f32 rx0, f32 ry0, f32 rx1, f32 ry1, f32 sx, f32 sy, int alpha) {
    f32 w = rx1 - rx0, h = ry1 - ry0, cx = (rx0 + rx1) * 0.5f, cy = (ry0 + ry1) * 0.5f;
    f32 c = NLUI_CHOICE_CAP_PX, ct = c * NLUI_PX;
    f32 iw = NLUI_CHOICE_WIN_IW, ih = NLUI_CHOICE_WIN_IH;
    f32 x0, x1, y0, y1, xa, xb, ya, yb, mw, mh;
    nlui_graph = graph;
    nlui_unit = 16.0f;
    if (sx < 0.01f || sy < 0.01f) return g;
    if (w > NLUI_CHOICE_WIN_W_PX) w = NLUI_CHOICE_WIN_W_PX;
    if (h > NLUI_CHOICE_WIN_H_PX) h = NLUI_CHOICE_WIN_H_PX;
    if (w < 2 * c + 1) w = 2 * c + 1;
    if (h < 2 * c + 1) h = 2 * c + 1;
    mw = (w - 2 * c) * NLUI_PX;
    mh = (h - 2 * c) * NLUI_PX;
    x0 = (cx - w * 0.5f) / sx; x1 = (cx + w * 0.5f) / sx; xa = (cx - w * 0.5f + c) / sx; xb = (cx + w * 0.5f - c) / sx;
    y1 = (cy + h * 0.5f) / sy; y0 = (cy - h * 0.5f) / sy; ya = (cy + h * 0.5f - c) / sy; yb = (cy - h * 0.5f + c) / sy;
    g = nlui_mode(g);
    gDPSetCombineLERP(g++, 0, 0, 0, TEXEL0, TEXEL0, 0, PRIMITIVE, 0, 0, 0, 0, TEXEL0, TEXEL0, 0, PRIMITIVE, 0);
    gDPSetPrimColor(g++, 0, 255, 255, 255, 255, alpha);
    g = nlui_tex(g, G_IM_FMT_RGBA, G_IM_SIZ_32b, NLUI_CHOICE_WIN_TW, NLUI_CHOICE_WIN_TH, nlui_choice_win_tex);
    /* corners */
    g = nlui_quad(g, x0, ya, xa, y1, 0, 0, ct, ct);
    g = nlui_quad(g, xb, ya, x1, y1, iw - ct, 0, iw, ct);
    g = nlui_quad(g, x0, y0, xa, yb, 0, ih - ct, ct, ih);
    g = nlui_quad(g, xb, y0, x1, yb, iw - ct, ih - ct, iw, ih);
    /* edges and middle: same-size pieces of the texture, so the dot pattern is never stretched */
    g = nlui_quad(g, xa, ya, xb, y1, ct, 0, ct + mw, ct);
    g = nlui_quad(g, xa, y0, xb, yb, iw - ct - mw, ih - ct, iw - ct, ih);
    g = nlui_quad(g, x0, yb, xa, ya, 0, ct, ct, ct + mh);
    g = nlui_quad(g, xb, yb, x1, ya, iw - ct, ih - ct - mh, iw, ih - ct);
    g = nlui_quad(g, xa, yb, xb, ya, ct, ct, ct + mw, ct + mh);
    return g;
}

/* in the choice font space: x, y are the GameCube text position (screen pixels, y down) */
Gfx* pc_nlui_choice_cursor(GRAPH* graph, Gfx* g, f32 x, f32 y) {
    f32 w = NLUI_CHOICE_CURSOR_W_PX, h = NLUI_CHOICE_CURSOR_H_PX;
    f32 cx = x - 9.0f - 160.0f, cy = 120.0f - (y + 8.0f);
    nlui_graph = graph;
    nlui_unit = 16.0f;
    g = nlui_mode(g);
    gDPSetCombineLERP(g++, 0, 0, 0, TEXEL0, 0, 0, 0, TEXEL0, 0, 0, 0, TEXEL0, 0, 0, 0, TEXEL0);
    g = nlui_tex(g, G_IM_FMT_RGBA, G_IM_SIZ_32b, NLUI_CHOICE_CURSOR_TW, NLUI_CHOICE_CURSOR_TH, nlui_choice_cursor_tex);
    g = nlui_quad(g, cx - w * 0.5f, cy - h * 0.5f, cx + w * 0.5f, cy + h * 0.5f, 0, 0, NLUI_CHOICE_CURSOR_IW,
                  NLUI_CHOICE_CURSOR_IH);
    return g;
}

/* NL orange underline under an option */
Gfx* pc_nlui_choice_underline(GRAPH* graph, Gfx* g, f32 x, f32 y, f32 w) {
    f32 x0 = x - 2.0f - 160.0f, x1 = x + w + 4.0f - 160.0f, yb = 120.0f - (y + 15.0f);
    nlui_graph = graph;
    nlui_unit = 16.0f;
    g = nlui_mode(g);
    gSPTexture(g++, 0, 0, 0, G_TX_RENDERTILE, G_OFF);
    gDPSetCombineLERP(g++, 0, 0, 0, PRIMITIVE, 0, 0, 0, PRIMITIVE, 0, 0, 0, PRIMITIVE, 0, 0, 0, PRIMITIVE);
    gDPSetPrimColor(g++, 0, 255, 255, 173, 33, 255);
    g = nlui_quad(g, x0, yb - 1.0f, x1, yb, 0, 0, 0, 0);
    return g;
}

/* ---- item name tag ---- */

/* NL item balloon, w x h pixels centred on the origin; drawn in the tag's pixel-unit matrix space */
Gfx* pc_nlui_tag_balloon(GRAPH* graph, Gfx* g, f32 w, f32 h) {
    f32 cap = NLUI_TAG_CAP_PX * h / NLUI_TAG_BALLOON_H_PX, ct = NLUI_TAG_CAP_PX * NLUI_PX;
    f32 iw = NLUI_TAG_BALLOON_IW, ih = NLUI_TAG_BALLOON_IH;
    f32 x0, x1;
    nlui_graph = graph;
    nlui_unit = 1.0f;
    if (w < 2 * cap) w = 2 * cap;
    x0 = -w * 0.5f; x1 = w * 0.5f;
    g = nlui_mode(g);
    gDPSetCombineLERP(g++, 0, 0, 0, TEXEL0, 0, 0, 0, TEXEL0, 0, 0, 0, TEXEL0, 0, 0, 0, TEXEL0);
    g = nlui_tex(g, G_IM_FMT_RGBA, G_IM_SIZ_32b, NLUI_TAG_BALLOON_TW, NLUI_TAG_BALLOON_TH, nlui_tag_balloon_tex);
    g = nlui_quad(g, x0, -h * 0.5f, x0 + cap, h * 0.5f, 0, 0, ct, ih);
    g = nlui_quad(g, x0 + cap, -h * 0.5f, x1 - cap, h * 0.5f, ct, 0, iw - ct, ih);
    g = nlui_quad(g, x1 - cap, -h * 0.5f, x1, h * 0.5f, iw - ct, 0, iw, ih);
    return g;
}

/* the three NL bubbles with their tip at the origin; mirror = 1 points them right instead of left */
Gfx* pc_nlui_tag_tail(GRAPH* graph, Gfx* g, int mirror) {
    f32 w = NLUI_TAG_TAIL_W_PX, h = NLUI_TAG_TAIL_H_PX;
    nlui_graph = graph;
    nlui_unit = 1.0f;
    g = nlui_mode(g);
    gDPSetCombineLERP(g++, 0, 0, 0, TEXEL0, 0, 0, 0, TEXEL0, 0, 0, 0, TEXEL0, 0, 0, 0, TEXEL0);
    g = nlui_tex(g, G_IM_FMT_RGBA, G_IM_SIZ_32b, NLUI_TAG_TAIL_TW, NLUI_TAG_TAIL_TH, nlui_tag_tail_tex);
    if (mirror) g = nlui_quad(g, -w, 0, 0, h, NLUI_TAG_TAIL_IW, 0, 0, NLUI_TAG_TAIL_IH);
    else g = nlui_quad(g, 0, 0, w, h, 0, 0, NLUI_TAG_TAIL_IW, NLUI_TAG_TAIL_IH);
    return g;
}
