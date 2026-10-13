#include "m_play.h"
#ifdef TARGET_PC
#include "pc_rolling_world.h"
#include "pc_donor_light.h"
#endif

#include "evw_anime.h"
#include "m_common_data.h"
#include "libultra/libultra.h"
#include "m_fbdemo_wipe1.h"
#include "m_fbdemo_triforce.h"
#include "m_fbdemo_fade.h"
#include "m_debug.h"
#include "boot.h"
#include "version.h"
#include "m_bgm.h"
#include "m_rcp.h"
#include "m_msg.h"
#include "m_banti.h"
#include "m_event.h"
#include "m_npc.h"
#include "m_huusui_room.h"
#include "m_field_make.h"
#include "m_card.h"
#include "m_eappli.h"
#include "famicom_emu.h"
#include "Famicom/famicomPriv.h"
#include "m_malloc.h"
#include "m_field_info.h"
#include "m_time.h"
#include "m_titledemo.h"
#include "sys_matrix.h"
#include "m_fuusen.h"
#include "m_watch_my_step.h"
#include "m_vibctl.h"
#include "m_train_control.h"
#include "gfxalloc.h"
#include "m_debug_display.h"
#include "jsyswrap.h"
#include "m_trademark.h"
#include "zurumode.h"
#include "m_scene_table.h"
#include "m_player_lib.h"
#include "m_skin_matrix.h"
#include "padmgr.h"
#ifdef TARGET_PC
#include "pc_diag.h"
#include "pc_platform.h"
#endif

#define Game_play_HYRAL_SIZE 0x3E800 // 256,000 bytes
#define Game_play_IS_PAUSED(play) (ZURUMODE2_ENABLED() ? (!Pause_proc(&(play)->pause, &(play)->game.pads[PAD1])) : FALSE)

static fbdemo_c fbdemo;
static f32 S_back_title_timer = 0.0f;
static f32 S_se_endcheck_timeout = 0.0f;
static u8 gxbuf[0x140] ATTRIBUTE_ALIGN(32);
static u8 prbuf[(2*SCREEN_WIDTH) * (2*SCREEN_HEIGHT) * sizeof(u32)] ATTRIBUTE_ALIGN(32); // 0x12C000

static void Game_play_fbdemo_wipe_init(GAME_PLAY* play);
static void Gameplay_Scene_Read(GAME_PLAY* play, s16 scene_no);

static void Game_play_dec_dt_timer(f32* timer, GAME_PLAY* play) {
    if (*timer > 0.0f) {
        *timer -= (f32)play->game.graph->dt_num_60fps_frames;
        if (*timer < 0.0f) {
            *timer = 0.0f;
        }
    }
}

static void Game_play_Reset_destiny() {
    lbRTC_time_c* rtc_time = Common_GetPointer(time.rtc_time);
    mPr_destiny_c* destiny = &Common_Get(now_private)->destiny;

    if (destiny->type == mPr_DESTINY_NORMAL) {
        return;
    }

    if ((rtc_time->year != destiny->received_time.year) || (rtc_time->month != destiny->received_time.month) ||
        (rtc_time->day != destiny->received_time.day)) {
        Common_Set(now_private->destiny.type, mPr_DESTINY_NORMAL);
    }
}

static void event_title_flag_on() {
    if (Common_Get(event_title_flags) != 0) {
        Common_Set(event_notification_active, 1);
    }
}

static void event_title_flag_off() {
    if (Common_Get(event_title_flags) == 2) {
        Common_Set(event_title_flags, 0);
        Common_Set(event_notification_active, 0);
    }
}

static void Game_play_camera_proc(GAME_PLAY* play) {
    Camera2_ClearActorTalking_Cull(play);
    Camera2_process(play);
}

static void Game_play_fbdemo_wipe_destroy(GAME_PLAY* play) {
    play->fbdemo_wipe.wipe_procs.cleanup_proc(&play->fbdemo_wipe.wipe_data);
    play->fb_wipe_mode = WIPE_MODE_NONE;
    play->fbdemo_wipe.wipe_type = -1;
}

static void Game_play_fbdemo_wipe_create_sub(GAME_PLAY* play) {
    static void* wipe_normal_proc[] = {
        fbdemo_wipe1_init,
        none_proc1,
        fbdemo_wipe1_move,
        fbdemo_wipe1_draw,
        fbdemo_wipe1_startup,
        fbdemo_wipe1_settype,
        fbdemo_wipe1_setcolor_rgba8888,
        NULL,
        fbdemo_wipe1_is_finish,
    };
    static void* wipe_triforce_proc[] = {
        fbdemo_triforce_init,
        none_proc1,
        fbdemo_triforce_move,
        fbdemo_triforce_draw,
        fbdemo_triforce_startup,
        fbdemo_triforce_settype,
        fbdemo_triforce_setcolor_rgba8888,
        NULL,
        fbdemo_triforce_is_finish,
    };
    static void* wipe_fade_proc[] = {
        fbdemo_fade_init,
        none_proc1,
        fbdemo_fade_move,
        fbdemo_fade_draw,
        fbdemo_fade_startup,
        fbdemo_fade_settype,
        fbdemo_fade_setcolor_rgba8888,
        NULL,
        fbdemo_fade_is_finish,
    };

    static void* wipe_proc[] = {
        wipe_normal_proc,   wipe_triforce_proc, wipe_fade_proc, wipe_fade_proc,
        wipe_triforce_proc, wipe_triforce_proc, wipe_fade_proc,
    };

    int type = play->fb_wipe_type;
    fbdemo_wipe_proc_c* cur;

    bzero(&play->fbdemo_wipe, sizeof(fbdemo_wipe));

    if (type >= WIPE_TYPE_NUM) {
        type = WIPE_TYPE_TRIFORCE;
    }

    play->fbdemo_wipe.wipe_type = type;
    cur = wipe_proc[type];
    play->fbdemo_wipe.wipe_procs.init_proc = cur->init_proc;
    play->fbdemo_wipe.wipe_procs.cleanup_proc = cur->cleanup_proc;
    play->fbdemo_wipe.wipe_procs.move_proc = cur->move_proc;
    play->fbdemo_wipe.wipe_procs.draw_proc = cur->draw_proc;
    play->fbdemo_wipe.wipe_procs.startup_proc = cur->startup_proc;
    play->fbdemo_wipe.wipe_procs.settype_proc = cur->settype_proc;
    play->fbdemo_wipe.wipe_procs.setcolor_proc = cur->setcolor_proc;
    play->fbdemo_wipe.wipe_procs.isfinished_proc = cur->isfinished_proc;
}

static void Game_play_fbdemo_wipe_create(GAME_PLAY* play) {
    Game_play_fbdemo_wipe_create_sub(play);
    Game_play_fbdemo_wipe_init(play);
}

static void Game_play_fbdemo_wipe_init(GAME_PLAY* play) {
    fbdemo_wipe* wipe = &play->fbdemo_wipe;
    u8 type;

    play->fbdemo_wipe.wipe_procs.init_proc(&wipe->wipe_data);

    Common_Set(transition.wipe_rate, 28);
    Common_Set(transition.fade_rate, 30);

    wipe->wipe_procs.setcolor_proc(&wipe->wipe_data, 0);

    type = play->fb_fade_type;

    if (wipe->wipe_type == WIPE_TYPE_CIRCLE_LEFT) {
        type |= 0x80;
    } else if (wipe->wipe_type == WIPE_TYPE_CIRCLE_RIGHT) {
        type |= 0x40;
    }
    wipe->wipe_procs.settype_proc(&wipe->wipe_data, type);
    wipe->wipe_procs.startup_proc(&wipe->wipe_data);

    play->fb_wipe_mode = WIPE_MODE_MOVE;

    S_back_title_timer = 120.0f;
    S_se_endcheck_timeout = 120.0f;
}

static void Game_play_fbdemo_fade_in_move_end(GAME_PLAY* play) {
    Game_play_fbdemo_wipe_destroy(play);

    if (play->fb_mode == FBDEMO_MODE_MOVE) {
        fbdemo_cleanup(&fbdemo);
        play->fb_mode = FBDEMO_MODE_NONE;
        SetGameFrame(3);
    }
}

static void Game_play_fbdemo_fade_out_start_emu_move_end(GAME_PLAY* play) {
    GAME_GOTO_NEXT(&play->game, famicom_emu, FAMICOM_EMU);
}

static void Game_play_fbdemo_fade_out_game_end_move_end(GAME_PLAY* play) {
    GAME_GOTO_NEXT(&play->game, trademark, TRADEMARK);
}

static void Game_play_change_scene_move_end(GAME_PLAY* play) {
    game_goto_next_game_play(&play->game);
    Common_Set(last_scene_no, Save_Get(scene_no));
    Save_Set(scene_no, play->next_scene_no);
}

static void Game_play_fbdemo_wipe_move(GAME_PLAY* play) {
    fbdemo_wipe* wipe = &play->fbdemo_wipe;
    s16 wipet = FALSE;
    int isDone = TRUE;

    if (wipe->wipe_procs.isfinished_proc(&wipe->wipe_data) != 0) {
        if ((play->fb_fade_type != FADE_TYPE_IN) && (play->fb_fade_type != FADE_TYPE_EVENT)) {
            Game_play_dec_dt_timer(&S_se_endcheck_timeout, play);

            if ((sAdo_SeFadeoutCheck() == 0) && (S_se_endcheck_timeout > 0.0f)) {
                isDone = FALSE;
            } else {
                sAdo_Set_ongenpos_refuse_fg(1);
            }
        }
        if (play->fb_fade_type == FADE_TYPE_EVENT) {
            sAdo_Set_ongenpos_refuse_fg(2);
        }

        if (isDone == TRUE) {
            switch (play->fb_fade_type) {
                case FADE_TYPE_IN:
                    Game_play_fbdemo_fade_in_move_end(play);
                    break;

                case FADE_TYPE_OUT_START_EMU:
                    Game_play_dec_dt_timer(&S_back_title_timer, play);

                    if ((sAdo_BgmFadeoutCheck() == 1) || (S_back_title_timer <= 0.0f)) {
                        Game_play_fbdemo_fade_out_start_emu_move_end(play);
                    } else {
                        wipet = TRUE;
                    }
                    break;

                case FADE_TYPE_OUT_RETURN_TITLE:
                case FADE_TYPE_OUT_GAME_END:
                    if (S_back_title_timer >= 120.0f) {
                        mBGMPsComp_make_ps_wipe(360);
                    }
                case FADE_TYPE_OUT_GAME_END_TRAIN:
                case FADE_TYPE_SELECT_END:
                    Game_play_dec_dt_timer(&S_back_title_timer, play);

                    if ((sAdo_BgmFadeoutCheck() == 1) || (S_back_title_timer <= 0.0f)) {
                        Game_play_fbdemo_fade_out_game_end_move_end(play);
                    } else {
                        wipet = TRUE;
                    }
                    break;

                case FADE_TYPE_SELECT:
                    Game_play_dec_dt_timer(&S_back_title_timer, play);

                    if ((sAdo_BgmFadeoutCheck() == 1) || (S_back_title_timer <= 0.0f)) {
                        if ((Common_Get(clip.animal_logo_clip) != NULL) &&
                            (Common_Get(clip.animal_logo_clip->data_init_proc) != NULL)) {
                            Common_Get(clip.animal_logo_clip->data_init_proc)(play);
                            Game_play_change_scene_move_end(play);
                        }
                    } else {
                        wipet = TRUE;
                    }
                    break;

                case FADE_TYPE_DEMO:
                    Game_play_dec_dt_timer(&S_back_title_timer, play);

                    if ((sAdo_BgmFadeoutCheck() == 1) || (S_back_title_timer <= 0.0f)) {
                        Game_play_change_scene_move_end(play);
                    } else {
                        wipet = TRUE;
                    }
                    break;

                case FADE_TYPE_EVENT:
                case FADE_TYPE_OTHER_ROOM:
                    Game_play_change_scene_move_end(play);
                    break;

                default:
                    Game_play_dec_dt_timer(&S_back_title_timer, play);

                    if ((sAdo_BgmFadeoutCheck() == 1) || (S_back_title_timer <= 0.0f)) {
                        Game_play_change_scene_move_end(play);
                    } else {
                        wipet = TRUE;
                    }
                    break;
            }
            if (!wipet) {
                play->fb_fade_type = FADE_TYPE_NONE;
            }
        }
    } else {
        wipe->wipe_procs.move_proc(&wipe->wipe_data, game_GameFrame);
    }
}

static void Game_play_fbdemo_wipe_proc(GAME_PLAY* play) {
    static PLAY_WIPE_PROC wipe_proc[] = { (PLAY_WIPE_PROC)none_proc1, Game_play_fbdemo_wipe_create,
                                          Game_play_fbdemo_wipe_init, Game_play_fbdemo_wipe_move };

    if ((play->fb_wipe_mode == WIPE_MODE_NONE) && (play->fb_fade_type != FADE_TYPE_NONE)) {
        play->fb_wipe_mode = WIPE_MODE_CREATE;
    }

    wipe_proc[play->fb_wipe_mode](play);
}

static Gfx* game_play_set_fog(GAME_PLAY* play, Gfx* gfx) {
    return gfx_set_fog_nosync(gfx, play->global_light.fogColor[0], play->global_light.fogColor[1],
                              play->global_light.fogColor[2], 0, play->global_light.fogNear, play->global_light.fogFar);
}

static void Game_play_fbdemo_proc(GAME_PLAY* play) {
    switch (play->fb_mode) {
        case FBDEMO_MODE_INIT:
            if (fbdemo_init(&fbdemo, 10, 7) == 0) {
                play->fb_mode = FBDEMO_MODE_NONE;
            } else {
                play->fb_mode = FBDEMO_MODE_MOVE;
                SetGameFrame(1);
            }
            break;

        case FBDEMO_MODE_MOVE:
            fbdemo_move(&fbdemo);
            break;
    }
}

extern void play_cleanup(GAME* game) {
    GAME_PLAY* play = (GAME_PLAY*)game;
#ifdef TARGET_PC
    pc_rolling_world_set_camera(0, 0,0,0, 0,0,0, 0,1,0, 0,0,0);
#endif

    mMsg_dt(game);
    banti_dt();

    game->graph->taskEndCallback = NULL;
    game->graph->taskEndData = NULL;
    play->submenu.mode = mSM_MODE_IDLE;

    PreRender_cleanup(&play->prerender);
    CollisionCheck_dt(game, &play->collision_check);

    if (play->fb_mode == FBDEMO_MODE_MOVE) {
        fbdemo_cleanup(&fbdemo);
        play->fb_mode = FBDEMO_MODE_NONE;
    }

    if (play->fb_wipe_mode == WIPE_MODE_MOVE) {
        Game_play_fbdemo_wipe_destroy(play);
    }

    Actor_info_dt(&play->actor_info, play);
    mEv_finish(&play->event);
    mNpc_ClearEventNpc();
    mNpc_ClearMaskNpc();

    mSM_submenu_dt(&play->submenu);
    play->submenu_ground_idx = -1;
    mSM_submenu_ovlptr_cleanup(&play->submenu);

    mPlib_Object_Exchange_keep_Player_dt(play);

    mHsRm_GetHuusuiRoom(NULL, Common_Get(player_no));
    mFM_Field_dt();
    mCD_toNextLand();
    mEA_CleanCardDLProgram();

    if (my_malloc_current == &my_malloc_func) {
        my_malloc_current = NULL;
    }

    zelda_CleanupArena();
}

static void VR_Box_ct(GAME_PLAY* play) {
    Global_kankyo_ct((GAME*)play, &play->kankyo);
}

extern void play_init(GAME* game) {
    GAME_PLAY* play = (GAME_PLAY*)game;
    GRAPH* graph = game->graph;
    int type;
    fbdemo_fade* fade;
    int freebytes;
    u32 alloc;
    u32 aligned;
    u32 size;

    game_resize_hyral(game, -Game_play_HYRAL_SIZE); // reserve bytes from gamealloc
    Common_Set(rhythym_updated, 0);

    mFI_ChangeClimate_ForEventNotice();
    mTM_time_init();
    sAdo_Set_ongenpos_refuse_fg(0);
    event_title_flag_on();
    mTD_rtc_set();
    mTM_set_season();
    mPlib_Clear_controller_data_for_title_demo();

    mSM_submenu_ovlptr_init(play);
    mDemo_Init(play);
    mEv_init(&play->event);

    initView(&play->view, graph);
    Init_Camera2(play);
    CollisionCheck_ct(game, &play->collision_check);

    mCoBG_InitMoveBgData();
    mCoBG_InitBlockBgCheckMode();
    mCoBG_InitDecalCircle();

    play->submenu_ground_idx = -1;

    Gameplay_Scene_Read(play, Save_Get(scene_no));

    mSM_submenu_ct(&play->submenu);
    play->submenu.mode = mSM_MODE_IDLE;

    PreRender_init(&play->prerender);
    PreRender_setup_savebuf(&play->prerender, SCREEN_WIDTH * 2, SCREEN_HEIGHT * 2, NULL, NULL, NULL);
    PreRender_setup_renderbuf(&play->prerender, SCREEN_WIDTH * 2, SCREEN_HEIGHT * 2, NULL, NULL);

    play->fb_mode = FBDEMO_MODE_NONE;
    type = WIPE_TYPE_TRIFORCE;

    play->fb_wipe_mode = WIPE_MODE_NONE;
    play->fb_fade_type = FADE_TYPE_IN;

    if (Common_Get(transition.wipe_type) != 0xFF) {
        type = Common_Get(transition.wipe_type);
        Common_Set(transition.wipe_type, 0xFF);
    }

    play->fb_wipe_type = type;

    Pause_ct(&play->pause);
    new_Matrix(game);

    fade = &play->color_fade;

    game->exec = play_main;
    game->cleanup = play_cleanup;
    fbdemo_fade_init(fade);
    fbdemo_fade_settype(fade, 7);
    fbdemo_fade_setcolor_rgba8888(fade, 0xA0A0A0FF);
    fbdemo_fade_startup(fade);

    play->fade_color_value.rgba8888 = 0;

    freebytes = game_getFreeBytes(game);
    alloc = (u32)THA_alloc16(&game->tha, freebytes);
    aligned = ALIGN_NEXT(alloc, 16);
    size = aligned - alloc;

    zelda_InitArena((void*)aligned, freebytes - size);

    if (my_malloc_current == NULL) {
        my_malloc_current = &my_malloc_func;
    }

    mFM_FieldInit(play);
    VR_Box_ct(play);
    mMmd_MakeMuseumDisplayData();
    Actor_info_ct(game, &play->actor_info, play->player_data);
    play->draw_chk_proc = none_proc1;
    mMsg_ct(game);
    mEv_2nd_init(&play->event);
    mTD_player_keydata_init(play);
    Balloon_init(play);
    mNtc_set_auto_nwrite_data();
    banti_ct();
    watch_my_step_ct();
    event_title_flag_off();
    mEA_GetCardDLProgram();
}

static void Game_play_move_fbdemo_not_move(GAME* game) {
    GAME_PLAY* play = (GAME_PLAY*)game;

    game->doing_point = 0;
    game->doing_point_specific = 0x8F;
    game->doing_point = 1;

    mSM_submenu_ctrl(play);

    if (play->submenu.process_status == mSM_PROCESS_WAIT) {
        game->doing_point = 2;
        mDemo_Main(play);
        game->doing_point = 3;
        mEv_run(&play->event);
    }

    game->doing_point = 4;
    mDemo_stock_clear();
    game->doing_point = 5;
    mSc_dmacopy_data_bank(&play->object_exchange);
    game->doing_point = 6;
    mSM_submenu_move(&play->submenu);

    if (play->submenu.process_status == mSM_PROCESS_WAIT) {
        play->game_frame++;
        mVibctl_clr_force_stop(2);
        game->doing_point = 7;
        CollisionCheck_OC(game, &play->collision_check);
        game->doing_point = 8;
        CollisionCheck_clear(game, &play->collision_check);
        game->doing_point = 9;
        game->doing_point = 0;
        game->doing_point_specific = 0x90;
        Actor_info_call_actor(play, &play->actor_info);
        game->doing_point = 0;
        game->doing_point_specific = 0x91;
        game->doing_point = 1;
        mCoBG_CalcTimerDecalCircle();
        game->doing_point = 2;
        mMsg_Main(game);
    } else {
        mVibctl_set_force_stop(2);
    }

    fbdemo_fade_move(&play->color_fade, game_GameFrame);
}

static void Game_play_move(GAME* game) {
    GAME_PLAY* play = (GAME_PLAY*)game;
    int pause;

#ifdef TARGET_PC
    {
        extern int g_pc_paused;
        if (g_pc_paused) return;
    }
#endif

    game->doing_point = 0;
    game->doing_point_specific = 0x8D;
    game->doing_point = 1;
    Game_play_Reset_destiny();
    game->doing_point = 2;

    if (ZURUMODE2_ENABLED()) {
        pause = !Pause_proc(&play->pause, &game->pads[PAD1]);
    } else {
        pause = FALSE;
    }

    game->doing_point = 0;
    game->doing_point_specific = 0x8E;

    if (!pause) {
        game->doing_point = 1;
        Game_play_fbdemo_wipe_proc(play);
        game->doing_point = 2;
        Game_play_fbdemo_proc(play);
        game->doing_point = 3;

        if (play->fb_mode != FBDEMO_MODE_MOVE) {
            Game_play_move_fbdemo_not_move(game);
        }
    }

    if (play->submenu.process_status == mSM_PROCESS_WAIT) {
        evw_anime_add_scroll_phase(&play->game);
        game->doing_point = 0;
        game->doing_point_specific = 0x92;
        game->doing_point = 1;
        Game_play_camera_proc(play);
        game->doing_point = 2;
        mPO_business_proc(play);
        game->doing_point = 3;
        mTRC_move(game);
        game->doing_point = 4;
        Balloon_move(play);
        mEnv_ManagePointLight(play, &play->kankyo, &play->global_light);
    }

    game->doing_point = 0;
    game->doing_point_specific = 0x93;
    game->doing_point = 1;
    Global_kankyo_set(play, &play->kankyo, &play->global_light);
    game->doing_point = 2;
    mEnv_WindMove();
    game->doing_point = 3;
    watch_my_step_move(play);
    game->doing_point = 4;
    banti_move(play);
    game->doing_point = 5;
    title_demo_move(play);
#ifdef TARGET_PC
    {
        extern void pc_tree_test_player_tick(GAME* game);
        extern void pc_trailer_activity_tick(GAME* game);
        pc_tree_test_player_tick(game);
        pc_trailer_activity_tick(game);
    }
#endif
    game->doing_point = 0;
    game->doing_point_specific = 0x95;
}

// @BUG - this function works properly in N64, but not in GC.
// The devs moved blocks (acres) to new display list buffers in GC,
// but forgot to apply fog to those new display list buffers.
static void setupFog(GAME_PLAY* play, GRAPH* graph) {
    OPEN_DISP(graph);

    SET_POLY_OPA_DISP(game_play_set_fog(play, NOW_POLY_OPA_DISP));
    SET_POLY_XLU_DISP(game_play_set_fog(play, NOW_POLY_XLU_DISP));

    #if defined(BUGFIXES) || defined(TARGET_PC)
    // Apply fog to blocks
    SET_BG_OPA_DISP(game_play_set_fog(play, NOW_BG_OPA_DISP));
    SET_BG_XLU_DISP(game_play_set_fog(play, NOW_BG_XLU_DISP));
    #endif

    CLOSE_DISP(graph);
}

static void setupViewer(GAME_PLAY* play) {
    showView(&play->view, VIEW_UPDATE_ALL);
}

static void setupViewMatrix(GAME_PLAY* play, GRAPH* graph1, GRAPH* graph2) {
    OPEN_DISP(graph1);

    Matrix_MtxtoMtxF(&play->view.mtx_viewing, &play->billboard_matrix);
    Matrix_MtxtoMtxF(&play->view.mtx_projection, &play->projection_matrix);
    Skin_Matrix_MulMatrix(&play->projection_matrix, &play->billboard_matrix, &play->projection_matrix);

    play->billboard_matrix.mf[0][3] = 0.0f;
    play->billboard_matrix.mf[1][3] = 0.0f;
    play->billboard_matrix.mf[2][3] = 0.0f;
    play->billboard_matrix.mf[3][0] = 0.0f;
    play->billboard_matrix.mf[3][1] = 0.0f;
    play->billboard_matrix.mf[3][2] = 0.0f;

    Matrix_reverse(&play->billboard_matrix);
    play->billboard_mtx_p = _MtxF_to_Mtx(&play->billboard_matrix, GRAPH_ALLOC_TYPE(graph2, MtxF, 1));
    gSPSegment(NEXT_BG_OPA_DISP, 7, play->billboard_mtx_p);
    gSPSegment(NEXT_POLY_OPA_DISP, 7, play->billboard_mtx_p);

    CLOSE_DISP(graph1);
}

static void copy_efb_to_texture(Gfx** graph, void* buf) {
    u32 dl;

    GXBeginDisplayList(gxbuf, sizeof(gxbuf));
    GXSetTexCopySrc(0, 0, SCREEN_WIDTH * 2, SCREEN_HEIGHT * 2);
    GXSetTexCopyDst(SCREEN_WIDTH * 2, SCREEN_HEIGHT * 2, GX_TF_RGB565, 0);
    GXSetCopyFilter(0, 0, 0, 0);
    GXCopyTex(buf, 0);
    dl = GXEndDisplayList();
    gGXCallDisplayList((*graph)++, gxbuf, dl);
}

static int makeBumpTexture(GAME_PLAY* play, GRAPH* graph1, GRAPH* graph2) {
    Gfx* newdisp;
    Gfx* polydisp;
    Gfx* rect_disp;
    Gfx* fbdemo_disp;
    Gfx* fb_disp;
    Gfx* old_fb;
    Gfx* poly;

    PC_DIAG(3, "makeBumpTexture: enter fb_mode=%d fb_wipe_mode=%d submenu.mode=%d\n",
            play->fb_mode, play->fb_wipe_mode, play->submenu.mode);
    OPEN_DISP(graph1);

    if ((GETREG(HREG, 80) != 10) || (GETREG(HREG, 92) != 0)) {
        newdisp = NOW_POLY_OPA_DISP;
        polydisp = gfxopen(newdisp);

        gSPDisplayList(NEXT_OVERLAY_DISP, polydisp);

#ifdef TARGET_PC
        /* Tell GXSetProjection to skip widescreen aspect correction for
         * transitions (wipes, fades) so they fill the entire screen.
         * See pc_platform.h for how the marker/flag mechanism works. */
        gDPNoOpTag(polydisp++, PC_NOOP_WIDESCREEN_STRETCH);
#endif

        if (play->fb_wipe_mode == WIPE_MODE_MOVE) {
            View view;
            rect rect;

            initView(&view, graph2);
            view.flag = VIEW_UPDATE_ORTHOGRAPHIC | VIEW_UPDATE_SCISSOR;
            rect.top = 0;
            rect.bottom = SCREEN_HEIGHT;
            rect.l = 0;
            rect.r = SCREEN_WIDTH;
            setScissorView(&view, &rect);
            showView1(&view, VIEW_UPDATE_ALL, &polydisp);
            play->fbdemo_wipe.wipe_procs.draw_proc(&play->fbdemo_wipe.wipe_data, &polydisp);
        }

        fbdemo_fade_draw(&play->color_fade, &polydisp);
        fade_rgba8888_draw(&polydisp, play->fade_color_value.rgba8888);

        gSPEndDisplayList(polydisp++);

        gfxclose(newdisp, polydisp);

        SET_POLY_OPA_DISP(polydisp);
    }

    if (play->fb_mode == FBDEMO_MODE_MOVE) {
        fbdemo_disp = NOW_POLY_OPA_DISP;
        fbdemo_draw(&fbdemo, &fbdemo_disp);
        SET_POLY_OPA_DISP(fbdemo_disp);
        return 1;
    }

    if (play->submenu.mode == mSM_MODE_PRERENDER_WAIT) {
        play->submenu.mode = mSM_MODE_PRERENDER_DONE;
        SETREG(SREG, 3, -(GETREG(SREG, 3)));
    } else if (play->submenu.mode >= mSM_MODE_NUM) {
        play->submenu.mode = mSM_MODE_IDLE;
    }

    if (play->submenu.mode == mSM_MODE_PRERENDER_DONE) {
        poly = NOW_POLY_OPA_DISP;

#ifdef TARGET_PC
        /* The prerendered background is a fullscreen textured rect that goes
         * through ortho projection — enable stretch so it fills widescreen. */
        gDPNoOpTag(poly++, PC_NOOP_WIDESCREEN_STRETCH);
#endif
        gDPPipeSync(poly++);
        rect_disp = gfx_rect_moji(poly++);
        gDPSetOtherMode(rect_disp++,
                        G_AD_PATTERN | G_CD_MAGICSQ | G_CK_NONE | G_TC_CONV | G_TF_POINT | G_TT_NONE | G_TL_TILE |
                            G_TD_CLAMP | G_TP_NONE | G_CYC_COPY | G_PM_NPRIMITIVE,
                        G_AC_NONE | G_ZS_PIXEL | G_RM_NOOP | G_RM_NOOP2);
        gDPSetTextureImage_Dolphin(rect_disp++, G_IM_FMT_I, G_IM_SIZ_16b, (2*SCREEN_HEIGHT), (2*SCREEN_WIDTH), prbuf);
        gDPSetTile_Dolphin(rect_disp++, G_DOLPHIN_TLUT_DEFAULT_MODE, 0, 0, 0, 0, 0, 0);
        gSPTextureRectangle(rect_disp++, 0, 0, ((2*SCREEN_WIDTH) - 1) << 2, ((2*SCREEN_HEIGHT) - 1) << 2, G_TX_RENDERTILE, 0, 0, (256) << G_TEXTURE_IMAGE_FRAC,
                            (256) << G_TEXTURE_IMAGE_FRAC);
#ifdef TARGET_PC
        /* Disable stretch so the inventory overlay UI gets 4:3 correction. */
        gDPNoOpTag(rect_disp++, PC_NOOP_WIDESCREEN_STRETCH_OFF);
#endif

        SET_POLY_OPA_DISP(rect_disp);
        return 1;
    }

    if ((GETREG(HREG, 80) != 10) || (GETREG(HREG, 85) != 0)) {
        PC_DIAG(3, "makeBumpTexture: before Actor_info_draw_actor\n");
        Actor_info_draw_actor(play, &play->actor_info);
        PC_DIAG(3, "makeBumpTexture: Actor draw done, Camera2...\n");
        Camera2_draw(play);
        mMsg_Draw((GAME*)play);
    }

    if ((GETREG(HREG, 80) != 10) || (GETREG(HREG, 93) != 0)) {
        Debug_Display_output(play);
    }

    if ((play->submenu.mode == mSM_MODE_PRERENDER_INIT) || (play->fb_mode == FBDEMO_MODE_CREATE)) {
        old_fb = NOW_POLY_OPA_DISP;
        fb_disp = gfxopen(old_fb);

        gSPDisplayList(NEXT_LIGHT_DISP, fb_disp);
        copy_efb_to_texture(&fb_disp, &prbuf);
        gSPEndDisplayList(fb_disp++);

        gfxclose(old_fb, fb_disp);

        SET_POLY_OPA_DISP(fb_disp);

        if (play->submenu.mode == mSM_MODE_PRERENDER_INIT) {
            play->submenu.mode = mSM_MODE_PRERENDER_WAIT;
            SETREG(SREG, 3, -(GETREG(SREG, 3)));
        } else {
            play->fb_mode = FBDEMO_MODE_INIT;
        }
        return 1;
    }

    CLOSE_DISP(graph1);

    return 1;
}

static void draw_version(GRAPH* graph) {
    JW_JUTReport(0x82, 0x172, 1, "[CopyDate:%.19s]", boot_copyDate);
    JW_JUTReport(0x82, 0x180, 1, "[Date:%s]", &__DateTime__);
    JW_JUTReport(0x82, 0x18E, 1, "[Creator:%s]", &__Creator__);
}

#ifdef TARGET_PC
#include <math.h>
#include "lb_reki.h"
#include "pc_donor_sky.c_inc"
#include "pc_donor_environment.c_inc"
extern void pc_gx_texture_invalidate_image(const void* data);
static u8 pc_cloud_image[PC_DONOR_CLOUD_WIDTH * PC_DONOR_CLOUD_HEIGHT * 4] ATTRIBUTE_ALIGN(32);
static u8 pc_moon_image[32*32*4] ATTRIBUTE_ALIGN(32);
static u8 pc_moon_halo_image[64*64*4] ATTRIBUTE_ALIGN(32);
static int pc_moon_halo_offset;

static void Game_play_prepare_moon(void) {
    static int last_date = -1;
    lbRTC_ymd_c date, lunar;
    int key, tx, ty, x, y, dst = 0;
    float angle;
    date.year = Common_Get(time.rtc_time.year);
    date.month = Common_Get(time.rtc_time.month);
    date.day = Common_Get(time.rtc_time.day);
    key = date.year*512+date.month*32+date.day;
    if (key == last_date) return;
    last_date = key;
    /* Use the host game's actual lunar calendar, not a fixed reference phase.
     * This is an adaptation; donor runtime phase scheduling is not decoded. */
    if (!lbRk_ToKyuuReki(&lunar, &date)) lunar.day = 1;
    angle = (lunar.day-1)*(6.28318530718f/29.53059f);
    {
        /* Source bg_moon_nml animation, moonlight_mdl X over29frames. */
        static const float offsets[30] = {-24,-24,-24,-24,-21,-18,-13,-8,-5.3332f,-2.6664f,
            0,0,0,0,0,0,0,0,0,0,0,2.6664f,5.3332f,8,13,18,21,24,24,24};
        int frame=lunar.day-1;
        if (frame<0) frame=0;
        if (frame>29) frame=29;
        pc_moon_halo_offset=(int)(offsets[frame]*34.0f/64.0f);
    }
    pc_gx_texture_invalidate_image(pc_moon_image);
    memcpy(pc_moon_image, pc_donor_moon_tex, sizeof(pc_moon_image));
    for (ty=0;ty<32;ty+=4) for (tx=0;tx<32;tx+=4) {
        for (y=0;y<4;y++) for (x=0;x<4;x++) {
            float nx=(tx+x-15.5f)/15.5f, ny=(ty+y-15.5f)/15.5f;
            float z2=1.0f-nx*nx-ny*ny;
            float lit=z2>0.0f ? nx*sinf(angle)-sqrtf(z2)*cosf(angle) : -1.0f;
            if (lit <= 0.0f) pc_moon_image[dst] = 0;
            dst += 2;
        }
        dst += 32;
    }
    pc_gx_texture_invalidate_image(pc_moon_halo_image);
    memcpy(pc_moon_halo_image, pc_donor_moon_halo_tex, sizeof(pc_moon_halo_image));
    dst=0;
    for (ty=0;ty<64;ty+=4) for (tx=0;tx<64;tx+=4) {
        for (y=0;y<4;y++) for (x=0;x<4;x++) {
            float nx=(tx+x-31.5f)/31.5f, ny=(ty+y-31.5f)/31.5f;
            float z2=1.0f-nx*nx-ny*ny;
            float lit=z2>0.0f ? nx*sinf(angle)-sqrtf(z2)*cosf(angle) : -1.0f;
            if (lit <= 0.0f) pc_moon_halo_image[dst]=0;
            dst+=2;
        }
        dst+=32;
    }
}

static float Game_play_cloud_sample(float u, float v) {
    float x = u*128.0f-0.5f, y = (1.0f-v)*128.0f-0.5f;
    int ix = (int)floorf(x), iy = (int)floorf(y);
    float fx = x-ix, fy = y-iy;
    float a = pc_donor_cloud_mask[(iy&127)*128+(ix&127)];
    float b = pc_donor_cloud_mask[(iy&127)*128+((ix+1)&127)];
    float c = pc_donor_cloud_mask[((iy+1)&127)*128+(ix&127)];
    float d = pc_donor_cloud_mask[((iy+1)&127)*128+((ix+1)&127)];
    return (a+(b-a)*fx)*(1.0f-fy)+(c+(d-c)*fx)*fy;
}

static void Game_play_prepare_clouds(GAME_PLAY* play, float wet_blend, const u8* light, const u8* shade) {
    static int previous_cutoff = -1;
    static float scroll_x, scroll_y, update_frames;
    static int reported_cloud_coverage;
    /* Verified cloud actor 0x22eda0: C1.a = 1 - weather density.
     * Donor clear-with-clouds density=.2, rain/snow density=1. Native weather
     * has no separate cloudless enum, so clear uses the cloudy-clear state. */
    int cutoff = (int)(204.0f * (1.0f-wet_blend) + 0.5f);
    int heavy = Common_Get(weather_intensity) == mEnv_WEATHER_INTENSITY_HEAVY;
    float uv_scale = 1.0f+(heavy ? 0.5f : 1.0f)*wet_blend;
    float frames = play->game.graph->dt_num_60fps_frames*0.5f;
    int tx, ty, x, y, dst = 0;
    int alpha_sum = 0, alpha_max = 0;
    /* Original ordinary-cloud actor advances these translations each 30 Hz
     * simulation frame. Clear-cloudy -> ordinary rain/snow follows the native
     * weather transition; native heavy intensity selects donor heavy rain/snow. */
    scroll_x += (0.0001f+0.0004f*wet_blend)*frames;
    scroll_y += (0.0005f+(heavy ? 0.0005f : 0.0003f)*wet_blend)*frames;
    scroll_x = fmodf(scroll_x,1.0f/uv_scale);
    scroll_y = fmodf(scroll_y,1.0f/uv_scale);
    update_frames += frames;
    /* Reconstruct at 10 Hz; phase still advances at the simulation rate. */
    if (cutoff == previous_cutoff && update_frames < 3.0f) return;
    update_frames = fmodf(update_frames,3.0f);
    pc_gx_texture_invalidate_image(pc_cloud_image);
    previous_cutoff = cutoff;
    /* Verified donor alpha: clamp(4*(density-cutoff))*vertexAlpha.
     * The cutoff now comes from the recovered weather density, not the
     * unrelated environment scalar formerly used as an approximation.
     * Evaluate the original RGB interpolation here too, so the GPU needs only
     * one texture pass regardless of the preceding moon/halo combiner. */
    for (ty = 0; ty < PC_DONOR_CLOUD_HEIGHT; ty += 4) {
        for (tx = 0; tx < PC_DONOR_CLOUD_WIDTH; tx += 4) {
            int tile_density[16];
            for (y = 0; y < 4; ++y) for (x = 0; x < 4; ++x) {
                int src = (ty+y)*PC_DONOR_CLOUD_WIDTH+tx+x;
                float u = pc_donor_cloud_uv[src*2]*(uv_scale/4096.0f);
                float v = pc_donor_cloud_uv[src*2+1]*(uv_scale/4096.0f);
                /* CGFX translation is subtracted in its cached UV matrix.
                 * Sampler1 keeps the source one-degree center rotation and
                 * scrolls oppositely in X. Both use the same original mask. */
                float first = Game_play_cloud_sample(u-scroll_x*uv_scale,v-scroll_y*uv_scale);
                float second = Game_play_cloud_sample(
                    .9998477101f*u-.0174524058f*v+.0088023543f+scroll_x*uv_scale,
                    .0174524058f*u+.9998477101f*v-.0086500645f-scroll_y*uv_scale);
                int d = (int)((first+second)*0.5f+0.5f);
                int alpha = (d-cutoff)*4;
                tile_density[y*4+x] = d;
                if (alpha < 0) alpha = 0;
                if (alpha > 255) alpha = 255;
                alpha = (alpha*pc_donor_cloud_coverage[src]+127)/255;
                alpha_sum += alpha;
                if (alpha > alpha_max) alpha_max = alpha;
                pc_cloud_image[dst++] = alpha;
                pc_cloud_image[dst++] = (shade[0]*(255-d)+light[0]*d+127)/255;
            }
            for (y = 0; y < 4; ++y) for (x = 0; x < 4; ++x) {
                int d = tile_density[y*4+x];
                pc_cloud_image[dst++] = (shade[1]*(255-d)+light[1]*d+127)/255;
                pc_cloud_image[dst++] = (shade[2]*(255-d)+light[2]*d+127)/255;
            }
        }
    }
    if (!reported_cloud_coverage) {
        OSReport("[DonorCloud] cutoff=%d alphaMean=%.2f alphaMax=%d palette=%d,%d,%d/%d,%d,%d\n",
            cutoff, (float)alpha_sum/(PC_DONOR_CLOUD_WIDTH*PC_DONOR_CLOUD_HEIGHT), alpha_max,
            light[0],light[1],light[2],shade[0],shade[1],shade[2]);
        reported_cloud_coverage = 1;
    }
}

static void Game_play_draw_rolling_sky(GAME_PLAY* play) {
    GRAPH* graph = play->game.graph;
    u8 zenith[3], horizon[3], cloud_light[3], cloud_shade[3];
    int seconds, clear, night_alpha;
    float wet_blend;
    if (g_pc_rolling_world_strength <= 0.0f ||
        (Save_Get(scene_no) != SCENE_FG && Save_Get(scene_no) != SCENE_FIELD_TOOL)) return;
    seconds = Common_Get(time.rtc_time.hour)*3600 + Common_Get(time.rtc_time.min)*60 + Common_Get(time.rtc_time.sec);
    clear = Common_Get(weather) != mEnv_WEATHER_RAIN && Common_Get(weather) != mEnv_WEATHER_SNOW;
    wet_blend = pc_donor_weather_blend();
    if (wet_blend < 0.0f) wet_blend = 0.0f;
    if (wet_blend > 1.0f) wet_blend = 1.0f;
    pc_donor_environment_color(zenith, PC_DONOR_SKY_ZENITH, seconds, wet_blend);
    pc_donor_environment_color(horizon, PC_DONOR_SKY_HORIZON, seconds, wet_blend);
    pc_donor_environment_color(cloud_light, PC_DONOR_CLOUD_LIGHT, seconds, wet_blend);
    pc_donor_environment_color(cloud_shade, PC_DONOR_CLOUD_SHADE, seconds, wet_blend);
    Game_play_prepare_clouds(play, wet_blend, cloud_light, cloud_shade);
    night_alpha = seconds >= 20*3600 || seconds < 5*3600 ? 255 :
                  seconds >= 19*3600 ? (seconds-19*3600)*255/3600 :
                  seconds < 6*3600 ? (6*3600-seconds)*255/3600 : 0;
    night_alpha = (int)(night_alpha * (1.0f-wet_blend));
    {
        static int sky_reported;
        if (!sky_reported) {
            OSReport("[RollingWorld] Hourly donor sky and clouds; time=%02d:%02d clear=%d cutoff=%.3f\n",
                seconds/3600, (seconds/60)%60, clear, 0.8f*(1.0f-wet_blend));
            sky_reported = 1;
        }
    }
    /* Before the ground, after the camera viewport is established. The sky
     * writes no depth, is not world-bent, and only belongs to outdoor views. */
    OPEN_DISP(graph);
    gDPNoOpTag(NOW_BG_OPA_DISP++, PC_NOOP_WIDESCREEN_STRETCH);
    gDPPipeSync(NOW_BG_OPA_DISP++);
    gSPClearGeometryMode(NOW_BG_OPA_DISP++, G_ZBUFFER | G_SHADE | G_CULL_BOTH | G_FOG |
                        G_LIGHTING | G_TEXTURE_GEN | G_TEXTURE_GEN_LINEAR | G_LOD | G_SHADING_SMOOTH);
    gDPSetOtherMode(NOW_BG_OPA_DISP++,
                   G_AD_DISABLE | G_CD_MAGICSQ | G_CK_NONE | G_TC_FILT | G_TF_BILERP |
                   G_TT_NONE | G_TL_TILE | G_TD_CLAMP | G_TP_NONE | G_CYC_1CYCLE | G_PM_1PRIMITIVE,
                   G_AC_NONE | G_ZS_PIXEL | G_RM_CLD_SURF | G_RM_CLD_SURF2);
    gDPSetCombineMode(NOW_BG_OPA_DISP++, G_CC_BLENDPEDECALA, G_CC_BLENDPEDECALA);
    gDPSetPrimColor(NOW_BG_OPA_DISP++, 0, 0, zenith[0], zenith[1], zenith[2], 255);
    gDPSetEnvColor(NOW_BG_OPA_DISP++, horizon[0], horizon[1], horizon[2], 255);
    gSPTexture(NOW_BG_OPA_DISP++, 0xFFFF, 0xFFFF, 0, G_TX_RENDERTILE, G_ON);
    gDPSetTextureImage_Dolphin(NOW_BG_OPA_DISP++, G_IM_FMT_RGBA, G_IM_SIZ_32b,
                               128, 256, pc_donor_sky_tex); /* Runtime macro: height, width. */
    gDPSetTile_Dolphin(NOW_BG_OPA_DISP++, G_DOLPHIN_TLUT_DEFAULT_MODE, 0, 0, GX_CLAMP, GX_CLAMP, 0, 0);
    gDPSetTileSize_Dolphin(NOW_BG_OPA_DISP++, G_TX_RENDERTILE, 0, 0, 256, 128);
    /* Sample the source mask's upper-to-center slope down to the visible
     * horizon. Sampling its far outer edges here would turn the horizon back
     * into the zenith color. This viewport crop remains a camera adaptation;
     * the mask and clock-driven color endpoints come from the donor. */
    gSPTextureRectangle(NOW_BG_OPA_DISP++, 0, 0, 640 << 2, 480 << 2,
                        G_TX_RENDERTILE, 80*32, 24*32, 154, 164);
    /* Actual donor star/noise textures, clock-faded behind the cloud layer. */
    if (night_alpha > 0) {
        float t = (seconds < 12*3600 ? seconds+24*3600 : seconds)-18*3600;
        int mx, my;
        t /= 12*3600.0f;
        mx = 112+(int)(400*t);
        my = 168-(int)(140*sinf(t*3.14159265359f));
        Game_play_prepare_moon();
        gDPPipeSync(NOW_BG_OPA_DISP++);
        gDPSetCombineMode(NOW_BG_OPA_DISP++, G_CC_MODULATEIA_PRIM, G_CC_MODULATEIA_PRIM);
        gDPSetPrimColor(NOW_BG_OPA_DISP++, 0, 0, 255, 255, 255, night_alpha*60/255);
        gDPSetTextureImage_Dolphin(NOW_BG_OPA_DISP++, G_IM_FMT_RGBA, G_IM_SIZ_32b, 256, 256, pc_donor_stars_tex);
        gDPSetTile_Dolphin(NOW_BG_OPA_DISP++, G_DOLPHIN_TLUT_DEFAULT_MODE, 0, 0, GX_REPEAT, GX_REPEAT, 0, 0);
        gDPSetTileSize_Dolphin(NOW_BG_OPA_DISP++, G_TX_RENDERTILE, 0, 0, 256, 256);
        /* Source star dome UV range0..1, .5..1 withscale4 gives4x2tiles. */
        gSPTextureRectangle(NOW_BG_OPA_DISP++, 0, 0, 640<<2, 480<<2, G_TX_RENDERTILE, 0, 0, 1638, 1092);
        gDPPipeSync(NOW_BG_OPA_DISP++);
        gDPSetPrimColor(NOW_BG_OPA_DISP++, 0, 0, 255, 255, 255, night_alpha);
        /* Donor m_moon_light uses SrcAlpha + One additive blending. Its
         * original glow mesh is132 units tall versus64for the moon itself. */
        gDPSetRenderMode(NOW_BG_OPA_DISP++, IM_RD | CVG_DST_SAVE | FORCE_BL | ZMODE_OPA |
                        GBL_c1(G_BL_CLR_IN,G_BL_A_IN,G_BL_CLR_MEM,G_BL_1),
                        IM_RD | CVG_DST_SAVE | FORCE_BL | ZMODE_OPA |
                        GBL_c2(G_BL_CLR_IN,G_BL_A_IN,G_BL_CLR_MEM,G_BL_1));
        gDPSetTextureImage_Dolphin(NOW_BG_OPA_DISP++, G_IM_FMT_RGBA, G_IM_SIZ_32b, 64,64,pc_moon_halo_image);
        /* Dolphin SETTILE binds the pending image to the render tile; changing
         * only its size would leave the crater texture bound for this pass. */
        gDPSetTile_Dolphin(NOW_BG_OPA_DISP++, G_DOLPHIN_TLUT_DEFAULT_MODE, 0, 0, GX_CLAMP, GX_CLAMP, 0, 0);
        gDPSetTileSize_Dolphin(NOW_BG_OPA_DISP++, G_TX_RENDERTILE, 0,0,64,64);
        gSPTextureRectangle(NOW_BG_OPA_DISP++, (mx-18+pc_moon_halo_offset)<<2,(my-18)<<2,
                            (mx+52+pc_moon_halo_offset)<<2,(my+52)<<2,G_TX_RENDERTILE,0,0,936,936);
        gDPPipeSync(NOW_BG_OPA_DISP++);
        gDPSetRenderMode(NOW_BG_OPA_DISP++, G_RM_CLD_SURF,G_RM_CLD_SURF2);
        /* Draw the dated crater disk over its glow. Explicitly restore the
         * ordinary blend and bind the disk, including the Dolphin tile. */
        gDPSetTextureImage_Dolphin(NOW_BG_OPA_DISP++, G_IM_FMT_RGBA, G_IM_SIZ_32b, 32, 32, pc_moon_image);
        gDPSetTile_Dolphin(NOW_BG_OPA_DISP++, G_DOLPHIN_TLUT_DEFAULT_MODE, 0, 0, GX_CLAMP, GX_CLAMP, 0, 0);
        gDPSetTileSize_Dolphin(NOW_BG_OPA_DISP++, G_TX_RENDERTILE, 0, 0, 32, 32);
        gSPTextureRectangle(NOW_BG_OPA_DISP++, mx<<2, my<<2, (mx+34)<<2, (my+34)<<2,
                            G_TX_RENDERTILE, 0, 0, 964, 964);
    }
    gDPPipeSync(NOW_BG_OPA_DISP++);
    /* Verified donor C2 alpha is one for cloudy-clear, rain and snow. The
     * recovered density cutoff and sampled mask supply cloud translucency. */
    gDPSetCycleType(NOW_BG_OPA_DISP++, G_CYC_1CYCLE);
    gDPSetRenderMode(NOW_BG_OPA_DISP++, G_RM_CLD_SURF, G_RM_CLD_SURF2);
    gDPSetCombineMode(NOW_BG_OPA_DISP++, G_CC_DECALRGBA, G_CC_DECALRGBA);
    gDPSetTextureImage_Dolphin(NOW_BG_OPA_DISP++, G_IM_FMT_RGBA, G_IM_SIZ_32b,
                               PC_DONOR_CLOUD_HEIGHT, PC_DONOR_CLOUD_WIDTH, pc_cloud_image);
    gDPSetTile_Dolphin(NOW_BG_OPA_DISP++, G_DOLPHIN_TLUT_DEFAULT_MODE, 0, 0, GX_CLAMP, GX_CLAMP, 0, 0);
    gDPSetTileSize_Dolphin(NOW_BG_OPA_DISP++, G_TX_RENDERTILE, 0, 0, PC_DONOR_CLOUD_WIDTH, PC_DONOR_CLOUD_HEIGHT);
    gSPTextureRectangle(NOW_BG_OPA_DISP++, 0, 0, 640 << 2, 480 << 2,
                        G_TX_RENDERTILE, 0, 0, PC_DONOR_CLOUD_WIDTH*1024/640, PC_DONOR_CLOUD_HEIGHT*1024/480);
    gDPPipeSync(NOW_BG_OPA_DISP++);
    gDPNoOpTag(NOW_BG_OPA_DISP++, PC_NOOP_WIDESCREEN_STRETCH_OFF);
    gSPDisplayList(NOW_BG_OPA_DISP++, RSP_RDP_clear_data);
    CLOSE_DISP(graph);
}
#endif

static void Game_play_draw(GAME_PLAY* play) {
    GRAPH* graph = play->game.graph;
    u8 fill_r = 0;
    u8 fill_g = 0;
    u8 fill_b = 0;

    // @BUG - when removing display list segment function present in N64, the devs went slightly too far
    // and removed setting the background fill color while in the main field area.
#if defined(BUGFIXES) || defined(TARGET_PC)
    if (Common_Get(field_type) == mFI_FIELDTYPE2_FG && mEv_CheckTitleDemo() != mEv_TITLEDEMO_STAFFROLL) {
        fill_r = play->kankyo.base_light.background_color[0];
        fill_g = play->kankyo.base_light.background_color[1];
        fill_b = play->kankyo.base_light.background_color[2];
    }
#endif

    DisplayList_initialize(graph, fill_r, fill_g, fill_b, &play->game);
    PC_DIAG(3, "Game_play_draw: DL_init done\n");

    if ((GETREG(HREG, 80) != 10) || (GETREG(HREG, 82) != 0)) {
        setupFog(play, graph);
        PC_DIAG(3, "Game_play_draw: fog done\n");
        setupViewer(play);
        PC_DIAG(3, "Game_play_draw: viewer done\n");
        setupViewMatrix(play, graph, graph);
        PC_DIAG(3, "Game_play_draw: viewMtx done\n");
#ifdef TARGET_PC
        /* showPerspectiveView has now emitted the viewport and camera setup
         * on BG_OPA. Draw the backdrop after that setup but before acres. */
        Game_play_draw_rolling_sky(play);
#endif

        if ((makeBumpTexture(play, graph, graph) == 1) && ((GETREG(HREG, 80) != 10) || (GETREG(HREG, 89) != 0))) {
            PC_DIAG(3, "Game_play_draw: bump done, drawing\n");
            watch_my_step_draw(play);
            banti_draw(play);
            mSM_submenu_draw(&play->submenu, (GAME*)play);
        }
    }
    if (zurumode_flag != 0) {
        switch (mEv_CheckTitleDemo()) {
            case mEv_TITLEDEMO_STAFFROLL:
            case mEv_TITLEDEMO_LOGO:
            default:
                draw_version(graph);
                break;

            case mEv_TITLEDEMO_NONE:
                break;
        }
    }
}

extern void play_main(GAME* game) {
    GAME_PLAY* play = (GAME_PLAY*)game;

    PC_DIAG(5, "play_main: enter scene=%d frame=%d\n", play->scene_id, play->game_frame);
    game->doing_point = 0;
    game->doing_point_specific = 0x6E;
    fqrand();
    game->doing_point = 0;
    game->doing_point_specific = 0x78;
    mCon_main(game);
    game->doing_point = 0;
    game->doing_point_specific = 0x82;
    Debug_Display_init();

    if ((GETREG(HREG, 80) == 10) && (GETREG(HREG, 94) != 10)) {
        SETREG(HREG, 81, 1);
        SETREG(HREG, 82, 1);
        SETREG(HREG, 83, 1);
        SETREG(HREG, 84, 3);
        SETREG(HREG, 85, 1);
        SETREG(HREG, 86, 1);
        SETREG(HREG, 87, 1);
        SETREG(HREG, 88, 1);
        SETREG(HREG, 89, 1);
        SETREG(HREG, 90, 15);
        SETREG(HREG, 91, 1);
        SETREG(HREG, 92, 1);
        SETREG(HREG, 93, 1);
        SETREG(HREG, 94, 10);
    }

    game->doing_point = 0;
    game->doing_point_specific = 0x8C;

    if ((GETREG(HREG, 80) != 10) || (GETREG(HREG, 81) != 0)) {
        Game_play_move(game);
    }
    game->doing_point = 0;
    game->doing_point_specific = 0xAA;
    Game_play_draw(play);

    game->doing_point = 0;
    game->doing_point_specific = 0xB4;

    {
        GRAPH* graph = game->graph;
        game_debug_draw_last(game, graph);
        game_draw_last(graph);
    }

    game->doing_point = 0;
    game->doing_point_specific = 0XBe;
}

static void Gameplay_Scene_Init(GAME_PLAY* play) {
    play->player_data = NULL;
    play->actor_data_num = 0;
    play->ctrl_actor_data_num = 0;
    play->obj_bank_data_num = 0;
    play->_20A8 = 0;

    mSc_data_bank_ct(play, &play->object_exchange);
    Global_light_ct(&play->global_light);
    Door_info_ct(&play->door_info);
    common_data_clear();
    Scene_ct(play, play->current_scene_data);
    mSc_decide_exchange_bank(&play->object_exchange);
}

static u8 mPl_SceneNo2SoundRoomType(int scene) {
    switch (scene) {
        case SCENE_MY_ROOM_S:
            return 1;

        case SCENE_NPC_HOUSE:
        case SCENE_SHOP0:
        case SCENE_BROKER_SHOP:
        case SCENE_POST_OFFICE:
        case SCENE_BUGGY:
        case SCENE_MY_ROOM_M:
        case SCENE_KAMAKURA:
        case SCENE_MY_ROOM_LL2:
        case SCENE_TENT:
            return 2;

        case SCENE_MY_ROOM_L:
        case SCENE_CONVENI:
        case SCENE_SUPER:
        case SCENE_DEPART:
        case SCENE_DEPART_2:
        case SCENE_MY_ROOM_LL1:
        case SCENE_COTTAGE_MY:
        case SCENE_POLICE_BOX:
            return 3;

        default:
            return 0;
    }
}

static void Gameplay_Scene_Read(GAME_PLAY* play, s16 idx) {
    static Scene_Word_u* scene_word_data[SCENE_NUM] = {
        test01_info,
        test02_info,
        test03_info,
        water_test_info,
        test_step01_info,
        test04_info,
        npc_room01_info,
        test_fd_npc_land_info,
        field_tool_field_info,
        shop01_info,
        BG_TEST01_info,
        BG_TEST01_XLU_info,
        broker_shop_info,
        fg_tool_in_info,
        post_office_info,
        start_demo1_info,
        start_demo2_info,
        police_box_info,
        buggy_info,
        player_select_info,
        player_room_s_info,
        player_room_m_info,
        player_room_l_info,
        shop02_info,
        shop03_info,
        shop04_1f_info,
        test05_info,
        PLAYER_SELECT2_info,
        PLAYER_SELECT3_info,
        shop04_2f_info,
        event_notification_info,
        kamakura_info,
        field_tool_field_info,
        title_demo_info,
        PLAYER_SELECT4_info,
        museum_entrance_info,
        museum_picture_info,
        museum_fossil_info,
        museum_insect_info,
        museum_fish_info,
        player_room_ll1_info,
        player_room_ll2_info,
        p_room_bm_s_info,
        p_room_bm_m_info,
        p_room_bm_l_info,
        p_room_bm_ll1_info,
        NEEDLEWORK_info,
        player_room_island_info,
        npc_room_island_info,
        start_demo3_info,
        lighthouse_info,
        tent_info,
    };

    Scene_data_status_c* current = &scene_data_status[idx];

    current->unk13 = 0;
    play->scene_data_status = current;
    play->scene_id = idx;
    play->current_scene_data = scene_word_data[idx];
    current->unk13 = 0;
    Gameplay_Scene_Init(play);
    sAdo_RoomType(mPl_SceneNo2SoundRoomType(Save_Get(scene_no)));
}
