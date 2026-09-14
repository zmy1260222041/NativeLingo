extends Control
## Campus illustrations share the town's painted backgrounds and outlined cast.
## Explicit texture dependencies include the complete cast in desktop exports.
const Palette := preload("res://scripts/novel/novel_palette.gd")
const BACKGROUNDS := {
	"class": preload("res://assets/novel/campus/class.png"),
	"study": preload("res://assets/novel/campus/study.png"),
	"club": preload("res://assets/novel/campus/club.png"),
	"dining": preload("res://assets/novel/campus/dining.png"),
	"sports": preload("res://assets/novel/campus/sports.png"),
	"home": preload("res://assets/novel/campus/home.png"),
}
const PORTRAITS := {
	"alex": preload("res://assets/novel/campus/alex.png"),
	"maya": preload("res://assets/novel/campus/maya.png"),
	"jules": preload("res://assets/novel/campus/jules.png"),
	"sam": preload("res://assets/novel/campus/sam.png"),
	"riley": preload("res://assets/novel/campus/riley.png"),
	"casey": preload("res://assets/novel/campus/casey.png"),
	"prof_chen": preload("res://assets/novel/campus/prof_chen.png"),
	"tavi": preload("res://assets/novel/campus/tavi.png"),
}
var place := "class"
var people: Array = []
var active := ""
var evening := false

func _ready() -> void:
	mouse_filter = Control.MOUSE_FILTER_IGNORE
	clip_contents = true
	resized.connect(queue_redraw)
	texture_filter = CanvasItem.TEXTURE_FILTER_LINEAR_WITH_MIPMAPS

func portrait_rect(index: int, count: int) -> Rect2:
	# Coordinates are local to the stage, 88px below the shared header.
	# Faces remain above the dialogue and to the right of the situation card.
	if count == 1: return Rect2(865, 78, 475, 660)
	if count == 2: return Rect2(745 + index * 320, 95, 380, 610)
	return Rect2(700 + index * 216, 105, 300, 570)

func _draw() -> void:
	var background: Texture2D = BACKGROUNDS.get(place, BACKGROUNDS["class"])
	var factor := maxf(size.x / background.get_width(), size.y / background.get_height())
	var source_size := size / factor
	var source := Rect2((background.get_size() - source_size) * 0.5, source_size)
	var light := Color("c6cbce") if evening else Color.WHITE
	draw_texture_rect_region(background, Rect2(Vector2.ZERO, size), source, light)
	draw_rect(Rect2(Vector2.ZERO, size), Color(Palette.SURFACE, 0.08))
	var stage_scale := size / Vector2(1440, 812)
	for i in range(people.size()):
		var id := str(people[i])
		if not PORTRAITS.has(id): continue
		var portrait: Texture2D = PORTRAITS[id]
		var slot := portrait_rect(i, people.size())
		var fit := minf(slot.size.x / portrait.get_width(), slot.size.y / portrait.get_height())
		var fitted := portrait.get_size() * fit
		var destination := Rect2(slot.position + Vector2((slot.size.x - fitted.x) * 0.5, 0), fitted)
		destination.position *= stage_scale
		destination.size *= stage_scale
		var tint := Color.WHITE if active.is_empty() or active == id or not people.has(active) else Color("c6cbce")
		draw_texture_rect(portrait, destination, false, tint)
