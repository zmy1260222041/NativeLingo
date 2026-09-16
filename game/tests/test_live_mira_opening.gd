extends "res://tests/test_live_novel_speaking.gd"
## Opt-in local service test of restart → dismiss guide → live Mira speech.
## Run in an isolated project user directory, with no microphone or saved progress.
var started := 0
var text_ms := -1
var shown_ms := -1
var audio_ms := -1
var shown_count := 0
var measuring := false

func _ready() -> void:
	GameState.persistence_enabled = false
	GameState.reset_run()
	var screen := preload("res://scenes/Novel.tscn").instantiate()
	screen.boot_from_save = false
	add_child(screen)
	model = screen.model
	model.novel_save_path = "user://mira-opening-test-unused.json"
	# Enable the production opening path only after bypassing save restoration.
	model.boot_from_save = true
	NpcDialogueService.dialogue_ready.connect(func(npc, _reply, text):
		if measuring and npc == "mira":
			text_ms = Time.get_ticks_msec() - started
			reply_text = text)
	NpcDialogueService.dialogue_failed.connect(func(_npc, reason): dialogue_error = reason)
	model.line_changed.connect(func(npc, text):
		if measuring and npc == "mira":
			shown_ms = Time.get_ticks_msec() - started
			shown_count += 1
			check(NpcVoice.audio_player.playing and NpcVoice.playing_npc_id == "mira", "Mira English is first shown while her audio is playing")
			check(text != "Welcome, stranger.", "Guide dismissal cannot reveal an old silent greeting"))
	NpcVoice.line_audio_ready.connect(func(npc, line):
		if measuring and npc == "mira" and line.begins_with("reply-"):
			audio_ms = Time.get_ticks_msec() - started
			var wav := NpcVoice.audio_player.stream as AudioStreamWAV
			check(wav != null and wav.data.size() > 1000 and wav.data.count(0) < wav.data.size(), "Actual service delivers non-silent audio bytes")
			check(screen.text_elapsed == 0.0, "Opening typewriter has not run ahead of the voice"))
	NpcVoice.line_audio_finished.connect(func(npc, line):
		if measuring and npc == "mira" and line.begins_with("reply-"): reply_audio_done = true)
	for attempt in range(2):
		measuring = false
		screen._new_journey()
		check(screen.modal.visible and screen.modal_kind == "guide", "Start over opens the guide")
		started = Time.get_ticks_msec()
		text_ms = -1
		shown_ms = -1
		audio_ms = -1
		shown_count = 0
		dialogue_error = ""
		reply_audio_done = false
		measuring = true
		screen._close_panel()
		check(screen.dialogue_text.text == "正在准备开场语音…", "Guide dismissal visibly waits for voice preparation")
		await until(func(): return reply_audio_done or not dialogue_error.is_empty(), 60.0)
		check(reply_audio_done and dialogue_error.is_empty(), "Live opening finishes without an audio error")
		check(shown_count == 1 and shown_ms >= text_ms and absi(shown_ms - audio_ms) <= 20, "Exactly one opening appears in sync with playback")
		check(model.recording_block_reason().is_empty(), "Recording is available after the opening")
		print("LIVE_MIRA_OPENING attempt=", attempt, " text_ms=", text_ms, " shown_ms=", shown_ms, " audio_ms=", audio_ms, " text=", reply_text)
	measuring = false
	model.cancel_activity()
	screen.queue_free()
	await get_tree().process_frame
	print("LiveMiraOpeningTest failures=", failures)
	get_tree().quit(1 if failures else 0)
