#ifndef PC_AUDIO_CAPTURE_H
#define PC_AUDIO_CAPTURE_H
/* Developer capture only. Main thread calls; normal playback stays unchanged.
 * Captures actual playback time, which can differ from fixed-step video time. */
int pc_audio_capture_begin(const char* path, int max_seconds);
int pc_audio_capture_end(void);
#endif
