extends Node

var failures := 0

func _ready() -> void:
	var previous_cloud_enabled: bool = ProjectSettings.get_setting("stranger_cloud/enabled", false)
	var previous_base_url: String = ProjectSettings.get_setting("stranger_cloud/base_url", "")
	NpcVoice.cache_enabled = false
	NpcVoice.availability_override = false
	if bool(ProjectSettings.get_setting("stranger_novel/enabled", false)):
		_expect(NpcVoice.audio_player is AudioStreamPlayer, "Novel NPC lines use non-positional audio")
		_expect(NpcVoice.audio_player.volume_db <= -8.0, "Novel voice retains comfortable playback volume")
		NpcVoice._sync_audio_position() # Safe without a 3D speaker or camera.
	else:
		_expect(NpcVoice.audio_player is AudioStreamPlayer3D, "NPC lines use a spatial 3D audio source")
		_expect(NpcVoice.audio_player.volume_db <= -8.0 and NpcVoice.audio_player.max_distance <= 10.0, "NPC voice is quieter and limited to a near-field listening radius")
		var speaker := Node3D.new()
		speaker.position = Vector3(4.0, 2.0, -3.0)
		add_child(speaker)
		NpcVoice.register_speaker("mira", speaker)
		NpcVoice.playing_npc_id = "mira"
		NpcVoice._sync_audio_position()
		_expect(NpcVoice.audio_player.global_position.distance_to(speaker.global_position + Vector3.UP * NpcVoice.VOICE_SOURCE_HEIGHT) < 0.01, "Spatial voice follows the speaking NPC")
		NpcVoice.playing_npc_id = ""
		NpcVoice.unregister_speaker("mira", speaker)
		speaker.queue_free()
	var failures_seen: Array[String] = []
	NpcVoice.line_audio_failed.connect(func(_npc_id: String, _line_id: String, reason: String) -> void:
		failures_seen.append(reason))
	_expect(NpcVoice.tts_url_for_line() == "http://127.0.0.1:17831/game/tts", "Local mode targets the optional localhost TTS boundary")
	_expect(not NpcVoice.request_line("mira", "greeting"), "Unavailable adapter never starts an HTTP request")
	_expect(failures_seen == ["VOICE_REASON_SERVICE_UNAVAILABLE"], "Unavailable adapter reports the safe localizable reason")
	failures_seen.clear()
	_expect(not NpcVoice.request_reply("mira", "reply-test"), "Unavailable adapter rejects dynamic replies without an HTTP request")
	_expect(failures_seen == ["VOICE_REASON_SERVICE_UNAVAILABLE"], "Dynamic reply failure uses the same safe voice reason")
	NpcVoice.availability_override = true
	ProjectSettings.set_setting("stranger_cloud/enabled", true)
	ProjectSettings.set_setting("stranger_cloud/base_url", "http://127.0.0.1:9999")
	NpcVoice.token_override = ""
	_expect(NpcVoice.tts_url_for_line() == "http://127.0.0.1:9999/game/tts", "Cloud mode pins the server /game/tts contract")
	failures_seen.clear()
	_expect(not NpcVoice.request_line("mira", "greeting"), "Unactivated cloud voice is blocked before any network request")
	_expect(failures_seen == ["VOICE_REASON_CLOUD_NOT_ACTIVATED"], "Cloud TTS without token falls back without penalty")
	NpcVoice.token_override = null
	ProjectSettings.set_setting("stranger_cloud/enabled", previous_cloud_enabled)
	ProjectSettings.set_setting("stranger_cloud/base_url", previous_base_url)
	NpcVoice.availability_override = null
	_test_feed_reply_pcm()
	if failures == 0:
		print("PASS: Stranger NPC voice adapter suite")
	get_tree().quit(failures)


func _test_feed_reply_pcm() -> void:
	var pcm := PackedByteArray()
	pcm.resize(4800)
	pcm.fill(7)
	var ready_seen: Array[String] = []
	var failed_seen: Array[String] = []
	NpcVoice.line_audio_ready.connect(func(_npc_id: String, line_id: String) -> void:
		ready_seen.append(line_id))
	NpcVoice.line_audio_failed.connect(func(_npc_id: String, line_id: String, _reason: String) -> void:
		failed_seen.append(line_id))
	NpcVoice.availability_override = false
	_expect(NpcVoice.feed_reply_pcm("tavi", "reply-feed", pcm), "Streamed PCM reply plays without the availability gate")
	_expect(NpcVoice.playing_npc_id == "tavi" and NpcVoice.playing_line_id == "reply-feed", "Fed reply owns the audio player")
	_expect(ready_seen == ["reply-feed"], "Fed reply emits the standard line_audio_ready signal")
	_expect(not NpcVoice.feed_reply_pcm("tavi", "reply-empty", PackedByteArray()), "Empty PCM is rejected")
	_expect(not NpcVoice.feed_reply_pcm("tavi", "reply-stereo", pcm, 24000, 2), "Non-mono PCM is rejected")
	_expect(failed_seen.size() == 2, "Rejected feeds report the same safe voice reason")
	NpcVoice.playing_npc_id = ""
	NpcVoice.playing_line_id = ""
	NpcVoice.audio_player.stop()
	NpcVoice.availability_override = null


func _expect(condition: bool, label: String) -> void:
	if condition:
		print("  OK  ", label)
	else:
		failures += 1
		push_error("FAIL: " + label)
