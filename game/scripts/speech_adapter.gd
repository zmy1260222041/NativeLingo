extends Node

signal recognition_finished(target_id: String, accepted: bool, transcript: String, reason: String)
signal recognition_pending(target_id: String)
signal recording_state_changed(active: bool)
signal recording_progress(elapsed_seconds: float, maximum_seconds: float)
signal session_cancelled(target_id: String)

const SERVICE_URL := "http://127.0.0.1:17831/transcribe"
const RECORDING_PATH := "user://stranger_speech_attempt"
const MAX_RECORDING_SECONDS := 15.0
## Web Beta 首轮不包含语音：该自定义 feature 只在 Web Beta 导出预设中开启。
const WEB_NO_VOICE_FEATURE := "web_beta_no_voice"
## Desktop Beta 同样以手势交付；语音增强版单独立项。
const DESKTOP_NO_VOICE_FEATURE := "desktop_beta_no_voice"

var record_effect: AudioEffectRecord
var microphone_player: AudioStreamPlayer
var http_request: HTTPRequest
var active_target_id := ""
var active_generation := -1
var pending_target_id := ""
var request_generation := -1
var recovery_target_id := ""
var recovery_active := false
var session_generation := 0
var recording_started_msec := 0
var recording_session_active := false
## 测试钩子：null 表示按 OS feature 自动判断；true/false 强制覆盖。
var availability_override: Variant = null

func is_available() -> bool:
	## 桌面普通构建可用；无语音 Web/Desktop Beta 构建固定返回 false，
	## 且从不创建麦克风/HTTP 客户端。
	if availability_override != null:
		return bool(availability_override)
	return not OS.has_feature(WEB_NO_VOICE_FEATURE) and not OS.has_feature(DESKTOP_NO_VOICE_FEATURE)

func _ready() -> void:
	if not is_available():
		# 首轮网页内测不包含语音：不创建 HTTPRequest，也不创建 AudioStreamMicrophone。
		return
	http_request = HTTPRequest.new()
	http_request.timeout = 18.0
	http_request.request_completed.connect(_on_request_completed)
	add_child(http_request)

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
	var generation := active_generation
	var recording := record_effect.get_recording()
	record_effect.set_recording_active(false)
	recording_session_active = false
	recording_state_changed.emit(false)
	active_target_id = ""
	active_generation = -1
	if recording == null or recording.get_length() < 0.25:
		_emit_failure(target_id, generation, "VOICE_REASON_TOO_SHORT")
		return
	if recording.save_to_wav(RECORDING_PATH) != OK:
		_emit_failure(target_id, generation, "VOICE_REASON_SAVE_FAILED")
		return
	var wav_path := RECORDING_PATH + ".wav"
	var file := FileAccess.open(wav_path, FileAccess.READ)
	if file == null:
		_emit_failure(target_id, generation, "VOICE_REASON_READ_FAILED")
		return
	var headers := PackedStringArray([
		"Content-Type: audio/wav",
		"X-Stranger-Target: " + target_id,
	])
	pending_target_id = target_id
	request_generation = generation
	var error := http_request.request_raw(SERVICE_URL, headers, HTTPClient.METHOD_POST, file.get_buffer(file.get_length()))
	if error != OK:
		pending_target_id = ""
		request_generation = -1
		_emit_failure(target_id, generation, "VOICE_REASON_SERVICE_UNAVAILABLE")
	else:
		recognition_pending.emit(target_id)

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
	var target_id := pending_target_id
	var generation := request_generation
	pending_target_id = ""
	request_generation = -1
	if target_id.is_empty() or generation != session_generation:
		return
	if result != HTTPRequest.RESULT_SUCCESS or response_code != 200:
		_emit_failure(target_id, generation, "VOICE_REASON_SERVICE_UNAVAILABLE")
		return
	var parsed = JSON.parse_string(body.get_string_from_utf8())
	if not parsed is Dictionary:
		_emit_failure(target_id, generation, "VOICE_REASON_RESULT_INVALID")
		return
	var accepted := bool(parsed.get("accepted", false))
	var transcript := str(parsed.get("text", ""))
	var reason := str(parsed.get("reason", "VOICE_REASON_CLARIFY"))
	if accepted:
		_clear_recovery(false)
		GameState.set_interaction_time_frozen(false)
		recognition_finished.emit(target_id, true, transcript, reason)
	else:
		recovery_active = true
		recovery_target_id = target_id
		recognition_finished.emit(target_id, false, transcript, reason)

func _emit_failure(target_id: String, generation: int, reason: String) -> void:
	if generation != session_generation:
		return
	recovery_active = true
	recovery_target_id = target_id
	recognition_finished.emit(target_id, false, "", reason)

func _request_in_flight() -> bool:
	return not pending_target_id.is_empty() or (http_request != null and http_request.get_http_client_status() != HTTPClient.STATUS_DISCONNECTED)

func _clear_recovery(_unused_notify: bool) -> void:
	recovery_active = false
	recovery_target_id = ""
