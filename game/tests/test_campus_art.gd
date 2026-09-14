extends Node
## Real renderer evidence; no model requests or player-save writes.
const Screen := preload("res://scenes/Campus.tscn")
const Town := preload("res://scenes/Novel.tscn")
const Visual := preload("res://scripts/novel/campus_visual.gd")
const OUTPUT := "res://../docs/reviews/campus_art_2026-09-12"
var failures := 0

func check(ok: bool, message: String) -> void:
	if not ok:
		failures += 1
		push_error(message)

func _ready() -> void:
	TranslationServer.set_locale("zh_CN")
	GameState.persistence_enabled = false
	SpeechAdapter.availability_override = false
	NpcVoice.availability_override = false
	for id in Visual.PORTRAITS:
		if "--backgrounds-only" in OS.get_cmdline_user_args(): break
		var texture: Texture2D = Visual.PORTRAITS[id]
		var source: Image = texture.get_image()
		if source.is_compressed(): source.decompress()
		check(source.get_pixel(0, 0).a == 0.0, id + " must have a transparent outer background")
		check(source.get_pixel(source.get_width() / 2, source.get_height() / 2).a > 0.9, id + " must retain opaque character artwork")
	var screen := Screen.instantiate()
	screen.boot_from_save = false
	add_child(screen)
	get_window().size = Vector2i(1440, 900)
	for place in Visual.BACKGROUNDS:
		screen.model.travel(place)
		await capture("location-" + place)
		check(screen.visual.place == place, "Correct illustrated location: " + place)
	screen.model.travel("class")
	screen.model.select_scene("class_project_roles")
	screen._line("jules", "Let's make sure each of us has a part we feel comfortable with. What would you like to take on?")
	screen.instant_text = true
	await capture("group-1440")
	check(screen.visual.people.size() == 3, "Three distinct people on the classroom stage")
	for id in Visual.PORTRAITS:
		screen.visual.people = [id]
		screen.visual.active = id
		screen.visual.queue_redraw()
		await capture("portrait-" + id)
	screen.model.travel("sports")
	screen.model.select_scene("sports_mistake")
	screen.transcript.add_theme_font_size_override("normal_font_size", 30)
	screen._line("casey", "I saw it differently, but I could have missed the first part. Could we talk through what happened before we decide how to continue? I would rather agree on a fair way forward than argue over who was right.")
	for dimensions in [Vector2i(960, 640), Vector2i(1152, 720)]:
		get_window().size = dimensions
		await capture("long-dialogue-%d" % dimensions.x)
		check(screen.record_button.get_global_rect().end.y <= screen.size.y, "Recording control fits small window")
	get_window().size = Vector2i(1440, 900)
	screen.model.travel("home")
	GameState.day_time = GameState.DAY_DURATION * (20.0 - GameState.DAY_START_HOUR) / (GameState.DAY_END_HOUR - GameState.DAY_START_HOUR)
	screen._refresh()
	# Use the presentation flag directly too: this fixture does not settle an activity.
	screen.visual.evening = true
	screen.visual.queue_redraw()
	await capture("home-evening")
	screen.queue_free()
	await get_tree().process_frame
	var town := Town.instantiate()
	town.boot_from_save = false
	add_child(town)
	await capture("town-reference")
	town.queue_free()
	await get_tree().process_frame
	print("CampusArtTest (%s): %d failures" % ["backgrounds-only; portraits NOT accepted" if "--backgrounds-only" in OS.get_cmdline_user_args() else "full artwork", failures])
	get_tree().quit(1 if failures else 0)

func capture(name: String) -> void:
	if DisplayServer.get_name() == "headless": return
	await get_tree().process_frame
	await get_tree().process_frame
	await RenderingServer.frame_post_draw
	DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(OUTPUT))
	get_viewport().get_texture().get_image().save_png(OUTPUT + "/" + ("wip-" if "--backgrounds-only" in OS.get_cmdline_user_args() else "") + name + ".png")
