#version 330 core
layout(location = 0) in vec3 a_position;
layout(location = 1) in vec3 a_normal;
layout(location = 2) in vec4 a_color0;
layout(location = 3) in vec2 a_texcoord0;
uniform mat4 u_projection;
uniform mat4 u_modelview;
uniform mat3 u_normal_mtx;
uniform float u_rolling_radius;
uniform vec3 u_rolling_camera;
uniform vec3 u_rolling_anchor;
uniform vec3 u_rolling_axis;
uniform mat3 u_rolling_view_rotation;
uniform vec4 u_texmtx_row0[2];
uniform vec4 u_texmtx_row1[2];
uniform int u_texmtx_enable[2];
uniform int u_texgen_src[2];  /* 1=GX_TG_NRM, 4=GX_TG_TEX0, etc. */
out vec4 v_color;
out vec2 v_texcoord0;
out vec2 v_texcoord1;
out float v_native_shore_t;
out vec3 v_normal;
out vec3 v_plant_normal;
out vec3 v_eye_position;
out float v_fog_z;
out vec2 v_terrain_position;
void main() {
    v_terrain_position = a_position.xz / 1280.0;
    v_native_shore_t = a_texcoord0.y;
    vec4 eyePos = u_modelview * vec4(a_position, 1.0);
    vec3 worldNormal = normalize(u_normal_mtx * a_normal);
    // CPU-lit imported trees use their world normals before cylinder bending.
    // Keep mound foliage in that same plant-lighting frame at every distance.
    v_plant_normal = worldNormal;
    if (u_rolling_radius > 0.0) {
        // Recover shared world space: actors, ground, water and shadows use
        // different model matrices, but must bend around the same player.
        vec3 world = transpose(u_rolling_view_rotation) * eyePos.xyz + u_rolling_camera;
        vec3 relative = world - u_rolling_anchor;
        float along = dot(relative, u_rolling_axis);
        float angle = along / u_rolling_radius;
        float c = cos(angle), s = sin(angle);
        float height = relative.y;
        vec3 curved = relative - u_rolling_axis * along;
        curved.y = (u_rolling_radius + height) * c - u_rolling_radius;
        curved += u_rolling_axis * ((u_rolling_radius + height) * s);
        eyePos.xyz = u_rolling_view_rotation * (curved + u_rolling_anchor - u_rolling_camera);
        // Inverse-transpose of the cylindrical deformation, in the same
        // world-normal convention used by the native emu64 lighting.
        float ns = dot(worldNormal, u_rolling_axis);
        float ny = worldNormal.y;
        vec3 across = worldNormal - u_rolling_axis * ns - vec3(0.0, ny, 0.0);
        ns /= max(0.1, 1.0 + height / u_rolling_radius);
        worldNormal = normalize(across + u_rolling_axis * (ns*c + ny*s) + vec3(0.0, ny*c - ns*s, 0.0));
    }
    v_eye_position = eyePos.xyz;
    gl_Position = u_projection * eyePos;
    v_fog_z = -eyePos.z;
    v_color = a_color0;
    v_normal = worldNormal;
    vec4 tc0 = (u_texgen_src[0] == 1) ? vec4(v_normal, 1.0) : vec4(a_texcoord0, 0.0, 1.0);
    if (u_texmtx_enable[0] != 0) {
        v_texcoord0 = vec2(dot(u_texmtx_row0[0], tc0), dot(u_texmtx_row1[0], tc0));
    } else {
        v_texcoord0 = tc0.xy;
    }
    vec4 tc1 = (u_texgen_src[1] == 1) ? vec4(v_normal, 1.0) : vec4(a_texcoord0, 0.0, 1.0);
    if (u_texmtx_enable[1] != 0) {
        v_texcoord1 = vec2(dot(u_texmtx_row0[1], tc1), dot(u_texmtx_row1[1], tc1));
    } else {
        v_texcoord1 = tc1.xy;
    }
}
