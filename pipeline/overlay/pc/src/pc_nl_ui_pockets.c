/* New Leaf extras for the GameCube pocket screen; the GameCube window and layout stay as they are.
 *  - New Leaf item icons in place of the GameCube ones (pc_nlui_pk_icon, used by mSM_draw_item),
 *  - the mouse with New Leaf's hand cursor (state here, the slot logic in m_tag_ovl.c next to GameCube's),
 *  - New Leaf's item action window for the GameCube select tags,
 *  - the bell bag merge rule and its refusal balloon.
 * Art: nl_ui_survey/gen_nlui_pockets.py -> pc_nl_ui_pockets_data.c. PC_NL_UI=0 restores the GameCube screen. */

#include "pc_nl_ui_pockets.h"
#include "pc_nl_ui_pockets_data.h"
#include "pc_nl_ui_internal.h"

#include "m_name_table.h"
#include "m_common_data.h"
#include "m_font.h"
#include "m_inventory_ovl.h"
#include "pc_hat_items.h"
#include "sys_matrix.h"
#include "m_rcp.h"
#include "libforest/gbi_extensions.h"
#include <string.h>
#include "pc_controls.h"

/* ======================= item icons ======================= */
static u8* const pk_icon_tex[NLUI_PK_ICON_N] = NLUI_PK_ICON_TEXES;
static const s16 pk_icon_slot[522] = NLUI_PK_ICON_SLOT;

/* GameCube fish in aGYO order (ITM_FISH_START + n) -> New Leaf icon (icons/icn_NNN.png), -1 = keep GameCube's */
static const s16 pk_fish_icon[40] = {
    193, /* crucian carp */ 215, /* brook trout */ 196, /* carp */      197, /* koi */          205, /* catfish */
    210, /* small bass */   210, /* bass */        210, /* large bass */ 208, /* bluegill */     205, /* giant catfish */
    207, /* snakehead */    195, /* barbel steed */ 194, /* dace */      192, /* pale chub */    191, /* bitterling */
    204, /* loach */        212, /* pond smelt */  213, /* sweetfish */  214, /* cherry salmon */ 215, /* large char */
    216, /* rainbow trout */ 217, /* stringfish */ 218, /* salmon */     198, /* goldfish */     223, /* piranha */
    224, /* arowana */      206, /* eel */         203, /* goby */       221, /* angelfish */    220, /* guppy */
    199, /* pop-eyed */     254, /* coelacanth */  201, /* crawfish */   202, /* frog */         200, /* killifish */
    -1,  /* jellyfish */    239, /* sea bass */    240, /* red snapper */ 238, /* knifejaw */    227, /* arapaima */
};

/* GameCube insects in aINS order (ITM_INSECT_START + n) */
static const s16 pk_insect_icon[40] = {
    127, /* common butterfly */ 128, /* yellow */      129, /* tiger */       132, /* purple */       145, /* robust cicada */
    146, /* walker */           147, /* evening */     144, /* brown */       139, /* bee */          150, /* common dragonfly */
    149, /* red */              151, /* darner */      152, /* banded */      140, /* long locust */  141, /* migratory */
    157, /* cricket */          159, /* grasshopper */ 158, /* bell cricket */ 157, /* pine cricket */ 170, /* drone beetle */
    178, /* dynastid */         172, /* flat stag */   171, /* jewel */       166, /* longhorn */     164, /* ladybug */
    164, /* spotted ladybug */  142, /* mantis */      -1,  /* firefly */     -1,  /* cockroach */    173, /* saw stag */
    179, /* mountain beetle */  174, /* giant beetle */ 156, /* snail */      160, /* mole cricket */ 154, /* pond skater */
    163, /* bagworm */          184, /* pill bug */    188, /* spider */      153, /* ant */          185, /* mosquito */
};

/* ITM_SHELL0..7: cowrie, wentletrap, venus comb, porceletta, sand dollar, white scallop, conch, coral */
static const s16 pk_shell_icon[8] = { 265, 264, 262, 264, 266, 263, 259, 261 };

int pc_nlui_pk_icon_index(mActor_name_t item) {
    if (ITEM_IS_HAT(item)) return -1; /* the hat thread's own New Leaf icons */
    if (item >= HANIWA_START && item <= HANIWA_END) return 309;
    if (item >= FTR_DINO_START && item <= FTR_DINO_END) return 330;
    if (ITEM_IS_FTR(item)) return 0;
    if (ITEM_NAME_GET_TYPE(item) != NAME_TYPE_ITEM1) return -1;
    switch (ITEM_NAME_GET_CAT(item)) {
        case ITEM1_CAT_MONEY: /* NL bag art by amount: small, medium, big */
            return item == ITM_MONEY_30000 ? 69 : item == ITM_MONEY_10000 ? 39 : 10;
        case ITEM1_CAT_TOOL:
            if (item == ITM_NET) return 325;
            if (item == ITM_AXE) return 319;
            if (item == ITM_SHOVEL) return 317;
            if (item == ITM_ROD) return 323;
            if (item >= ITM_UMBRELLA_START && item <= ITM_MY_ORG_UMBRELLA7) return 313;
            if (item == ITM_GOLDEN_NET) return 326;
            if (item == ITM_GOLDEN_AXE) return 322;
            if (item == ITM_GOLDEN_SHOVEL) return 318;
            if (item == ITM_GOLDEN_ROD) return 324;
            if (item >= ITM_AXE_USE_1 && item <= ITM_AXE_USE_3) return 320; /* worn axes */
            if (item >= ITM_AXE_USE_4 && item <= ITM_AXE_USE_7) return 321;
            if (item >= ITM_RED_BALLOON && item <= ITM_BUNNY_O_BALLOON) return 355;
            if (item >= ITM_YELLOW_PINWHEEL && item <= ITM_FANCY_PINWHEEL) return 357;
            return -1; /* fans, paint, sickle */
        case ITEM1_CAT_FISH:
            return (item - ITM_FISH_START) < 40 ? pk_fish_icon[item - ITM_FISH_START] : -1;
        case ITEM1_CAT_INSECT:
            return (item - ITM_INSECT_START) < 40 ? pk_insect_icon[item - ITM_INSECT_START] : -1;
        case ITEM1_CAT_ETC:
            if (item >= ITM_SHELL_START && item < ITM_SHELL_END) return pk_shell_icon[item - ITM_SHELL_START];
            if (item == ITM_DUST0_EMPTY_CAN) return 255;
            if (item == ITM_DUST1_BOOT) return 256;
            if (item == ITM_DUST2_OLD_TIRE) return 257;
            if (item == ITM_FOSSIL) return 330;
            if (item == ITM_PITFALL) return 335;
            if (item == ITM_MONEY1000BELL) return 10;
            if (item == ITM_PRESENT || (item >= ITM_GOLDEN_NET_PRESENT && item <= ITM_GOLDEN_ROD_PRESENT)) return 370;
            return -1;
        case ITEM1_CAT_CARPET:
            return 308;
        case ITEM1_CAT_WALL:
            return 307;
        case ITEM1_CAT_FRUIT:
            switch (item) {
                case ITM_FOOD_APPLE: return 301;
                case ITM_FOOD_CHERRY: return 305;
                case ITM_FOOD_PEAR: return 303;
                case ITM_FOOD_PEACH: return 304;
                case ITM_FOOD_ORANGE: return 302;
                case ITM_FOOD_MUSHROOM: return 345;
                case ITM_FOOD_CANDY: return 368;
                case ITM_FOOD_COCONUT: return 306;
            }
            return -1;
        case ITEM1_CAT_PLANT:
            if (item == ITM_SAPLING) return 333;
            if (item == ITM_CEDAR_SAPLING) return 334;
            if (item >= ITM_WHITE_PANSY_BAG && item <= ITM_YELLOW_TULIP_BAG) return 332;
            return -1;
        case ITEM1_CAT_MINIDISK:
            return 310;
        case ITEM1_CAT_DUMMY:
            return 490; /* diaries */
        case ITEM1_CAT_TICKET:
            return 369;
        case ITEM1_CAT_HUKUBUKURO:
            return 427;
        /* stationery (its 1-4 sheet stacks), shirts (one icon per pattern colour) and turnips keep GameCube's */
    }
    return -1;
}

u8* pc_nlui_pk_icon(mActor_name_t item) {
    int n, s;
    if (!pc_nlui_enabled()) return NULL;
    n = pc_nlui_pk_icon_index(item);
    if (n < 0 || n >= 522) return NULL;
    s = pk_icon_slot[n];
    return s < 0 ? NULL : pk_icon_tex[s];
}

/* ======================= mouse ======================= */
extern int pc_nlui_mouse_ui(float* ux, float* uy, int* left); /* pc_nl_ui_mouse.c */
extern void pc_nlui_mouse_show_os(int show);
extern void pc_nlui_mouse_reset(void);

pc_nlui_pk_mouse_c pc_nlui_pk_mouse;
static struct {
    int primed, left_prev;
    f32 last_ux, last_uy;
} pk_ms;

void pc_nlui_pk_mouse_open(void) {
    memset(&pc_nlui_pk_mouse, 0, sizeof(pc_nlui_pk_mouse));
    memset(&pk_ms, 0, sizeof(pk_ms));
    pc_nlui_mouse_reset();
}

void pc_nlui_pk_mouse_close(void) {
    pc_nlui_pk_mouse.active = FALSE;
    pc_nlui_pk_mouse.dragging = FALSE;
    pc_nlui_mouse_show_os(1);
}

void pc_nlui_pk_mouse_update(void) {
    pc_nlui_pk_mouse_c* m = &pc_nlui_pk_mouse;
    int left = 0;
    m->press = m->release = m->moved = FALSE;
    if (!pc_nlui_enabled()) return;
    pc_ctl_claim_mouse(); /* the pockets handle the mouse: no click = A (pc_controls.c) */
    m->inside = pc_nlui_mouse_ui(&m->ux, &m->uy, &left);
    if (!m->inside) {
        if (m->down) m->release = TRUE; /* let go when the mouse leaves the window */
        m->down = FALSE;
        pk_ms.left_prev = FALSE;
        pc_nlui_mouse_show_os(1);
        return;
    }
    if (!pk_ms.primed) { /* where the mouse already was when the pockets opened does not count as a move */
        pk_ms.primed = TRUE;
        pk_ms.last_ux = m->ux;
        pk_ms.last_uy = m->uy;
        pk_ms.left_prev = left;
    }
    m->press = left && !pk_ms.left_prev;
    m->release = !left && pk_ms.left_prev;
    pk_ms.left_prev = left;
    m->down = left;
    if (m->ux != pk_ms.last_ux || m->uy != pk_ms.last_uy || m->press) {
        m->moved = m->ux != pk_ms.last_ux || m->uy != pk_ms.last_uy;
        pk_ms.last_ux = m->ux;
        pk_ms.last_uy = m->uy;
        m->active = TRUE;
    }
    if (m->press) {
        m->press_ux = m->ux;
        m->press_uy = m->uy;
    }
    if (m->press) m->press_latch = TRUE;
    if (m->release) m->release_latch = TRUE;
    pc_nlui_mouse_show_os(0); /* one cursor in the pockets: the New Leaf hand */
}

/* ======================= overlay: hand, refusal balloon ======================= */
static f32 pk_key_x, pk_key_y;
static int pk_key_holding, pk_key_set;

void pc_nlui_pk_set_key_hand(f32 x, f32 y, int holding) {
    pk_key_x = x;
    pk_key_y = y;
    pk_key_holding = holding;
    pk_key_set = TRUE;
}

int pc_nlui_pk_hand_replaces_gc(Submenu* submenu) {
    return pc_nlui_enabled() && submenu->current_menu_type == mSM_OVL_INVENTORY;
}

int pc_nlui_pk_held_item_pos(f32* x, f32* y) {
    pc_nlui_pk_mouse_c* m = &pc_nlui_pk_mouse;
    if (!m->active || !m->inside) return FALSE;
    *x = m->ux - 160.0f + 9.0f; /* under the New Leaf hand's fingers */
    *y = 120.0f - m->uy - 11.0f;
    return TRUE;
}

static f32 pk_refuse_timer, pk_refuse_x, pk_refuse_y;

void pc_nlui_pk_refuse(f32 x, f32 y) {
    pk_refuse_timer = 90.0f; /* 60 Hz frames */
    pk_refuse_x = x;
    pk_refuse_y = y;
}

static u8 pk_refuse_str[] = "Can't combine those!";

void pc_nlui_pk_draw_overlay(Submenu* submenu, GAME* game) {
    GRAPH* graph = game->graph;
    pc_nlui_pk_mouse_c* m = &pc_nlui_pk_mouse;
    Gfx* g;

    if (!pc_nlui_enabled()) return;
    nlui_graph = graph;
    nlui_unit = 1.0f;

    if (pk_refuse_timer > 0.0f) {
        f32 w = (f32)mFont_GetStringWidth(pk_refuse_str, sizeof(pk_refuse_str) - 1, TRUE) * 0.875f;
        f32 x = pk_refuse_x, y = pk_refuse_y + 22.0f;
        if (x - w * 0.5f - 12.0f < -150.0f) x = -150.0f + w * 0.5f + 12.0f;
        if (x + w * 0.5f + 12.0f > 150.0f) x = 150.0f - w * 0.5f - 12.0f;
        pk_refuse_timer -= (f32)gamePT->graph->dt_num_60fps_frames;
        Matrix_scale(16.0f, 16.0f, 1.0f, MTX_LOAD);
        Matrix_translate(x, y, 140.0f, MTX_MULT);
        OPEN_POLY_OPA_DISP(graph);
        gSPMatrix(POLY_OPA_DISP++, _Matrix_to_Mtx_new(graph), G_MTX_NOPUSH | G_MTX_LOAD | G_MTX_MODELVIEW);
        POLY_OPA_DISP = pc_nlui_tag_balloon(graph, POLY_OPA_DISP, w + 20.0f, 22.0f);
        CLOSE_POLY_OPA_DISP(graph);
        submenu->overlay->set_char_matrix_proc(graph);
        mFont_SetLineStrings(game, pk_refuse_str, sizeof(pk_refuse_str) - 1, 160.0f + x - w * 0.5f,
                             120.0f - y - 7.0f, 90, 60, 50, 255, FALSE, TRUE, 0.875f, 0.875f, mFont_MODE_POLY);
    }

    if ((m->active && m->inside) || pk_key_set) {
        /* at the mouse, or where the keys put the cursor (the GameCube hand is no longer drawn) */
        int mouse = m->active && m->inside;
        f32 s = NLUI_PK_HAND_PX;
        f32 x = (mouse ? m->ux - 160.0f : pk_key_x) - NLUI_PK_HAND_HOT_X; /* texture top-left, model pixels, y up */
        f32 y = (mouse ? 120.0f - m->uy : pk_key_y) + NLUI_PK_HAND_HOT_Y;
        u8* tex = mouse ? (m->dragging ? nlui_pk_hand_g_tex : (m->down ? nlui_pk_hand_c_tex : nlui_pk_hand_tex))
                        : (pk_key_holding ? nlui_pk_hand_g_tex : nlui_pk_hand_tex);
        pk_key_set = FALSE;
        Matrix_scale(16.0f, 16.0f, 1.0f, MTX_LOAD);
        OPEN_POLY_OPA_DISP(graph);
        g = POLY_OPA_DISP;
        gSPMatrix(g++, _Matrix_to_Mtx_new(graph), G_MTX_NOPUSH | G_MTX_LOAD | G_MTX_MODELVIEW);
        g = nlui_mode(g);
        g = nlui_tex(g, G_IM_FMT_RGBA, G_IM_SIZ_32b, NLUI_PK_HAND_TW, NLUI_PK_HAND_TH, tex);
        /* NL's flat black shadow a few pixels lower, then the hand */
        gDPSetCombineLERP(g++, 0, 0, 0, 0, TEXEL0, 0, PRIMITIVE, 0, 0, 0, 0, 0, TEXEL0, 0, PRIMITIVE, 0);
        gDPSetPrimColor(g++, 0, 255, 0, 0, 0, 90);
        g = nlui_quad(g, x, y - s - NLUI_PK_HAND_SHADOW_DY, x + s, y - NLUI_PK_HAND_SHADOW_DY, 0, 0, NLUI_PK_HAND_IW,
                      NLUI_PK_HAND_IH);
        gDPPipeSync(g++);
        gDPSetCombineLERP(g++, 0, 0, 0, TEXEL0, 0, 0, 0, TEXEL0, 0, 0, 0, TEXEL0, 0, 0, 0, TEXEL0);
        g = nlui_quad(g, x, y - s, x + s, y, 0, 0, NLUI_PK_HAND_IW, NLUI_PK_HAND_IH);
        POLY_OPA_DISP = g;
        CLOSE_POLY_OPA_DISP(graph);
    }
}

/* ======================= item action window ======================= */
#define SEL_CAP_X 10.0f /* left/right caps kept unstretched, pixels */

/* one horizontal slice of the paper: caps at both ends, the middle stretched to width w */
static Gfx* pk_sel_slice(Gfx* g, u8* tex, int tw, int th, int iw, int ih, f32 x0, f32 y1, f32 w, f32 h) {
    f32 c = SEL_CAP_X, ct = SEL_CAP_X * NLUI_PX;
    g = nlui_tex(g, G_IM_FMT_RGBA, G_IM_SIZ_32b, tw, th, tex);
    g = nlui_quad(g, x0, y1 - h, x0 + c, y1, 0, 0, ct, ih);
    g = nlui_quad(g, x0 + c, y1 - h, x0 + w - c, y1, ct, 0, iw - ct, ih);
    g = nlui_quad(g, x0 + w - c, y1 - h, x0 + w, y1, iw - ct, 0, iw, ih);
    return g;
}

/* Paper with `rows` lines, in the tag's pixel space (y up): text_x/text_top = where the GameCube draws the first
 * line, row_h = its line spacing, text_w = the widest line. The cursor arrow goes on row `cursor` (-1: none). */
Gfx* pc_nlui_pk_select_window(GRAPH* graph, Gfx* g, f32 text_x, f32 text_top, f32 row_h, int rows, f32 text_w,
                              int cursor) {
    f32 s = row_h / NLUI_PK_SEL_ROW_H; /* the paper scales with the GameCube rows */
    f32 x0 = text_x - NLUI_PK_SEL_TEXT_X * s;
    f32 w = (NLUI_PK_SEL_TEXT_X + 10.0f) * s + text_w;
    f32 y = text_top + NLUI_PK_SEL_CAP * s; /* the paper's top edge */
    f32 wt = w + (NLUI_PK_SEL_W - 132.0f) * s; /* + the shade strip on the right */
    int i;

    nlui_graph = graph;
    nlui_unit = 1.0f;
    if (w < 2.0f * SEL_CAP_X + 4.0f) w = 2.0f * SEL_CAP_X + 4.0f;
    g = nlui_mode(g);
    gDPSetCombineLERP(g++, 0, 0, 0, TEXEL0, 0, 0, 0, TEXEL0, 0, 0, 0, TEXEL0, 0, 0, 0, TEXEL0);
    if (rows < 2) rows = 2;
    g = pk_sel_slice(g, nlui_pk_sel_top_tex, NLUI_PK_SEL_TOP_TW, NLUI_PK_SEL_TOP_TH, NLUI_PK_SEL_TOP_IW,
                     NLUI_PK_SEL_TOP_IH, x0, y, wt, NLUI_PK_SEL_TOP_H * s);
    y -= NLUI_PK_SEL_TOP_H * s;
    for (i = 1; i < rows - 1; i++) {
        g = pk_sel_slice(g, nlui_pk_sel_row_tex, NLUI_PK_SEL_ROW_TW, NLUI_PK_SEL_ROW_TH, NLUI_PK_SEL_ROW_IW,
                         NLUI_PK_SEL_ROW_IH, x0, y, wt, NLUI_PK_SEL_ROW_H * s);
        y -= NLUI_PK_SEL_ROW_H * s;
    }
    g = pk_sel_slice(g, nlui_pk_sel_bot_tex, NLUI_PK_SEL_BOT_TW, NLUI_PK_SEL_BOT_TH, NLUI_PK_SEL_BOT_IW,
                     NLUI_PK_SEL_BOT_IH, x0, y, wt, NLUI_PK_SEL_BOT_H * s);
    if (cursor >= 0) {
        f32 cw = NLUI_PK_SEL_CURSOR_W * s, ch = NLUI_PK_SEL_CURSOR_H * s;
        f32 cx = text_x - cw - 3.0f * s, cy = text_top - (cursor + 0.5f) * row_h + 1.0f;
        g = nlui_tex(g, G_IM_FMT_RGBA, G_IM_SIZ_32b, NLUI_PK_SEL_CURSOR_TW, NLUI_PK_SEL_CURSOR_TH,
                     nlui_pk_sel_cursor_tex);
        g = nlui_quad(g, cx, cy - ch * 0.5f, cx + cw, cy + ch * 0.5f, 0, 0, NLUI_PK_SEL_CURSOR_IW,
                      NLUI_PK_SEL_CURSOR_IH);
    }
    return g;
}

/* ======================= bell bags ======================= */
static int pk_bag_amount(mActor_name_t item) {
    switch (item) {
        case ITM_MONEY_100: return 100;
        case ITM_MONEY_1000: return 1000;
        case ITM_MONEY_10000: return 10000;
        case ITM_MONEY_30000: return 30000;
    }
    return 0;
}

int pc_nlui_pk_is_bag(mActor_name_t item) {
    return pk_bag_amount(item) != 0;
}

/* Bell bag merge. The GameCube only has 100, 1,000, 10,000 and 30,000 bell bags, so a merge must end in one of
 * those: the next bag up takes 10 x 100, 10 x 1,000 or 3 x 10,000. Dropping a bag on a bag of the same size merges
 * the held bag, the target bag and as many more bags of that size from the pockets as the next bag needs; the result
 * replaces the target. Anything else (different sizes, 30,000 bags, not enough bags) is refused.
 * Returns the merged bag (and fills `use` with the other pocket slots to empty), or EMPTY_NO to refuse. */
mActor_name_t pc_nlui_pk_bag_merge(mActor_name_t held, int target_idx, int* use, int* n_use) {
    mActor_name_t target = Now_Private->inventory.pockets[target_idx];
    mActor_name_t next;
    int need, i, have;

    *n_use = 0;
    if (held != target || !pc_nlui_pk_is_bag(held)) return EMPTY_NO;
    switch (held) {
        case ITM_MONEY_100: next = ITM_MONEY_1000; need = 10; break;
        case ITM_MONEY_1000: next = ITM_MONEY_10000; need = 10; break;
        case ITM_MONEY_10000: next = ITM_MONEY_30000; need = 3; break;
        default: return EMPTY_NO;
    }
    have = 2; /* the held bag and the target */
    for (i = 0; i < mPr_POCKETS_SLOT_COUNT && have < need; i++) {
        if (i != target_idx && Now_Private->inventory.pockets[i] == held &&
            mPr_GET_ITEM_COND(Now_Private->inventory.item_conditions, i) == mPr_ITEM_COND_NORMAL) {
            use[(*n_use)++] = i;
            have++;
        }
    }
    if (have < need) {
        *n_use = 0;
        return EMPTY_NO;
    }
    return next;
}
