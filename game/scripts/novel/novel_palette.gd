extends RefCounted
## FR-47: warm paper, botanical greens and quiet brass, shared by all 2D panels.
const SURFACE := Color("f3efe5")
const SURFACE_RAISED := Color("faf6ee")
const SURFACE_INSET := Color("e9e7dc")
const TEXT := Color("38433c")
const MUTED := Color("626c61")
const ACCENT := Color("80664c")
const POSITIVE := Color("496b59")
const BORDER := Color("d2d4c6")
const SELECTED := Color("dce4d6")
const HOVER := Color("e2e8dc")
const PRESSED := Color("d4dfcd")
const PRIMARY := Color("59705e")
const PRIMARY_HOVER := Color("4e6554")
const PRIMARY_PRESSED := Color("435b49")
const ON_PRIMARY := Color("faf6ee")
const FOCUS := Color("647a60")
const DISABLED := Color("e5e3da")
const ON_DISABLED := Color("85897d")
const SHADOW := Color("394036")
const ON_SCENE := Color("fff7e8")
const SALIENCE := Color("a14e48")
const FOOD := Color("a07c57")
const DRINK := Color("638078")
const HOME := Color("708162")
const NEED_FOOD := Color("b29470")
const NEED_WARMTH := Color("b38f84")
const NEED_ENERGY := Color("889d83")
## The 2D chapters are written for Chinese-native learners; English stays the
## language NPCs speak, never the language of the interface.
const UI_LOCALE := "zh_CN"
## P2-06: reading text is at least 18 canvas px (about 14 px at 1152×720). The
## shared large-text setting scales every reading surface by the same factor.
const LARGE_TEXT_SCALE := 1.15
static var text_scale := 1.0
const UI_FONT := preload("res://assets/fonts/NotoSansSC-Variable.ttf")
const STORY_FONT := preload("res://assets/fonts/NotoSerifSC-Variable.ttf")

static func font(story := false, weight := 400.0) -> FontVariation:
	var result := FontVariation.new()
	result.base_font = STORY_FONT if story else UI_FONT
	result.variation_opentype = {TextServerManager.get_primary_interface().name_to_tag("wght"): weight}
	return result

static func text_px(size_px: int) -> int:
	return roundi(size_px * text_scale)

## P1-16 / P2-14: the CJK fonts draw ’ and ‘ full-width ("TAVI’ S", "I’ m"). English
## shown to the player, authored or from the model, uses the ASCII apostrophe.
static func plain_quotes(text: String) -> String:
	return text.replace("’", "'").replace("‘", "'")

static func style(fill: Color, border := Color.TRANSPARENT, width := 0, radius := 6) -> StyleBoxFlat:
	var result := StyleBoxFlat.new()
	result.bg_color = fill
	result.border_color = border
	result.set_border_width_all(width)
	result.set_corner_radius_all(radius)
	return result

static func primary(button: Button) -> void:
	for entry in [["normal", PRIMARY], ["hover", PRIMARY_HOVER], ["pressed", PRIMARY_PRESSED]]:
		var surface := style(entry[1], Color.TRANSPARENT, 0, 4)
		surface.content_margin_left = 16
		surface.content_margin_right = 16
		button.add_theme_stylebox_override(entry[0], surface)
	for state in ["font_color", "font_hover_color", "font_pressed_color", "font_focus_color"]:
		button.add_theme_color_override(state, ON_PRIMARY)
	# Inset paper ring stays visible on a green primary action.
	var focus := style(Color.TRANSPARENT, ON_PRIMARY, 2, 3)
	focus.expand_margin_left = -4
	focus.expand_margin_right = -4
	focus.expand_margin_top = -4
	focus.expand_margin_bottom = -4
	button.add_theme_stylebox_override("focus", focus)

static func button_style(fill: Color, border: Color) -> StyleBoxFlat:
	var result := style(fill, border, 0, 4)
	result.border_width_bottom = 1
	result.content_margin_left = 16
	result.content_margin_right = 16
	return result

static func quiet(button: Button) -> void:
	for state in ["font_color", "font_hover_color", "font_pressed_color", "font_focus_color"]:
		button.add_theme_color_override(state, TEXT)
	for entry in [["normal", Color.TRANSPARENT], ["hover", HOVER], ["pressed", PRESSED]]:
		var surface := style(entry[1], Color.TRANSPARENT, 0, 3)
		surface.content_margin_left = 12
		surface.content_margin_right = 12
		button.add_theme_stylebox_override(entry[0], surface)

static func navigation(button: Button, selected: bool, tab := false) -> void:
	for entry in [["normal", SELECTED if selected else Color.TRANSPARENT], ["hover", HOVER], ["pressed", PRESSED]]:
		var surface := style(entry[1], FOCUS, 0, 3)
		surface.content_margin_left = 16
		surface.content_margin_right = 16
		if selected:
			if tab: surface.border_width_bottom = 2
			else: surface.border_width_left = 2
		button.add_theme_stylebox_override(entry[0], surface)
