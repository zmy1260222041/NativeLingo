extends Node
## Dynamic dialogue boundary for the Godot game. The client sends a transcript
## and a server-owned scenario context; it never sends an OpenAI credential or
## arbitrary text to TTS.

signal dialogue_pending(npc_id: String, scenario_id: String)
signal scenario_opened(npc_id: String, scenario_id: String, text: String)
signal dialogue_ready(npc_id: String, reply_id: String, text: String)
signal dialogue_failed(npc_id: String, reason: String)
signal dialogue_closed(npc_id: String, reason: String)
signal town_exchange_finished(npc_id: String, player_text: String, reply_text: String, opening: bool)
## FR-45 speaker subtitle: the player's own words are mirrored the moment the
## transcript is locked in; marks arrive later with the scored player_turn.
signal player_turn_displayed(npc_id: String, transcript: String)
signal player_turn_scored(npc_id: String, transcript: String, errors: Array)
signal service_turn_updated(npc_id: String, detail: Dictionary)

const LOCAL_URL := "http://127.0.0.1:17831/game/dialogue"
const CLOUD_PATH := "/game/dialogue"
const LOCAL_PREWARM_URL := "http://127.0.0.1:17831/game/prewarm"
const CLOUD_PREWARM_PATH := "/game/prewarm"
const ENABLED_SETTING := "stranger_ai_dialogue/enabled"
const CLOUD_BASE_URL_SETTING := "stranger_cloud/base_url"
const CLOUD_WEB_RELATIVE_SETTING := "stranger_cloud/web_relative_urls"
const CLOUD_ENABLED_SETTING := "stranger_cloud/enabled"
const CLOUD_CA_PATH_SETTING := "stranger_cloud/ca_cert_path"
const CLOUD_INSECURE_DEV_SETTING := "stranger_cloud/allow_insecure_dev"
const CLOUD_VOICE_FEATURE := "stranger_cloud_voice"
const MAX_TEXT_WORDS := 30
const MAX_TEXT_SENTENCES := 2
const MAX_HISTORY := 8
const SESSION_TIMEOUT_SECONDS := 90.0
const RESPONSE_STATES := ["awaiting_player", "awaiting_follow_up", "closed"]
## The server streams reply PCM inside the SSE dialogue response; if it never
## arrives (old server, dropped events, TTS failure) fall back to the classic
## /game/tts fetch after this delay.
## Keep the live plane inside NFR-9. Once speaking is committed, a missing first
## audio event must fall back quickly enough that the classic TTS fetch can still
## start playback inside the three-second end-to-end budget.
const AUDIO_FALLBACK_SECONDS := 0.9
## After audio starts, this timer becomes an inactivity watchdog. Valid longer
## replies may exceed it in total as long as chunks continue to arrive.
const AUDIO_STALL_SECONDS := 1.5
const MAX_STREAM_AUDIO_BYTES := 2 * 1024 * 1024
const PREWARM_THROTTLE_SECONDS := 10.0
## FR-45: only the tier enum leaves the device; anything else is dropped.
const VALID_PLAYER_TIERS := ["infant", "toddler", "youth", "professional"]

var availability_override: Variant = null
var request_override: Callable
var http_request: HTTPRequest
var current_npc_id := ""
var current_scenario_id := ""
var session_id := ""
var retry_count := 0
var pending_transcript := ""
var pending_pronunciation := -1.0
## Transcript of the in-flight turn. pending_transcript is cleared once the
## reply commits, but the scored marks and the vocabulary rewiring still need
## the exact words the player said.
var current_turn_transcript := ""
var current_reply_id := ""
var current_reply_text := ""
var current_reply_speech_act := ""
var current_transaction_complete := false
var current_confirmed_item := ""
## Diagnostics for live acceptance tests and logs. These never drive rewards;
## reply identity and validated player_turn remain authoritative.
var last_reply_source := ""
var last_reply_model := ""
var session_timer: Timer
var _pinned_certificate: X509Certificate
var _stream_client: HTTPClient
var _stream_buffer := ""
var _stream_request_sent := false
var _stream_body := ""
var _score_received := false
var _audio_finished_pending := false
var _pending_next_state := "awaiting_follow_up"
## True while the desktop SSE path owns this turn: reply audio is expected to
## arrive as audio_begin/audio/audio_end events instead of a /game/tts fetch.
var _streaming_response := false
var _awaiting_stream_audio := false
var _stream_audio := PackedByteArray()
var _stream_audio_seq := -1
var _stream_audio_sample_rate := 24000
var audio_fallback_timer: Timer
var prewarm_request: HTTPRequest
var _prewarm_last_msec := 0


func _ready() -> void:
	process_mode = Node.PROCESS_MODE_ALWAYS
	http_request = HTTPRequest.new()
	http_request.name = "NpcDialogueHttp"
	http_request.timeout = 45.0
	http_request.request_completed.connect(_on_request_completed)
	add_child(http_request)
	session_timer = Timer.new()
	session_timer.name = "NpcDialogueSessionTimeout"
	session_timer.one_shot = true
	session_timer.wait_time = SESSION_TIMEOUT_SECONDS
	session_timer.timeout.connect(_on_session_timeout)
	add_child(session_timer)
	audio_fallback_timer = Timer.new()
	audio_fallback_timer.name = "NpcDialogueAudioFallback"
	audio_fallback_timer.one_shot = true
	audio_fallback_timer.wait_time = AUDIO_FALLBACK_SECONDS
	audio_fallback_timer.timeout.connect(_on_audio_fallback_timeout)
	add_child(audio_fallback_timer)
	prewarm_request = HTTPRequest.new()
	prewarm_request.name = "NpcDialoguePrewarmHttp"
	# The request is asynchronous and overlaps recording. Allow enough time for
	# one dropped proxy connection to be replaced before the transcript arrives.
	prewarm_request.timeout = 6.0
	add_child(prewarm_request)
	var npc_voice := get_tree().root.get_node_or_null(NodePath("NpcVoice"))
	if npc_voice != null:
		npc_voice.line_audio_ready.connect(_on_reply_audio_ready)
		npc_voice.line_audio_finished.connect(_on_reply_audio_finished)
		npc_voice.line_audio_failed.connect(_on_reply_audio_failed)
	if cloud_mode_enabled():
		_configure_cloud_tls()
	set_process(false)


func _process(_delta: float) -> void:
	if _stream_client != null:
		_poll_dialogue_stream()


func enabled() -> bool:
	return bool(ProjectSettings.get_setting(ENABLED_SETTING, true))


func is_available() -> bool:
	if availability_override != null:
		return bool(availability_override)
	if not enabled():
		return false
	if cloud_mode_enabled():
		return not cloud_token().is_empty()
	return true


func cloud_mode_enabled() -> bool:
	return bool(ProjectSettings.get_setting(CLOUD_ENABLED_SETTING, false)) or OS.has_feature(CLOUD_VOICE_FEATURE)


func cloud_token() -> String:
	if not is_inside_tree():
		return ""
	var config := ConfigFile.new()
	if config.load("user://stranger_cloud.cfg") != OK:
		return ""
	return str(config.get_value("stranger_cloud", "token", "")).strip_edges()


func begin_scenario(npc_id: String, scenario_id := "", announce_entry := true) -> bool:
	var npc := npc_id.strip_edges().to_lower()
	if npc.is_empty():
		return false
	if is_session_active_for(npc):
		return true
	if has_active_session():
		cancel("VOICE_REASON_DIALOGUE_CANCELLED")
	var selected := scenario_id.strip_edges().to_lower()
	if selected.is_empty():
		selected = _registry().next_scenario_for(npc)
	if not _registry().has_scenario(selected):
		return false
	_dialogue().finish_word_practice()
	if not _dialogue().begin_scenario(npc, selected):
		return false
	current_npc_id = npc
	current_scenario_id = selected
	session_id = "%s-%s" % [npc, Time.get_ticks_msec()]
	retry_count = 0
	pending_transcript = ""
	pending_pronunciation = -1.0
	current_reply_id = ""
	current_reply_text = ""
	current_reply_speech_act = ""
	current_transaction_complete = false
	current_confirmed_item = ""
	_score_received = false
	_audio_finished_pending = false
	_pending_next_state = "awaiting_follow_up"
	_close_dialogue_stream()
	var runner := _runner()
	if runner == null or not runner.begin(npc, selected):
		_dialogue().close(npc)
		current_npc_id = ""
		current_scenario_id = ""
		session_id = ""
		return false
	if GameState.presentation_state.get("chapter") != "campus":
		var known: Dictionary = GameState.presentation_state.get("town_contacts", {}).get(npc, {})
		var previous: Array = []
		for turn in known.get("history", []):
			if turn is Dictionary and turn.get("role") in ["player", "npc"] and turn.get("text") is String:
				previous.append({"role": turn.role, "text": str(turn.text).left(1000)})
		_dialogue().sessions[npc]["history"] = previous.slice(maxi(0, previous.size() - MAX_HISTORY))
	var scenario: Dictionary = _registry().get_scenario(selected)
	var entry_dialogue := str(scenario.get("entry_dialogue", "")).strip_edges()
	_dialogue().await_player(npc, "entry_dialogue")
	if announce_entry and not entry_dialogue.is_empty():
		scenario_opened.emit(npc, selected, entry_dialogue)
	_restart_session_timeout()
	return true


func is_session_active_for(npc_id: String) -> bool:
	var npc := npc_id.strip_edges().to_lower()
	return not current_npc_id.is_empty() and current_npc_id == npc and _dialogue().has_dynamic_session(npc)


func has_active_session() -> bool:
	return not current_npc_id.is_empty() and _dialogue().has_dynamic_session(current_npc_id)


func active_npc_id() -> String:
	return current_npc_id


func scenario_id() -> String:
	return current_scenario_id


var current_turn_is_opening := false

func start_social_opening(npc: String, scenario: String, day: int) -> bool:
	if _registry().get_scenario(scenario).get("conversation_mode") != "social": return false
	if not begin_scenario(npc, scenario, false): return false
	return submit_transcript("[NPC opens conversation]", {"turn_kind": "opening", "day": day})

func _reply_within_limits(text: String) -> bool:
	var social: bool = _registry().get_scenario(current_scenario_id).get("conversation_mode") == "social"
	return text.split(" ", false).size() <= (60 if social else MAX_TEXT_WORDS) and _sentence_count(text) <= (3 if social else MAX_TEXT_SENTENCES)

func submit_transcript(transcript: String, game_context: Dictionary = {}) -> bool:
	var text := transcript.strip_edges()
	if text.is_empty() or not is_session_active_for(current_npc_id):
		return false
	if not current_reply_id.is_empty() or _awaiting_stream_audio:
		return false
	if http_request == null or http_request.get_http_client_status() != HTTPClient.STATUS_DISCONNECTED or _stream_busy():
		return false
	if not is_available():
		_fail("VOICE_REASON_SERVICE_UNAVAILABLE")
		return false
	current_turn_is_opening = game_context.get("turn_kind") == "opening" and _registry().get_scenario(current_scenario_id).get("conversation_mode") == "social"
	if not _dialogue().begin_generation(current_npc_id, text, not current_turn_is_opening):
		return false
	pending_transcript = text
	pending_pronunciation = float(game_context.get("pronunciation", -1.0))
	current_turn_transcript = text
	if not current_turn_is_opening: player_turn_displayed.emit(current_npc_id, text)
	retry_count = 0
	_score_received = false
	last_reply_source = ""
	last_reply_model = ""
	_audio_finished_pending = false
	_pending_next_state = "awaiting_follow_up"
	_clear_stream_audio_state()
	_restart_session_timeout()
	GameState.set_interaction_time_frozen(true)
	if not _send_request(game_context):
		GameState.set_interaction_time_frozen(false)
		return false
	return true


func reject_empty_transcript(reason := "VOICE_REASON_CLARIFY") -> void:
	if not has_active_session():
		return
	var safe_reason := reason if not reason.strip_edges().is_empty() else "VOICE_REASON_CLARIFY"
	GameState.set_interaction_time_frozen(false)
	_dialogue().dynamic_failed(current_npc_id, safe_reason)
	dialogue_failed.emit(current_npc_id, safe_reason)
	_restart_session_timeout()


func _send_request(game_context: Dictionary = {}) -> bool:
	dialogue_pending.emit(current_npc_id, current_scenario_id)
	var context := game_context.duplicate(true)
	if GameState.presentation_state.get("chapter") == "campus": context["chapter"] = "campus"
	else:
		var contact: Dictionary = GameState.presentation_state.get("town_contacts", {}).get(current_npc_id, {})
		context["town_contact"] = {"completed_exchanges": int(contact.get("completed_exchanges", 0)), "days_met": contact.get("days", []).size()}
		if current_npc_id == "rowan": context["town_contact"]["helped_rowan"] = GameState.completed_steps.has("help_rowan")
	if pending_pronunciation >= 0.0:
		context["pronunciation"] = pending_pronunciation
	var runner := _runner()
	if runner != null:
		context.merge(runner.game_context(current_npc_id), false)
	var tier := _player_tier()
	if not tier.is_empty():
		context["player_level"] = tier
	var body := {
		"session_id": session_id,
		"npc_id": current_npc_id,
		"scenario_id": current_scenario_id,
		"transcript": pending_transcript,
		"history": _recent_history(),
		"game_context": context,
		"retry": retry_count,
		"require_live_dialogue": bool(ProjectSettings.get_setting("stranger_novel/enabled", false)),
	}
	var headers := PackedStringArray(["Content-Type: application/json"])
	if cloud_mode_enabled():
		headers.append("Authorization: Bearer " + cloud_token())
	var error: int
	if request_override.is_valid():
		error = int(request_override.call(_dialogue_url(), headers, HTTPClient.METHOD_POST, JSON.stringify(body)))
	else:
		var body_text := JSON.stringify(body)
		if _should_stream():
			# HTTPRequest completes a length-less SSE response immediately with
			# an empty body, so desktop streaming must drive a raw HTTPClient.
			headers.append("Accept: text/event-stream")
			error = _begin_dialogue_stream(headers, body_text)
			if error == OK:
				_streaming_response = true
				set_process(true)
		else:
			error = http_request.request(_dialogue_url(), headers, HTTPClient.METHOD_POST, body_text)
	if error != OK:
		_retry_or_fail("VOICE_REASON_SERVICE_UNAVAILABLE")
		return false
	return true


func cancel(reason := "VOICE_REASON_DIALOGUE_CANCELLED") -> void:
	if not has_active_session():
		return
	GameState.set_interaction_time_frozen(false)
	_clear_stream_audio_state()
	var npc := current_npc_id
	_close_dialogue_stream()
	if http_request != null and http_request.get_http_client_status() != HTTPClient.STATUS_DISCONNECTED:
		http_request.cancel_request()
	var npc_voice := get_tree().root.get_node_or_null(NodePath("NpcVoice"))
	if npc_voice != null:
		npc_voice.cancel_reply(npc)
	_close_session(reason)


func _dialogue_url() -> String:
	if not cloud_mode_enabled():
		return LOCAL_URL
	if OS.has_feature("web") and bool(ProjectSettings.get_setting(CLOUD_WEB_RELATIVE_SETTING, true)):
		return CLOUD_PATH
	return str(ProjectSettings.get_setting(CLOUD_BASE_URL_SETTING, "")).trim_suffix("/") + CLOUD_PATH


func _should_stream() -> bool:
	if request_override.is_valid():
		return false
	if OS.has_feature("web") or DisplayServer.get_name() == "headless":
		return false
	return true


func _looks_like_sse(text: String) -> bool:
	var trimmed := text.strip_edges()
	return trimmed.begins_with("event:") or trimmed.contains("\nevent:") or trimmed.contains("\r\nevent:")


func _apply_sse_body(raw: String) -> void:
	var normalized := raw.replace("\r\n", "\n").replace("\r", "\n")
	for block in normalized.split("\n\n"):
		if not block.strip_edges().is_empty():
			_handle_sse_block(block)
	if has_active_session() and current_reply_id.is_empty() and not _score_received:
		_retry_or_fail("VOICE_REASON_RESULT_INVALID")


func _stream_busy() -> bool:
	return _stream_client != null and _stream_client.get_status() != HTTPClient.STATUS_DISCONNECTED


func _close_dialogue_stream() -> void:
	if _stream_client != null:
		_stream_client.close()
	_stream_client = null
	_stream_buffer = ""
	_stream_request_sent = false
	_stream_body = ""
	_streaming_response = false
	_clear_stream_audio_state()
	set_process(false)


func _split_http_url(url: String) -> Dictionary:
	var tls := url.begins_with("https://")
	var rest := url.trim_prefix("https://").trim_prefix("http://")
	var slash := rest.find("/")
	var hostport := rest if slash < 0 else rest.substr(0, slash)
	var path := "/" if slash < 0 else rest.substr(slash)
	var host := hostport
	var port := 443 if tls else 80
	var colon := hostport.rfind(":")
	if colon > 0:
		host = hostport.substr(0, colon)
		port = int(hostport.substr(colon + 1))
	return {"host": host, "port": port, "path": path, "tls": tls}


func _begin_dialogue_stream(headers: PackedStringArray, body: String) -> int:
	_close_dialogue_stream()
	var parsed: Dictionary = _split_http_url(_dialogue_url())
	if str(parsed.get("host", "")).is_empty():
		return ERR_CANT_CONNECT
	_stream_client = HTTPClient.new()
	_stream_body = body
	_stream_buffer = ""
	_stream_request_sent = false
	var tls_ok := not bool(parsed.get("tls", false))
	var err: int
	if bool(parsed.get("tls", false)):
		var ca_path := str(ProjectSettings.get_setting(CLOUD_CA_PATH_SETTING, "")).strip_edges()
		var certificate := _load_pinned_certificate(ca_path)
		if certificate != null:
			err = _stream_client.connect_to_host(str(parsed["host"]), int(parsed["port"]), TLSOptions.client(certificate))
			tls_ok = err == OK
		elif bool(ProjectSettings.get_setting(CLOUD_INSECURE_DEV_SETTING, false)):
			err = _stream_client.connect_to_host(str(parsed["host"]), int(parsed["port"]), TLSOptions.client_unsafe())
			tls_ok = err == OK
		else:
			err = _stream_client.connect_to_host(str(parsed["host"]), int(parsed["port"]))
			tls_ok = err == OK
	else:
		err = _stream_client.connect_to_host(str(parsed["host"]), int(parsed["port"]))
	if err != OK or not tls_ok:
		_close_dialogue_stream()
		return err if err != OK else ERR_CANT_CONNECT
	_stream_client.set_meta("path", parsed["path"])
	_stream_client.set_meta("headers", headers)
	return OK


func _poll_dialogue_stream() -> void:
	if _stream_client == null:
		return
	_stream_client.poll()
	var status := _stream_client.get_status()
	if status == HTTPClient.STATUS_CONNECTING or status == HTTPClient.STATUS_RESOLVING:
		return
	if status == HTTPClient.STATUS_CONNECTED and not _stream_request_sent:
		var headers: PackedStringArray = _stream_client.get_meta("headers", PackedStringArray())
		var path := str(_stream_client.get_meta("path", "/game/dialogue"))
		var err := _stream_client.request(HTTPClient.METHOD_POST, path, headers, _stream_body)
		_stream_request_sent = true
		if err != OK:
			_close_dialogue_stream()
			_retry_or_fail("VOICE_REASON_SERVICE_UNAVAILABLE")
		return
	if status == HTTPClient.STATUS_BODY:
		var chunk := _stream_client.read_response_body_chunk()
		if chunk.size() > 0:
			_stream_buffer += chunk.get_string_from_utf8()
			if _stream_client.has_response() and _stream_client.get_response_code() == 200:
				_drain_sse_buffer()
		return
	if status == HTTPClient.STATUS_DISCONNECTED:
		var disconnected_client := _stream_client
		var code := 200
		if _stream_client.has_response():
			code = _stream_client.get_response_code()
		if code != 200:
			var reason := _response_reason(_stream_buffer.to_utf8_buffer(), "VOICE_REASON_SERVICE_UNAVAILABLE")
			_close_dialogue_stream()
			_retry_or_fail(reason)
			return
		if not _stream_buffer.is_empty():
			_drain_sse_buffer(true)
		if _stream_client != disconnected_client:
			# Drain already reacted (e.g. an error event retried with a fresh
			# stream, or done closed it); touching it here would kill that result.
			return
		var incomplete_score := has_active_session() and not _score_received
		if _score_received and _awaiting_stream_audio:
			_stream_audio_finish({"npc_id": current_npc_id, "reply_id": current_reply_id}, true)
		_close_dialogue_stream()
		if incomplete_score:
			_retry_or_fail("VOICE_REASON_SERVICE_UNAVAILABLE")
		return
	if status == HTTPClient.STATUS_CONNECTION_ERROR or status == HTTPClient.STATUS_TLS_HANDSHAKE_ERROR:
		_close_dialogue_stream()
		_retry_or_fail("VOICE_REASON_SERVICE_UNAVAILABLE")


func _drain_sse_buffer(flush := false) -> void:
	while true:
		var split := _stream_buffer.find("\n\n")
		if split < 0:
			break
		var block := _stream_buffer.substr(0, split)
		_stream_buffer = _stream_buffer.substr(split + 2)
		_handle_sse_block(block)
	if flush and not _stream_buffer.strip_edges().is_empty():
		_handle_sse_block(_stream_buffer)
		_stream_buffer = ""


func _handle_sse_block(block: String) -> void:
	var event_name := "message"
	var data_lines: PackedStringArray = PackedStringArray()
	for line in block.split("\n"):
		var trimmed := line.strip_edges()
		if trimmed.begins_with("event:"):
			event_name = trimmed.substr(6).strip_edges()
		elif trimmed.begins_with("data:"):
			data_lines.append(trimmed.substr(5).strip_edges())
	if data_lines.is_empty():
		return
	var parsed = JSON.parse_string("\n".join(data_lines))
	if not parsed is Dictionary:
		return
	match event_name:
		"speaking":
			_apply_speaking(parsed)
		"score":
			_apply_score(parsed)
		"audio_begin":
			_stream_audio_begin(parsed)
		"audio":
			_stream_audio_chunk(parsed)
		"audio_end":
			_stream_audio_finish(parsed, false)
		"audio_failed":
			_stream_audio_finish(parsed, true)
		"error":
			_retry_or_fail(str(parsed.get("reason", "VOICE_REASON_SERVICE_UNAVAILABLE")))
		"done":
			_close_dialogue_stream()


func _configure_cloud_tls() -> void:
	if OS.has_feature("web") or http_request == null:
		return
	var ca_path := str(ProjectSettings.get_setting(CLOUD_CA_PATH_SETTING, "")).strip_edges()
	var certificate := _load_pinned_certificate(ca_path)
	if certificate != null:
		http_request.set_tls_options(TLSOptions.client(certificate))
	elif bool(ProjectSettings.get_setting(CLOUD_INSECURE_DEV_SETTING, false)):
		http_request.set_tls_options(TLSOptions.client_unsafe())


func _load_pinned_certificate(ca_path: String) -> X509Certificate:
	if _pinned_certificate != null:
		return _pinned_certificate
	if ca_path.is_empty() or not FileAccess.file_exists(ca_path):
		return null
	var candidate := X509Certificate.new()
	if candidate.load(ca_path) == OK:
		_pinned_certificate = candidate
		return candidate
	return null


func _on_request_completed(result: int, response_code: int, _headers: PackedStringArray, body: PackedByteArray) -> void:
	if not has_active_session():
		return
	if result != HTTPRequest.RESULT_SUCCESS:
		_retry_or_fail("VOICE_REASON_SERVICE_UNAVAILABLE")
		return
	if response_code != 200:
		var reason := _response_reason(body, "VOICE_REASON_SERVICE_UNAVAILABLE")
		if response_code == 401 or response_code == 403:
			_fail("VOICE_REASON_CLOUD_UNAUTHORIZED", true)
		elif response_code == 422:
			_retry_or_fail(reason)
		elif response_code in [400, 408, 429, 500, 502, 503, 504]:
			_retry_or_fail(reason)
		else:
			_fail(reason, true)
		return
	var text := body.get_string_from_utf8()
	if _looks_like_sse(text):
		_apply_sse_body(text)
		return
	var parsed = JSON.parse_string(text)
	if not parsed is Dictionary:
		_retry_or_fail("VOICE_REASON_RESULT_INVALID")
		return
	if not _apply_speaking(parsed):
		return
	_apply_score(parsed)


func _apply_speaking(parsed: Dictionary) -> bool:
	if bool(ProjectSettings.get_setting("stranger_novel/enabled", false)) and str(parsed.get("source", "")).to_lower() == "stub":
		_retry_or_fail("VOICE_REASON_SERVICE_UNAVAILABLE")
		return false
	var validation := _validate_speaking(parsed)
	if not bool(validation.get("ok", false)):
		_retry_or_fail(str(validation.get("reason", "VOICE_REASON_RESULT_INVALID")))
		return false
	var reply_id := str(parsed["reply_id"])
	var text := str(parsed["text"])
	last_reply_source = str(parsed.get("source", "")).strip_edges().to_lower()
	var next_state := str(parsed.get("next_state", "awaiting_follow_up"))
	if next_state.is_empty() or not next_state in RESPONSE_STATES:
		next_state = "awaiting_follow_up"
	if not _dialogue().accept_dynamic_reply(current_npc_id, reply_id, text, next_state):
		_retry_or_fail("VOICE_REASON_RESULT_INVALID")
		return false
	current_reply_id = reply_id
	current_reply_text = text
	if str(parsed.get("speech_act", "")).strip_edges() != "":
		current_reply_speech_act = str(parsed.get("speech_act", ""))
	_pending_next_state = next_state
	if _streaming_response:
		# The server streams this reply's PCM right after the speaking event;
		# wait for it (audio_end → feed_reply_pcm) with a timed fallback to the
		# classic /game/tts fetch for older servers and lost events.
		_awaiting_stream_audio = true
		_stream_audio = PackedByteArray()
		_stream_audio_seq = -1
		_stream_audio_sample_rate = 24000
		if audio_fallback_timer != null:
			audio_fallback_timer.start(AUDIO_FALLBACK_SECONDS)
		dialogue_ready.emit(current_npc_id, reply_id, text)
		retry_count = 0
		pending_transcript = ""
		_restart_session_timeout()
		return true
	if not _request_reply_audio():
		return false
	dialogue_ready.emit(current_npc_id, reply_id, text)
	retry_count = 0
	pending_transcript = ""
	_restart_session_timeout()
	return true


func _request_reply_audio() -> bool:
	var npc_voice := get_tree().root.get_node_or_null(NodePath("NpcVoice"))
	if npc_voice == null or not npc_voice.request_reply(current_npc_id, current_reply_id):
		if not current_reply_id.is_empty():
			_fail_reply_audio("VOICE_REASON_SERVICE_UNAVAILABLE")
		return false
	return true


func _stream_reply_matches(parsed: Dictionary) -> bool:
	if not _awaiting_stream_audio:
		return false
	return str(parsed.get("npc_id", "")).strip_edges().to_lower() == current_npc_id \
		and str(parsed.get("reply_id", "")) == current_reply_id


func _stream_audio_begin(parsed: Dictionary) -> void:
	if not _stream_reply_matches(parsed):
		return
	_stream_audio_sample_rate = clampi(int(parsed.get("sample_rate", 24000)), 8000, 96000)
	if audio_fallback_timer != null:
		audio_fallback_timer.start(AUDIO_STALL_SECONDS)


func _stream_audio_chunk(parsed: Dictionary) -> void:
	if not _stream_reply_matches(parsed):
		return
	var seq := int(parsed.get("seq", _stream_audio_seq + 1))
	if seq <= _stream_audio_seq:
		return
	_stream_audio_seq = seq
	var chunk: PackedByteArray = Marshalls.base64_to_raw(str(parsed.get("pcm_b64", "")))
	if chunk.is_empty():
		return
	if _stream_audio.size() + chunk.size() > MAX_STREAM_AUDIO_BYTES:
		_stream_audio_finish(parsed, true)
		return
	_stream_audio.append_array(chunk)
	if audio_fallback_timer != null:
		audio_fallback_timer.start(AUDIO_STALL_SECONDS)


func _stream_audio_finish(parsed: Dictionary, failed: bool) -> void:
	if not _stream_reply_matches(parsed):
		return
	if audio_fallback_timer != null:
		audio_fallback_timer.stop()
	if not _awaiting_stream_audio:
		return
	_awaiting_stream_audio = false
	var npc := current_npc_id
	var reply := current_reply_id
	var sample_rate := _stream_audio_sample_rate
	var pcm := _stream_audio
	_stream_audio = PackedByteArray()
	_stream_audio_seq = -1
	if failed or pcm.size() < 32:
		# Streaming failed: fall back to the /game/tts fetch (server cache or a
		# fresh synthesis) before declaring the turn failed.
		if not reply.is_empty() and _request_reply_audio():
			return
		if current_reply_id == reply:
			_fail_reply_audio("VOICE_REASON_SERVICE_UNAVAILABLE")
		return
	var npc_voice := get_tree().root.get_node_or_null(NodePath("NpcVoice"))
	if npc_voice == null or not npc_voice.feed_reply_pcm(npc, reply, pcm, sample_rate):
		if current_reply_id == reply:
			_fail_reply_audio("VOICE_REASON_SERVICE_UNAVAILABLE")
		return
	GameState.set_interaction_time_frozen(false)


func _on_audio_fallback_timeout() -> void:
	if not _awaiting_stream_audio:
		return
	_awaiting_stream_audio = false
	_stream_audio = PackedByteArray()
	_stream_audio_seq = -1
	_request_reply_audio()


func _clear_stream_audio_state() -> void:
	_awaiting_stream_audio = false
	_stream_audio = PackedByteArray()
	_stream_audio_seq = -1
	if audio_fallback_timer != null:
		audio_fallback_timer.stop()


func prewarm(npc_id: String) -> void:
	## V-press prewarm: keep the server's TTS websocket pool warm while the
	## player is still speaking. Fire-and-forget, throttled, and only for NPCs
	## whose voice turn will actually hit the dialogue service.
	var npc := npc_id.strip_edges().to_lower()
	if npc.is_empty() or not is_available():
		return
	if not is_session_active_for(npc) and not GameState.can_start_service_dialogue(npc):
		return
	if _prewarm_last_msec > 0 and Time.get_ticks_msec() - _prewarm_last_msec < PREWARM_THROTTLE_SECONDS * 1000.0:
		return
	if prewarm_request == null or prewarm_request.get_http_client_status() != HTTPClient.STATUS_DISCONNECTED:
		return
	_prewarm_last_msec = Time.get_ticks_msec()
	var headers := PackedStringArray(["Content-Type: application/json"])
	if cloud_mode_enabled():
		headers.append("Authorization: Bearer " + cloud_token())
	prewarm_request.request(prewarm_url(), headers, HTTPClient.METHOD_POST, JSON.stringify({"npc_id": npc}))


func prewarm_url() -> String:
	if not cloud_mode_enabled():
		return LOCAL_PREWARM_URL
	if OS.has_feature("web") and bool(ProjectSettings.get_setting(CLOUD_WEB_RELATIVE_SETTING, true)):
		return CLOUD_PREWARM_PATH
	return str(ProjectSettings.get_setting(CLOUD_BASE_URL_SETTING, "")).trim_suffix("/") + CLOUD_PREWARM_PATH


func _apply_score(parsed: Dictionary) -> void:
	var player_turn = parsed.get("player_turn", {})
	if not player_turn is Dictionary:
		return
	var score_check := _validate_score(parsed)
	if not bool(score_check.get("ok", false)):
		return
	current_reply_speech_act = str(parsed.get("speech_act", current_reply_speech_act))
	var score_source := str(parsed.get("source", "")).strip_edges().to_lower()
	if not score_source.is_empty():
		last_reply_source = score_source
	last_reply_model = str(parsed.get("model", "")).strip_edges()
	var requested_complete := bool(player_turn.get("transaction_complete", false))
	var confirmed_item := str(player_turn.get("confirmed_item", "")).strip_edges().to_lower()
	var spoken_evidence := bool(player_turn.get("spoken_delivery_confirmed", false))
	# Older/offline service contracts do not send the two audit fields above.
	# The client can still prove the same fact from the already accepted spoken
	# reply and the role-card inventory; a generic acknowledgement remains invalid.
	if confirmed_item.is_empty() or not spoken_evidence:
		confirmed_item = _concrete_item_named_in_reply(current_reply_text, current_reply_speech_act)
		spoken_evidence = not confirmed_item.is_empty()
	var off_inventory := bool(player_turn.get("off_inventory", false))
	var confirmation_valid := requested_complete \
		and spoken_evidence \
		and not off_inventory \
		and _spoken_reply_confirms_item(current_reply_text, confirmed_item, current_reply_speech_act)
	current_transaction_complete = confirmation_valid
	current_confirmed_item = confirmed_item if confirmation_valid else ""
	_pending_next_state = str(parsed.get("next_state", _pending_next_state))
	if requested_complete and not confirmation_valid:
		# A score flag can never close a conversation unless the already-played
		# NPC line itself named and committed the concrete inventory item.
		_pending_next_state = "awaiting_follow_up"
	_score_received = true
	# Score and audio race independently. The audio timeout/end event owns fallback.
	var runner := _runner()
	if runner != null and not current_turn_is_opening:
		var idiomaticity := float(player_turn.get("idiomaticity", 0.0))
		var pronunciation := pending_pronunciation if pending_pronunciation >= 0.0 else idiomaticity
		runner.record_player_turn(current_npc_id, pronunciation, idiomaticity)
	if not current_turn_is_opening:
		_emit_player_turn_scored(player_turn, score_source)
		_record_vocabulary_use(current_turn_transcript)
	service_turn_updated.emit(current_npc_id, {
		"confirmed": confirmation_valid,
		"item": current_confirmed_item if confirmation_valid else str(player_turn.get("requested_item", "")),
		"off_inventory": off_inventory,
	})
	if _audio_finished_pending:
		_settle_finished_audio()


func _validate_speaking(reply: Dictionary) -> Dictionary:
	var reply_id := str(reply.get("reply_id", "")).strip_edges()
	var npc := str(reply.get("npc_id", "")).strip_edges().to_lower()
	var text := str(reply.get("text", "")).strip_edges()
	if not reply_id.begins_with("reply-") or reply_id.length() > 64 or npc != current_npc_id or text.is_empty():
		return {"ok": false, "reason": "VOICE_REASON_RESULT_INVALID"}
	var words := text.split(" ", false)
	if not _reply_within_limits(text):
		return {"ok": false, "reason": "VOICE_REASON_RESULT_INVALID"}
	var lowered := text.to_lower()
	for marker in ["learn english", "your score", "pronunciation", "repeat after", "you should say"]:
		if lowered.contains(marker):
			return {"ok": false, "reason": "VOICE_REASON_DIALOGUE_REJECTED"}
	var gate = reply.get("gate", {})
	if gate is Dictionary:
		var raw_violations = gate.get("violations", [])
		if raw_violations is Array and not raw_violations.is_empty():
			return {"ok": false, "reason": "VOICE_REASON_DIALOGUE_REJECTED"}
		if gate.has("accepted") and not bool(gate.get("accepted", false)):
			return {"ok": false, "reason": "VOICE_REASON_DIALOGUE_REJECTED"}
	var speech_act := str(reply.get("speech_act", "")).strip_edges()
	if not speech_act.is_empty():
		var scenario: Dictionary = _registry().get_scenario(current_scenario_id)
		if not speech_act in scenario.get("allowed_speech_acts", []):
			return {"ok": false, "reason": "VOICE_REASON_DIALOGUE_REJECTED"}
	return {"ok": true}


func _validate_score(reply: Dictionary) -> Dictionary:
	var reply_id := str(reply.get("reply_id", "")).strip_edges()
	var npc := str(reply.get("npc_id", "")).strip_edges().to_lower()
	if current_reply_id.is_empty() or reply_id != current_reply_id or npc != current_npc_id:
		return {"ok": false, "reason": "VOICE_REASON_RESULT_INVALID"}
	var speech_act := str(reply.get("speech_act", "")).strip_edges()
	var scenario: Dictionary = _registry().get_scenario(current_scenario_id)
	if not speech_act.is_empty() and not speech_act in scenario.get("allowed_speech_acts", []):
		return {"ok": false, "reason": "VOICE_REASON_DIALOGUE_REJECTED"}
	var next_state := str(reply.get("next_state", "awaiting_follow_up")).strip_edges()
	if not next_state.is_empty() and not next_state in RESPONSE_STATES:
		return {"ok": false, "reason": "VOICE_REASON_RESULT_INVALID"}
	var player_turn = reply.get("player_turn", {})
	if not player_turn is Dictionary:
		return {"ok": false, "reason": "VOICE_REASON_RESULT_INVALID"}
	var idiomaticity := float(player_turn.get("idiomaticity", -1.0))
	if not is_finite(idiomaticity) or idiomaticity < 0.0 or idiomaticity > 100.0:
		return {"ok": false, "reason": "VOICE_REASON_RESULT_INVALID"}
	return {"ok": true}


func _spoken_reply_confirms_item(text: String, confirmed_item: String, speech_act: String) -> bool:
	var scenario: Dictionary = _registry().get_scenario(current_scenario_id)
	if scenario.is_empty() or confirmed_item.is_empty():
		return false
	if not speech_act in scenario.get("completion_speech_acts", []):
		return false
	var inventory: Array = scenario.get("inventory", [])
	var generic_terms: Array = scenario.get("generic_inventory_terms", [])
	if not confirmed_item in inventory or confirmed_item in generic_terms:
		return false
	var clean := _dialogue_words(text)
	if clean.contains("?") or not _contains_dialogue_phrase(clean, confirmed_item):
		return false
	for marker in [
		"sure thing", "you got it", "got it", "here you go", "here's your", "here is your",
		"coming right up", "i'll get", "i will get", "i can get", "i'll grab", "i will grab",
		"i can grab", "i'll give", "i will give", "i can give", "i'll hand", "i will hand",
		"i can hand", "i'll bring", "i will bring", "i can bring", "i'll lend", "i will lend",
		"i can lend",
	]:
		if _contains_dialogue_phrase(clean, marker):
			return true
	return false


func _concrete_item_named_in_reply(text: String, speech_act: String) -> String:
	var scenario: Dictionary = _registry().get_scenario(current_scenario_id)
	for alias in scenario.get("inventory", []):
		var item := str(alias).strip_edges().to_lower()
		if not item in scenario.get("generic_inventory_terms", []) \
				and not GameState.items.resolve_item(item).is_empty() \
				and _spoken_reply_confirms_item(text, item, speech_act):
			return item
	return ""


func _dialogue_words(text: String) -> String:
	var regex := RegEx.new()
	regex.compile("[^a-z0-9'?]+")
	return regex.sub(text.to_lower(), " ", true).strip_edges()


func _contains_dialogue_phrase(clean_text: String, phrase: String) -> bool:
	var clean_phrase := _dialogue_words(phrase)
	if clean_phrase.is_empty():
		return false
	return (" " + clean_text + " ").contains(" " + clean_phrase + " ")


func _validate_reply(reply: Dictionary) -> Dictionary:
	var reply_id := str(reply.get("reply_id", "")).strip_edges()
	var npc := str(reply.get("npc_id", "")).strip_edges().to_lower()
	var text := str(reply.get("text", "")).strip_edges()
	if not reply_id.begins_with("reply-") or reply_id.length() > 64 or npc != current_npc_id or text.is_empty():
		return {"ok": false, "reason": "VOICE_REASON_RESULT_INVALID"}
	var words := text.split(" ", false)
	if not _reply_within_limits(text):
		return {"ok": false, "reason": "VOICE_REASON_RESULT_INVALID"}
	var lowered := text.to_lower()
	for marker in ["learn english", "your score", "pronunciation", "repeat after", "you should say"]:
		if lowered.contains(marker):
			return {"ok": false, "reason": "VOICE_REASON_DIALOGUE_REJECTED"}
	var gate = reply.get("gate", {})
	if gate is Dictionary:
		var raw_violations = gate.get("violations", [])
		if raw_violations is Array and not raw_violations.is_empty():
			return {"ok": false, "reason": "VOICE_REASON_DIALOGUE_REJECTED"}
		if gate.has("accepted") and not bool(gate.get("accepted", false)):
			return {"ok": false, "reason": "VOICE_REASON_DIALOGUE_REJECTED"}
	var scenario: Dictionary = _registry().get_scenario(current_scenario_id)
	var speech_act := str(reply.get("speech_act", "")).strip_edges()
	if not speech_act in scenario.get("allowed_speech_acts", []):
		return {"ok": false, "reason": "VOICE_REASON_DIALOGUE_REJECTED"}
	var next_state := str(reply.get("next_state", "awaiting_follow_up")).strip_edges()
	if not next_state in RESPONSE_STATES:
		return {"ok": false, "reason": "VOICE_REASON_RESULT_INVALID"}
	var player_turn = reply.get("player_turn", {})
	if not player_turn is Dictionary:
		return {"ok": false, "reason": "VOICE_REASON_RESULT_INVALID"}
	var idiomaticity := float(player_turn.get("idiomaticity", -1.0))
	if not is_finite(idiomaticity) or idiomaticity < 0.0 or idiomaticity > 100.0:
		return {"ok": false, "reason": "VOICE_REASON_RESULT_INVALID"}
	return {"ok": true}


func _sentence_count(text: String) -> int:
	var count := 0
	for character in text:
		if character in ".!?":
			count += 1
	return max(1, count)


func _retry_or_fail(reason: String) -> void:
	_close_dialogue_stream()
	if retry_count < 1 and not pending_transcript.is_empty():
		retry_count += 1
		_dialogue().dynamic_failed(current_npc_id, reason)
		_dialogue().retry_generation(current_npc_id)
		_send_request({"retry": retry_count})
		return
	_fail(reason, reason != "VOICE_REASON_DIALOGUE_REJECTED")


func _fail(reason: String, close_session := false) -> void:
	GameState.set_interaction_time_frozen(false)
	SpeechAdapter.mark_runtime_unavailable(reason)
	_clear_stream_audio_state()
	var npc := current_npc_id
	if not npc.is_empty() and _dialogue().has_dynamic_session(npc):
		_dialogue().dynamic_failed(npc, reason)
	dialogue_failed.emit(npc, reason)
	pending_transcript = ""
	retry_count = 0
	if close_session:
		_close_session(reason)
	else:
		_restart_session_timeout()


func _fail_reply_audio(reason: String) -> void:
	current_reply_id = ""
	current_reply_text = ""
	current_reply_speech_act = ""
	current_transaction_complete = false
	current_confirmed_item = ""
	_fail(reason)


func _on_reply_audio_ready(npc_id: String, reply_id: String) -> void:
	if npc_id == current_npc_id and reply_id == current_reply_id:
		GameState.set_interaction_time_frozen(false)


func _on_reply_audio_finished(npc_id: String, reply_id: String) -> void:
	if npc_id != current_npc_id or reply_id != current_reply_id:
		return
	if not _score_received:
		_audio_finished_pending = true
		return
	_settle_finished_audio()


func _settle_finished_audio() -> void:
	if current_reply_id.is_empty():
		return
	var npc := current_npc_id
	var reply_id := current_reply_id
	var speech_act := current_reply_speech_act
	var transaction_complete := current_transaction_complete
	var confirmed_item := current_confirmed_item
	var next_state: String = str(_dialogue().finish_speaking(npc, reply_id))
	if not _pending_next_state.is_empty():
		next_state = _pending_next_state
	var scenario_id_value := current_scenario_id
	var spoken_text := current_reply_text
	var player_text := current_turn_transcript
	var opening := current_turn_is_opening
	current_reply_id = ""
	current_reply_text = ""
	current_reply_speech_act = ""
	current_transaction_complete = false
	current_confirmed_item = ""
	_audio_finished_pending = false
	var runner := _runner()
	if runner != null:
		runner.apply_validated_reply(
			npc,
			scenario_id_value,
			speech_act,
			next_state,
			transaction_complete,
			confirmed_item,
		)
	if GameState.presentation_state.get("chapter") != "campus":
		town_exchange_finished.emit(npc, player_text, spoken_text, opening)
	if next_state == "closed":
		_close_session("completed", false, false)
	else:
		_restart_session_timeout()


func _on_reply_audio_failed(npc_id: String, reply_id: String, reason: String) -> void:
	if npc_id == current_npc_id and reply_id == current_reply_id:
		_fail_reply_audio(reason)


func _on_session_timeout() -> void:
	if has_active_session():
		_fail("VOICE_REASON_DIALOGUE_TIMEOUT", true)


func _restart_session_timeout() -> void:
	if session_timer != null:
		session_timer.start(SESSION_TIMEOUT_SECONDS)


func _close_session(reason: String, cancel_runner := true, cancel_voice := true) -> void:
	var npc := current_npc_id
	var scenario := current_scenario_id
	if session_timer != null:
		session_timer.stop()
	if not npc.is_empty() and _dialogue().has_dynamic_session(npc):
		_dialogue().close(npc)
	if cancel_voice:
		var npc_voice := get_tree().root.get_node_or_null(NodePath("NpcVoice"))
		if npc_voice != null:
			npc_voice.cancel_reply(npc)
	var runner := _runner()
	if cancel_runner and runner != null:
		runner.cancel(npc, scenario)
	current_npc_id = ""
	current_scenario_id = ""
	session_id = ""
	pending_transcript = ""
	pending_pronunciation = -1.0
	current_turn_transcript = ""
	current_reply_id = ""
	current_reply_text = ""
	current_reply_speech_act = ""
	current_transaction_complete = false
	current_confirmed_item = ""
	_score_received = false
	_audio_finished_pending = false
	_close_dialogue_stream()
	retry_count = 0
	dialogue_closed.emit(npc, reason)


func _recent_history() -> Array:
	var history: Array = _dialogue().history_for(current_npc_id)
	if history.size() <= MAX_HISTORY:
		return history
	return history.slice(history.size() - MAX_HISTORY)


func _response_reason(body: PackedByteArray, fallback: String) -> String:
	var parsed = JSON.parse_string(body.get_string_from_utf8())
	if parsed is Dictionary:
		var reason := str(parsed.get("reason", "")).strip_edges()
		if not reason.is_empty():
			return reason
	return fallback


func _emit_player_turn_scored(player_turn: Dictionary, score_source: String) -> void:
	## FR-45 G-B2: marks exist only for real scored turns; stub turns keep the
	## neutral subtitle exactly as it was first displayed.
	var errors: Array = []
	var raw_errors = player_turn.get("errors", [])
	if raw_errors is Array and score_source in ["gemini", "grok"]:
		for span in raw_errors:
			errors.append(str(span))
	player_turn_scored.emit(current_npc_id, current_turn_transcript, errors)


func _record_vocabulary_use(transcript: String) -> void:
	## FR-45 G-C: real conversational production proves "used" for words the
	## player has already practised aloud (spoken -> used only; the ladder and
	## its rewards stay exactly as FR-36 defined them).
	var text := transcript.strip_edges()
	if text.is_empty():
		return
	var vocabulary := get_tree().root.get_node_or_null(NodePath("Vocabulary"))
	if vocabulary != null:
		vocabulary.record_words_used_from_text(text)


func _player_tier() -> String:
	var tier := str(GameState.vocabulary_tier).strip_edges().to_lower()
	return tier if tier in VALID_PLAYER_TIERS else ""


func _registry() -> Node:
	return get_tree().root.get_node_or_null(NodePath("NpcScenarioRegistry"))


func _dialogue() -> Node:
	return get_tree().root.get_node_or_null(NodePath("Dialogue"))


func _runner() -> Node:
	return get_tree().root.get_node_or_null(NodePath("NpcScenarioRunner"))
