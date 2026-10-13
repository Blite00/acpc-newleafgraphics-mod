/* Dev-only: PC_CC_TEST=<folder> plays a new game through the train intro with scripted presses, drives the
 * character creator and saves screenshots (cc_*.bmp) into the folder. Inactive without the variable. */
#include "pc_platform.h"
#include "pc_gx_internal.h"
#include "dolphin/pad.h"
#include <SDL.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

extern int pc_cc_is_open(void);

static int t_on = -1;
static const char* t_dir;
static int t_frame, t_open_at = -1, t_closed_at = -1, t_opened;
static char t_shot[256];

static int t_active(void) {
    if (t_on < 0) {
        t_dir = getenv("PC_CC_TEST");
        t_on = t_dir != NULL;
    }
    return t_on;
}

static void t_capture(const char* name) {
    snprintf(t_shot, sizeof(t_shot), "%s/cc_%s.bmp", t_dir, name);
}

/* creator script: frames after it opened -> buttons */
static u16 t_creator(int f) {
    /* dev: PC_CC_SWEEP=boy|girl captures every hairstyle (the creator preview) in one run */
    const char* sweep = getenv("PC_CC_SWEEP");
    if (sweep != NULL) {
        int girl = sweep[0] == 'g', k, rel;
        if (girl && f == 50) return PAD_BUTTON_RIGHT;
        if (f == 60 || f == 70) return PAD_BUTTON_DOWN;
        if (f >= 100) {
            k = (f - 100) / 24; rel = (f - 100) % 24;
            if (k < 16 && rel == 16) { char n[24]; snprintf(n, sizeof(n), "sw_%s_%02d", girl ? "girl" : "boy", k); t_capture(n); }
            if (k < 15 && rel == 20) return PAD_BUTTON_RIGHT;
        }
        return 0;
    }
    static const struct { int f; u16 b; const char* shot; } s[] = {
        { 40, 0, "1_default" },
        { 50, PAD_BUTTON_RIGHT }, /* girl */
        { 60, PAD_BUTTON_DOWN },  { 70, PAD_BUTTON_RIGHT }, { 80, PAD_BUTTON_RIGHT },
        { 90, PAD_BUTTON_DOWN },  { 100, PAD_BUTTON_RIGHT }, { 110, PAD_BUTTON_RIGHT }, { 120, PAD_BUTTON_RIGHT },
        { 130, PAD_BUTTON_DOWN }, { 140, PAD_BUTTON_LEFT }, { 150, PAD_BUTTON_LEFT },
        { 190, 0, "2_girl" },
        { 200, PAD_BUTTON_UP }, { 210, PAD_BUTTON_RIGHT }, { 220, PAD_BUTTON_RIGHT }, { 230, PAD_BUTTON_RIGHT },
        { 240, PAD_BUTTON_RIGHT }, { 250, PAD_BUTTON_RIGHT }, { 260, PAD_BUTTON_RIGHT },
        { 270, PAD_BUTTON_DOWN }, { 280, PAD_BUTTON_LEFT }, { 290, PAD_BUTTON_LEFT }, { 300, PAD_BUTTON_LEFT },
        { 340, 0, "3_girl2" },
        { 350, PAD_BUTTON_DOWN }, { 400, 0, "4_done_row" }, { 410, PAD_BUTTON_A },
    };
    int i;
    for (i = 0; i < (int)(sizeof(s) / sizeof(s[0])); i++) {
        if (s[i].f == f) {
            if (s[i].shot) t_capture(s[i].shot);
            return s[i].b;
        }
    }
    return 0;
}

int pc_cc_test_pad(PADStatus* status) {
    u16 b = 0;
    if (!t_active()) return 0;
    memset(status, 0, sizeof(PADStatus) * 4);
    status[1].err = status[2].err = status[3].err = -1;
    if (t_frame % 1500 == 0) { char n[32]; snprintf(n, sizeof(n), "0_frame_%05d", t_frame); t_capture(n); }
    if (pc_cc_is_open()) {
        if (t_open_at < 0) t_open_at = t_frame;
        t_opened = 1;
        b = t_creator(t_frame - t_open_at);
    } else {
        int k = t_frame % 24;
        if (t_opened && t_closed_at < 0) t_closed_at = t_frame;
        if (t_closed_at >= 0) {
            int d = t_frame - t_closed_at;
            if (d == 50) t_capture("5_rover_back");
            if (d == 140) t_capture("6_rover_more");
            if (d > 0 && d % 900 == 0) { char n[32]; snprintf(n, sizeof(n), "7_after_%05d", d); t_capture(n); }
            if (d > 9000) g_pc_running = 0;
        }
        /* mash A; every 4th pulse START (finishes the name / town name editors) */
        if (k < 2) b = ((t_frame / 24) % 4 == 3) ? PAD_BUTTON_START : PAD_BUTTON_A;
    }
    status[0].button = b;
    return 1;
}

void pc_cc_test_frame(void) {
    int w, h, y;
    unsigned char *px, *fl;
    SDL_Surface* s;
    if (!t_active()) return;
    t_frame++;
    if (t_frame > 40000 || (getenv("PC_CC_TEST_STOP") && t_frame > atoi(getenv("PC_CC_TEST_STOP")))) g_pc_running = 0;
    if (!t_shot[0]) return;
    SDL_GL_GetDrawableSize(g_pc_window, &w, &h);
    px = malloc((size_t)w * h * 4);
    fl = malloc((size_t)w * h * 4);
    if (px && fl) {
        glReadPixels(0, 0, w, h, GL_RGBA, GL_UNSIGNED_BYTE, px);
        for (y = 0; y < h; y++) memcpy(fl + (size_t)y * w * 4, px + (size_t)(h - 1 - y) * w * 4, (size_t)w * 4);
        s = SDL_CreateRGBSurfaceFrom(fl, w, h, 32, w * 4, 0xff, 0xff00, 0xff0000, 0xff000000);
        if (s) { SDL_SaveBMP(s, t_shot); SDL_FreeSurface(s); }
        printf("[CC_TEST] frame %d %s\n", t_frame, t_shot);
    }
    free(px);
    free(fl);
    t_shot[0] = 0;
}
