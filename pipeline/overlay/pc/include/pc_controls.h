#ifndef PC_CONTROLS_H
#define PC_CONTROLS_H

/* Modern PC keyboard + mouse layer on top of the GameCube pad (pc_controls.c).
 *  - context: the game reports each frame whether a menu (submenu) is open; mouse-driven UIs claim the mouse,
 *  - mouse: left click = A and right click = B where no UI claims the mouse, wheel = tool cycle (D-pad) in the field,
 *  - Esc: back (B) in menus, finish in the text editor, the PC pause menu otherwise,
 *  - in-game text that names GameCube buttons is rewritten for the PC keys (pc_controls_msgs.c_inc). */

#ifdef __cplusplus
extern "C" {
#endif

/* game side, once per frame */
void pc_ctl_set_menu_open(int open); /* m_submenu.c: a submenu is open or opening */
void pc_ctl_claim_mouse(void);       /* pockets / keyboard: the mouse is handled by this UI this frame */

/* platform side */
int pc_ctl_menu_open(void);
int pc_ctl_mouse_claimed(void);
int pc_ctl_escape(void);       /* Esc pressed (not paused): 1 = used by the game, 0 = open the pause menu */
void pc_ctl_wheel(int dy);     /* SDL mouse wheel */
unsigned short pc_ctl_pad_extra(int typing); /* PAD_BUTTON_* bits from the mouse / pulses, called by PADRead */
int pc_ctl_run_active(void);   /* run key: held in the field */
extern int g_pc_editor_end_req; /* Esc in the text editor: finish editing (m_editor_ovl.c) */

/* message text override (called from mMsg_LoadMsgData): new length, or -1 to keep the text */
int pc_ctl_msg_override(int index, unsigned char* buf, int size, int cap);

/* short key names for on-screen prompts */
const char* pc_ctl_key_label(int pc_input_code);

/* prompt style = the device used last: keyboard/mouse or the kind of controller (switches live).
 * PC_CTL_STYLE=kb|xbox|ps|nin forces one (dev). */
enum { PC_CTL_STYLE_KB, PC_CTL_STYLE_XBOX, PC_CTL_STYLE_PS, PC_CTL_STYLE_NIN, PC_CTL_STYLE_COUNT };
int pc_ctl_style(void);
void pc_ctl_input_event(const void* sdl_event); /* every SDL event (pc_main.c) */
/* short prompt for a GameCube button ('A','B','X','Y','S'tart,'Z','L','R') in the current style; may hold
 * game-font symbol bytes (PlayStation shapes) */
const char* pc_ctl_prompt(char gc_button);

#ifdef __cplusplus
}
#endif

#endif
