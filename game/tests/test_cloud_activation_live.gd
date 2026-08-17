extends Node
## Live cloud-activation + cloud-TTS smoke against the real server with the
## pinned private CA (no insecure flag). Requires NL_TEST_CODE env with a
## fresh one-time activation code. Not part of the export (tests/ excluded).

const SpeechAdapterScript = preload("res://scripts/speech_adapter.gd")
const NpcVoiceScript = preload("res://scripts/npc_voice_adapter.gd")

var failures := 0
var finished := false
var speech: Node
var voice: Node


func _ready() -> void:
	ProjectSettings.set_setting("stranger_cloud/enabled", true)
	ProjectSettings.set_setting("stranger_cloud/base_url", "https://124.220.234.178:8756")
	ProjectSettings.set_setting("stranger_cloud/ca_cert_path", "res://certs/nl_ca.pem")
	ProjectSettings.set_setting("stranger_cloud/allow_insecure_dev", false)
	var code := OS.get_environment("NL_TEST_CODE").strip_edges()
	if code.is_empty():
		_expect(false, "NL_TEST_CODE env with a fresh activation code is required")
		_finish()
		return
	speech = SpeechAdapterScript.new()
	add_child(speech)
	await get_tree().process_frame
	_expect(speech._load_pinned_certificate("res://certs/nl_ca.pem") != null, "Pinned CA loads via X509Certificate.load")
	speech.cloud_auth_finished.connect(_on_auth)
	print("activating...")
	speech.activate_cloud(code)


func _on_auth(success: bool, message: String) -> void:
	print("auth finished: success=", success, " msg=", message)
	_expect(success, "Activation succeeds against the real server over pinned TLS")
	if not success:
		_finish()
		return
	_expect(not speech.cloud_token().is_empty(), "Device token stored locally")
	voice = NpcVoiceScript.new()
	add_child(voice)
	voice.cache_enabled = false
	voice.line_audio_ready.connect(func(_npc: String, _line: String) -> void:
		_expect(true, "Cloud /game/tts returns audio through the Godot client")
		_finish())
	voice.line_audio_failed.connect(func(_npc: String, _line: String, reason: String) -> void:
		print("tts failed reason=", reason)
		_expect(false, "Cloud /game/tts returns audio through the Godot client")
		_finish())
	var requested: bool = voice.request_line("tavi", "greeting")
	_expect(requested, "TTS line request accepted with a stored cloud token")
	await get_tree().create_timer(30.0).timeout
	_finish()


func _expect(condition: bool, label: String) -> void:
	if condition:
		print("  OK  ", label)
	else:
		failures += 1
		push_error("FAIL: " + label)


func _finish() -> void:
	if finished:
		return
	finished = true
	if failures == 0:
		print("PASS: Stranger live cloud activation suite")
	get_tree().quit(failures)
