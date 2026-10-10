extends Node
## Streams speaker events; the shared NpcVoice adapter plays each signed reply in order.
signal line_ready(line: Dictionary)
signal completed(receipt: Dictionary, lines: Array)
## P3-10: "service" (online dialogue unreachable or unavailable), "invalid" (a reply
## that failed validation), "audio" (a reply could not play) or "cloud" (cloud voice
## not activated). The controller words it for the player.
signal failed(kind: String)
signal busy_changed
var busy := false
var text_only := false
var active_turn := ""
var client: HTTPClient
var request: HTTPRequest
var endpoint: Dictionary = {}
var headers := PackedStringArray()
var body_text := ""
var sent := false
var received_response := false
var buffer := PackedByteArray()
var started := 0
var queue: Array = []
var lines: Array = []
var receipt: Dictionary = {}
var playing: Dictionary = {}
var playback_started := 0
var play_reply: Callable = func(npc: String, reply: String): return NpcVoice.request_reply(npc, reply)

func _ready() -> void:
	request = HTTPRequest.new()
	request.timeout = 45
	add_child(request)
	request.request_completed.connect(_json_finished)
	NpcVoice.line_audio_finished.connect(_audio_finished)
	NpcVoice.line_audio_failed.connect(_audio_failed)
	set_process(false)

func cancel() -> void:
	active_turn = ""
	if client != null: client.close()
	client = null
	if request != null: request.cancel_request()
	NpcVoice.stop_all()
	queue.clear()
	playing.clear()
	lines.clear()
	receipt.clear()
	buffer.clear()
	busy = false
	set_process(false)
	busy_changed.emit()

func submit(body: Dictionary, silent := false) -> bool:
	if busy: return false
	var url: String = NpcDialogueService._dialogue_url().replace("/game/dialogue", "/game/campus/dialogue")
	if NpcDialogueService.cloud_mode_enabled() and NpcDialogueService.cloud_token().is_empty():
		failed.emit("cloud")
		return false
	cancel()
	text_only = silent
	active_turn = str(body.turn_id)
	body_text = JSON.stringify(body)
	headers = PackedStringArray(["Content-Type: application/json"])
	if NpcDialogueService.cloud_mode_enabled(): headers.append("Authorization: Bearer " + NpcDialogueService.cloud_token())
	busy = true
	started = Time.get_ticks_msec()
	set_process(true)
	busy_changed.emit()
	if OS.has_feature("web"):
		if request.request(url, headers, HTTPClient.METHOD_POST, body_text) != OK: _fail()
		return busy
	headers.append("Accept: text/event-stream")
	endpoint = NpcDialogueService._split_http_url(url)
	client = HTTPClient.new()
	sent = false
	received_response = false
	var tls: TLSOptions = null
	if endpoint.tls:
		var cert := X509Certificate.new()
		if cert.load("res://certs/nl_ca.pem") == OK: tls = TLSOptions.client(cert)
		else: tls = TLSOptions.client()
	if client.connect_to_host(endpoint.host, endpoint.port, tls) != OK: _fail()
	return busy

func _process(_delta: float) -> void:
	if not busy: return
	if Time.get_ticks_msec() - started > 120000: _fail(); return
	if not playing.is_empty() and Time.get_ticks_msec() - playback_started > 60000: _fail("audio"); return
	if client == null: return
	if client.poll() != OK: _fail(); return
	var status := client.get_status()
	if status == HTTPClient.STATUS_CONNECTED and not sent:
		sent = true
		if client.request(HTTPClient.METHOD_POST, endpoint.path, headers, body_text) != OK: _fail()
	elif status == HTTPClient.STATUS_BODY:
		received_response = true
		if client.get_response_code() != 200: _fail("invalid" if client.get_response_code() == 400 else "service"); return
		var chunk := client.read_response_body_chunk()
		buffer.append_array(chunk)
		if buffer.size() > 256 * 1024: _fail("invalid"); return
		_parse_blocks()
	elif status == HTTPClient.STATUS_CONNECTED and received_response:
		client.close()
		client = null
		if receipt.is_empty(): _fail("invalid")
	elif status in [HTTPClient.STATUS_CANT_CONNECT, HTTPClient.STATUS_CANT_RESOLVE, HTTPClient.STATUS_CONNECTION_ERROR, HTTPClient.STATUS_TLS_HANDSHAKE_ERROR]: _fail()
	elif status == HTTPClient.STATUS_DISCONNECTED and sent and receipt.is_empty(): _fail()

func _parse_blocks() -> void:
	# Decode only complete UTF-8 SSE blocks; a Chinese code point may span reads.
	while busy:
		var end := -1
		for i in range(buffer.size() - 1):
			if buffer[i] == 10 and buffer[i + 1] == 10: end = i; break
		if end < 0: return
		var block := buffer.slice(0, end).get_string_from_utf8()
		buffer = buffer.slice(end + 2)
		var event := ""
		var data := ""
		for line in block.split("\n"):
			if line.begins_with("event:"): event = line.trim_prefix("event:").strip_edges()
			if line.begins_with("data:"): data += line.trim_prefix("data:").strip_edges()
		var parsed = JSON.parse_string(data)
		if not parsed is Dictionary: _fail("invalid"); return
		accept_event(event, parsed)

func accept_event(event: String, data: Dictionary) -> void:
	if not busy or str(data.get("turn_id", active_turn)) != active_turn: return
	if event == "speaking":
		if str(data.get("reply_id", "")).is_empty() or str(data.get("speaker_id", "")).is_empty(): _fail("invalid"); return
		if lines.any(func(line): return line.reply_id == data.reply_id): return
		lines.append(data.duplicate(true))
		queue.append(data.duplicate(true))
		_play_next()
	elif event == "done":
		receipt = data.duplicate(true)
		_finish_if_ready()
	elif event == "error": _fail("service" if data.get("reason") == "campus_unavailable" else "invalid")

func _play_next() -> void:
	if not playing.is_empty() or queue.is_empty(): _finish_if_ready(); return
	playing = queue.pop_front()
	playback_started = Time.get_ticks_msec()
	line_ready.emit(playing)
	if text_only:
		playing = {}
		call_deferred("_play_next")
	else:
		play_reply.call(str(playing.speaker_id), str(playing.reply_id))

func _audio_finished(npc: String, id: String) -> void:
	if not busy or playing.is_empty() or playing.reply_id != id or playing.speaker_id != npc: return
	playing = {}
	_play_next()

func _audio_failed(npc: String, id: String, _reason: String) -> void:
	if busy and playing.get("reply_id") == id and playing.get("speaker_id") == npc: _fail("audio")

func _finish_if_ready() -> void:
	if not busy or receipt.is_empty() or not queue.is_empty() or not playing.is_empty(): return
	var done := receipt.duplicate(true)
	var spoken := lines.duplicate(true)
	if client != null: client.close()
	client = null
	busy = false
	set_process(false)
	busy_changed.emit()
	completed.emit(done, spoken)

func _json_finished(result: int, code: int, _headers: PackedStringArray, data: PackedByteArray) -> void:
	if not busy: return
	if result != HTTPRequest.RESULT_SUCCESS or code != 200: _fail("invalid" if code == 400 else "service"); return
	var parsed = JSON.parse_string(data.get_string_from_utf8())
	if not parsed is Dictionary or not parsed.get("events") is Array: _fail("invalid"); return
	for event in parsed.events: accept_event(str(event.get("event", "")), event.get("data", {}))

func _fail(kind := "service") -> void:
	cancel()
	failed.emit(kind)
