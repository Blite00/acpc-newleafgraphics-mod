#ifndef PC_NL_UI_MAP_H
#define PC_NL_UI_MAP_H
/* New Leaf UI: town map acres. Each GameCube acre picture (kan_tizu_*_TA_tex_txt + palette) is replaced by a
 * pre-generated copy re-textured with New Leaf grass, water, sand and bridge planks
 * (asset_import_work/nl_ui_survey/gen_nlui_map.py -> pc_nl_ui_map_data.c). */
#include "pc_nl_ui.h"

/* the re-textured RGBA acre for a GameCube acre texture + palette number, or NULL if there is none */
u8* pc_nlui_map_acre_tex(u8* gc_tex, int pal);
/* draw that acre over the GameCube acre quad (22x22 pixels centred on the current matrix, pixel model units);
 * call after kan_tizu_mode and the acre's gSPMatrix */
Gfx* pc_nlui_map_acre(GRAPH* graph, Gfx* g, u8* nl_tex);

#endif
