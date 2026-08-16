extends SceneTree
## Headless RPC client that drives a running game's control port (6505) to
## capture multi-view environment screenshots for art-bible §8.8 review.
##
## Usage (from the game/ directory, with the rendered game already running):
##   /Applications/Godot-4.6.app/Contents/MacOS/Godot --headless \
##       -s res://tools/rpc_env_review.gd -- --views <json> [--out <dir>] [--settle-ms 400]
##
## The views JSON is an array of:
##   { "name": "...", "position": "x,y,z", "look_at": "x,y,z",
##     "fov": 60.0, "day_time": 0.35, "max_dim": 1280 }

const PORT := 6505
const SETTLE_FRAMES := 25

var _peer := WebSocketPeer.new()
var _pending_id := 0
var _responses: Dictionary = {}
var _views: Array = []
var _out_dir := ""
var _settle_ms := 420
var _captured := 0
var _hud_hidden := false
var _restore_only := false


func _init() -> void:
	var args := OS.get_cmdline_user_args()
	var views_path := ""
	var i := 0
	while i < args.size():
		var arg := args[i]
		if arg == "--views" and i + 1 < args.size():
			views_path = args[i + 1]
			i += 2
		elif arg == "--out" and i + 1 < args.size():
			_out_dir = args[i + 1]
			i += 2
		elif arg == "--restore":
			_restore_only = true
			i += 1
		elif arg == "--settle-ms" and i + 1 < args.size():
			_settle_ms = int(args[i + 1])
			i += 2
		else:
			i += 1
	if views_path.is_empty() and not "--restore" in args:
		push_error("rpc_env_review: --views <json> is required")
		quit(2)
		return
	if _out_dir.is_empty():
		_out_dir = OS.get_user_data_dir() + "/env_review"
	if _restore_only:
		DirAccess.make_dir_recursive_absolute(OS.get_user_data_dir())
		var err0 := _peer.connect_to_url("ws://127.0.0.1:%d" % PORT)
		if err0 != OK:
			quit(3)
		return
	var file := FileAccess.open(views_path, FileAccess.READ)
	if file == null:
		push_error("rpc_env_review: cannot read views file: %s" % views_path)
		quit(2)
		return
	var parsed = JSON.parse_string(file.get_as_text())
	file.close()
	if parsed == null or not parsed is Array or (parsed as Array).is_empty():
		push_error("rpc_env_review: views file must be a non-empty JSON array")
		quit(2)
		return
	_views = parsed
	DirAccess.make_dir_recursive_absolute(_out_dir)
	var err := _peer.connect_to_url("ws://127.0.0.1:%d" % PORT)
	if err != OK:
		push_error("rpc_env_review: cannot connect to control port %d (err %d)" % [PORT, err])
		quit(3)
		return
	print("rpc_env_review: connected, %d views -> %s" % [_views.size(), _out_dir])


func _process(_delta: float) -> bool:
	_peer.poll()
	var state := _peer.get_ready_state()
	if state == WebSocketPeer.STATE_OPEN:
		_drain_messages()
		_pump_capture_queue()
	elif state == WebSocketPeer.STATE_CLOSED:
		if _captured > 0 or _restore_only:
			_call_rpc("game.restore_view", {})
			print("rpc_env_review: done captured=%d" % _captured)
			quit(0)
		else:
			push_error("rpc_env_review: control port closed before any capture")
			quit(4)
	return false


func _drain_messages() -> void:
	while _peer.get_available_packet_count() > 0:
		var message := _peer.get_packet().get_string_from_utf8()
		var parsed = JSON.parse_string(message)
		if parsed is Dictionary and parsed.has("id"):
			_responses[int(parsed.id)] = parsed


func _pump_capture_queue() -> void:
	if _views.is_empty():
		if _captured > 0 or _restore_only:
			OS.delay_msec(200)
			_call_rpc("game.restore_view", {})
			_call_rpc("game.set_property", {"node_path": "/root/Main/HUD", "property": "visible", "value": true})
			_call_rpc("control.freeze", {"frozen": false})
		_peer.close()
		return
	if not _hud_hidden:
		_hud_hidden = true
		_call_rpc("game.set_property", {"node_path": "/root/Main/HUD", "property": "visible", "value": false})
	var view: Dictionary = _views[0]
	var view_name := String(view.get("name", "view_%d" % _captured))
	# 1. freeze + optional day time
	_call_rpc("control.freeze", {"frozen": true})
	if view.has("day_time"):
		_call_rpc("game.set_property", {
			"node_path": "/root/GameState",
			"property": "day_time",
			"value": float(view.day_time),
		})
	# 2. capture (server writes the file; window may stay in background)
	OS.delay_msec(120)
	var capture := _call_rpc("game.capture_view", {
		"position": String(view.get("position", "0,3,0")),
		"look_at": String(view.get("look_at", "0,1,0")),
		"fov": float(view.get("fov", 60.0)),
		"max_dim": int(view.get("max_dim", 800)),
		"name": view_name,
	}, 60000)
	if capture.has("format") and String(capture.get("format", "")) == "jpg" and capture.has("path"):
		var src_path := String(capture.path)
		var out_path := _out_dir + "/" + view_name + ".jpg"
		var src := FileAccess.open(src_path, FileAccess.READ)
		if src != null:
			var buffer := src.get_buffer(src.get_length())
			src.close()
			var out := FileAccess.open(out_path, FileAccess.WRITE)
			if out != null:
				out.store_buffer(buffer)
				out.close()
				_captured += 1
				print("rpc_env_review: saved %s (%d KB)" % [out_path, buffer.size() / 1024])
	else:
		push_error("rpc_env_review: capture failed for %s: %s" % [view_name, JSON.stringify(capture)])
	_views.pop_front()


func _call_rpc(method: String, params: Dictionary, timeout_ms := 5000) -> Dictionary:
	_pending_id += 1
	var id := _pending_id
	var request := JSON.stringify({"jsonrpc": "2.0", "id": id, "method": method, "params": params})
	var err := _peer.send_text(request)
	if err != OK:
		push_error("rpc_env_review: send failed for %s" % method)
		return {}
	var deadline := Time.get_ticks_msec() + timeout_ms
	while Time.get_ticks_msec() < deadline:
		_peer.poll()
		_drain_messages()
		if _responses.has(id):
			var response: Dictionary = _responses[id]
			_responses.erase(id)
			if response.has("error"):
				return response
			return response.get("result", {}) if response.has("result") else response
		OS.delay_msec(10)
	push_error("rpc_env_review: timeout waiting for %s" % method)
	return {}
