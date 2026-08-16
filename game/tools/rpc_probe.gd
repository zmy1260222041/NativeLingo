extends SceneTree
const PORT := 6505
var _peer := WebSocketPeer.new()
var _id := 0
func _init() -> void:
	_peer.connect_to_url("ws://127.0.0.1:%d" % PORT)
func _process(_d: float) -> bool:
	_peer.poll()
	if _peer.get_ready_state() == WebSocketPeer.STATE_OPEN:
		for path in ["/root/Main/env_hut_residential_a", "/root/Main/env_hut_residential_b",
					"/root/Main/prp_crate_stack_a", "/root/Main/HUD", "/root/EnvDebugCamera"]:
			var r := _call("game.get_game_node_property", {"node_path": path, "property": "visible"})
			print("PROBE ", path, " -> ", JSON.stringify(r))
		var r2 := _call("game.get_node_properties", {"node_path": "/root/Main"})
		var kids: Array = []
		if r2.has("children"):
			kids = r2.children
		var names: Array = []
		for k in kids:
			names.append(String(k.get("name", "?")))
		print("MAIN_CHILDREN ", ", ".join(names))
		_peer.close()
	elif _peer.get_ready_state() == WebSocketPeer.STATE_CLOSED:
		quit(0)
	return false
func _call(method: String, params: Dictionary) -> Dictionary:
	_id += 1
	_peer.send_text(JSON.stringify({"jsonrpc": "2.0", "id": _id, "method": method, "params": params}))
	var deadline := Time.get_ticks_msec() + 8000
	while Time.get_ticks_msec() < deadline:
		_peer.poll()
		while _peer.get_available_packet_count() > 0:
			var parsed = JSON.parse_string(_peer.get_packet().get_string_from_utf8())
			if parsed is Dictionary and int(parsed.get("id", -1)) == _id:
				return parsed.get("result", {}) if parsed.has("result") else parsed
		OS.delay_msec(10)
	return {"timeout": true}
