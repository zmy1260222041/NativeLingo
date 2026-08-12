class_name VoiceStatusIcon
extends Control

var state := "idle"

func _ready() -> void:
	custom_minimum_size = Vector2(32, 32)
	mouse_filter = Control.MOUSE_FILTER_IGNORE
	queue_redraw()

func set_state(next_state: String) -> void:
	state = next_state
	visible = state != "idle"
	queue_redraw()

func _draw() -> void:
	var center := size * 0.5
	var color := Color("78c9a4")
	match state:
		"listening":
			_draw_microphone(center, color)
			draw_circle(center + Vector2(10, -9), 3.2, Color("f2a85b"))
		"transcribing":
			color = Color("9a6acb")
			draw_arc(center, 10, 0, TAU, 24, color, 2.5, true)
			draw_line(center, center + Vector2(0, -6), color, 2.5, true)
			draw_line(center, center + Vector2(5, 2), color, 2.5, true)
		"clarify":
			color = Color("f2a85b")
			draw_arc(center + Vector2(0, -2), 9, -2.8, 2.45, 24, color, 2.5, true)
			draw_line(center + Vector2(-5, 6), center + Vector2(-8, 10), color, 2.5, true)
			draw_circle(center + Vector2(0, 7), 1.8, color)
		"unavailable":
			color = Color("f2a85b")
			_draw_microphone(center, color)
			draw_line(center + Vector2(-10, 10), center + Vector2(10, -10), color, 3.0, true)
		"accepted":
			draw_arc(center, 10, 0, TAU, 24, color, 2.5, true)
			draw_polyline(PackedVector2Array([center + Vector2(-6, 0), center + Vector2(-1, 5), center + Vector2(7, -5)]), color, 3.0, true)

func _draw_microphone(center: Vector2, color: Color) -> void:
	draw_arc(center + Vector2(0, -3), 5.5, 0, TAU, 20, color, 2.5, true)
	draw_line(center + Vector2(-8, -1), center + Vector2(-8, 3), color, 2.2, true)
	draw_arc(center + Vector2(0, 2), 8, 0, PI, 16, color, 2.2, true)
	draw_line(center + Vector2(0, 10), center + Vector2(0, 14), color, 2.2, true)
	draw_line(center + Vector2(-5, 14), center + Vector2(5, 14), color, 2.2, true)
