extends Node
## Delayed TTS must not silently run the opening's typewriter ahead of playback.
var failures := 0

func check(ok: bool, label: String) -> void:
	print("PASS: " + label if ok else "FAIL: " + label)
	if not ok: failures += 1

func _ready() -> void:
	GameState.persistence_enabled = false
	GameState.reset_run()
	var screen := preload("res://scenes/Novel.tscn").instantiate()
	screen.boot_from_save = false
	add_child(screen)
	var model = screen.model
	var before: int = model.history.size()
	var previous: String = screen.dialogue_text.text
	NpcDialogueService.dialogue_ready.emit("mira", "delayed", "I'm Mira. Take your time here.")
	await get_tree().create_timer(0.2).timeout
	check(screen.dialogue_text.text == previous and model.history.size() == before, "Delayed audio cannot display or log silent English")
	check(screen.feedback_label.text == "正在准备语音…", "Voice preparation is visible")
	NpcVoice.line_audio_ready.emit("rowan", "delayed")
	NpcVoice.line_audio_ready.emit("mira", "older")
	check(model.history.size() == before, "Other NPC and stale audio cannot reveal the pending line")
	var pcm := PackedByteArray()
	pcm.resize(48000)
	NpcVoice.feed_reply_pcm("mira", "delayed", pcm)
	check(NpcVoice.audio_player.playing and screen.dialogue_text.text == "I'm Mira. Take your time here." and screen.text_elapsed == 0.0, "English typewriter starts with actual playback")
	NpcVoice.line_audio_ready.emit("mira", "delayed")
	check(model.history.size() == before + 1, "Duplicate audio callback cannot repeat the line")
	model.cancel_activity()
	NpcVoice.feed_reply_pcm("mira", "already-playing", pcm)
	NpcDialogueService.dialogue_ready.emit("mira", "already-playing", "Good to see you.")
	check(screen.dialogue_text.text == "Good to see you." and model._pending_spoken_reply.is_empty(), "Audio arriving before text displays immediately")
	model.cancel_activity()
	NpcDialogueService.dialogue_ready.emit("mira", "cancelled", "Do not show this.")
	model.cancel_activity()
	NpcVoice.line_audio_ready.emit("mira", "cancelled")
	check(screen.dialogue_text.text == "Good to see you.", "Cancellation discards pending speech")
	NpcDialogueService.dialogue_ready.emit("mira", "failed", "The square is a good place to meet people.")
	NpcDialogueService.dialogue_failed.emit("mira", "VOICE_REASON_SERVICE_UNAVAILABLE")
	check(screen.dialogue_text.text == "The square is a good place to meet people." and screen.feedback_label.text.contains("语音未能播放"), "Failed audio preserves readable text with an explicit failure")
	check(model._pending_spoken_reply.is_empty(), "Failure releases pending presentation")
	model._preparing_opening = true
	model.line_changed.emit("", "正在准备开场语音…")
	NpcDialogueService.dialogue_failed.emit("mira", "VOICE_REASON_SERVICE_UNAVAILABLE")
	check(not model._preparing_opening and screen.dialogue_text.text == "Welcome, stranger." and screen.speaker_label.text == "Mira", "Opening generation failure falls back to the authored opening line")
	check(not screen.feedback_label.text.contains("这次回应") and not screen.feedback_label.text.contains("Local speech"), "An unrequested opening failure is not reported as the player's failed reply")
	screen.queue_free()
	await get_tree().process_frame
	print("NovelReplyAudioTest failures=", failures)
	get_tree().quit(1 if failures else 0)
