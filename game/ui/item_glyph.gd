@tool
extends Control
## Compact monochrome-safe category glyphs for the FR-44 item selector.
## Each family has a different silhouette, so colour is never the only cue.

const INK := Color("17243b")
const FOOD := Color("ffc857")
const DRINK := Color("72b7d9")
const HOME := Color("78c9a4")

var ink_color := INK
var food_color := FOOD
var drink_color := DRINK
var home_color := HOME

var kind := "food":
	set(value):
		kind = value
		queue_redraw()


func _init() -> void:
	custom_minimum_size = Vector2(32, 32)
	mouse_filter = Control.MOUSE_FILTER_IGNORE


func _draw() -> void:
	var center := size * 0.5
	var scale := minf(size.x, size.y) / 32.0
	var width := maxf(2.25, 2.5 * scale)
	match kind:
		"drink":
			_draw_bottle(center, scale, width)
		"home":
			_draw_home_slot(center, scale, width)
		_:
			_draw_food_pod(center, scale, width)


func _draw_food_pod(center: Vector2, scale: float, width: float) -> void:
	var radius := 10.0 * scale
	draw_arc(center + Vector2(-1.0, 0.0) * scale, radius, -2.45, 1.25, 22, food_color, width, true)
	draw_line(center + Vector2(-7.0, 6.0) * scale, center + Vector2(7.0, -4.0) * scale, ink_color, width, true)
	for seed in [Vector2(-3.0, 2.0), Vector2(1.0, -0.5), Vector2(5.0, -3.0)]:
		draw_circle(center + seed * scale, 1.8 * scale, food_color, true)


func _draw_bottle(center: Vector2, scale: float, width: float) -> void:
	var points := PackedVector2Array([
		center + Vector2(-3.0, -11.0) * scale,
		center + Vector2(3.0, -11.0) * scale,
		center + Vector2(3.0, -6.0) * scale,
		center + Vector2(7.0, -2.0) * scale,
		center + Vector2(7.0, 10.0) * scale,
		center + Vector2(-7.0, 10.0) * scale,
		center + Vector2(-7.0, -2.0) * scale,
		center + Vector2(-3.0, -6.0) * scale,
	])
	draw_polyline(points, drink_color, width, true)
	draw_line(points[-1], points[0], drink_color, width, true)
	draw_line(center + Vector2(-5.0, 3.0) * scale, center + Vector2(5.0, 3.0) * scale, ink_color, width, true)


func _draw_home_slot(center: Vector2, scale: float, width: float) -> void:
	var cradle := PackedVector2Array([
		center + Vector2(-10.0, -5.0) * scale,
		center + Vector2(-10.0, 8.0) * scale,
		center + Vector2(10.0, 8.0) * scale,
		center + Vector2(10.0, -5.0) * scale,
	])
	draw_polyline(cradle, home_color, width, true)
	draw_line(center + Vector2(-6.0, 3.0) * scale, center + Vector2(6.0, 3.0) * scale, ink_color, width, true)
	draw_line(center + Vector2(-6.0, -1.0) * scale, center + Vector2(2.0, -8.0) * scale, home_color, width, true)
	draw_line(center + Vector2(2.0, -8.0) * scale, center + Vector2(8.0, -2.0) * scale, home_color, width, true)
