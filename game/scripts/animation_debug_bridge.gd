extends Node
## Local-only runtime bridge for animation debugging.
##
## The editor plugin owns the same ports while the editor is idle. When a game
## is running, the runtime bridge retries until it owns 6505/6506/6507 so the
## control, telemetry and test clients always talk to the process that owns
## the character.
##
## Web Beta 发布包不导出 addons/tools/tests，因此 addon 类只在桌面运行时按需
## load；Web 构建在 _ready 直接短路，不触碰这些资源。

const DebugLogClass = preload("res://scripts/debug_log.gd")

const CHANNEL_PORTS := {
	"control": 6505,
	"telemetry": 6506,
	"test": 6507,
}
const TELEMETRY_PATH := "user://logs/animation_telemetry.jsonl"
const ANIMATION_PROBE_CAPTURE_DIR := "user://logs/animation_probe"
const TEST_DIR := "user://mcp_tests"
const MAX_INLINE_TEST_BYTES := 256 * 1024
const DEFAULT_TELEMETRY_HZ := 30.0

var _servers: Dictionary = {}
var _runtime_commands: RefCounted
var _input_commands: RefCounted
var _characters: Array[Node] = []
var _log_events: Array[Dictionary] = []
var _max_log_events := 1000
var _telemetry_elapsed := 0.0
var _retry_elapsed := 0.0
var _telemetry_subscribers: Dictionary = {}
var _log_subscribers: Dictionary = {}
var _frozen := false
var _last_state: Dictionary = {}
var _test_results: Dictionary = {}
var _test_sequence := 0

func _ready() -> void:
	if OS.has_feature("web") or OS.has_feature("desktop_beta_no_voice"):
		# Web/Desktop 发布版不开放本地调试端口，也不做 30 Hz 采样与 user:// 日志写入。
		set_process(false)
		return
	_runtime_commands = (load("res://addons/godot_mcp/editors/runtime_commands.gd") as GDScript).new()
	_input_commands = (load("res://addons/godot_mcp/editors/input_commands.gd") as GDScript).new()
	DebugLogClass.set_file("user://logs/debug.log")
	DebugLogClass.info("debug_bridge", "runtime bridge starting ports=%s" % str(CHANNEL_PORTS))
	_open_available_servers()

func _exit_tree() -> void:
	for server in _servers.values():
		server.stop()
	_servers.clear()

func _process(delta: float) -> void:
	if OS.has_feature("web") or OS.has_feature("desktop_beta_no_voice"):
		return
	for channel in _servers.keys():
		_servers[channel].poll()
	_retry_elapsed += delta
	if _retry_elapsed >= 0.5:
		_retry_elapsed = 0.0
		_open_available_servers()
	_telemetry_elapsed += delta
	var interval := 1.0 / DEFAULT_TELEMETRY_HZ
	if _telemetry_elapsed >= interval:
		_telemetry_elapsed = fmod(_telemetry_elapsed, interval)
		_record_animation_frame()

func register_character(character: Node) -> void:
	if not _characters.has(character):
		_characters.append(character)
		character.tree_exited.connect(_on_character_exited.bind(character), CONNECT_ONE_SHOT)

func _on_character_exited(character: Node) -> void:
	_characters.erase(character)

func record_animation_transition(character: Node, animation_name: String, reason: String) -> void:
	_append_event({
		"type": "animation_transition",
		"time": Time.get_ticks_msec() / 1000.0,
		"animation": animation_name,
		"reason": reason,
		"state": _serialize(character.get_animation_debug_state()) if character.has_method("get_animation_debug_state") else {},
	})

func is_game_frozen() -> bool:
	return _frozen

func _open_available_servers() -> void:
	var websocket_server_class := load("res://addons/godot_mcp/websocket_server.gd") as GDScript
	if websocket_server_class == null:
		return
	for channel in CHANNEL_PORTS:
		if _servers.has(channel):
			continue
		var server = websocket_server_class.new()
		var err: Error = server.start(int(CHANNEL_PORTS[channel]))
		if err != OK:
			continue
		server.message_received.connect(_on_message_received.bind(channel))
		server.client_connected.connect(_on_client_connected.bind(channel))
		server.client_disconnected.connect(_on_client_disconnected.bind(channel))
		_servers[channel] = server
		DebugLogClass.info("debug_bridge", "channel=%s listening port=%d" % [channel, CHANNEL_PORTS[channel]])

func _on_client_connected(peer_id: int, channel: String) -> void:
	DebugLogClass.info("debug_bridge", "client connected channel=%s peer=%d" % [channel, peer_id])

func _on_client_disconnected(peer_id: int, channel: String) -> void:
	var key := _peer_key(channel, peer_id)
	_telemetry_subscribers.erase(key)
	_log_subscribers.erase(key)
	DebugLogClass.info("debug_bridge", "client disconnected channel=%s peer=%d" % [channel, peer_id])

func _on_message_received(peer_id: int, message: String, channel: String) -> void:
	var response := await _handle(message, channel, peer_id)
	if response.is_empty() or not _servers.has(channel):
		return
	_servers[channel].send_to(peer_id, response)

func _handle(message: String, channel: String, peer_id: int) -> String:
	var parsed = JSON.parse_string(message)
	if parsed == null or not parsed is Dictionary:
		return _error_response(null, -32700, "Parse error")
	var id = parsed.get("id", null)
	if parsed.get("jsonrpc", "") != "2.0":
		return _error_response(id, -32600, "Invalid Request: not JSON-RPC 2.0")
	var method := String(parsed.get("method", ""))
	var params: Dictionary = parsed.get("params", {})
	var result := await _route(method, params, channel, peer_id)
	if result.has("error"):
		return _error_response(id, int(result.error.code), String(result.error.message), result.error.get("data"))
	return JSON.stringify({"jsonrpc": "2.0", "id": id, "result": result.get("result", {})})

func _route(method: String, params: Dictionary, channel: String, peer_id: int) -> Dictionary:
	match method:
		"handshake":
			return {"result": {"version": "animation-debug-1", "channel": channel, "port": CHANNEL_PORTS[channel]}}
		"control.run":
			get_tree().paused = false
			return {"result": {"running": true}}
		"control.stop":
			get_tree().quit()
			return {"result": {"stopping": true}}
		"control.freeze":
			_frozen = bool(params.get("frozen", true))
			for player in get_tree().get_nodes_in_group("player"):
				if player.has_method("set_debug_frozen"):
					player.set_debug_frozen(_frozen)
			return {"result": {"frozen": _frozen}}
		"control.animation_probe":
			return await _animation_probe(params)
		"control.capture_sequence":
			var probe_params := params.duplicate(true)
			if String(probe_params.get("animation", "")).is_empty():
				probe_params["animation"] = String(_last_state.get("animation", "anim_chr_player_walk_forward"))
			return await _animation_probe(probe_params)
		"input.simulate_key":
			return _input_commands.simulate_key(params)
		"input.simulate_mouse_click":
			return _input_commands.simulate_mouse_click(params)
		"input.simulate_mouse_move":
			return _input_commands.simulate_mouse_move(params)
		"input.simulate_action":
			return _input_commands.simulate_action(params)
		"input.simulate_sequence":
			return _input_commands.simulate_sequence(params)
		"input.get_input_actions":
			return _input_commands.get_input_actions(params)
		"input.set_input_action":
			return _input_commands.set_input_action(params)
		"game.capture_frames":
			return _runtime_commands.capture_frames(params)
		"game.debug_view":
			return _debug_view(params)
		"game.restore_view":
			return _restore_view()
		"game.set_property":
			return _set_property(params)
		"game.env_stats":
			return _env_stats()
		"game.capture_view":
			return await _capture_view(params)
		"game.bring_to_front":
			DisplayServer.window_move_to_foreground(DisplayServer.MAIN_WINDOW_ID)
			return {"result": {"front": true}}
		"game.get_tree":
			return _runtime_commands.get_tree(params)
		"game.get_node_properties":
			return _runtime_commands.get_node_properties(params)
		"game.get_game_node_property":
			return _runtime_commands.get_game_node_property(params)
		"game.monitor_properties":
			return _runtime_commands.monitor_properties(params)
		"log.tail":
			return _log_tail(params)
		"log.subscribe":
			_log_subscribers[_peer_key(channel, peer_id)] = params.duplicate(true)
			return {"result": {"subscribed": true, "hz": DEFAULT_TELEMETRY_HZ}}
		"animation.get_state":
			return {"result": _last_state if not _last_state.is_empty() else _sample_character_state(params)}
		"animation.sample":
			# A requested bone set must be sampled live. Returning the cached
			# default frame here previously ignored hands/knees requested by the
			# three-port visual regression client.
			return {"result": _sample_character_state(params)}
		"animation.subscribe":
			_telemetry_subscribers[_peer_key(channel, peer_id)] = params.duplicate(true)
			return {"result": {"subscribed": true, "hz": params.get("hz", DEFAULT_TELEMETRY_HZ)}}
		"test.list":
			return _list_tests()
		"test.write_inline":
			return _write_inline_test(params)
		"test.run":
			return _run_test(params)
		"test.status", "test.result":
			return _test_status(params)
		"test.stop":
			return {"error": {"code": -32101, "message": "Synchronous test runs cannot be stopped after launch"}}
		_:
			return {"error": {"code": -32601, "message": "Method not found: %s" % method}}

func _animation_probe(params: Dictionary) -> Dictionary:
	var animation_name := String(params.get("animation", "anim_chr_player_walk_forward"))
	var frames := clampi(int(params.get("frames", 32)), 1, 600)
	var fps := clampf(float(params.get("fps", 30.0)), 1.0, 120.0)
	var blend := clampf(float(params.get("blend", 0.0)), 0.0, 1.0)
	var capture := bool(params.get("capture", false))
	var visual := _find_character()
	if visual == null or not visual.has_method("debug_play_animation"):
		return {"error": {"code": -32102, "message": "No runtime CharacterVisual found"}}
	if not visual.debug_play_animation(animation_name, blend):
		return {"error": {"code": -32103, "message": "Animation not found: %s" % animation_name}}
	var player := get_tree().get_first_node_in_group("player")
	var previously_frozen := _frozen
	_frozen = true
	if player != null and player.has_method("set_debug_frozen"):
		player.set_debug_frozen(true)
	var samples: Array = []
	for frame in frames:
		await get_tree().process_frame
		var sample := _sample_character_state(params)
		sample["frame"] = frame
		sample["animation_position"] = visual.get_animation_debug_state().get("animation_position", 0.0)
		if capture:
			var capture_result: Dictionary = _runtime_commands.capture_frames({})
			if capture_result.has("result"):
				sample["capture"] = _store_animation_probe_capture(capture_result.result, animation_name, frame)
		samples.append(sample)
		await get_tree().create_timer(1.0 / fps).timeout
	if visual.has_method("debug_clear_animation_override"):
		visual.debug_clear_animation_override()
	_frozen = previously_frozen
	if player != null and player.has_method("set_debug_frozen"):
		player.set_debug_frozen(previously_frozen)
	return {"result": {"animation": animation_name, "frames": samples.size(), "samples": samples}}

func _store_animation_probe_capture(payload: Dictionary, animation_name: String, frame: int) -> Dictionary:
	## Keep large JPEG payloads off the WebSocket response. Returning a numbered
	## local path makes multi-frame probes reliable and matches the protocol's
	## screenshot-index contract.
	if not payload.has("data"):
		return {}
	DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(ANIMATION_PROBE_CAPTURE_DIR))
	var safe_name := animation_name.replace("/", "_").replace(":", "_")
	var path := "%s/%s_%03d_%d.jpg" % [ANIMATION_PROBE_CAPTURE_DIR, safe_name, frame, Time.get_ticks_msec()]
	var bytes := Marshalls.base64_to_raw(String(payload.data))
	var file := FileAccess.open(path, FileAccess.WRITE)
	if file == null:
		return {}
	file.store_buffer(bytes)
	file.close()
	return {"frame": frame, "format": "jpg", "path": path, "bytes": bytes.size()}

func _find_character() -> Node:
	for character in _characters:
		if is_instance_valid(character):
			return character
	var candidates := get_tree().get_nodes_in_group("character_visual")
	return candidates[0] if not candidates.is_empty() else null

func _sample_character_state(_params: Dictionary) -> Dictionary:
	var visual := _find_character()
	if visual == null or not visual.has_method("get_animation_debug_state"):
		return {}
	var state: Dictionary = visual.get_animation_debug_state(_params.get("bones", []))
	var player := get_tree().get_first_node_in_group("player")
	if player != null and player.has_method("get_animation_debug_state"):
		state["player"] = player.get_animation_debug_state()
	return _serialize(state)

func _record_animation_frame() -> void:
	var visual := _find_character()
	if visual == null or not visual.has_method("get_animation_debug_state"):
		return
	_last_state = _sample_character_state({})
	_last_state["type"] = "animation_frame"
	_last_state["time"] = Time.get_ticks_msec() / 1000.0
	_append_event(_last_state)
	for key in _telemetry_subscribers:
		var channel := "telemetry"
		var peer_id := int(String(key).get_slice(":", 1))
		if _servers.has(channel):
			_servers[channel].send_to(peer_id, JSON.stringify({"jsonrpc": "2.0", "method": "animation.frame", "params": _last_state}))

func _append_event(event: Dictionary) -> void:
	_log_events.append(event)
	if _log_events.size() > _max_log_events:
		_log_events.pop_front()
	var file := FileAccess.open(TELEMETRY_PATH, FileAccess.READ_WRITE)
	if file == null:
		file = FileAccess.open(TELEMETRY_PATH, FileAccess.WRITE)
	if file != null:
		file.seek_end()
		file.store_line(JSON.stringify(_serialize(event)))
		file.flush()
	for key in _log_subscribers:
		var channel := "telemetry"
		var peer_id := int(String(key).get_slice(":", 1))
		if _servers.has(channel):
			_servers[channel].send_to(peer_id, JSON.stringify({"jsonrpc": "2.0", "method": "log.event", "params": _serialize(event)}))

func _log_tail(params: Dictionary) -> Dictionary:
	var count := clampi(int(params.get("lines", 100)), 1, _max_log_events)
	var start := maxi(0, _log_events.size() - count)
	return {"result": {"lines": _log_events.slice(start), "count": _log_events.size() - start, "source": TELEMETRY_PATH}}

func _list_tests() -> Dictionary:
	var tests: Array[String] = []
	var dir := DirAccess.open("res://tests")
	if dir == null:
		return {"result": {"tests": tests}}
	dir.list_dir_begin()
	var entry := dir.get_next()
	while not entry.is_empty():
		if not dir.current_is_dir() and entry.ends_with(".gd"):
			tests.append("res://tests/" + entry)
		entry = dir.get_next()
	dir.list_dir_end()
	tests.sort()
	return {"result": {"tests": tests}}

func _write_inline_test(params: Dictionary) -> Dictionary:
	var filename := String(params.get("filename", "mcp_test.gd"))
	if filename.is_empty() or filename.contains("/") or filename.contains("\\") or filename.contains(".."):
		return {"error": {"code": -32104, "message": "filename must be a simple .gd filename"}}
	if not filename.ends_with(".gd"):
		filename += ".gd"
	var content := String(params.get("content", ""))
	if content.to_utf8_buffer().size() > MAX_INLINE_TEST_BYTES:
		return {"error": {"code": -32105, "message": "inline test is too large"}}
	DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(TEST_DIR))
	var path := TEST_DIR + "/" + filename
	var file := FileAccess.open(path, FileAccess.WRITE)
	if file == null:
		return {"error": {"code": -32106, "message": "cannot write inline test"}}
	file.store_string(content)
	file.close()
	return {"result": {"path": path, "bytes": content.to_utf8_buffer().size()}}

func _run_test(params: Dictionary) -> Dictionary:
	var path := String(params.get("path", ""))
	if path.is_empty() or (not path.begins_with("res://tests/") and not path.begins_with(TEST_DIR + "/")):
		return {"error": {"code": -32107, "message": "test path must be under res://tests or user://mcp_tests"}}
	if path.contains("..") or not FileAccess.file_exists(path):
		return {"error": {"code": -32108, "message": "test file not found or invalid"}}
	_test_sequence += 1
	var run_id := "test-%d" % _test_sequence
	var output: Array = []
	var args := PackedStringArray(["--headless", "--path", ProjectSettings.globalize_path("res://"), "--script", ProjectSettings.globalize_path(path)])
	var exit_code := OS.execute(OS.get_executable_path(), args, output, true, false)
	var result := {
		"run_id": run_id,
		"path": path,
		"exit_code": exit_code,
		"passed": exit_code == 0,
		"output": output,
	}
	_test_results[run_id] = result
	return {"result": result}

func _test_status(params: Dictionary) -> Dictionary:
	var run_id := String(params.get("run_id", ""))
	if run_id.is_empty():
		return {"result": {"runs": _test_results.values()}}
	if not _test_results.has(run_id):
		return {"error": {"code": -32109, "message": "unknown run_id: %s" % run_id}}
	return {"result": _test_results[run_id]}

func _peer_key(channel: String, peer_id: int) -> String:
	return "%s:%d" % [channel, peer_id]

func _serialize(value: Variant) -> Variant:
	if value is Vector3:
		return [value.x, value.y, value.z]
	if value is Quaternion:
		return [value.x, value.y, value.z, value.w]
	if value is Transform3D:
		return {"origin": _serialize(value.origin), "basis": _serialize(value.basis)}
	if value is Basis:
		return {"x": _serialize(value.x), "y": _serialize(value.y), "z": _serialize(value.z)}
	if value is Dictionary:
		var result := {}
		for key in value:
			result[String(key)] = _serialize(value[key])
		return result
	if value is Array:
		return value.map(func(item): return _serialize(item))
	return value

func _error_response(id: Variant, code: int, message: String, data: Variant = null) -> String:
	var error := {"code": code, "message": message}
	if data != null:
		error["data"] = data
	return JSON.stringify({"jsonrpc": "2.0", "id": id, "error": error})


## --- Environment art review helpers (art-bible §8.8 multi-view audit) ---

func _parse_vec3(text: String) -> Variant:
	var parts := text.strip_edges().split(",")
	if parts.size() != 3:
		return null
	var values: Array[float] = []
	for part in parts:
		values.append(part.to_float())
	return Vector3(values[0], values[1], values[2])


func _debug_view(params: Dictionary) -> Dictionary:
	var position_value: Variant = _parse_vec3(String(params.get("position", "")))
	var look_value: Variant = _parse_vec3(String(params.get("look_at", "")))
	if position_value == null or look_value == null:
		return {"error": {"code": -32110, "message": "position/look_at must be 'x,y,z'"}}
	var cam := get_tree().root.get_node_or_null(^"EnvDebugCamera") as Camera3D
	if cam == null:
		cam = Camera3D.new()
		cam.name = "EnvDebugCamera"
		get_tree().root.add_child(cam)
	cam.position = position_value
	cam.look_at(look_value)
	if params.has("fov"):
		cam.fov = clampf(float(params.fov), 20.0, 120.0)
	cam.current = true
	var player := get_tree().get_first_node_in_group("player")
	if player != null and player.has_method("set_debug_frozen"):
		player.call("set_debug_frozen", true)
	return {"result": {
		"camera": "EnvDebugCamera",
		"position": [position_value.x, position_value.y, position_value.z],
		"look_at": [look_value.x, look_value.y, look_value.z],
	}}


func _restore_view() -> Dictionary:
	var cam := get_tree().root.get_node_or_null(^"EnvDebugCamera") as Camera3D
	if cam != null:
		cam.queue_free()
	var player := get_tree().get_first_node_in_group("player")
	if player != null:
		var player_cam := _find_camera(player)
		if player_cam != null:
			player_cam.current = true
		if player.has_method("set_debug_frozen"):
			player.call("set_debug_frozen", false)
	return {"result": {"restored": true}}


func _find_camera(node: Node) -> Camera3D:
	if node is Camera3D:
		return node as Camera3D
	for child in node.get_children():
		var found := _find_camera(child)
		if found != null:
			return found
	return null


func _set_property(params: Dictionary) -> Dictionary:
	var node_path := String(params.get("node_path", ""))
	var property := String(params.get("property", ""))
	var value: Variant = params.get("value", null)
	var target := get_tree().root.get_node_or_null(NodePath(node_path))
	if target == null:
		return {"error": {"code": -32111, "message": "node not found: %s" % node_path}}
	if property.is_empty() or not property in target:
		return {"error": {"code": -32112, "message": "property not found: %s" % property}}
	target.set(property, value)
	return {"result": {"node": node_path, "property": property, "value": value}}


func _env_stats() -> Dictionary:
	var counters := {"meshes": 0, "lights": 0, "draw": 0}
	for node in get_tree().root.get_children():
		_count_env_nodes(node, counters)
	return {"result": {
		"meshes": counters.meshes,
		"lights": counters.lights,
		"draw_estimate": counters.draw,
	}}


func _count_env_nodes(node: Node, counters: Dictionary) -> void:
	if node is MeshInstance3D:
		counters.meshes = int(counters.meshes) + 1
		var mi := node as MeshInstance3D
		if mi.visible and mi.mesh != null:
			counters.draw = int(counters.draw) + mi.mesh.get_surface_count()
	if node is Light3D:
		counters.lights = int(counters.lights) + 1
	for child in node.get_children():
		_count_env_nodes(child, counters)


## Offscreen multi-view capture: renders through a SubViewport so screenshots
## never depend on the game window being visible/occluded (the root-window
## texture readback stalls when macOS stops compositing the window).
func _capture_view(params: Dictionary) -> Dictionary:
	var position_value: Variant = _parse_vec3(String(params.get("position", "")))
	var look_value: Variant = _parse_vec3(String(params.get("look_at", "")))
	if position_value == null or look_value == null:
		return {"error": {"code": -32110, "message": "position/look_at must be 'x,y,z'"}}
	var vp := get_tree().root.get_node_or_null(^"EnvReviewViewport") as SubViewport
	if vp == null:
		vp = SubViewport.new()
		vp.name = "EnvReviewViewport"
		vp.size = Vector2i(1280, 800)
		vp.render_target_update_mode = SubViewport.UPDATE_ONCE
		get_tree().root.add_child(vp)
		var cam := Camera3D.new()
		cam.name = "ReviewCamera"
		vp.add_child(cam)
	var camera := vp.get_node(^"ReviewCamera") as Camera3D
	camera.position = position_value
	camera.look_at(look_value)
	camera.fov = clampf(float(params.get("fov", 60.0)), 20.0, 120.0)
	var player := get_tree().get_first_node_in_group("player")
	if player != null and player.has_method("set_debug_frozen"):
		player.call("set_debug_frozen", true)
	print("[capture_view] posing camera done")
	vp.render_target_update_mode = SubViewport.UPDATE_ONCE
	# bounded wait: frame_post_draw never fires while the window is fully
	# occluded (macOS stops compositing), so poll process frames instead
	for _i in range(6):
		await get_tree().process_frame
	print("[capture_view] frames awaited")
	var image := vp.get_texture().get_image()
	print("[capture_view] image=", image != null)
	if image == null:
		return {"error": {"code": -32113, "message": "subviewport capture returned no image"}}
	var max_dim := clampi(int(params.get("max_dim", 800)), 160, 1280)
	if image.get_width() > max_dim or image.get_height() > max_dim:
		var new_width := image.get_width()
		var new_height := image.get_height()
		if new_width > new_height:
			new_height = int(new_height * max_dim / float(new_width))
			new_width = max_dim
		else:
			new_width = int(new_width * max_dim / float(new_height))
			new_height = max_dim
		image.resize(new_width, new_height)
	# Write to disk and return the path only — large base64 responses get lost
	# on the WebSocket trip, and file delivery works with the window in background.
	var dir_path := OS.get_user_data_dir() + "/env_review"
	DirAccess.make_dir_recursive_absolute(dir_path)
	var file_name := String(params.get("name", "view_%d" % Time.get_ticks_msec()))
	if file_name.contains("/") or file_name.contains(".."):
		file_name = "view_safe"
	var out_path := dir_path + "/" + file_name + ".jpg"
	image.save_jpg(out_path)
	print("[capture_view] saved ", out_path)
	return {"result": {"format": "jpg", "path": out_path}}
