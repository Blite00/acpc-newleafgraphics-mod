/* pc_audio.c - SDL2 audio backend with dedicated producer thread.
 *
 * Architecture (matches GC):
 *   Game thread:  Na_GameFrame() queues commands via message queues
 *   Audio thread: pc_audio_process_frame() produces samples into ring buffer
 *   SDL callback: reads ring buffer → speakers
 *
 * The audio thread decouples sample production from the game frame,
 * so OS preemption of the game thread doesn't cause audio dropouts.
 */
#include "pc_platform.h"
#include "pc_settings.h"
#include "pc_audio_capture.h"
#include "jaudio_NES/audiothread.h"

#define PC_AUDIO_SAMPLE_RATE 32000

/* lock-free SPSC ring buffer (producer=audio thread, consumer=SDL callback) */
#define RING_BUF_SAMPLES (32768) /* ~512ms at 32kHz stereo */
#define RING_BUF_MASK    (RING_BUF_SAMPLES - 1)

/* Produce more samples when buffer drops below this level.
 * ~4 audio frames ahead = ~70ms of buffer at 32kHz stereo. */
#define AUDIO_PRODUCE_THRESHOLD 4480

static s16 ring_buffer[RING_BUF_SAMPLES];
static SDL_atomic_t ring_write_pos; /* written by audio producer thread */
static SDL_atomic_t ring_read_pos;  /* written by SDL audio callback */
static SDL_AudioDeviceID audio_device = 0;

/* Optional developer recording. The callback only copies to bounded RAM;
 * opening/writing files and allocating/freeing memory stay on the main thread.
 * The SDL device lock serializes buffer ownership with the callback. */
static s16* capture_samples = NULL;
static size_t capture_count = 0;
static size_t capture_capacity = 0;
static char capture_path[1024];
static int capture_full = 0;

static void pc_audio_capture_u32(unsigned char* p, uint32_t value) {
    p[0] = (unsigned char)value;
    p[1] = (unsigned char)(value >> 8);
    p[2] = (unsigned char)(value >> 16);
    p[3] = (unsigned char)(value >> 24);
}

int pc_audio_capture_begin(const char* path, int max_seconds) {
    if (!audio_device || !path || !path[0] || strlen(path) >= sizeof(capture_path) ||
        capture_samples || max_seconds < 1 || max_seconds > 300) return 0;
    size_t capacity = (size_t)max_seconds * PC_AUDIO_SAMPLE_RATE * 2;
    s16* samples = (s16*)malloc(capacity * sizeof(s16));
    if (!samples) return 0;
    SDL_LockAudioDevice(audio_device);
    strcpy(capture_path, path);
    capture_count = 0;
    capture_capacity = capacity;
    capture_full = 0;
    capture_samples = samples;
    SDL_UnlockAudioDevice(audio_device);
    return 1;
}

int pc_audio_capture_end(void) {
    if (!capture_samples) return 1;
    if (audio_device) SDL_LockAudioDevice(audio_device);
    s16* samples = capture_samples;
    size_t count = capture_count;
    int full = capture_full;
    capture_samples = NULL;
    capture_count = capture_capacity = 0;
    if (audio_device) SDL_UnlockAudioDevice(audio_device);

    unsigned char header[44] = {0};
    uint32_t bytes = (uint32_t)(count * sizeof(s16));
    memcpy(header, "RIFF", 4);
    pc_audio_capture_u32(header + 4, 36 + bytes);
    memcpy(header + 8, "WAVEfmt ", 8);
    pc_audio_capture_u32(header + 16, 16);
    header[20] = 1; /* PCM */
    header[22] = 2; /* stereo */
    pc_audio_capture_u32(header + 24, PC_AUDIO_SAMPLE_RATE);
    pc_audio_capture_u32(header + 28, PC_AUDIO_SAMPLE_RATE * 4);
    header[32] = 4;
    header[34] = 16;
    memcpy(header + 36, "data", 4);
    pc_audio_capture_u32(header + 40, bytes);
    FILE* file = fopen(capture_path, "wb");
    int ok = 0;
    if (file) {
        ok = fwrite(header, 1, sizeof(header), file) == sizeof(header);
        /* Supported PC builds are little endian, matching WAV PCM. */
        if (ok) ok = fwrite(samples, sizeof(s16), count, file) == count;
        if (fclose(file) != 0) ok = 0;
    }
    printf("[TRAILER AUDIO] %s: %.3f seconds%s%s\n", capture_path,
           (double)count / (PC_AUDIO_SAMPLE_RATE * 2),
           full ? " (capture limit reached)" : "", ok ? "" : " (write failed)");
    free(samples);
    return ok && !full;
}

typedef void (*AIDMACallback)(void);
static AIDMACallback ai_dma_callback = NULL;
static u32 ai_dsp_sample_rate = PC_AUDIO_SAMPLE_RATE;

/* --- Audio producer thread --- */
static SDL_Thread* audio_producer_thread = NULL;
static SDL_atomic_t audio_thread_running;

static int pc_audio_producer_func(void* data) {
    (void)data;
    while (SDL_AtomicGet(&audio_thread_running)) {
        int fill = pc_audio_get_buffer_fill();
        if (fill < AUDIO_PRODUCE_THRESHOLD) {
            pc_audio_process_frame();
        } else {
            SDL_Delay(1);
        }
    }
    return 0;
}

void pc_audio_start_producer_thread(void) {
    if (audio_producer_thread) return;
    SDL_AtomicSet(&audio_thread_running, 1);
    audio_producer_thread = SDL_CreateThread(pc_audio_producer_func, "AudioProducer", NULL);
    if (audio_producer_thread) {
        printf("[AUDIO] Producer thread started\n");
    } else {
        printf("[AUDIO] Failed to create producer thread: %s\n", SDL_GetError());
    }
}

/* --- SDL audio callback (runs on SDL's audio device thread) --- */
static void pc_audio_callback(void* userdata, Uint8* stream, int len) {
    s16* out = (s16*)stream;
    int total_samples = len / sizeof(s16);
    u32 wp = (u32)SDL_AtomicGet(&ring_write_pos);
    SDL_MemoryBarrierAcquire();
    u32 rp = (u32)SDL_AtomicGet(&ring_read_pos);
    u32 used = wp - rp;

    /* overrun: producer lapped us */
    if (used > RING_BUF_SAMPLES) {
        rp = wp - RING_BUF_SAMPLES;
        rp &= ~1u; /* stereo-align */
        used = wp - rp;
    }

    int avail = (int)used;
    avail &= ~1; /* whole stereo frames only */
    int copy = (avail < total_samples) ? avail : total_samples;
    copy &= ~1;

    for (int i = 0; i < copy; i++) {
        out[i] = ring_buffer[(rp + i) & RING_BUF_MASK];
    }
    if (copy < total_samples) {
        memset(&out[copy], 0, (total_samples - copy) * sizeof(s16));
    }

    if (capture_samples) {
        size_t remaining = capture_capacity - capture_count;
        size_t n = (size_t)total_samples;
        if (n > remaining) { n = remaining; capture_full = 1; }
        memcpy(capture_samples + capture_count, out, n * sizeof(s16));
        capture_count += n;
    }

    SDL_MemoryBarrierRelease();
    SDL_AtomicSet(&ring_read_pos, (int)(rp + copy));
}

/* --- AI (Audio Interface) --- */

void AIInit(u8* stack) {
    (void)stack;
    if (audio_device != 0) return;

    SDL_AudioSpec want, have;
    memset(&want, 0, sizeof(want));
    want.freq = PC_AUDIO_SAMPLE_RATE;
    want.format = AUDIO_S16SYS;
    want.channels = 2;
    want.samples = 512;
    want.callback = pc_audio_callback;

    audio_device = SDL_OpenAudioDevice(NULL, 0, &want, &have, 0);
    if (audio_device != 0) {
        printf("[AUDIO] Opened: freq=%d fmt=0x%04X ch=%d samples=%d (requested: freq=%d)\n",
               have.freq, have.format, have.channels, have.samples, want.freq);
    } else {
        printf("[AUDIO] Failed to open: %s\n", SDL_GetError());
    }
}

void AIInitDMA(u32 addr, u32 size) {
    s16* src = (s16*)(uintptr_t)addr;
    u32 n_samples = size / sizeof(s16);
    n_samples &= ~1u; /* whole stereo frames */

    u32 wp = (u32)SDL_AtomicGet(&ring_write_pos);
    u32 rp = (u32)SDL_AtomicGet(&ring_read_pos);
    SDL_MemoryBarrierAcquire();
    u32 used = wp - rp;
    u32 free = RING_BUF_SAMPLES - used;

    if (n_samples > free) {
        n_samples = free & ~1u;
    }

    int vol = g_pc_settings.master_volume;
    if (vol < 0)   vol = 0;
    if (vol > 100) vol = 100;

    for (u32 i = 0; i < n_samples; i++) {
        int s = ((int)src[i] * vol) / 100;
        if (s >  32767) s =  32767;
        if (s < -32768) s = -32768;
        ring_buffer[(wp + i) & RING_BUF_MASK] = (s16)s;
    }

    SDL_MemoryBarrierRelease();
    SDL_AtomicSet(&ring_write_pos, (int)(wp + n_samples));
}

void AIStartDMA(void) {
    if (audio_device != 0) SDL_PauseAudioDevice(audio_device, 0);
}

void AIStopDMA(void) {
    if (audio_device != 0) SDL_PauseAudioDevice(audio_device, 1);
}

void pc_audio_set_paused(int paused) {
    /* Currently unused */
    if (audio_device != 0) SDL_PauseAudioDevice(audio_device, paused ? 1 : 0);
}

u32  AIGetDMAStartAddr(void) { return 0; }
u16  AIGetDMALength(void) { return 0; }
u32  AIGetStreamTrigger(void) { return 0; }
u32  AIGetStreamSampleCount(void) { return 0; }
void AISetStreamPlayState(u32 state) { (void)state; }
u32  AIGetStreamPlayState(void) { return 0; }
void AISetStreamSampleRate(u32 rate) { (void)rate; }
u32  AIGetStreamSampleRate(void) { return PC_AUDIO_SAMPLE_RATE; }
void AISetStreamVolLeft(u8 vol) { (void)vol; }
void AISetStreamVolRight(u8 vol) { (void)vol; }
u8   AIGetStreamVolLeft(void) { return 0; }
u8   AIGetStreamVolRight(void) { return 0; }
void AIResetStreamSampleCount(void) {}
void AISetDSPSampleRate(u32 rate) { ai_dsp_sample_rate = rate; }
u32  AIGetDSPSampleRate(void) { return ai_dsp_sample_rate; }

void* AIRegisterDMACallback(void* callback) {
    void* old = (void*)ai_dma_callback;
    ai_dma_callback = (AIDMACallback)callback;
    return old;
}

/* --- DSP stubs (rspsim does everything in software) --- */

void DSPInit(void) {}
BOOL DSPCheckMailToDSP(void) { return FALSE; }
BOOL DSPCheckMailFromDSP(void) { return FALSE; }
u32  DSPReadMailFromDSP(void) { return 0; }
void DSPSendMailToDSP(u32 mail) { (void)mail; }
void DSPAssertInt(void) {}
void* DSPAddTask(void* task) { return task; }

/* --- ring buffer queries for frame pacing (pc_vi.c) --- */

int pc_audio_get_buffer_fill(void) {
    return SDL_AtomicGet(&ring_write_pos) - SDL_AtomicGet(&ring_read_pos);
}

int pc_audio_is_active(void) {
    return audio_device != 0;
}

void pc_audio_shutdown(void) {
    pc_audio_capture_end();
    /* Stop producer thread first */
    SDL_AtomicSet(&audio_thread_running, 0);
    if (audio_producer_thread) {
        SDL_WaitThread(audio_producer_thread, NULL);
        audio_producer_thread = NULL;
    }
    if (audio_device != 0) {
        SDL_CloseAudioDevice(audio_device);
        audio_device = 0;
    }
}
