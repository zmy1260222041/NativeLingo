extends Node

signal recognition_finished(target_id: String, accepted: bool, transcript: String, reason: String, expression: Dictionary)
signal recognition_pending(target_id: String)
signal recording_state_changed(active: bool)
signal recording_progress(elapsed_seconds: float, maximum_seconds: float)
signal session_cancelled(target_id: String)
signal cloud_auth_finished(success: bool, message: String)
signal word_score_finished(lexical_id: String, accepted: bool, expression: Dictionary, reason: String)

const SERVICE_URL := "http://127.0.0.1:17831/transcribe"
const RECORDING_PATH := "user://stranger_speech_attempt"
const MAX_RECORDING_SECONDS := 15.0
## Web Beta 首轮不包含语音：该自定义 feature 只在 Web Beta 导出预设中开启。
const WEB_NO_VOICE_FEATURE := "web_beta_no_voice"
## Desktop Beta 同样以手势交付；语音增强版单独立项。
const DESKTOP_NO_VOICE_FEATURE := "desktop_beta_no_voice"
## FR-29 云评分设置(发布构建由 export_presets/构建脚本注入)。
const CLOUD_ENABLED_SETTING := "stranger_cloud/enabled"
const CLOUD_BASE_URL_SETTING := "stranger_cloud/base_url"
const CLOUD_CA_PATH_SETTING := "stranger_cloud/ca_cert_path"
const CLOUD_INSECURE_DEV_SETTING := "stranger_cloud/allow_insecure_dev"
const CLOUD_WEB_RELATIVE_SETTING := "stranger_cloud/web_relative_urls"
const CLOUD_VOICE_FEATURE := "stranger_cloud_voice"
const CLOUD_EVALUATE_PATH := "/game/evaluate"
const CLOUD_WORD_SCORE_PATH := "/game/score_word"
const LOCAL_WORD_SCORE_URL := "http://127.0.0.1:17831/score_word"
const CLOUD_REGISTER_PATH := "/register"
const CLOUD_TOKEN_PATH := "user://stranger_cloud.cfg"
const CLOUD_DEVICE_PATH := "user://stranger_device.cfg"

var record_effect: AudioEffectRecord
var microphone_player: AudioStreamPlayer
var http_request: HTTPRequest
var active_target_id := ""
var active_generation := -1
var pending_target_id := ""
var request_generation := -1
var recovery_target_id := ""
var recovery_active := false
var word_mode := false
var active_lexical_id := ""
var active_lexical_options: Array = []
var pending_word_lexical_id := ""
var pending_word_options: Array = []
var pending_word_mode := false
var session_generation := 0
var recording_started_msec := 0
var recording_session_active := false
var pending_activation := false
## 测试钩子：null 表示按 OS feature 自动判断；true/false 强制覆盖。
var availability_override: Variant = null
## 测试钩子：null 表示读取 user:// token；其它值直接作为 cloud token。
var token_override: Variant = null
## 最近一次"语音能力本身不可用"的失败原因；普通听不清(score low)不写入。
var last_unavailable_reason := ""

func is_available() -> bool:
	## 云评分构建可用(不依赖本地模型)；普通桌面构建可用；无语音
	## Web/Desktop Beta 构建固定返回 false，且从不创建麦克风/HTTP 客户端。
	if availability_override != null:
		return bool(availability_override)
	if cloud_mode_enabled():
		return true
	return not OS.has_feature(WEB_NO_VOICE_FEATURE) and not OS.has_feature(DESKTOP_NO_VOICE_FEATURE)

func cloud_mode_enabled() -> bool:
	return bool(ProjectSettings.get_setting(CLOUD_ENABLED_SETTING, false)) or OS.has_feature(CLOUD_VOICE_FEATURE)

func runtime_speech_unavailable() -> bool:
	## FR-28 G4 / FR-29 G5：无语音构建、云评分未激活、或最近一次尝试确认
	## 麦克风/服务/结果通道不可用，才允许 gesture_fallback 给最低生存档。
	## 普通表达分数低不是"语音不可用"，不能靠手势换物资。
	if not is_available():
		return true
	if cloud_mode_enabled() and cloud_token().is_empty():
		return true
	return last_unavailable_reason in [
		"VOICE_REASON_MIC_UNAVAILABLE",
		"VOICE_REASON_SERVICE_UNAVAILABLE",
		"VOICE_REASON_SAVE_FAILED",
		"VOICE_REASON_READ_FAILED",
		"VOICE_REASON_RESULT_INVALID",
		"VOICE_REASON_CLOUD_NOT_ACTIVATED",
		"VOICE_REASON_CLOUD_UNAUTHORIZED",
	]

func _ready() -> void:
	if not is_available():
		# 无语音构建：不创建 HTTPRequest，也不创建 AudioStreamMicrophone。
		return
	http_request = HTTPRequest.new()
	http_request.process_mode = Node.PROCESS_MODE_ALWAYS
	# 本地服务首次请求可能等模型预热；云端冷启动也可能较慢。两者都比单次
	# 转写本身久，因此给一个偏长的 deadline，后续请求都在几秒内返回。
	http_request.timeout = 60.0
	http_request.request_completed.connect(_on_request_completed)
	add_child(http_request)
	if cloud_mode_enabled():
		_configure_cloud_tls()

func _process(_delta: float) -> void:
	if not is_recording():
		return
	var elapsed := float(Time.get_ticks_msec() - recording_started_msec) / 1000.0
	recording_progress.emit(minf(elapsed, MAX_RECORDING_SECONDS), MAX_RECORDING_SECONDS)
	if elapsed >= MAX_RECORDING_SECONDS:
		finish_recording()

func _exit_tree() -> void:
	if record_effect and record_effect.is_recording_active():
		record_effect.set_recording_active(false)
	recording_session_active = false
	if microphone_player:
		microphone_player.stop()
		microphone_player.stream = null
		microphone_player = null
	var bus_index := AudioServer.get_bus_index("SpeechRecord")
	if bus_index >= 0:
		AudioServer.remove_bus(bus_index)
	record_effect = null

func start_recording(target_id: String) -> bool:
	if not is_available():
		# 无语音构建的防御路径：不进入录音、不冻结时间、不产生 HTTP 请求。
		return false
	if record_effect == null and DisplayServer.get_name() != "headless":
		_setup_audio_input()
	if record_effect == null:
		session_generation += 1
		GameState.set_interaction_time_frozen(true)
		_emit_failure(target_id, session_generation, "VOICE_REASON_MIC_UNAVAILABLE")
		return false
	if is_recording() or _request_in_flight():
		return false
	_clear_recovery(false)
	session_generation += 1
	active_generation = session_generation
	active_target_id = target_id
	last_unavailable_reason = ""
	recording_started_msec = Time.get_ticks_msec()
	record_effect.set_recording_active(true)
	recording_session_active = true
	GameState.set_interaction_time_frozen(true)
	recording_state_changed.emit(true)
	recording_progress.emit(0.0, MAX_RECORDING_SECONDS)
	return true

func start_word_recording(lexical_id: String) -> bool:
	## FR-36: independent word practice session. The lexical ID is a server-known
	## catalog key; the client never sends free text for word scoring.
	if not is_available():
		word_score_finished.emit(lexical_id, false, {}, "VOICE_REASON_SERVICE_UNAVAILABLE")
		return false
	if record_effect == null and DisplayServer.get_name() != "headless":
		_setup_audio_input()
	if record_effect == null:
		word_score_finished.emit(lexical_id, false, {}, "VOICE_REASON_MIC_UNAVAILABLE")
		return false
	if is_recording() or _request_in_flight():
		return false
	_clear_recovery(false)
	session_generation += 1
	active_generation = session_generation
	active_lexical_id = lexical_id.strip_edges().to_lower()
	active_lexical_options = [active_lexical_id]
	word_mode = true
	active_target_id = ""
	last_unavailable_reason = ""
	recording_started_msec = Time.get_ticks_msec()
	record_effect.set_recording_active(true)
	recording_session_active = true
	GameState.set_interaction_time_frozen(true)
	recording_state_changed.emit(true)
	recording_progress.emit(0.0, MAX_RECORDING_SECONDS)
	return true


func start_word_choice_recording(options: Array) -> bool:
	var clean: Array = []
	for option in options:
		var word := str(option).strip_edges().to_lower()
		if not word.is_empty() and word not in clean:
			clean.append(word)
	if clean.is_empty():
		word_score_finished.emit("", false, {}, "VOICE_REASON_RESULT_INVALID")
		return false
	if not is_available():
		word_score_finished.emit(",".join(clean), false, {}, "VOICE_REASON_SERVICE_UNAVAILABLE")
		return false
	if record_effect == null and DisplayServer.get_name() != "headless":
		_setup_audio_input()
	if record_effect == null:
		word_score_finished.emit(",".join(clean), false, {}, "VOICE_REASON_MIC_UNAVAILABLE")
		return false
	if is_recording() or _request_in_flight():
		return false
	_clear_recovery(false)
	session_generation += 1
	active_generation = session_generation
	active_lexical_options = clean
	active_lexical_id = ",".join(clean)
	word_mode = true
	active_target_id = ""
	last_unavailable_reason = ""
	recording_started_msec = Time.get_ticks_msec()
	record_effect.set_recording_active(true)
	recording_session_active = true
	GameState.set_interaction_time_frozen(true)
	recording_state_changed.emit(true)
	recording_progress.emit(0.0, MAX_RECORDING_SECONDS)
	return true


func is_recording() -> bool:
	return recording_session_active

func is_recovery_active() -> bool:
	return recovery_active

func session_target_id() -> String:
	if not active_target_id.is_empty():
		return active_target_id
	if not pending_target_id.is_empty():
		return pending_target_id
	return recovery_target_id

func is_interaction_active() -> bool:
	return is_recording() or _request_in_flight() or recovery_active

func cancel_recording() -> void:
	var cancelled_target := active_target_id if not active_target_id.is_empty() else (pending_target_id if not pending_target_id.is_empty() else recovery_target_id)
	var had_session := is_interaction_active()
	if is_recording():
		if record_effect and record_effect.is_recording_active():
			record_effect.set_recording_active(false)
		recording_session_active = false
		recording_state_changed.emit(false)
	if _request_in_flight():
		http_request.cancel_request()
	session_generation += 1
	active_generation = -1
	request_generation = -1
	active_target_id = ""
	pending_target_id = ""
	active_lexical_id = ""
	active_lexical_options.clear()
	pending_word_lexical_id = ""
	pending_word_options.clear()
	pending_word_mode = false
	word_mode = false
	_clear_recovery(false)
	GameState.set_interaction_time_frozen(false)
	if had_session:
		session_cancelled.emit(cancelled_target)

func clear_recovery() -> void:
	if not recovery_active:
		return
	var target_id := recovery_target_id
	_clear_recovery(false)
	GameState.set_interaction_time_frozen(false)
	session_cancelled.emit(target_id)

func finish_recording() -> void:
	if not is_recording():
		return
	var target_id := active_target_id
	var lexical_id := active_lexical_id
	var lexical_options: Array = active_lexical_options.duplicate()
	var generation := active_generation
	var was_word_mode := word_mode
	var recording := record_effect.get_recording()
	record_effect.set_recording_active(false)
	recording_session_active = false
	recording_state_changed.emit(false)
	active_target_id = ""
	active_lexical_id = ""
	active_lexical_options.clear()
	active_generation = -1
	word_mode = false
	if recording == null or recording.get_length() < 0.25:
		if was_word_mode:
			_emit_word_failure(lexical_id, generation, "VOICE_REASON_TOO_SHORT")
		else:
			_emit_failure(target_id, generation, "VOICE_REASON_TOO_SHORT")
		return
	if recording.save_to_wav(RECORDING_PATH) != OK:
		if was_word_mode:
			_emit_word_failure(lexical_id, generation, "VOICE_REASON_SAVE_FAILED")
		else:
			_emit_failure(target_id, generation, "VOICE_REASON_SAVE_FAILED")
		return
	var wav_path := RECORDING_PATH + ".wav"
	var file := FileAccess.open(wav_path, FileAccess.READ)
	if file == null:
		if was_word_mode:
			_emit_word_failure(lexical_id, generation, "VOICE_REASON_READ_FAILED")
		else:
			_emit_failure(target_id, generation, "VOICE_REASON_READ_FAILED")
		return
	var headers := PackedStringArray(["Content-Type: audio/wav"])
	var url := SERVICE_URL
	if was_word_mode:
		url = _word_score_url()
		if cloud_mode_enabled():
			var token := cloud_token()
			if token.is_empty():
				_emit_word_failure(lexical_id, generation, "VOICE_REASON_CLOUD_NOT_ACTIVATED")
				return
			headers.append("Authorization: Bearer " + token)
		headers.append("X-Stranger-Lexical: " + ",".join(lexical_options))
		pending_word_lexical_id = lexical_id
		pending_word_options = lexical_options.duplicate()
		pending_word_mode = true
		request_generation = generation
		var word_error := http_request.request_raw(url, headers, HTTPClient.METHOD_POST, file.get_buffer(file.get_length()))
		if word_error != OK:
			pending_word_lexical_id = ""
			pending_word_options.clear()
			pending_word_mode = false
			request_generation = -1
			_emit_word_failure(lexical_id, generation, "VOICE_REASON_SERVICE_UNAVAILABLE")
		else:
			recognition_pending.emit(lexical_id)
		return
	if cloud_mode_enabled():
		var token := cloud_token()
		if token.is_empty():
			_emit_failure(target_id, generation, "VOICE_REASON_CLOUD_NOT_ACTIVATED")
			return
		url = _cloud_evaluate_url()
		headers.append("Authorization: Bearer " + token)
	headers.append("X-Stranger-Target: " + target_id)
	pending_target_id = target_id
	request_generation = generation
	var error := http_request.request_raw(url, headers, HTTPClient.METHOD_POST, file.get_buffer(file.get_length()))
	if error != OK:
		pending_target_id = ""
		request_generation = -1
		_emit_failure(target_id, generation, "VOICE_REASON_SERVICE_UNAVAILABLE")
	else:
		recognition_pending.emit(target_id)

func _cloud_base_url() -> String:
	return str(ProjectSettings.get_setting(CLOUD_BASE_URL_SETTING, "")).trim_suffix("/")

func _cloud_evaluate_url() -> String:
	if OS.has_feature("web") and bool(ProjectSettings.get_setting(CLOUD_WEB_RELATIVE_SETTING, true)):
		# Web Beta 经 nginx 同源反代 /game/ → 云服务器,避免 CORS 与私有 CA。
		return CLOUD_EVALUATE_PATH
	return _cloud_base_url() + CLOUD_EVALUATE_PATH

func _cloud_register_url() -> String:
	return _cloud_base_url() + CLOUD_REGISTER_PATH


func _word_score_url() -> String:
	if cloud_mode_enabled():
		if OS.has_feature("web") and bool(ProjectSettings.get_setting(CLOUD_WEB_RELATIVE_SETTING, true)):
			return CLOUD_WORD_SCORE_PATH
		return _cloud_base_url() + CLOUD_WORD_SCORE_PATH
	return LOCAL_WORD_SCORE_URL


func _emit_word_failure(lexical_id: String, generation: int, reason: String) -> void:
	if generation != session_generation:
		return
	GameState.set_interaction_time_frozen(false)
	word_score_finished.emit(lexical_id, false, {}, reason)

func _configure_cloud_tls() -> void:
	## 桌面端固定内置私有 CA(与 Android/iOS 同源);Web 由浏览器/nignx 承担 TLS。
	if OS.has_feature("web") or http_request == null:
		return
	var ca_path := str(ProjectSettings.get_setting(CLOUD_CA_PATH_SETTING, "")).strip_edges()
	var certificate := _load_pinned_certificate(ca_path)
	if certificate != null:
		http_request.set_tls_options(TLSOptions.client(certificate))
		return
	if bool(ProjectSettings.get_setting(CLOUD_INSECURE_DEV_SETTING, false)):
		# 仅本机开发:显式开关,发布构建必须为 false。
		push_warning("SpeechAdapter: stranger_cloud/allow_insecure_dev is enabled; TLS verification disabled")
		http_request.set_tls_options(TLSOptions.client_unsafe())

var _pinned_certificate: X509Certificate

func _load_pinned_certificate(ca_path: String) -> X509Certificate:
	## X509Certificate.load reads the raw PEM through FileAccess, which works
	## for non-resource files inside the exported PCK. ResourceLoader.exists
	## is false for them in exports even though the file is packed, so relying
	## on it silently dropped the pinned CA and broke TLS in release builds.
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

func cloud_token() -> String:
	if token_override != null:
		return str(token_override).strip_edges()
	var config := ConfigFile.new()
	if config.load(CLOUD_TOKEN_PATH) != OK:
		return ""
	return str(config.get_value("stranger_cloud", "token", "")).strip_edges()

func cloud_activated() -> bool:
	return not cloud_token().is_empty()

func clear_cloud_token() -> void:
	var config := ConfigFile.new()
	config.set_value("stranger_cloud", "token", "")
	config.save(CLOUD_TOKEN_PATH)

func cloud_device_id() -> String:
	var config := ConfigFile.new()
	if config.load(CLOUD_DEVICE_PATH) == OK:
		var existing := str(config.get_value("stranger_cloud", "device_id", "")).strip_edges()
		if not existing.is_empty():
			return existing
	var crypto := Crypto.new()
	var random_bytes := crypto.generate_random_bytes(16)
	var device_id := random_bytes.hex_encode()
	config.set_value("stranger_cloud", "device_id", device_id)
	config.save(CLOUD_DEVICE_PATH)
	return device_id

func activate_cloud(code: String) -> bool:
	## 复用云服务器 /register:一次性激活码换每设备 token(与 Android/iOS 同源)。
	## PCK 内不含激活码;token 仅存 user://。
	if not cloud_mode_enabled() or http_request == null:
		cloud_auth_finished.emit(false, tr("CLOUD_ACTIVATE_UNAVAILABLE"))
		return false
	if _request_in_flight() or pending_activation:
		return false
	var cleaned := code.strip_edges()
	if cleaned.is_empty():
		cloud_auth_finished.emit(false, tr("CLOUD_ACTIVATE_EMPTY_CODE"))
		return false
	pending_activation = true
	var body := "device_id=%s&code=%s" % [cloud_device_id().uri_encode(), cleaned.uri_encode()]
	var headers := PackedStringArray(["Content-Type: application/x-www-form-urlencoded"])
	var error := http_request.request_raw(
		_cloud_register_url(),
		headers,
		HTTPClient.METHOD_POST,
		body.to_utf8_buffer()
	)
	if error != OK:
		pending_activation = false
		cloud_auth_finished.emit(false, tr("CLOUD_ACTIVATE_NETWORK"))
		return false
	return true

func cancel_activation() -> void:
	if not pending_activation:
		return
	pending_activation = false
	if http_request != null:
		http_request.cancel_request()

func _on_activation_completed(result: int, response_code: int, body: PackedByteArray) -> void:
	if result != HTTPRequest.RESULT_SUCCESS:
		cloud_auth_finished.emit(false, tr("CLOUD_ACTIVATE_NETWORK"))
		return
	if response_code == 401:
		cloud_auth_finished.emit(false, tr("CLOUD_ACTIVATE_BAD_CODE"))
		return
	if response_code != 200:
		cloud_auth_finished.emit(false, tr("CLOUD_ACTIVATE_BAD_RESPONSE"))
		return
	var parsed = JSON.parse_string(body.get_string_from_utf8())
	if not parsed is Dictionary:
		cloud_auth_finished.emit(false, tr("CLOUD_ACTIVATE_BAD_RESPONSE"))
		return
	var token := str(parsed.get("token", "")).strip_edges()
	if token.is_empty():
		cloud_auth_finished.emit(false, tr("CLOUD_ACTIVATE_BAD_CODE"))
		return
	var config := ConfigFile.new()
	config.set_value("stranger_cloud", "token", token)
	if config.save(CLOUD_TOKEN_PATH) != OK:
		cloud_auth_finished.emit(false, tr("CLOUD_ACTIVATE_SAVE_FAILED"))
		return
	last_unavailable_reason = ""
	cloud_auth_finished.emit(true, tr("CLOUD_ACTIVATED"))

func _setup_audio_input() -> void:
	if not is_available():
		return
	var bus_index := AudioServer.get_bus_index("SpeechRecord")
	if bus_index < 0:
		AudioServer.add_bus()
		bus_index = AudioServer.bus_count - 1
		AudioServer.set_bus_name(bus_index, "SpeechRecord")
		AudioServer.set_bus_mute(bus_index, true)
	var existing: AudioEffect = AudioServer.get_bus_effect(bus_index, 0) if AudioServer.get_bus_effect_count(bus_index) > 0 else null
	if existing is AudioEffectRecord:
		record_effect = existing
	else:
		record_effect = AudioEffectRecord.new()
		AudioServer.add_bus_effect(bus_index, record_effect)
	microphone_player = AudioStreamPlayer.new()
	microphone_player.stream = AudioStreamMicrophone.new()
	microphone_player.bus = "SpeechRecord"
	add_child(microphone_player)
	microphone_player.play()

func _on_request_completed(result: int, response_code: int, _headers: PackedStringArray, body: PackedByteArray) -> void:
	if pending_activation:
		pending_activation = false
		_on_activation_completed(result, response_code, body)
		return
	if pending_word_mode:
		var word_lexical := pending_word_lexical_id
		var word_options: Array = pending_word_options.duplicate()
		var word_generation := request_generation
		pending_word_lexical_id = ""
		pending_word_options.clear()
		pending_word_mode = false
		request_generation = -1
		if word_generation != session_generation:
			return
		if result != HTTPRequest.RESULT_SUCCESS or (response_code != 200 and response_code != 201):
			var word_reason := "VOICE_REASON_CLOUD_UNAUTHORIZED" if response_code == 401 or response_code == 403 else "VOICE_REASON_SERVICE_UNAVAILABLE"
			_emit_word_failure(word_lexical, word_generation, word_reason)
			return
		var word_parsed = JSON.parse_string(body.get_string_from_utf8())
		if not word_parsed is Dictionary:
			_emit_word_failure(word_lexical, word_generation, "VOICE_REASON_RESULT_INVALID")
			return
		var word_accepted := bool(word_parsed.get("accepted", false))
		var word_expression := _extract_expression(word_parsed)
		var word_text := str(word_parsed.get("text", ""))
		word_expression["text"] = word_text
		var matched_lexical := str(word_parsed.get("lexical_id", word_lexical))
		if matched_lexical.is_empty() and word_options.size() == 1:
			matched_lexical = word_options[0]
		GameState.set_interaction_time_frozen(false)
		word_score_finished.emit(matched_lexical, word_accepted, word_expression, str(word_parsed.get("reason", "VOICE_REASON_CLARIFY")))
		return
	var target_id := pending_target_id
	var generation := request_generation
	pending_target_id = ""
	request_generation = -1
	if target_id.is_empty() or generation != session_generation:
		return
	if result != HTTPRequest.RESULT_SUCCESS or (response_code != 200 and response_code != 201):
		if response_code == 401 or response_code == 403:
			clear_cloud_token()
			_emit_failure(target_id, generation, "VOICE_REASON_CLOUD_UNAUTHORIZED")
		else:
			_emit_failure(target_id, generation, "VOICE_REASON_SERVICE_UNAVAILABLE")
		return
	var parsed = JSON.parse_string(body.get_string_from_utf8())
	if not parsed is Dictionary:
		_emit_failure(target_id, generation, "VOICE_REASON_RESULT_INVALID")
		return
	var accepted := bool(parsed.get("accepted", false))
	var transcript := str(parsed.get("text", ""))
	var reason := str(parsed.get("reason", "VOICE_REASON_CLARIFY"))
	var expression := _extract_expression(parsed)
	last_unavailable_reason = ""
	if accepted:
		_clear_recovery(false)
		GameState.set_interaction_time_frozen(false)
		recognition_finished.emit(target_id, true, transcript, reason, expression)
	else:
		recovery_active = true
		recovery_target_id = target_id
		recognition_finished.emit(target_id, false, transcript, reason, expression)

func _extract_expression(parsed: Dictionary) -> Dictionary:
	var expression := {}
	for key in ["pronunciation", "delivery", "score", "band", "pronunciation_source"]:
		if parsed.has(key):
			expression[key] = parsed.get(key)
	if not expression.is_empty() and expression.has("band"):
		expression["text"] = str(parsed.get("text", ""))
	return expression

func _emit_failure(target_id: String, generation: int, reason: String) -> void:
	if generation != session_generation:
		return
	if reason in ["VOICE_REASON_MIC_UNAVAILABLE", "VOICE_REASON_SERVICE_UNAVAILABLE", "VOICE_REASON_SAVE_FAILED", "VOICE_REASON_READ_FAILED", "VOICE_REASON_RESULT_INVALID", "VOICE_REASON_CLOUD_NOT_ACTIVATED", "VOICE_REASON_CLOUD_UNAUTHORIZED"]:
		last_unavailable_reason = reason
	recovery_active = true
	recovery_target_id = target_id
	recognition_finished.emit(target_id, false, "", reason, {})

func _request_in_flight() -> bool:
	return not pending_target_id.is_empty() or not pending_word_lexical_id.is_empty() or (http_request != null and http_request.get_http_client_status() != HTTPClient.STATUS_DISCONNECTED)

func _clear_recovery(_unused_notify: bool) -> void:
	recovery_active = false
	recovery_target_id = ""
