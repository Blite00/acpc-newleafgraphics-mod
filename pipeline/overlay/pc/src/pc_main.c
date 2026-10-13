/* pc_main.c - PC entry point: SDL2/GL init and boot sequence */
#include "pc_platform.h"
#include "pc_gx_internal.h"
#include "pc_texture_pack.h"
#include "pc_settings.h"
#include "pc_keybindings.h"
#include "pc_assets.h"
#include "pc_disc.h"
#include "pc_controls.h"
#include "pc_typing.h"
#include "pc_pause_menu.h"
#include "pc_settings_menu.h"
#include "pc_profiler.h"
#include "pc_trailer_capture.h"
#include "m_kankyo.h"
#include <math.h>
#ifdef _WIN32
#include <windows.h>
#endif

/* prefer discrete GPU on laptops */
#ifdef _WIN32
__declspec(dllexport) unsigned long NvOptimusEnablement = 1;
__declspec(dllexport) int AmdPowerXpressRequestHighPerformance = 1;
#endif

SDL_Window*   g_pc_window = NULL;
SDL_GLContext  g_pc_gl_context = NULL;
int           g_pc_running = 1;
int           g_pc_frame_limit_override = -1;
int           g_pc_speedhack_enabled = 0;
int           g_pc_verbose = 0;
int           g_pc_time_override = -1; /* -1=system clock, 0-23=override hour */
int           g_pc_min_override = -1; /* -1=system clock, 0-59=override minute */
int           g_pc_sec_override = -1; /* -1=system clock, 0-59=override second */
int           g_pc_date_month = -1; /* -1=system clock, 1-12=override month */
int           g_pc_date_day = -1; /* -1=system clock, 1-31=override day */
int           g_pc_date_year = -1; /* -1=system clock, else override year */
int           g_pc_weather_override = -1;
int           g_pc_weather_intensity_override = mEnv_WEATHER_INTENSITY_HEAVY;
int           g_pc_window_w = PC_SCREEN_WIDTH;
int           g_pc_window_h = PC_SCREEN_HEIGHT;
int           g_pc_widescreen_stretch = 0;
static const char* g_pc_capture_path = NULL;
static int g_pc_capture_after = 120;
int g_pc_tree_world = 1; /* Deployed donor graphics are enabled in normal play. */
int g_pc_tree_test_town = 0;
float g_pc_test_spawn_x = 2117.0f, g_pc_test_spawn_z = 1488.0f;
int g_pc_terrain_normals = 1;
float g_pc_rolling_world_strength = 1.0f;
int g_pc_tree_self_test = 0;

/* exe image range -- used by seg2k0 to distinguish pointers from segment addresses */
unsigned int pc_image_base = 0;
unsigned int pc_image_end  = 0;

void pc_platform_init(void) {
    extern int g_pc_tree_viewer;
#ifdef _WIN32
    SetProcessDPIAware();
    SDL_SetHint(SDL_HINT_WINDOWS_INTRESOURCE_ICON, "1");
#endif
    printf("[PC] Initializing SDL devices%s\n", g_pc_tree_viewer ? " (keyboard-only tree preview)" : "");
    if (SDL_Init(SDL_INIT_VIDEO | SDL_INIT_TIMER | SDL_INIT_AUDIO |
                 ((g_pc_tree_viewer || g_pc_tree_test_town) ? 0 : SDL_INIT_GAMECONTROLLER)) < 0) {
        fprintf(stderr, "SDL_Init failed: %s\n", SDL_GetError());
        exit(1);
    }
    printf("[PC] SDL device initialization complete\n");

    SDL_GL_SetAttribute(SDL_GL_CONTEXT_MAJOR_VERSION, 3);
    SDL_GL_SetAttribute(SDL_GL_CONTEXT_MINOR_VERSION, 3);
    SDL_GL_SetAttribute(SDL_GL_CONTEXT_PROFILE_MASK, SDL_GL_CONTEXT_PROFILE_CORE);
    SDL_GL_SetAttribute(SDL_GL_DOUBLEBUFFER, 1);
    SDL_GL_SetAttribute(SDL_GL_DEPTH_SIZE, 24);
#ifdef PC_ENHANCEMENTS
    if (g_pc_settings.msaa > 0) {
        SDL_GL_SetAttribute(SDL_GL_MULTISAMPLEBUFFERS, 1);
        SDL_GL_SetAttribute(SDL_GL_MULTISAMPLESAMPLES, g_pc_settings.msaa);
    }
#endif

    {
        Uint32 flags = SDL_WINDOW_OPENGL | SDL_WINDOW_SHOWN | SDL_WINDOW_RESIZABLE;
        int win_w = g_pc_settings.window_width;
        int win_h = g_pc_settings.window_height;
        if (g_pc_settings.fullscreen == 1) {
            flags |= SDL_WINDOW_FULLSCREEN;
        } else if (g_pc_settings.fullscreen == 2) {
            flags |= SDL_WINDOW_FULLSCREEN_DESKTOP;
        }
        g_pc_window = SDL_CreateWindow(
            PC_WINDOW_TITLE,
            SDL_WINDOWPOS_CENTERED, SDL_WINDOWPOS_CENTERED,
            win_w, win_h, flags
        );
    }
    if (!g_pc_window) {
        fprintf(stderr, "SDL_CreateWindow failed: %s\n", SDL_GetError());
        SDL_Quit();
        exit(1);
    }

    g_pc_gl_context = SDL_GL_CreateContext(g_pc_window);
    if (!g_pc_gl_context) {
        fprintf(stderr, "SDL_GL_CreateContext failed: %s\n", SDL_GetError());
        SDL_DestroyWindow(g_pc_window);
        SDL_Quit();
        exit(1);
    }

    if (!gladLoadGL((GLADloadfunc)SDL_GL_GetProcAddress)) {
        fprintf(stderr, "gladLoadGL failed\n");
        SDL_GL_DeleteContext(g_pc_gl_context);
        SDL_DestroyWindow(g_pc_window);
        SDL_Quit();
        exit(1);
    }

    SDL_GL_SetSwapInterval(g_pc_settings.vsync);

    pc_platform_update_window_size();

#ifdef PC_ENHANCEMENTS
    if (g_pc_settings.msaa > 0) {
        glEnable(GL_MULTISAMPLE);
    }
#endif

    pc_gx_init();
    pc_texture_pack_init();
#ifdef PC_ENHANCEMENTS
    if (g_pc_settings.preload_textures) {
        pc_texture_pack_preload_all();
    }
#endif
}

extern void PADCleanup(void);

static void pc_speedhack_toggle(void) {
    g_pc_speedhack_enabled = !g_pc_speedhack_enabled;
    if (g_pc_window != NULL) {
        SDL_SetWindowTitle(g_pc_window, g_pc_speedhack_enabled ? "Animal Crossing [5x]" : PC_WINDOW_TITLE);
    }

    if (g_pc_verbose) {
        printf("[PC] speedhack %s\n", g_pc_speedhack_enabled ? "5x" : "off");
    }
}

void pc_platform_shutdown(void) {
    pc_trailer_close();
    pc_audio_shutdown();
    pc_audio_mq_shutdown();
    PADCleanup();
    pc_texture_pack_shutdown();
    pc_gx_shutdown();

    if (g_pc_gl_context) {
        SDL_GL_DeleteContext(g_pc_gl_context);
        g_pc_gl_context = NULL;
    }
    if (g_pc_window) {
        SDL_DestroyWindow(g_pc_window);
        g_pc_window = NULL;
    }
    SDL_Quit();
}

void pc_platform_update_window_size(void) {
    SDL_GL_GetDrawableSize(g_pc_window, &g_pc_window_w, &g_pc_window_h);
    if (g_pc_window_w <= 0) g_pc_window_w = PC_SCREEN_WIDTH;
    if (g_pc_window_h <= 0) g_pc_window_h = PC_SCREEN_HEIGHT;
}

void pc_platform_swap_buffers(void) {
    static int capture_frames = 0;
    pc_gx_draw_pending();
    pc_trailer_frame();
    {
        extern void pc_cc_test_frame(void) __attribute__((weak)); /* dev: PC_CC_TEST screenshots */
        if (pc_cc_test_frame != NULL) pc_cc_test_frame();
        { extern void pc_ctl_dev_frame(void); pc_ctl_dev_frame(); } /* dev: PC_CTL_SHOTS */
    }
    if (g_pc_capture_path && ++capture_frames == g_pc_capture_after) {
        int w, h, y;
        unsigned char* pixels;
        unsigned char* flipped;
        SDL_Surface* surface;
        SDL_GL_GetDrawableSize(g_pc_window, &w, &h);
        pixels = (unsigned char*)malloc((size_t)w * h * 4);
        flipped = (unsigned char*)malloc((size_t)w * h * 4);
        if (pixels && flipped && w > 0 && h > 0) {
            glReadPixels(0, 0, w, h, GL_RGBA, GL_UNSIGNED_BYTE, pixels);
            for (y = 0; y < h; ++y)
                memcpy(flipped + y*w*4, pixels + (h-1-y)*w*4, (size_t)w*4);
            surface = SDL_CreateRGBSurfaceFrom(flipped, w, h, 32, w*4,
                                               0xff, 0xff00, 0xff0000, 0xff000000);
            if (surface) {
                int result = SDL_SaveBMP(surface, g_pc_capture_path);
                printf("[DevCapture] %s: %s (%dx%d)\n", result == 0 ? "Saved" : "FAILED",
                       g_pc_capture_path, w, h);
                SDL_FreeSurface(surface);
            }
        }
        free(pixels);
        free(flipped);
        g_pc_running = 0;
    }
    SDL_GL_SwapWindow(g_pc_window);
}

int pc_platform_poll_events(void) {
    SDL_Event event;

    pc_typing_update();
    { extern void pc_ctl_frame(void); pc_ctl_frame(); } /* PC controls: frame clock */

    while (SDL_PollEvent(&event)) {
        { extern void pc_ctl_input_event(const void*); pc_ctl_input_event(&event); } /* prompt style (pc_controls.c) */
        switch (event.type) {
            case SDL_QUIT:
                g_pc_running = 0;
                return 0;
            case SDL_WINDOWEVENT:
                if (event.window.event == SDL_WINDOWEVENT_SIZE_CHANGED) {
                    pc_platform_update_window_size();
                }
                break;
            case SDL_KEYDOWN:
                /* Keybinding capture eats all input first (works from both
                 * the pause menu and the title Options menu). */
                if (pc_settings_menu_capture_active()) {
                    pc_settings_menu_handle_capture_event(&event);
                    break;
                }
                if (event.key.keysym.sym == SDLK_F3 && !event.key.repeat) {
                    pc_speedhack_toggle();
                    break;
                }
                if (event.key.keysym.sym == SDLK_ESCAPE && !event.key.repeat) {
                    if (g_pc_paused) {
                        pc_pause_menu_handle_event(&event);
                    } else if (!pc_ctl_escape()) { /* back in menus, finish in the editor (pc_controls.c) */
                        pc_pause_menu_toggle();
                    }
                    break;
                }
                if (g_pc_paused) {
                    pc_pause_menu_handle_event(&event);
                    break; /* swallow all keys while paused */
                }
                pc_typing_handle_event(&event);
                break;
            case SDL_MOUSEWHEEL:
                if (!g_pc_paused) pc_ctl_wheel(event.wheel.direction == SDL_MOUSEWHEEL_FLIPPED ? -event.wheel.y : event.wheel.y);
                break;
            case SDL_MOUSEBUTTONDOWN:
                if (pc_settings_menu_capture_active()) {
                    pc_settings_menu_handle_capture_event(&event);
                }
                break;
            case SDL_CONTROLLERBUTTONDOWN:
                if (pc_settings_menu_capture_active()) {
                    pc_settings_menu_handle_capture_event(&event);
                    break;
                }
                if (g_pc_paused) {
                    pc_pause_menu_handle_event(&event);
                    break;
                }
                /* Back/Select opens the pause menu (controller Esc). */
                if (event.cbutton.button == SDL_CONTROLLER_BUTTON_BACK) {
                    pc_pause_menu_toggle();
                }
                break;
            case SDL_CONTROLLERAXISMOTION:
                if (pc_settings_menu_capture_active()) {
                    pc_settings_menu_handle_capture_event(&event);
                    break;
                }
                if (g_pc_paused) {
                    pc_pause_menu_handle_event(&event);
                }
                break;
            case SDL_TEXTINPUT:
                if (g_pc_paused) break;
                pc_typing_handle_event(&event);
                break;
        }
    }
    return 1;
}

/* game's main() renamed to ac_entry via -Dmain=ac_entry, boot.c's to boot_main */
extern void ac_entry(void);
extern int boot_main(int argc, const char** argv);

static int pc_parse_rain_intensity(const char* text) {
    if (strcmp(text, "light") == 0) {
        return mEnv_WEATHER_INTENSITY_LIGHT;
    }

    if (strcmp(text, "normal") == 0) {
        return mEnv_WEATHER_INTENSITY_NORMAL;
    }

    if (strcmp(text, "heavy") == 0) {
        return mEnv_WEATHER_INTENSITY_HEAVY;
    }

    return -1;
}

int main(int argc, char* argv[]) {
    for (int i = 1; i < argc; i++) {
        if (pc_trailer_parse(argc, argv, &i)) {
            continue;
        } else if (strcmp(argv[i], "--help") == 0 || strcmp(argv[i], "-h") == 0) {
            printf("Usage: AnimalCrossing [options]\n");
            printf("  --verbose, -v       Enable diagnostic output\n");
            printf("  --no-framelimit     Alias for --framelimit 0 (uncapped)\n");
            printf("  --framelimit N      Set the target frame rate (default 60, 0 = uncapped)\n");
            printf("  --profile [N]       Print frame profiler summary every N frames (default 120)\n");
            printf("  --model-viewer [N]  Launch model viewer (optional start index)\n");
            printf("  --tree-viewer      Preview the imported 3DS hardwood mesh\n");
            printf("  --tree-test-town   Play the disposable seasonal tree/terrain test field\n");
            printf("  --cedar-self-test / --cedar-lights-self-test  Disposable cedar interaction checks\n");
            printf("  --rolling-world [N] Enable outdoor curvature (0..1.5, default 1)\n");
            printf("  --terrain-no-normals Disable imported terrain relief and sheen\n");
            printf("  --tree-angle DEG  Set initial tree preview camera angle\n");
            printf("  --capture-frame P  Save framebuffer BMP after 120 frames and exit\n");
            printf("  --time H[:M[:S]]    Override in-game time (e.g. 5, 17:30, 5:55:00)\n");
            printf("  --date M/D[/Y]      Override in-game date (e.g. 7/4, 12/24/2026)\n");
            printf("  --rain [intensity]  Force rainy weather; intensity is light, normal, or heavy\n");
            printf("  --snow [intensity]  Force snow; intensity is light, normal, or heavy\n");
            printf("  --clear             Force clear weather for a consistent daylight preview\n");
            printf("  --uber-shader       Disable shader specialization (single uber shader)\n");
            printf("  --help, -h          Show this help message\n");
            return 0;
        } else if (strcmp(argv[i], "--framelimit") == 0) {
            if (i + 1 < argc && argv[i + 1][0] != '-') {
                int v = atoi(argv[i + 1]);
                if (v > 0) {
                    g_pc_frame_limit_override = v;
                } else if (v == 0) {
                    g_pc_frame_limit_override = 0;
                }
                i++;
            }
        } else if (strcmp(argv[i], "--no-framelimit") == 0) {
            g_pc_frame_limit_override = 0;
        } else if (strcmp(argv[i], "--uber-shader") == 0) {
            extern int g_pc_uber_shader_only;
            g_pc_uber_shader_only = 1;
        } else if (strcmp(argv[i], "--verbose") == 0 || strcmp(argv[i], "-v") == 0) {
            g_pc_verbose = 1;
        } else if (strcmp(argv[i], "--profile") == 0) {
            g_pc_profile_enabled = 1;
            if (i + 1 < argc && argv[i + 1][0] != '-') {
                int interval = atoi(argv[i + 1]);
                if (interval > 0) g_pc_profile_interval = interval;
                i++;
            }

        } else if (strcmp(argv[i], "--tree-world") == 0) {
            g_pc_tree_world = 1;
        } else if (strcmp(argv[i], "--clear") == 0) {
            g_pc_weather_override = mEnv_WEATHER_CLEAR;
            g_pc_weather_intensity_override = mEnv_WEATHER_INTENSITY_NONE;
        } else if (strcmp(argv[i], "--rolling-world") == 0) {
            g_pc_rolling_world_strength = 1.0f;
            if (i + 1 < argc && argv[i + 1][0] != '-') {
                char* end = NULL;
                float value = strtof(argv[i + 1], &end);
                if (end != argv[i + 1] && *end == '\0' && isfinite(value)) {
                    g_pc_rolling_world_strength = value < 0.0f ? 0.0f : value > 1.5f ? 1.5f : value;
                    i++;
                }
            }
        } else if (strcmp(argv[i], "--terrain-no-normals") == 0) {
            g_pc_terrain_normals = 0;
        } else if (strcmp(argv[i], "--tree-test-town") == 0) {
            g_pc_tree_world = g_pc_tree_test_town = 1;
        } else if (strcmp(argv[i], "--test-position") == 0 && i+2 < argc) {
            g_pc_test_spawn_x = (float)atof(argv[++i]);
            g_pc_test_spawn_z = (float)atof(argv[++i]);
        } else if (strcmp(argv[i], "--tree-self-test") == 0) {
            g_pc_tree_world = g_pc_tree_test_town = g_pc_tree_self_test = 1;
        } else if (strcmp(argv[i], "--cedar-self-test") == 0 || strcmp(argv[i], "--cedar-lights-self-test") == 0) {
            g_pc_tree_world = g_pc_tree_test_town = 1;
            g_pc_tree_self_test = strcmp(argv[i], "--cedar-lights-self-test") == 0 ? 3 : 2;
        } else if (strcmp(argv[i], "--plant-gallery") == 0) {
            /* Disposable field only: plant every replaced plant near the player. */
            g_pc_tree_world = g_pc_tree_test_town = 1;
            g_pc_tree_self_test = 4;
        } else if (strcmp(argv[i], "--young-tree-self-test") == 0 || strcmp(argv[i], "--palm-self-test") == 0 ||
                   strcmp(argv[i], "--young-cedar-self-test") == 0 || strcmp(argv[i], "--sapling-self-test") == 0) {
            g_pc_tree_world = g_pc_tree_test_town = 1;
            g_pc_tree_self_test = strcmp(argv[i], "--young-tree-self-test") == 0 ? 5 :
                                  strcmp(argv[i], "--palm-self-test") == 0 ? 6 :
                                  strcmp(argv[i], "--sapling-self-test") == 0 ? 8 : 7;
        } else if (strcmp(argv[i], "--capture-after") == 0 && i + 1 < argc) {
            g_pc_capture_after = atoi(argv[++i]);
            if (g_pc_capture_after < 1) g_pc_capture_after = 1;
        } else if (strcmp(argv[i], "--tree-viewer") == 0) {
            extern int g_pc_tree_viewer;
            g_pc_model_viewer = 1;
            g_pc_tree_viewer = 1;
        } else if (strcmp(argv[i], "--tree-angle") == 0 && i + 1 < argc) {
            extern float g_pc_tree_angle;
            g_pc_tree_angle = (float)atof(argv[++i]) * 0.01745329252f;
        } else if (strcmp(argv[i], "--capture-frame") == 0 && i + 1 < argc) {
            g_pc_capture_path = argv[++i];
        } else if (strcmp(argv[i], "--model-viewer") == 0) {
            g_pc_model_viewer = 1;
            if (i + 1 < argc && argv[i + 1][0] != '-') {
                g_pc_model_viewer_start = atoi(argv[i + 1]);
                i++;
            }
        } else if (strcmp(argv[i], "--time") == 0 && i + 1 < argc) {
            int h = -1, m = -1, s = -1;
            sscanf(argv[i + 1], "%d:%d:%d", &h, &m, &s);
            if (h >= 0 && h <= 23) g_pc_time_override = h;
            if (m >= 0 && m <= 59) g_pc_min_override = m;
            if (s >= 0 && s <= 59) g_pc_sec_override = s;
            i++;
        } else if (strcmp(argv[i], "--date") == 0 && i + 1 < argc) {
            int mo = -1, d = -1, y = -1;
            sscanf(argv[i + 1], "%d/%d/%d", &mo, &d, &y);
            if (mo >= 1 && mo <= 12 && d >= 1 && d <= 31) {
                g_pc_date_month = mo;
                g_pc_date_day = d;
                if (y >= 2000) g_pc_date_year = y;
            }
            i++;
        } else if (strcmp(argv[i], "--rain") == 0 || strcmp(argv[i], "--snow") == 0) {
            g_pc_weather_override = strcmp(argv[i], "--snow") == 0 ? mEnv_WEATHER_SNOW : mEnv_WEATHER_RAIN;
            g_pc_weather_intensity_override = mEnv_WEATHER_INTENSITY_HEAVY;
            if (i + 1 < argc && argv[i + 1][0] != '-') {
                int intensity = pc_parse_rain_intensity(argv[i + 1]);
                if (intensity >= 0) {
                    g_pc_weather_intensity_override = intensity;
                    i++;
                }
            }
        }
    }

    /* Redirect stdout/stderr to NUL unless verbose — unbuffered terminal writes
     * are extremely slow on Windows and tank FPS. */
    if (!g_pc_verbose && !g_pc_profile_enabled) {
#ifdef _WIN32
        freopen("NUL", "w", stdout);
        freopen("NUL", "w", stderr);
#else
        freopen("/dev/null", "w", stdout);
        freopen("/dev/null", "w", stderr);
#endif
    } else {
        setvbuf(stdout, NULL, _IONBF, 0);
        setvbuf(stderr, NULL, _IONBF, 0);
    }

    /* exe image range for seg2k0 — BSS can overlap N64 segment addresses */
#ifdef _WIN32
    {
        HMODULE exe = GetModuleHandle(NULL);
        IMAGE_DOS_HEADER* dos = (IMAGE_DOS_HEADER*)exe;
        IMAGE_NT_HEADERS* nt = (IMAGE_NT_HEADERS*)((char*)exe + dos->e_lfanew);
        pc_image_base = (unsigned int)(uintptr_t)exe;
        pc_image_end = pc_image_base + nt->OptionalHeader.SizeOfImage;
    }
#else
    {
        Dl_info dl;
        if (dladdr((void*)main, &dl) && dl.dli_fbase) {
            pc_image_base = (unsigned int)(uintptr_t)dl.dli_fbase;
            Elf32_Ehdr* ehdr = (Elf32_Ehdr*)dl.dli_fbase;
            Elf32_Phdr* phdr = (Elf32_Phdr*)((char*)dl.dli_fbase + ehdr->e_phoff);
            unsigned int max_end = 0;
            for (int i = 0; i < ehdr->e_phnum; i++) {
                if (phdr[i].p_type == PT_LOAD) {
                    unsigned int seg_end = phdr[i].p_vaddr + phdr[i].p_memsz;
                    if (seg_end > max_end) max_end = seg_end;
                }
            }
            /* ET_EXEC: p_vaddr is absolute. ET_DYN (PIE): relative to load address. */
            if (ehdr->e_type == ET_DYN) {
                pc_image_end = pc_image_base + max_end;
            } else {
                pc_image_end = max_end;
            }
        }
    }
#endif

    SDL_SetMainReady();
    pc_settings_load();
    pc_keybindings_load();
    pc_platform_init();
    pc_disc_init();
    int assets_ok = pc_assets_init();
    { extern void pc_furn_apply(void); pc_furn_apply(); }
    if (assets_ok && getenv("PC_DUMP_NAMES") != NULL) {
        /* dev: PC_DUMP_NAMES=<dir> writes the GameCube item name tables (16 bytes per item) and exits */
        extern unsigned char itemName_carpet[], itemName_wall[], ftrName_table[], ftrName2_table[];
        struct { const char* n; unsigned char* p; size_t sz; } t[] = {
            { "carpet", itemName_carpet, 0x430 }, { "wall", itemName_wall, 0x430 },
            { "ftr", ftrName_table, 0x4000 }, { "ftr2", ftrName2_table, 0xF20 } };
        for (int k = 0; k < 4; k++) {
            char path[512]; FILE* f;
            snprintf(path, sizeof(path), "%s/names_%s.bin", getenv("PC_DUMP_NAMES"), t[k].n);
            f = fopen(path, "wb");
            if (f) { fwrite(t[k].p, 1, t[k].sz, f); fclose(f); }
        }
        return 0;
    }
    if (!assets_ok) {
        const char* msg =
            "No game data found.\n\n"
            "Animal Crossing needs the original GameCube ROM to run.\n"
            "Place a disc image (.iso, .gcm, or .ciso) to the \"rom\" subfolder.";
        fprintf(stderr, "[PC] %s\n", msg);
        SDL_ShowSimpleMessageBox(SDL_MESSAGEBOX_ERROR,
                                 "Animal Crossing - Missing ROM", msg, g_pc_window);
        pc_platform_shutdown();
        return 1;
    }

    {
        extern void pc_chr_smooth_install(void);
        pc_chr_smooth_install();        /* subdivided villager/player display lists */
    }
    ac_entry();                         /* sets HotStartEntry = &entry */
    boot_main(argc, (const char**)argv); /* full init → HotStartEntry → game loop */

    pc_disc_shutdown();
    pc_platform_shutdown();
    return 0;
}
