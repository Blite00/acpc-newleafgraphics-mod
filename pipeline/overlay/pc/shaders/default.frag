#version 330 core
in vec4 v_color;
in vec2 v_texcoord0;
in vec2 v_texcoord1;
in float v_native_shore_t;
in vec3 v_normal;
in vec3 v_plant_normal;
in float v_fog_z;
in vec2 v_terrain_position;
in vec3 v_eye_position;
#ifdef PC_NATIVE_ONLY
const int u_terrain_kind[3] = int[3](0,0,0);
#else
uniform int u_terrain_kind[3];
#endif
uniform int u_terrain_normals;
// Original float tables; integer fetch + original interpolation is unchanged.
uniform sampler2D u_donor_luts;
uniform vec2 u_water_phase;
uniform float u_donor_water_frame;
uniform int u_donor_light_enabled;
uniform int u_nl_char;  /* New Leaf character lighting (player heads): hemisphere fill + rim + specular */
/* New Leaf's player lighting LUTs lu_player_rim1 (on N.V) and lu_player_spc1 (on N.H), 64 steps over -1..1 */
const float NL_RIM[64] = float[](0.0000f,0.0000f,0.0000f,0.0000f,0.0000f,0.0000f,0.0000f,0.0000f,0.0000f,0.0000f,0.0000f,0.0000f,0.0000f,0.0000f,0.0000f,0.0000f,0.0000f,0.0000f,0.0000f,0.0000f,0.0000f,0.0000f,0.0000f,0.0000f,0.0000f,0.0000f,0.0000f,0.0000f,0.0000f,0.0000f,0.0000f,0.0000f,0.0000f,0.0000f,0.0000f,0.0000f,0.0000f,0.0000f,0.0000f,0.0000f,0.0000f,0.0000f,0.0000f,0.0000f,0.0000f,0.0000f,0.0000f,0.0000f,0.0000f,0.0000f,0.0000f,0.0000f,0.0000f,0.0000f,0.0000f,0.0000f,0.0000f,0.0000f,0.0000f,0.0000f,0.0000f,0.0000f,0.0000f,0.0000f);
const float NL_SPC[64] = float[](0.0000f,0.0000f,0.0000f,0.0000f,0.0000f,0.0000f,0.0000f,0.0000f,0.0000f,0.0000f,0.0000f,0.0000f,0.0000f,0.0000f,0.0000f,0.0000f,0.0000f,0.0000f,0.0000f,0.0000f,0.0000f,0.0000f,0.0000f,0.0000f,0.0000f,0.0000f,0.0000f,0.0000f,0.0000f,0.0000f,0.0000f,0.0000f,0.0000f,0.0000f,0.0000f,0.0000f,0.0000f,0.0000f,0.0000f,0.0000f,0.0000f,0.0000f,0.0000f,0.0000f,0.0000f,0.0000f,0.0000f,0.0000f,0.0000f,0.0000f,0.0000f,0.0000f,0.0000f,0.0000f,0.0000f,0.0000f,0.0000f,0.0000f,0.0000f,0.0000f,0.0000f,0.0000f,0.0000f,0.0000f);
float nlLut(int which, float x) {
    /* PICA LUT inputs are signed: the first half of the table covers 0..1, the second half -1..0 */
    float f = clamp(x, 0.0, 1.0)*31.0; int i = int(floor(f)), j = min(i+1, 31);
    return which == 0 ? mix(NL_RIM[i], NL_RIM[j], fract(f)) : mix(NL_SPC[i], NL_SPC[j], fract(f));
}
uniform vec3 u_donor_diffuse;
uniform vec3 u_donor_specular;
uniform vec3 u_donor_hemi_sky;
uniform vec3 u_donor_hemi_ground;
uniform vec3 u_donor_ground_direction;
uniform vec3 u_donor_ground_ambient;
uniform vec3 u_donor_actor_direction;
uniform vec3 u_donor_water_base;
uniform vec3 u_donor_water_buffer;
uniform vec3 u_donor_water_bank;
uniform mat3 u_normal_mtx;
uniform mat3 u_rolling_view_rotation;
uniform float u_rolling_radius;
uniform vec3 u_rolling_camera;
uniform vec3 u_rolling_anchor;
uniform vec3 u_rolling_axis;
uniform vec4 u_texmtx_row1[2];

// Recovered /Bg/Outdoor/Animation/common.bcres, grd_M_F,600-frame loop.
// Argument is SOURCE ANIMATION FRAME; frame/second rate is supplied separately.
// Translation values are source texture-coordinator translations. Apply donor
// cached UV matrix convention/sign; these are not blindly image-space offsets.
vec2 donorOceanTranslation(int coordinator,float frame) {
    float t=mod(frame,600.0)/600.0;
    return (coordinator==2 ? vec2(3.0,-1.0) : vec2(-2.0,-2.0))*t;
}
vec2 donorRiverTranslation(int coordinator,float frame) {
    // Host visual tuning: calm river drift has its own clock. Do not speed
    // it up with the shoreline wash or alter gameplay river current.
    float t=mod(frame*0.5,600.0)/600.0;
    return (coordinator==0 ? vec2(0.0,-6.0) : coordinator==1 ? vec2(2.0,-4.0) : vec2(-2.0,-4.0))*t;
}
// All source Hermite tangents on these tracks are zero: smoothstep is exact.
float donorWaveTranslationY(int coordinator,float frame) {
    frame*=1.5; // shoreline-only playback, original curve shape retained
    if(coordinator==0) return 2.0*mod(frame,600.0)/600.0;
    float t=mod(frame+(coordinator==2?150.0:0.0),300.0);
    if(t<120.0) return -0.075*smoothstep(0.0,120.0,t);
    if(t<240.0) return -0.075;
    return mix(-0.075,0.0,(t-240.0)/60.0);
}
float donorWaveScaleY(int coordinator,float frame) {
    frame*=1.5; // same clock as foam translation and exposed wet sand
    if(coordinator==0) return 1.0;
    float t=mod(frame+(coordinator==2?150.0:0.0),300.0);
    return t<120.0 ? mix(1.0,1.75,smoothstep(0.0,120.0,t))
                   : mix(1.75,1.0,smoothstep(120.0,300.0,t));
}

// BEGIN DONOR FIELD LUT

// END DONOR FIELD LUT

float donorFieldDistribution(float NdotV) {
    // CGFX LUTS IsAbsolute bool is 1 (not PICA's inverted disable_abs bit).
    // Ohana's false is an unset exporter field. All 256 base values above are
    // extracted from season00.bcres/Lut_field/lu_field_grass, not a Fresnel
    // approximation. Linear interpolation replaces PICA's packed slopes.
    float x = clamp(abs(NdotV) * 256.0, 0.0, 255.0);
    int i = int(floor(x));
    return mix(texelFetch(u_donor_luts,ivec2(i,0),0).r, texelFetch(u_donor_luts,ivec2(min(i+1,255),0),0).r, fract(x));
}

// Repeat each atlas cell independently. fract*127+0.5 clamps within a
// cell and creates a jump at its repeat boundary; wrap the four bilinear
// taps instead, exactly as a standalone repeating 128x128 texture would.
vec4 terrainRepeat(sampler2D tex, int cellX, vec2 uv) {
    vec2 pixel = fract(uv)*128.0-0.5;
    ivec2 q = ivec2(floor(pixel));
    vec2 f = fract(pixel);
    ivec2 lo = q & ivec2(127);
    ivec2 hi = (q+ivec2(1)) & ivec2(127);
    vec4 a = texelFetch(tex,ivec2(cellX+lo.x,lo.y),0);
    vec4 b = texelFetch(tex,ivec2(cellX+hi.x,lo.y),0);
    vec4 c = texelFetch(tex,ivec2(cellX+lo.x,hi.y),0);
    vec4 d = texelFetch(tex,ivec2(cellX+hi.x,hi.y),0);
    return mix(mix(a,b,f.x),mix(c,d,f.x),f.y);
}

// Foliage alone has a 256-square source-detail cell in its taller atlas.
// Keep the same world-space period and wrap all bilinear taps independently.
vec4 foliageRepeat(sampler2D tex, vec2 uv) {
    vec2 pixel=fract(uv)*256.0-0.5;
    ivec2 q=ivec2(floor(pixel));
    vec2 f=fract(pixel);
    ivec2 lo=q&ivec2(255),hi=(q+ivec2(1))&ivec2(255);
    vec4 a=texelFetch(tex,ivec2(384+lo.x,lo.y),0);
    vec4 b=texelFetch(tex,ivec2(384+hi.x,lo.y),0);
    vec4 c=texelFetch(tex,ivec2(384+lo.x,hi.y),0);
    vec4 d=texelFetch(tex,ivec2(384+hi.x,hi.y),0);
    return mix(mix(a,b,f.x),mix(c,d,f.x),f.y);
}

// Outer foliage banks retain cutouts. A recessed shell closes the interior.
vec2 foliageBankUV(vec2 uv) {
    float depthUV=uv.y < -4.0 ? -uv.y-8.0 : uv.y;
    vec2 outward=v_plant_normal.xz;
    outward=dot(outward,outward)>0.0001 ? normalize(outward) : vec2(0.0,1.0);
    return v_terrain_position+outward*depthUV;
}

vec4 terrainSample(sampler2D tex, vec2 uv, int kind) {
    if (kind == 0) return texture(tex, uv);
    if (kind == 26) return vec4(1.0);
    if (kind >= 20) {
        // Native water samples remain solely to preserve its alpha/shore masks.
        if (kind == 23 || kind == 25)
            return texture(tex,vec2((fract(uv.x)*127.0+0.5)/1024.0,clamp(uv.y,0.5/128.0,127.5/128.0)));
        return terrainRepeat(tex,0,uv);
    }
    vec2 edgeUV = vec2(fract(uv.x), kind == 5 ? (fract(uv.y)*127.0+0.5)/128.0 : clamp(uv.y,0.5/128.0,127.5/128.0));
    float lawn = texture(tex,vec2((edgeUV.x*127.0+0.5)/1024.0,edgeUV.y)).r;
    if (kind == 7) return vec4(lawn,lawn,lawn,1.0);
    if (kind == 11) {
        vec4 leaves=foliageRepeat(tex,foliageBankUV(uv));
        if (uv.y < -4.0) leaves.a=1.0;
        return leaves;
    }
    if (kind == 9) {
        vec4 leaves=foliageRepeat(tex,v_terrain_position);
        leaves.a*=texture(tex,vec2((edgeUV.x*127.0+0.5)/1024.0,edgeUV.y)).a;
        return leaves;
    }
    vec3 grass = terrainRepeat(tex,128,v_terrain_position).rgb;
    vec3 ground = kind >= 5 ? terrainRepeat(tex,384,kind == 5 ? uv : v_terrain_position).rgb
        : kind == 3 ? terrainRepeat(tex,384,v_terrain_position).rgb
        : texture(tex,vec2(257.5/1024.0,0.5/128.0)).rgb;
    return vec4(mix(ground,grass,lawn),1.0);
}

// The donor wear combiner requires its own acre wear field. Native edge
// coverage is not that field: feeding it into the donor stages creates a
// colored border. Keep the native linear boundary blend in terrainSample.
// Source texture alpha remains preserved for a future faithful wear mapping.

vec3 terrainNormal(sampler2D tex, vec2 uv, int kind) {
    vec3 N = kind == 8 ? normalize(u_normal_mtx*vec3(0,1,0)) : normalize(v_normal);
    if (kind == 0 || kind == 9 || kind == 10 || kind == 11 || kind >= 20 || u_terrain_normals == 0) return N;
    if (kind == 5) {
        // Original cliff normal map follows the native wall UV chart, not XZ.
        vec3 mapped = terrainRepeat(tex,640,uv).rgb*2.0-1.0;
        mapped.z=sqrt(max(0.0,1.0-dot(mapped.xy,mapped.xy)));
        vec2 dx=dFdx(uv),dy=dFdy(uv);
        float det=dx.x*dy.y-dx.y*dy.x;
        if (abs(det)<0.0000001) return N;
        vec3 ex=transpose(u_rolling_view_rotation)*dFdx(v_eye_position);
        vec3 ey=transpose(u_rolling_view_rotation)*dFdy(v_eye_position);
        vec3 T=(ex*dy.y-ey*dx.y)/det;
        T=normalize(T-N*dot(N,T));
        vec3 B=(ey*dx.x-ex*dy.x)/det;
        B=normalize(B-N*dot(N,B)-T*dot(T,B));
        // m_cliff enables renormalization, unlike the grass/soil material.
        return normalize(T*mapped.x+B*mapped.y+N*mapped.z);
    }
    vec2 edge = vec2((fract(uv.x)*127.0+0.5)/1024.0, clamp(uv.y,0.5/128.0,127.5/128.0));
    float lawn = kind == 4 ? 0.0 : texture(tex, edge).r;
    // Donor acre UV spans 0..16 and its normal coordinator is (.25,.5):
    // four U repeats and eight V repeats per acre. Native raw acre is 10240
    // units, so v_terrain_position spans eight; grass atlas remains 16 repeats.
    // m_beach uses UV0 at unit scale; m_grass uses (.25,.5) on its
    // doubled UV0 span. Sharing the grass scale enlarged sand relief.
    vec2 normalScale=(kind == 6 || kind == 7) ? vec2(1.0) : vec2(0.5,1.0);
    vec3 grain = kind == 4 ? vec3(0.0) : terrainRepeat(tex,512,v_terrain_position*normalScale).rgb*2.0-1.0;
    vec3 stone = (kind == 3 || kind == 4)
        ? terrainRepeat(tex,640,v_terrain_position).rgb*2.0-1.0 : grain;
    // Preserve the normal map vectors from the source material unchanged.
    // Kind 4 is the pure paving endpoint, before native boundary coverage.
    if (kind == 4) lawn = 0.0;
    vec3 mapped = mix((kind == 3 || kind == 4) ? stone : grain, grain, lawn);
    // Both diffuse and normals use the same acre-plane frame, independent of
    // the rotating/mirrored boundary strip UVs. Transform into GX light space.
    vec3 T = normalize(u_normal_mtx * vec3(1,0,0));
    T = normalize(T - N * dot(N,T));
    // Donor +V runs toward -Z on the flat acre; PNG image rows already
    // reverse the sampled V coordinate, but normal-vector Y keeps this basis.
    vec3 B = normalize(cross(N,T));
    // Both donor m_grass and m_smat disable bump renormalization.
    return T*mapped.x + B*mapped.y + N*mapped.z;
}

/* Fog on/off is separate from the range params so shader specialization can
   fold the branch while start/end stay dynamic */
uniform int u_fog_enable;
uniform vec4 u_fog_params;  /* y=start, z=end (x unused) */
uniform vec4 u_fog_color;

/* TEV registers: PREV, REG0, REG1(=PRIM), REG2(=ENV) */
uniform vec4 u_tev_prev;
uniform vec4 u_tev_reg0;
uniform vec4 u_tev_reg1;
uniform vec4 u_tev_reg2;

/* Per-stage TEV config. All stages are identical in shape, so one loop
   over these arrays handles them; keep PC_GX_MAX_TEV_STAGES (=3) in sync. */
uniform int u_num_tev_stages;
uniform ivec4 u_tev_color_in[3];  /* x=a, y=b, z=c, w=d (GXTevColorArg) */
uniform ivec4 u_tev_alpha_in[3];
uniform int   u_tev_color_op[3];  /* 0=add, 1=sub */
uniform int   u_tev_alpha_op[3];
uniform int   u_tev_tc_src[3];    /* texcoord index (0 or 1) */
uniform ivec4 u_tev_bsc[3];       /* x=c_bias, y=c_scale, z=a_bias, w=a_scale */
uniform ivec4 u_tev_out[3];       /* x=c_clamp, y=a_clamp, z=c_out_reg, w=a_out_reg */
uniform ivec2 u_tev_swap[3];      /* x=ras swap idx, y=tex swap idx */
uniform ivec4 u_tev_ind_cfg[3];   /* x=ind_stage, y=ind_mtx, z=ind_bias, w=ind_alpha */
uniform ivec3 u_tev_ind_wrap[3];  /* x=wrap_s, y=wrap_t, z=add_prev */

/* Textures: stage N samples u_textureN; sampler uniforms stay separate,
   while enable flags are packed into one int array upload. */
uniform sampler2D u_texture0;
uniform sampler2D u_texture1;
uniform sampler2D u_texture2;
uniform int u_use_texture[3];

/* Lighting / color channels */
uniform ivec4 u_lighting_cfg0; /* x=lighting, y=mat_src, z=amb_src, w=num_chans */
uniform ivec4 u_lighting_cfg1; /* x=alpha_lighting, y=alpha_mat_src, z=light_mask */
uniform vec4 u_chan_color[2];  /* 0=mat, 1=amb */
uniform vec3 u_light_pos[8];
uniform vec4 u_light_color[8];

/* KONST colors and per-stage selection */
uniform vec4 u_kcolor[4];
uniform ivec3 u_tev_ksel[3];   /* x=kcolor_sel, y=kalpha_sel */

/* Swap tables (channel remapping) */
uniform ivec4 u_swap_table[4];

/* Alpha compare: control folds into specialized variants; refs are runtime
   values and must stay uniforms so they don't fragment the variant cache */
uniform ivec3 u_alpha_ctrl; /* x=comp0, y=op, z=comp1 */
uniform ivec2 u_alpha_refs; /* x=ref0, y=ref1 */

/* Indirect textures */
uniform int u_num_ind_stages;
uniform sampler2D u_ind_tex0;
uniform sampler2D u_ind_tex1;
uniform vec2 u_ind_scale[4];
uniform vec3 u_ind_mtx_r0[3];
uniform vec3 u_ind_mtx_r1[3];

out vec4 fragColor;

/* GXTevKColorSel: 0-7 = constant fractions 8/8..1/8, 8-11 = reserved (zero),
   12-15 = K0..K3 RGB, 16+ = K0..K3 single channel (R,G,B,A). The split range
   structure doesn't benefit from a switch, so the discrete and ranged cases
   stay as ifs. */
vec3 getKonstC(int sel) {
    if (sel <= 7)  return vec3(float(8 - sel) / 8.0);
    if (sel <= 11) return vec3(0.0);
    if (sel <= 15) return u_kcolor[sel - 12].rgb;
    int ki = (sel - 16) & 3;
    int ch = (sel - 16) >> 2;
    switch (ch) {
        case 0:  return vec3(u_kcolor[ki].r);
        case 1:  return vec3(u_kcolor[ki].g);
        case 2:  return vec3(u_kcolor[ki].b);
        default: return vec3(u_kcolor[ki].a);
    }
}

float getKonstA(int sel) {
    if (sel <= 7)  return float(8 - sel) / 8.0;
    if (sel <= 15) return 0.0;
    int ki = (sel - 16) & 3;
    int ch = (sel - 16) >> 2;
    switch (ch) {
        case 0:  return u_kcolor[ki].r;
        case 1:  return u_kcolor[ki].g;
        case 2:  return u_kcolor[ki].b;
        default: return u_kcolor[ki].a;
    }
}

/* GXTevColorArg enum (0-15) */
vec3 getTevC(int id, vec4 prev, vec4 tex, vec4 ras,
             vec4 r0, vec4 r1, vec4 r2, vec3 konst) {
    switch (id) {
        case 0:  return prev.rgb;      /* CPREV */
        case 1:  return vec3(prev.a);  /* APREV */
        case 2:  return r0.rgb;        /* C0 */
        case 3:  return vec3(r0.a);    /* A0 */
        case 4:  return r1.rgb;        /* C1 */
        case 5:  return vec3(r1.a);    /* A1 */
        case 6:  return r2.rgb;        /* C2 */
        case 7:  return vec3(r2.a);    /* A2 */
        case 8:  return tex.rgb;       /* TEXC */
        case 9:  return vec3(tex.a);   /* TEXA */
        case 10: return ras.rgb;       /* RASC */
        case 11: return vec3(ras.a);   /* RASA */
        case 12: return vec3(1.0);     /* ONE */
        case 13: return vec3(0.5);     /* HALF */
        case 14: return konst;         /* KONST */
        default: return vec3(0.0);     /* ZERO */
    }
}

/* GXTevAlphaArg enum (0-7) */
float getTevA(int id, float prev, float tex, float ras,
              float r0, float r1, float r2, float konst) {
    switch (id) {
        case 0:  return prev;   /* APREV */
        case 1:  return r0;     /* A0 */
        case 2:  return r1;     /* A1 */
        case 3:  return r2;     /* A2 */
        case 4:  return tex;    /* TEXA */
        case 5:  return ras;    /* RASA */
        case 6:  return konst;  /* KONST */
        default: return 0.0;    /* ZERO */
    }
}

vec4 applySwap(vec4 v, ivec4 sw) {
    return vec4(v[sw.x], v[sw.y], v[sw.z], v[sw.w]);
}

/* TEV formula: d OP ((1-c)*a + c*b) */
vec4 tevStage(ivec4 cin, int cop, ivec4 ain, int aop,
              vec4 prev, vec4 tex, vec4 ras,
              vec4 r0, vec4 r1, vec4 r2,
              vec3 konstC, float konstA) {
    vec3 ca = getTevC(cin.x, prev, tex, ras, r0, r1, r2, konstC);
    vec3 cb = getTevC(cin.y, prev, tex, ras, r0, r1, r2, konstC);
    vec3 cc = getTevC(cin.z, prev, tex, ras, r0, r1, r2, konstC);
    vec3 cd = getTevC(cin.w, prev, tex, ras, r0, r1, r2, konstC);
    vec3 blend = mix(ca, cb, cc);
    vec3 cResult = (cop == 1) ? (cd - blend) : (cd + blend);

    float aa = getTevA(ain.x, prev.a, tex.a, ras.a, r0.a, r1.a, r2.a, konstA);
    float ab = getTevA(ain.y, prev.a, tex.a, ras.a, r0.a, r1.a, r2.a, konstA);
    float ac = getTevA(ain.z, prev.a, tex.a, ras.a, r0.a, r1.a, r2.a, konstA);
    float ad = getTevA(ain.w, prev.a, tex.a, ras.a, r0.a, r1.a, r2.a, konstA);
    float aBlend = mix(aa, ab, ac);
    float aResult = (aop == 1) ? (ad - aBlend) : (ad + aBlend);

    return vec4(cResult, aResult);
}

/* bias: 0=none, 1=+0.5, 2=-0.5; scale: 0=x1, 1=x2, 2=x4, 3=x0.5 */
vec4 applyBSC(vec4 v, ivec4 bsc) {
    switch (bsc.x) {
        case 1: v.rgb += 0.5; break;
        case 2: v.rgb -= 0.5; break;
    }
    switch (bsc.y) {
        case 1: v.rgb *= 2.0; break;
        case 2: v.rgb *= 4.0; break;
        case 3: v.rgb *= 0.5; break;
    }
    switch (bsc.z) {
        case 1: v.a += 0.5; break;
        case 2: v.a -= 0.5; break;
    }
    switch (bsc.w) {
        case 1: v.a *= 2.0; break;
        case 2: v.a *= 4.0; break;
        case 3: v.a *= 0.5; break;
    }
    return v;
}

/* out_cfg.zw selects target register: 0=PREV, 1=REG0, 2=REG1, 3=REG2 */
void writeToReg(vec4 val, ivec4 out_cfg,
                inout vec4 prev, inout vec4 r0, inout vec4 r1, inout vec4 r2) {
    vec3 rgb = (out_cfg.x != 0) ? clamp(val.rgb, 0.0, 1.0) : val.rgb;
    float a  = (out_cfg.y != 0) ? clamp(val.a,   0.0, 1.0) : val.a;
    switch (out_cfg.z) {
        case 0:  prev.rgb = rgb; break;
        case 1:  r0.rgb   = rgb; break;
        case 2:  r1.rgb   = rgb; break;
        default: r2.rgb   = rgb; break;
    }
    switch (out_cfg.w) {
        case 0:  prev.a = a; break;
        case 1:  r0.a   = a; break;
        case 2:  r1.a   = a; break;
        default: r2.a   = a; break;
    }
}

vec3 sampleIndTex(int ind_stage, vec2 tc0, vec2 tc1) {
    vec2 tc = (ind_stage == 0) ? tc0 : tc1;
    vec4 s = (ind_stage == 0) ? texture(u_ind_tex0, tc) : texture(u_ind_tex1, tc);
    return s.rgb;
}

vec2 applyIndirect(ivec4 ind_cfg, ivec3 ind_wrap, vec2 coord,
                   vec2 prev_offset, vec2 tc0, vec2 tc1) {
    int ind_mtx_id = ind_cfg.y;
    if (ind_mtx_id == 0) return coord;  /* GX_ITM_OFF */

    vec3 indSample = sampleIndTex(ind_cfg.x, tc0, tc1);

    /* Bias: shift [0,1] to [-0.5,0.5] per axis (GX_ITB bitmask: S=1, T=2, U=4) */
    int bias = ind_cfg.z;
    vec3 biased = indSample;
    if ((bias & 1) != 0) biased.x -= 0.5;
    if ((bias & 2) != 0) biased.y -= 0.5;
    if ((bias & 4) != 0) biased.z -= 0.5;

    /* GX_ITM 1-3=full 2D, 5-7=S-only, 9-11=T-only. Ranged ids rather than
       discrete cases, so keep as ifs. */
    vec2 offset = vec2(0.0);
    int idx;
    if (ind_mtx_id >= 1 && ind_mtx_id <= 3) {
        idx = ind_mtx_id - 1;
        offset.x = dot(u_ind_mtx_r0[idx], biased);
        offset.y = dot(u_ind_mtx_r1[idx], biased);
    } else if (ind_mtx_id >= 5 && ind_mtx_id <= 7) {
        idx = ind_mtx_id - 5;
        offset.x = dot(u_ind_mtx_r0[idx], biased);
        offset.y = 0.0;
    } else if (ind_mtx_id >= 9 && ind_mtx_id <= 11) {
        idx = ind_mtx_id - 9;
        offset.x = 0.0;
        offset.y = dot(u_ind_mtx_r1[idx], biased);
    }

    if (ind_wrap.z != 0) offset += prev_offset;

    /* Wrap base texcoord: 0=off, 1-5=256..16 texels, 6=zero.
       Uses floor-based wrap instead of mod() to handle negative inputs. */
    vec2 wrappedCoord = coord;
    if (ind_wrap.x == 6) wrappedCoord.x = 0.0;
    else if (ind_wrap.x >= 1 && ind_wrap.x <= 5) {
        float wrapSize = float(1 << (9 - ind_wrap.x));  /* 256,128,64,32,16 */
        float w = coord.x * 256.0;
        wrappedCoord.x = (w - wrapSize * floor(w / wrapSize)) / 256.0;
    }
    if (ind_wrap.y == 6) wrappedCoord.y = 0.0;
    else if (ind_wrap.y >= 1 && ind_wrap.y <= 5) {
        float wrapSize = float(1 << (9 - ind_wrap.y));
        float w = coord.y * 256.0;
        wrappedCoord.y = (w - wrapSize * floor(w / wrapSize)) / 256.0;
    }

    return wrappedCoord + offset;
}

/* EQUAL/NEQUAL use epsilon for float precision after interpolation */
bool alphaTest(int comp, float val, float ref) {
    const float EPS = 0.5 / 255.0;
    switch (comp) {
        case 0:  return false;                  /* NEVER */
        case 1:  return val < ref;              /* LESS */
        case 2:  return abs(val - ref) < EPS;   /* EQUAL */
        case 3:  return val <= ref;             /* LEQUAL */
        case 4:  return val > ref;              /* GREATER */
        case 5:  return abs(val - ref) >= EPS;  /* NEQUAL */
        case 6:  return val >= ref;             /* GEQUAL */
        default: return true;                   /* ALWAYS */
    }
}

// Donor m_grass's fully grassed and fully bare endpoints simplify to
// albedo * fragmentPrimary + fragmentSecondary. Native coverage is only a
// geometric blend between those endpoints; it is NOT donor wear-map input.
// Original hourly colors and daily direction in the host player-anchored frame.
float donorDiffuseFactor(vec3 normal) {
    if (u_donor_light_enabled != 0)
        return max(dot(normal,normalize(u_donor_ground_direction)),0.0);
    float weighted = 0.0;
    float weight = 0.0;
    for (int i=0; i<8; i++) {
        if ((u_lighting_cfg1.z & (1 << i)) != 0) {
            float w = dot(u_light_color[i].rgb,vec3(0.2126,0.7152,0.0722));
            if (dot(u_light_pos[i],u_light_pos[i]) > 0.00001) {
                weighted += w*max(dot(normal,normalize(u_light_pos[i])),0.0);
                weight += w;
            }
        }
    }
    return weight > 0.00001 ? weighted/weight : max(normal.y,0.0);
}

vec3 terrainEndpoint(vec3 albedo, vec3 normal, float exposure) {
    if (u_donor_light_enabled != 0) {
        vec3 primary = clamp(u_donor_ground_ambient+u_donor_diffuse*donorDiffuseFactor(normal),0.0,1.0);
        vec3 view = transpose(u_rolling_view_rotation)*normalize(-v_eye_position);
        // Source clampHighlight is false: specular has no diffuse-angle gate.
        vec3 secondary = u_terrain_normals != 0
            ? donorFieldDistribution(dot(normal,view))*vec3(0.68,0.56,0.30)*u_donor_specular : vec3(0.0);
        return floor(clamp(albedo*primary+secondary,0.0,1.0)*255.0+0.5)/255.0;
    }
    if (u_lighting_cfg0.x == 0) return albedo;
    // Donor ambient/diffuse material coefficients are white. Do not apply
    // ACPC vertex/material/primitive colors to these imported materials.
    vec3 primary = u_chan_color[1].rgb;
    vec3 direct = vec3(0.0);
    for (int i=0; i<8; i++) {
        if ((u_lighting_cfg1.z & (1 << i)) != 0) {
            float diffuse = clamp(dot(normal,normalize(u_light_pos[i])),0.0,1.0);
            direct += diffuse*u_light_color[i].rgb;
        }
    }
    primary = clamp(primary+direct,0.0,1.0);
    vec3 secondary = vec3(0.0);
    if (u_terrain_normals != 0) {
        vec3 view = transpose(u_rolling_view_rotation)*normalize(-v_eye_position);
        secondary = exposure*donorFieldDistribution(dot(normal,view))
                  * vec3(0.68,0.56,0.30)*clamp(direct,0.0,1.0);
    }
    // Current light colors and exposure remain the host lighting adapter.
    // Matching the donor's complete environment-light tables is separate.
    return floor(clamp(albedo*primary+secondary,0.0,1.0)*255.0+0.5)/255.0;
}

vec3 terrainStoneEndpoint(vec4 stone, vec3 normal) {
    // Actual m_smat from grd_F_H_0: stage selectors 0,1; white diffuse/
    // ambient material, warm constant0 and texture-alpha-gated specular0.
    vec3 primary = vec3(1.0);
    vec3 direct = vec3(0.0);
    if (u_donor_light_enabled == 0 && u_lighting_cfg0.x != 0) {
        for (int i=0; i<8; i++) {
            if ((u_lighting_cfg1.z & (1 << i)) != 0)
                direct += clamp(dot(normal,normalize(u_light_pos[i])),0.0,1.0)*u_light_color[i].rgb;
        }
        primary = clamp(u_chan_color[1].rgb+direct,0.0,1.0);
    }
    if (u_donor_light_enabled != 0) primary = clamp(u_donor_ground_ambient+u_donor_diffuse*donorDiffuseFactor(normal),0.0,1.0);
    vec3 stage0 = floor(clamp(stone.rgb*primary+vec3(0.08,0.02,0.0),0.0,1.0)*255.0+0.5)/255.0;
    float specularMask = clamp(2.0*floor(clamp(stone.a-0.5,0.0,1.0)*255.0+0.5)/255.0,0.0,1.0);
    vec3 secondary = vec3(0.0);
    if (u_donor_light_enabled == 0 && u_terrain_normals != 0 && u_lighting_cfg0.x != 0) {
        vec3 view = transpose(u_rolling_view_rotation)*normalize(-v_eye_position);
        secondary = donorFieldDistribution(dot(normal,view))*vec3(0.60,0.55,0.40)*clamp(direct,0.0,1.0);
    }
    if (u_donor_light_enabled != 0 && u_terrain_normals != 0) {
        vec3 view = transpose(u_rolling_view_rotation)*normalize(-v_eye_position);
        secondary = donorFieldDistribution(dot(normal,view))*vec3(0.60,0.55,0.40)*u_donor_specular;
    }
    // Source stage1: secondary * previousAlpha + previousRGB. Its final
    // alpha is unrelated to native path coverage and is not used here.
    return floor(clamp(stage0+secondary*specularMask,0.0,1.0)*255.0+0.5)/255.0;
}

// Original Lut_field/lu_field_cliff0, absolute light-normal input.

float donorCliffDistribution(float nl) {
    float x=clamp(abs(nl)*256.0,0.0,255.0);
    int i=int(floor(x));
    return mix(texelFetch(u_donor_luts,ivec2(i,1),0).r,texelFetch(u_donor_luts,ivec2(min(i+1,255),1),0).r,fract(x));
}
vec3 coastEndpoint(vec3 albedo,vec3 normal,bool cliff) {
    float nl=donorDiffuseFactor(normal);
    vec3 primary=vec3(1.0),specular=vec3(0.0);
    if (u_donor_light_enabled != 0) {
        // Ground scene global ambient is environment slot4. Beach material
        // uses ambient .8/diffuse .9; cliffs use white for both coefficients.
        primary=clamp(u_donor_ground_ambient*(cliff ? 1.0 : 0.8)
                     +u_donor_diffuse*nl*(cliff ? 1.0 : 0.9),0.0,1.0);
        specular=u_donor_specular;
    } else if (u_lighting_cfg0.x != 0) {
        primary=u_chan_color[1].rgb;
        for (int i=0;i<8;i++) if ((u_lighting_cfg1.z & (1<<i)) != 0) {
            vec3 direct=max(dot(normal,normalize(u_light_pos[i])),0.0)*u_light_color[i].rgb;
            primary+=direct; specular+=direct;
        }
    }
    vec3 view=transpose(u_rolling_view_rotation)*normalize(-v_eye_position);
    // Actual m_cliff and m_beach material coefficients/LUT scales.
    vec3 response=cliff
        ? vec3(0.62,0.39,0.25)*donorCliffDistribution(nl)+vec3(0.30,0.23,0.17)*donorFieldDistribution(dot(normal,view))
        : vec3(1.0,0.80,0.65)*0.5*donorFieldDistribution(dot(normal,view))+vec3(0.30,0.16,0.12);
    if (u_terrain_normals == 0) response=vec3(0.0);
    return floor(clamp(albedo*primary+response*specular,0.0,1.0)*255.0+0.5)/255.0;
}

// Cliff and river-bank meshes have unrelated native UV charts. Project the
// same original stone cells in acre/world space so their shared edge has the
// same scale and phase. Native UVs still own all grass/water boundary masks.
// Original m_cliff sampler: U repeat, V mirrored repeat (donor enum2/3).
// Mirror integer bilinear taps within this atlas cell. Ordinary V repeat
// joins unrelated first/last rows, creating a horizontal seam every level.
vec4 cliffSample(sampler2D tex,int cell,vec2 uv) {
    vec2 pixel=vec2(fract(uv.x),mod(uv.y,2.0))*128.0-0.5;
    ivec2 q=ivec2(floor(pixel));vec2 f=fract(pixel);
    int x0=q.x&127,x1=(q.x+1)&127;
    int y0=q.y&255,y1=(q.y+1)&255;
    y0=y0<128?y0:255-y0;y1=y1<128?y1:255-y1;
    vec4 a=texelFetch(tex,ivec2(cell+x0,y0),0);
    vec4 b=texelFetch(tex,ivec2(cell+x1,y0),0);
    vec4 c=texelFetch(tex,ivec2(cell+x0,y1),0);
    vec4 d=texelFetch(tex,ivec2(cell+x1,y1),0);
    return mix(mix(a,b,f.x),mix(c,d,f.x),f.y);
}
vec3 cliffMappedNormal(sampler2D tex,int cell,vec2 uv,vec3 N) {
    if(u_terrain_normals==0)return N;
    vec3 mapped=cliffSample(tex,cell,uv).rgb*2.0-1.0;
    mapped.z=sqrt(max(0.0,1.0-dot(mapped.xy,mapped.xy)));
    vec2 dx=dFdx(uv),dy=dFdy(uv);
    float det=dx.x*dy.y-dx.y*dy.x;
    if(abs(det)<0.0000001)return N;
    vec3 ex=transpose(u_rolling_view_rotation)*dFdx(v_eye_position);
    vec3 ey=transpose(u_rolling_view_rotation)*dFdy(v_eye_position);
    vec3 T=(ex*dy.y-ey*dx.y)/det;
    T-=N*dot(N,T);
    if(dot(T,T)<0.000001)return N;
    T=normalize(T);
    vec3 B=(ey*dx.x-ex*dy.x)/det;
    B-=N*dot(N,B)+T*dot(T,B);
    if(dot(B,B)<0.000001)return N;
    return normalize(T*mapped.x+normalize(B)*mapped.y+N*mapped.z);
}
vec3 cliffStoneMaterial(sampler2D tex,int colorCell,int normalCell) {
    vec3 world=transpose(u_rolling_view_rotation)*v_eye_position+u_rolling_camera;
    vec3 relative=world-u_rolling_anchor;
    float height=world.y,cs=1.0,sn=0.0;
    if(u_rolling_radius>0.0) {
        float along=dot(relative,u_rolling_axis);
        float radial=length(vec2(along,u_rolling_radius+relative.y));
        height=radial-u_rolling_radius+u_rolling_anchor.y;
        cs=(u_rolling_radius+relative.y)/max(radial,0.001);
        sn=along/max(radial,0.001);
    }
    vec3 N=normalize(v_normal);
    // Steep wall/bank stone uses a single material frame, not a UV-height
    // fade that only moves the lighting break farther along the slope.
    float wallContact=1.0-smoothstep(0.70,0.83,normalize(v_plant_normal).y);
    vec3 vertical=vec3(v_plant_normal.x,0.0,v_plant_normal.z);
    if(wallContact>0.0 && dot(vertical,vertical)>0.000001) {
        vertical=normalize(vertical);
        float along=dot(vertical,u_rolling_axis);
        vec3 across=vertical-u_rolling_axis*along;
        vertical=normalize(across+u_rolling_axis*(along*cs)+vec3(0.0,-along*sn,0.0));
        N=normalize(mix(N,vertical,wallContact));
    }
    vec2 weights=abs(v_plant_normal.xz);
    if(weights.x+weights.y<0.0001)
        return coastEndpoint(terrainRepeat(tex,colorCell,v_terrain_position).rgb,N,true);
    weights*=weights;weights*=weights;
    weights/=max(weights.x+weights.y,0.000001);
    // Eight repeats per 640-world-unit acre: acre borders are integer phases.
    vec2 xUV=vec2(v_terrain_position.y,-height/80.0);
    vec2 zUV=vec2(v_terrain_position.x,-height/80.0);
    vec3 albedo=vec3(0.0),normal=vec3(0.0);
    if(weights.x>0.0001) {
        albedo+=cliffSample(tex,colorCell,xUV).rgb*weights.x;
        normal+=cliffMappedNormal(tex,normalCell,xUV,N)*weights.x;
    }
    if(weights.y>0.0001) {
        albedo+=cliffSample(tex,colorCell,zUV).rgb*weights.y;
        normal+=cliffMappedNormal(tex,normalCell,zUV,N)*weights.y;
    }
    if(dot(normal,normal)<0.000001)normal=N;
    return coastEndpoint(albedo,normalize(normal),true);
}

vec4 waterSurfaceCells(sampler2D tex,vec2 flowA,vec2 flowB,bool ocean,int albedoCell,int normalCell);
vec4 waterSurfaceCells(sampler2D tex,vec2 flowA,vec2 flowB,bool ocean,int albedoCell,int normalCell);
vec3 waterMaterialCells(sampler2D tex,vec2 flowA,vec2 flowB,bool ocean,int albedoCell,int normalCell);
float donorBottomWet(sampler2D tex,vec2 uv,int maskCell);
vec4 waterFoamCells(sampler2D tex,vec2 uv,float nativeShoreT,int waveCell,int maskCell);

vec3 foliageMaterial(vec3 leaves) {
    vec3 N=normalize(v_plant_normal);
    float hw=clamp(dot(N,normalize(vec3(0.0,1.0,0.5)))*0.5+0.5,0.0,1.0);
    vec3 light=u_donor_light_enabled != 0
        ? u_donor_ground_ambient+u_donor_diffuse*max(dot(N,normalize(u_donor_actor_direction)),0.0)
          +mix(u_donor_hemi_ground,u_donor_hemi_sky,hw) : vec3(1.0);
    return floor(clamp(leaves*light,0.0,1.0)*255.0+0.5)/255.0;
}

vec3 terrainMaterial(sampler2D tex, vec2 uv, int kind, vec3 nativeColor) {
    if (kind == 9 || kind == 11) {
        vec2 leafUV=kind == 11 ? foliageBankUV(uv) : v_terrain_position;
        return foliageMaterial(foliageRepeat(tex,leafUV).rgb);
    }
    if (kind == 7) {
        vec3 albedo=terrainRepeat(tex,384,v_terrain_position).rgb;
        vec3 surface=coastEndpoint(albedo,terrainNormal(tex,uv,kind),false);
        // Original m_bottom has its own moving damp-sand mask. Its
        // recovered phase trails/advances independently of the foam,
        // leaving visible darker sand when the shallow wash withdraws.
        float waveV=1.0-clamp(uv.y,0.0,1.0);
        float wet=donorBottomWet(tex,vec2(v_terrain_position.x,waveV),256);
        return surface*mix(vec3(1.0),vec3(229.0,217.0,204.0)/255.0,wet);
    }
    vec2 edge = vec2((fract(uv.x)*127.0+0.5)/1024.0,
                     kind == 5 ? (fract(uv.y)*127.0+0.5)/128.0 : clamp(uv.y,0.5/128.0,127.5/128.0));
    float coverage = clamp(texture(tex,edge).r,0.0,1.0);
    vec3 grass = terrainRepeat(tex,128,v_terrain_position).rgb;
    if (kind == 10) {
        // The native floor fills a real hole in the surrounding acre mesh.
        return terrainEndpoint(grass,terrainNormal(tex,v_terrain_position*2.0,1),0.35);
    }
    vec3 grassNormal = terrainNormal(tex,uv,1);
    vec3 lawn = terrainEndpoint(grass,grassNormal,0.35);
    vec3 ground;
    if (kind == 5 || kind == 6) {
        vec3 albedo=terrainRepeat(tex,384,kind == 5 ? uv : v_terrain_position).rgb;
        vec3 surface=kind==5 ? cliffStoneMaterial(tex,384,640)
            : coastEndpoint(albedo,terrainNormal(tex,uv,kind),false);
        if (kind == 5) {
            // Only the lowest cliff row can meet foreground ground. Preserve
            // stacked upper wall repeats, and do not sprout grass at a steep
            // wall/water junction where the native normals have no shelf.
            float groundSupport=smoothstep(0.45,0.65,normalize(v_plant_normal).y);
            float foot=smoothstep(0.92,1.0,uv.y)*groundSupport;
            // The lawn/snow is sampled triplanar here: a planar XZ projection stretches into vertical streaks on a
            // steep face, while the shelf (second step) keeps its grass.
            vec3 cw=pow(abs(normalize(v_plant_normal)),vec3(4.0));
            cw/=max(cw.x+cw.y+cw.z,0.000001);
            float wy=(transpose(u_rolling_view_rotation)*v_eye_position+u_rolling_camera).y/1280.0;
            vec3 grassTri=terrainRepeat(tex,128,v_terrain_position).rgb*cw.y
                         +terrainRepeat(tex,128,vec2(v_terrain_position.y,-wy)).rgb*cw.x
                         +terrainRepeat(tex,128,vec2(v_terrain_position.x,-wy)).rgb*cw.z;
            vec3 lawnTri=terrainEndpoint(grassTri,grassNormal,0.35);
            // the native fade mask is stretched down a steep face too, so it only counts on shelf-like surfaces
            float shelf=smoothstep(0.50,0.75,normalize(v_plant_normal).y);
            float rim=uv.y>=0.90 ? 0.0 : coverage*shelf;
            vec3 footLawn=terrainEndpoint(grass,terrainNormal(tex,uv,8),0.35);
            return mix(mix(surface,lawnTri,rim),footLawn,foot);
        }
        return mix(surface,lawn,coverage);
    }
    if (kind == 3) {
        vec4 stone = terrainRepeat(tex,384,v_terrain_position);
        ground = terrainStoneEndpoint(stone,terrainNormal(tex,uv,4));
    } else {
        // Keep the recovered seasonal soil material. Native strip coverage
        // cannot stand in for the donor acre wear field: its inverse mapping
        // jumped in RGB at 0/1 and generated colored bands at strip joins.
        vec3 soil = texture(tex,vec2(257.5/1024.0,0.5/128.0)).rgb;
        ground = terrainEndpoint(soil,grassNormal,0.25);
    }
    // Blend compatible fully-grassed/bare donor endpoints. The same grass
    // endpoint is reached continuously on soil, paving and pure-grass draws.
    return mix(ground,lawn,coverage);
}




float waterLutSample(float angle,bool fresnel) {
    float x=clamp(abs(angle)*256.0,0.0,255.0);
    int i=int(floor(x)),j=min(i+1,255);
    return fresnel ? mix(texelFetch(u_donor_luts,ivec2(i,3),0).r,texelFetch(u_donor_luts,ivec2(j,3),0).r,fract(x))
                   : mix(texelFetch(u_donor_luts,ivec2(i,2),0).r,texelFetch(u_donor_luts,ivec2(j,2),0).r,fract(x));
}
vec3 waterPrimary(vec3 normal) {
    if (u_donor_light_enabled != 0) return clamp(u_donor_ground_ambient+u_donor_diffuse*donorDiffuseFactor(normal),0.0,1.0);
    if (u_lighting_cfg0.x == 0) return vec3(1.0);
    vec3 color=u_chan_color[1].rgb;
    for (int i=0;i<8;i++) if ((u_lighting_cfg1.z & (1<<i)) != 0)
        color+=max(dot(normal,normalize(u_light_pos[i])),0.0)*u_light_color[i].rgb;
    return clamp(color,0.0,1.0);
}
// Staged source equations; root owns shader insertion.
// PICA semantics verified against primary emulator source:
// https://raw.githubusercontent.com/azahar-emu/azahar/master/src/video_core/shader/generator/glsl_fs_shader_gen.cpp
// WriteTevStage clamps operation, quantizes, THEN multiplies scale/clamps.
// AddThenMultiply clamps its SUM before multiplying third input.
float donorWaterQ8(float x) { return floor(clamp(x,0.0,1.0)*255.0+0.5)/255.0; }
vec3 donorWaterQ8(vec3 x) { return floor(clamp(x,0.0,1.0)*255.0+0.5)/255.0; }
vec3 donorWaterTevRGB(vec3 tex1,vec3 tex2,vec3 primary,vec3 secondary) {
    vec3 stage0=clamp(donorWaterQ8((vec3(1.0)-tex2)*tex1)*4.0,0.0,1.0);
    vec3 stage1=clamp(donorWaterQ8(stage0*tex2)*2.0,0.0,1.0);
    vec3 stage2=donorWaterQ8(mix(u_donor_water_base,u_donor_water_buffer,stage1));
    return donorWaterQ8(stage2*clamp(primary,0.0,1.0)+clamp(secondary,0.0,1.0));
}
float donorWaterOpacity(float sourceVertexAlpha,float NdotV,bool ocean) {
    // Both LUTs use abs(NdotV), scale2, primary-fragment alpha enabled.
    // Ocean=lu_field_grass, river=lu_field_water_f.
    float fresnel=ocean ? donorFieldDistribution(NdotV) : waterLutSample(NdotV,true);
    float primaryAlpha=clamp(2.0*fresnel,0.0,1.0);
    float vertex=donorWaterQ8(sourceVertexAlpha);
    float stage0=donorWaterQ8(vertex*vertex);
    float stage1=donorWaterQ8(stage0*stage0);
    // Exported packed constant alpha115; original float field .45.
    return donorWaterQ8(min(primaryAlpha+115.0/255.0,1.0)*stage1);
}
// Native caustic alpha is NOT sourceVertexAlpha. Donor river vertices are
// opaque; ocean vertices supply shore coverage. Keep host shoreline coverage
// separate. Applying this alpha requires actual blending or compositing over
// the bottom; multiplying RGB alone incorrectly darkens water.
// Existing LUT helpers interpolate decoded base values, not original packed
// slopes. This is source-based shading, not bit-identical LUT emulation.

vec4 waterSurfaceCells(sampler2D tex,vec2 flowA,vec2 flowB,bool ocean,int albedoCell,int normalCell) {
    // Shared world projection avoids stretched native river charts. Source
    // layer scales are retained; native phases adapt the original animation.
    vec2 normalUV=flowA*(ocean ? vec2(0.5,1.0) : vec2(1.0,0.5))
        +(ocean ? donorOceanTranslation(0,u_donor_water_frame) : donorRiverTranslation(0,u_donor_water_frame));
    vec2 albedoA=flowA*(ocean ? 1.5 : 2.0)
        +(ocean ? donorOceanTranslation(1,u_donor_water_frame) : donorRiverTranslation(1,u_donor_water_frame));
    vec2 albedoB=flowB
        +(ocean ? donorOceanTranslation(2,u_donor_water_frame) : donorRiverTranslation(2,u_donor_water_frame));
    vec3 a=terrainRepeat(tex,albedoCell,albedoA).rgb;
    vec3 b=terrainRepeat(tex,albedoCell,albedoB).rgb;
    vec3 N=normalize(v_normal);
    if (ocean) {
        // The native intertidal fan has sloped shading normals although its
        // positions are flat. Its water layer must share the sea-plane frame.
        N=vec3(0.0,1.0,0.0);
        if (u_rolling_radius>0.0) {
            vec3 curved=transpose(u_rolling_view_rotation)*v_eye_position
                       +u_rolling_camera-u_rolling_anchor;
            float angle=atan(dot(curved,u_rolling_axis),curved.y+u_rolling_radius);
            N=normalize(u_rolling_axis*sin(angle)+vec3(0.0,cos(angle),0.0));
        }
    }
    if (u_terrain_normals != 0) {
        vec3 mapped=terrainRepeat(tex,normalCell,normalUV).rgb*2.0-1.0;
        mapped.z=sqrt(max(0.0,1.0-dot(mapped.xy,mapped.xy)));
        vec3 T=normalize(u_normal_mtx*vec3(1,0,0));
        T=normalize(T-N*dot(N,T));
        N=normalize(T*mapped.x+normalize(cross(N,T))*mapped.y+N*mapped.z);
    }
    vec3 primary=waterPrimary(N);
    vec3 specular=u_donor_light_enabled != 0 ? u_donor_specular : primary;
    vec3 view=transpose(u_rolling_view_rotation)*normalize(-v_eye_position);
    vec3 secondary=waterLutSample(dot(N,view),false)*vec3(0.63,0.37,0.39)*specular;
    return vec4(donorWaterTevRGB(a,b,primary,secondary),donorWaterOpacity(1.0,dot(N,view),ocean));
}
vec3 waterMaterialCells(sampler2D tex,vec2 flowA,vec2 flowB,bool ocean,int albedoCell,int normalCell) {
    vec4 water=waterSurfaceCells(tex,flowA,flowB,ocean,albedoCell,normalCell);
    if (!ocean) return water.rgb;
    // Native ocean is opaque. Composite its recovered water response over a
    // source beach/bank endpoint here, preserving fish/depth draw ordering.
    // This is a host bottom adapter, not the donor's separate m_bottom mesh.
    // Original submerged m_bottom vertices are black: its final TEV stage
    // selects raw environment slot11, AFTER lighting. Do not light it twice.
    vec3 bottom=u_donor_water_bank;
    return mix(bottom,water.rgb,water.a);
}
float donorBottomWet(sampler2D tex,vec2 uv,int maskCell) {
    // Recovered m_bottom coordinator1 translation, common.bcres. Segment
    // start is -60; the first Hermite span ends at frame20, not frame80.
    float frame=mod(u_donor_water_frame*1.5,600.0);
    float phase=mod(frame,300.0);
    float tx=phase<150.0 ? 0.25*smoothstep(0.0,150.0,phase)
                        : 0.25*(1.0-smoothstep(150.0,300.0,phase));
    float ty;
    if(frame<20.0) ty=mix(-0.18,0.025,smoothstep(-60.0,20.0,frame));
    else {
        float p=mod(frame-20.0,150.0);
        ty=p<75.0 ? mix(0.025,-0.18,smoothstep(0.0,75.0,p))
                  : mix(-0.18,0.025,smoothstep(75.0,150.0,p));
    }
    float u=2.0*(uv.x-tx);
    u=1.0-abs(mod(u,2.0)-1.0);
    vec2 maskUV=clamp(vec2(u,1.0-(uv.y-ty)),vec2(0.5/128.0),vec2(127.5/128.0));
    return terrainRepeat(tex,maskCell,maskUV).a;
}
vec4 donorWaveMask(sampler2D tex,int cell,vec2 uv,int coordinator) {
    // Original cached coordinator matrix is scale * (UV - translation).
    // The decoded atlas uses top-down image V; donor mesh V points upward.
    float u=2.0*(uv.x-(coordinator==2 ? 0.25 : 0.0));
    u=1.0-abs(mod(u,2.0)-1.0); // source MirroredRepeat U
    float v=1.0-donorWaveScaleY(coordinator,u_donor_water_frame)
                  *(uv.y-donorWaveTranslationY(coordinator,u_donor_water_frame));
    return terrainRepeat(tex,cell,clamp(vec2(u,v),vec2(0.5/128.0),vec2(127.5/128.0)));
}
vec4 waterFoamCells(sampler2D tex,vec2 uv,float nativeShoreT,int waveCell,int maskCell) {
    // Original broad m_wave surface: two 300-frame masks, 150 frames apart.
    // Only the masks move; no invented narrow cosine-driven water front.
    // Keep RGB ripple spacing independent of the compressed shoreline mask.
    // Donor m_wave has one V repeat per53.528 arc units; at the512->640
    // acre conversion that is66.910 host units, or1141.931 native tc.t.
    // The old mask V fit packed3bright repeats into this60-unit host strip.
    float wave=terrainRepeat(tex,waveCell,
        vec2(uv.x,nativeShoreT/1141.931+donorWaveTranslationY(0,u_donor_water_frame))).r;
    vec4 a=donorWaveMask(tex,maskCell,uv,1);
    vec4 b=donorWaveMask(tex,maskCell,uv,2);
    // Source edge rows have vertex alpha1 at V1..-1 and alpha0 at V-2.
    float vertexAlpha=clamp(uv.y+2.0,0.0,1.0);
    float mask=clamp(a.a+b.a,0.0,1.0)*vertexAlpha;
    vec3 color=clamp(wave*vec3(128.0,153.0,97.0)/255.0
        +clamp(a.rgb+b.rgb,0.0,1.0)*vec3(38.0,51.0,77.0)/255.0,0.0,1.0);
    return vec4(color*waterPrimary(normalize(v_normal)),mask);
}

// Insert after waterMaterialCells/waterPrimary definitions, before main.
vec3 riverBankMaterial(sampler2D tex,vec2 uv) {
    vec2 edgeUV=vec2((fract(uv.x)*127.0+0.5)/1024.0,clamp(uv.y,0.5/128.0,127.5/128.0));
    vec2 coverage=clamp(texture(tex,edgeUV).rg,0.0,1.0);
    // The native bank atlas also covers vertical waterfall/cliff contacts.
    // Its grass row belongs only to an exposed upward bank, not a second
    // green shelf beneath an adjoining cliff. Use pre-roll geometric normals.
    coverage.r*=smoothstep(0.70,0.83,normalize(v_plant_normal).y);
    // Same donor sampler and continuous stone frame as the adjacent wall.
    vec3 cliff=cliffStoneMaterial(tex,640,768);
    // Same source grass, phase and normal-map cell as surrounding acre.
    vec3 lawn=terrainEndpoint(terrainRepeat(tex,896,v_terrain_position).rgb,terrainNormal(tex,uv,1),0.35);
    // The opaque channel is the submerged cliff endpoint, not another copy
    // of the ripples. The translucent surface above supplies source Fresnel.
    vec3 bottom=u_donor_water_bank;
    vec3 color=mix(mix(cliff,lawn,coverage.r),bottom,coverage.g);
    // m_river_edge: real source tex_wave in both stages, source scales/offsets.
    float a=terrainRepeat(tex,384,uv*vec2(3.0,2.0)).r;
    float b=terrainRepeat(tex,384,uv*vec2(2.0,1.0)+vec2(0.0,-0.25)).r;
    // Keep the original edge artwork in a narrow, soft ribbon at the
    // water-side bank. The previous whole-bank envelope read as ocean surf.
    float strip=smoothstep(0.74,0.86,coverage.g)
               *(1.0-smoothstep(0.94,1.0,coverage.g))*(1.0-coverage.r);
    float alpha=clamp(2.0*(a+b)*strip*0.45,0.0,1.0);
    vec3 edgeColor=vec3(128.0,140.0,153.0)/255.0*waterPrimary(normalize(v_normal));
    return clamp(color+edgeColor*alpha,0.0,1.0);
}


void main() {
    // Legacy ocean surf is replaced by the continuous shoreline crest above.
    // Its native gameplay wave/collision state still updates normally.
    bool donorOceanSurface=u_terrain_kind[0] == 22 && u_terrain_kind[1] == 24;
    bool donorOceanShore=u_terrain_kind[0] == 22 && u_terrain_kind[1] == 23;
    if (u_terrain_kind[0] == 22 && !donorOceanSurface && !donorOceanShore) discard;
    vec2 tc[2];
    tc[0] = v_texcoord0;
    tc[1] = v_texcoord1;

    /* Pre-pass: compute per-stage texcoord (with indirect offset). The
       indirect chain has a serial dependency via ind_prev_offset, so this
       runs as its own loop before the main TEV loop. */
    vec2 stc[3];
    {
        vec2 ind_prev_offset = vec2(0.0);
        for (int s = 0; s < u_num_tev_stages; s++) {
            vec2 base = tc[u_tev_tc_src[s]];
            stc[s] = base;
            if (u_num_ind_stages > 0 && u_tev_ind_cfg[s].y != 0) {
                stc[s] = applyIndirect(u_tev_ind_cfg[s], u_tev_ind_wrap[s],
                                       stc[s], ind_prev_offset, tc[0], tc[1]);
                ind_prev_offset = stc[s] - base;
            }
        }
    }

    // Imported opaque terrain replaces the native color combiner entirely.
    // Shade it once: running native lighting/TEV first duplicated the expensive
    // donor normal/LUT work at every ground pixel without changing its output.
    if (u_terrain_kind[0] > 0 && u_terrain_kind[0] < 20) {
        int kind=u_terrain_kind[0];
        vec4 surface=vec4(1.0);
        if (kind == 9 || kind == 11) {
            vec2 leafUV=kind == 11 ? foliageBankUV(stc[0]) : v_terrain_position;
            surface=foliageRepeat(u_texture0,leafUV);
            if (u_use_texture[0] == 0) surface.a=1.0;
            else if (kind == 9) {
                vec2 edge=vec2((fract(stc[0].x)*127.0+0.5)/1024.0,
                    clamp(stc[0].y,0.5/128.0,127.5/128.0));
                surface.a*=texture(u_texture0,edge).a;
            } else if (stc[0].y < -4.0) surface.a=1.0;
            if (surface.a < 0.5) discard;
            fragColor=vec4(foliageMaterial(surface.rgb),surface.a);
        } else {
            fragColor=vec4(terrainMaterial(u_texture0,stc[0],kind,vec3(1.0)),1.0);
        }
        if (u_fog_enable != 0) {
            float fog=clamp((v_fog_z-u_fog_params.y)/max(u_fog_params.z-u_fog_params.y,1e-6),0.0,1.0);
            fragColor.rgb=mix(fragColor.rgb,u_fog_color.rgb,fog);
        }
        return;
    }

    /* Texture samples. Kept as an explicit 3-way dispatch rather than a
       sampler array so the C side doesn't need to change. */
    vec4 texColor[3];
    texColor[0] = (u_use_texture[0] != 0) ? terrainSample(u_texture0, stc[0], u_terrain_kind[0]) : vec4(1.0);
    texColor[1] = (u_use_texture[1] != 0) ? terrainSample(u_texture1, stc[1], u_terrain_kind[1]) : vec4(1.0);
    texColor[2] = (u_use_texture[2] != 0) ? terrainSample(u_texture2, stc[2], u_terrain_kind[2]) : vec4(1.0);

    /* Rasterized color: GX lighting model */
    vec3 surfaceNormal = v_normal;
    if (u_terrain_kind[0] != 0) surfaceNormal = terrainNormal(u_texture0, stc[0], u_terrain_kind[0]);
    else if (u_terrain_kind[1] != 0) surfaceNormal = terrainNormal(u_texture1, stc[1], u_terrain_kind[1]);
    else if (u_terrain_kind[2] != 0) surfaceNormal = terrainNormal(u_texture2, stc[2], u_terrain_kind[2]);
    vec4 rasColor;
    vec3 nlPrimary = vec3(0.0), nlSecondary = vec3(0.0);
    float nlStrongest = 0.0;
    if (u_lighting_cfg0.w == 0) {
        rasColor = vec4(1.0);
    } else {
        vec3 matC = (u_lighting_cfg0.y != 0) ? v_color.rgb : u_chan_color[0].rgb;
        vec3 ambC = (u_lighting_cfg0.z != 0) ? v_color.rgb : u_chan_color[1].rgb;
        if (u_lighting_cfg0.x != 0) {
            vec3 lightAccum = ambC;
            vec3 N = normalize(surfaceNormal);
            if (u_nl_char != 0) {
                /* hemisphere fill instead of flat ambient (eye-space up stands in for the sky direction) */
                lightAccum = ambC*(0.80+0.40*(N.y*0.5+0.5));
            }
            for (int i = 0; i < 8; i++) {
                if ((u_lighting_cfg1.z & (1 << i)) != 0) {
                    vec3 L = normalize(u_light_pos[i]);
                    float diff = clamp(dot(surfaceNormal, L), 0.0, 1.0);
                    /* cloth: wrapped diffuse, so the light rolls softly around the body like fabric */
                    if (u_nl_char == 3) diff = clamp((dot(surfaceNormal, L)+0.45)/1.45, 0.0, 1.0)*0.9;
                    lightAccum += diff * u_light_color[i].rgb;
                    if (u_nl_char == 1 || u_nl_char == 2) {
                        /* New Leaf specular layer: material specular 0.8 x (rim LUT on N.V + highlight LUT on N.H),
                           from the strongest light only (rooms light actors with several lights, which summed
                           would wash the hair out to white) */
                        vec3 V = normalize(-v_eye_position);
                        vec3 H = normalize(L+V);
                        vec3 spec = 0.8*min(u_light_color[i].rgb, vec3(1.0))*(nlLut(0, dot(N, V))+nlLut(1, dot(N, H)));
                        if (dot(u_light_color[i].rgb, vec3(1.0)) > nlStrongest) {
                            nlStrongest = dot(u_light_color[i].rgb, vec3(1.0));
                            nlSecondary = spec;
                        }
                    }
                }
            }
            rasColor.rgb = matC * clamp(lightAccum, 0.0, 1.0);
            nlPrimary = clamp(lightAccum, 0.0, 1.0);
        } else {
            rasColor.rgb = matC;
        }
        float matA = (u_lighting_cfg1.y != 0) ? v_color.a : u_chan_color[0].a;
        rasColor.a = (u_lighting_cfg1.x != 0) ? matA * u_chan_color[1].a : matA;
    }

    vec4 prev = u_tev_prev;
    vec4 r0 = u_tev_reg0;
    vec4 r1 = u_tev_reg1;
    vec4 r2 = u_tev_reg2;

    /* Main TEV loop (Stage 0, 1, 2) */
    for (int s = 0; s < u_num_tev_stages; s++) {
        ivec2 swap = u_tev_swap[s];
        vec4 sTex = applySwap(texColor[s], u_swap_table[swap.y]);
        vec4 sRas = applySwap(rasColor,    u_swap_table[swap.x]);
        vec3 kc = getKonstC(u_tev_ksel[s].x);
        float ka = getKonstA(u_tev_ksel[s].y);
        vec4 result = tevStage(u_tev_color_in[s], u_tev_color_op[s],
                               u_tev_alpha_in[s], u_tev_alpha_op[s],
                               prev, sTex, sRas, r0, r1, r2, kc, ka);
        result = applyBSC(result, u_tev_bsc[s]);
        writeToReg(result, u_tev_out[s], prev, r0, r1, r2);
    }

    /* Alpha compare */
    if (!donorOceanSurface && !donorOceanShore && (u_terrain_kind[0] != 20 && u_terrain_kind[0] != 21) && (u_alpha_ctrl.x != 7 || u_alpha_ctrl.z != 7)) {
        float ref0 = float(u_alpha_refs.x) / 255.0;
        float ref1 = float(u_alpha_refs.y) / 255.0;
        bool pass0 = alphaTest(u_alpha_ctrl.x, prev.a, ref0);
        bool pass1 = alphaTest(u_alpha_ctrl.z, prev.a, ref1);
        bool pass;
        switch (u_alpha_ctrl.y) {
            case 0:  pass = pass0 && pass1; break;
            case 1:  pass = pass0 || pass1; break;
            case 2:  pass = pass0 != pass1; break;
            default: pass = pass0 == pass1; break;
        }
        if (!pass) discard;
    }

    fragColor = prev;
    if (u_nl_char != 0) {
        /* New Leaf: final = lit base + lit (rim + specular) x mask (0.7 on hair, 1.0 on skin; the head texture's
           alpha is the hair coverage) */
        float hair = u_use_texture[0] != 0 ? texColor[0].a : 0.0;
        /* the highlight takes the surface's own colour (a plain white add greys dark hair under room lights) */
        vec3 tint = mix(clamp(fragColor.rgb*1.8, 0.0, 1.0), vec3(1.0), 0.2);
        if (u_nl_char == 1) /* mode 2 = face art: no specular layer */
            fragColor.rgb = clamp(fragColor.rgb+nlPrimary*nlSecondary*mix(1.0, 0.7, hair)*0.45*tint, 0.0, 1.0);
        if (u_nl_char == 3 && u_use_texture[0] != 0) {
            /* cloth: fine weave (two threads per shirt texel) and a soft fuzz rim; no shine */
            vec2 w = stc[0]*vec2(64.0, 64.0)*6.2831853;
            float weave = 0.5+0.25*(sin(w.x)+sin(w.y))+0.15*sin(w.x)*sin(w.y);
            vec3 V = normalize(-v_eye_position);
            float rim = nlLut(0, dot(normalize(surfaceNormal), V));
            /* fade the weave out where a thread is smaller than a pixel (far away), so it never shimmers */
            float threadPx = max(fwidth(w.x), fwidth(w.y));
            weave = mix(0.5, weave, clamp(1.5-threadPx*0.5, 0.0, 1.0));
            fragColor.rgb *= mix(0.86, 1.04, weave);
            fragColor.rgb = clamp(fragColor.rgb+rim*0.10*nlPrimary*mix(fragColor.rgb, vec3(1.0), 0.35), 0.0, 1.0);
        }
    }

    // Imported terrain bypasses the native RGB TEV/material chain. Retain
    // native alpha, fog, coverage/topology, and separate shadow draws.
    if (donorOceanSurface || donorOceanShore) {
        vec4 water=waterSurfaceCells(u_texture0,v_terrain_position,v_terrain_position,true,128,256);
        vec4 sourceWater=water;
        // Use the same recovered Fresnel and bottom endpoint on both native
        // sea-level material sections; their common edge must shade identically.
        water.rgb=mix(u_donor_water_bank,water.rgb,water.a);
        water.a=1.0;
        if (donorOceanShore) {
            // Fit the original broad wave V1..-2 to the native shore plane
            // tc.t0..1024. The beach/bed seam is halfway through this plane.
            // Use untransformed native tc.t directly. Inverting a possibly
            // disabled or non-diagonal native texture matrix is not reliable.
            // GXTexCoord2s16 forwards raw tc units without /32 scaling.
            float nativeT=v_native_shore_t;
            // Expand the active source wash across more of the sandy strip.
            // Fit its remaining offshore fade to the existing deep-water join.
            float waveV=nativeT<=512.0 ? 1.0-clamp(nativeT/512.0,0.0,1.0)
                                      : -2.0*clamp((nativeT-512.0)/512.0,0.0,1.0);
            // Keep the sandy half free to ebb. The previous source-alpha
            // fit became permanently opaque at tc171, hiding the receding
            // sheet. Only the seabed join requires stable full coverage.
            float coverage=smoothstep(256.0,512.0,nativeT);
            vec2 waveUV=vec2(v_terrain_position.x,waveV);
            vec4 foam=waterFoamCells(u_texture0,waveUV,nativeT,384,512);
            // A shallow sheet advances/recedes with the recovered source masks.
            // Static deep coverage remains unchanged; no geometry/collision motion.
            // Cell896 stores distance to the original mask's alpha contour.
            // Source foam keeps its cutout; only the added shallow sheet needs
            // a continuous soft fringe rather than a subpixel blue knife edge.
            float wash=clamp(smoothstep(0.46,0.54,donorWaveMask(u_texture0,896,waveUV,1).r)
                            +smoothstep(0.46,0.54,donorWaveMask(u_texture0,896,waveUV,2).r),0.0,1.0);
            // The host strip ends abruptly at its landward polygon boundary.
            // Ease only the added shallow film into that edge; the donor deep
            // coverage and the source mask cycles remain unchanged.
            float landwardFade=smoothstep(0.0,144.0,max(nativeT,0.0));
            float shallowCoverage=max(coverage,wash*landwardFade);
            float wet=donorBottomWet(u_texture0,waveUV,512);
            vec3 sand=coastEndpoint(terrainRepeat(u_texture0,640,v_terrain_position).rgb,normalize(v_normal),false);
            sand*=mix(vec3(1.0),vec3(229.0,217.0,204.0)/255.0,wet);
            // Visible shallow water rests over source beach material instead of
            // the deep blue bank endpoint; join the established ocean offshore.
            vec3 bottom=mix(sand,u_donor_water_bank,clamp(nativeT/512.0,0.0,1.0));
            water.rgb=mix(bottom,sourceWater.rgb,sourceWater.a);
            water.a=shallowCoverage;
            // The host combines source additive foam and the water sheet in
            // one normal-alpha draw. Keep RGB bounded before framebuffer
            // conversion: division by near-zero coverage clipped highlights
            // into a hard white edge rather than a soft transparent fringe.
            water.rgb=clamp(water.rgb+foam.rgb*foam.a*landwardFade,0.0,1.0);

        }
        fragColor=water;
    } else if (u_terrain_kind[0] == 25) {
        // Native beach2 slopes from Y20/tc.t0 to Y-40/tc.t1536.
        // With its 16px texture those endpoints are V0 and V3. The donor
        // bottom's black deep endpoint must not replace its sandy upper rim:
        // receding-wave transparency exposes that rim directly.
        float bedDepth=clamp((stc[0].y-0.5/16.0)/3.0,0.0,1.0);
        vec3 bedNormal=normalize(v_normal);
        if (u_terrain_normals!=0) {
            vec3 mapped=terrainRepeat(u_texture0,768,v_terrain_position).rgb*2.0-1.0;
            vec3 T=normalize(u_normal_mtx*vec3(1,0,0));
            T=normalize(T-bedNormal*dot(T,bedNormal));
            bedNormal=T*mapped.x+normalize(cross(bedNormal,T))*mapped.y+bedNormal*mapped.z;
        }
        vec3 sand=coastEndpoint(terrainRepeat(u_texture0,640,v_terrain_position).rgb,bedNormal,false);
        sand*=vec3(0.9,0.85,0.8); // original beach/bottom wet-sand constant
        fragColor=vec4(mix(sand,u_donor_water_bank,smoothstep(0.0,1.0,bedDepth)),1.0);
    } else if (u_terrain_kind[0] == 26) {
        fragColor.rgb=riverBankMaterial(u_texture0,stc[0]);
    } else if (u_terrain_kind[0] >= 20) {
        bool ocean=u_terrain_kind[0] >= 22;
        // Both ripples and normal maps use a coherent 80-world-unit period.
        if (ocean) {
            fragColor.rgb=waterMaterialCells(u_texture0,v_terrain_position,v_terrain_position,true,128,256);
        } else {
            vec4 water=waterSurfaceCells(u_texture0,v_terrain_position,v_terrain_position,false,128,256);
            fragColor=water;
        }

    } else if (u_terrain_kind[0] != 0)
        fragColor.rgb = terrainMaterial(u_texture0,stc[0],u_terrain_kind[0],fragColor.rgb);
    else if (u_terrain_kind[1] != 0)
        fragColor.rgb = terrainMaterial(u_texture1,stc[1],u_terrain_kind[1],fragColor.rgb);
    else if (u_terrain_kind[2] != 0)
        fragColor.rgb = terrainMaterial(u_texture2,stc[2],u_terrain_kind[2],fragColor.rgb);

    /* Fog */
    if (u_fog_enable != 0) {
        float fog_denom = max(u_fog_params.z - u_fog_params.y, 1e-6);
        float fog_factor = clamp((v_fog_z - u_fog_params.y) / fog_denom, 0.0, 1.0);
        fragColor.rgb = mix(fragColor.rgb, u_fog_color.rgb, fog_factor);
    }
}
