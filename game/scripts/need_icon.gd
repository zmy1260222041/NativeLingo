class_name NeedIcon
extends Control

@export_enum("food", "warmth", "energy") var kind := "food":
	set(value):
		kind = value
		queue_redraw()

var icon_color := Color("e7d2a3")

func _ready() -> void:
	custom_minimum_size = Vector2(28, 28)
	mouse_filter = Control.MOUSE_FILTER_IGNORE
	queue_redraw()

func set_tone(color: Color) -> void:
	icon_color = color
	queue_redraw()

func _draw() -> void:
	var center := size * 0.5
	match kind:
		"warmth":
			_draw_heat_bands(center)
		"energy":
			_draw_forward_fold(center)
		_:
			_draw_open_seed(center)

func _draw_open_seed(center: Vector2) -> void:
	draw_arc(center + Vector2(-1, 1), 8.5, -2.35, 1.0, 18, icon_color, 2.5, true)
	draw_arc(center + Vector2(1, 1), 8.5, 2.15, 5.5, 18, icon_color, 2.5, true)
	draw_line(center + Vector2(-1, 7), center + Vector2(5, -6), icon_color, 2.2, true)
	draw_circle(center + Vector2(3, -2), 2.2, icon_color)

func _draw_heat_bands(center: Vector2) -> void:
	for index in range(3):
		var y := center.y + 7.0 - float(index) * 6.0
		var points := PackedVector2Array([
			Vector2(center.x - 9, y),
			Vector2(center.x - 5, y - 2),
			Vector2(center.x - 1, y),
			Vector2(center.x + 3, y - 2),
			Vector2(center.x + 8, y),
		])
		draw_polyline(points, icon_color, 2.2, true)

func _draw_forward_fold(center: Vector2) -> void:
	var outer := PackedVector2Array([
		center + Vector2(-9, -7),
		center + Vector2(8, 0),
		center + Vector2(-9, 7),
		center + Vector2(-4, 0),
	])
	draw_colored_polygon(outer, icon_color)
	var cut := PackedVector2Array([
		center + Vector2(-4, -3),
		center + Vector2(2, 0),
		center + Vector2(-4, 3),
	])
	draw_colored_polygon(cut, Color("17243b"))
