/* PC mouse in the 320x240 GameCube UI space, for the New Leaf UI (keyboard hand cursor). Only SDL here, so the
 * game-side code (pc_nl_ui_keyboard.c) stays free of platform headers.
 * PC_NLUI_FAKE_MOUSE (dev only, with the PC_CC_TEST harness): "<n>:<ux>:<uy>:<button>,..." gives the mouse UI
 * position and left button for the n-th call after the editor opened (held until the next entry). */
#include "pc_platform.h"
#include "pc_settings.h"
#include <SDL.h>
#include <stdlib.h>
#include <string.h>

static int fake_step = -1;

int pc_nlui_mouse_fake_step(void) {
    return fake_step;
}

void pc_nlui_mouse_reset(void) {
    fake_step = 0;
}

static int fake_mouse(float* ux, float* uy, int* left) {
    static const char* spec = (const char*)1;
    const char* p;
    int found = 0;
    if (spec == (const char*)1) spec = getenv("PC_NLUI_FAKE_MOUSE");
    if (spec == NULL) return -1;
    if (fake_step < 0) return 0;
    fake_step++;
    for (p = spec; p && *p;) {
        int n = atoi(p);
        float x, y;
        int b;
        const char* q = strchr(p, ':');
        if (q == NULL || n > fake_step) break;
        x = (float)atof(q + 1);
        q = strchr(q + 1, ':'); if (q == NULL) break;
        y = (float)atof(q + 1);
        q = strchr(q + 1, ':'); if (q == NULL) break;
        b = atoi(q + 1);
        *ux = x; *uy = y; *left = b; found = 1;
        p = strchr(q, ',');
        if (p) p++;
    }
    return found;
}

/* Mouse position in UI pixels (320x240, y down) and the left button. Returns 0 when the mouse is not over the
 * game window. The UI is a centred 4:3 picture unless the aspect setting stretches it. */
int pc_nlui_mouse_ui(float* ux, float* uy, int* left) {
    int mx, my, w, h;
    float cw, x0;
    Uint32 b;
    int f = fake_mouse(ux, uy, left);
    if (f >= 0) return f;
    if (g_pc_window == NULL || SDL_GetMouseFocus() != g_pc_window) return 0;
    b = SDL_GetMouseState(&mx, &my);
    SDL_GetWindowSize(g_pc_window, &w, &h);
    if (w <= 0 || h <= 0) return 0;
    cw = (float)w;
#ifdef PC_ENHANCEMENTS
    if (g_pc_settings.aspect_mode == 0) cw = (float)h * 4.0f / 3.0f;
#endif
    x0 = ((float)w - cw) * 0.5f;
    *ux = ((float)mx - x0) * 320.0f / cw;
    *uy = (float)my * 240.0f / (float)h;
    *left = (b & SDL_BUTTON(SDL_BUTTON_LEFT)) != 0;
    return 1;
}

void pc_nlui_mouse_show_os(int show) {
    static int shown = 1;
    if (show != shown) {
        SDL_ShowCursor(show ? SDL_ENABLE : SDL_DISABLE);
        shown = show;
    }
}
