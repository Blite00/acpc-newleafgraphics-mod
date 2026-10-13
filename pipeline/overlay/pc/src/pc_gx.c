/* pc_gx.c - GX API → OpenGL 3.3: state management, vertex submission, draw dispatch */
#include "pc_gx_internal.h"
#include "pc_profiler.h"
#include "pc_settings.h"
#include "pc_rolling_world.h"
#include "pc_donor_light.h"
#include <stddef.h>
#include "pc_donor_lut_values.c_inc"
static GLuint s_donor_lut_texture;
static GLushort quad_index_buf[(PC_GX_MAX_VERTS / 4) * 6];
#include <math.h>
#include <dolphin/gx/GXEnum.h>

extern void pc_tree_world_set_donor_light(int enabled,const unsigned char* diffuse,
    const unsigned char* specular,const unsigned char* sky,const unsigned char* ground);
static int donor_light_enabled;
float g_pc_donor_global_ambient[3];
void pc_donor_global_ambient_set(const unsigned char ambient[3]) {
    pc_gx_draw_pending();
    for(int c=0;c<3;++c)g_pc_donor_global_ambient[c]=ambient[c]/255.0f;
    DIRTY(PC_GX_DIRTY_LIGHTING);
}
static float donor_ground_direction[3]={0.0f,1.0f,0.0f};
float g_pc_donor_actor_direction[3]={0.0f,1.0f,0.0f};
static float donor_water_base[3]={0.0f,173.0f/255.0f,1.0f};
static float donor_water_buffer[3]={115.0f/255.0f,1.0f,1.0f};
static float donor_water_bank[3]={38.0f/255.0f,56.0f/255.0f,110.0f/255.0f};
void pc_donor_light_directions_set(const float ground[3], const float actor[3]) {
    pc_gx_draw_pending();
    for(int c=0;c<3;++c) {
        donor_ground_direction[c]=ground[c];
        g_pc_donor_actor_direction[c]=actor[c];
    }
    DIRTY(PC_GX_DIRTY_LIGHTING);
}
void pc_donor_water_palette_set(const unsigned char* base,
    const unsigned char* buffer, const unsigned char* bank) {
    pc_gx_draw_pending();
    for(int c=0;c<3;++c) {
        donor_water_base[c]=base[c]/255.0f;
        donor_water_buffer[c]=buffer[c]/255.0f;
        donor_water_bank[c]=bank[c]/255.0f;
    }
    DIRTY(PC_GX_DIRTY_LIGHTING);
}
static float water_phase[2];
static float donor_water_frame;
void pc_donor_water_frame_set(float frame) {
    pc_gx_draw_pending();
    donor_water_frame=fmodf(frame,600.0f);
    if(donor_water_frame<0.0f) donor_water_frame+=600.0f;
    DIRTY(PC_GX_DIRTY_LIGHTING);
}
void pc_water_set_phase(float flow,float wave) {
    pc_gx_draw_pending();
    water_phase[0]=flow; water_phase[1]=wave;
    DIRTY(PC_GX_DIRTY_LIGHTING);
}
static float donor_diffuse[3], donor_specular[3], donor_hemi_sky[3], donor_hemi_ground[3];
void pc_donor_light_set(int enabled, const unsigned char* diffuse,
    const unsigned char* specular, const unsigned char* sky, const unsigned char* ground) {
    pc_gx_draw_pending();
    donor_light_enabled = enabled;
    pc_tree_world_set_donor_light(enabled,diffuse,specular,sky,ground);
    for (int c=0;c<3;c++) {
        donor_diffuse[c]=diffuse[c]/255.0f; donor_specular[c]=specular[c]/255.0f;
        donor_hemi_sky[c]=sky[c]/255.0f; donor_hemi_ground[c]=ground[c]/255.0f;
    }
    DIRTY(PC_GX_DIRTY_LIGHTING);
}
/* New Leaf character lighting (PC_NOOP_NL_CHAR_ON/OFF markers in the New Leaf head display lists) */
static int nl_char;
void pc_gx_set_nl_char(int on) {
    if (on == nl_char) return;
    pc_gx_draw_pending();
    nl_char = on;
    DIRTY(PC_GX_DIRTY_LIGHTING);
}
static int nl_cloth;
void pc_gx_set_nl_cloth(int on) {
    static int enabled = -1;
    extern char* getenv(const char*);
    if (enabled < 0) { const char* e = getenv("PC_NL_CLOTH"); enabled = (e == NULL || e[0] != '0'); }
    if (!enabled) on = 0;
    if (on == nl_cloth) return;
    pc_gx_draw_pending();
    nl_cloth = on;
    DIRTY(PC_GX_DIRTY_LIGHTING);
}
static int rolling_outdoor;
static float rolling_projection_a, rolling_projection_b;
static int rolling_projection_valid;
static float rolling_camera[3], rolling_anchor[3], rolling_axis[3] = {0, 0, 1};
static float rolling_view_rotation[9] = {1,0,0, 0,1,0, 0,0,1};

void pc_rolling_world_set_projection(float near_plane, float far_plane, float scale) {
    pc_gx_draw_pending();
    DIRTY(PC_GX_DIRTY_PROJECTION);
    rolling_projection_valid = near_plane > 0.0f && far_plane > near_plane && scale > 0.0f;
    if (rolling_projection_valid) {
        /* Match guPerspectiveF -> N64 fixed point -> emu64::dl_G_MTX,
         * including its historical near/far reconstruction convention. */
        float a = truncf(((near_plane + far_plane) / (near_plane - far_plane)) * scale * 65536.0f) / 65536.0f;
        float b = truncf((2.0f * near_plane * far_plane / (near_plane - far_plane)) * scale * 65536.0f) / 65536.0f;
        float n, f;
        if (fabsf(a - 1.0f) < 0.000001f || fabsf(a + 1.0f) < 0.000001f) {
            rolling_projection_valid = 0;
            return;
        }
        n = b * ((a + 1.0f) / (a - 1.0f) - 1.0f) / 2.0f;
        f = n * ((a - 1.0f) / (a + 1.0f) + 1.0f);
        rolling_projection_a = n / (n - f);
        rolling_projection_b = n * f / (n - f);
    }
}

static int pc_rolling_world_projection_matches(void) {
    /* Inventory models also use perspective, but with their own clipping
     * planes and camera. Only bend draws using the actual outdoor camera's
     * projection. Allow N64 fixed-point matrix quantization error. */
    return rolling_projection_valid && g_gx.projection_type == GX_PERSPECTIVE &&
        fabsf(g_gx.projection_mtx[2][2] - rolling_projection_a) <
            0.00002f + 0.005f * fabsf(rolling_projection_a) &&
        fabsf(g_gx.projection_mtx[2][3] - rolling_projection_b) <
            0.00002f + 0.005f * fabsf(rolling_projection_b);
}

void pc_rolling_world_set_camera(int outdoor,
    float ex, float ey, float ez, float cx, float cy, float cz,
    float ux, float uy, float uz, float px, float py, float pz) {
    float zx = ex-cx, zy = ey-cy, zz = ez-cz;
    float len, xx, xy, xz, yx, yy, yz;
    /* Camera is updated once per scene frame, before display-list submission.
     * Flush any previous run before mutating uniforms and invalidate every
     * shader variant through the normal projection generation counter. */
    pc_gx_draw_pending();
    rolling_outdoor = 0;
    DIRTY(PC_GX_DIRTY_PROJECTION);
    if (!outdoor) return;
    len = sqrtf(zx*zx + zy*zy + zz*zz);
    if (len < 0.001f) return;
    zx /= len; zy /= len; zz /= len;
    xx = uy*zz-uz*zy; xy = uz*zx-ux*zz; xz = ux*zy-uy*zx;
    len = sqrtf(xx*xx+xy*xy+xz*xz);
    if (len < 0.001f) return;
    xx /= len; xy /= len; xz /= len;
    yx = zy*xz-zz*xy; yy = zz*xx-zx*xz; yz = zx*xy-zy*xx;
    rolling_view_rotation[0]=xx; rolling_view_rotation[1]=xy; rolling_view_rotation[2]=xz;
    rolling_view_rotation[3]=yx; rolling_view_rotation[4]=yy; rolling_view_rotation[5]=yz;
    rolling_view_rotation[6]=zx; rolling_view_rotation[7]=zy; rolling_view_rotation[8]=zz;
    rolling_camera[0]=ex; rolling_camera[1]=ey; rolling_camera[2]=ez;
    rolling_anchor[0]=px; rolling_anchor[1]=py; rolling_anchor[2]=pz;
    len = sqrtf(zx*zx+zz*zz);
    if (len < 0.001f) return;
    rolling_axis[0]=zx/len; rolling_axis[1]=0; rolling_axis[2]=zz/len;
    rolling_outdoor = 1;
}

int pc_rolling_world_bend_position(float x, float y, float z, float* ox, float* oy, float* oz) {
    float rx=x-rolling_anchor[0], ry=y-rolling_anchor[1], rz=z-rolling_anchor[2];
    float radius, along, angle, c, s;
    if (!rolling_outdoor || g_pc_rolling_world_strength <= 0.0f) return 0;
    radius=800.0f/g_pc_rolling_world_strength;
    along=rx*rolling_axis[0]+rz*rolling_axis[2];
    angle=along/radius; c=cosf(angle); s=sinf(angle);
    *ox=rolling_anchor[0]+rx+rolling_axis[0]*((radius+ry)*s-along);
    *oy=rolling_anchor[1]+(radius+ry)*c-radius;
    *oz=rolling_anchor[2]+rz+rolling_axis[2]*((radius+ry)*s-along);
    return 1;
}

/* Can't include GXTev.h — it uses enum types while we use u32 */
void GXSetTevColorIn(u32 stage, u32 a, u32 b, u32 c, u32 d);
void GXSetTevAlphaIn(u32 stage, u32 a, u32 b, u32 c, u32 d);
void GXSetTevColorOp(u32 stage, u32 op, u32 bias, u32 scale, GXBool clamp, u32 out_reg);
void GXSetTevAlphaOp(u32 stage, u32 op, u32 bias, u32 scale, GXBool clamp, u32 out_reg);

typedef struct { u8 r, g, b, a; } GXColor;

#undef glUniform1i
#undef glUniform2i
#undef glUniform3i
#undef glUniform4i
#undef glUniform1f
#undef glUniform2f
#undef glUniform3f
#undef glUniform4f
#undef glUniform1iv
#undef glUniform2iv
#undef glUniform3iv
#undef glUniform4iv
#undef glUniform4fv
#undef glUniform3fv
#undef glUniformMatrix3fv
#undef glUniformMatrix4fv

#define glUniform1i(...)        (pc_profiler_add_count_uniform(), glad_glUniform1i(__VA_ARGS__))
#define glUniform2i(...)        (pc_profiler_add_count_uniform(), glad_glUniform2i(__VA_ARGS__))
#define glUniform3i(...)        (pc_profiler_add_count_uniform(), glad_glUniform3i(__VA_ARGS__))
#define glUniform4i(...)        (pc_profiler_add_count_uniform(), glad_glUniform4i(__VA_ARGS__))
#define glUniform1f(...)        (pc_profiler_add_count_uniform(), glad_glUniform1f(__VA_ARGS__))
#define glUniform2f(...)        (pc_profiler_add_count_uniform(), glad_glUniform2f(__VA_ARGS__))
#define glUniform3f(...)        (pc_profiler_add_count_uniform(), glad_glUniform3f(__VA_ARGS__))
#define glUniform4f(...)        (pc_profiler_add_count_uniform(), glad_glUniform4f(__VA_ARGS__))
#define glUniform1iv(...)       (pc_profiler_add_count_uniform(), glad_glUniform1iv(__VA_ARGS__))
#define glUniform2iv(...)       (pc_profiler_add_count_uniform(), glad_glUniform2iv(__VA_ARGS__))
#define glUniform3iv(...)       (pc_profiler_add_count_uniform(), glad_glUniform3iv(__VA_ARGS__))
#define glUniform4iv(...)       (pc_profiler_add_count_uniform(), glad_glUniform4iv(__VA_ARGS__))
#define glUniform4fv(...)       (pc_profiler_add_count_uniform(), glad_glUniform4fv(__VA_ARGS__))
#define glUniform3fv(...)       (pc_profiler_add_count_uniform(), glad_glUniform3fv(__VA_ARGS__))
#define glUniformMatrix3fv(...) (pc_profiler_add_count_uniform(), glad_glUniformMatrix3fv(__VA_ARGS__))
#define glUniformMatrix4fv(...) (pc_profiler_add_count_uniform(), glad_glUniformMatrix4fv(__VA_ARGS__))

/* --- Global GX State --- */
PCGXState g_gx;

#ifdef PC_ENHANCEMENTS
/* Aspect correction: factor = gc_aspect/actual_aspect, offset = content left edge in GC coords */
static float g_aspect_factor = 1.0f;
static float g_aspect_offset = 0.0f;
static int   g_aspect_active = 0;

static void pc_gx_update_aspect(void) {
    float gc_aspect = (float)PC_GC_WIDTH / (float)PC_GC_HEIGHT;
    float win_aspect = (float)g_pc_window_w / (float)g_pc_window_h;
    if (g_pc_settings.aspect_mode == 0 && fabsf(win_aspect-gc_aspect) > 0.01f) {
        g_aspect_factor = gc_aspect / win_aspect;
        g_aspect_offset = (1.0f - g_aspect_factor) / 2.0f * (float)PC_GC_WIDTH;
        g_aspect_active = 1;
    } else {
        g_aspect_factor = 1.0f;
        g_aspect_offset = 0.0f;
        g_aspect_active = 0;
    }
}

/* EFB capture: keep full-res GL textures from GXCopyTex instead of downsampling to 640x480 */
#define MAX_EFB_CAPTURES 4
static struct {
    u32 dest_ptr;
    GLuint gl_tex;
} s_efb_captures[MAX_EFB_CAPTURES];
static int s_efb_capture_count = 0;

void pc_gx_efb_capture_store(u32 dest_ptr, GLuint gl_tex) {
    for (int i = 0; i < s_efb_capture_count; i++) {
        if (s_efb_captures[i].dest_ptr == dest_ptr) {
            if (s_efb_captures[i].gl_tex)
                glDeleteTextures(1, &s_efb_captures[i].gl_tex);
            s_efb_captures[i].gl_tex = gl_tex;
            return;
        }
    }
    if (s_efb_capture_count >= MAX_EFB_CAPTURES) {
        if (s_efb_captures[0].gl_tex)
            glDeleteTextures(1, &s_efb_captures[0].gl_tex);
        memmove(&s_efb_captures[0], &s_efb_captures[1],
                (MAX_EFB_CAPTURES - 1) * sizeof(s_efb_captures[0]));
        s_efb_capture_count = MAX_EFB_CAPTURES - 1;
    }
    s_efb_captures[s_efb_capture_count].dest_ptr = dest_ptr;
    s_efb_captures[s_efb_capture_count].gl_tex = gl_tex;
    s_efb_capture_count++;
}

GLuint pc_gx_efb_capture_find(u32 data_ptr) {
    for (int i = 0; i < s_efb_capture_count; i++) {
        if (s_efb_captures[i].dest_ptr == data_ptr)
            return s_efb_captures[i].gl_tex;
    }
    return 0;
}

void pc_gx_efb_capture_cleanup(void) {
    for (int i = 0; i < s_efb_capture_count; i++) {
        if (s_efb_captures[i].gl_tex)
            glDeleteTextures(1, &s_efb_captures[i].gl_tex);
    }
    s_efb_capture_count = 0;
}
#endif

typedef struct {
    int active;
    u8* buf;
    u32 size;
    u32 off;
    int overflow;
} PCGXDLBuildState;

static PCGXDLBuildState g_pc_gx_dl = {0};

enum {
    PCGX_DL_OP_TEXCOPY_SRC = 0x1001,
    PCGX_DL_OP_TEXCOPY_DST = 0x1002,
    PCGX_DL_OP_COPY_FILTER = 0x1003,
    PCGX_DL_OP_COPY_TEX = 0x1004,
};

static void pc_gx_dl_write(const void* data, u32 len) {
    if (!g_pc_gx_dl.active || g_pc_gx_dl.overflow) return;
    if (g_pc_gx_dl.off + len > g_pc_gx_dl.size) {
        g_pc_gx_dl.overflow = 1;
        return;
    }
    memcpy(g_pc_gx_dl.buf + g_pc_gx_dl.off, data, len);
    g_pc_gx_dl.off += len;
}

static void pc_unpack_rgba8f(u32 packed, float* out_rgba) {
    /* Shift-based: works for colors packed as (r<<24|g<<16|b<<8|a) from N64 DL data */
    out_rgba[0] = ((packed >> 24) & 0xFF) / 255.0f;
    out_rgba[1] = ((packed >> 16) & 0xFF) / 255.0f;
    out_rgba[2] = ((packed >> 8) & 0xFF) / 255.0f;
    out_rgba[3] = (packed & 0xFF) / 255.0f;
}

/* Byte-based: reads RGBA from memory order. Use for GXColor structs (not N64 DL data). */
static void pc_unpack_gxcolor_f(u32 color_as_u32, float* out_rgba) {
    const u8* bytes = (const u8*)&color_as_u32;
    out_rgba[0] = bytes[0] / 255.0f;
    out_rgba[1] = bytes[1] / 255.0f;
    out_rgba[2] = bytes[2] / 255.0f;
    out_rgba[3] = bytes[3] / 255.0f;
}

/* Map tex matrix ID to slot: raw 0..9, GX enum 30..57 (stride 3), or 60=identity */
static int pc_tex_mtx_id_to_slot(int id) {
    if (id == GX_IDENTITY) return -1;
    if (id >= 0 && id < 10) return id;
    if (id >= GX_TEXMTX0 && id < GX_IDENTITY) return (id - GX_TEXMTX0) / 3;
    return -1;
}

static GLint pc_gx_get_uniform_location_profiled(GLuint shader, const char* name) {
    Uint64 t = pc_profiler_begin_timer();
    GLint loc = glGetUniformLocation(shader, name);
    pc_profiler_add_time(PC_PROF_TIMER_UNIFORM_LOOKUP, t);
    pc_profiler_add_count_uniform_lookup();
    return loc;
}

static void pc_gx_use_program_profiled(GLuint shader) {
    Uint64 t = pc_profiler_begin_timer();
    glUseProgram(shader);
    pc_profiler_add_time(PC_PROF_TIMER_SHADER_SWITCH, t);
    pc_profiler_add_count_shader_switch();
}

#ifndef PC_GX_ENABLE_TEXTURE_BIND_CACHE
#define PC_GX_ENABLE_TEXTURE_BIND_CACHE 0
#endif

#if PC_GX_ENABLE_TEXTURE_BIND_CACHE
#define PC_GX_MAX_TEXTURE_UNITS 8
static int s_active_texture_unit = -1;
static GLuint s_bound_texture_2d[PC_GX_MAX_TEXTURE_UNITS];
#endif

void pc_gx_texture_bind_cache_invalidate(void) {
#if PC_GX_ENABLE_TEXTURE_BIND_CACHE
    s_active_texture_unit = -1;
    memset(s_bound_texture_2d, 0, sizeof(s_bound_texture_2d));
#endif
}

static void pc_gx_active_texture_cached(GLenum texture) {
#if PC_GX_ENABLE_TEXTURE_BIND_CACHE
    int unit = (int)(texture - GL_TEXTURE0);
    if (unit < 0 || unit >= PC_GX_MAX_TEXTURE_UNITS) {
        glActiveTexture(texture);
        s_active_texture_unit = -1;
        return;
    }
    if (s_active_texture_unit == unit) return;
    glActiveTexture(texture);
    s_active_texture_unit = unit;
#else
    glActiveTexture(texture);
#endif
}

static void pc_gx_bind_texture_profiled(GLenum target, GLuint texture) {
#if PC_GX_ENABLE_TEXTURE_BIND_CACHE
    int unit = s_active_texture_unit;
    if (target == GL_TEXTURE_2D && unit >= 0 && unit < PC_GX_MAX_TEXTURE_UNITS &&
        s_bound_texture_2d[unit] == texture) {
        return;
    }

    Uint64 t = pc_profiler_begin_timer();
    glBindTexture(target, texture);
    pc_profiler_add_time(PC_PROF_TIMER_TEXTURE_BIND, t);
    pc_profiler_add_count_texture_bind();

    if (target == GL_TEXTURE_2D && unit >= 0 && unit < PC_GX_MAX_TEXTURE_UNITS) {
        s_bound_texture_2d[unit] = texture;
    }
#else
    Uint64 t = pc_profiler_begin_timer();
    glBindTexture(target, texture);
    pc_profiler_add_time(PC_PROF_TIMER_TEXTURE_BIND, t);
    pc_profiler_add_count_texture_bind();
#endif
}

static void pc_gx_buffer_data_profiled(GLenum target, GLsizeiptr size, const void* data, GLenum usage) {
    Uint64 t = pc_profiler_begin_timer();
    glBufferData(target, size, data, usage);
    pc_profiler_add_time(PC_PROF_TIMER_BUFFER_UPLOAD, t);
    pc_profiler_add_count_buffer_upload((size_t)size);
}

/* Commit pending vertex + flush batch to GL. Used by GXBegin/GXEnd/GXCopyDisp/etc. */
static void pc_gx_commit_pending_and_flush(void) {
    if (!g_gx.in_begin) return;
    if (g_gx.vertex_pending && g_gx.current_vertex_idx < PC_GX_MAX_VERTS) {
        g_gx.vertex_buffer[g_gx.current_vertex_idx] = g_gx.current_vertex;
        g_gx.current_vertex_idx++;
        g_gx.vertex_pending = 0;
    }
    g_gx.in_begin = 0;
    if (g_gx.current_vertex_idx > g_gx.pending_verts)
        pc_gx_flush_vertices();
}

/* emu64 omits GXEnd() — flush when expected vertex count is reached so the
 * batch renders with the state it was built with, not subsequent state changes. */
void pc_gx_flush_if_begin_complete(void) {
    if (!g_gx.in_begin || g_gx.expected_vertex_count <= 0) return;

    int submitted = g_gx.current_vertex_idx + (g_gx.vertex_pending ? 1 : 0);
    if (submitted < g_gx.expected_vertex_count) return;

    pc_gx_commit_pending_and_flush();
}

int pc_emu64_frame_cmds = 0;
int pc_emu64_frame_noop_cmds = 0;
int pc_emu64_frame_tri_cmds = 0;
int pc_emu64_frame_vtx_cmds = 0;
int pc_emu64_frame_dl_cmds = 0;
int pc_emu64_frame_cull_visible = 0;
int pc_emu64_frame_cull_rejected = 0;

/* Unit7 is outside TEV0..2 and indirect3..6; GL3.3 guarantees >=16.
 * This immutable 4KiB table replaces per-fragment dynamic GLSL array access. */
static void pc_gx_donor_luts_init(void) {
    glGenTextures(1, &s_donor_lut_texture);
    pc_gx_active_texture_cached(GL_TEXTURE7);
    pc_gx_bind_texture_profiled(GL_TEXTURE_2D, s_donor_lut_texture);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_NEAREST);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_NEAREST);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAX_LEVEL, 0);
    glTexImage2D(GL_TEXTURE_2D, 0, GL_R32F, 256, 4, 0, GL_RED, GL_FLOAT, pc_donor_lut_values);
    pc_gx_active_texture_cached(GL_TEXTURE0);
}

void pc_gx_init(void) {
    memset(&g_gx, 0, sizeof(g_gx));

    g_gx.projection_type = GX_PERSPECTIVE;
    g_gx.num_tev_stages = 1;
    g_gx.num_chans = 1;
    g_gx.num_tex_gens = 0;
    g_gx.cull_mode = GX_CULL_NONE;
    g_gx.z_compare_enable = 1;
    g_gx.z_compare_func = GX_LEQUAL;
    g_gx.z_update_enable = 1;
    g_gx.color_update_enable = 1;
    g_gx.alpha_update_enable = 1;
    g_gx.blend_mode = GX_BM_NONE;
    g_gx.blend_src = GX_BL_ONE;
    g_gx.blend_dst = GX_BL_ZERO;
    g_gx.clear_color[3] = 0.0f;
    g_gx.clear_depth = 1.0f;

    for (int i = 0; i < 4; i++)
        g_gx.projection_mtx[i][i] = 1.0f;

    for (int i = 0; i < 10; i++) {
        g_gx.pos_mtx[i][0][0] = 1.0f;
        g_gx.pos_mtx[i][1][1] = 1.0f;
        g_gx.pos_mtx[i][2][2] = 1.0f;
    }

    for (int i = 0; i < 10; i++) {
        g_gx.nrm_mtx[i][0][0] = 1.0f;
        g_gx.nrm_mtx[i][1][1] = 1.0f;
        g_gx.nrm_mtx[i][2][2] = 1.0f;
    }

    g_gx.tev_swap_table[0] = (PCGXTevSwapTable){0, 1, 2, 3};
    g_gx.tev_swap_table[1] = (PCGXTevSwapTable){0, 1, 2, 3};
    g_gx.tev_swap_table[2] = (PCGXTevSwapTable){0, 1, 2, 3};
    g_gx.tev_swap_table[3] = (PCGXTevSwapTable){0, 1, 2, 3};

    for (int i = 0; i < 2; i++) {
        g_gx.chan_mat_color[i][0] = 1.0f;
        g_gx.chan_mat_color[i][1] = 1.0f;
        g_gx.chan_mat_color[i][2] = 1.0f;
        g_gx.chan_mat_color[i][3] = 1.0f;
    }

    /* Quad-to-triangle index buffer */
    for (int q = 0; q < PC_GX_MAX_VERTS / 4; q++) {
        int base = q * 4;
        quad_index_buf[q * 6 + 0] = base + 0;
        quad_index_buf[q * 6 + 1] = base + 1;
        quad_index_buf[q * 6 + 2] = base + 2;
        quad_index_buf[q * 6 + 3] = base + 0;
        quad_index_buf[q * 6 + 4] = base + 2;
        quad_index_buf[q * 6 + 5] = base + 3;
    }

    glGenVertexArrays(1, &g_gx.vao);
    glGenBuffers(1, &g_gx.vbo);
    glGenBuffers(1, &g_gx.ebo);

    /* VAO setup: attrib pointers persist since PCGXVertex layout and VBO ID never change */
    glBindVertexArray(g_gx.vao);
    glBindBuffer(GL_ARRAY_BUFFER, g_gx.vbo);
    glBufferData(GL_ARRAY_BUFFER, PC_GX_MAX_VERTS * sizeof(PCGXVertex), NULL, GL_STREAM_DRAW);
    {
        size_t stride = sizeof(PCGXVertex);
        glEnableVertexAttribArray(0);
        glVertexAttribPointer(0, 3, GL_FLOAT, GL_FALSE, stride, (void*)offsetof(PCGXVertex, position));
        glEnableVertexAttribArray(1);
        glVertexAttribPointer(1, 3, GL_FLOAT, GL_FALSE, stride, (void*)offsetof(PCGXVertex, normal));
        glEnableVertexAttribArray(2);
        glVertexAttribPointer(2, 4, GL_UNSIGNED_BYTE, GL_TRUE, stride, (void*)offsetof(PCGXVertex, color0));
        glEnableVertexAttribArray(3);
        glVertexAttribPointer(3, 2, GL_FLOAT, GL_FALSE, stride, (void*)offsetof(PCGXVertex, texcoord));
    }

    glBindBuffer(GL_ELEMENT_ARRAY_BUFFER, g_gx.ebo);
    glBufferData(GL_ELEMENT_ARRAY_BUFFER, sizeof(quad_index_buf), quad_index_buf, GL_STATIC_DRAW);

    glBindVertexArray(0);

    pc_gx_tev_init();
    pc_gx_texture_init();
    pc_gx_donor_luts_init();
    pc_gx_texture_bind_cache_invalidate();

    glEnable(GL_DEPTH_TEST);
    glDepthFunc(GL_LEQUAL);
    glEnable(GL_BLEND);
    glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA);

    g_gx.dirty = PC_GX_DIRTY_ALL;
}

void pc_gx_begin_frame(void) {
    /* Profiler frame opens in graph_main so game_main is captured */
    Uint64 prof_start = pc_profiler_begin_timer();
    pc_emu64_frame_cmds = 0;
    pc_emu64_frame_noop_cmds = 0;
    pc_emu64_frame_tri_cmds = 0;
    pc_emu64_frame_vtx_cmds = 0;
    pc_emu64_frame_dl_cmds = 0;
    pc_emu64_frame_cull_visible = 0;
    pc_emu64_frame_cull_rejected = 0;
    pc_gx_draw_call_count = 0;
    g_pc_widescreen_stretch = 0;
    pc_gx_draw_pending();
    /* glClear respects write masks — must enable all before clearing */
    glDepthMask(GL_TRUE);
    glColorMask(GL_TRUE, GL_TRUE, GL_TRUE, GL_TRUE);
    /* Masks were changed behind the dirty system; reapply at first flush */
    DIRTY(PC_GX_DIRTY_DEPTH | PC_GX_DIRTY_COLOR_MASK);
#ifdef PC_ENHANCEMENTS
    pc_gx_update_aspect();
    glDisable(GL_SCISSOR_TEST);
    glViewport(0, 0, g_pc_window_w, g_pc_window_h);
    pc_gx_viewport_state_invalidate();
#endif
    glClearDepth(g_gx.clear_depth);
    glClearColor(g_gx.clear_color[0], g_gx.clear_color[1], g_gx.clear_color[2], g_gx.clear_color[3]);
    glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT);
    pc_profiler_add_time(PC_PROF_TIMER_GX_BEGIN, prof_start);
}

void pc_gx_restore_after_nes(void) {
    /* NES emulator uses its own shader/VAO/state. Rebind the game's GL objects
     * and mark all GX state dirty so uniforms/textures get re-uploaded. */
    glBindVertexArray(g_gx.vao);
    glBindBuffer(GL_ARRAY_BUFFER, g_gx.vbo);
    glBindBuffer(GL_ELEMENT_ARRAY_BUFFER, g_gx.ebo);
    g_gx.dirty = PC_GX_DIRTY_ALL;
    g_gx.current_shader = 0; /* Force shader rebind on next draw */
    pc_gx_texture_bind_cache_invalidate();
    pc_gx_viewport_state_invalidate();
    glEnable(GL_DEPTH_TEST);
    glDepthFunc(GL_LEQUAL);
    glEnable(GL_BLEND);
    glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA);
}

void pc_gx_shutdown(void) {
    if (s_donor_lut_texture) glDeleteTextures(1, &s_donor_lut_texture);
    s_donor_lut_texture=0;
    pc_gx_tev_shutdown();
    pc_gx_texture_shutdown();
#ifdef PC_ENHANCEMENTS
    pc_gx_efb_capture_cleanup();
#endif

    if (g_gx.ebo) glDeleteBuffers(1, &g_gx.ebo);
    if (g_gx.vbo) glDeleteBuffers(1, &g_gx.vbo);
    if (g_gx.vao) glDeleteVertexArrays(1, &g_gx.vao);
}

/* --- Vertex Submission --- */
void GXBegin(u32 primitive, u32 vtxfmt, u16 nverts) {
    /* Auto-flush previous batch if GXEnd was omitted (normal on real HW) */
    pc_gx_commit_pending_and_flush();

    if (g_gx.pending_verts > 0 && g_gx.pending_verts + (int)nverts > PC_GX_MAX_VERTS)
        pc_gx_draw_pending();

    g_gx.current_primitive = primitive;
    g_gx.current_vtxfmt = vtxfmt;
    g_gx.expected_vertex_count = nverts;
    g_gx.current_vertex_idx = g_gx.pending_verts;
    g_gx.in_begin = 1;
    g_gx.vertex_pending = 0;
    memset(&g_gx.current_vertex, 0, sizeof(PCGXVertex));
    g_gx.current_vertex.color0[0] = 255;
    g_gx.current_vertex.color0[1] = 255;
    g_gx.current_vertex.color0[2] = 255;
    g_gx.current_vertex.color0[3] = 255;
}

void GXEnd(void) {
    pc_gx_commit_pending_and_flush();
}

void GXPosition3f32(f32 x, f32 y, f32 z) {
    /* Deferred commit: position call commits the previous vertex */
    if (g_gx.vertex_pending && g_gx.current_vertex_idx < PC_GX_MAX_VERTS) {
        g_gx.vertex_buffer[g_gx.current_vertex_idx] = g_gx.current_vertex;
        g_gx.current_vertex_idx++;
    }

    /* Reset vertex but carry last color forward */
    u8 r = g_gx.current_vertex.color0[0];
    u8 g = g_gx.current_vertex.color0[1];
    u8 b = g_gx.current_vertex.color0[2];
    u8 a = g_gx.current_vertex.color0[3];
    memset(&g_gx.current_vertex, 0, sizeof(PCGXVertex));
    g_gx.current_vertex.color0[0] = r;
    g_gx.current_vertex.color0[1] = g;
    g_gx.current_vertex.color0[2] = b;
    g_gx.current_vertex.color0[3] = a;

    g_gx.current_vertex.position[0] = x;
    g_gx.current_vertex.position[1] = y;
    g_gx.current_vertex.position[2] = z;
    g_gx.vertex_pending = 1;
}

void GXPosition3u16(u16 x, u16 y, u16 z) { GXPosition3f32((f32)x, (f32)y, (f32)z); }
void GXPosition3s16(s16 x, s16 y, s16 z) { GXPosition3f32((f32)x, (f32)y, (f32)z); }
void GXPosition3u8(u8 x, u8 y, u8 z) { GXPosition3f32((f32)x, (f32)y, (f32)z); }
void GXPosition3s8(s8 x, s8 y, s8 z) { GXPosition3f32((f32)x, (f32)y, (f32)z); }

void GXPosition2f32(f32 x, f32 y) { GXPosition3f32(x, y, 0.0f); }
void GXPosition2u16(u16 x, u16 y) { GXPosition3f32((f32)x, (f32)y, 0.0f); }
void GXPosition2s16(s16 x, s16 y) { GXPosition3f32((f32)x, (f32)y, 0.0f); }
void GXPosition2u8(u8 x, u8 y) { GXPosition3f32((f32)x, (f32)y, 0.0f); }
void GXPosition2s8(s8 x, s8 y) { GXPosition3f32((f32)x, (f32)y, 0.0f); }

void GXPosition1x16(u16 index) {
    if (g_gx.array_base[GX_VA_POS]) {
        const u8* base = (const u8*)g_gx.array_base[GX_VA_POS];
        const f32* pos = (const f32*)(base + index * g_gx.array_stride[GX_VA_POS]);
        GXPosition3f32(pos[0], pos[1], pos[2]);
    }
}
void GXPosition1x8(u8 index) { GXPosition1x16(index); }

void GXNormal3f32(f32 x, f32 y, f32 z) {
    g_gx.current_vertex.normal[0] = x;
    g_gx.current_vertex.normal[1] = y;
    g_gx.current_vertex.normal[2] = z;
}
void GXNormal3s16(s16 x, s16 y, s16 z) {
    GXNormal3f32(x / 32767.0f, y / 32767.0f, z / 32767.0f);
}
void GXNormal3s8(s8 x, s8 y, s8 z) {
    GXNormal3f32(x / 127.0f, y / 127.0f, z / 127.0f);
}
void GXNormal1x16(u16 index) {
    if (g_gx.array_base[GX_VA_NRM]) {
        const u8* base = (const u8*)g_gx.array_base[GX_VA_NRM];
        const f32* nrm = (const f32*)(base + index * g_gx.array_stride[GX_VA_NRM]);
        GXNormal3f32(nrm[0], nrm[1], nrm[2]);
    }
}
void GXNormal1x8(u8 index) { GXNormal1x16(index); }

void GXColor4u8(u8 r, u8 g, u8 b, u8 a) {
    g_gx.current_vertex.color0[0] = r;
    g_gx.current_vertex.color0[1] = g;
    g_gx.current_vertex.color0[2] = b;
    g_gx.current_vertex.color0[3] = a;
}
void GXColor3u8(u8 r, u8 g, u8 b) { GXColor4u8(r, g, b, 255); }
void GXColor1u32(u32 clr) {
    GXColor4u8((clr >> 24) & 0xFF, (clr >> 16) & 0xFF, (clr >> 8) & 0xFF, clr & 0xFF);
}
void GXColor1u16(u16 clr) { GXColor1u32((u32)clr << 16); }
void GXColor1x16(u16 index) {
    if (g_gx.array_base[GX_VA_CLR0]) {
        const u8* base = (const u8*)g_gx.array_base[GX_VA_CLR0];
        const u8* clr = base + index * g_gx.array_stride[GX_VA_CLR0];
        GXColor4u8(clr[0], clr[1], clr[2], clr[3]);
    }
}
void GXColor1x8(u8 index) { GXColor1x16(index); }

void GXColor4f32(float r, float g, float b, float a) {
    GXColor4u8((u8)(r * 255.0f + 0.5f), (u8)(g * 255.0f + 0.5f),
               (u8)(b * 255.0f + 0.5f), (u8)(a * 255.0f + 0.5f));
}

void GXTexCoord2f32(f32 s, f32 t) {
    /* Channel 0 only — emu64 emits one texcoord; multi-tex uses matrix transforms */
    g_gx.current_vertex.texcoord[0][0] = s;
    g_gx.current_vertex.texcoord[0][1] = t;
}
void GXTexCoord2u16(u16 s, u16 t) { GXTexCoord2f32((f32)s, (f32)t); }
void GXTexCoord2s16(s16 s, s16 t) {
    /* No frac scaling — emu64 already provides pre-scaled texcoords */
    GXTexCoord2f32((f32)s, (f32)t);
}
void GXTexCoord2u8(u8 s, u8 t) { GXTexCoord2f32((f32)s, (f32)t); }
void GXTexCoord2s8(s8 s, s8 t) { GXTexCoord2f32((f32)s, (f32)t); }

void GXTexCoord1f32(f32 s, f32 t) { GXTexCoord2f32(s, t); }
void GXTexCoord1u16(u16 s, u16 t) { GXTexCoord2f32((f32)s, (f32)t); }
void GXTexCoord1s16(s16 s, s16 t) { GXTexCoord2s16(s, t); }
void GXTexCoord1u8(u8 s, u8 t) { GXTexCoord2f32((f32)s, (f32)t); }
void GXTexCoord1s8(s8 s, s8 t) { GXTexCoord2f32((f32)s, (f32)t); }

void GXTexCoord1x16(u16 index) {
    if (g_gx.array_base[GX_VA_TEX0]) {
        const u8* base = (const u8*)g_gx.array_base[GX_VA_TEX0];
        const f32* tc = (const f32*)(base + index * g_gx.array_stride[GX_VA_TEX0]);
        GXTexCoord2f32(tc[0], tc[1]);
    }
}
void GXTexCoord1x8(u8 index) { GXTexCoord1x16(index); }

/* --- Uniform Location Cache --- */
void pc_gx_cache_uniform_locations(GLuint shader, PCGXUloc* u) {
    char name[48];
    int i;
    #define UL(n) pc_gx_get_uniform_location_profiled(shader, n)

    u->projection = UL("u_projection");
    u->modelview  = UL("u_modelview");
    u->normal_mtx = UL("u_normal_mtx");
    u->rolling_radius = UL("u_rolling_radius");
    u->rolling_camera = UL("u_rolling_camera");
    u->rolling_anchor = UL("u_rolling_anchor");
    u->rolling_axis = UL("u_rolling_axis");
    u->rolling_view_rotation = UL("u_rolling_view_rotation");

    u->tev_prev = UL("u_tev_prev");
    u->tev_reg0 = UL("u_tev_reg0");
    u->tev_reg1 = UL("u_tev_reg1");
    u->tev_reg2 = UL("u_tev_reg2");

    u->num_tev_stages = UL("u_num_tev_stages");
    for (i = 0; i < PC_GX_MAX_TEV_STAGES; i++) {
        snprintf(name, sizeof(name), "u_tev_color_in[%d]", i);
        u->tev_color_in[i] = UL(name);
        snprintf(name, sizeof(name), "u_tev_alpha_in[%d]", i);
        u->tev_alpha_in[i] = UL(name);
        snprintf(name, sizeof(name), "u_tev_color_op[%d]", i);
        u->tev_color_op[i] = UL(name);
        snprintf(name, sizeof(name), "u_tev_alpha_op[%d]", i);
        u->tev_alpha_op[i] = UL(name);
        snprintf(name, sizeof(name), "u_tev_tc_src[%d]", i);
        u->tev_tc_src[i] = UL(name);
        snprintf(name, sizeof(name), "u_tev_ind_cfg[%d]", i);
        u->tev_ind_cfg[i] = UL(name);
        snprintf(name, sizeof(name), "u_tev_ind_wrap[%d]", i);
        u->tev_ind_wrap[i] = UL(name);
    }

    u->kcolor   = UL("u_kcolor");
    u->tev_ksel = UL("u_tev_ksel");

    u->alpha_ctrl = UL("u_alpha_ctrl");
    u->alpha_refs = UL("u_alpha_refs");

    u->lighting_enabled = UL("u_lighting_cfg0");
    u->mat_color  = UL("u_chan_color[0]");
    u->amb_color  = -1;
    u->chan_mat_src = -1;
    u->chan_amb_src = -1;
    u->num_chans  = -1;
    u->alpha_lighting_enabled = UL("u_lighting_cfg1");
    u->alpha_mat_src = -1;

    u->light_mask = -1;
    for (i = 0; i < 8; i++) {
        snprintf(name, sizeof(name), "u_light_pos[%d]", i);
        u->light_pos[i] = UL(name);
        snprintf(name, sizeof(name), "u_light_color[%d]", i);
        u->light_color[i] = UL(name);
    }

    u->texmtx_enable[0] = UL("u_texmtx_enable[0]");
    u->texmtx_row0[0]  = UL("u_texmtx_row0[0]");
    u->texmtx_row1[0]  = UL("u_texmtx_row1[0]");
    u->texgen_src[0]   = UL("u_texgen_src[0]");
    u->texmtx_enable[1] = -1;
    u->texmtx_row0[1]  = -1;
    u->texmtx_row1[1]  = -1;
    u->texgen_src[1]   = -1;

    u->use_texture0 = UL("u_use_texture[0]");
    u->use_texture1 = -1;
    u->use_texture2 = -1;
    u->texture0 = UL("u_texture0");
    u->donor_luts = UL("u_donor_luts");
    u->terrain_kind = UL("u_terrain_kind[0]");
    u->water_phase = UL("u_water_phase");
    u->donor_water_frame = UL("u_donor_water_frame");
    u->terrain_normals = UL("u_terrain_normals");
    u->donor_light_enabled = UL("u_donor_light_enabled");
    u->nl_char = UL("u_nl_char");
    u->donor_ground_direction = UL("u_donor_ground_direction");
    u->donor_ground_ambient = UL("u_donor_ground_ambient");
    u->donor_actor_direction = UL("u_donor_actor_direction");
    u->donor_water_base = UL("u_donor_water_base");
    u->donor_water_buffer = UL("u_donor_water_buffer");
    u->donor_water_bank = UL("u_donor_water_bank");
    u->donor_diffuse = UL("u_donor_diffuse");
    u->donor_specular = UL("u_donor_specular");
    u->donor_hemi_sky = UL("u_donor_hemi_sky");
    u->donor_hemi_ground = UL("u_donor_hemi_ground");
    u->texture1 = UL("u_texture1");
    u->texture2 = UL("u_texture2");

    u->num_ind_stages = UL("u_num_ind_stages");
    for (i = 0; i < 4; i++) {
        snprintf(name, sizeof(name), "u_ind_tex%d", i);
        u->ind_tex[i] = UL(name);
        snprintf(name, sizeof(name), "u_ind_scale[%d]", i);
        u->ind_scale[i] = UL(name);
    }
    for (i = 0; i < PC_GX_MAX_TEV_STAGES; i++) {
        snprintf(name, sizeof(name), "u_ind_mtx_r0[%d]", i);
        u->ind_mtx_r0[i] = UL(name);
        snprintf(name, sizeof(name), "u_ind_mtx_r1[%d]", i);
        u->ind_mtx_r1[i] = UL(name);
    }

    u->fog_type   = UL("u_fog_params");
    u->fog_enable = UL("u_fog_enable");
    u->fog_start  = -1;
    u->fog_end    = -1;
    u->fog_color  = UL("u_fog_color");

    /* Per-stage bias/scale/clamp/output */
    for (i = 0; i < PC_GX_MAX_TEV_STAGES; i++) {
        snprintf(name, sizeof(name), "u_tev_bsc[%d]", i);
        u->tev_bsc[i] = UL(name);
        snprintf(name, sizeof(name), "u_tev_out[%d]", i);
        u->tev_out[i] = UL(name);
        snprintf(name, sizeof(name), "u_tev_swap[%d]", i);
        u->tev_swap[i] = UL(name);
    }
    u->swap_table = UL("u_swap_table");

    #undef UL
}

/* Uniform groups this program hasn't seen the latest values of */
static unsigned int pc_gx_variant_stale_groups(const PCGXShaderVariant* v) {
    unsigned int stale = 0;
    for (int b = 0; (1u << b) <= PC_GX_DIRTY_UNIFORM_GROUPS; b++) {
        if (v->uploaded_seq[b] != g_gx.group_seq[b]) stale |= (1u << b);
    }
    return stale;
}

/* --- Vertex Flush --- */
int pc_gx_draw_call_count = 0;
#include "pc_surface_curve.c_inc"


/* Draws the deferred run. Must run before any GL call that bypasses the
 * dirty system (viewport, scissor, readpixels, raw texture binds, swap)
 * so the run renders with the state it was built under. */
void pc_gx_draw_pending(void) {
    int count = g_gx.pending_verts;
    if (count == 0) return;
    {
        extern int g_pc_tree_viewer;
        static int tree_debug = 0;
        if (g_pc_tree_viewer && !tree_debug++) {
            PCGXVertex* v = g_gx.vertex_buffer;
            printf("[TreeDebug] count=%d pos=%f,%f,%f color=%u,%u,%u,%u uv=%f,%f\n",
                count,v->position[0],v->position[1],v->position[2],v->color0[0],v->color0[1],v->color0[2],v->color0[3],v->texcoord[0][0],v->texcoord[0][1]);
            for (int r=0;r<4;r++) printf("[TreeDebug] P %f %f %f %f\n",g_gx.projection_mtx[r][0],g_gx.projection_mtx[r][1],g_gx.projection_mtx[r][2],g_gx.projection_mtx[r][3]);
            printf("[TreeDebug] matrix=%d texture=%d,%d fmt=%d\n",g_gx.current_mtx,g_gx.tex_obj_w[0],g_gx.tex_obj_h[0],g_gx.tex_obj_fmt[0]);
            for (int r=0;r<3;r++) printf("[TreeDebug] M %f %f %f %f\n",g_gx.pos_mtx[g_gx.current_mtx][r][0],g_gx.pos_mtx[g_gx.current_mtx][r][1],g_gx.pos_mtx[g_gx.current_mtx][r][2],g_gx.pos_mtx[g_gx.current_mtx][r][3]);
        }
    }

    glBindVertexArray(g_gx.vao);
    glBindBuffer(GL_ARRAY_BUFFER, g_gx.vbo);
    Uint64 draw_start = pc_profiler_begin_timer();
    int surface_drawn=pc_surface_curve_draw(g_gx.vertex_buffer,count,g_gx.pending_prim);
    if(!surface_drawn) {
    pc_gx_buffer_data_profiled(GL_ARRAY_BUFFER, count * sizeof(PCGXVertex), g_gx.vertex_buffer, GL_STREAM_DRAW);
    if (g_gx.pending_prim == GX_QUADS) {
        int num_indices = (count / 4) * 6;
        glDrawElements(GL_TRIANGLES, num_indices, GL_UNSIGNED_SHORT, 0);
        pc_profiler_add_count_draw(count, num_indices);
        PC_GL_CHECK("glDrawElements");
    } else {
        glDrawArrays(GL_TRIANGLES, 0, count);
        pc_profiler_add_count_draw(count, 0);
        PC_GL_CHECK("glDrawArrays");
    }
    pc_gx_draw_call_count++;
    }
    pc_profiler_add_time(PC_PROF_TIMER_DRAW_SUBMIT, draw_start);

    /* Shift verts committed after the run down to the buffer start */
    int extra = g_gx.current_vertex_idx - count;
    if (extra > 0) {
        memmove(g_gx.vertex_buffer, g_gx.vertex_buffer + count,
                (size_t)extra * sizeof(PCGXVertex));
        g_gx.current_vertex_idx = extra;
    } else {
        g_gx.current_vertex_idx = 0;
    }
    g_gx.pending_verts = 0;
}

void pc_gx_flush_vertices(void) {
    int count = g_gx.current_vertex_idx - g_gx.pending_verts;
    if (count <= 0) return;

    Uint64 flush_start = pc_profiler_begin_timer();
    pc_profiler_add_count_flush();

    PCGXShaderVariant* var = pc_gx_tev_get_variant();
    GLuint shader = var->prog;
    int prim = g_gx.current_primitive;
    /* Strips/fans would join across batches */
    int deferrable = (prim == GX_TRIANGLES || prim == GX_QUADS);

    /* Same GL state as the deferred run: absorb the verts, no GL work */
    if (g_gx.pending_verts > 0 && g_gx.dirty == 0 && deferrable &&
        prim == g_gx.pending_prim && shader == g_gx.current_shader) {
        g_gx.pending_verts = g_gx.current_vertex_idx;
        pc_profiler_add_time(PC_PROF_TIMER_GX_FLUSH, flush_start);
        return;
    }

    /* State is changing: draw the deferred run while GL state still matches it */
    pc_gx_draw_pending();

    if (shader && shader != g_gx.current_shader) {
        pc_gx_use_program_profiled(shader);
        PC_GL_CHECK("glUseProgram");
        g_gx.current_shader = shader;
        g_gx.uloc = var->uloc;
        /* Uniform values persist per program: re-upload only groups that
         * changed while another program was bound */
        g_gx.dirty |= pc_gx_variant_stale_groups(var);
    }

    glBindVertexArray(g_gx.vao);
    glBindBuffer(GL_ARRAY_BUFFER, g_gx.vbo);

    /* Upload only dirty state groups */
    if (shader) {
        Uint64 uniform_start = pc_profiler_begin_timer();
        GLint loc;
        unsigned int dirty = g_gx.dirty;
        pc_profiler_add_dirty_mask(dirty);
        #define UL(field) g_gx.uloc.field

        if (dirty & PC_GX_DIRTY_PROJECTION) {
            float rolling_radius = rolling_outdoor && pc_rolling_world_projection_matches() &&
                g_pc_rolling_world_strength > 0.0f ? 800.0f / g_pc_rolling_world_strength : 0.0f;
            static int rolling_reported;
            if (rolling_radius > 0.0f && !rolling_reported) {
                printf("[RollingWorld] Outdoor projection matched; radius=%.1f, player anchor=(%.1f,%.1f,%.1f)\n",
                    rolling_radius, rolling_anchor[0], rolling_anchor[1], rolling_anchor[2]);
                rolling_reported = 1;
            }
            loc = UL(projection);
            if (loc >= 0) glUniformMatrix4fv(loc, 1, GL_TRUE, (float*)g_gx.projection_mtx);
            loc = UL(rolling_radius);
            if (loc >= 0) glUniform1f(loc, rolling_radius);
            loc = UL(rolling_camera); if (loc >= 0) glUniform3fv(loc, 1, rolling_camera);
            loc = UL(rolling_anchor); if (loc >= 0) glUniform3fv(loc, 1, rolling_anchor);
            loc = UL(rolling_axis); if (loc >= 0) glUniform3fv(loc, 1, rolling_axis);
            loc = UL(rolling_view_rotation);
            if (loc >= 0) glUniformMatrix3fv(loc, 1, GL_TRUE, rolling_view_rotation);
        }

        if (dirty & PC_GX_DIRTY_LIGHTING) {
            loc = UL(water_phase); if (loc >= 0) glUniform2fv(loc, 1, water_phase);
            loc = UL(donor_water_frame); if (loc >= 0) glUniform1f(loc, donor_water_frame);
            loc = UL(donor_light_enabled); if (loc >= 0) glUniform1i(loc, donor_light_enabled);
            loc = UL(nl_char); if (loc >= 0) glUniform1i(loc, nl_char ? nl_char : (nl_cloth ? 3 : 0)); /* 3 = cloth */
            loc = UL(donor_ground_direction); if (loc >= 0) glUniform3fv(loc, 1, donor_ground_direction);
            loc = UL(donor_ground_ambient); if (loc >= 0) glUniform3fv(loc, 1, g_pc_donor_global_ambient);
            loc = UL(donor_actor_direction); if (loc >= 0) glUniform3fv(loc, 1, g_pc_donor_actor_direction);
            loc = UL(donor_water_base); if (loc >= 0) glUniform3fv(loc, 1, donor_water_base);
            loc = UL(donor_water_buffer); if (loc >= 0) glUniform3fv(loc, 1, donor_water_buffer);
            loc = UL(donor_water_bank); if (loc >= 0) glUniform3fv(loc, 1, donor_water_bank);
            loc = UL(donor_diffuse); if (loc >= 0) glUniform3fv(loc, 1, donor_diffuse);
            loc = UL(donor_specular); if (loc >= 0) glUniform3fv(loc, 1, donor_specular);
            loc = UL(donor_hemi_sky); if (loc >= 0) glUniform3fv(loc, 1, donor_hemi_sky);
            loc = UL(donor_hemi_ground); if (loc >= 0) glUniform3fv(loc, 1, donor_hemi_ground);
        }

        if (dirty & PC_GX_DIRTY_MODELVIEW) {
            loc = UL(modelview);
            if (loc >= 0) {
                float mv44[16];
                const float* src = (const float*)g_gx.pos_mtx[g_gx.current_mtx];
                mv44[ 0] = src[0]; mv44[ 1] = src[1]; mv44[ 2] = src[2]; mv44[ 3] = src[3];
                mv44[ 4] = src[4]; mv44[ 5] = src[5]; mv44[ 6] = src[6]; mv44[ 7] = src[7];
                mv44[ 8] = src[8]; mv44[ 9] = src[9]; mv44[10] = src[10]; mv44[11] = src[11];
                mv44[12] = 0.0f;   mv44[13] = 0.0f;   mv44[14] = 0.0f;    mv44[15] = 1.0f;
                glUniformMatrix4fv(loc, 1, GL_TRUE, mv44);
            }
            loc = UL(normal_mtx);
            if (loc >= 0) glUniformMatrix3fv(loc, 1, GL_TRUE, (const float*)g_gx.nrm_mtx[g_gx.current_mtx]);
        }

        if (dirty & PC_GX_DIRTY_TEV_COLORS) {
            loc = UL(tev_prev); if (loc >= 0) glUniform4fv(loc, 1, g_gx.tev_colors[0]);
            loc = UL(tev_reg0); if (loc >= 0) glUniform4fv(loc, 1, g_gx.tev_colors[1]);
            loc = UL(tev_reg1); if (loc >= 0) glUniform4fv(loc, 1, g_gx.tev_colors[2]);
            loc = UL(tev_reg2); if (loc >= 0) glUniform4fv(loc, 1, g_gx.tev_colors[3]);
        }

        if (dirty & PC_GX_DIRTY_TEV_STAGES) {
            loc = UL(num_tev_stages); if (loc >= 0) glUniform1i(loc, g_gx.num_tev_stages);
            {
                GLint color_in[PC_GX_MAX_TEV_STAGES][4];
                GLint alpha_in[PC_GX_MAX_TEV_STAGES][4];
                GLint color_op[PC_GX_MAX_TEV_STAGES];
                GLint alpha_op[PC_GX_MAX_TEV_STAGES];
                GLint bsc[PC_GX_MAX_TEV_STAGES][4];
                GLint out_cfg[PC_GX_MAX_TEV_STAGES][4];
                GLint swap[PC_GX_MAX_TEV_STAGES][2];
                GLint ksel[PC_GX_MAX_TEV_STAGES][3];
                GLint tc_src[PC_GX_MAX_TEV_STAGES];

                for (int s = 0; s < PC_GX_MAX_TEV_STAGES; s++) {
                    PCGXTevStage* ts = &g_gx.tev_stages[s];
                    color_in[s][0] = ts->color_a;
                    color_in[s][1] = ts->color_b;
                    color_in[s][2] = ts->color_c;
                    color_in[s][3] = ts->color_d;
                    alpha_in[s][0] = ts->alpha_a;
                    alpha_in[s][1] = ts->alpha_b;
                    alpha_in[s][2] = ts->alpha_c;
                    alpha_in[s][3] = ts->alpha_d;
                    color_op[s] = ts->color_op;
                    alpha_op[s] = ts->alpha_op;
                    bsc[s][0] = ts->color_bias;
                    bsc[s][1] = ts->color_scale;
                    bsc[s][2] = ts->alpha_bias;
                    bsc[s][3] = ts->alpha_scale;
                    out_cfg[s][0] = ts->color_clamp;
                    out_cfg[s][1] = ts->alpha_clamp;
                    out_cfg[s][2] = ts->color_out;
                    out_cfg[s][3] = ts->alpha_out;
                    swap[s][0] = ts->ras_swap;
                    swap[s][1] = ts->tex_swap;
                    ksel[s][0] = ts->k_color_sel;
                    ksel[s][1] = ts->k_alpha_sel;
                    ksel[s][2] = s;
                    if (s < g_gx.num_tev_stages) {
                        tc_src[s] = pc_gx_tc_src_normalize(ts->tex_coord, s);
                    } else {
                        tc_src[s] = 0;
                    }
                }

                loc = UL(tev_color_in[0]); if (loc >= 0) glUniform4iv(loc, PC_GX_MAX_TEV_STAGES, &color_in[0][0]);
                loc = UL(tev_alpha_in[0]); if (loc >= 0) glUniform4iv(loc, PC_GX_MAX_TEV_STAGES, &alpha_in[0][0]);
                loc = UL(tev_color_op[0]); if (loc >= 0) glUniform1iv(loc, PC_GX_MAX_TEV_STAGES, color_op);
                loc = UL(tev_alpha_op[0]); if (loc >= 0) glUniform1iv(loc, PC_GX_MAX_TEV_STAGES, alpha_op);
                loc = UL(tev_bsc[0]);      if (loc >= 0) glUniform4iv(loc, PC_GX_MAX_TEV_STAGES, &bsc[0][0]);
                loc = UL(tev_out[0]);      if (loc >= 0) glUniform4iv(loc, PC_GX_MAX_TEV_STAGES, &out_cfg[0][0]);
                loc = UL(tev_swap[0]);     if (loc >= 0) glUniform2iv(loc, PC_GX_MAX_TEV_STAGES, &swap[0][0]);
                loc = UL(tev_ksel);        if (loc >= 0) glUniform3iv(loc, PC_GX_MAX_TEV_STAGES, &ksel[0][0]);
                loc = UL(tev_tc_src[0]);   if (loc >= 0) glUniform1iv(loc, PC_GX_MAX_TEV_STAGES, tc_src);
            }
        }

        if (dirty & PC_GX_DIRTY_SWAP_TABLES) {
            loc = UL(swap_table);
            if (loc >= 0) {
                int sw[16];
                for (int t = 0; t < 4; t++) {
                    sw[t*4+0] = g_gx.tev_swap_table[t].r;
                    sw[t*4+1] = g_gx.tev_swap_table[t].g;
                    sw[t*4+2] = g_gx.tev_swap_table[t].b;
                    sw[t*4+3] = g_gx.tev_swap_table[t].a;
                }
                glUniform4iv(loc, 4, sw);
            }
        }

        if (dirty & PC_GX_DIRTY_KONST) {
            loc = UL(kcolor); if (loc >= 0) glUniform4fv(loc, 4, (const float*)g_gx.tev_k_colors);
        }

        if (dirty & PC_GX_DIRTY_ALPHA_CMP) {
            GLint ctrl[3] = { g_gx.alpha_comp0, g_gx.alpha_op, g_gx.alpha_comp1 };
            GLint refs[2] = { g_gx.alpha_ref0, g_gx.alpha_ref1 };
            loc = UL(alpha_ctrl); if (loc >= 0) glUniform3iv(loc, 1, ctrl);
            loc = UL(alpha_refs); if (loc >= 0) glUniform2iv(loc, 1, refs);
        }

        if (dirty & PC_GX_DIRTY_LIGHTING) {
            GLint lighting_cfg0[4] = {
                g_gx.chan_ctrl_enable[0],
                g_gx.chan_ctrl_mat_src[0],
                g_gx.chan_ctrl_amb_src[0],
                g_gx.num_chans
            };
            GLint lighting_cfg1[4] = {
                g_gx.chan_ctrl_enable[1],
                g_gx.chan_ctrl_mat_src[1],
                g_gx.chan_ctrl_light_mask[0],
                0
            };
            GLfloat chan_color[2][4];

            memcpy(chan_color[0], g_gx.chan_mat_color[0], sizeof(chan_color[0]));
            memcpy(chan_color[1], g_gx.chan_amb_color[0], sizeof(chan_color[1]));

            loc = UL(lighting_enabled); if (loc >= 0) glUniform4iv(loc, 1, lighting_cfg0);
            loc = UL(alpha_lighting_enabled); if (loc >= 0) glUniform4iv(loc, 1, lighting_cfg1);
            loc = UL(mat_color); if (loc >= 0) glUniform4fv(loc, 2, &chan_color[0][0]);
            {
                float lpos[8][3], lcol[8][4];
                for (int i = 0; i < 8; i++) {
                    memcpy(lpos[i], g_gx.lights[i].pos, sizeof(lpos[i]));
                    memcpy(lcol[i], g_gx.lights[i].color, sizeof(lcol[i]));
                }
                loc = UL(light_pos[0]);   if (loc >= 0) glUniform3fv(loc, 8, &lpos[0][0]);
                loc = UL(light_color[0]); if (loc >= 0) glUniform4fv(loc, 8, &lcol[0][0]);
            }
        }

        if (dirty & PC_GX_DIRTY_TEXGEN) {
            GLint texmtx_enable[2];
            GLint texgen_src[2];
            GLfloat texmtx_row0[2][4];
            GLfloat texmtx_row1[2][4];

            for (int tg = 0; tg < 2; tg++) {
                int slot = pc_tex_mtx_id_to_slot(g_gx.tex_gen_mtx[tg]);
                texmtx_enable[tg] = (slot >= 0 && slot < 10);
                texgen_src[tg] = g_gx.tex_gen_src[tg];
                memset(texmtx_row0[tg], 0, sizeof(texmtx_row0[tg]));
                memset(texmtx_row1[tg], 0, sizeof(texmtx_row1[tg]));
                texmtx_row0[tg][0] = 1.0f;
                texmtx_row1[tg][1] = 1.0f;
                if (texmtx_enable[tg]) {
                    const GLfloat* tm = (const GLfloat*)g_gx.tex_mtx[slot];
                    memcpy(texmtx_row0[tg], &tm[0], sizeof(texmtx_row0[tg]));
                    memcpy(texmtx_row1[tg], &tm[4], sizeof(texmtx_row1[tg]));
                }
            }

            loc = g_gx.uloc.texmtx_enable[0]; if (loc >= 0) glUniform1iv(loc, 2, texmtx_enable);
            loc = g_gx.uloc.texmtx_row0[0];   if (loc >= 0) glUniform4fv(loc, 2, &texmtx_row0[0][0]);
            loc = g_gx.uloc.texmtx_row1[0];   if (loc >= 0) glUniform4fv(loc, 2, &texmtx_row1[0][0]);
            loc = g_gx.uloc.texgen_src[0];    if (loc >= 0) glUniform1iv(loc, 2, texgen_src);
        }

        if (dirty & (PC_GX_DIRTY_TEXTURES | PC_GX_DIRTY_TEV_STAGES)) {
            int use_tex_stage[PC_GX_MAX_TEV_STAGES] = { 0 };
            GLuint tex_obj_stage[PC_GX_MAX_TEV_STAGES] = { 0 };
            for (int s = 0; s < PC_GX_MAX_TEV_STAGES; s++) {
                if (s < g_gx.num_tev_stages) {
                    int tex_map = g_gx.tev_stages[s].tex_map;
                    if (tex_map >= 0 && tex_map < 8)
                        tex_obj_stage[s] = g_gx.gl_textures[tex_map];
                }
                if (tex_obj_stage[s] != 0) {
                    use_tex_stage[s] = 1;
                    pc_gx_active_texture_cached(GL_TEXTURE0 + s);
                    pc_gx_bind_texture_profiled(GL_TEXTURE_2D, tex_obj_stage[s]);
                }
            }
            loc = UL(use_texture0); if (loc >= 0) glUniform1iv(loc, PC_GX_MAX_TEV_STAGES, use_tex_stage);
            {
                extern int pc_terrain_texture_kind(GLuint tex);
                int kinds[PC_GX_MAX_TEV_STAGES];
                for (int s=0; s<PC_GX_MAX_TEV_STAGES; s++) {
                    kinds[s]=pc_terrain_texture_kind(tex_obj_stage[s]);
                }
                loc = UL(terrain_kind); if (loc >= 0) glUniform1iv(loc, PC_GX_MAX_TEV_STAGES, kinds);
                extern int g_pc_terrain_normals;
                loc = UL(terrain_normals); if (loc >= 0) glUniform1i(loc, g_pc_terrain_normals);
            }
        }

        if ((dirty & (PC_GX_DIRTY_TEXTURES | PC_GX_DIRTY_TEV_STAGES)) && g_gx.uloc.donor_luts >= 0) {
            pc_gx_active_texture_cached(GL_TEXTURE7);
            pc_gx_bind_texture_profiled(GL_TEXTURE_2D, s_donor_lut_texture);
        }

        /* Indirect textures on units 3-6 */
        if (dirty & (PC_GX_DIRTY_INDIRECT | PC_GX_DIRTY_TEXTURES)) {
            for (int i = 0; i < g_gx.num_ind_stages && i < 4; i++) {
                int ind_tex_map = g_gx.ind_order[i].tex_map;
                if (ind_tex_map >= 0 && ind_tex_map < 8) {
                    GLuint ind_tex = g_gx.gl_textures[ind_tex_map];
                    if (ind_tex) {
                        pc_gx_active_texture_cached(GL_TEXTURE3 + i);
                        pc_gx_bind_texture_profiled(GL_TEXTURE_2D, ind_tex);
                    }
                }
            }
        }

        if (dirty & PC_GX_DIRTY_INDIRECT) {
            loc = UL(num_ind_stages); if (loc >= 0) glUniform1i(loc, g_gx.num_ind_stages);
            for (int i = 0; i < g_gx.num_ind_stages && i < 4; i++) {
                loc = UL(ind_scale[i]);
                if (loc >= 0) {
                    float s_scale = 1.0f / (float)(1 << g_gx.ind_order[i].scale_s);
                    float t_scale = 1.0f / (float)(1 << g_gx.ind_order[i].scale_t);
                    glUniform2f(loc, s_scale, t_scale);
                }
            }
            for (int i = 0; i < 3; i++) {
                float scale_val = ldexpf(1.0f, g_gx.ind_mtx_scale[i] + 17) / 1024.0f;
                float packed[6];
                for (int j = 0; j < 6; j++)
                    packed[j] = ((float*)g_gx.ind_mtx[i])[j] * scale_val;
                loc = UL(ind_mtx_r0[i]); if (loc >= 0) glUniform3f(loc, packed[0], packed[1], packed[2]);
                loc = UL(ind_mtx_r1[i]); if (loc >= 0) glUniform3f(loc, packed[3], packed[4], packed[5]);
            }
            for (int s = 0; s < g_gx.num_tev_stages && s < PC_GX_MAX_TEV_STAGES; s++) {
                PCGXTevStage* ts = &g_gx.tev_stages[s];
                loc = UL(tev_ind_cfg[s]);
                if (loc >= 0) glUniform4i(loc, ts->ind_stage, ts->ind_mtx, ts->ind_bias, ts->ind_alpha);
                loc = UL(tev_ind_wrap[s]);
                if (loc >= 0) glUniform3i(loc, ts->ind_wrap_s, ts->ind_wrap_t, ts->ind_add_prev);
            }
        }
        pc_gx_active_texture_cached(GL_TEXTURE0);

        if (dirty & PC_GX_DIRTY_FOG) {
            GLfloat fog_params[4] = {
                (GLfloat)g_gx.fog_type, g_gx.fog_start, g_gx.fog_end, 0.0f
            };
            loc = UL(fog_type);   if (loc >= 0) glUniform4fv(loc, 1, fog_params);
            loc = UL(fog_enable); if (loc >= 0) glUniform1i(loc, g_gx.fog_type != 0);
            loc = UL(fog_color);  if (loc >= 0) glUniform4fv(loc, 1, g_gx.fog_color);
        }

        #undef UL
        pc_profiler_add_time(PC_PROF_TIMER_UNIFORM_UPLOAD, uniform_start);

        /* Record what this program has now seen for stale tracking */
        {
            unsigned int groups = dirty & PC_GX_DIRTY_UNIFORM_GROUPS;
            for (int b = 0; groups; b++, groups >>= 1) {
                if (groups & 1) var->uploaded_seq[b] = g_gx.group_seq[b];
            }
        }
    }

    GLenum gl_prim;
    switch (g_gx.current_primitive) {
        case GX_QUADS:         gl_prim = GL_TRIANGLES; break;
        case GX_TRIANGLES:     gl_prim = GL_TRIANGLES; break;
        case GX_TRIANGLESTRIP: gl_prim = GL_TRIANGLE_STRIP; break;
        case GX_TRIANGLEFAN:   gl_prim = GL_TRIANGLE_FAN; break;
        case GX_LINES:         gl_prim = GL_LINES; break;
        case GX_LINESTRIP:     gl_prim = GL_LINE_STRIP; break;
        case GX_POINTS:        gl_prim = GL_POINTS; break;
        default:               gl_prim = GL_TRIANGLES; break;
    }

    Uint64 state_start = pc_profiler_begin_timer();

    if (g_gx.dirty & PC_GX_DIRTY_DEPTH) {
        pc_profiler_add_count_state_change();
        if (g_gx.z_compare_enable) {
            glEnable(GL_DEPTH_TEST);
            GLenum zfunc;
            switch (g_gx.z_compare_func) {
                case GX_NEVER:   zfunc = GL_NEVER; break;
                case GX_LESS:    zfunc = GL_LESS; break;
                case GX_EQUAL:   zfunc = GL_EQUAL; break;
                case GX_LEQUAL:  zfunc = GL_LEQUAL; break;
                case GX_GREATER: zfunc = GL_GREATER; break;
                case GX_NEQUAL:  zfunc = GL_NOTEQUAL; break;
                case GX_GEQUAL:  zfunc = GL_GEQUAL; break;
                case GX_ALWAYS:  zfunc = GL_ALWAYS; break;
                default:         zfunc = GL_LEQUAL; break;
            }
            glDepthFunc(zfunc);
        } else {
            glDisable(GL_DEPTH_TEST);
        }
        glDepthMask(g_gx.z_update_enable ? GL_TRUE : GL_FALSE);
    }

    if (g_gx.dirty & PC_GX_DIRTY_COLOR_MASK) {
        pc_profiler_add_count_state_change();
        glColorMask(
            g_gx.color_update_enable ? GL_TRUE : GL_FALSE,
            g_gx.color_update_enable ? GL_TRUE : GL_FALSE,
            g_gx.color_update_enable ? GL_TRUE : GL_FALSE,
            g_gx.alpha_update_enable ? GL_TRUE : GL_FALSE
        );
    }

    if (g_gx.dirty & PC_GX_DIRTY_CULL) {
        pc_profiler_add_count_state_change();
        switch (g_gx.cull_mode) {
            case GX_CULL_NONE:  glDisable(GL_CULL_FACE); break;
            case GX_CULL_FRONT: glEnable(GL_CULL_FACE); glCullFace(GL_FRONT); break;
            case GX_CULL_BACK:  glEnable(GL_CULL_FACE); glCullFace(GL_BACK); break;
            case GX_CULL_ALL:   glEnable(GL_CULL_FACE); glCullFace(GL_FRONT_AND_BACK); break;
        }
    }

    if (g_gx.dirty & PC_GX_DIRTY_BLEND) {
        pc_profiler_add_count_state_change();
        /* Equation is state-driven: no hidden post-draw reset, so an
         * early-out on unchanged blend state stays correct */
        glBlendEquation(g_gx.blend_mode == GX_BM_SUBTRACT ? GL_FUNC_REVERSE_SUBTRACT
                                                          : GL_FUNC_ADD);
        switch (g_gx.blend_mode) {
            case GX_BM_NONE:
                glDisable(GL_BLEND);
                break;
            case GX_BM_BLEND:
                glEnable(GL_BLEND);
                {
                    GLenum src, dst;
                    switch (g_gx.blend_src) {
                        case GX_BL_ZERO:        src = GL_ZERO; break;
                        case GX_BL_ONE:         src = GL_ONE; break;
                        case GX_BL_DSTCLR:      src = GL_DST_COLOR; break;
                        case GX_BL_INVDSTCLR:   src = GL_ONE_MINUS_DST_COLOR; break;
                        case GX_BL_SRCALPHA:    src = GL_SRC_ALPHA; break;
                        case GX_BL_INVSRCALPHA: src = GL_ONE_MINUS_SRC_ALPHA; break;
                        case GX_BL_DSTALPHA:    src = GL_DST_ALPHA; break;
                        case GX_BL_INVDSTALPHA: src = GL_ONE_MINUS_DST_ALPHA; break;
                        default:                src = GL_ONE; break;
                    }
                    switch (g_gx.blend_dst) {
                        case GX_BL_ZERO:        dst = GL_ZERO; break;
                        case GX_BL_ONE:         dst = GL_ONE; break;
                        case GX_BL_SRCCLR:      dst = GL_SRC_COLOR; break;
                        case GX_BL_INVSRCCLR:   dst = GL_ONE_MINUS_SRC_COLOR; break;
                        case GX_BL_SRCALPHA:    dst = GL_SRC_ALPHA; break;
                        case GX_BL_INVSRCALPHA: dst = GL_ONE_MINUS_SRC_ALPHA; break;
                        case GX_BL_DSTALPHA:    dst = GL_DST_ALPHA; break;
                        case GX_BL_INVDSTALPHA: dst = GL_ONE_MINUS_DST_ALPHA; break;
                        default:                dst = GL_ZERO; break;
                    }
                    /* DST_ALPHA→SRC_ALPHA: GC EFB alpha semantics differ from GL */
                    if (g_gx.blend_src == GX_BL_DSTALPHA && g_gx.blend_dst == GX_BL_INVDSTALPHA) {
                        src = GL_SRC_ALPHA;
                        dst = GL_ONE_MINUS_SRC_ALPHA;
                    }
                    glBlendFunc(src, dst);
                }
                break;
            case GX_BM_LOGIC:
                glDisable(GL_BLEND);
                break;
            case GX_BM_SUBTRACT:
                glEnable(GL_BLEND);
                glBlendFunc(GL_ONE, GL_ONE);
                break;
        }
    }
    pc_profiler_add_time(PC_PROF_TIMER_GL_STATE, state_start);

    pc_surface_curve_capture();
    g_gx.dirty = 0;

    if (deferrable) {
        /* Defer the draw: the next batch may merge into it */
        g_gx.pending_prim = prim;
        g_gx.pending_verts = count;
        pc_profiler_add_time(PC_PROF_TIMER_GX_FLUSH, flush_start);
        return;
    }

    Uint64 draw_start = pc_profiler_begin_timer();
    int surface_drawn=pc_surface_curve_draw(g_gx.vertex_buffer,count,prim);
    if(!surface_drawn) {
    pc_gx_buffer_data_profiled(GL_ARRAY_BUFFER, count * sizeof(PCGXVertex), g_gx.vertex_buffer, GL_STREAM_DRAW);
    if (prim == GX_QUADS) {
        int num_quads = count / 4;
        int num_indices = num_quads * 6;
        glDrawElements(GL_TRIANGLES, num_indices, GL_UNSIGNED_SHORT, 0);
        pc_profiler_add_count_draw(count, num_indices);
        PC_GL_CHECK("glDrawElements");
    } else {
        glDrawArrays(gl_prim, 0, count);
        pc_profiler_add_count_draw(count, 0);
        PC_GL_CHECK("glDrawArrays");
    }
    pc_gx_draw_call_count++;
    }
    pc_profiler_add_time(PC_PROF_TIMER_DRAW_SUBMIT, draw_start);

    g_gx.current_vertex_idx = 0;
    pc_profiler_add_time(PC_PROF_TIMER_GX_FLUSH, flush_start);
}

/* --- Vertex Descriptor / Format --- */
void GXSetVtxDesc(u32 attr, u32 type) {
    if (attr < PC_GX_MAX_ATTR) g_gx.vtx_desc[attr] = type;
}
void GXSetVtxDescv(const void* list) {
    const u32* p = (const u32*)list;
    while (p[0] != GX_VA_NULL) {
        GXSetVtxDesc(p[0], p[1]);
        p += 2;
    }
}
void GXClearVtxDesc(void) { memset(g_gx.vtx_desc, 0, sizeof(g_gx.vtx_desc)); }

void GXSetVtxAttrFmt(u32 vtxfmt, u32 attr, u32 cnt, u32 type, u8 frac) {
    (void)cnt; (void)type;
    if (vtxfmt < GX_MAX_VTXFMT) {
        if (attr >= GX_VA_TEX0 && attr <= GX_VA_TEX7) {
            int tc = (int)attr - GX_VA_TEX0;
            g_gx.vtx_fmt[vtxfmt].has_texcoord[tc] = 1;
            g_gx.vtx_fmt[vtxfmt].texcoord_frac[tc] = frac;
        }
    }
}

void GXSetArray(u32 attr, const void* data, u32 size, u8 stride) {
    if (attr < GX_VA_MAX_ATTR) {
        g_gx.array_base[attr] = data;
        g_gx.array_stride[attr] = stride;
    }
}

void GXInvalidateVtxCache(void) { }

/* --- Transforms --- */
#ifdef PC_ENHANCEMENTS
/* Raw row 0 of the last projection, and whether UI sub-viewports are already narrowed by the aspect factor. */
static float s_proj_row0_raw[4];
static int s_proj_raw_valid;
static float pc_gx_proj_x_scale(void) {
    if (g_pc_widescreen_stretch == 1 || !g_aspect_active) return 1.0f;
    if (g_pc_widescreen_stretch == 2) {
        /* a UI sub-viewport (inventory portrait) is already remapped to GC proportions by GXSetViewport; scaling the
         * projection as well squeezed the 3D picture twice */
        int is_full = (g_gx.viewport[0] < 1.0f && g_gx.viewport[1] < 1.0f &&
                       g_gx.viewport[2] > (float)(PC_GC_WIDTH - 1) && g_gx.viewport[3] > (float)(PC_GC_HEIGHT - 1));
        if (!is_full) return 1.0f;
    }
    return g_aspect_factor;
}
#endif
void GXSetProjection(const void* mtx, u32 type) {
    /* Stored matrix gets aspect-scaled below, so filter on a shadow of the
     * raw input plus everything that feeds the final matrix */
    static float last_in[12];
    static int last_type = -1;
    int same = 0;
#ifdef PC_ENHANCEMENTS
    static int last_stretch = -1, last_aspect_active = -1;
    static float last_aspect_factor;
#endif

    pc_gx_flush_if_begin_complete();
    same = (int)type == last_type && memcmp(last_in, mtx, sizeof(last_in)) == 0;
#ifdef PC_ENHANCEMENTS
    same = same && g_pc_widescreen_stretch == last_stretch &&
           g_aspect_active == last_aspect_active &&
           g_aspect_factor == last_aspect_factor;
    last_stretch = g_pc_widescreen_stretch;
    last_aspect_active = g_aspect_active;
    last_aspect_factor = g_aspect_factor;
#endif
    if (same) return;
    memcpy(last_in, mtx, sizeof(last_in));
    last_type = (int)type;

    DIRTY(PC_GX_DIRTY_PROJECTION);
    g_gx.projection_type = type;
    memcpy(g_gx.projection_mtx, mtx, sizeof(float) * 12);
    /* GX only stores 3 rows — 4th row is implicit based on projection type */
    if (type == GX_PERSPECTIVE) {
        g_gx.projection_mtx[3][0] = 0.0f;
        g_gx.projection_mtx[3][1] = 0.0f;
        g_gx.projection_mtx[3][2] = -1.0f;
        g_gx.projection_mtx[3][3] = 0.0f;
    } else { /* GX_ORTHOGRAPHIC */
        g_gx.projection_mtx[3][0] = 0.0f;
        g_gx.projection_mtx[3][1] = 0.0f;
        g_gx.projection_mtx[3][2] = 0.0f;
        g_gx.projection_mtx[3][3] = 1.0f;
    }

#ifdef PC_ENHANCEMENTS
    /* Mode 2 ends a stretched background pass. Restore world correction too;
     * the same pass continues with perspective terrain/actors before the UI. */
    for (int col=0;col<4;col++) s_proj_row0_raw[col] = g_gx.projection_mtx[0][col];
    s_proj_raw_valid = 1;
    {
        /* Scale clip X including orthographic translation so UI stays centered. */
        float k = pc_gx_proj_x_scale();
        if (k != 1.0f) {
            for (int col=0;col<4;col++) g_gx.projection_mtx[0][col] *= k;
        }
    }
#endif
}

void GXLoadPosMtxImm(const void* mtx, u32 id) {
    pc_gx_flush_if_begin_complete();
    int slot = id / 3;
    if (slot >= 10) return;
    if (memcmp(g_gx.pos_mtx[slot], mtx, sizeof(float) * 12) == 0) return;
    DIRTY(PC_GX_DIRTY_MODELVIEW);
    memcpy(g_gx.pos_mtx[slot], mtx, sizeof(float) * 12);
}

void GXLoadNrmMtxImm(const void* mtx, u32 id) {
    pc_gx_flush_if_begin_complete();
    int slot = id / 3;
    if (slot >= 10) return;

    /* Extract upper-left 3x3 from 3x4 row-major Mtx (stride 4, not contiguous) */
    const float* src = (const float*)mtx;
    if (g_gx.nrm_mtx[slot][0][0] == src[0] && g_gx.nrm_mtx[slot][0][1] == src[1] &&
        g_gx.nrm_mtx[slot][0][2] == src[2] && g_gx.nrm_mtx[slot][1][0] == src[4] &&
        g_gx.nrm_mtx[slot][1][1] == src[5] && g_gx.nrm_mtx[slot][1][2] == src[6] &&
        g_gx.nrm_mtx[slot][2][0] == src[8] && g_gx.nrm_mtx[slot][2][1] == src[9] &&
        g_gx.nrm_mtx[slot][2][2] == src[10]) {
        return;
    }

    DIRTY(PC_GX_DIRTY_MODELVIEW);
    g_gx.nrm_mtx[slot][0][0] = src[0]; g_gx.nrm_mtx[slot][0][1] = src[1]; g_gx.nrm_mtx[slot][0][2] = src[2];
    g_gx.nrm_mtx[slot][1][0] = src[4]; g_gx.nrm_mtx[slot][1][1] = src[5]; g_gx.nrm_mtx[slot][1][2] = src[6];
    g_gx.nrm_mtx[slot][2][0] = src[8]; g_gx.nrm_mtx[slot][2][1] = src[9]; g_gx.nrm_mtx[slot][2][2] = src[10];
}

void GXLoadTexMtxImm(const void* mtx, u32 id, u32 type) {
    pc_gx_flush_if_begin_complete();
    int slot = pc_tex_mtx_id_to_slot((int)id);
    if (slot < 0 || slot >= 10) return;
    if (memcmp(g_gx.tex_mtx[slot], mtx, sizeof(float) * 12) == 0) return;
    DIRTY(PC_GX_DIRTY_TEXGEN);
    memcpy(g_gx.tex_mtx[slot], mtx, sizeof(float) * 12);
}

void GXSetCurrentMtx(u32 id) {
    pc_gx_flush_if_begin_complete();
    u32 slot = id / 3;
    if (slot >= 10 || g_gx.current_mtx == (int)slot) return;
    DIRTY(PC_GX_DIRTY_MODELVIEW);
    g_gx.current_mtx = slot;
}

/* Last GL viewport/scissor actually applied. J2D setPort re-sends both every
 * frame with unchanged values; comparing applied GL state (which folds in
 * window size and aspect mode) lets those calls skip the batch drain.
 * Invalidated wherever raw GL calls bypass the setters. */
static struct { int valid, x, y, w, h; double n, f; } s_gl_viewport;
static struct { int valid, x, y, w, h; } s_gl_scissor;

void pc_gx_viewport_state_invalidate(void) {
    s_gl_viewport.valid = 0;
    s_gl_scissor.valid = 0;
}

void GXSetViewport(f32 left, f32 top, f32 wd, f32 ht, f32 nearz, f32 farz) {
    int gl_x, gl_y, gl_w, gl_h;

    g_gx.viewport[0] = left;
    g_gx.viewport[1] = top;
    g_gx.viewport[2] = wd;
    g_gx.viewport[3] = ht;
    g_gx.viewport[4] = nearz;
    g_gx.viewport[5] = farz;
#ifdef PC_ENHANCEMENTS
    if (s_proj_raw_valid && g_pc_widescreen_stretch == 2 && g_aspect_active) {
        /* the projection's aspect scale depends on whether this viewport is a UI sub-viewport */
        float k = pc_gx_proj_x_scale();
        if (g_gx.projection_mtx[0][0] != s_proj_row0_raw[0]*k || g_gx.projection_mtx[0][2] != s_proj_row0_raw[2]*k) {
            pc_gx_draw_pending();
            for (int col=0;col<4;col++) g_gx.projection_mtx[0][col] = s_proj_row0_raw[col]*k;
            DIRTY(PC_GX_DIRTY_PROJECTION);
        }
    }
#endif
#ifdef PC_ENHANCEMENTS
    {
        float sx = (float)g_pc_window_w / (float)PC_GC_WIDTH;
        float sy = (float)g_pc_window_h / (float)PC_GC_HEIGHT;
        float adj_left = left;
        float adj_wd = wd;

        /* UI mode: remap sub-viewports to match aspect-corrected content */
        if (g_pc_widescreen_stretch == 2 && g_aspect_active) {
            int is_full = (left < 1.0f && top < 1.0f &&
                           wd > (float)(PC_GC_WIDTH - 1) &&
                           ht > (float)(PC_GC_HEIGHT - 1));
            if (!is_full) {
                adj_left = g_aspect_offset + left * g_aspect_factor;
                adj_wd = wd * g_aspect_factor;
            }
        }

        gl_x = (int)(adj_left * sx);
        gl_w = (int)(adj_wd * sx);
        gl_h = (int)(ht * sy);
        gl_y = g_pc_window_h - (int)(top * sy) - gl_h;
    }
#else
    /* GX is Y-down, GL is Y-up */
    gl_x = (int)left;
    gl_w = (int)wd;
    gl_h = (int)ht;
    gl_y = PC_GC_HEIGHT - (int)top - gl_h;
#endif

    if (s_gl_viewport.valid && gl_x == s_gl_viewport.x && gl_y == s_gl_viewport.y &&
        gl_w == s_gl_viewport.w && gl_h == s_gl_viewport.h &&
        (double)nearz == s_gl_viewport.n && (double)farz == s_gl_viewport.f)
        return;

    pc_gx_draw_pending(); /* glViewport is not dirty-tracked */
    glViewport(gl_x, gl_y, gl_w, gl_h);
    glDepthRange((double)nearz, (double)farz);
    s_gl_viewport.valid = 1;
    s_gl_viewport.x = gl_x;
    s_gl_viewport.y = gl_y;
    s_gl_viewport.w = gl_w;
    s_gl_viewport.h = gl_h;
    s_gl_viewport.n = (double)nearz;
    s_gl_viewport.f = (double)farz;
}

void GXSetViewportJitter(f32 left, f32 top, f32 wd, f32 ht, f32 nearz, f32 farz, u32 field) {
    GXSetViewport(left, top, wd, ht, nearz, farz);
}

void GXSetScissor(u32 left, u32 top, u32 wd, u32 ht) {
    int gl_x, gl_y, gl_w, gl_h;

    g_gx.scissor[0] = left;
    g_gx.scissor[1] = top;
    g_gx.scissor[2] = wd;
    g_gx.scissor[3] = ht;
#ifdef PC_ENHANCEMENTS
    {
        float sx = (float)g_pc_window_w / (float)PC_GC_WIDTH;
        float sy = (float)g_pc_window_h / (float)PC_GC_HEIGHT;
        gl_x = (int)(left * sx);
        gl_w = (int)(wd * sx);
        gl_h = (int)(ht * sy);
        gl_y = g_pc_window_h - (int)(top * sy) - gl_h;
    }
#else
    /* GX is Y-down, GL is Y-up */
    gl_x = (int)left;
    gl_w = (int)wd;
    gl_h = (int)ht;
    gl_y = PC_GC_HEIGHT - (int)top - (int)ht;
#endif

    /* Cache validity implies GL_SCISSOR_TEST is enabled */
    if (s_gl_scissor.valid && gl_x == s_gl_scissor.x && gl_y == s_gl_scissor.y &&
        gl_w == s_gl_scissor.w && gl_h == s_gl_scissor.h)
        return;

    pc_gx_draw_pending(); /* glScissor is not dirty-tracked */
    glEnable(GL_SCISSOR_TEST);
    glScissor(gl_x, gl_y, gl_w, gl_h);
    s_gl_scissor.valid = 1;
    s_gl_scissor.x = gl_x;
    s_gl_scissor.y = gl_y;
    s_gl_scissor.w = gl_w;
    s_gl_scissor.h = gl_h;
}

void GXSetScissorBoxOffset(s32 x, s32 y) { (void)x; (void)y; }
void GXSetClipMode(u32 mode) { (void)mode; }

void GXGetProjectionv(f32* p) {
    if (p) memcpy(p, g_gx.projection_mtx, sizeof(float) * 16);
}

void GXGetVtxAttrFmt(u32 idx, u32 attr, u32* compCnt, u32* compType, u8* shift) {
    if (compCnt) *compCnt = 0;
    if (compType) *compType = 0;
    if (shift) *shift = 0;
}

/* --- TEV Configuration --- */
void GXSetNumTevStages(u8 nStages) {
    pc_gx_flush_if_begin_complete();
    if (g_gx.num_tev_stages == nStages) return;
    DIRTY(PC_GX_DIRTY_TEV_STAGES);
    g_gx.num_tev_stages = nStages;
}

void GXSetTevOp(u32 stage, u32 mode) {
    pc_gx_flush_if_begin_complete();
    if (stage >= 16) return;

    /* TEV formula: out = (d + ((1-c)*a + c*b) + bias) * scale */
    switch (mode) {
    case GX_MODULATE:
        GXSetTevColorIn(stage, GX_CC_ZERO, GX_CC_TEXC, GX_CC_RASC, GX_CC_ZERO);
        GXSetTevAlphaIn(stage, GX_CA_ZERO, GX_CA_TEXA, GX_CA_RASA, GX_CA_ZERO);
        break;
    case GX_DECAL:
        GXSetTevColorIn(stage, GX_CC_RASC, GX_CC_TEXC, GX_CC_TEXA, GX_CC_ZERO);
        GXSetTevAlphaIn(stage, GX_CA_ZERO, GX_CA_ZERO, GX_CA_ZERO, GX_CA_RASA);
        break;
    case GX_BLEND:
        GXSetTevColorIn(stage, GX_CC_ONE, GX_CC_RASC, GX_CC_TEXC, GX_CC_ZERO);
        GXSetTevAlphaIn(stage, GX_CA_ZERO, GX_CA_TEXA, GX_CA_RASA, GX_CA_ZERO);
        break;
    case GX_REPLACE:
        GXSetTevColorIn(stage, GX_CC_ZERO, GX_CC_ZERO, GX_CC_ZERO, GX_CC_TEXC);
        GXSetTevAlphaIn(stage, GX_CA_ZERO, GX_CA_ZERO, GX_CA_ZERO, GX_CA_TEXA);
        break;
    case GX_PASSCLR:
        GXSetTevColorIn(stage, GX_CC_ZERO, GX_CC_ZERO, GX_CC_ZERO, GX_CC_RASC);
        GXSetTevAlphaIn(stage, GX_CA_ZERO, GX_CA_ZERO, GX_CA_ZERO, GX_CA_RASA);
        break;
    default:
        return;
    }
    GXSetTevColorOp(stage, GX_TEV_ADD, GX_TB_ZERO, GX_CS_SCALE_1, GX_TRUE, GX_TEVPREV);
    GXSetTevAlphaOp(stage, GX_TEV_ADD, GX_TB_ZERO, GX_CS_SCALE_1, GX_TRUE, GX_TEVPREV);
}

void GXSetTevColorIn(u32 stage, u32 a, u32 b, u32 c, u32 d) {
    pc_gx_flush_if_begin_complete();
    if (stage < 16) {
        PCGXTevStage* ts = &g_gx.tev_stages[stage];
        if (ts->color_a == (int)a && ts->color_b == (int)b &&
            ts->color_c == (int)c && ts->color_d == (int)d) return;
        DIRTY(PC_GX_DIRTY_TEV_STAGES);
        ts->color_a = a;
        ts->color_b = b;
        ts->color_c = c;
        ts->color_d = d;
    }
}

void GXSetTevAlphaIn(u32 stage, u32 a, u32 b, u32 c, u32 d) {
    pc_gx_flush_if_begin_complete();
    if (stage < 16) {
        PCGXTevStage* ts = &g_gx.tev_stages[stage];
        if (ts->alpha_a == (int)a && ts->alpha_b == (int)b &&
            ts->alpha_c == (int)c && ts->alpha_d == (int)d) return;
        DIRTY(PC_GX_DIRTY_TEV_STAGES);
        ts->alpha_a = a;
        ts->alpha_b = b;
        ts->alpha_c = c;
        ts->alpha_d = d;
    }
}

void GXSetTevColorOp(u32 stage, u32 op, u32 bias, u32 scale, GXBool clamp, u32 out_reg) {
    pc_gx_flush_if_begin_complete();
    if (stage < 16) {
        PCGXTevStage* ts = &g_gx.tev_stages[stage];
        if (ts->color_op == (int)op && ts->color_bias == (int)bias &&
            ts->color_scale == (int)scale && ts->color_clamp == (int)clamp &&
            ts->color_out == (int)out_reg) return;
        DIRTY(PC_GX_DIRTY_TEV_STAGES);
        ts->color_op = op;
        ts->color_bias = bias;
        ts->color_scale = scale;
        ts->color_clamp = clamp;
        ts->color_out = out_reg;
    }
}

void GXSetTevAlphaOp(u32 stage, u32 op, u32 bias, u32 scale, GXBool clamp, u32 out_reg) {
    pc_gx_flush_if_begin_complete();
    if (stage < 16) {
        PCGXTevStage* ts = &g_gx.tev_stages[stage];
        if (ts->alpha_op == (int)op && ts->alpha_bias == (int)bias &&
            ts->alpha_scale == (int)scale && ts->alpha_clamp == (int)clamp &&
            ts->alpha_out == (int)out_reg) return;
        DIRTY(PC_GX_DIRTY_TEV_STAGES);
        ts->alpha_op = op;
        ts->alpha_bias = bias;
        ts->alpha_scale = scale;
        ts->alpha_clamp = clamp;
        ts->alpha_out = out_reg;
    }
}

void GXSetTevOrder(u32 stage, u32 coord, u32 map, u32 color) {
    pc_gx_flush_if_begin_complete();
    if (stage < 16) {
        PCGXTevStage* ts = &g_gx.tev_stages[stage];
        if (ts->tex_coord == (int)coord && ts->tex_map == (int)map &&
            ts->color_chan == (int)color) return;
        DIRTY(PC_GX_DIRTY_TEV_STAGES | PC_GX_DIRTY_TEXTURES);
        ts->tex_coord = coord;
        ts->tex_map = map;
        ts->color_chan = color;
    }
}

void GXSetTevColor(u32 id, u32 color_packed) {
    pc_gx_flush_if_begin_complete();
    /* TEVREG0 uses GXColor fields (byte unpack), others come from EmuColor.raw (shift unpack) */
    if (id < GX_MAX_TEVREG) {
        float c[4];
        if (id == GX_TEVREG0) {
            pc_unpack_gxcolor_f(color_packed, c);
        } else {
            pc_unpack_rgba8f(color_packed, c);
        }
        if (memcmp(g_gx.tev_colors[id], c, sizeof(c)) == 0) return;
        DIRTY(PC_GX_DIRTY_TEV_COLORS);
        memcpy(g_gx.tev_colors[id], c, sizeof(c));
    }
}

void GXSetTevColorS10(u32 id, s16 r, s16 g, s16 b, s16 a) {
    pc_gx_flush_if_begin_complete();
    if (id < GX_MAX_TEVREG) {
        float c[4] = { r / 255.0f, g / 255.0f, b / 255.0f, a / 255.0f };
        if (memcmp(g_gx.tev_colors[id], c, sizeof(c)) == 0) return;
        DIRTY(PC_GX_DIRTY_TEV_COLORS);
        memcpy(g_gx.tev_colors[id], c, sizeof(c));
    }
}

void GXSetTevKColor(u32 id, u32 color_packed) {
    pc_gx_flush_if_begin_complete();
    if (id < 4) {
        float c[4];
        pc_unpack_rgba8f(color_packed, c);
        if (memcmp(g_gx.tev_k_colors[id], c, sizeof(c)) == 0) return;
        DIRTY(PC_GX_DIRTY_KONST);
        memcpy(g_gx.tev_k_colors[id], c, sizeof(c));
    }
}

void GXSetTevKColorSel(u32 stage, u32 sel) {
    pc_gx_flush_if_begin_complete();
    if (stage < 16 && g_gx.tev_stages[stage].k_color_sel != (int)sel) {
        DIRTY(PC_GX_DIRTY_TEV_STAGES);
        g_gx.tev_stages[stage].k_color_sel = sel;
    }
}
void GXSetTevKAlphaSel(u32 stage, u32 sel) {
    pc_gx_flush_if_begin_complete();
    if (stage < 16 && g_gx.tev_stages[stage].k_alpha_sel != (int)sel) {
        DIRTY(PC_GX_DIRTY_TEV_STAGES);
        g_gx.tev_stages[stage].k_alpha_sel = sel;
    }
}

void GXSetTevSwapMode(u32 stage, u32 ras_sel, u32 tex_sel) {
    pc_gx_flush_if_begin_complete();
    if (stage < 16) {
        PCGXTevStage* ts = &g_gx.tev_stages[stage];
        if (ts->ras_swap == (int)ras_sel && ts->tex_swap == (int)tex_sel) return;
        DIRTY(PC_GX_DIRTY_TEV_STAGES);
        ts->ras_swap = ras_sel;
        ts->tex_swap = tex_sel;
    }
}

void GXSetTevSwapModeTable(u32 table, u32 red, u32 green, u32 blue, u32 alpha) {
    pc_gx_flush_if_begin_complete();
    if (table < 4) {
        PCGXTevSwapTable* t = &g_gx.tev_swap_table[table];
        if (t->r == (int)red && t->g == (int)green &&
            t->b == (int)blue && t->a == (int)alpha) return;
        DIRTY(PC_GX_DIRTY_SWAP_TABLES);
        t->r = red;
        t->g = green;
        t->b = blue;
        t->a = alpha;
    }
}

/* --- Alpha / Depth / Blend --- */
void GXSetAlphaCompare(u32 comp0, u8 ref0, u32 op, u32 comp1, u8 ref1) {
    pc_gx_flush_if_begin_complete();
    if (g_gx.alpha_comp0 == (int)comp0 && g_gx.alpha_ref0 == (int)ref0 &&
        g_gx.alpha_op == (int)op && g_gx.alpha_comp1 == (int)comp1 &&
        g_gx.alpha_ref1 == (int)ref1) return;
    DIRTY(PC_GX_DIRTY_ALPHA_CMP);
    g_gx.alpha_comp0 = comp0;
    g_gx.alpha_ref0 = ref0;
    g_gx.alpha_op = op;
    g_gx.alpha_comp1 = comp1;
    g_gx.alpha_ref1 = ref1;
}

void GXSetBlendMode(u32 type, u32 src, u32 dst, u32 logic_op) {
    pc_gx_flush_if_begin_complete();
    if (g_gx.blend_mode == (int)type && g_gx.blend_src == (int)src &&
        g_gx.blend_dst == (int)dst && g_gx.blend_logic_op == (int)logic_op) return;
    DIRTY(PC_GX_DIRTY_BLEND);
    g_gx.blend_mode = type;
    g_gx.blend_src = src;
    g_gx.blend_dst = dst;
    g_gx.blend_logic_op = logic_op;
}

void GXSetZMode(GXBool compare_enable, u32 func, GXBool update_enable) {
    pc_gx_flush_if_begin_complete();
    if (g_gx.z_compare_enable == (int)compare_enable &&
        g_gx.z_compare_func == (int)func &&
        g_gx.z_update_enable == (int)update_enable) return;
    DIRTY(PC_GX_DIRTY_DEPTH);
    g_gx.z_compare_enable = compare_enable;
    g_gx.z_compare_func = func;
    g_gx.z_update_enable = update_enable;
}

void GXSetColorUpdate(GXBool enable) {
    pc_gx_flush_if_begin_complete();
    if (g_gx.color_update_enable == (int)enable) return;
    DIRTY(PC_GX_DIRTY_COLOR_MASK);
    g_gx.color_update_enable = enable;
}
void GXSetAlphaUpdate(GXBool enable) {
    pc_gx_flush_if_begin_complete();
    if (g_gx.alpha_update_enable == (int)enable) return;
    DIRTY(PC_GX_DIRTY_COLOR_MASK);
    g_gx.alpha_update_enable = enable;
}
void GXSetZCompLoc(GXBool before_tex) { (void)before_tex; }
void GXSetDither(GXBool dither) { (void)dither; }
void GXSetDstAlpha(GXBool enable, u8 alpha) { (void)enable; (void)alpha; }
void GXSetFieldMask(GXBool odd, GXBool even) { (void)odd; (void)even; }
void GXSetFieldMode(GXBool field_mode, GXBool half_aspect) { (void)field_mode; (void)half_aspect; }
void GXSetPixelFmt(u32 pix_fmt, u32 z_fmt) { (void)pix_fmt; (void)z_fmt; }

void GXSetCullMode(u32 mode) {
    pc_gx_flush_if_begin_complete();
    if (g_pc_model_viewer_no_cull) mode = GX_CULL_NONE;
    if (g_gx.cull_mode == (int)mode) return;
    DIRTY(PC_GX_DIRTY_CULL);
    g_gx.cull_mode = mode;
}
void GXSetCoPlanar(GXBool enable) { (void)enable; }

/* --- Fog --- */
void GXSetFog(u32 type, f32 startz, f32 endz, f32 nearz, f32 farz, GXColor color) {
    pc_gx_flush_if_begin_complete();
    float c[4] = { color.r / 255.0f, color.g / 255.0f, color.b / 255.0f, color.a / 255.0f };
    if (g_gx.fog_type == (int)type && g_gx.fog_start == startz &&
        g_gx.fog_end == endz && g_gx.fog_near == nearz && g_gx.fog_far == farz &&
        memcmp(g_gx.fog_color, c, sizeof(c)) == 0) return;
    DIRTY(PC_GX_DIRTY_FOG);
    g_gx.fog_type = type;
    g_gx.fog_start = startz;
    g_gx.fog_end = endz;
    g_gx.fog_near = nearz;
    g_gx.fog_far = farz;
    memcpy(g_gx.fog_color, c, sizeof(c));
}

void GXInitFogAdjTable(void* table, u16 width, f32 projmtx[4][4]) {
    (void)table; (void)width; (void)projmtx;
}
void GXSetFogRangeAdj(GXBool enable, u16 center, void* table) {
    (void)enable; (void)center; (void)table;
}

/* --- Lighting --- */
static int pc_gx_chan_index(u32 chan) {
    switch (chan) {
        case GX_COLOR0:
        case GX_ALPHA0:
        case GX_COLOR0A0:
            return 0;
        case GX_COLOR1:
        case GX_ALPHA1:
        case GX_COLOR1A1:
            return 1;
        default:
            return -1;
    }
}

void GXSetNumChans(u8 nChans) {
    pc_gx_flush_if_begin_complete();
    if (g_gx.num_chans == nChans) return;
    DIRTY(PC_GX_DIRTY_LIGHTING);
    g_gx.num_chans = nChans;
}

static int pc_gx_chan_ctrl_same(int i, GXBool enable, u32 amb_src, u32 mat_src,
                                u32 light_mask, u32 diff_fn, u32 attn_fn) {
    return g_gx.chan_ctrl_enable[i] == (int)enable &&
           g_gx.chan_ctrl_amb_src[i] == (int)amb_src &&
           g_gx.chan_ctrl_mat_src[i] == (int)mat_src &&
           g_gx.chan_ctrl_light_mask[i] == (int)light_mask &&
           g_gx.chan_ctrl_diff_fn[i] == (int)diff_fn &&
           g_gx.chan_ctrl_attn_fn[i] == (int)attn_fn;
}

void GXSetChanCtrl(u32 chan, GXBool enable, u32 amb_src, u32 mat_src,
                   u32 light_mask, u32 diff_fn, u32 attn_fn) {
    pc_gx_flush_if_begin_complete();
    int idx = pc_gx_chan_index(chan);
    if (idx >= 0) {
        int is_combined = (chan >= GX_COLOR0A0);
        int is_alpha = (chan == GX_ALPHA0 || chan == GX_ALPHA1);
        int set_color = !is_alpha || is_combined;
        int set_alpha = is_alpha || is_combined;

        if ((!set_color || pc_gx_chan_ctrl_same(idx * 2, enable, amb_src, mat_src,
                                                light_mask, diff_fn, attn_fn)) &&
            (!set_alpha || pc_gx_chan_ctrl_same(idx * 2 + 1, enable, amb_src, mat_src,
                                                light_mask, diff_fn, attn_fn))) {
            return;
        }
        DIRTY(PC_GX_DIRTY_LIGHTING);
        if (set_color) {
            g_gx.chan_ctrl_enable[idx * 2] = enable;
            g_gx.chan_ctrl_amb_src[idx * 2] = amb_src;
            g_gx.chan_ctrl_mat_src[idx * 2] = mat_src;
            g_gx.chan_ctrl_light_mask[idx * 2] = light_mask;
            g_gx.chan_ctrl_diff_fn[idx * 2] = diff_fn;
            g_gx.chan_ctrl_attn_fn[idx * 2] = attn_fn;
        }
        if (set_alpha) {
            g_gx.chan_ctrl_enable[idx * 2 + 1] = enable;
            g_gx.chan_ctrl_amb_src[idx * 2 + 1] = amb_src;
            g_gx.chan_ctrl_mat_src[idx * 2 + 1] = mat_src;
            g_gx.chan_ctrl_light_mask[idx * 2 + 1] = light_mask;
            g_gx.chan_ctrl_diff_fn[idx * 2 + 1] = diff_fn;
            g_gx.chan_ctrl_attn_fn[idx * 2 + 1] = attn_fn;
        }
    }
}

void GXSetChanAmbColor(u32 chan, u32 color_packed) {
    pc_gx_flush_if_begin_complete();
    int idx = pc_gx_chan_index(chan);
    if (idx >= 0 && idx < 2) {
        float c[4];
        pc_unpack_gxcolor_f(color_packed, c);
        if (memcmp(g_gx.chan_amb_color[idx], c, sizeof(c)) == 0) return;
        DIRTY(PC_GX_DIRTY_LIGHTING);
        memcpy(g_gx.chan_amb_color[idx], c, sizeof(c));
    }
}

void GXSetChanMatColor(u32 chan, u32 color_packed) {
    pc_gx_flush_if_begin_complete();
    int idx = pc_gx_chan_index(chan);
    if (idx >= 0 && idx < 2) {
        float c[4];
        pc_unpack_gxcolor_f(color_packed, c);
        if (memcmp(g_gx.chan_mat_color[idx], c, sizeof(c)) == 0) return;
        DIRTY(PC_GX_DIRTY_LIGHTING);
        memcpy(g_gx.chan_mat_color[idx], c, sizeof(c));
    }
}

/* GXLightObj internal layout (from GXPriv.h) */
typedef struct {
    u32 padding[3];
    u32 color;
    f32 a0, a1, a2;
    f32 k0, k1, k2;
    f32 px, py, pz;
    f32 nx, ny, nz;
} PCGXLightObjInternal;

void GXInitLightSpot(void* lt, f32 cutoff, u32 spot_func) {
    PCGXLightObjInternal* l = (PCGXLightObjInternal*)lt;
    f32 a0, a1, a2, r, cr, d;

    if (cutoff <= 0.0f || cutoff > 90.0f)
        spot_func = GX_SP_OFF;

    r = PC_PIf * cutoff / 180.0f;
    cr = cosf(r);
    switch (spot_func) {
    case GX_SP_FLAT:
        a0 = -1000.0f * cr;
        a1 = 1000.0f;
        a2 = 0.0f;
        break;
    case GX_SP_COS:
        a0 = -cr / (1.0f - cr);
        a1 = 1.0f / (1.0f - cr);
        a2 = 0.0f;
        break;
    case GX_SP_COS2:
        a0 = 0.0f;
        a1 = -cr / (1.0f - cr);
        a2 = 1.0f / (1.0f - cr);
        break;
    case GX_SP_SHARP:
        d = (1.0f - cr) * (1.0f - cr);
        a0 = (cr * (cr - 2.0f)) / d;
        a1 = 2.0f / d;
        a2 = -1.0f / d;
        break;
    case GX_SP_RING1:
        d = (1.0f - cr) * (1.0f - cr);
        a0 = (-4.0f * cr) / d;
        a1 = (4.0f * (1.0f + cr)) / d;
        a2 = -4.0f / d;
        break;
    case GX_SP_RING2:
        d = (1.0f - cr) * (1.0f - cr);
        a0 = 1.0f - ((2.0f * cr * cr) / d);
        a1 = (4.0f * cr) / d;
        a2 = -2.0f / d;
        break;
    case GX_SP_OFF:
    default:
        a0 = 1.0f;
        a1 = 0.0f;
        a2 = 0.0f;
        break;
    }
    l->a0 = a0; l->a1 = a1; l->a2 = a2;
}
void GXInitLightDistAttn(void* lt, f32 ref_dist, f32 ref_bright, u32 dist_func) {
    PCGXLightObjInternal* l = (PCGXLightObjInternal*)lt;
    f32 k0, k1, k2;

    if (ref_dist < 0.0f)
        dist_func = GX_DA_OFF;
    if (ref_bright <= 0.0f || ref_bright >= 1.0f)
        dist_func = GX_DA_OFF;

    switch (dist_func) {
    case GX_DA_GENTLE:
        k0 = 1.0f;
        k1 = (1.0f - ref_bright) / (ref_bright * ref_dist);
        k2 = 0.0f;
        break;
    case GX_DA_MEDIUM:
        k0 = 1.0f;
        k1 = (0.5f * (1.0f - ref_bright)) / (ref_bright * ref_dist);
        k2 = (0.5f * (1.0f - ref_bright)) / (ref_bright * ref_dist * ref_dist);
        break;
    case GX_DA_STEEP:
        k0 = 1.0f;
        k1 = 0.0f;
        k2 = (1.0f - ref_bright) / (ref_bright * ref_dist * ref_dist);
        break;
    case GX_DA_OFF:
    default:
        k0 = 1.0f;
        k1 = 0.0f;
        k2 = 0.0f;
        break;
    }
    l->k0 = k0; l->k1 = k1; l->k2 = k2;
}
void GXInitLightPos(void* lt, f32 x, f32 y, f32 z) {
    PCGXLightObjInternal* l = (PCGXLightObjInternal*)lt;
    l->px = x; l->py = y; l->pz = z;
}
void GXInitLightDir(void* lt, f32 nx, f32 ny, f32 nz) {
    PCGXLightObjInternal* l = (PCGXLightObjInternal*)lt;
    l->nx = nx; l->ny = ny; l->nz = nz;
}
void GXInitLightColor(void* lt, u32 color) {
    PCGXLightObjInternal* l = (PCGXLightObjInternal*)lt;
    l->color = color;
}
void GXInitLightAttn(void* lt, f32 a0, f32 a1, f32 a2, f32 k0, f32 k1, f32 k2) {
    PCGXLightObjInternal* l = (PCGXLightObjInternal*)lt;
    l->a0 = a0; l->a1 = a1; l->a2 = a2;
    l->k0 = k0; l->k1 = k1; l->k2 = k2;
}
void GXInitLightAttnA(void* lt, f32 a0, f32 a1, f32 a2) {
    PCGXLightObjInternal* l = (PCGXLightObjInternal*)lt;
    l->a0 = a0; l->a1 = a1; l->a2 = a2;
}
void GXInitLightAttnK(void* lt, f32 k0, f32 k1, f32 k2) {
    PCGXLightObjInternal* l = (PCGXLightObjInternal*)lt;
    l->k0 = k0; l->k1 = k1; l->k2 = k2;
}
void GXLoadLightObjImm(void* lt, u32 light) {
    pc_gx_flush_if_begin_complete();
    PCGXLightObjInternal* l = (PCGXLightObjInternal*)lt;
    int slot = -1;
    for (int i = 0; i < 8; i++) {
        if (light == (1u << i)) { slot = i; break; }
    }
    if (slot < 0) return;

    float c[4];
    pc_unpack_gxcolor_f(l->color, c);
    if (g_gx.lights[slot].pos[0] == l->px && g_gx.lights[slot].pos[1] == l->py &&
        g_gx.lights[slot].pos[2] == l->pz && g_gx.lights[slot].dir[0] == l->nx &&
        g_gx.lights[slot].dir[1] == l->ny && g_gx.lights[slot].dir[2] == l->nz &&
        g_gx.lights[slot].a0 == l->a0 && g_gx.lights[slot].a1 == l->a1 &&
        g_gx.lights[slot].a2 == l->a2 && g_gx.lights[slot].k0 == l->k0 &&
        g_gx.lights[slot].k1 == l->k1 && g_gx.lights[slot].k2 == l->k2 &&
        memcmp(g_gx.lights[slot].color, c, sizeof(c)) == 0) {
        return;
    }
    DIRTY(PC_GX_DIRTY_LIGHTING);
    g_gx.lights[slot].pos[0] = l->px;
    g_gx.lights[slot].pos[1] = l->py;
    g_gx.lights[slot].pos[2] = l->pz;
    g_gx.lights[slot].dir[0] = l->nx;
    g_gx.lights[slot].dir[1] = l->ny;
    g_gx.lights[slot].dir[2] = l->nz;
    g_gx.lights[slot].a0 = l->a0;
    g_gx.lights[slot].a1 = l->a1;
    g_gx.lights[slot].a2 = l->a2;
    g_gx.lights[slot].k0 = l->k0;
    g_gx.lights[slot].k1 = l->k1;
    g_gx.lights[slot].k2 = l->k2;
    memcpy(g_gx.lights[slot].color, c, sizeof(c));
}
void GXGetLightPos(void* lt, f32* x, f32* y, f32* z) {
    PCGXLightObjInternal* l = (PCGXLightObjInternal*)lt;
    *x = l->px; *y = l->py; *z = l->pz;
}
void GXGetLightColor(void* lt, void* color) {
    PCGXLightObjInternal* l = (PCGXLightObjInternal*)lt;
    memcpy(color, &l->color, 4);
}

/* --- Texture Coordinate Generation --- */
void GXSetNumTexGens(u8 n) {
    pc_gx_flush_if_begin_complete();
    if (g_gx.num_tex_gens == n) return;
    DIRTY(PC_GX_DIRTY_TEXGEN);
    g_gx.num_tex_gens = n;
}
void GXSetTexCoordGen2(u32 dst, u32 func, u32 src, u32 mtx, GXBool normalize, u32 postmtx) {
    pc_gx_flush_if_begin_complete();
    if (dst < 8) {
        if (g_gx.tex_gen_type[dst] == (int)func &&
            g_gx.tex_gen_src[dst] == (int)src &&
            g_gx.tex_gen_mtx[dst] == (int)mtx) {
            return;
        }
        DIRTY(PC_GX_DIRTY_TEXGEN);
        g_gx.tex_gen_type[dst] = func;
        g_gx.tex_gen_src[dst] = src;
        g_gx.tex_gen_mtx[dst] = mtx;
    }
}
void GXSetLineWidth(u8 width, u32 texOffsets) { glLineWidth(width / 16.0f); }
void GXSetPointSize(u8 size, u32 texOffsets) { glPointSize(size / 16.0f); }
void GXEnableTexOffsets(u32 coord, GXBool line, GXBool point) {
    (void)coord; (void)line; (void)point;
}
void GXSetTexCoordScaleManually(u32 coord, GXBool enable, u16 ss, u16 ts) {
    (void)coord; (void)enable; (void)ss; (void)ts;
}
void GXSetTexCoordBias(u32 coord, u8 s, u8 t) { (void)coord; (void)s; (void)t; }

/* --- Framebuffer / Copy --- */
void GXSetCopyClear(GXColor clear_clr, u32 clear_z) {
    g_gx.clear_color[0] = clear_clr.r / 255.0f;
    g_gx.clear_color[1] = clear_clr.g / 255.0f;
    g_gx.clear_color[2] = clear_clr.b / 255.0f;
    g_gx.clear_color[3] = clear_clr.a / 255.0f;
    g_gx.clear_depth = clear_z / (float)0x00FFFFFF;
}

void GXCopyDisp(void* dest, GXBool clear) {
    /* On PC we render to the back buffer directly; swap happens in VIWaitForRetrace.
     * Just flush pending geometry — do NOT swap or clear here. */
    pc_gx_commit_pending_and_flush();
    pc_gx_draw_pending();
    (void)dest;
    (void)clear;
}

void GXSetDispCopyGamma(u32 gamma) { (void)gamma; }
void GXSetDispCopySrc(u16 left, u16 top, u16 wd, u16 ht) {
    g_gx.copy_src[0] = left; g_gx.copy_src[1] = top;
    g_gx.copy_src[2] = wd; g_gx.copy_src[3] = ht;
}
void GXSetDispCopyDst(u16 wd, u16 ht) { g_gx.copy_dst[0] = wd; g_gx.copy_dst[1] = ht; }
f32 GXGetYScaleFactor(u16 efbHeight, u16 xfbHeight) {
    return (f32)xfbHeight / (f32)efbHeight;
}
u32 GXSetDispCopyYScale(f32 vscale) { return (u32)(vscale * 256.0f); }
u16 GXGetNumXfbLines(u16 efbHeight, f32 yScale) { return (u16)(efbHeight * yScale); }
void GXSetCopyFilter(GXBool aa, const void* pattern, GXBool vf, const void* vfilter) {
    if (g_pc_gx_dl.active) {
        u32 op = PCGX_DL_OP_COPY_FILTER;
        pc_gx_dl_write(&op, sizeof(op));
        return;
    }
    (void)aa; (void)pattern; (void)vf; (void)vfilter;
}
void GXAdjustForOverscan(void* rmin, void* rmout, u16 hor, u16 ver) {
    memcpy(rmout, rmin, sizeof(u32) * 16);
}

static void pc_gx_copy_tex_execute_impl(void* dest, GXBool clear) {
    pc_gx_commit_pending_and_flush();
    pc_gx_draw_pending(); /* everything must hit the framebuffer before glReadPixels */

    if (!dest) return;

    int out_wd = g_gx.tex_copy_src[2];
    int out_ht = g_gx.tex_copy_src[3];
    if (out_wd <= 0 || out_ht <= 0) return;
    if (out_wd > 4096 || out_ht > 4096) return;

#ifdef PC_ENHANCEMENTS
    /* Scale readback coordinates from GC coords to window resolution */
    float sx = (float)g_pc_window_w / (float)PC_GC_WIDTH;
    float sy = (float)g_pc_window_h / (float)PC_GC_HEIGHT;
    int read_left = (int)(g_gx.tex_copy_src[0] * sx);
    int read_top  = (int)(g_gx.tex_copy_src[1] * sy);
    int read_wd   = (int)(out_wd * sx);
    int read_ht   = (int)(out_ht * sy);
#else
    int read_left = g_gx.tex_copy_src[0];
    int read_top  = g_gx.tex_copy_src[1];
    int read_wd   = out_wd;
    int read_ht   = out_ht;
#endif

    if (read_left < 0) { read_wd += read_left; read_left = 0; }
    if (read_top < 0)  { read_ht += read_top;  read_top = 0; }
    if (read_left + read_wd > g_pc_window_w) read_wd = g_pc_window_w - read_left;
    if (read_top + read_ht > g_pc_window_h)  read_ht = g_pc_window_h - read_top;
    if (read_wd <= 0 || read_ht <= 0) return;

    int gl_y = g_pc_window_h - (read_top + read_ht);
    if (gl_y < 0) return;

    size_t rgba_size = (size_t)read_wd * (size_t)read_ht * 4;
    u8* rgba = (u8*)malloc(rgba_size);
    if (!rgba) return;

    glPixelStorei(GL_PACK_ALIGNMENT, 1);
    glReadPixels(read_left, gl_y, read_wd, read_ht, GL_RGBA, GL_UNSIGNED_BYTE, rgba);

#ifdef PC_ENHANCEMENTS
    /* Store as full-res GL texture; GXLoadTexObj will substitute it for the RGB565 buffer */
    {
        /* Flip: glReadPixels is bottom-up, textures are top-down */
        int row_bytes = read_wd * 4;
        for (int y = 0; y < read_ht / 2; y++) {
            u8* top_row = &rgba[y * row_bytes];
            u8* bot_row = &rgba[(read_ht - 1 - y) * row_bytes];
            for (int b = 0; b < row_bytes; b++) {
                u8 tmp = top_row[b];
                top_row[b] = bot_row[b];
                bot_row[b] = tmp;
            }
        }

        GLuint efb_tex;
        glGenTextures(1, &efb_tex);
        glBindTexture(GL_TEXTURE_2D, efb_tex);
        pc_profiler_add_count_texture_bind();
        pc_gx_texture_bind_cache_invalidate();
        glPixelStorei(GL_UNPACK_ALIGNMENT, 1);
        glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA, read_wd, read_ht, 0,
                     GL_RGBA, GL_UNSIGNED_BYTE, rgba);
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR);
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR);
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE);
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE);
        pc_gx_efb_capture_store((u32)(uintptr_t)dest, efb_tex);
        glBindTexture(GL_TEXTURE_2D, 0);
        pc_profiler_add_count_texture_bind();
        pc_gx_texture_bind_cache_invalidate();
        /* Unit 0 binding was clobbered; force rebind at next flush */
        DIRTY(PC_GX_DIRTY_TEXTURES);
    }
#else
    if (g_gx.tex_copy_fmt == 0x4) {
        u8* out = (u8*)dest;
        int bw = (out_wd + 3) / 4;
        int bh = (out_ht + 3) / 4;

        for (int by = 0; by < bh; by++) {
            for (int bx = 0; bx < bw; bx++) {
                for (int y = 0; y < 4; y++) {
                    for (int x = 0; x < 4; x++) {
                        int px = bx * 4 + x;
                        int py = by * 4 + y;
                        u16 rgb565 = 0;

                        if (px < out_wd && py < out_ht) {
                            int src_x = px * read_wd / out_wd;
                            int src_y = py * read_ht / out_ht;
                            src_y = read_ht - 1 - src_y;
                            const u8* p = &rgba[(src_y * read_wd + src_x) * 4];
                            rgb565 = (u16)(((p[0] >> 3) << 11) | ((p[1] >> 2) << 5) | (p[2] >> 3));
                        }

                        out[0] = (u8)((rgb565 >> 8) & 0xFF);
                        out[1] = (u8)(rgb565 & 0xFF);
                        out += 2;
                    }
                }
            }
        }
    }
#endif

    free(rgba);
    (void)clear;
}

/* Times the synchronous glReadPixels stall (called via GXCopyDisp and DL replay) */
static void pc_gx_copy_tex_execute(void* dest, GXBool clear) {
    Uint64 prof_start = pc_profiler_begin_timer();
    pc_gx_copy_tex_execute_impl(dest, clear);
    pc_profiler_add_time(PC_PROF_TIMER_EFB_COPY, prof_start);
}

void GXSetTexCopySrc(u16 left, u16 top, u16 wd, u16 ht) {
    if (g_pc_gx_dl.active) {
        u32 pkt[5] = { PCGX_DL_OP_TEXCOPY_SRC, left, top, wd, ht };
        pc_gx_dl_write(pkt, sizeof(pkt));
        return;
    }
    g_gx.tex_copy_src[0] = left;
    g_gx.tex_copy_src[1] = top;
    g_gx.tex_copy_src[2] = wd;
    g_gx.tex_copy_src[3] = ht;
}
void GXSetTexCopyDst(u16 wd, u16 ht, u32 fmt, GXBool mipmap) {
    if (g_pc_gx_dl.active) {
        u32 pkt[5] = { PCGX_DL_OP_TEXCOPY_DST, wd, ht, fmt, mipmap ? 1u : 0u };
        pc_gx_dl_write(pkt, sizeof(pkt));
        return;
    }
    g_gx.tex_copy_dst[0] = wd;
    g_gx.tex_copy_dst[1] = ht;
    g_gx.tex_copy_fmt = fmt;
    g_gx.tex_copy_mipmap = mipmap ? 1 : 0;
}
void GXCopyTex(void* dest, GXBool clear) {
    if (g_pc_gx_dl.active) {
        u32 op = PCGX_DL_OP_COPY_TEX;
        u64 dest64 = (u64)(uintptr_t)dest;
        u32 clear_u32 = clear ? 1u : 0u;
        pc_gx_dl_write(&op, sizeof(op));
        pc_gx_dl_write(&dest64, sizeof(dest64));
        pc_gx_dl_write(&clear_u32, sizeof(clear_u32));
        return;
    }

    pc_gx_copy_tex_execute(dest, clear);
}
void GXSetCopyClamp(u32 clamp) { (void)clamp; }

/* --- GX Init / Management --- */
void* GXInit(void* base, u32 size) {
    (void)base; (void)size;
    return base;
}

void GXSetMisc(u32 token, u32 val) { (void)token; (void)val; }
void GXFlush(void) { pc_gx_draw_pending(); glFlush(); }
void GXResetWriteGatherPipe(void) {}
void GXAbortFrame(void) {}
void GXSetDrawSync(u16 token) { (void)token; }
u16  GXReadDrawSync(void) { return 0; }
void GXSetDrawDone(void) {}
void GXWaitDrawDone(void) {}
void GXDrawDone(void) {}
void GXPixModeSync(void) {}
void GXTexModeSync(void) {}

void* GXSetDrawSyncCallback(void* cb) { return NULL; }
void* GXSetDrawDoneCallback(void* cb) { return NULL; }

/* --- FIFO --- */
typedef struct { u8 pad[128]; } GXFifoObj;
void GXInitFifoBase(GXFifoObj* fifo, void* base, u32 size) { (void)fifo; (void)base; (void)size; }
void GXInitFifoPtrs(GXFifoObj* fifo, void* rp, void* wp) { (void)fifo; (void)rp; (void)wp; }
void GXInitFifoLimits(GXFifoObj* fifo, u32 hi, u32 lo) { (void)fifo; (void)hi; (void)lo; }
void GXSetCPUFifo(GXFifoObj* fifo) { (void)fifo; }
void GXSetGPFifo(GXFifoObj* fifo) { (void)fifo; }
void GXSaveCPUFifo(GXFifoObj* fifo) { (void)fifo; }
void GXSaveGPFifo(GXFifoObj* fifo) { (void)fifo; }
void GXGetGPStatus(GXBool* a, GXBool* b, GXBool* c, GXBool* d, GXBool* e) {
    if (a) *a = 0;
    if (b) *b = 0;
    if (c) *c = 1;
    if (d) *d = 1;
    if (e) *e = 0;
}
void GXGetFifoStatus(GXFifoObj* f, GXBool* a, GXBool* b, u32* c, GXBool* d, GXBool* e, GXBool* g) {
    if (a) *a = 0;
    if (b) *b = 0;
    if (c) *c = 0;
    if (d) *d = 0;
    if (e) *e = 0;
    if (g) *g = 0;
}
void GXGetFifoPtrs(GXFifoObj* f, void** rp, void** wp) { if (rp) *rp = NULL; if (wp) *wp = NULL; }
void* GXGetFifoBase(GXFifoObj* f) { return NULL; }
u32 GXGetFifoSize(GXFifoObj* f) { return 0; }
void GXGetFifoLimits(GXFifoObj* f, u32* hi, u32* lo) { if (hi) *hi = 0; if (lo) *lo = 0; }
void* GXSetBreakPtCallback(void* cb) { return NULL; }
void GXEnableBreakPt(void* bp) { (void)bp; }
void GXDisableBreakPt(void) {}
void* GXSetCurrentGXThread(void) { return NULL; }
void* GXGetCurrentGXThread(void) { return NULL; }
GXFifoObj* GXGetCPUFifo(void) { static GXFifoObj f; return &f; }
GXFifoObj* GXGetGPFifo(void) { static GXFifoObj f; return &f; }
u32 GXGetOverflowCount(void) { return 0; }
u32 GXResetOverflowCount(void) { return 0; }
volatile void* GXRedirectWriteGatherPipe(void* ptr) { return ptr; }
void GXRestoreWriteGatherPipe(void) {}
int IsWriteGatherBufferEmpty(void) { return 1; }

/* --- Display List --- */
void GXBeginDisplayList(void* list, u32 size) {
    g_pc_gx_dl.active = 1;
    g_pc_gx_dl.buf = (u8*)list;
    g_pc_gx_dl.size = size;
    g_pc_gx_dl.off = 0;
    g_pc_gx_dl.overflow = 0;
}
u32 GXEndDisplayList(void) {
    u32 nbytes = 0;
    if (g_pc_gx_dl.active && !g_pc_gx_dl.overflow) {
        nbytes = g_pc_gx_dl.off;
    }
    g_pc_gx_dl.active = 0;
    g_pc_gx_dl.buf = NULL;
    g_pc_gx_dl.size = 0;
    g_pc_gx_dl.off = 0;
    g_pc_gx_dl.overflow = 0;
    return nbytes;
}
void GXCallDisplayList(void* list, u32 nbytes) {
    if (!list || nbytes == 0) return;

    Uint64 prof_start = pc_profiler_begin_timer();
#define PC_GX_DL_RETURN() do { pc_profiler_add_time(PC_PROF_TIMER_DISPLAY_LIST, prof_start); return; } while (0)

    const u8* p = (const u8*)list;
    u32 off = 0;

    while (off + sizeof(u32) <= nbytes) {
        u32 op = 0;
        memcpy(&op, p + off, sizeof(op));
        off += sizeof(op);

        switch (op) {
            case PCGX_DL_OP_TEXCOPY_SRC: {
                u32 v[4];
                if (off + sizeof(v) > nbytes) PC_GX_DL_RETURN();
                memcpy(v, p + off, sizeof(v));
                off += sizeof(v);
                GXSetTexCopySrc((u16)v[0], (u16)v[1], (u16)v[2], (u16)v[3]);
                break;
            }
            case PCGX_DL_OP_TEXCOPY_DST: {
                u32 v[4];
                if (off + sizeof(v) > nbytes) PC_GX_DL_RETURN();
                memcpy(v, p + off, sizeof(v));
                off += sizeof(v);
                GXSetTexCopyDst((u16)v[0], (u16)v[1], v[2], (GXBool)(v[3] ? 1 : 0));
                break;
            }
            case PCGX_DL_OP_COPY_FILTER:
                break;
            case PCGX_DL_OP_COPY_TEX: {
                u64 dest64 = 0;
                u32 clear = 0;
                if (off + sizeof(dest64) + sizeof(clear) > nbytes) PC_GX_DL_RETURN();
                memcpy(&dest64, p + off, sizeof(dest64));
                off += sizeof(dest64);
                memcpy(&clear, p + off, sizeof(clear));
                off += sizeof(clear);
                pc_gx_copy_tex_execute((void*)(uintptr_t)dest64, (GXBool)(clear ? 1 : 0));
                break;
            }
            default:
                PC_GX_DL_RETURN();
        }
    }

    pc_profiler_add_time(PC_PROF_TIMER_DISPLAY_LIST, prof_start);
#undef PC_GX_DL_RETURN
}

/* --- Indirect Texture --- */
void GXSetTevIndirect(u32 stage, u32 ind_stage, u32 fmt, u32 bias_sel,
                      u32 mtx_sel, u32 wrap_s, u32 wrap_t, GXBool add_prev,
                      GXBool ind_lod, u32 alpha_sel);

void GXSetTevDirect(u32 stage) {
    GXSetTevIndirect(stage, 0/*GX_INDTEXSTAGE0*/, 0/*GX_ITF_8*/, 0/*GX_ITB_NONE*/,
                     0/*GX_ITM_OFF*/, 0/*GX_ITW_OFF*/, 0/*GX_ITW_OFF*/, 0, 0, 0/*GX_ITBA_OFF*/);
}
void GXSetNumIndStages(u8 n) { DIRTY(PC_GX_DIRTY_INDIRECT); g_gx.num_ind_stages = n; }

void GXSetIndTexMtx(u32 mtx_sel, const void* offset, s8 scale) {
    DIRTY(PC_GX_DIRTY_INDIRECT);
    int id;
    switch (mtx_sel) {
        case 1: case 2: case 3:   id = mtx_sel - 1; break;
        case 5: case 6: case 7:   id = mtx_sel - 5; break;
        case 9: case 10: case 11: id = mtx_sel - 9; break;
        default: return;
    }
    if (id < 0 || id >= 3) return;
    const float* mtx = (const float*)offset;
    g_gx.ind_mtx[id][0][0] = mtx[0];
    g_gx.ind_mtx[id][0][1] = mtx[1];
    g_gx.ind_mtx[id][0][2] = mtx[2];
    g_gx.ind_mtx[id][1][0] = mtx[3];
    g_gx.ind_mtx[id][1][1] = mtx[4];
    g_gx.ind_mtx[id][1][2] = mtx[5];
    g_gx.ind_mtx_scale[id] = scale;
}

void GXSetIndTexOrder(u32 ind_stage, u32 tex_coord, u32 tex_map) {
    DIRTY(PC_GX_DIRTY_INDIRECT);
    if (ind_stage >= 4) return;
    g_gx.ind_order[ind_stage].tex_coord = tex_coord;
    g_gx.ind_order[ind_stage].tex_map = tex_map;
}

void GXSetTevIndirect(u32 stage, u32 ind_stage, u32 fmt, u32 bias_sel,
                      u32 mtx_sel, u32 wrap_s, u32 wrap_t, GXBool add_prev,
                      GXBool ind_lod, u32 alpha_sel) {
    DIRTY(PC_GX_DIRTY_INDIRECT);
    if (stage >= 16) return;
    PCGXTevStage* s = &g_gx.tev_stages[stage];
    s->ind_stage  = ind_stage;
    s->ind_format = fmt;
    s->ind_bias   = bias_sel;
    s->ind_mtx    = mtx_sel;
    s->ind_wrap_s = wrap_s;
    s->ind_wrap_t = wrap_t;
    s->ind_add_prev = add_prev;
    s->ind_lod    = ind_lod;
    s->ind_alpha  = alpha_sel;
}

void GXSetTevIndWarp(u32 stage, u32 ind_stage, GXBool signed_ofs, GXBool replace, u32 mtx_sel) {
    u32 wrap = replace ? 6/*GX_ITW_0*/ : 0/*GX_ITW_OFF*/;
    u32 bias = signed_ofs ? 7/*GX_ITB_STU*/ : 0/*GX_ITB_NONE*/;
    GXSetTevIndirect(stage, ind_stage, 0/*GX_ITF_8*/, bias, mtx_sel, wrap, wrap, 0, 0, 0);
}

void GXSetIndTexCoordScale(u32 ind_stage, u32 scale_s, u32 scale_t) {
    DIRTY(PC_GX_DIRTY_INDIRECT);
    if (ind_stage >= 4) return;
    g_gx.ind_order[ind_stage].scale_s = scale_s;
    g_gx.ind_order[ind_stage].scale_t = scale_t;
}

void __GXSetIndirectMask(u32 mask) { (void)mask; }

/* --- Z Texture --- */
void GXSetZTexture(u32 op, u32 fmt, u32 bias) { (void)op; (void)fmt; (void)bias; }

/* --- Draw Utility --- */
void GXDrawSphere(u8 numMajor, u8 numMinor) { (void)numMajor; (void)numMinor; }

/* --- Perf --- */
void GXReadXfRasMetric(u32* xf_wait_in, u32* xf_wait_out, u32* ras_busy, u32* clocks) {
    if (xf_wait_in) *xf_wait_in = 0;
    if (xf_wait_out) *xf_wait_out = 0;
    if (ras_busy) *ras_busy = 0;
    if (clocks) *clocks = 0;
}

/* --- Verify --- */
void GXSetVerifyLevel(u32 level) { (void)level; }
void* GXSetVerifyCallback(void* cb) { return NULL; }
