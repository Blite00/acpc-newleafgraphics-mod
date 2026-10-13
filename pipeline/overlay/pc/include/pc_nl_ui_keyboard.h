#ifndef PC_NL_UI_KEYBOARD_H
#define PC_NL_UI_KEYBOARD_H

/* New Leaf wooden QWERTY keyboard for the GameCube editor (m_editor_ovl.c): NL key art laid on the GameCube
 * 10x4 key grid, labels in the GameCube font. Art from nl_ui_survey/gen_nlui_keyboard.py. */

#include "pc_nl_ui.h"
#include "m_editor_ovl.h"

/* Key art. In place of mED_KeyDraw: x, y are the editor's panel offset (menu_info->position). */
void pc_nlui_kb_draw(GRAPH* graph, mED_Ovl_c* editor_ovl, f32 x, f32 y);

/* Key labels, in the editor's character matrix (set_char_matrix_proc already applied). codes[] holds the 40
 * characters of the current page (mED_get_code, row-major), CHAR_SPACE_3 for an empty cell. */
void pc_nlui_kb_strings(GAME* game, mED_Ovl_c* editor_ovl, const u8* codes, f32 x, f32 y);

/* PC mouse. pc_nlui_kb_mouse runs once per editor frame: a moving mouse moves the key cursor to the key under it
 * and shows NL's hand cursor (the OS cursor is hidden until pc_nlui_kb_close). It returns what a left click hit. */
enum {
    PC_NLUI_KB_NONE = -1,
    PC_NLUI_KB_TYPE = 100, /* a character key: the key cursor is on it, type mED_get_code() */
    PC_NLUI_KB_BSP = 101,
    PC_NLUI_KB_OK,
    PC_NLUI_KB_SPC,
    PC_NLUI_KB_CPS,
    PC_NLUI_KB_SFT,
    PC_NLUI_KB_MODE0, /* + input mode */
};
void pc_nlui_kb_open(void);
void pc_nlui_kb_close(void);
int pc_nlui_kb_mouse(mED_Ovl_c* editor_ovl);
void pc_nlui_kb_draw_hand(GRAPH* graph);

/* Top edge of the keyboard in screen pixels (for callers that place things above it). */
f32 pc_nlui_kb_top(void);

#endif
