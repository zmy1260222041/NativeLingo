extends Node

var failures := 0

func _ready() -> void:
	var previous_cloud_enabled: bool = ProjectSettings.get_setting("stranger_cloud/enabled", false)
	var previous_base_url: String = ProjectSettings.get_setting("stranger_cloud/base_url", "")
	NpcVoice.cache_enabled = false
	NpcVoice.availability_override = false
	var failures_seen: Array[String] = []
	NpcVoice.line_audio_failed.connect(func(_npc_id: String, _line_id: String, reason: String) -> void:
		failures_seen.append(reason))
	_expect(NpcVoice.tts_url_for_line() == "http://127.0.0.1:17831/game/tts", "Local mode targets the optional localhost TTS boundary")
	_expect(not NpcVoice.request_line("mira", "greeting"), "Unavailable adapter never starts an HTTP request")
	_expect(failures_seen == ["VOICE_REASON_SERVICE_UNAVAILABLE"], "Unavailable adapter reports the safe localizable reason")
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
	if failures == 0:
		print("PASS: Stranger NPC voice adapter suite")
	get_tree().quit(failures)


func _expect(condition: bool, label: String) -> void:
	if condition:
		print("  OK  ", label)
	else:
		failures += 1
		push_error("FAIL: " + label)
