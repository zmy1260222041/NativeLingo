extends SceneTree
## Opt-in live local TTS check. Does not read or write player progress.
var heard: Array[String] = []
var failures := 0

func _initialize() -> void:
	call_deferred("_run")

func _run() -> void:
	var game = root.get_node("GameState")
	game.persistence_enabled = false
	game.reset_run()
	var voice = root.get_node("NpcVoice")
	voice.availability_override = true
	voice.line_audio_ready.connect(func(npc, line):
		var player = voice.audio_player
		var wav = player.stream as AudioStreamWAV
		if player.playing and wav != null and wav.data.size() > 1000:
			heard.append(npc)
			print("LIVE_OPENING_PLAYING npc=", npc, " line=", line, " bytes=", wav.data.size())
		else:
			failures += 1
			push_error("Audio not playing: " + npc))
	var screen = load("res://scenes/Novel.tscn").instantiate()
	screen.boot_from_save = false
	root.add_child(screen)
	for place in ["food", "store", "parts", "neighbor", "plaza"]:
		var count := heard.size()
		screen.model.travel(place)
		var deadline := Time.get_ticks_msec() + 15000
		while heard.size() == count and Time.get_ticks_msec() < deadline:
			await create_timer(0.1).timeout
		if heard.size() == count:
			failures += 1
			push_error("Opening timed out: " + place)
		if heard.size() > count:
			await create_timer(0.15).timeout
			var before: float = voice.audio_player.get_playback_position()
			var stream = voice.audio_player.stream
			screen._refresh_record_button()
			if not screen.record_button.disabled:
				failures += 1
				push_error("Live playback leaves the record button enabled")
			for attempt in range(3):
				screen.record_button.pressed.emit()
				var key := InputEventAction.new()
				key.action = "push_to_talk"
				key.pressed = true
				screen._unhandled_input(key)
			await create_timer(0.1).timeout
			if voice.audio_player.stream != stream or voice.audio_player.get_playback_position() < before or heard.size() != count + 1 or root.get_node("SpeechAdapter").is_recording():
				failures += 1
				push_error("Recording input interrupted or restarted live opening: " + place)
			else:
				print("LIVE_RECORD_CONFLICT_GUARD_PASS place=", place)
		while screen.model._listening and Time.get_ticks_msec() < deadline:
			await create_timer(0.1).timeout
	print("LIVE_OPENING_RESULT voices=", heard.size(), " failures=", failures)
	quit(0 if failures == 0 and heard.size() == 5 else 1)
