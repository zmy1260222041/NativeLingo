extends SceneTree
const PORT := 6505
var _peer := WebSocketPeer.new()
var _id := 0
func _init() -> void:
	_peer.connect_to_url("ws://127.0.0.1:%d" % PORT)
func _process(_d: float) -> bool:
	_peer.poll()
	if _peer.get_ready_state() == WebSocketPeer.STATE_OPEN:
		var result := _call("game.env_stats", {})
		print("ENV_STATS ", JSON.stringify(result))
		var tree := _call("game.get_tree", {"max_depth": 2})
		var names := []
		if tree.has("nodes"):
			for n in tree.nodes:
				names.append(String(n.get("name", "?")))
		print("ROOT_CHILDREN ", ", ".join(names))
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
	return {}
