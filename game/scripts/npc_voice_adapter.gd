extends Node
## FR-32: NPC voice adapter. The game sends only server-known line IDs; the
## Qwen API key lives exclusively on the local dev service or the cloud server.
## Lines play strictly one at a time end-to-end (fetch -> play -> finish) and
## further requests queue behind the active line, so social scenes can submit
## a whole conversation up front and hear it in order.

signal line_audio_ready(npc_id: String, line_id: String)
signal line_audio_failed(npc_id: String, line_id: String, reason: String)
signal line_audio_finished(npc_id: String, line_id: String)

const LOCAL_TTS_URL := "http://127.0.0.1:17831/game/tts"
const CLOUD_TTS_PATH := "/game/tts"
const CLOUD_ENABLED_SETTING := "stranger_cloud/enabled"
const CLOUD_BASE_URL_SETTING := "stranger_cloud/base_url"
const CLOUD_CA_PATH_SETTING := "stranger_cloud/ca_cert_path"
const CLOUD_INSECURE_DEV_SETTING := "stranger_cloud/allow_insecure_dev"
const CLOUD_WEB_RELATIVE_SETTING := "stranger_cloud/web_relative_urls"
const CLOUD_TOKEN_PATH := "user://stranger_cloud.cfg"
const CLOUD_VOICE_FEATURE := "stranger_cloud_voice"
const WEB_NO_VOICE_FEATURE := "web_beta_no_voice"
const DESKTOP_NO_VOICE_FEATURE := "desktop_beta_no_voice"
const CACHE_DIR := "user://npc_voice"
const MAX_LINE_BYTES := 2 * 1024 * 1024
const MAX_QUEUE_SIZE := 4

var availability_override: Variant = null
var token_override: Variant = null
var cache_enabled := true
var audio_player: AudioStreamPlayer
var http_request: HTTPRequest
var pending_npc_id := ""
var pending_line_id := ""
var pending_voice := ""
var pending_options: Array = []
var playing_npc_id := ""
var playing_line_id := ""
var line_queue: Array[Dictionary] = []


func _ready() -> void:
	process_mode = Node.PROCESS_MODE_ALWAYS
	audio_player = AudioStreamPlayer.new()
	audio_player.name = "NpcVoicePlayer"
	audio_player.finished.connect(_on_audio_finished)
	add_child(audio_player)
	http_request = HTTPRequest.new()
	http_request.name = "NpcVoiceHttp"
	http_request.timeout = 20.0
	http_request.request_completed.connect(_on_request_completed)
	add_child(http_request)
	if cloud_mode_enabled():
		_configure_cloud_tls()

func _configure_cloud_tls() -> void:
	## Same pinned-CA contract as SpeechAdapter: this node owns its own
	## HTTPRequest, so without applying the private CA here every cloud line
	## request fails the TLS handshake against the self-signed server.
	if OS.has_feature("web") or http_request == null:
		return
	var ca_path := str(ProjectSettings.get_setting(CLOUD_CA_PATH_SETTING, "")).strip_edges()
	var certificate := _load_pinned_certificate(ca_path)
	if certificate != null:
		http_request.set_tls_options(TLSOptions.client(certificate))
		return
	if bool(ProjectSettings.get_setting(CLOUD_INSECURE_DEV_SETTING, false)):
		push_warning("NpcVoice: stranger_cloud/allow_insecure_dev is enabled; TLS verification disabled")
		http_request.set_tls_options(TLSOptions.client_unsafe())

var _pinned_certificate: X509Certificate

func _load_pinned_certificate(ca_path: String) -> X509Certificate:
	## X509Certificate.load reads the raw PEM through FileAccess, which works
	## for non-resource files inside the exported PCK (ResourceLoader.exists
	## is false for them in exports even though the file is packed).
	if _pinned_certificate != null:
		return _pinned_certificate
	if ca_path.is_empty() or not FileAccess.file_exists(ca_path):
		return null
	var candidate := X509Certificate.new()
	if candidate.load(ca_path) == OK:
		_pinned_certificate = candidate
		return candidate
	var fallback := load(ca_path) as X509Certificate
	if fallback != null:
		_pinned_certificate = fallback
	return fallback


func is_available() -> bool:
	if availability_override != null:
		return bool(availability_override)
	if cloud_mode_enabled():
		return true
	# Local headless runs exercise the contract without attempting localhost TTS.
	if DisplayServer.get_name() == "headless":
		return false
	return not OS.has_feature(WEB_NO_VOICE_FEATURE) and not OS.has_feature(DESKTOP_NO_VOICE_FEATURE)


func cloud_mode_enabled() -> bool:
	return bool(ProjectSettings.get_setting(CLOUD_ENABLED_SETTING, false)) or OS.has_feature(CLOUD_VOICE_FEATURE)


func request_line(npc_id: String, line_id: String, voice := "", response_format := "wav", options: Array = []) -> bool:
	var npc := npc_id.strip_edges().to_lower()
	var line := line_id.strip_edges().to_lower()
	if npc.is_empty() or line.is_empty():
		line_audio_failed.emit(npc, line, "VOICE_REASON_RESULT_INVALID")
		return false
	if not is_available():
		line_audio_failed.emit(npc, line, "VOICE_REASON_SERVICE_UNAVAILABLE")
		return false
	if cloud_mode_enabled() and cloud_token().is_empty():
		line_audio_failed.emit(npc, line, "VOICE_REASON_CLOUD_NOT_ACTIVATED")
		return false
	# Drop duplicate queue entries so a repeated line never plays twice in a row.
	for queued in line_queue:
		if str(queued.get("npc_id", "")) == npc and str(queued.get("line_id", "")) == line:
			return true
	if playing_line_id == line and playing_npc_id == npc:
		return true
	if line_queue.size() >= MAX_QUEUE_SIZE:
		line_audio_failed.emit(npc, line, "VOICE_REASON_SERVICE_UNAVAILABLE")
		return false
	line_queue.append({
		"npc_id": npc,
		"line_id": line,
		"voice": voice,
		"format": response_format,
		"options": options.duplicate(),
	})
	_advance_queue()
	return true


func _advance_queue() -> void:
	# pending_* are only non-empty while a fetch is in flight; a line that is
	# playing owns the audio player until it finishes.
	if playing_line_id != "" or not pending_line_id.is_empty():
		return
	if line_queue.is_empty():
		return
	var item: Dictionary = line_queue.pop_front()
	var npc: String = item["npc_id"]
	var line: String = item["line_id"]
	var voice: String = item["voice"]
	var response_format: String = item["format"]
	var options: Array = item["options"]
	var cache_path := _cache_path(npc, line, voice, options)
	if cache_enabled and FileAccess.file_exists(cache_path):
		if _play_file(cache_path, npc, line):
			line_audio_ready.emit(npc, line)
			return
		# Cache unreadable: fall through to a fresh request.
	var headers := PackedStringArray(["Content-Type: application/json"])
	if cloud_mode_enabled():
		headers.append("Authorization: Bearer " + cloud_token())
	var body := JSON.stringify({
		"npc_id": npc,
		"line_id": line,
		"voice": voice,
		"format": response_format,
		"options": options,
	})
	var url := tts_url_for_line(npc, line)
	if url.is_empty():
		line_audio_failed.emit(npc, line, "VOICE_REASON_SERVICE_UNAVAILABLE")
		_advance_queue()
		return
	pending_npc_id = npc
	pending_line_id = line
	pending_voice = voice
	pending_options = options.duplicate()
	var error := http_request.request(url, headers, HTTPClient.METHOD_POST, body)
	if error != OK:
		var failed_line := pending_line_id
		var failed_npc := pending_npc_id
		_clear_pending()
		line_audio_failed.emit(failed_npc, failed_line, "VOICE_REASON_SERVICE_UNAVAILABLE")
		_advance_queue()
		return


func tts_url_for_line(_npc_id := "", _line_id := "") -> String:
	if cloud_mode_enabled():
		if OS.has_feature("web") and bool(ProjectSettings.get_setting(CLOUD_WEB_RELATIVE_SETTING, true)):
			return CLOUD_TTS_PATH
		var base := str(ProjectSettings.get_setting(CLOUD_BASE_URL_SETTING, "")).trim_suffix("/")
		return base + CLOUD_TTS_PATH if not base.is_empty() else ""
	return LOCAL_TTS_URL


func cloud_token() -> String:
	if token_override != null:
		return str(token_override).strip_edges()
	var config := ConfigFile.new()
	if config.load(CLOUD_TOKEN_PATH) != OK:
		return ""
	return str(config.get_value("stranger_cloud", "token", "")).strip_edges()


func _cache_key(npc_id: String, line_id: String, voice: String, options: Array = []) -> String:
	var selected_voice := voice.strip_edges()
	var option_key := ",".join(options)
	return "%s/%s/%s/%s" % [npc_id, line_id, selected_voice if not selected_voice.is_empty() else "default", option_key if not option_key.is_empty() else "single"]


func _cache_path(npc_id: String, line_id: String, voice: String, options: Array = []) -> String:
	return CACHE_DIR.path_join(_cache_key(npc_id, line_id, voice, options).replace("/", "_") + ".wav")


func _play_file(path: String, npc_id := "", line_id := "") -> bool:
	var stream := AudioStreamWAV.load_from_file(path)
	if stream == null or stream.get_length() <= 0.0:
		return false
	audio_player.stream = stream
	playing_npc_id = npc_id
	playing_line_id = line_id
	audio_player.play()
	return true


func _on_request_completed(result: int, response_code: int, _headers: PackedStringArray, body: PackedByteArray) -> void:
	var npc := pending_npc_id
	var line := pending_line_id
	var voice := pending_voice
	var options: Array = pending_options.duplicate()
	_clear_pending()
	if result != HTTPRequest.RESULT_SUCCESS or response_code != 200 or body.size() < 44 or body.size() > MAX_LINE_BYTES:
		var reason := "VOICE_REASON_SERVICE_UNAVAILABLE"
		if response_code == 401 or response_code == 403:
			reason = "VOICE_REASON_CLOUD_UNAUTHORIZED"
		elif response_code == 404:
			reason = "VOICE_REASON_RESULT_INVALID"
		line_audio_failed.emit(npc, line, reason)
		_advance_queue()
		return
	if cache_enabled:
		var path := _cache_path(npc, line, voice, options)
		var dir := DirAccess.open(CACHE_DIR)
		if dir == null:
			DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(CACHE_DIR))
		var file := FileAccess.open(path, FileAccess.WRITE)
		if file:
			file.store_buffer(body)
			file.flush()
			file.close()
			if _play_file(path, npc, line):
				line_audio_ready.emit(npc, line)
				return
		line_audio_failed.emit(npc, line, "VOICE_REASON_SAVE_FAILED")
		_advance_queue()
		return
	if _play_buffer(body, npc, line):
		line_audio_ready.emit(npc, line)
		return
	line_audio_failed.emit(npc, line, "VOICE_REASON_SAVE_FAILED")
	_advance_queue()


func _play_buffer(data: PackedByteArray, npc_id: String, line_id: String) -> bool:
	var stream := AudioStreamWAV.load_from_buffer(data)
	if stream == null or stream.get_length() <= 0.0:
		return false
	audio_player.stream = stream
	playing_npc_id = npc_id
	playing_line_id = line_id
	audio_player.play()
	return true


func _on_audio_finished() -> void:
	if playing_line_id.is_empty():
		return
	var npc := playing_npc_id
	var line := playing_line_id
	playing_npc_id = ""
	playing_line_id = ""
	audio_player.stream = null
	line_audio_finished.emit(npc, line)
	_advance_queue()


func _clear_pending() -> void:
	pending_npc_id = ""
	pending_line_id = ""
	pending_voice = ""
	pending_options.clear()
