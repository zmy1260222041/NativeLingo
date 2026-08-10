extends Node

signal recognition_finished(target_id: String, accepted: bool, transcript: String, reason: String)
signal recording_state_changed(active: bool)

const SERVICE_URL := "http://127.0.0.1:17831/transcribe"
const RECORDING_PATH := "user://stranger_speech_attempt"

var record_effect: AudioEffectRecord
var microphone_player: AudioStreamPlayer
var http_request: HTTPRequest
var active_target_id := ""

func _ready() -> void:
	http_request = HTTPRequest.new()
	http_request.timeout = 18.0
	http_request.request_completed.connect(_on_request_completed)
	add_child(http_request)

func _exit_tree() -> void:
	if record_effect and record_effect.is_recording_active():
		record_effect.set_recording_active(false)
	if microphone_player:
		microphone_player.stop()
		microphone_player.stream = null
		microphone_player = null
	var bus_index := AudioServer.get_bus_index("SpeechRecord")
	if bus_index >= 0:
		AudioServer.remove_bus(bus_index)
	record_effect = null

func start_recording(target_id: String) -> bool:
	if record_effect == null and DisplayServer.get_name() != "headless":
		_setup_audio_input()
	if record_effect == null or record_effect.is_recording_active() or http_request.get_http_client_status() != HTTPClient.STATUS_DISCONNECTED:
		return false
	active_target_id = target_id
	record_effect.set_recording_active(true)
	recording_state_changed.emit(true)
	return true

func finish_recording() -> void:
	if record_effect == null or not record_effect.is_recording_active():
		return
	var recording := record_effect.get_recording()
	record_effect.set_recording_active(false)
	recording_state_changed.emit(false)
	if recording == null or recording.get_length() < 0.25:
		recognition_finished.emit(active_target_id, false, "", "没有录到足够的声音")
		return
	if recording.save_to_wav(RECORDING_PATH) != OK:
		recognition_finished.emit(active_target_id, false, "", "无法保存本次录音")
		return
	var wav_path := RECORDING_PATH + ".wav"
	var file := FileAccess.open(wav_path, FileAccess.READ)
	if file == null:
		recognition_finished.emit(active_target_id, false, "", "无法读取本次录音")
		return
	var headers := PackedStringArray([
		"Content-Type: audio/wav",
		"X-Stranger-Target: " + active_target_id,
	])
	var error := http_request.request_raw(SERVICE_URL, headers, HTTPClient.METHOD_POST, file.get_buffer(file.get_length()))
	if error != OK:
		recognition_finished.emit(active_target_id, false, "", "本地语音服务未启动")

func _setup_audio_input() -> void:
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
	if result != HTTPRequest.RESULT_SUCCESS or response_code != 200:
		recognition_finished.emit(active_target_id, false, "", "本地语音服务不可用，请按 G 使用手势")
		return
	var parsed = JSON.parse_string(body.get_string_from_utf8())
	if not parsed is Dictionary:
		recognition_finished.emit(active_target_id, false, "", "语音结果无法读取，请免费重试")
		return
	recognition_finished.emit(
		active_target_id,
		bool(parsed.get("accepted", false)),
		str(parsed.get("text", "")),
		str(parsed.get("reason", "没有听清，请免费重试或按 G 使用手势"))
	)
