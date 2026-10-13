#ifndef PC_NL_UI_INTERNAL_H
#define PC_NL_UI_INTERNAL_H
/* Shared helpers for the New Leaf UI modules (pc_nl_ui*.c). */
#include "pc_nl_ui.h"

extern GRAPH* nlui_graph;   /* set by each public draw function: per-frame vertices come from this graph */
extern f32 nlui_unit;       /* model units per pixel in the caller's matrix space (16 or 1) */

Vtx* nlui_alloc_quad(void);
void nlui_set_v(Vtx* v, f32 x, f32 y, f32 s, f32 t);
/* rectangle in pixels (y up), texture texels s0..s1, t0..t1 (t down) */
Gfx* nlui_quad(Gfx* g, f32 x0, f32 y0, f32 x1, f32 y1, f32 s0, f32 t0, f32 s1, f32 t1);
/* 1-cycle, translucent, bilinear, no z: call before setting the combiner */
Gfx* nlui_mode(Gfx* g);
/* load a GX-format texture (RGBA32 / IA16 / ...) into tile 0, clamped */
Gfx* nlui_tex(Gfx* g, int fmt, int siz, int w, int h, void* tex);

#endif
