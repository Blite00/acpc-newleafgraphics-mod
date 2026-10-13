#ifndef PC_NL_UI_POCKETS_H
#define PC_NL_UI_POCKETS_H

/* New Leaf extras for the GameCube pocket screen (the GameCube window and layout stay):
 *  - New Leaf item icons in place of the GameCube ones wherever pocket icons are drawn (mSM_draw_item),
 *  - the mouse with New Leaf's hand: hover moves the cursor, click = A, drag and drop (slots, player, bells),
 *  - bell bags merged by dropping one onto another,
 *  - New Leaf's item action window for the GameCube select tags.
 * Art: asset_import_work/nl_ui_survey/gen_nlui_pockets.py -> pc_nl_ui_pockets_data.c. PC_NL_UI=0 turns all off. */

#include "pc_nl_ui.h"
#include "m_submenu.h"

/* RGBA8 32x32 New Leaf icon for a GameCube item, or NULL to keep the GameCube icon. */
u8* pc_nlui_pk_icon(mActor_name_t item);
int pc_nlui_pk_icon_index(mActor_name_t item);

/* Mouse, polled once per frame while the pockets are open (UI pixels, y down). */
typedef struct {
    int inside;   /* over the game window */
    int active;   /* moved since the pockets opened: NL hand shown, OS cursor hidden */
    int down, press, release, moved;
    int dragging; /* an item is being dragged (set by m_tag_ovl.c) */
    int press_latch, release_latch; /* kept until m_tag_ovl.c sees them (it skips frames while tags animate) */
    f32 ux, uy, press_ux, press_uy;
} pc_nlui_pk_mouse_c;
extern pc_nlui_pk_mouse_c pc_nlui_pk_mouse;
void pc_nlui_pk_mouse_open(void);
void pc_nlui_pk_mouse_close(void);
void pc_nlui_pk_mouse_update(void);

/* NL hand at the mouse and the bag refusal balloon, drawn last in the pocket screen. */
void pc_nlui_pk_draw_overlay(Submenu* submenu, GAME* game);
void pc_nlui_pk_refuse(f32 x, f32 y); /* window pixels, y up */
/* The GameCube hand is not drawn: m_hand_ovl.c reports where it points (pixels, y up) so the New Leaf hand stands in
 * for it when the keys drive the cursor, and asks where a held item goes. */
void pc_nlui_pk_set_key_hand(f32 x, f32 y, int holding);
int pc_nlui_pk_hand_replaces_gc(Submenu* submenu);
int pc_nlui_pk_held_item_pos(f32* x, f32* y); /* TRUE: draw the held item here (mouse mode) */

/* NL item action paper behind a GameCube select tag, in the tag's pixel space. */
Gfx* pc_nlui_pk_select_window(GRAPH* graph, Gfx* g, f32 text_x, f32 text_top, f32 row_h, int rows, f32 text_w,
                              int cursor);

/* Bell bags: TRUE for the four GameCube bags; the merge (see pc_nl_ui_pockets.c for the rule). */
int pc_nlui_pk_is_bag(mActor_name_t item);
mActor_name_t pc_nlui_pk_bag_merge(mActor_name_t held, int target_idx, int* use, int* n_use);

#endif
