#ifndef PC_NL_UI_LETTERS_H
#define PC_NL_UI_LETTERS_H

/* New Leaf letter screen (Letter/ltr_base) around the player's GameCube stationery, and New Leaf's wooden
 * bulletin board (Board/board_base_T + board_paper) for the GameCube notice board.
 * Board art: asset_import_work/nl_ui_survey/gen_nlui_letters.py -> pc_nl_ui_letters_data.c. */

#include "pc_nl_ui.h"

/* ---- letters (m_board_ovl.c) ---- */
/* Text lines: 0 = header, 1..6 = body, 7 = footer. Returns how many screen pixels the line moves up from its
 * GameCube position (draw at gc_screen_y - dy). */
f32 pc_nlui_letter_line_dy(int paper_type, int line);
/* body line pitch in screen pixels (GameCube: 16) */
f32 pc_nlui_letter_pitch(int paper_type);
/* NL's dark brown, unless the paper is dark (GameCube gave it a light text colour) */
void pc_nlui_letter_text_color(const rgba_t* gc, rgba_t* out);
/* NL drop shadow + the GameCube paper (and its ruled lines) fitted into NL's paper slot.
 * x, y: the letter's GameCube position (menu_info->position). */
void pc_nlui_letter_frame(GRAPH* graph, f32 x, f32 y, Gfx* mode, Gfx* paper, Gfx* sen_mode, Gfx* sen);

/* ---- notice board (m_notice_ovl.c) ---- */
void pc_nlui_notice_board(GRAPH* graph, f32 y);          /* wooden board, does not slide with the pages */
void pc_nlui_notice_paper(GRAPH* graph, f32 x, f32 y);   /* pinned paper at page offset x */

/* Notice text on the NL paper lines (screen pixels, relative to the page offset; y down) */
#define NLUI_NOTICE_DATE_X 41.0f    /* T_date_00, left aligned */
#define NLUI_NOTICE_DATE_Y 36.0f
#define NLUI_NOTICE_PAGE_R 280.0f   /* page number, right aligned on the date line */
#define NLUI_NOTICE_PAGE_Y 38.0f
#define NLUI_NOTICE_BODY_X 57.0f    /* T_Hnbn_00..05 */
#define NLUI_NOTICE_BODY_Y 62.5f
#define NLUI_NOTICE_PITCH 21.0f
#define NLUI_NOTICE_KEYS_DY 24.0f   /* GameCube button hints moved down, off the paper's text lines */
#define NLUI_TEXT_R 70
#define NLUI_TEXT_G 50
#define NLUI_TEXT_B 40

#endif
