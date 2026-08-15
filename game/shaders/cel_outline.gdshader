// cel_outline.gdshader — inverted-hull 卡通描边（art-bible §3.1.B）
//
// - cull_front 只画背面，VERTEX 沿 NORMAL 外扩 outline_width，形成"描边壳"
// - unshaded 纯色，颜色 = 淤泥墨 #17243B
// - 宽度标定：§1.5 机位（5.5m / 68° / 1440×900）下 ~1.5px（5.5m 处 1px≈5.1mm）
// - 距离关闭：描边是独立子 MeshInstance3D，由 env_lod.gd 在 12m 处 .visible=false
//   （§3.1.B"远景可关闭，关闭后主形仍须成立"）
// - 不投影、深度常写，避免与主体 Z-fighting
shader_type spatial;
render_mode unshaded, cull_front, depth_draw_always, shadows_disabled;

uniform vec3 outline_color : source_color = vec3(0.09, 0.141, 0.231); // #17243B
uniform float outline_width : hint_range(0.0, 0.1) = 0.016;
// 可选风摆：与 cel_foliage.gdshader 逐字同式，保证树冠描边壳不与摆动的
// 树冠分离（§3.7.A）。默认 0 = 静止（建筑与道具描边不受影响）。
uniform float sway_amp : hint_range(0.0, 0.2) = 0.0;
uniform float canopy_height : hint_range(0.5, 10.0) = 4.0;
uniform float phase_offset : hint_range(0.0, 100.0) = 0.0;

void vertex() {
	VERTEX += NORMAL * outline_width;
	if (sway_amp > 0.0) {
		float h = clamp(VERTEX.y / canopy_height, 0.0, 1.0);
		float k = sway_amp * h * h;
		float phase = TIME * 1.7 + VERTEX.x * 0.6 + VERTEX.z * 0.8 + phase_offset;
		VERTEX.x += sin(phase) * k;
		VERTEX.z += cos(phase * 0.83 + 1.3) * k * 0.6;
	}
}

void fragment() {
	ALBEDO = outline_color;
}
