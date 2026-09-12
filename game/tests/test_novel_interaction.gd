extends Node
## FR-46/47: conflicting actions and modal lifecycle; isolated from player saves.
var failures := 0
var screen: Control
var model: Node

func check(value: bool, message: String) -> void:
	if not value:
		failures += 1
		push_error(message)

func _ready() -> void:
	TranslationServer.set_locale("zh_CN")
	GameState.persistence_enabled = false
	GameState.reset_run()
	SpeechAdapter.availability_override = false
	NpcVoice.availability_override = false
	screen = preload("res://scenes/Novel.tscn").instantiate()
	screen.boot_from_save = false
	add_child(screen)
	model = screen.model
	if "--interaction-playtest" in OS.get_cmdline_user_args():
		get_window().title = "Stranger 2D · Interaction playtest (no saves)"
		return
	await get_tree().process_frame
	for kind in ["bag", "growth", "settings", "history"]:
		model.begin_practice("food")
		screen._open_panel(kind)
		screen._close_panel()
		check(model.practice_word.is_empty(), "%s cancels practice consistently" % kind)
		check(screen.role_label.text == model.Content.place(model.location).role, "%s restores the location role" % kind)
		check(not buttons_contain("结束练习"), "%s removes obsolete practice actions" % kind)
		check(screen.dialogue_text.text == model.Content.place(model.location).opening, "%s restores location dialogue" % kind)
	# A detached button can still deliver an already queued pressed callback.
	screen._open_panel("theater")
	var old_button: Button
	for child in screen.modal_body.get_children():
		if child is Button:
			old_button = child
			break
	screen._close_panel()
	old_button.pressed.emit()
	check(model.social_index == -1, "Closed modal buttons cannot start a scene")
	# The reveal action must complete immediately, even with two calls in one frame.
	model.play_social(0)
	screen.instant_text = false
	screen.reduce_motion = false
	screen._process(0.0)
	screen._advance()
	check(screen.dialogue_text.visible_characters == -1, "Reveal updates the text immediately")
	screen._advance()
	check(model.social_line == 1, "Next click after reveal advances exactly one line")
	model.cancel_activity()
	model.start(false)
	# Real playback state: repeated talk/gesture/replay must not replace the stream.
	var audio := AudioStreamWAV.new()
	audio.format = AudioStreamWAV.FORMAT_16_BITS
	audio.mix_rate = 24000
	var samples := PackedByteArray()
	samples.resize(24000 * 2 * 3)
	audio.data = samples
	NpcVoice.audio_player.stream = audio
	NpcVoice.playing_npc_id = model.npc_id()
	NpcVoice.playing_line_id = "interaction-test"
	NpcVoice.audio_player.play()
	model._replay = {"npc": model.npc_id(), "line": "interaction-test", "options": []}
	var before := GameState.items.snapshot()
	for i in range(3):
		model.talk()
		model.greet()
		model.listen_again()
	check(NpcVoice.audio_player.playing and NpcVoice.audio_player.stream == audio, "Conflicting buttons preserve active playback")
	check(NpcVoice.playing_line_id == "interaction-test", "Repeated replay does not restart the line")
	check(GameState.items.snapshot() == before, "Busy gestures cannot issue rewards")
	screen._refresh_record_button()
	check(screen.talk_button.disabled and screen.gesture_button.disabled and screen.replay_button.disabled, "All conflicting visible actions explain their disabled state")
	model.cancel_activity()
	for pending in ["line", "reply"]:
		if pending == "line": NpcVoice.pending_line_id = "interaction-pending"
		else: NpcVoice.pending_reply_id = "interaction-pending"
		model.talk()
		model.greet()
		model.listen_again()
		check(NpcVoice.pending_line_id == "interaction-pending" or NpcVoice.pending_reply_id == "interaction-pending", "Actions preserve pending %s audio" % pending)
		model.cancel_activity()
	# Feed an isolated silent bus into the recording effect; never open a microphone.
	var original_effect = SpeechAdapter.record_effect
	var bus := AudioServer.bus_count
	AudioServer.add_bus()
	AudioServer.set_bus_name(bus, "InteractionTest")
	AudioServer.set_bus_mute(bus, true)
	SpeechAdapter.record_effect = AudioEffectRecord.new()
	AudioServer.add_bus_effect(bus, SpeechAdapter.record_effect)
	var source := AudioStreamPlayer.new()
	source.bus = "InteractionTest"
	source.stream = audio
	add_child(source)
	source.play()
	await get_tree().create_timer(0.1).timeout
	SpeechAdapter.availability_override = true
	model.record()
	check(SpeechAdapter.is_recording(), "Isolated recording starts")
	for attempt in range(3):
		model.talk()
		model.greet()
		model.listen_again()
	check(SpeechAdapter.is_recording(), "Talk, gesture and replay do not discard the player's recording")
	screen._refresh_record_button()
	check(not screen.record_button.disabled and screen.record_button.text.contains("结束录音"), "Stop recording remains available")
	screen._open_panel("history")
	check(not SpeechAdapter.is_recording(), "Opening history cancels recording instead of hiding its stop control")
	screen._close_panel()
	source.stop()
	source.queue_free()
	AudioServer.remove_bus(bus)
	SpeechAdapter.record_effect = original_effect
	SpeechAdapter.availability_override = false
	model.cancel_activity()
	print("PASS: novel interaction conflicts" if failures == 0 else "FAIL: %d interaction checks" % failures)
	screen.queue_free()
	await get_tree().process_frame
	get_tree().quit(failures)

func buttons_contain(label: String) -> bool:
	for child in screen.action_row.get_children():
		if child is Button and child.text.contains(label): return true
	return false
