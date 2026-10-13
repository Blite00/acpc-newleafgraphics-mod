#ifndef PC_DONOR_LIGHT_H
#define PC_DONOR_LIGHT_H
#ifdef __cplusplus
extern "C" {
#endif
float pc_donor_weather_blend(void);
/* Original CANM frame coordinate; caller owns playback-rate adaptation. */
void pc_donor_water_frame_set(float frame);
/* Original slot4 global ambient; applies to all source outdoor light sets. */
extern float g_pc_donor_global_ambient[3];
void pc_donor_global_ambient_set(const unsigned char ambient[3]);
/* Source world-frame surface-to-light direction, shared by actor renderers. */
extern float g_pc_donor_actor_direction[3];
void pc_donor_light_directions_set(const float ground[3], const float actor[3]);
void pc_donor_water_palette_set(const unsigned char* base,
    const unsigned char* buffer, const unsigned char* bank);
void pc_donor_light_set(int enabled, const unsigned char* diffuse,
    const unsigned char* specular, const unsigned char* sky, const unsigned char* ground);
#ifdef __cplusplus
}
#endif
#endif
