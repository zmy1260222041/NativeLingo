@tool
extends StyleBox
## Art Bible §6.4 panel: silt-ink outline, one folded corner, no four-corner
## modern flat card. The border is drawn as a closed polyline around a cut-corner
## polygon; it is intentionally not StyleBoxFlat so future hand-drawn jitter can
## replace the deterministic line without touching panel layout.

const INK_COLOR := Color("17243b")
const BG_COLOR := Color("111a2be8")
const CUT_SIZE := 16.0
const CONTENT_MARGIN := 18.0


func _init() -> void:
	set_content_margin_all(CONTENT_MARGIN)


func _get_draw_rect(rect: Rect2) -> Rect2:
	if rect.size.x <= CONTENT_MARGIN * 2.0 or rect.size.y <= CONTENT_MARGIN * 2.0:
		return rect
	return Rect2(rect.position + Vector2(CONTENT_MARGIN, CONTENT_MARGIN), rect.size - Vector2(CONTENT_MARGIN * 2.0, CONTENT_MARGIN * 2.0))


func _get_minimum_size() -> Vector2:
	return Vector2(CONTENT_MARGIN * 2.0, CONTENT_MARGIN * 2.0)


func _draw(to_canvas_item: RID, rect: Rect2):
	if rect.size.x <= 1.0 or rect.size.y <= 1.0:
		return
	var cut := minf(CUT_SIZE, minf(rect.size.x * 0.22, rect.size.y * 0.22))
	var top_left := rect.position
	var top_right := rect.position + Vector2(rect.size.x, 0.0)
	var bottom_right := rect.end
	var bottom_left := rect.position + Vector2(0.0, rect.size.y)
	var cut_point := Vector2(rect.end.x - cut, rect.position.y)
	var cut_end := Vector2(rect.end.x, rect.position.y + cut)
	var points := PackedVector2Array([
		top_left,
		Vector2(bottom_left.x, bottom_left.y - 4.0),
		bottom_left,
		Vector2(bottom_right.x - 4.0, bottom_right.y),
		bottom_right,
		cut_end,
		cut_point,
		Vector2(top_left.x + 4.0, top_left.y),
	])
	var bg_colors := PackedColorArray()
	for _index in points.size():
		bg_colors.append(BG_COLOR)
	RenderingServer.canvas_item_add_polygon(to_canvas_item, points, bg_colors)
	var outline := points.duplicate()
	outline.append(points[0])
	var ink_colors := PackedColorArray()
	for _index in outline.size():
		ink_colors.append(INK_COLOR)
	RenderingServer.canvas_item_add_polyline(to_canvas_item, outline, ink_colors, 2.0, true)
