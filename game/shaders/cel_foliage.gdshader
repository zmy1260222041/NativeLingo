// cel_foliage.gdshader — 植被 cel 着色 + 风动（art-bible §3.6 活体生态 / §5.4 / §3.7.A）
//
// 在 cel_base 的两段量化光照之上叠加顶点风摆：
//  - 振幅随高度增加（h = VERTEX.y / canopy_height 归一，h² 放大），根部固定
//  - 相位按顶点位置错开，整片树冠波浪而非刚体摇摆
//  - 振幅很小（默认 0.035 m），只提供"世界活着"的次级运动，不抢动作剪影
// 其余光照 / 顶点色 / 家族规则与 cel_base 完全一致（§3.1.B）。
shader_type spatial;
render_mode diffuse_burley, specular_disabled, cull_back, ambient_light_disabled;

uniform sampler2D albedo_tex : source_color, hint_default_white;
uniform sampler2D normal_tex : hint_normal, filter_linear_mipmap;
uniform sampler2D orm_tex : hint_default_white, filter_linear_mipmap;
uniform vec3 base_color : source_color = vec3(1.0);
uniform vec3 shadow_color : source_color = vec3(0.14, 0.16, 0.24); // 淤泥墨调冷暗影（§3.7.C）
uniform float shadow_threshold : hint_range(0.0, 1.0) = 0.62;
uniform float shadow_softness : hint_range(0.0, 0.2) = 0.02;
uniform float rough : hint_range(0.0, 1.0) = 0.85;
uniform float metal : hint_range(0.0, 1.0) = 0.0;
uniform float fill : hint_range(0.0, 1.0) = 0.05;
uniform float vcol_strength : hint_range(0.0, 1.0) = 0.55;
uniform float sway_amp : hint_range(0.0, 0.2) = 0.035;
uniform float canopy_height : hint_range(0.5, 10.0) = 4.0;
uniform float phase_offset : hint_range(0.0, 100.0) = 0.0;

void vertex() {
	float h = clamp(VERTEX.y / canopy_height, 0.0, 1.0);
	float k = sway_amp * h * h;
	// 每实例 phase_offset 错开相位，整片树冠成波浪而非刚体摇摆
	float phase = TIME * 1.7 + VERTEX.x * 0.6 + VERTEX.z * 0.8 + phase_offset;
	VERTEX.x += sin(phase) * k;
	VERTEX.z += cos(phase * 0.83 + 1.3) * k * 0.6;
}

void fragment() {
	vec3 albedo = texture(albedo_tex, UV).rgb * base_color;
	bool authored_vcol = COLOR.a > 0.51 && (COLOR.r < 0.995 || COLOR.g < 0.995 || COLOR.b < 0.995);
	if (authored_vcol) {
		albedo *= mix(vec3(1.0), COLOR.rgb, vcol_strength);
	}
	vec4 orm = texture(orm_tex, UV);
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
		col = ALBEDO * shadow_color;
	} else if (nd < 0.64) {
		col = ALBEDO * vec3(0.70, 0.64, 0.56);
	} else {
		col = ALBEDO;
	}
	if (LIGHT_IS_DIRECTIONAL) {
		DIFFUSE_LIGHT += col * LIGHT_COLOR;
	} else {
		DIFFUSE_LIGHT += ALBEDO * LIGHT_COLOR * ATTENUATION * 0.10;
	}
}
