class_name NeedMeter
extends Control

@export_enum("food", "warmth", "energy") var kind := "food":
	set(new_kind):
		kind = new_kind
		queue_redraw()

var need_value := 100.0
var reduce_motion := false
var displayed_value := 100.0

func _ready() -> void:
	custom_minimum_size = Vector2(240, 18)
	mouse_filter = Control.MOUSE_FILTER_IGNORE
	queue_redraw()

func set_need(value: float, motion_reduced := false) -> void:
	need_value = clampf(value, 0.0, 100.0)
	reduce_motion = motion_reduced
	if reduce_motion:
		displayed_value = need_value
		queue_redraw()
	else:
		var tween := create_tween()
		tween.tween_method(_set_displayed_value, displayed_value, need_value, 0.18).set_trans(Tween.TRANS_CUBIC).set_ease(Tween.EASE_OUT)

func _set_displayed_value(value: float) -> void:
	displayed_value = value
	queue_redraw()

func _draw() -> void:
	var outline := Color("9ba9be")
	draw_rect(Rect2(Vector2.ZERO, size), Color("17243b"), true)
	draw_rect(Rect2(Vector2.ONE, size - Vector2(2, 2)), outline, false, 2.0)
	var gap := 3.0
	var inner := Rect2(4, 4, maxf(0.0, size.x - 8.0), maxf(0.0, size.y - 8.0))
	var segment_width := (inner.size.x - gap * 9.0) / 10.0
	var filled_count := int(ceil(displayed_value / 10.0))
	var active_color := _tone_color(displayed_value)
	for index in range(10):
		var x := inner.position.x + float(index) * (segment_width + gap)
		var rect := Rect2(x, inner.position.y, segment_width, inner.size.y)
		_draw_segment(rect, index, active_color if index < filled_count else Color("42516b"))

func _draw_segment(rect: Rect2, index: int, color: Color) -> void:
	match kind:
		"warmth":
			var lift := float(index % 3) * 0.7
			var points := PackedVector2Array([
				Vector2(rect.position.x, rect.end.y),
				Vector2(rect.position.x + 2.0, rect.position.y + lift),
				Vector2(rect.end.x, rect.position.y),
				Vector2(rect.end.x - 2.0, rect.end.y - lift),
			])
			draw_colored_polygon(points, color)
		"energy":
			var notch := minf(4.0, rect.size.x * 0.34)
			var points := PackedVector2Array([
				Vector2(rect.position.x, rect.position.y),
				Vector2(rect.end.x - notch, rect.position.y),
				Vector2(rect.end.x, rect.get_center().y),
				Vector2(rect.end.x - notch, rect.end.y),
				Vector2(rect.position.x, rect.end.y),
				Vector2(rect.position.x + notch, rect.get_center().y),
			])
			draw_colored_polygon(points, color)
		_:
			var notch := minf(3.0, rect.size.x * 0.28)
			var points := PackedVector2Array([
				Vector2(rect.position.x + notch, rect.position.y),
				Vector2(rect.end.x, rect.position.y),
				Vector2(rect.end.x - notch, rect.end.y),
				Vector2(rect.position.x, rect.end.y),
			])
			draw_colored_polygon(points, color)

func _tone_color(value: float) -> Color:
	if value <= 25.0:
		return Color("ff8b7f")
	if value <= 50.0:
		return Color("f2a85b")
	return Color("78c9a4")
