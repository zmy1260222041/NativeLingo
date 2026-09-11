// Environment v1.7: soft diffuse and material-family highlights.
shader_type spatial;
render_mode diffuse_burley, specular_schlick_ggx, cull_back;
uniform sampler2D albedo_tex : source_color, hint_default_white, filter_linear_mipmap;
uniform sampler2D normal_tex : hint_normal, filter_linear_mipmap;
uniform sampler2D orm_tex : hint_default_white, filter_linear_mipmap;
uniform sampler2D ao_tex : hint_default_white, filter_linear_mipmap;
uniform vec3 base_color : source_color = vec3(1.0);
uniform vec3 shadow_color : source_color = vec3(0.30, 0.36, 0.48);
uniform float shadow_threshold = 0.62;
uniform float shadow_softness = 0.02;
uniform bool soft_surface = false;
uniform float rough = 0.85;
uniform float metal = 0.0;
uniform float specular_strength = 0.22;
uniform float normal_strength = 1.0;
uniform float orm_strength = 0.0;
uniform float orm_rough_factor = 1.0;
uniform float orm_metal_factor = 1.0;
uniform bool separate_ao = false;
uniform bool functional_rim = false;
uniform vec3 rim_color : source_color = vec3(0.47, 0.79, 0.64);
uniform float rim_strength = 0.4;
uniform float fill = 0.0;
uniform float heat_glow = 0.0;
uniform float vcol_strength = 0.55;
uniform bool use_triplanar = false;
uniform float triplanar_scale = 0.28;
uniform bool contact_enabled = true;
uniform float contact_ao = 0.32;
uniform float contact_height = 0.32;
varying vec3 world_pos;
varying vec3 local_pos;
varying float surface_rough;
varying float surface_metal;
void vertex() {
	world_pos = (MODEL_MATRIX * vec4(VERTEX, 1.0)).xyz;
	local_pos = VERTEX;
}
void fragment() {
	vec2 tex_uv = use_triplanar ? world_pos.xz * triplanar_scale : UV;
	vec3 albedo = texture(albedo_tex, tex_uv).rgb * base_color;
	albedo *= mix(vec3(1.0), COLOR.rgb, vcol_strength);
	vec3 orm = texture(orm_tex, UV).rgb;
	float occlusion = mix(1.0, orm.r, orm_strength);
	if (separate_ao) { occlusion = texture(ao_tex, UV).r; }
	vec3 world_n = normalize(mat3(INV_VIEW_MATRIX) * NORMAL);
	if (contact_enabled) {
		float base = (1.0 - smoothstep(0.0, contact_height, world_pos.y)) *
			(1.0 - smoothstep(0.25, 0.8, world_n.y));
		albedo *= 1.0 - base * contact_ao;
	}
	ALBEDO = albedo;
	NORMAL_MAP = texture(normal_tex, UV).rgb;
	NORMAL_MAP_DEPTH = normal_strength;
	surface_rough = clamp(mix(rough, orm.g * orm_rough_factor, orm_strength), 0.30, 1.0);
	surface_metal = clamp(mix(metal, orm.b * orm_metal_factor, orm_strength), 0.0, 0.8);
	ROUGHNESS = surface_rough;
	METALLIC = surface_metal;
	SPECULAR = specular_strength;
	AO = mix(1.0, occlusion, 0.60);
	AO_LIGHT_AFFECT = 0.35;
	EMISSION = albedo * fill;
	float heat_region = smoothstep(1.25, 1.31, local_pos.y) * (1.0 - smoothstep(0.23, 0.34, length(local_pos.xz)));
	EMISSION += vec3(1.0, 0.24, 0.055) * heat_glow * heat_region;
}
void light() {
	float ndl = max(dot(NORMAL, LIGHT), 0.0);
	if (soft_surface) {
		float diffuse = ndl * (1.0 - surface_metal * 0.45);
		DIFFUSE_LIGHT += ALBEDO * LIGHT_COLOR * ATTENUATION * diffuse / PI;
		vec3 halfway = normalize(LIGHT + VIEW);
		float exponent = mix(90.0, 4.0, surface_rough * surface_rough);
		float lobe = pow(max(dot(NORMAL, halfway), 0.0), exponent);
		vec3 reflection = mix(vec3(0.10), ALBEDO * 0.6, surface_metal);
		SPECULAR_LIGHT += reflection * LIGHT_COLOR * ATTENUATION * ndl * lobe *
			specular_strength * (exponent + 2.0) / (8.0 * PI);
	} else {
		float nd = ndl * smoothstep(0.45, 1.0, ATTENUATION);
		vec3 tone = nd < 0.30 ? shadow_color : (nd < 0.64 ? vec3(0.70, 0.64, 0.56) : vec3(1.0));
		DIFFUSE_LIGHT += ALBEDO * tone * LIGHT_COLOR * (LIGHT_IS_DIRECTIONAL ? 1.0 : ATTENUATION * 0.10);
	}
	if (functional_rim && LIGHT_IS_DIRECTIONAL) {
		DIFFUSE_LIGHT += rim_color * pow(1.0 - abs(dot(NORMAL, VIEW)), 3.0) * rim_strength * ATTENUATION;
	}
}
