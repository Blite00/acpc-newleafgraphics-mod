/* New Leaf TVs: the furniture's own draw is replaced by one that draws the NL body plus its screen.
 * Off: the model's own dark screen. On: New Leaf's TV programmes (pc_furn_tvprog.c), picked by the hour like NL:
 * a test card late at night, the weather report in the morning, a different show every other hour.
 * The GC move code (switch sounds, on/off) is kept. PC_FURN_GC=1 skips the hook. */
#include "m_play.h"
#include "ac_furniture.h"
#include "m_common_data.h"
#include "m_rcp.h"
#include "sys_matrix.h"
#include "m_kankyo.h"
#include "libforest/gbi_extensions.h"

extern const int pc_tvprog_count;
extern u8** pc_tvprog_frames[];
extern const int pc_tvprog_nframes[];

#define PC_TV_SLOTS 8
typedef struct { aFTR_PROFILE* profile; Gfx* body; Gfx* screen; u8* off; } pc_tv_c;
static pc_tv_c pc_tv[PC_TV_SLOTS];
static int pc_tv_n = 0;

static int pc_tv_program(void) {
    int hour = Common_Get(time.rtc_time.hour);
    if (hour >= 1 && hour < 6) return 0;                     /* test card */
    if (hour >= 6 && hour < 9) {                             /* morning weather report */
        switch (Common_Get(weather)) {
            case mEnv_WEATHER_RAIN: return 22;
            case mEnv_WEATHER_SNOW: return 23;
            case mEnv_WEATHER_CLEAR: return 21;
            default: return 24;
        }
    }
    return 1 + (hour * 7) % 20;                              /* a show per hour */
}

static void pc_tv_draw(int slot, FTR_ACTOR* ftr_actor, GAME* game) {
    pc_tv_c* tv = &pc_tv[slot];
    u8* tex = tv->off;

    if (ftr_actor->switch_bit) {
        int prog = pc_tv_program();
        int n = pc_tvprog_nframes[prog];
        tex = pc_tvprog_frames[prog][(game->frame_counter / 90) % n];
    }
    OPEN_DISP(game->graph);
    gSPMatrix(NEXT_POLY_OPA_DISP, _Matrix_to_Mtx_new(game->graph), G_MTX_NOPUSH | G_MTX_LOAD | G_MTX_MODELVIEW);
    gSPDisplayList(NEXT_POLY_OPA_DISP, tv->body);
    gDPPipeSync(NEXT_POLY_OPA_DISP);
    gDPSetTextureImage_Dolphin(NEXT_POLY_OPA_DISP, G_IM_FMT_RGBA, G_IM_SIZ_32b, 64, 32, tex);
    gSPDisplayList(NEXT_POLY_OPA_DISP, tv->screen);
    CLOSE_DISP(game->graph);
}

#define PC_TV_DW(n) static void pc_tv_dw##n(FTR_ACTOR* a, ACTOR* r, GAME* g, u8* d) { pc_tv_draw(n, a, g); }
PC_TV_DW(0) PC_TV_DW(1) PC_TV_DW(2) PC_TV_DW(3) PC_TV_DW(4) PC_TV_DW(5) PC_TV_DW(6) PC_TV_DW(7)
static aFTR_FTR_DRAW_PROC pc_tv_dw[PC_TV_SLOTS] = { pc_tv_dw0, pc_tv_dw1, pc_tv_dw2, pc_tv_dw3,
                                                    pc_tv_dw4, pc_tv_dw5, pc_tv_dw6, pc_tv_dw7 };

void pc_furn_tv_hook(void* profile, Gfx* body, Gfx* screen, u8* off_tex) {
    aFTR_PROFILE* p = (aFTR_PROFILE*)profile;
    if (pc_tv_n >= PC_TV_SLOTS || p->vtable == NULL) return;
    pc_tv[pc_tv_n].profile = p;
    pc_tv[pc_tv_n].body = body;
    pc_tv[pc_tv_n].screen = screen;
    pc_tv[pc_tv_n].off = off_tex;
    p->opaque0 = p->opaque1 = p->translucent0 = p->translucent1 = NULL;
    p->vtable->draw_proc = pc_tv_dw[pc_tv_n];
    pc_tv_n++;
}
