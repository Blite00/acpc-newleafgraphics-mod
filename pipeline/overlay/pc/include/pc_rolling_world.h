#ifndef PC_ROLLING_WORLD_H
#define PC_ROLLING_WORLD_H
#ifdef __cplusplus
extern "C" {
#endif
extern float g_pc_rolling_world_strength;
/* Outdoor actor preloading; does not change acre-transition controls. */
int pc_rolling_world_actor_preload(void);
/* CPU visibility must use the same cylindrical position as the vertex shader. */
int pc_rolling_world_bend_position(float x, float y, float z, float* ox, float* oy, float* oz);
void pc_rolling_world_set_projection(float near_plane, float far_plane, float scale);
void pc_rolling_world_set_camera(int outdoor,
    float ex, float ey, float ez, float cx, float cy, float cz,
    float ux, float uy, float uz, float px, float py, float pz);
#ifdef __cplusplus
}
#endif
#endif
