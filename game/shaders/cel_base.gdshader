// cel_base.gdshader — 两段量化 cel 基础着色（art-bible §3.1.B）
//
// 规则落地：
//  - 哑光：roughness 固定 0.85，关闭默认 specular（render_mode specular_disabled）
//  - 单层硬边阴影：ndl 过 shadow_threshold，smoothstep 软化吸附（±shadow_softness）；
//    遮挡（shadow）折叠在 light() 的 ATTENUATION 里（Godot 4.6 无 SHADOW 内置），
//    用 smoothstep(0.5, 1.0, ATTENUATION) 量化
//  - 极少功能高光：仅 functional_rim=true 的苔薄荷语义交互面加 rim
//  - metallic 默认 0；旧合金道具 0.6（材质参数化，不复制 shader）
//
// 顶点色是 tint / 混层遮罩，乘在 albedo 上，不再整面替换贴图（art-bible v1.6 §3.6）。
shader_type spatial;
render_mode diffuse_burley, specular_disabled, cull_back;

uniform sampler2D albedo_tex : source_color, hint_default_white;
uniform sampler2D normal_tex : hint_normal, filter_linear_mipmap;
uniform sampler2D orm_tex : hint_default_white, filter_linear_mipmap;
uniform vec3 base_color : source_color = vec3(1.0);
uniform vec3 shadow_color : source_color = vec3(0.14, 0.16, 0.24); // 淤泥墨调暗影
uniform float shadow_threshold : hint_range(0.0, 1.0) = 0.62;
uniform float shadow_softness : hint_range(0.0, 0.2) = 0.02;
uniform float rough : hint_range(0.0, 1.0) = 0.85;
uniform float metal : hint_range(0.0, 1.0) = 0.0;
uniform bool functional_rim = false;
uniform vec3 rim_color : source_color = vec3(0.47, 0.79, 0.64); // 苔薄荷
uniform float rim_strength : hint_range(0.0, 1.0) = 0.4;
uniform float fill : hint_range(0.0, 1.0) = 0.05;
uniform float vcol_strength : hint_range(0.0, 1.0) = 0.55;
uniform bool use_triplanar = false;
uniform float triplanar_scale : hint_range(0.05, 2.0) = 0.28;
uniform bool contact_enabled = true;
uniform float contact_ao : hint_range(0.0, 1.0) = 0.55;
uniform float contact_height : hint_range(0.05, 1.6) = 0.42;
varying vec3 world_pos;
varying float ao_weight;

void vertex() {
	vec4 view_pos = MODELVIEW_MATRIX * vec4(VERTEX, 1.0);
	world_pos = (inverse(VIEW_MATRIX) * view_pos).xyz;
	ao_weight = textureLod(orm_tex, UV, 2.0).r;
}

void fragment() {
	vec2 sample_uv = use_triplanar ? world_pos.xz * triplanar_scale : UV;
	vec3 albedo = texture(albedo_tex, sample_uv).rgb * base_color;
	bool authored_vcol = COLOR.a > 0.51 && (COLOR.r < 0.995 || COLOR.g < 0.995 || COLOR.b < 0.995);
	if (authored_vcol) {
		albedo *= mix(vec3(1.0), COLOR.rgb, vcol_strength);
	}
	vec3 world_n = normalize(mat3(INV_VIEW_MATRIX) * NORMAL);
	float hx = abs(world_n.x);
	float hy = abs(world_n.y);
	float hz = abs(world_n.z);
	float face_mul = 1.0;
	if (hy > 0.72) {
		face_mul = 1.08;
	} else {
		face_mul = mix(0.68, 1.0, smoothstep(0.18, 0.82, hz / max(hx + hz, 0.001)));
	}
	albedo *= face_mul;
	vec4 orm = texture(orm_tex, UV);
	if (contact_enabled) {
		float h_fall = 1.0 - smoothstep(0.0, contact_height, world_pos.y);
		float wall = 1.0 - smoothstep(0.22, 0.78, world_n.y);
		float contact = h_fall * wall * contact_ao;
		albedo *= mix(vec3(1.0), vec3(0.38, 0.37, 0.46), contact);
	}
	ALBEDO = albedo;
	NORMAL_MAP = texture(normal_tex, UV).rgb;
	ROUGHNESS = mix(rough, orm.g, 0.65);
	METALLIC = max(metal, orm.b);
	EMISSION = albedo * fill;
}

void light() {
	float ndl = max(dot(NORMAL, LIGHT), 0.0);
	float in_light = smoothstep(0.45, 1.0, ATTENUATION);
	float nd = ndl * in_light;
	vec3 col;
	if (nd < 0.30) {
		col = ALBEDO * shadow_color * mix(0.78, 1.0, ao_weight);
	} else if (nd < 0.64) {
		col = ALBEDO * vec3(0.70, 0.64, 0.56);
	} else {
		col = ALBEDO;
	}
	if (functional_rim && LIGHT_IS_DIRECTIONAL) {
		float rim = pow(1.0 - abs(dot(NORMAL, VIEW)), 3.0);
		col += rim_color * rim * rim_strength;
	}
	if (LIGHT_IS_DIRECTIONAL) {
		DIFFUSE_LIGHT += col * LIGHT_COLOR;
	} else {
		DIFFUSE_LIGHT += ALBEDO * LIGHT_COLOR * ATTENUATION * 0.10;
	}
}
