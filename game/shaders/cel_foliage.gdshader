// Soft foliage: authored spherical normals, anchored wind, neutral map fallbacks.
shader_type spatial;
render_mode diffuse_lambert_wrap, specular_schlick_ggx, cull_back;
uniform sampler2D albedo_tex : source_color, hint_default_white;
uniform sampler2D normal_tex : hint_normal, filter_linear_mipmap;
uniform sampler2D orm_tex : hint_default_white, filter_linear_mipmap;
uniform vec3 base_color : source_color = vec3(1.0);
uniform float rough = 0.88;
uniform float metal = 0.0;
uniform float orm_strength = 0.0;
uniform float fill = 0.0;
uniform float vcol_strength = 1.0;
uniform float sway_amp = 0.035;
uniform float canopy_height = 4.0;
uniform float phase_offset = 0.0;
void vertex() {
	float h = clamp(VERTEX.y / canopy_height, 0.0, 1.0);
	float phase = TIME * 1.7 + VERTEX.x * 0.6 + VERTEX.z * 0.8 + phase_offset;
	VERTEX.x += sin(phase) * sway_amp * h * h;
	VERTEX.z += cos(phase * 0.83 + 1.3) * sway_amp * h * h * 0.6;
}
void fragment() {
	ALBEDO = texture(albedo_tex, UV).rgb * base_color * mix(vec3(1.0), COLOR.rgb, vcol_strength);
	NORMAL_MAP = texture(normal_tex, UV).rgb;
	vec3 orm = texture(orm_tex, UV).rgb;
	ROUGHNESS = mix(rough, orm.g, orm_strength);
	METALLIC = 0.0;
	SPECULAR = 0.12;
	AO = mix(1.0, orm.r, orm_strength * 0.5);
	EMISSION = ALBEDO * fill;
}
