/* New Leaf UI: town map acres re-textured with New Leaf grass / water / sand (approved mock nl_map_mock2.png).
 * The GameCube acre pictures keep their shapes, cliffs and icons; see gen_nlui_map.py. */

#include "pc_nl_ui_map.h"
#include "pc_nl_ui_map_data.h"
#include "pc_nl_ui_internal.h"

#include "libforest/gbi_extensions.h"
#include "graph.h"

struct nlui_map_entry {
    u8* gc_tex;
    int pal;
    u8* nl_tex;
};

extern const struct nlui_map_entry pc_nl_ui_map_table[NLUI_MAP_COUNT];

u8* pc_nlui_map_acre_tex(u8* gc_tex, int pal) {
    int i;
    for (i = 0; i < NLUI_MAP_COUNT; i++) {
        if (pc_nl_ui_map_table[i].gc_tex == gc_tex && pc_nl_ui_map_table[i].pal == pal) {
            return pc_nl_ui_map_table[i].nl_tex;
        }
    }
    return NULL;
}

Gfx* pc_nlui_map_acre(GRAPH* graph, Gfx* g, u8* nl_tex) {
    nlui_graph = graph;
    nlui_unit = 1.0f;
    gDPSetTextureLUT(g++, G_TT_NONE);
    g = nlui_tex(g, G_IM_FMT_RGBA, G_IM_SIZ_32b, NLUI_MAP_CELL, NLUI_MAP_CELL, nl_tex);
    /* same 22x22 pixel square as kan_tizu_v; the texture already has GC's grid line removed */
    g = nlui_quad(g, -11.0f, -11.0f, 11.0f, 11.0f, 0.0f, 0.0f, (f32)NLUI_MAP_CELL, (f32)NLUI_MAP_CELL);
    return g;
}
