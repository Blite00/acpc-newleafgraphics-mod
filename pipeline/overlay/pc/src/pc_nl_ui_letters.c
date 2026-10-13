/* New Leaf letter screen and bulletin board. See pc_nl_ui_letters.h. PC_NL_UI=0 restores the GameCube UI
 * (the callers only use these when pc_nlui_enabled()). */

#include "pc_nl_ui_letters.h"
#include "pc_nl_ui_letters_data.h"
#include "pc_nl_ui_internal.h"

#include "libforest/gbi_extensions.h"
#include "graph.h"
#include "sys_matrix.h"

/* ---- letter: Letter/ltr_base.bclyt (320x240, the GameCube UI space; y up, centred) ----
 * P_ltrBase_00: 256x192 at (0,14), x scale 1.1  -> x -140.8..140.8, y -82..110
 * P_ltrBaseSdw_00: same size at (3.7,9), colour (255,220,210), alpha 0.39
 * Text panes (top edges): header 98, body 74 53 32 11 -10 -31 (21 apart), footer -55; 21 high. */
#define LTR_X0 -140.8f
#define LTR_X1 140.8f
#define LTR_Y0 -82.0f
#define LTR_Y1 110.0f
#define LTR_SDW_DX 3.7f
#define LTR_SDW_DY -5.0f
/* GameCube papers span x -124..124, y -86..100 in model pixels */
#define GC_PAPER_SX (281.6f / 248.0f)
#define GC_PAPER_SY (192.0f / 186.0f)
#define GC_PAPER_TY (14.0f - 7.0f * GC_PAPER_SY)
/* NL text: GameCube 16-pixel glyphs centred in NL's 21-pixel lines */
#define NL_PITCH 21.0f
#define NL_GLYPH_OFS 2.5f
/* ruled lines (lat_letterNN_sen): one 16-pixel tile per GameCube line, the line 14 pixels into the tile at the
 * glyph bottom; stretched to NL's pitch and put under the NL lines */
#define SEN_SY (NL_PITCH / 16.0f)
/* first NL body glyph bottom: 120-74+2.5+16 = 64.5; GameCube sen tile top is model y 54 */
#define SEN_TY ((120.0f - (64.5f - 14.0f * SEN_SY)) - 54.0f * SEN_SY)

/* papers whose guide lines are printed in the paper art (no separate ruled-line model): keep GameCube line
 * positions (scaled with the paper) so text stays in the boxes / on the lines */
static int ltr_baked_lines(int paper_type) {
    return paper_type == 4 /* lat_letter05: 16x6 squares */ || paper_type == 12 /* lat_letter13: wave lines */;
}

static f32 gc_line_top(int line) {
    if (line <= 0) return 36.0f;
    if (line >= 7) return 172.0f;
    return 64.0f + 16.0f * (line - 1);
}

static f32 nl_line_top(int line) {
    if (line <= 0) return 120.0f - 98.0f + NL_GLYPH_OFS;
    if (line >= 7) return 120.0f + 55.0f + NL_GLYPH_OFS;
    return 120.0f - 74.0f + NL_PITCH * (line - 1) + NL_GLYPH_OFS;
}

f32 pc_nlui_letter_line_dy(int paper_type, int line) {
    f32 gc = gc_line_top(line);
    if (line > 7) gc += 16.0f * (line - 7); /* defensive: past the footer */
    if (ltr_baked_lines(paper_type)) {
        /* glyph centre carried through the paper's fit into the NL slot */
        f32 c = 120.0f - (gc + 8.0f);
        f32 c2 = c * GC_PAPER_SY + GC_PAPER_TY;
        return gc - ((120.0f - c2) - 8.0f);
    }
    return gc - nl_line_top(line);
}

f32 pc_nlui_letter_pitch(int paper_type) {
    return ltr_baked_lines(paper_type) ? 16.0f * GC_PAPER_SY : NL_PITCH;
}

void pc_nlui_letter_text_color(const rgba_t* gc, rgba_t* out) {
    int lum = (gc->r * 30 + gc->g * 59 + gc->b * 11) / 100;
    if (lum > 150) { /* light text on a dark paper: keep it readable */
        *out = *gc;
    } else {
        out->r = NLUI_TEXT_R;
        out->g = NLUI_TEXT_G;
        out->b = NLUI_TEXT_B;
        out->a = gc->a;
    }
}

static Gfx* flat_quad(Gfx* g, f32 x0, f32 y0, f32 x1, f32 y1, int r, int gr, int b, int a) {
    g = nlui_mode(g);
    gSPTexture(g++, 0, 0, 0, G_TX_RENDERTILE, G_OFF);
    gDPSetCombineLERP(g++, 0, 0, 0, PRIMITIVE, 0, 0, 0, PRIMITIVE, 0, 0, 0, PRIMITIVE, 0, 0, 0, PRIMITIVE);
    gDPSetPrimColor(g++, 0, 255, r, gr, b, a);
    return nlui_quad(g, x0, y0, x1, y1, 0, 0, 0, 0);
}

void pc_nlui_letter_frame(GRAPH* graph, f32 x, f32 y, Gfx* mode, Gfx* paper, Gfx* sen_mode, Gfx* sen) {
    Gfx* g;

    nlui_graph = graph;
    nlui_unit = 1.0f; /* Matrix_scale(16) below: model units are pixels */
    Matrix_scale(16.0f, 16.0f, 1.0f, MTX_LOAD);
    Matrix_translate(x, y, 140.0f, MTX_MULT);

    OPEN_DISP(graph);
    g = NOW_POLY_OPA_DISP;

    gSPMatrix(g++, _Matrix_to_Mtx_new(graph), G_MTX_NOPUSH | G_MTX_LOAD | G_MTX_MODELVIEW);
    /* P_ltrBaseSdw_00 */
    g = flat_quad(g, LTR_X0 + LTR_SDW_DX, LTR_Y0 + LTR_SDW_DY, LTR_X1 + LTR_SDW_DX, LTR_Y1 + LTR_SDW_DY, 255, 220, 210,
                  100);

    /* the selected GameCube paper in P_ltrBase_00's place */
    if (paper != NULL) {
        Matrix_push();
        Matrix_translate(0.0f, GC_PAPER_TY, 0.0f, MTX_MULT);
        Matrix_scale(GC_PAPER_SX, GC_PAPER_SY, 1.0f, MTX_MULT);
        gSPMatrix(g++, _Matrix_to_Mtx_new(graph), G_MTX_NOPUSH | G_MTX_LOAD | G_MTX_MODELVIEW);
        gSPDisplayList(g++, mode);
        gSPDisplayList(g++, paper);
        Matrix_pull();
    }

    if (sen != NULL) {
        Matrix_push();
        Matrix_translate(0.0f, SEN_TY, 0.0f, MTX_MULT);
        Matrix_scale(GC_PAPER_SX, SEN_SY, 1.0f, MTX_MULT);
        gSPMatrix(g++, _Matrix_to_Mtx_new(graph), G_MTX_NOPUSH | G_MTX_LOAD | G_MTX_MODELVIEW);
        gSPDisplayList(g++, sen_mode);
        gSPDisplayList(g++, sen);
        Matrix_pull();
    }

    SET_POLY_OPA_DISP(g);
    CLOSE_DISP(graph);
}

/* ---- notice board ---- */

static Gfx* tex_quad(Gfx* g, void* tex, int tw, int th, int iw, int ih, f32 x0, f32 y0, f32 x1, f32 y1) {
    g = nlui_mode(g);
    gDPSetCombineLERP(g++, 0, 0, 0, TEXEL0, 0, 0, 0, TEXEL0, 0, 0, 0, TEXEL0, 0, 0, 0, TEXEL0);
    g = nlui_tex(g, G_IM_FMT_RGBA, G_IM_SIZ_16b, tw, th, tex); /* RGB5A3 */
    return nlui_quad(g, x0, y0, x1, y1, 0, 0, iw, ih);
}

static void notice_draw(GRAPH* graph, f32 x, f32 y, int paper) {
    Gfx* g;

    nlui_graph = graph;
    nlui_unit = 1.0f;
    Matrix_scale(16.0f, 16.0f, 1.0f, MTX_LOAD);
    Matrix_translate(x, y, 140.0f, MTX_MULT);

    OPEN_DISP(graph);
    g = NOW_POLY_OPA_DISP;
    gSPMatrix(g++, _Matrix_to_Mtx_new(graph), G_MTX_NOPUSH | G_MTX_LOAD | G_MTX_MODELVIEW);
    if (paper) {
        g = tex_quad(g, nlui_board_paper_tex, NLUI_BOARD_PAPER_TW, NLUI_BOARD_PAPER_TH, NLUI_BOARD_PAPER_IW,
                     NLUI_BOARD_PAPER_IH, NLUI_BOARD_PAPER_X0, NLUI_BOARD_PAPER_Y0, NLUI_BOARD_PAPER_X1,
                     NLUI_BOARD_PAPER_Y1);
    } else {
        g = tex_quad(g, nlui_board_base_tex, NLUI_BOARD_BASE_TW, NLUI_BOARD_BASE_TH, NLUI_BOARD_BASE_IW,
                     NLUI_BOARD_BASE_IH, -160.0f, -120.0f, 160.0f, 120.0f);
    }
    SET_POLY_OPA_DISP(g);
    CLOSE_DISP(graph);
}

void pc_nlui_notice_board(GRAPH* graph, f32 y) {
    notice_draw(graph, 0.0f, y, 0);
}

void pc_nlui_notice_paper(GRAPH* graph, f32 x, f32 y) {
    notice_draw(graph, x, y, 1);
}
