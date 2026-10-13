#ifndef PC_TRAILER_CAPTURE_H
#define PC_TRAILER_CAPTURE_H
#include <dolphin/pad.h>
int pc_trailer_parse(int argc, char** argv, int* index);
int pc_trailer_active(void);
int pc_trailer_activity_tool(void);
int pc_trailer_activity_scene(void);
int pc_trailer_activity_facing(void);
void pc_trailer_frame(void);
void pc_trailer_close(void);
int pc_trailer_pad(PADStatus* status);
#endif
