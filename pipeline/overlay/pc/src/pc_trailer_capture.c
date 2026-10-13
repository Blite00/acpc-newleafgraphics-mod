/* Explicit disposable-town recording tool; inactive during normal gameplay. */
#include "pc_platform.h"
#include "pc_trailer_capture.h"
#include "pc_audio_capture.h"
#include "jaudio_NES/game64.h"
#include <string.h>
#include <stdio.h>
#include <stdlib.h>
#include <math.h>
#include <windows.h>
#include <io.h>
#include <fcntl.h>

static const char *output, *encoder = "ffmpeg", *motion = "idle";
static const char* audio_path;
static int duration = 480, warmup = 120, frame, width, height;
static int no_music;
static int activity_tool, activity_scene, activity_facing = -1;
static FILE* pipe;
static HANDLE encoder_process;
static unsigned char* pixels;
extern int g_pc_tree_test_town;

int pc_trailer_parse(int argc, char** argv, int* index) {
    const char* arg = argv[*index];
    if (!strcmp(arg, "--trailer-no-music")) { no_music = 1; return 1; }
    if (*index + 1 >= argc) return 0;
    if (!strcmp(arg, "--trailer-output")) output = argv[++*index];
    else if (!strcmp(arg, "--trailer-audio")) audio_path = argv[++*index];
    else if (!strcmp(arg, "--trailer-encoder")) encoder = argv[++*index];
    else if (!strcmp(arg, "--trailer-motion")) motion = argv[++*index];
    else if (!strcmp(arg, "--trailer-tool")) {
        const char* value = argv[++*index];
        activity_tool = !strcmp(value, "shovel") ? 1 : !strcmp(value, "rod") ? 2 : !strcmp(value, "net") ? 3 :
                        !strcmp(value, "axe") ? 4 : !strcmp(value, "umbrella") ? 5 : !strcmp(value, "golden-axe") ? 6 :
                        !strcmp(value, "golden-net") ? 7 : !strcmp(value, "golden-rod") ? 8 : !strcmp(value, "golden-shovel") ? 9 :
                        !strcmp(value, "axe-worn") ? 10 : !strcmp(value, "axe-cracked") ? 11 : 0;
    }
    else if (!strcmp(arg, "--trailer-scene")) {
        const char* value = argv[++*index];
        activity_scene = !strcmp(value, "fruit-tree") ? 1 : !strcmp(value, "butterfly") ? 2 : !strcmp(value, "neighbor") ? 3 : 0;
    }
    else if (!strcmp(arg, "--trailer-facing")) {
        const char* value = argv[++*index];
        activity_facing = !strcmp(value, "north") ? 0x8000 : !strcmp(value, "east") ? 0x4000 : !strcmp(value, "west") ? 0xC000 : 0;
    }
    else if (!strcmp(arg, "--trailer-frames")) duration = atoi(argv[++*index]);
    else if (!strcmp(arg, "--trailer-warmup")) warmup = atoi(argv[++*index]);
    else return 0;
    if (duration < 2) duration = 2;
    if (duration > 36000) duration = 36000;
    if (warmup < 1) warmup = 1;
    return 1;
}

int pc_trailer_active(void) { return output && g_pc_tree_test_town; }
int pc_trailer_activity_tool(void) { return activity_tool; }
int pc_trailer_activity_scene(void) { return activity_scene; }
int pc_trailer_activity_facing(void) { return activity_facing; }

void pc_trailer_close(void) {
    pc_audio_capture_end();
    if (pipe) {
        DWORD result = 1;
        fclose(pipe);
        WaitForSingleObject(encoder_process, INFINITE);
        GetExitCodeProcess(encoder_process, &result);
        CloseHandle(encoder_process); encoder_process = NULL;
        fprintf(stderr, "[Trailer] Encoder exit %d; %d native frames\n", result, frame - warmup);
        pipe = NULL;
    }
    free(pixels); pixels = NULL;
}

void pc_trailer_frame(void) {
    char command[4096];
    if (!pc_trailer_active()) return;
    ++frame;
    if (no_music && frame >= 30) Na_BGMVolume(0.0f, 0);
    if (frame <= warmup) return;
    if (!pipe) {
        /* Reject command interpreter metacharacters in these local tool paths. */
        if (strpbrk(output, "\"%\r\n&|<>^") || strpbrk(encoder, "\"%\r\n&|<>^")) {
            fprintf(stderr, "[Trailer] Unsafe output/encoder path\n");
            g_pc_running = 0; return;
        }
        SDL_GL_GetDrawableSize(g_pc_window, &width, &height);
        if (width < 1 || height < 1 || width > 8192 || height > 8192) { g_pc_running = 0; return; }
        pixels = malloc((size_t)width * height * 3);
        snprintf(command, sizeof(command),
          "\"%s\" -hide_banner -loglevel error -y -f rawvideo -pixel_format rgb24 -video_size %dx%d -framerate 30 -i pipe:0 -an -vf vflip -c:v libx264 -preset fast -crf 16 -pix_fmt yuv420p -movflags +faststart \"%s\"",
          encoder, width, height, output);
        if (pixels) {
            SECURITY_ATTRIBUTES sa = { sizeof(sa), NULL, TRUE };
            STARTUPINFOA si = { sizeof(si) };
            PROCESS_INFORMATION pi = {0};
            HANDLE input = NULL, writer = NULL;
            if (CreatePipe(&input, &writer, &sa, 0)) {
                SetHandleInformation(writer, HANDLE_FLAG_INHERIT, 0);
                si.dwFlags = STARTF_USESTDHANDLES | STARTF_USESHOWWINDOW;
                si.wShowWindow = SW_HIDE;
                si.hStdInput = input;
                si.hStdOutput = GetStdHandle(STD_OUTPUT_HANDLE);
                si.hStdError = GetStdHandle(STD_ERROR_HANDLE);
                if (CreateProcessA(NULL, command, NULL, NULL, TRUE, CREATE_NO_WINDOW, NULL, NULL, &si, &pi)) {
                    int fd = _open_osfhandle((intptr_t)writer, _O_BINARY | _O_WRONLY);
                    pipe = fd >= 0 ? _fdopen(fd, "wb") : NULL;
                    encoder_process = pi.hProcess;
                    CloseHandle(pi.hThread);
                    if (!pipe) { if (fd >= 0) _close(fd); else CloseHandle(writer); }
                } else CloseHandle(writer);
                CloseHandle(input);
            }
        }
        if (!pipe) { fprintf(stderr, "[Trailer] Cannot open encoder\n"); g_pc_running = 0; return; }
        if (audio_path) pc_audio_capture_begin(audio_path, duration / 60 + 30);
    }
    if (((frame - warmup - 1) & 1) == 0) {
        size_t bytes = (size_t)width * height * 3;
        glPixelStorei(GL_PACK_ALIGNMENT, 1);
        glReadPixels(0, 0, width, height, GL_RGB, GL_UNSIGNED_BYTE, pixels);
        if (fwrite(pixels, 1, bytes, pipe) != bytes) {
            fprintf(stderr, "[Trailer] Encoder write failed\n");
            pc_trailer_close(); g_pc_running = 0; return;
        }
    }
    if (frame - warmup >= duration) { pc_trailer_close(); g_pc_running = 0; }
}

/* A segment's speed is stick magnitude, not a world-space displacement.
 * Default 28 is a stroll; explicit @42 restores the earlier faster walk.
 * Diagonals preserve that magnitude rather than accelerating by sqrt(2). */
static void pc_trailer_motion_at(int t, float* x, float* y, u16* button) {
    *x = *y = 0.0f;
    *button = 0;
    if (t >= 0) {
        const char* segment = motion;
        char action[40] = {0};
        int length = duration, count = 0;
        float speed = 28.0f;
        int running = 0;
        char* magnitude;
        while (*segment) {
            const char* next = strchr(segment, ',');
            const char* colon = strchr(segment, ':');
            int n = (int)((colon && (!next || colon < next) ? colon : next ? next : segment + strlen(segment)) - segment);
            if (n >= (int)sizeof(action)) n = sizeof(action) - 1;
            memcpy(action, segment, n); action[n] = 0;
            length = colon && (!next || colon < next) ? atoi(colon + 1) : duration;
            if (length < 1) length = 1;
            if (t < count + length) break;
            count += length;
            if (!next) { action[0] = 0; break; }
            segment = next + 1;
        }
        if (!strncmp(action, "run-", 4) && strlen(action) < sizeof(action) - 1) {
            running = 1;
            speed = 55.0f;
            /* Reuse all eight native stick directions; B is the game's run input. */
            memmove(action + 5, action + 4, strlen(action + 4) + 1);
            memcpy(action, "walk-", 5);
        }
        magnitude = strchr(action, '@');
        if (magnitude) {
            char* end;
            float requested = strtof(magnitude + 1, &end);
            *magnitude = 0;
            if (end != magnitude + 1 && *end == 0 && isfinite(requested))
                speed = requested < 0.0f ? 0.0f : requested > 72.0f ? 72.0f : requested;
        }
        if (!strcmp(action, "walk-left")) *x = -speed;
        else if (!strcmp(action, "walk-right")) *x = speed;
        else if (!strcmp(action, "walk-up")) *y = speed;
        else if (!strcmp(action, "walk-down")) *y = -speed;
        else if (!strcmp(action, "walk-up-right")) { *x = speed * 0.70710678f; *y = speed * 0.70710678f; }
        else if (!strcmp(action, "walk-up-left")) { *x = -speed * 0.70710678f; *y = speed * 0.70710678f; }
        else if (!strcmp(action, "walk-down-right")) { *x = speed * 0.70710678f; *y = -speed * 0.70710678f; }
        else if (!strcmp(action, "walk-down-left")) { *x = -speed * 0.70710678f; *y = -speed * 0.70710678f; }
        else if ((!strcmp(action, "shake") && t - count < 5) || !strcmp(action, "a")) *button = PAD_BUTTON_A;
        else if (!strcmp(action, "b")) *button = PAD_BUTTON_B;
        else if (!strcmp(action, "x")) *button = PAD_BUTTON_X;
        else if (!strcmp(action, "y")) *button = PAD_BUTTON_Y;
        if (running) *button |= PAD_BUTTON_B;
    }
}

int pc_trailer_pad(PADStatus* status) {
    int t, i;
    float x = 0.0f, y = 0.0f, sample_x, sample_y;
    u16 button;
    if (!pc_trailer_active()) return 0;
    memset(status, 0, sizeof(PADStatus) * 4);
    status[1].err = status[2].err = status[3].err = -1;
    t = frame - warmup;
    /* Twelve-frame causal ramp: starts/stops take 0.2 seconds, and adjacent
     * directions flow through a turn. Evaluate by frame so repeated PADRead
     * calls cannot advance the script or change its smoothing. Native actor
     * movement, turning, collision and camera follow still own the result. */
    for (i = 0; i < 12; ++i) {
        pc_trailer_motion_at(t - i, &sample_x, &sample_y, &button);
        x += sample_x;
        y += sample_y;
    }
    status[0].stickX = (s8)lroundf(x / 12.0f);
    status[0].stickY = (s8)lroundf(y / 12.0f);
    pc_trailer_motion_at(t, &sample_x, &sample_y, &button);
    status[0].button = button; /* Button pulses retain their exact frame. */
    return 1;
}
